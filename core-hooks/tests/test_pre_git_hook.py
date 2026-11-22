import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "pre_git_hook.py"
CODEX_HOOKS = ROOT / "hooks" / "hooks.codex.json"
# A full head SHA for `gh pr merge --match-head-commit`.
SHA = "0123456789abcdef0123456789abcdef01234567"


def load_hook_module():
    spec = importlib.util.spec_from_file_location("pre_git_hook", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPT.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def run_hook_process(payload):
    # The timeout turns a regex that backtracks without end into a test error.
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )


def run_hook_raw(payload):
    result = run_hook_process(payload)
    assert result.returncode == 0, f"Hook failed (exit {result.returncode}): {result.stderr}"
    return result


def run_hook(payload):
    # Commands the hook ignores produce no stdout; use run_hook_raw for those.
    return json.loads(run_hook_raw(payload).stdout)


def run_blocked_hook(payload):
    result = run_hook_process(payload)
    assert result.returncode == 2, (
        f"Hook allowed or failed open (exit {result.returncode}): {result.stderr}"
    )
    assert result.stderr.strip(), "Blocked hook must explain the denial on stderr"
    return result


def codex_payload(cmd):
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "exec_command",
        "tool_input": {"cmd": cmd},
    }


class PreGitHookTests(unittest.TestCase):
    def assertReminds(self, response, title):
        """Check that the hook allows the command and shows the reminder to the
        user (`systemMessage`) and to the agent (`additionalContext`)."""
        output = response["hookSpecificOutput"]
        self.assertEqual(output["hookEventName"], "PreToolUse")
        self.assertNotIn("permissionDecision", output)
        self.assertIn(title, output["additionalContext"])
        self.assertEqual(response["systemMessage"], output["additionalContext"])

    def test_monitor_command_gets_the_bash_result(self):
        # The Claude Code Monitor tool runs its `command` as a shell script
        # (#527).
        for command, status in (
            ("git add .", 2),
            ("git add --all", 2),
            ("git switch -c no-prefix", 2),
            ("git status", 0),
        ):
            results = {
                tool: run_hook_process({
                    "hook_event_name": "PreToolUse",
                    "tool_name": tool,
                    "tool_input": {"command": command},
                })
                for tool in ("Bash", "Monitor")
            }
            with self.subTest(command=command):
                monitor, bash = results["Monitor"], results["Bash"]
                self.assertEqual(monitor.returncode, status, monitor.stderr)
                self.assertEqual(
                    (monitor.returncode, monitor.stdout, monitor.stderr),
                    (bash.returncode, bash.stdout, bash.stderr),
                )
        result = run_hook_process({
            "hook_event_name": "PreToolUse",
            "tool_name": "Monitor",
            "tool_input": {"command": "git add ."},
        })
        self.assertIn("Bulk git add operations are prohibited", result.stderr)

    def test_allows_monitor_without_a_command(self):
        result = run_hook_raw({
            "hook_event_name": "PreToolUse",
            "tool_name": "Monitor",
            "tool_input": {
                "ws": {"url": "wss://events.example.invalid/stream"},
                "description": "events",
                "timeout_ms": 1000,
            },
        })
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")

    def test_blocks_invalid_grok_branch_name(self):
        result = run_blocked_hook(
            {
                "hookEventName": "PreToolUse",
                "toolName": "run_terminal_command",
                "toolInput": {"command": "git switch -c grok-plugin-support"},
            }
        )

        self.assertIn("Branch name must start with one of", result.stderr)

    def test_blocks_grok_bulk_git_add(self):
        result = run_blocked_hook(
            {
                "hookEventName": "PreToolUse",
                "toolName": "run_terminal_command",
                "toolInput": {"command": "git add --all"},
            }
        )

        self.assertIn("Bulk git add operations are prohibited", result.stderr)

    def test_blocks_grok_attribution_in_commit(self):
        result = run_blocked_hook(
            {
                "hookEventName": "PreToolUse",
                "toolName": "run_terminal_command",
                "toolInput": {
                    "command": 'git commit -m "Generated with Claude Code"'
                },
            }
        )

        self.assertIn("AI tool attribution detected", result.stderr)

    def test_blocks_grok_attribution_in_pull_request_comment(self):
        result = run_blocked_hook(
            {
                "hookEventName": "PreToolUse",
                "toolName": "run_terminal_command",
                "toolInput": {
                    "command": 'gh pr comment 187 --body "Generated by Codex"'
                },
            }
        )

        self.assertIn("AI tool attribution detected", result.stderr)

    def test_allows_valid_grok_branch_name(self):
        result = run_hook_process(
            {
                "hookEventName": "PreToolUse",
                "toolName": "run_terminal_command",
                "toolInput": {"command": "git switch -c feat-187-grok-hooks"},
            }
        )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_prefers_existing_snake_case_payload_fields(self):
        result = run_hook_process(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "git switch -c feat-187-grok-hooks"},
                "toolName": "run_terminal_command",
                "toolInput": {"command": "git switch -c invalid-branch"},
            }
        )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_allows_malformed_grok_tool_input(self):
        result = run_hook_process(
            {
                "hookEventName": "PreToolUse",
                "toolName": "run_terminal_command",
                "toolInput": ["git", "switch", "-c", "invalid-branch"],
            }
        )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_blocks_invalid_codex_exec_command_branch_name(self):
        result = run_blocked_hook(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "exec_command",
                "tool_input": {"cmd": "git switch -c codex-plugin-support"},
            }
        )

        self.assertIn("codex-plugin-support", result.stderr)

    # --- Issue #104: bare branch listing in a compound command ---

    def test_bare_branch_listing_in_compound_command_is_allowed(self):
        # `git branch` (no args) followed by another command must not be
        # misread as creating a branch named after the next command's token.
        result = run_hook_raw(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "git branch\ngit status -sb"},
            }
        )
        self.assertEqual(result.stdout.strip(), "")

    def test_invalid_branch_on_same_line_still_blocked(self):
        # The cross-line fix must not weaken real same-line detection.
        result = run_blocked_hook(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "git branch badname"},
            }
        )
        self.assertIn("badname", result.stderr)

    # --- Issue #105: AI attribution in gh pr edit / comment ---

    def test_blocks_attribution_in_gh_pr_edit(self):
        result = run_blocked_hook(
            {
                "tool_name": "Bash",
                "tool_input": {"command": 'gh pr edit 1 --body "Generated with Claude Code"'},
            }
        )
        self.assertIn("AI tool attribution detected", result.stderr)

    def test_blocks_attribution_in_gh_pr_comment(self):
        result = run_blocked_hook(
            {
                "tool_name": "Bash",
                "tool_input": {"command": 'gh pr comment 1 --body "noreply@anthropic.com"'},
            }
        )
        self.assertIn("AI tool attribution detected", result.stderr)

    def test_clean_gh_pr_edit_is_allowed(self):
        response = run_hook(
            {
                "tool_name": "Bash",
                "tool_input": {"command": 'gh pr edit 1 --body "Fix typo in README"'},
            }
        )
        # Advisory message fires, but the operation is not denied.
        self.assertReminds(response, "Contribution Guidelines")

    def test_blocks_attribution_despite_spaces_and_global_flags(self):
        # The guard must survive extra whitespace and gh global flags placed
        # before the `pr` subcommand (e.g. `gh -R owner/repo pr edit`).
        for command in [
            'gh  pr  edit 1 --body "Generated with Claude Code"',
            'gh -R owner/repo pr edit 1 --body "Generated with Claude Code"',
        ]:
            with self.subTest(command=command):
                result = run_blocked_hook(
                    {"tool_name": "Bash", "tool_input": {"command": command}}
                )
                self.assertIn("AI tool attribution detected", result.stderr)

    def test_clean_git_commit_gets_advisory(self):
        # The other half of is_contribution_cmd: a clean commit is allowed with
        # the advisory, not denied or silently passed.
        response = run_hook(
            {
                "tool_name": "Bash",
                "tool_input": {"command": 'git commit -m "Fix typo in README"'},
            }
        )
        self.assertReminds(response, "Contribution Guidelines")

    def test_blocks_attribution_in_gh_pr_review(self):
        result = run_blocked_hook(
            {
                "tool_name": "Bash",
                "tool_input": {"command": 'gh pr review 1 --comment --body "Generated with Claude Code"'},
            }
        )
        self.assertIn("AI tool attribution detected", result.stderr)

    def test_blocks_attribution_in_compound_edit_then_merge(self):
        # A merge advisory must not short-circuit the attribution deny when both
        # appear in one compound command.
        result = run_blocked_hook(
            {
                "tool_name": "Bash",
                "tool_input": {"command": 'gh pr edit 1 --body "Generated with Claude Code" && gh pr merge 1'},
            }
        )
        self.assertIn("AI tool attribution detected", result.stderr)

    # --- #104 regressions: rename, tabs, worktree in compound commands ---

    def test_rename_to_invalid_branch_is_blocked(self):
        result = run_blocked_hook(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "git branch -m old-name badname"},
            }
        )
        self.assertIn("badname", result.stderr)

    def test_rename_to_valid_branch_is_allowed(self):
        # A valid branch name emits the "good practice" advisory (non-empty
        # JSON, no deny), so run_hook is safe here — the path is not silent.
        response = run_hook(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "git branch -m old-name feat-42-new"},
            }
        )
        self.assertNotIn("hookSpecificOutput", response)

    def test_tab_separator_is_still_detected(self):
        result = run_blocked_hook(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "git switch -c\tbadname"},
            }
        )
        self.assertIn("badname", result.stderr)

    def test_worktree_add_in_compound_uses_path_not_next_token(self):
        # Before the fix, the separator before the branch group matched the
        # newline and captured "git" from the next command. Now the worktree's
        # own path basename is used, so a valid prefix is allowed. The basename
        # is valid, so the hook emits the advisory (non-empty JSON) — run_hook
        # is safe here.
        response = run_hook(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "git worktree add ../trees/feat-99-x\ngit status"},
            }
        )
        self.assertNotIn("hookSpecificOutput", response)

    # --- Issue #107: per-command parsing of compound commands ---

    def test_split_commands_is_quote_aware(self):
        split = load_hook_module().split_commands
        # Segments are returned stripped of surrounding whitespace.
        self.assertEqual(split("git branch -l; git branch x"), ["git branch -l", "git branch x"])
        self.assertEqual(split("a && b | c"), ["a", "b", "c"])
        # A separator inside double or single quotes must not create a segment.
        self.assertEqual(split('git commit -m "a; b"'), ['git commit -m "a; b"'])
        self.assertEqual(split("git commit -m 'a; b'"), ["git commit -m 'a; b'"])
        # A backslash-escaped quote must not desync quote state.
        self.assertEqual(split('git commit -m "a\\"b"; ls'), ['git commit -m "a\\"b"', 'ls'])
        # `&` inside a redirection token is not a command boundary.
        self.assertEqual(split("git status 2>&1"), ["git status 2>&1"])
        self.assertEqual(split("git checkout -b feat-1-x &>log"), ["git checkout -b feat-1-x &>log"])

    def test_listing_then_invalid_creation_in_compound_is_blocked(self):
        # The read-only listing must not mask the later invalid creation.
        result = run_blocked_hook(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "git branch -l; git branch badname"},
            }
        )
        self.assertIn("badname", result.stderr)

    def test_valid_then_invalid_creation_in_compound_is_blocked(self):
        # An earlier valid creation must not mask a later invalid one.
        result = run_blocked_hook(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "git checkout -b feat-1-a && git checkout -b badname"},
            }
        )
        self.assertIn("badname", result.stderr)

    def test_two_valid_creations_in_compound_are_allowed(self):
        response = run_hook(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "git checkout -b feat-1-a && git checkout -b feat-2-b"},
            }
        )
        self.assertNotIn("hookSpecificOutput", response)

    def test_escaped_quote_does_not_mask_invalid_branch(self):
        # An escaped quote in a commit message must not desync the splitter and
        # swallow a later invalid creation into a read-only segment (#107).
        result = run_blocked_hook(
            {
                "tool_name": "Bash",
                "tool_input": {"command": 'git commit -m "a\\"b" ; git branch -l ; git branch badname'},
            }
        )
        self.assertIn("badname", result.stderr)

    def test_line_continuation_does_not_mask_invalid_branch(self):
        # A backslash-newline continuation must not join two commands into one
        # segment, which would let a later valid creation mask the invalid one.
        result = run_blocked_hook(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "git branch bad \\\ngit checkout -b feat-1-x"},
            }
        )
        self.assertIn("bad", result.stderr)

    def test_first_invalid_branch_is_reported(self):
        # When several invalid branches appear, the first is surfaced; the
        # command is denied regardless of how many follow.
        result = run_blocked_hook(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "git branch bad1 && git branch bad2"},
            }
        )
        self.assertIn("bad1", result.stderr)

    def test_logical_or_separates_commands(self):
        # `||` splits on each `|`, so an invalid creation after it is caught.
        result = run_blocked_hook(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "git branch -l || git branch badname"},
            }
        )
        self.assertIn("badname", result.stderr)

    def test_redirection_ampersand_does_not_mask_branch_creation(self):
        # `&` in a redirection (2>&1, &>file) is not a command boundary, so an
        # invalid creation with redirected output is still caught.
        for command in [
            "git checkout -b badname 2>&1",
            "git checkout -b badname &>log",
        ]:
            with self.subTest(command=command):
                result = run_blocked_hook(
                    {"tool_name": "Bash", "tool_input": {"command": command}}
                )
                self.assertIn("badname", result.stderr)

    # --- #236 regressions: product names are not attribution ---

    def test_allows_descriptive_ai_tool_mention_in_commit(self):
        # This repository develops Claude Code and Codex plugins, so a tool
        # name in a commit message describes the change (issue #236).
        for command in [
            'git commit -m "Add a skill that backs up the global Claude Code instruction file"',
            'git commit -m "core-hooks: document the Codex CLI hook payload"',
            'git commit -m "Support Claude Code and Codex marketplace registries"',
        ]:
            with self.subTest(command=command):
                response = run_hook(
                    {"tool_name": "Bash", "tool_input": {"command": command}}
                )
                self.assertReminds(response, "Contribution Guidelines")

    def test_allows_descriptive_ai_tool_mention_in_pull_request_body(self):
        response = run_hook(
            {
                "tool_name": "Bash",
                "tool_input": {
                    "command": 'gh pr create --title "Add Codex CLI support" --body "Ship the Claude Code hooks for the Codex CLI."'
                },
            }
        )
        self.assertReminds(response, "Contribution Guidelines")

    def test_merge_without_squash_gets_a_reminder(self):
        response = run_hook(
            {"tool_name": "Bash", "tool_input": {"command": f"gh pr merge 1 --merge --match-head-commit {SHA}"}}
        )
        self.assertReminds(response, "Merge Strategy")

    def test_reminder_reaches_the_agent_after_a_valid_branch(self):
        response = run_hook(
            {
                "tool_name": "Bash",
                "tool_input": {"command": 'git checkout -b feat-1-x && git commit -m "Fix typo"'},
            }
        )
        self.assertReminds(response, "Contribution Guidelines")

    def test_squash_merge_gets_no_reminder(self):
        result = run_hook_raw(
            {"tool_name": "Bash", "tool_input": {"command": f"gh pr merge 1 --squash --match-head-commit {SHA}"}}
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "")

    def test_blocks_attribution_forms(self):
        for message in [
            "Generated with [Claude Code](https://claude.com/claude-code)",
            "Created by Claude",
            "Written with Codex CLI",
            "Co-authored by Codex",
            "Co-Authored-By: Claude <claude@example.invalid>",
            "See https://claude.ai/code for details",
            "Reported-by: agent <noreply@anthropic.com>",
        ]:
            with self.subTest(message=message):
                result = run_blocked_hook(
                    {
                        "tool_name": "Bash",
                        "tool_input": {
                            "command": f'git commit -m "Fix typo" -m "{message}"'
                        },
                    }
                )
                self.assertIn("AI tool attribution detected", result.stderr)

    def test_allows_human_co_author_trailer(self):
        response = run_hook(
            {
                "tool_name": "Bash",
                "tool_input": {
                    "command": 'git commit -m "Fix typo" -m "Co-Authored-By: Jamie Doe <jamie@example.invalid>"'
                },
            }
        )
        self.assertReminds(response, "Contribution Guidelines")

    # --- #280: attribution checks stay linear on long commands ---

    def test_blocks_attribution_after_an_earlier_trailer_or_gh_word(self):
        # The patterns search on from the first trailer on a line and the first
        # `gh` word in a command segment, so later text must still count.
        for command in [
            'git commit -m "Fix typo" -m "Co-Authored-By: Jamie Doe, Co-Authored-By: Claude"',
            'echo gh; gh pr edit 1 --body "Generated with Claude Code"',
            'GH_REPO=cli/gh gh pr edit 1 --body "Generated with Claude Code"',
        ]:
            with self.subTest(command=command):
                result = run_blocked_hook(
                    {"tool_name": "Bash", "tool_input": {"command": command}}
                )
                self.assertIn("AI tool attribution detected", result.stderr)

    def test_reads_long_attribution_lookalikes_quickly(self):
        # A failed search must not rescan the rest of the line or segment from
        # each trailer or `gh` word. That quadratic search took about 200 s on
        # each command, past the process timeout.
        with self.subTest("trailers"):
            command = 'git commit -m "' + "Co-Authored-By: x " * 25000 + '"'
            response = run_hook({"tool_name": "Bash", "tool_input": {"command": command}})
            self.assertIn("Contribution Guidelines", response.get("systemMessage", ""))
        with self.subTest("gh words"):
            command = "gh pr " * 50000
            result = run_hook_raw({"tool_name": "Bash", "tool_input": {"command": command}})
            self.assertEqual(result.stdout.strip(), "")

    # --- #262: only a real `git add` invocation is a bulk add ---

    def test_allows_bulk_add_text_in_heredoc_body(self):
        # A heredoc body is data, even when a line looks like a command.
        for command in [
            "python3 - <<'EOF'\nprint('git add -A')\nEOF",
            "cat > notes.md <<'EOF'\ngit add .\nEOF",
            "cat <<EOF > notes.md\ngit add --all && git add ./\nEOF\ngit status",
            # The usual commit form: a heredoc in a quoted substitution.
            "git commit -m \"$(cat <<'EOF'\nfix: explain the policy\n\ngit add -A stages every file.\nEOF\n)\"",
        ]:
            with self.subTest(command=command):
                run_hook_raw({"tool_name": "Bash", "tool_input": {"command": command}})

    def test_allows_bulk_add_text_in_quoted_argument(self):
        # A separator inside quotes does not start a command, and a quoted
        # line break does not either.
        for command in [
            'git commit -m "Block git add -A in the hook"',
            "git commit -m 'Explain why git add . is blocked'",
            'echo "stage files; git add --all"',
            'gh pr comment 1 --body "Do not run git add ./"',
            'git commit -m "Subject\ngit add -A\n"',
        ]:
            with self.subTest(command=command):
                run_hook_raw({"tool_name": "Bash", "tool_input": {"command": command}})

    def test_blocks_real_bulk_add_in_simple_and_compound_commands(self):
        for command in [
            "git add -A",
            "git add --all",
            "git add .",
            "git add ./",
            "git status && git add -A",
            "git status || git add .",
            "cd repo; git add --all",
            "echo x | git add ./",
            "git status & git add .",
            "git status\ngit add -A && git commit -m 'x'",
            "git add .>/dev/null",
            # A bulk add after a heredoc body is a real command.
            "cat <<'EOF' > notes.md\ngit add -A\nEOF\ngit add .",
            # An apostrophe in the body must not hide the command after it.
            "cat <<EOF > notes.md\ndon't stage\nEOF\ngit add -A",
            # Grouping and control keywords come before a command word.
            "(git add .)",
            "{ git add ./; }",
            "if true; then git add -A; fi",
            "for f in a; do git add .; done",
            "! git add --all",
            "time git add -A",
            # W3-25 g16 and g17: git global options, `--`, and other forms.
            "git -C trees/doc-x add .",
            "git add -- .",
            "git add :/",
            'git add "."',
            "git -C trees/doc-x add -A",
            "git add -Av",
            "GIT_DIR=.git git add .",
        ]:
            with self.subTest(command=command):
                result = run_blocked_hook(
                    {"tool_name": "Bash", "tool_input": {"command": command}}
                )
                self.assertIn("Bulk git add operations are prohibited", result.stderr)

    def test_codex_exec_command_uses_the_same_bulk_add_rule(self):
        run_hook_raw(codex_payload('git commit -m "Block git add -A in the hook"'))
        result = run_blocked_hook(codex_payload("git status && git add -A"))
        self.assertIn("Bulk git add operations are prohibited", result.stderr)

    def test_allows_named_files_and_scoped_adds(self):
        for command in [
            "git add .gitignore",
            "git add ./src/file.py",
            "git add -- README.md",
            # W3-25 g15: `-A` with a pathspec stages no more than the pathspec.
            "git add -A docs/",
            "git add --all -- docs/",
            "git -C trees/doc-x add README.md",
        ]:
            with self.subTest(command=command):
                run_hook_raw({"tool_name": "Bash", "tool_input": {"command": command}})

    # --- #272: only a real git command creates a branch ---

    def test_allows_branch_creation_text_in_heredoc_body(self):
        # A heredoc body is data, even when a line looks like a command.
        for command in [
            "cat > notes.md <<EOF\ngit checkout -b badname\nEOF",
            "cat > notes.md <<'EOF'\ngit switch -c badname\nEOF",
            "python3 - <<'EOF'\nrun('git worktree add trees/badname')\nEOF",
            "cat <<EOF > notes.md\ngit branch badname && git branch -m a badname\nEOF\ngit status",
        ]:
            with self.subTest(command=command):
                run_hook_raw({"tool_name": "Bash", "tool_input": {"command": command}})

    def test_allows_branch_creation_text_in_quoted_argument(self):
        # A quoted argument stays in the segment of the command that owns it.
        for command in [
            "python3 -c \"print('git checkout -b badname')\"",
            'echo "x; git checkout -b badname"',
            "gh issue create --body 'run git switch -c badname'",
            'git commit -m "Explain why git branch badname fails"',
            'git commit -m "Subject\ngit worktree add trees/badname\n"',
        ]:
            with self.subTest(command=command):
                run_hook_raw({"tool_name": "Bash", "tool_input": {"command": command}})

    def test_blocks_branch_creation_at_command_start(self):
        for command in [
            # A creation after a heredoc body is a real command.
            "cat <<'EOF' > notes.md\nhi\nEOF\ngit checkout -b badname",
            "cat <<EOF > notes.md\ndon't stop\nEOF\ngit switch -c badname",
            # A pipe or a background `&` also starts a command.
            "git status | git branch badname",
            "sleep 1 & git checkout -b badname",
            # Grouping and control keywords come before a command word.
            "(git checkout -b badname)",
            "{ git branch badname; }",
            "if true; then git switch -c badname; fi",
            "for f in a; do git worktree add trees/badname; done",
            "! git branch -m old badname",
            "time git checkout -b badname",
        ]:
            with self.subTest(command=command):
                result = run_blocked_hook(
                    {"tool_name": "Bash", "tool_input": {"command": command}}
                )
                self.assertIn("Branch name 'badname' is invalid", result.stderr)

    def test_allows_valid_worktree_branch_after_options(self):
        # An option or a redirection is not the path or the commit-ish, so the
        # valid name is checked and the naming advisory fires.
        for command in [
            "git worktree add -q trees/bugfix-1-x -b bugfix-1-x",
            "git worktree add -f --lock trees/x -b feat-1-x",
            "git worktree add --lock --reason 'ci build' trees/feat-1-x",
            "git worktree add --quiet -b feat-1-x trees/x",
            "git worktree add -q trees/feat-1-x/",
            "git worktree add -q trees/feat-1-x > log.txt 2>&1",
        ]:
            with self.subTest(command=command):
                response = run_hook(
                    {"tool_name": "Bash", "tool_input": {"command": command}}
                )
                self.assertIn("Branch Naming Convention", response.get("systemMessage", ""))

    def test_allows_detached_worktree(self):
        # A detached worktree creates no branch.
        for command in [
            "git worktree add --detach trees/x",
            "git worktree add -d trees/x HEAD~1",
            "git worktree add -fd trees/badname",
        ]:
            with self.subTest(command=command):
                result = run_hook_raw(
                    {"tool_name": "Bash", "tool_input": {"command": command}}
                )
                self.assertEqual(result.stdout.strip(), "")

    def test_blocks_invalid_worktree_branch_after_options(self):
        for command in [
            "git worktree add -q trees/x -b badname",
            "git worktree add -q -B badname trees/feat-1-x",
            "git worktree add -q trees/badname",
            "git worktree add --lock --reason 'keep it' trees/badname",
            "git worktree add trees/badname/",
        ]:
            with self.subTest(command=command):
                result = run_blocked_hook(
                    {"tool_name": "Bash", "tool_input": {"command": command}}
                )
                self.assertIn("Branch name 'badname' is invalid", result.stderr)

    def test_blocks_invalid_branch_after_git_global_options(self):
        for command in [
            "git -C /repo checkout -b badname",
            "git -C /repo switch -c badname",
            "git -C /repo worktree add trees/x -b badname",
            'git -C "my repo" branch badname',
            "git -c core.hooksPath=/dev/null checkout -b badname",
            "git --git-dir=/repo/.git --work-tree=/repo branch badname",
            "git --git-dir /repo/.git branch -m old badname",
            "git --no-pager -C /repo switch -c badname",
            "cd /repo && git -C sub checkout -b badname",
        ]:
            with self.subTest(command=command):
                result = run_blocked_hook(
                    {"tool_name": "Bash", "tool_input": {"command": command}}
                )
                self.assertIn("Branch name 'badname' is invalid", result.stderr)

    def test_allows_valid_branch_after_git_global_options(self):
        for command in [
            "git -C /repo checkout -b feat-1-x",
            "git -C /repo worktree add -q trees/bugfix-1-x -b bugfix-1-x",
            "git -c user.name=x switch -c doc-1-x",
        ]:
            with self.subTest(command=command):
                response = run_hook(
                    {"tool_name": "Bash", "tool_input": {"command": command}}
                )
                self.assertIn("Branch Naming Convention", response.get("systemMessage", ""))

    def test_allows_read_only_branch_commands_after_git_global_options(self):
        for command in [
            "git -C /repo branch -l",
            "git -C /repo branch --delete feat-1-x",
            "git -C /repo checkout master",
        ]:
            with self.subTest(command=command):
                result = run_hook_raw(
                    {"tool_name": "Bash", "tool_input": {"command": command}}
                )
                self.assertEqual(result.stdout.strip(), "")

    def test_reads_many_git_global_options_quickly(self):
        # Option words that could also be option values must not make a
        # pattern that fails (here, checkout) backtrack exponentially.
        command = "git " + "-C -c --git-dir " * 30 + "branch badname"
        result = run_blocked_hook({"tool_name": "Bash", "tool_input": {"command": command}})
        self.assertIn("Branch name 'badname' is invalid", result.stderr)

    # --- #281: every branch creation form, quoted names, worktree commit-ish ---

    def test_blocks_invalid_name_in_checkout_and_switch_creation_forms(self):
        # Options can come before or after the creating option, and its value
        # can be separate, stuck, or follow a bundle of flags.
        for command in [
            "git checkout -B badname",
            "git checkout --orphan badname",
            "git checkout --orphan=badname",
            "git checkout -q -b badname",
            "git checkout --track -b badname origin/main",
            "git checkout -bbadname",
            "git checkout -qb badname",
            "git switch -C badname",
            "git switch --create badname",
            "git switch --create=badname",
            "git switch --force-create badname",
            "git switch --orphan badname",
            "git switch -q -c badname",
            "git switch --no-guess -c badname",
            "git switch -qc badname",
            "git -C /repo switch --create badname",
        ]:
            with self.subTest(command=command):
                result = run_blocked_hook(
                    {"tool_name": "Bash", "tool_input": {"command": command}}
                )
                self.assertIn("Branch name 'badname' is invalid", result.stderr)

    def test_allows_valid_name_in_checkout_and_switch_creation_forms(self):
        for command in [
            "git checkout -B feat-1-x",
            "git checkout -q -b bugfix-2-y",
            "git checkout --orphan=doc-3-z",
            "git switch --create refactor-4-w",
            "git switch -qc chore-5-v",
        ]:
            with self.subTest(command=command):
                response = run_hook(
                    {"tool_name": "Bash", "tool_input": {"command": command}}
                )
                self.assertIn("Branch Naming Convention", response.get("systemMessage", ""))

    def test_allows_checkout_and_switch_without_a_branch_creation(self):
        # After `--`, checkout reads paths, not options.
        for command in [
            "git checkout -q main",
            "git checkout -- -b",
            "git switch --detach HEAD~1",
            "git switch -",
        ]:
            with self.subTest(command=command):
                result = run_hook_raw(
                    {"tool_name": "Bash", "tool_input": {"command": command}}
                )
                self.assertEqual(result.stdout.strip(), "")

    def test_blocks_invalid_name_after_git_branch_creation_options(self):
        # git creates a branch for each of these forms (git 2.52).
        for command in [
            "git branch -f badname",
            "git branch --force badname",
            "git branch --force badname HEAD~1",
            "git branch --no-color badname",
            "git branch -i badname",
            "git branch --abbrev=7 badname",
            "git branch --sort=refname badname",
            "git branch --sort refname badname",
            "git branch --no-create-reflog badname",
            "git branch --track badname origin/main",
            "git branch --track=inherit badname origin/main",
            "git branch -t badname origin/main",
            "git branch --no-track badname origin/main",
            "git branch -q badname",
            "git branch -fq badname",
            "git branch -v badname",
            "git branch --create-reflog badname",
            "git branch -- badname",
            "git branch -f -m old badname",
            "git -C /repo branch -f badname",
        ]:
            with self.subTest(command=command):
                result = run_blocked_hook(
                    {"tool_name": "Bash", "tool_input": {"command": command}}
                )
                self.assertIn("Branch name 'badname' is invalid", result.stderr)

    def test_allows_valid_name_after_git_branch_creation_options(self):
        for command in [
            "git branch -f feat-1-x",
            "git branch --track bugfix-2-y origin/main",
            "git branch -M old doc-3-z",
        ]:
            with self.subTest(command=command):
                response = run_hook(
                    {"tool_name": "Bash", "tool_input": {"command": command}}
                )
                self.assertIn("Branch Naming Convention", response.get("systemMessage", ""))

    def test_allows_git_branch_commands_without_a_branch_creation(self):
        # These list, delete, or change upstream or description settings.
        for command in [
            "git branch -l",
            "git branch -l 'bad*'",
            "git branch --list 'bad*'",
            "git branch -vv",
            "git branch -D old",
            "git branch -D badname",
            "git branch -dr origin/badname",
            "git branch -a",
            "git branch -r",
            "git branch --contains HEAD",
            "git branch --no-contains HEAD",
            "git branch --merged main",
            "git branch --sort=-committerdate",
            "git branch --format '%(refname:short)'",
            "git branch -u origin/main",
            "git branch --set-upstream-to=origin/main badname",
            "git branch --unset-upstream badname",
            "git branch --edit-description",
            "git branch --show-current",
        ]:
            with self.subTest(command=command):
                result = run_hook_raw(
                    {"tool_name": "Bash", "tool_input": {"command": command}}
                )
                self.assertEqual(result.stdout.strip(), "")

    def test_blocks_quoted_invalid_name_without_its_quotes(self):
        # The shell removes one level of quotes, so git sees `badname`.
        for command in [
            'git checkout -b "badname"',
            "git switch -c 'badname'",
            'git branch "badname"',
            "git branch -m old 'badname'",
            'git worktree add -b "badname" trees/x',
            'git worktree add "trees/badname"',
            "git checkout -b bad\"name\"",
        ]:
            with self.subTest(command=command):
                result = run_blocked_hook(
                    {"tool_name": "Bash", "tool_input": {"command": command}}
                )
                self.assertIn("Branch name 'badname' is invalid", result.stderr)

    def test_allows_quoted_valid_name(self):
        for command in [
            'git checkout -b "feat-1-x"',
            "git switch -c 'bugfix-2-y'",
            'git branch -m old "doc-3-z"',
            "git checkout -b feat-\"1\"-x",
            'git worktree add "trees/feat-1-x"',
            "git worktree add -b 'feat-1-x' \"trees/x\"",
            'git checkout "-b" feat-1-x',
        ]:
            with self.subTest(command=command):
                response = run_hook(
                    {"tool_name": "Bash", "tool_input": {"command": command}}
                )
                self.assertIn("Branch Naming Convention", response.get("systemMessage", ""))

    def test_allows_worktree_from_a_commit_ish(self):
        # With a commit-ish, git makes a local branch only by copying the name
        # of an existing remote-tracking branch, which is not a branch
        # creation, and it ignores the path name.
        for command in [
            "git worktree add trees/x HEAD",
            "git worktree add trees/x origin/main",
            "git worktree add trees/x HEAD~1",
            "git worktree add trees/badname 1a2b3c4",
            "git worktree add trees/x main",
            "git worktree add -f trees/x main",
            "git worktree add trees/x v1.2.0",
        ]:
            with self.subTest(command=command):
                result = run_hook_raw(
                    {"tool_name": "Bash", "tool_input": {"command": command}}
                )
                self.assertEqual(result.stdout.strip(), "")

    def test_blocks_named_worktree_branch_with_a_commit_ish(self):
        for command in [
            "git worktree add -b badname trees/x origin/main",
            "git worktree add -qB badname trees/x HEAD",
            "git worktree add --orphan trees/badname",
        ]:
            with self.subTest(command=command):
                result = run_blocked_hook(
                    {"tool_name": "Bash", "tool_input": {"command": command}}
                )
                self.assertIn("Branch name 'badname' is invalid", result.stderr)

    def test_reads_many_options_and_quoted_parts_quickly(self):
        # Long runs of options or quoted parts must be read in linear time.
        for command in [
            "git checkout " + "-q " * 5000 + "-b badname",
            "git switch " + "--no-guess " * 5000 + "--create=badname",
            "git branch " + "-f " * 5000 + "badname",
            "git worktree add " + "--lock " * 5000 + "trees/badname",
            "git checkout -b bad" + '""' * 5000 + "name",
            "git checkout -b badname " + "'\"" * 5000,
        ]:
            with self.subTest(command=command[:40]):
                result = run_blocked_hook(
                    {"tool_name": "Bash", "tool_input": {"command": command}}
                )
                self.assertIn("Branch name 'badname' is invalid", result.stderr)
        # A long bundle of short options is read in linear time too; `-d` in
        # the bundle detaches the worktree.
        command = "git worktree add -" + "d" * 100000 + "1 trees/badname"
        result = run_hook_raw({"tool_name": "Bash", "tool_input": {"command": command}})
        self.assertEqual(result.stdout.strip(), "")

    def test_reads_no_words_after_a_shell_comment(self):
        # A word that starts with `#` starts a comment, so later words are not
        # arguments of the git command.
        result = run_hook_raw(
            {"tool_name": "Bash", "tool_input": {"command": "git checkout main # -b badname"}}
        )
        self.assertEqual(result.stdout.strip(), "")
        for command in [
            "git worktree add trees/badname # from main",
            "git branch badname # for the fix",
        ]:
            with self.subTest(command=command):
                result = run_blocked_hook(
                    {"tool_name": "Bash", "tool_input": {"command": command}}
                )
                self.assertIn("Branch name 'badname' is invalid", result.stderr)

    def test_codex_exec_command_checks_every_creation_form(self):
        result = run_hook_raw(codex_payload("git worktree add trees/x origin/main"))
        self.assertEqual(result.stdout.strip(), "")
        result = run_blocked_hook(codex_payload("git switch --create 'badname'"))
        self.assertIn("Branch name 'badname' is invalid", result.stderr)

    def test_codex_exec_command_uses_the_same_branch_rule(self):
        run_hook_raw(codex_payload("cat > notes.md <<'EOF'\ngit checkout -b badname\nEOF"))
        result = run_blocked_hook(codex_payload("git -C /repo checkout -b badname"))
        self.assertIn("Branch name 'badname' is invalid", result.stderr)

    def test_codex_hooks_match_exec_command_for_git_guard(self):
        hooks = json.loads(CODEX_HOOKS.read_text())
        matchers = [
            entry["matcher"]
            for entry in hooks["hooks"]["PreToolUse"]
            for hook in entry["hooks"]
            if "pre_git_hook.py" in hook["command"]
        ]

        self.assertTrue(
            any("exec_command" in matcher for matcher in matchers),
            f"pre_git_hook.py matcher should include exec_command, got {matchers}",
        )

    def test_blocks_git_grep_extended_regexp_with_a_plain_escape(self):
        # On macOS, `git grep -E` reads `\b` as a plain `b` (#389).
        result = run_blocked_hook(
            {"tool_name": "Bash", "tool_input": {"command": r"git grep -n -E '\bmockApi\b'"}}
        )
        self.assertIn(r"`\b`", result.stderr)
        self.assertIn("`-P`", result.stderr)

    def test_blocks_each_git_grep_extended_regexp_form(self):
        # Each command is denied; the value is the escape that the denial names.
        cases = {
            r"git grep -E 'call\sAPI'": r"\s",
            r"git grep --extended-regexp 'x\Sy'": r"\S",
            r"git grep -nE 'x\dy'": r"\d",
            r"git grep -P -E 'x\Dy'": r"\D",
            r"git grep -G -nE 'x\wy'": r"\w",
            r"git grep -iEn 'x\Wy'": r"\W",
            r"git grep -E -e foo -e '\Bx'": r"\B",
            r"git grep -Ee '\<word\>'": r"\<",
            r"git grep -E -e'word\>'": r"\>",
            r'git grep -E "\bword"': r"\b",
            r"git grep -E \\bword": r"\b",
            r"git grep -E -- '\bword'": r"\b",
            r"git grep -E -C 2 -m1 --max-depth 3 '\bword' -- src": r"\b",
            r"git -C /repo grep -E '\bword'": r"\b",
            r"git --no-pager grep -E '\bword'": r"\b",
            r"git status && git grep -E '\bword'": r"\b",
            r"false || git grep -E '\bword'": r"\b",
            r"cd /repo; git grep -E '\bword'": r"\b",
            r"echo x | git grep -E '\bword' | head": r"\b",
        }
        for command, escape in cases.items():
            for payload in (
                {"tool_name": "Bash", "tool_input": {"command": command}},
                codex_payload(command),
            ):
                with self.subTest(command=command, tool=payload["tool_name"]):
                    result = run_blocked_hook(payload)
                    self.assertIn(f"`{escape}`", result.stderr)
                    self.assertIn(r"word boundary as `\b`", result.stderr)

    def test_allows_git_grep_escapes_that_git_reads(self):
        for command in [
            r"git grep '\bmockApi\b'",
            r"git grep -G 'a\sb'",
            r"git grep -P '\bmockApi\b'",
            r"git grep -F '\bmockApi\b'",
            r"git grep -E -P 'x\dy'",
            r"git grep -PF -E -G '\bx'",
            r"git grep -E 'a\.b\(c\)d\+'",
            r"git grep -E 'a\\bc'",
            r"git grep -E \bword",
            r"git grep -E -e foo -- '\bdir'",
            r"git grep -E foo '\brev'",
            r"git grep -E -f patterns.txt",
            r"git grep -E -C 2 'x\.y'",
            r"grep -E '\bword'",
            r"echo 'git grep -E \b'",
            "cat <<'EOF'\ngit grep -E '\\bword'\nEOF",
            r"git commit -m 'Deny git grep -E \b'",
        ]:
            for payload in (
                {"tool_name": "Bash", "tool_input": {"command": command}},
                codex_payload(command),
            ):
                with self.subTest(command=command, tool=payload["tool_name"]):
                    result = run_hook_process(payload)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertNotIn("git grep -E", result.stderr)

    # --- #455: contribution commands, body files, and pinned merges ---

    def test_allows_attribution_text_outside_a_contribution_command(self):
        # W3-04 g11 and x11: a search or a script that only mentions a commit
        # and a trailer commits nothing.
        for command in [
            "git grep -n -E 'git commit.*Co-Authored-By: Claude' -- '*.md'",
            "python3 - <<'EOF'\nprint(\"git commit -m 'x' -m 'Co-Authored-By: Claude'\")\nEOF",
        ]:
            with self.subTest(command=command):
                run_hook_raw({"tool_name": "Bash", "tool_input": {"command": command}})

    def test_blocks_attribution_in_each_contribution_command(self):
        trailer = "Co-Authored-By: Claude <noreply@anthropic.com>"
        link = "Generated with [Claude Code](https://claude.com/claude-code)"
        for command in [
            f"git commit -F - <<'EOF'\nFix typo\n\n{trailer}\nEOF",
            f'git -C trees/doc-x commit -m "Fix typo" -m "{trailer}"',
            f'GIT_AUTHOR_DATE=now git commit -m "Fix typo" -m "{trailer}"',
            f'MSG="{trailer}"; git commit -m "$MSG"',
            f"bash -c 'git commit -m \"Fix typo\" -m \"{trailer}\"'",
            # W3-15 g18 and g19: issue text and the squash commit message.
            f'gh issue create --title "Fix typo" --body "{link}"',
            f'gh issue comment 1 --body "{link}"',
            f'gh issue edit 1 --body "{link}"',
            f'gh pr merge 12 --squash --match-head-commit {SHA} --body "{trailer}"',
            f'gh pr merge 12 --squash --match-head-commit {SHA} --subject "{link}"',
        ]:
            with self.subTest(command=command):
                result = run_blocked_hook(
                    {"tool_name": "Bash", "tool_input": {"command": command}}
                )
                self.assertIn("AI tool attribution detected", result.stderr)

    def test_reads_body_files_against_the_payload_cwd(self):
        # W3-08 g26 and g27: the form that the repository recommends.
        with tempfile.TemporaryDirectory() as cwd:
            Path(cwd, "sub").mkdir()
            Path(cwd, "bad.md").write_text("Fix typo\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n")
            Path(cwd, "sub", "bad.md").write_text("Generated with Claude Code\n")
            Path(cwd, "clean.md").write_text("Fix typo\n\nCo-Authored-By: Jamie Doe <jamie@example.invalid>\n")
            Path(cwd, "plan.md").write_text("## Summary\n\nFix.\n\n## Test plan\n\n- Run it.\n")
            for command, reason in [
                ("gh pr create --title x --body-file bad.md", "AI tool attribution"),
                ("gh pr comment 1 -F bad.md", "AI tool attribution"),
                ("gh issue create --title x --body-file=bad.md", "AI tool attribution"),
                ("git commit -F bad.md", "AI tool attribution"),
                ("git commit --file=bad.md", "AI tool attribution"),
                ("git -C sub commit -F bad.md", "AI tool attribution"),
                ("gh pr create --title x --body-file plan.md", "Test plan"),
            ]:
                for payload in (
                    {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": cwd},
                    dict(codex_payload(command), cwd=cwd),
                ):
                    with self.subTest(command=command, tool=payload["tool_name"]):
                        result = run_blocked_hook(payload)
                        self.assertIn(reason, result.stderr)
            for command in [
                "gh pr create --title x --body-file clean.md",
                "git commit -F clean.md",
                # A missing file can be one that the same command writes.
                "git commit -F missing.md",
                "git commit -F -",
            ]:
                with self.subTest(command=command):
                    run_hook_raw({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": cwd})

    def test_blocks_a_test_plan_heading_in_a_pull_request_body(self):
        # W3-16 g20.
        for command in [
            'gh pr create --title x --body "## Summary\nFix.\n\n## Test plan\n- Run it."',
            'gh pr edit 1 --body "### Test Plan\n- Run it."',
            "gh pr create --title x --body-file - <<'EOF'\nFix.\n\n## Test plan\nEOF",
        ]:
            with self.subTest(command=command):
                result = run_blocked_hook(
                    {"tool_name": "Bash", "tool_input": {"command": command}}
                )
                self.assertIn("Test plan", result.stderr)
        response = run_hook(
            {
                "tool_name": "Bash",
                "tool_input": {"command": 'gh pr create --title x --body "No test plan is needed for a typo."'},
            }
        )
        self.assertReminds(response, "Contribution Guidelines")

    def test_blocks_a_merge_that_is_not_pinned_to_the_full_head_sha(self):
        # W1-04: a merge must name the reviewed head.
        for command in [
            "gh pr merge 1 --squash",
            "gh pr merge 1 --squash --match-head-commit abc1234",
            "gh -R owner/repo pr merge 1 --squash",
            "cd repo && gh pr merge 1 --squash",
        ]:
            for payload in (
                {"tool_name": "Bash", "tool_input": {"command": command}},
                codex_payload(command),
            ):
                with self.subTest(command=command, tool=payload["tool_name"]):
                    result = run_blocked_hook(payload)
                    self.assertIn("--match-head-commit", result.stderr)

    def test_allows_a_merge_pinned_to_the_head_sha(self):
        for command in [
            f"gh pr merge 1 --squash --match-head-commit {SHA}",
            f"gh pr merge 1 --squash --match-head-commit={SHA}",
            'gh pr merge 1 --squash --match-head-commit "$sha"',
            # It turns auto-merge off and merges nothing.
            "gh pr merge 1 --disable-auto",
        ]:
            with self.subTest(command=command):
                result = run_hook_process({"tool_name": "Bash", "tool_input": {"command": command}})
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_reads_commands_after_wrappers_launchers_and_program_paths(self):
        # A wrapper, a shell string, or a program path must not hide a
        # contribution command from any of the #455 checks.
        trailer = "Co-Authored-By: Claude <noreply@anthropic.com>"
        link = "Generated with [Claude Code](https://claude.com/claude-code)"
        with tempfile.TemporaryDirectory() as cwd:
            Path(cwd, "bad.md").write_text(f"Fix typo\n\n{trailer}\n")
            for command, reason in [
                (f'timeout 60 git commit -m "Fix" -m "{trailer}"', "AI tool attribution"),
                (f'nice -n 5 git commit -m "Fix" -m "{trailer}"', "AI tool attribution"),
                (f'/usr/bin/git commit -m "Fix" -m "{trailer}"', "AI tool attribution"),
                (f'\\git commit -m "Fix" -m "{trailer}"', "AI tool attribution"),
                (f'/opt/homebrew/bin/gh pr create --title x --body "{link}"', "AI tool attribution"),
                ("bash -c 'git commit -F bad.md'", "AI tool attribution"),
                ("env GH_TOKEN=x gh pr merge 1 --squash", "--match-head-commit"),
                ("bash -c 'gh pr merge 1 --squash'", "--match-head-commit"),
                ("timeout 60 gh pr merge 1 --squash", "--match-head-commit"),
                ("/opt/homebrew/bin/gh pr merge 1 --squash", "--match-head-commit"),
                ('timeout 60 gh pr create --title x --body "## Test plan"', "Test plan"),
                ("timeout 5 git add .", "Bulk git add"),
            ]:
                with self.subTest(command=command):
                    result = run_blocked_hook(
                        {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": cwd}
                    )
                    self.assertIn(reason, result.stderr)
        for command in [
            "rg -n 'git commit.*Co-Authored-By: Claude' -- docs",
            "timeout 5 rg -n 'gh pr merge 1 --squash' docs",
            "command -v gh",
            # A wrapper alone does not start the whole-command search.
            "timeout 60 git grep -n -E 'git commit.*Co-Authored-By: Claude' -- '*.md'",
            "nice rg -n 'git commit.*Co-Authored-By: Claude' -- docs",
            "timeout 10 git cat-file commit HEAD | grep -i 'Co-Authored-By: Claude'",
            "timeout 60 python3 - <<'EOF'\nprint(\"git commit -m 'x' -m 'Co-Authored-By: Claude'\")\nEOF",
        ]:
            with self.subTest(command=command):
                run_hook_raw({"tool_name": "Bash", "tool_input": {"command": command}})

    def test_reads_shell_strings_and_shells_that_read_standard_input(self):
        trailer = "Co-Authored-By: Claude <noreply@anthropic.com>"
        for command, reason in [
            # A shell with no `-c` string runs commands the hook cannot read.
            (f"bash <<'EOF'\ngit commit -m Fix -m '{trailer}'\nEOF", "AI tool attribution"),
            (f"eval 'git commit -m Fix -m \"{trailer}\"'", "AI tool attribution"),
            ("bash -o pipefail -c 'gh pr merge 1 --squash'", "--match-head-commit"),
            ("bash -c -- 'gh pr merge 1 --squash'", "--match-head-commit"),
        ]:
            with self.subTest(command=command):
                result = run_blocked_hook(
                    {"tool_name": "Bash", "tool_input": {"command": command}}
                )
                self.assertIn(reason, result.stderr)


if __name__ == "__main__":
    unittest.main()
