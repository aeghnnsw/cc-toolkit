import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "pre_git_hook.py"
CODEX_HOOKS = ROOT / "hooks" / "hooks.codex.json"


def run_hook_raw(payload):
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, f"Hook failed (exit {result.returncode}): {result.stderr}"
    return result


def run_hook(payload):
    # Commands the hook ignores produce no stdout; use run_hook_raw for those.
    return json.loads(run_hook_raw(payload).stdout)


class PreGitHookTests(unittest.TestCase):
    def test_blocks_invalid_codex_exec_command_branch_name(self):
        response = run_hook(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "exec_command",
                "tool_input": {"cmd": "git switch -c codex-plugin-support"},
            }
        )

        self.assertEqual(response["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("codex-plugin-support", response["systemMessage"])

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
        response = run_hook(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "git branch badname"},
            }
        )
        self.assertEqual(response["hookSpecificOutput"]["permissionDecision"], "deny")

    # --- Issue #105: AI attribution in gh pr edit / comment ---

    def test_blocks_attribution_in_gh_pr_edit(self):
        response = run_hook(
            {
                "tool_name": "Bash",
                "tool_input": {"command": 'gh pr edit 1 --body "Generated with Claude Code"'},
            }
        )
        self.assertEqual(response["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_blocks_attribution_in_gh_pr_comment(self):
        response = run_hook(
            {
                "tool_name": "Bash",
                "tool_input": {"command": 'gh pr comment 1 --body "noreply@anthropic.com"'},
            }
        )
        self.assertEqual(response["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_clean_gh_pr_edit_is_allowed(self):
        response = run_hook(
            {
                "tool_name": "Bash",
                "tool_input": {"command": 'gh pr edit 1 --body "Fix typo in README"'},
            }
        )
        self.assertNotIn("hookSpecificOutput", response)

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


if __name__ == "__main__":
    unittest.main()
