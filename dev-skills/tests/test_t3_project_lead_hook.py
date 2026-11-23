"""Contract checks for the t3-project-lead hook (issues #520 and #530).

The hook acts only in a session that ran `t3_project_lead.py start` from the
hook's own copy or from a copy outside every Git work tree. In that session it
allows the step script with arguments as one simple shell command and file
reads in T3 attachments. It blocks every other shell command, file read, file
edit, and native subagent call, and it reminds the lead to run `start` on each
user message. Issue #545 also blocks the T3 Code MCP calls that return issue
or PR text, in the Claude Code and Codex names. Each test runs the hook as a
process with a JSON payload on stdin, as Claude Code, Codex, and Antigravity
do, and checks the exit status, stdout, stderr, and the state folder.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
HOOK = PLUGIN_ROOT / "scripts" / "t3_project_lead_hook.py"
STEP_SCRIPT = PLUGIN_ROOT / "scripts" / "t3_project_lead.py"
HOSTS = ("claude", "codex", "antigravity")
SESSION = "lead-session-1"
LEAD_NAME = "20261122-lead-x"
BLOCK_LINE = ("BLOCKED: t3-project-lead: This is not a lead action. Give it to a worker with "
              "`t3_project_lead.py dispatch`.")
REMINDER = ('This is a t3-project-lead session. Before anything else in this turn, run: '
            f'python3 "{STEP_SCRIPT}" start')
DAY = 24 * 60 * 60
TEXT_LINE = ("Read no issue or PR text: a lead that read issues was flagged. Allowed: list_issues, "
             "pull_request_list, and pull_request_read with no include or with only checks. Give a triage "
             "that needs issue text to a read-only worker.")
# The T3 Code MCP tools that can return issue or PR text, in each host's names (#545). Claude Code
# keeps the server key t3-code. Codex changes "-" to "_", puts a 12-character environment hash after
# mcp__ for a server of one environment, and its sessions also use the server key t3-code-direct.
READ_ISSUE = {"claude": ("mcp__t3-code__read_issue",),
              "codex": ("mcp__t3_code__read_issue", "mcp__t3_code_direct__read_issue",
                        "mcp__0123456789ab__t3_code__read_issue")}
PR_READ = {"claude": ("mcp__t3-code__pull_request_read",),
           "codex": ("mcp__t3_code__pull_request_read", "mcp__t3_code_direct__pull_request_read",
                     "mcp__0123456789ab__t3_code__pull_request_read")}


def text_calls(names, inputs):
    """Return (host, name, tool input) for each Claude Code and Codex name in `names` and each input."""
    return [(host, name, tool_input) for host in ("claude", "codex") for name in names[host]
            for tool_input in inputs]
GIT = ("git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
       "-c", "commit.gpgsign=false", "-c", "init.defaultBranch=main")
# Git variables of a calling process would point the test repository elsewhere.
CLEAN_ENV = {key: value for key, value in os.environ.items()
             if key not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE")}


def tool_payload(host, name, tool_input, cwd, session=SESSION):
    """Return a PreToolUse payload in the form that `host` sends."""
    if host == "antigravity":
        return {"conversationId": session, "cwd": str(cwd), "hookEventName": "PreToolUse",
                "stepIdx": 2, "workspacePaths": [str(cwd)],
                "toolCall": {"name": name, "args": tool_input, "id": "call_1"}}
    payload = {"session_id": session, "cwd": str(cwd), "hook_event_name": "PreToolUse",
               "tool_name": name, "tool_input": tool_input, "transcript_path": "/dev/null",
               "permission_mode": "default"}
    if host == "codex":
        payload.update({"turn_id": "turn-1", "model": "gpt-test", "tool_use_id": "call-1"})
    return payload


def shell_payload(host, command, cwd, session=SESSION):
    """Return a PreToolUse payload of a shell command on `host`."""
    if host == "antigravity":
        return tool_payload(host, "run_command", {"CommandLine": command, "WaitMsBeforeAsync": 5000,
                                                  "toolSummary": "Run the command"}, cwd, session)
    return tool_payload(host, "Bash", {"command": command}, cwd, session)


def prompt_payload(host, session=SESSION, cwd="/"):
    return {"session_id": session, "cwd": str(cwd), "hook_event_name": "UserPromptSubmit",
            "prompt": "Next task.", "transcript_path": "/dev/null"}


class HookCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temp_dir = tempfile.TemporaryDirectory()
        cls.addClassCleanup(temp_dir.cleanup)
        cls.temp = Path(temp_dir.name).resolve()
        cls.main = cls.temp / "main"
        subprocess.run([*GIT, "init", "-q", str(cls.main)], check=True, env=CLEAN_ENV)
        subprocess.run([*GIT, "-C", str(cls.main), "commit", "-q", "--no-verify", "--allow-empty",
                        "-m", "init"], check=True, env=CLEAN_ENV)
        cls.lead = cls.main / ".scratch" / LEAD_NAME
        cls.lead.mkdir(parents=True)
        cls.lead_md = cls.lead / "lead.md"
        cls.lead_md.write_text("# Lead\n", encoding="utf-8")
        (cls.main / ".scratch" / "520-other").mkdir()
        (cls.main / ".gitignore").write_text(".scratch/\n", encoding="utf-8")
        (cls.main / "notes.md").write_text("notes\n", encoding="utf-8")
        cls.exclude = cls.main / ".git" / "info" / "exclude"
        cls.exclude.parent.mkdir(exist_ok=True)
        cls.exclude.touch()
        # A developer's linked worktree with its own copy of the step script.
        cls.dev = cls.temp / "dev"
        subprocess.run([*GIT, "-C", str(cls.main), "worktree", "add", "-q", "-b", "dev", str(cls.dev)],
                       check=True, env=CLEAN_ENV)
        cls.dev_script = cls.dev / "dev-skills" / "scripts" / "t3_project_lead.py"
        cls.dev_script.parent.mkdir(parents=True)
        shutil.copy2(STEP_SCRIPT, cls.dev_script)
        # An installed copy outside every Git work tree.
        cls.installed = cls.temp / "installed" / "scripts" / "t3_project_lead.py"
        cls.installed.parent.mkdir(parents=True)
        shutil.copy2(STEP_SCRIPT, cls.installed)

    def setUp(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.state = Path(temp_dir.name).resolve() / "sessions"

    def run_hook(self, host, payload, env=None):
        process_env = dict(CLEAN_ENV, T3_PROJECT_LEAD_STATE_DIR=str(self.state))
        process_env.update(env or {})
        data = payload if isinstance(payload, str) else json.dumps(payload)
        # The hook runs from a folder that is not the session cwd, as in
        # Antigravity, which runs hooks from the plugin root.
        return subprocess.run([sys.executable, str(HOOK), "--host", host], input=data, text=True,
                              capture_output=True, cwd=self.temp, env=process_env, check=False)

    def record(self, session=SESSION):
        self.state.mkdir(parents=True, exist_ok=True)
        (self.state / session).touch()

    def assert_passes(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")

    def assert_blocks(self, result):
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(result.stdout, "")
        lines = result.stderr.splitlines()
        self.assertEqual(lines[0], BLOCK_LINE)
        self.assertEqual(len(lines), 2, result.stderr)

    def check(self, jobs, *, allowed, env=None):
        """Run each (host, payload) job at once, then check that each passes or blocks."""
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda job: self.run_hook(*job, env), jobs))
        for (host, payload), result in zip(jobs, results):
            with self.subTest(host=host, payload=payload, allowed=allowed):
                if allowed:
                    self.assert_passes(result)
                else:
                    self.assert_blocks(result)

    def check_shell(self, cases, *, allowed, cwd=None):
        """Check shell commands; the cases cycle through the hosts, so that a
        list covers each host's payload form."""
        jobs = [(HOSTS[index % len(HOSTS)], command) for index, command in enumerate(cases)]
        self.check([(host, shell_payload(host, command, cwd or self.main)) for host, command in jobs],
                   allowed=allowed)


class SessionWithoutRecordTests(HookCase):
    def test_a_call_outside_the_lead_list_passes_silently(self):
        self.check([(host, payload) for host in HOSTS
                    for payload in (shell_payload(host, "git status | head", self.main),
                                    tool_payload(host, "Agent", {"prompt": "x"}, self.main),
                                    tool_payload(host, "Bash", "not a dict", self.main))], allowed=True)
        self.assertFalse(self.state.exists())

    def test_no_session_id_or_bad_input_passes_silently(self):
        self.record()
        jobs = []
        for host in HOSTS:
            no_id = shell_payload(host, "git status", self.main)
            no_id.pop("session_id", None)
            no_id.pop("conversationId", None)
            jobs += [(host, payload) for payload in (
                no_id, "not json", "[1, 2]", "", f'{{"session_id": "{SESSION}", "conversationId": "{SESSION}"',
                shell_payload(host, "git status", self.main, session="../" + SESSION),
                shell_payload(host, "git status", self.main, session=".."))]
        self.check(jobs, allowed=True)

    def test_a_prompt_gets_no_reminder(self):
        self.check([(host, prompt_payload(host)) for host in ("claude", "codex")], allowed=True)

    def test_issue_and_pr_text_reads_pass(self):
        jobs = [(host, tool_payload(host, name, tool_input, self.main))
                for host in ("claude", "codex")
                for name, tool_input in ([(name, {"url": "https://github.com/o/r/issues/1"})
                                          for name in READ_ISSUE[host]]
                                         + [(name, {"include": ["body", "diff"]}) for name in PR_READ[host]])]
        self.check(jobs, allowed=True)
        self.assertFalse(self.state.exists())

    def test_antigravity_reads_the_conversation_id_not_a_session_id(self):
        self.record()
        payload = shell_payload("antigravity", "git status", self.main, session="other")
        payload["session_id"] = SESSION
        self.assert_passes(self.run_hook("antigravity", payload))


class RecordTests(HookCase):
    def test_start_from_the_hooks_own_copy_records_the_session(self):
        for host in HOSTS:
            with self.subTest(host=host):
                shutil.rmtree(self.state, ignore_errors=True)
                result = self.run_hook(host, shell_payload(host, f'python3 "{STEP_SCRIPT}" start', self.main))
                self.assert_passes(result)
                self.assertTrue((self.state / SESSION).is_file())
                self.assertEqual((self.state / SESSION).read_text(), "")

    def test_codex_command_forms_record_the_session(self):
        command = f"python3 '{STEP_SCRIPT}' start"
        for tool_input in ({"cmd": command}, {"cmd": f'bash -lc "{command}"'},
                           {"command": ["bash", "-lc", command]}):
            with self.subTest(tool_input=tool_input):
                shutil.rmtree(self.state, ignore_errors=True)
                name = "exec_command" if "cmd" in tool_input else "shell"
                self.assert_passes(self.run_hook("codex", tool_payload("codex", name, tool_input, self.main)))
                self.assertTrue((self.state / SESSION).is_file())

    def test_a_relative_or_variable_path_resolves_before_the_check(self):
        cases = (("python scripts/t3_project_lead.py start", PLUGIN_ROOT, {}),
                 ('python3 "$LEAD_TEST_ROOT/scripts/t3_project_lead.py" start', self.main,
                  {"LEAD_TEST_ROOT": str(PLUGIN_ROOT)}),
                 ("python3 ${LEAD_TEST_ROOT}/scripts/t3_project_lead.py start", self.main,
                  {"LEAD_TEST_ROOT": str(PLUGIN_ROOT)}))
        for command, cwd, env in cases:
            with self.subTest(command=command):
                shutil.rmtree(self.state, ignore_errors=True)
                self.assert_passes(self.run_hook("claude", shell_payload("claude", command, cwd), env))
                self.assertTrue((self.state / SESSION).is_file())

    def test_start_from_a_copy_outside_every_git_work_tree_records_the_session(self):
        self.assert_passes(self.run_hook("codex", shell_payload("codex", f"python3 {self.installed} start",
                                                                self.main)))
        self.assertTrue((self.state / SESSION).is_file())

    def test_a_worktree_copy_or_another_step_records_nothing(self):
        for host in HOSTS:
            for command in (f"python3 {self.dev_script} start",
                            "python3 dev-skills/scripts/t3_project_lead.py start",
                            f"python3 {STEP_SCRIPT} plan",
                            f"python3 {STEP_SCRIPT} start | cat",
                            f"cat {self.installed} start",
                            f"python3 {STEP_SCRIPT.parent / 'missing' / 't3_project_lead.py'} start"):
                with self.subTest(host=host, command=command):
                    self.assert_passes(self.run_hook(host, shell_payload(host, command, self.dev)))
        self.assertFalse((self.state / SESSION).exists())

    def test_start_with_more_words_records_nothing(self):
        for host in HOSTS:
            for command in (f"python3 {STEP_SCRIPT} start extra", f"python3 {self.installed} start --x 1"):
                with self.subTest(host=host, command=command):
                    self.assert_passes(self.run_hook(host, shell_payload(host, command, self.main)))
        self.assertFalse((self.state / SESSION).exists())

    def test_an_invalid_session_id_records_nothing(self):
        payload = shell_payload("claude", f"python3 {STEP_SCRIPT} start", self.main, session="../escape")
        self.assert_passes(self.run_hook("claude", payload))
        self.assertFalse((self.state.parent / "escape").exists())
        self.assertFalse(self.state.exists() and any(self.state.iterdir()))

    def test_a_new_record_deletes_records_older_than_30_days(self):
        self.state.mkdir(parents=True)
        old = self.state / "old-session"
        recent = self.state / "recent-session"
        for path, age in ((old, 31 * DAY), (recent, 29 * DAY)):
            path.touch()
            stamp = time.time() - age
            os.utime(path, (stamp, stamp))
        self.assert_passes(self.run_hook("claude", shell_payload("claude", f"python3 {STEP_SCRIPT} start",
                                                                 self.main)))
        self.assertFalse(old.exists())
        self.assertTrue(recent.exists())
        self.assertTrue((self.state / SESSION).exists())


class GateTests(HookCase):
    def setUp(self):
        super().setUp()
        self.record()

    def test_the_skills_own_step_script_runs(self):
        self.check_shell((f'python3 "{STEP_SCRIPT}" plan', f"python {STEP_SCRIPT} dispatch",
                          f"python3 {self.installed} report", f"python3 '{STEP_SCRIPT}' start"),
                         allowed=True)

    def test_the_step_script_runs_with_arguments(self):
        self.check_shell((f"python3 {STEP_SCRIPT} task add fix-503 'Triage #503 (lean-tests)' --batch 2",
                          f'python3 "{STEP_SCRIPT}" show', f"python3 {STEP_SCRIPT} wait --task x --decisions 3",
                          f"python {self.installed} outcome 'a | b; c > d'", f"python3 {STEP_SCRIPT} plan extra",
                          f'python3 {STEP_SCRIPT} criteria "Tests pass (all)"', f"python3 {STEP_SCRIPT} takeover",
                          f"python3 {STEP_SCRIPT} init demo --also"),
                         allowed=True)

    def test_a_worktree_copy_of_the_step_script_is_blocked(self):
        self.check_shell((f"python3 {self.dev_script} plan", f"python3 -c 'print(1)' {STEP_SCRIPT} plan",
                          f"python3 {self.dev_script} task add fix-503 'Triage #503' --batch 2",
                          f"/usr/bin/python3 {STEP_SCRIPT} plan"),
                         allowed=False)

    def test_a_bad_subcommand_or_a_compound_step_command_is_blocked(self):
        self.check_shell((f"python3 {STEP_SCRIPT} Task add", f"python3 {STEP_SCRIPT} --help",
                          f"python3 {STEP_SCRIPT} show | cat", f"python3 {STEP_SCRIPT}",
                          f"python3 {STEP_SCRIPT} task-add x", f"python3 {STEP_SCRIPT} '' show"),
                         allowed=False)

    def test_only_a_three_word_start_refreshes_the_record(self):
        record = self.state / SESSION
        stamp = int(time.time()) - DAY
        os.utime(record, (stamp, stamp))
        self.assert_passes(self.run_hook("claude", shell_payload("claude", f"python3 {STEP_SCRIPT} start extra",
                                                                 self.main)))
        self.assertEqual(record.stat().st_mtime, stamp)
        self.assert_passes(self.run_hook("claude", shell_payload("claude", f"python3 {STEP_SCRIPT} start",
                                                                 self.main)))
        self.assertGreater(record.stat().st_mtime, stamp)

    def test_shell_reads_of_lead_files_are_blocked(self):
        lead_md = f".scratch/{LEAD_NAME}/lead.md"
        self.check_shell((f"cat {lead_md}", f"cat '{self.lead_md}'", f"head -n 5 {lead_md}",
                          f"tail -n +2 {lead_md}", f"tail -3 {lead_md}", f"wc -l {lead_md} .gitignore",
                          f"ls -la .scratch/{LEAD_NAME}", f"ls .scratch/{LEAD_NAME}/",
                          f"grep -n 'a|b' {lead_md}", f"grep -rn -e Lead .scratch/{LEAD_NAME}",
                          f"sed -n '1,5p' {lead_md}", f"sed -n '/^#/p;$p' {lead_md}",
                          f"cat {self.exclude}", "cat .gitignore"),
                         allowed=False)
        self.check_shell((f"cat {self.lead_md}", f"cat {self.exclude}"), allowed=False, cwd=self.dev)

    def test_other_shell_commands_are_blocked(self):
        lead_md = f".scratch/{LEAD_NAME}/lead.md"
        self.check_shell(("git status", "ssh host uptime", "cat notes.md", f"cat {lead_md} notes.md",
                          "cat .scratch/520-other/x.md", f"cat .scratch/{LEAD_NAME}/../../notes.md",
                          "ls", f"cat {self.dev}/.gitignore", f"tail -f {lead_md}",
                          f"sed -n '1w out' {lead_md}", f"sed -i 's/a/b/' {lead_md}", f"sed -n 1e {lead_md}",
                          f"grep -f notes.md {lead_md}", f"grep Lead {lead_md} -f notes.md",
                          f"cat .scratch/*/lead.md", f'cat "$LEAD_TEST_UNSET/lead.md"', "echo hi",
                          f"FOO=1 cat {lead_md}", f"cat {lead_md} # note"),
                         allowed=False)

    def test_listings_of_scratch_are_blocked(self):
        scratch = self.main / ".scratch"
        self.check_shell(("ls .scratch", f"ls -1 {scratch}/", "grep -rn x .scratch", "ls .scratch/520-other"),
                         allowed=False)
        self.check_tools("claude", (), (("Glob", {"pattern": "*-lead-*/lead.md", "path": str(scratch)}),
                                        ("Grep", {"pattern": "x", "path": str(scratch)}),
                                        ("Glob", {"pattern": "*", "path": str(scratch / "520-other")})))
        self.check_tools("antigravity", (), (("list_dir", {"DirectoryPath": str(scratch)}),
                                             ("grep_search", {"SearchPath": str(scratch), "Query": "x"})))

    def test_claude_monitor_is_a_shell_tool(self):
        lead_md = f".scratch/{LEAD_NAME}/lead.md"
        self.check_tools("claude", (("Monitor", {"command": f"python3 {STEP_SCRIPT} show", "description": "x"}),),
                         (("Monitor", {"command": "ssh h1 'claude plugin update'", "description": "x"}),
                          ("Monitor", {"command": f"cat {lead_md}", "description": "x"})))

    def test_pipes_redirects_lists_and_substitutions_are_blocked(self):
        # Each command runs the step script, so only the parser can block.
        step = "python3 t3_project_lead.py"
        self.check_shell((f"{step} show | sh", f"{step} show|sh", f"{step} show > out", f"{step} show < in",
                          f"{step} show; sh", f"{step} show && sh", f"{step} show &", f"{step} outcome $(echo x)",
                          f"{step} outcome `echo x`", f"{step} outcome <(sh)", f"{step} show\nsh",
                          f"{step} outcome 'x", f'{step} outcome "x', f'{step} outcome "$(sh)"',
                          f'{step} outcome "`sh`"', f"{step} outcome {{a,b}}", f"{step} outcome *.md",
                          f"{step} show # sh", f"bash -lc '{step} show | sh'", f"({step} show)",
                          f"{step} outcome $LEAD_TEST_UNSET", f"FOO=1 {step} show"),
                         allowed=False, cwd=STEP_SCRIPT.parent)
        self.check_shell((f"{step} show", 'python3 "t3_project_lead.py" show', "python3 't3_project'_lead.py show",
                          "python3 t3_project_lead\\.py show", f"{step} outcome 'a | b; c > d'",
                          f'{step} outcome "a (b) #c"'),
                         allowed=True, cwd=STEP_SCRIPT.parent)

    def test_rm_of_the_lead_folder_is_blocked(self):
        self.check_shell((f"rm -rf {self.lead}", f"rm -r .scratch/{LEAD_NAME}/",
                          f"rm -fr .scratch/{LEAD_NAME}", f"rm -f .scratch/{LEAD_NAME}/lead.md",
                          f"rm .scratch/{LEAD_NAME}/lead.md"),
                         allowed=False)
        self.assertTrue(self.lead_md.exists())

    def test_rm_of_another_path_is_blocked(self):
        self.check_shell(("rm -rf .scratch", "rm -rf .scratch/", "rm -rf notes.md",
                          f"rm -rf .scratch/{LEAD_NAME} notes.md", "rm -rf .scratch/520-other",
                          f"rm -i .scratch/{LEAD_NAME}/lead.md", f"rm -rfv .scratch/{LEAD_NAME}",
                          f"rm -rf .scratch/{LEAD_NAME}/../520-other", "rm -rf /", "rm -rf ."),
                         allowed=False)

    def test_claude_file_reads_outside_attachments_are_blocked(self):
        blocked = (("Read", {"file_path": str(self.lead_md)}), ("Read", {"file_path": str(self.main / ".gitignore")}),
                   ("Read", {"file_path": str(self.exclude)}),
                   ("Grep", {"pattern": "x", "path": str(self.lead)}),
                   ("Glob", {"pattern": "*.md", "path": str(self.lead)}),
                   ("Read", {"file_path": str(self.main / "notes.md")}), ("Read", {}),
                   ("Grep", {"pattern": "x"}), ("Glob", {"pattern": "**/*.md"}),
                   ("Glob", {"pattern": "../../*", "path": str(self.lead)}),
                   ("Glob", {"pattern": "/etc/*", "path": str(self.lead)}),
                   ("Read", {"file_path": str(self.dev / ".gitignore")}))
        self.check_tools("claude", (), blocked)

    def test_t3_attachments_are_readable_not_editable(self):
        home = self.temp / "home"
        attachments = home / ".t3" / "userdata" / "attachments"
        shot = attachments / "shot.png"
        shot.parent.mkdir(parents=True, exist_ok=True)
        shot.write_bytes(b"png")
        env = {"HOME": str(home)}
        allowed = [("claude", tool_payload("claude", "Read", {"file_path": str(shot)}, self.main)),
                   ("claude", tool_payload("claude", "Grep", {"pattern": "x", "path": str(attachments)}, self.main)),
                   ("claude", tool_payload("claude", "Glob", {"pattern": "*.png", "path": str(attachments)},
                                           self.main)),
                   ("antigravity", tool_payload("antigravity", "view_file", {"AbsolutePath": str(shot)}, self.main)),
                   ("antigravity", tool_payload("antigravity", "list_dir", {"DirectoryPath": str(attachments)},
                                                self.main)),
                   ("codex", shell_payload("codex", f"ls {attachments}", self.main)),
                   ("codex", shell_payload("codex", f"cat {shot}", self.main)),
                   ("codex", shell_payload("codex", f"sed -n 1,5p {shot}", self.main))]
        blocked = [("claude", tool_payload("claude", "Write", {"file_path": str(shot), "content": "x"}, self.main)),
                   ("claude", tool_payload("claude", "Glob", {"pattern": "*.png"}, self.main)),
                   ("claude", tool_payload("claude", "Glob", {"pattern": f"{attachments}/*"}, self.main)),
                   ("claude", tool_payload("claude", "Read", {"file_path": f"{attachments}/../notes.md"}, self.main)),
                   ("codex", shell_payload("codex", f"cat {attachments}/../notes.md", self.main)),
                   ("codex", shell_payload("codex", f"cat {shot} | head", self.main)),
                   ("codex", shell_payload("codex", f"rm {shot}", self.main))]
        self.check(allowed, allowed=True, env=env)
        self.check(blocked, allowed=False, env=env)
        self.assert_blocks(self.run_hook("claude", tool_payload("claude", "Read", {"file_path": str(shot)},
                                                                self.main)))

    def test_claude_file_edits_are_blocked(self):
        blocked = (("Write", {"file_path": str(self.lead_md), "content": "x"}),
                   ("Edit", {"file_path": str(self.lead / "new.md"), "old_string": "a", "new_string": "b"}),
                   ("MultiEdit", {"file_path": str(self.lead_md), "edits": []}),
                   ("Edit", {"file_path": str(self.exclude), "old_string": "a", "new_string": "b"}),
                   ("Write", {"file_path": str(self.main / "notes.md"), "content": "x"}),
                   ("Edit", {"file_path": str(self.main / ".gitignore"), "old_string": "a", "new_string": "b"}),
                   ("Write", {"file_path": str(self.main / ".scratch" / "520-other" / "x.md"), "content": "x"}),
                   ("Write", {"file_path": f"{self.lead}/../../notes.md", "content": "x"}),
                   ("NotebookEdit", {"notebook_path": str(self.main / "n.ipynb"), "new_source": "x"}),
                   ("Write", {"content": "x"}), ("Write", "not a dict"))
        self.check_tools("claude", (), blocked)

    def test_codex_apply_patch_is_blocked(self):
        def patch(*headers):
            body = "".join(f"*** {header}\n+line\n" for header in headers)
            return {"command": f"*** Begin Patch\n{body}*** End Patch\n"}

        lead_md = f".scratch/{LEAD_NAME}/lead.md"
        blocked = (("apply_patch", patch(f"Update File: {lead_md}")),
                   ("apply_patch", patch(f"Add File: {self.lead}/new.md", f"Update File: {self.exclude}")),
                   ("apply_patch", patch(f"Delete File: {lead_md}")),
                   ("apply_patch", patch(f"Update File: {lead_md}", "Update File: notes.md")),
                   ("apply_patch", patch("Add File: .scratch/520-other/x.md")),
                   ("apply_patch", {"command": "*** Begin Patch\n*** End Patch\n"}),
                   ("apply_patch", {}))
        self.check_tools("codex", (), blocked)

    def test_codex_runs_the_step_script_through_a_shell_wrapper_or_workdir(self):
        lead_md = f".scratch/{LEAD_NAME}/lead.md"
        allowed = (("exec_command", {"cmd": f"bash -lc 'python3 {STEP_SCRIPT} show'"}),
                   ("exec_command", {"cmd": "python3 t3_project_lead.py show", "workdir": str(STEP_SCRIPT.parent)}),
                   ("shell", {"command": ["bash", "-lc", f"python3 {STEP_SCRIPT} outcome 'a b'"]}))
        blocked = (("exec_command", {"cmd": f"bash -lc 'cat {lead_md}'"}),
                   ("exec_command", {"cmd": "cat lead.md", "workdir": str(self.lead)}),
                   ("shell", {"command": ["bash", "-lc", f"sed -n 1,3p {lead_md}"]}),
                   ("exec_command", {"cmd": "python3 t3_project_lead.py show", "workdir": str(self.main)}),
                   ("exec_command", {"cmd": "cat notes.md"}),
                   ("exec_command", {"cmd": 7}))
        self.check_tools("codex", allowed, blocked)

    def test_antigravity_file_tools(self):
        allowed = (("run_command", {"CommandLine": "python3 t3_project_lead.py show",
                                    "Cwd": str(STEP_SCRIPT.parent)}),)
        blocked = (("view_file", {"AbsolutePath": str(self.lead_md)}), ("read_file", {"Path": str(self.lead_md)}),
                   ("list_dir", {"DirectoryPath": str(self.lead)}),
                   ("grep_search", {"SearchPath": str(self.lead), "Query": "x"}),
                   ("write_to_file", {"TargetFile": str(self.lead / "new.md"), "CodeContent": "x"}),
                   ("replace_file_content", {"TargetFile": str(self.exclude), "ReplacementContent": "x"}),
                   ("run_command", {"CommandLine": "cat lead.md", "Cwd": str(self.lead)}),
                   ("view_file", {"AbsolutePath": str(self.main / "notes.md")}), ("view_file", {}),
                   ("grep_search", {"SearchPath": str(self.main), "Query": "x"}),
                   ("multi_replace_file_content", {"TargetFile": str(self.main / "notes.md")}),
                   ("write_to_file", {"TargetFile": str(self.main / ".gitignore"), "CodeContent": "x"}),
                   ("run_command", {"CommandLine": "git status"}))
        self.check_tools("antigravity", allowed, blocked)

    def test_native_subagent_calls_are_blocked(self):
        cases = (("claude", "Agent"), ("claude", "Task"), ("codex", "spawn_agent"),
                 ("codex", "collaborationspawn_agent"), ("antigravity", "invoke_subagent"))
        self.check([(host, tool_payload(host, name, {"prompt": "x"}, self.main)) for host, name in cases],
                   allowed=False)

    def test_mcp_and_other_tools_pass(self):
        cases = (("claude", "mcp__t3-code__delegate_task"), ("claude", "TodoWrite"),
                 ("codex", "mcp__t3_code__t3_thread_list"), ("codex", "update_plan"),
                 ("antigravity", "ask_question"), ("claude", "mcp__t3-code__list_issues"),
                 ("claude", "mcp__t3-code__pull_request_list"), ("codex", "mcp__t3_code__list_issues"),
                 ("codex", "mcp__t3_code__pull_request_list"))
        self.check([(host, tool_payload(host, name, {"x": 1}, self.main)) for host, name in cases], allowed=True)

    def check_text_reads(self, cases, *, allowed):
        """Check (host, name, tool input) calls; a blocked call names the reading rule (#545)."""
        jobs = [(host, tool_payload(host, name, tool_input, self.main)) for host, name, tool_input in cases]
        self.check(jobs, allowed=allowed)
        if not allowed:
            for host, payload in jobs:
                with self.subTest(host=host, payload=payload):
                    self.assertEqual(self.run_hook(host, payload).stderr.splitlines()[1], TEXT_LINE)

    def test_read_issue_is_blocked(self):
        self.check_text_reads(text_calls(READ_ISSUE, ({"url": "https://github.com/o/r/issues/1"}, {"key": "1"}, {})),
                              allowed=False)

    def test_pull_request_read_with_text_is_blocked(self):
        includes = (["body"], ["comments"], ["threads"], ["diff"], ["checks", "body"], ["diff", "checks"],
                    ["body", "comments", "threads", "diff"])
        self.check_text_reads(text_calls(PR_READ, [{"number": 5, "include": include} for include in includes]),
                              allowed=False)

    def test_pull_request_read_without_text_passes(self):
        inputs = ({}, {"number": 5}, {"include": ["checks"]}, {"number": 5, "include": ["checks", "checks"]},
                  {"include": []}, {"repository": "o/r", "includeResolved": True})
        self.check_text_reads(text_calls(PR_READ, inputs), allowed=True)

    def test_an_unreadable_pull_request_read_is_blocked(self):
        # The hook fails closed: an include that is not a list of strings, an unknown value, or a tool
        # input that is not an object (Codex passes arguments that do not parse as a string).
        inputs = ({"include": "body"}, {"include": "checks"}, {"include": None}, {"include": [1]},
                  {"include": ["checks", None]}, {"include": {"checks": True}}, {"include": ["Body"]},
                  {"include": ["files"]}, "{not json", ["include"], None)
        self.check_text_reads(text_calls(PR_READ, inputs), allowed=False)

    def test_a_malformed_call_is_blocked(self):
        step = "python3 scripts/t3_project_lead.py show"
        cases = (("claude", tool_payload("claude", "Bash", "not a dict", self.main)),
                 ("claude", tool_payload("claude", "Bash", {"command": ["cat"]}, self.main)),
                 ("claude", tool_payload("claude", "Bash", {}, self.main)),
                 ("codex", {"session_id": SESSION, "hook_event_name": "PreToolUse", "cwd": str(self.main)}),
                 ("claude", shell_payload("claude", step, "relative/cwd")),
                 ("claude", shell_payload("claude", step, self.temp / "missing")),
                 ("claude", tool_payload("claude", "Read", {"file_path": "shot.png"}, "relative/cwd")),
                 ("antigravity", {"conversationId": SESSION, "hookEventName": "PreToolUse",
                                  "cwd": str(self.main)}),
                 ("antigravity", {"conversationId": SESSION, "hookEventName": "PreToolUse",
                                  "cwd": str(self.main), "toolCall": {"name": "view_file", "args": None}}))
        self.check(list(cases), allowed=False)

    def test_a_prompt_gets_the_start_reminder(self):
        for host in ("claude", "codex"):
            with self.subTest(host=host):
                result = self.run_hook(host, prompt_payload(host))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr, "")
                self.assertEqual(json.loads(result.stdout), {"hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit", "additionalContext": REMINDER}})

    def test_other_events_pass(self):
        payload = shell_payload("claude", "git status", self.main)
        payload["hook_event_name"] = "PostToolUse"
        self.assert_passes(self.run_hook("claude", payload))

    def check_tools(self, host, allowed, blocked):
        for cases, expected in ((allowed, True), (blocked, False)):
            self.check([(host, tool_payload(host, name, tool_input, self.main)) for name, tool_input in cases],
                       allowed=expected)


BINDING = '{"project_id": "abcdefghijklmnopqrst", "owner_id": "11111111-1111-4111-8111-111111111111"}'
REQUEST = json.dumps({"request_id": "22222222-2222-4222-8222-222222222222", "operations": [{
    "op": "create", "id": "33333333-3333-4333-8333-333333333333",
    "data": {"kind": "inbox", "title": "Review the travel options"}}]}, indent=2)


def add_file_patch(path, text):
    """Return a Codex apply_patch input that adds one file."""
    body = "".join(f"+{line}\n" for line in text.splitlines())
    return {"command": f"*** Begin Patch\n*** Add File: {path}\n{body}*** End Patch\n"}


class GtdInboxTests(HookCase):
    """Issue #531: a recorded lead session can run the calls of a gtd-inbox capture."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.home = cls.temp / "gtd-home"
        cls.binding = cls.home / ".config" / "cc-toolkit" / "gtd.json"
        cls.binding.parent.mkdir(parents=True)
        cls.binding.write_text(BINDING, encoding="utf-8")
        (cls.binding.parent / "other.json").write_text("{}", encoding="utf-8")
        cls.copy = cls.make_copy(cls.temp / "plugins" / "productivity-skills" / "installed")
        cls.dev_copy = cls.make_copy(cls.dev / "productivity-skills")
        cls.script = cls.copy / "scripts" / "gtd_sql.py"
        # A folder with the renderer but not the contract is not a Productivity Skills copy.
        cls.partial = cls.temp / "partial"
        (cls.partial / "scripts").mkdir(parents=True)
        (cls.partial / "scripts" / "gtd_sql.py").write_text("", encoding="utf-8")
        cls.private = cls.temp / "private"
        cls.private.mkdir()
        (cls.private / "held.json").write_text(REQUEST, encoding="utf-8")
        (cls.private / "notes.json").write_text('{"a": 1}', encoding="utf-8")
        (cls.private / "link.json").symlink_to(cls.main / "notes.json")
        # A link to a folder outside Git: `<link>/../main/r.json` is outside Git
        # when the link is followed first, and in the main work tree after a
        # host tool removes `..` first, as Node.js does.
        (cls.private / "deep").mkdir()
        cls.link_dir = cls.temp / "link-dir"
        cls.link_dir.symlink_to(cls.private / "deep")

    @staticmethod
    def make_copy(root):
        for relative in ("scripts/gtd_sql.py", "references/gtd-cloud.md", "references/gtd-planning.md",
                         "skills/gtd-inbox/SKILL.md", "codex-skills/gtd-inbox/SKILL.md"):
            (root / relative).parent.mkdir(parents=True, exist_ok=True)
            (root / relative).write_text("x\n", encoding="utf-8")
        return root

    def setUp(self):
        super().setUp()
        self.record()

    def check_gtd(self, allowed, blocked):
        env = {"HOME": str(self.home)}
        for cases, expected in ((allowed, True), (blocked, False)):
            self.check([(host, tool_payload(host, name, tool_input, self.main))
                        for host, name, tool_input in cases], allowed=expected, env=env)

    def test_reads_of_the_installed_copy_and_the_binding_pass(self):
        cloud = self.copy / "references" / "gtd-cloud.md"
        skill = self.copy / "codex-skills" / "gtd-inbox" / "SKILL.md"
        allowed = (("claude", "Read", {"file_path": str(cloud)}),
                   ("claude", "Read", {"file_path": str(self.binding)}),
                   ("claude", "Grep", {"pattern": "binding", "path": str(self.copy / "references")}),
                   ("codex", "Bash", {"command": f"cat {skill}"}),
                   ("codex", "Bash", {"command": f"sed -n 1,80p {self.copy}/references/gtd-planning.md"}),
                   ("codex", "Bash", {"command": "cat ~/.config/cc-toolkit/gtd.json"}),
                   ("antigravity", "read_file", {"Path": str(self.copy / "skills" / "gtd-inbox" / "SKILL.md")}),
                   ("antigravity", "view_file", {"AbsolutePath": str(cloud)}))
        blocked = (("claude", "Read", {"file_path": str(self.binding.parent / "other.json")}),
                   ("claude", "Read", {"file_path": str(self.dev_copy / "references" / "gtd-cloud.md")}),
                   ("claude", "Read", {"file_path": str(self.partial / "scripts" / "gtd_sql.py")}),
                   ("claude", "Read", {"file_path": f"{self.copy}/../../../notes.md"}),
                   ("codex", "Bash", {"command": f"cat {cloud} | head"}),
                   ("codex", "Bash", {"command": f"cp {self.binding} {self.private}/binding.json"}),
                   ("antigravity", "read_file", {"Path": str(self.main / "notes.md")}))
        self.check_gtd(allowed, blocked)

    def test_the_renderer_of_an_installed_copy_passes(self):
        prefix = "uv run --no-project --python '>=3.11' python"
        allowed = (("claude", "Bash", {"command": f"{prefix} {self.script} --config {self.private}/b.json read "
                                                  "--kind inbox --limit 50"}),
                   ("claude", "Bash", {"command": f"{prefix} {self.script} uuid --count 2"}),
                   ("codex", "Bash", {"command": f"{prefix} {self.script} uuid"}),
                   ("claude", "Bash", {"command": f"uv run -q --no-cache --no-project --python=3.13 python3 "
                                                  f"'{self.script}' apply {self.private}/held.json"}),
                   ("codex", "Bash", {"command": f"uv run --offline --quiet --no-project --python '>=3.11' "
                                                 f"python {self.script} get 33333333-3333-4333-8333-333333333333"}),
                   ("codex", "exec_command", {"cmd": f"bash -lc \"{prefix} {self.script} receipt x\""}),
                   ("antigravity", "run_command", {"CommandLine": f"{prefix} {self.script} read"}))
        blocked = (("claude", "Bash", {"command": f"uv run --with requests --no-project python {self.script} read"}),
                   ("claude", "Bash", {"command": f"uv run python {self.script} read"}),
                   ("claude", "Bash", {"command": f"uv run --python '>=3.11' python {self.script} read"}),
                   ("claude", "Bash", {"command": f"uv run --no-project --python /usr/bin/env python {self.script} "
                                                  "read"}),
                   ("codex", "Bash", {"command": f"uv run --no-project --python={self.script} python {self.script} "
                                                 "read"}),
                   ("claude", "Bash", {"command": f"{prefix} {self.dev_copy}/scripts/gtd_sql.py read"}),
                   ("claude", "Bash", {"command": f"{prefix} {self.partial}/scripts/gtd_sql.py read"}),
                   ("claude", "Bash", {"command": f"{prefix} {self.copy}/references/gtd_sql.py read"}),
                   ("claude", "Bash", {"command": f"{prefix} {self.copy}/scripts/other.py read"}),
                   ("claude", "Bash", {"command": f"{prefix} -c 'print(1)'"}),
                   ("claude", "Bash", {"command": f"{prefix} -I {self.script} read"}),
                   ("claude", "Bash", {"command": f"uv run --no-project --python '>=3.11' {self.script} read"}),
                   ("claude", "Bash", {"command": f"{prefix} {self.script} read | head"}),
                   ("claude", "Bash", {"command": f"{prefix} {self.script} read > {self.private}/out.json"}),
                   ("claude", "Bash", {"command": f"UV_CACHE_DIR=/tmp/x {prefix} {self.script} read"}),
                   ("codex", "Bash", {"command": "uv pip install requests"}),
                   ("claude", "Bash", {"command": "uuidgen"}),
                   ("codex", "Bash", {"command": "uv run --no-project --python"}),
                   ("antigravity", "run_command", {"CommandLine": f"{prefix} {self.script} read && ls"}))
        self.check_gtd(allowed, blocked)

    def test_a_whole_gtd_file_write_outside_git_passes(self):
        allowed = (("claude", "Write", {"file_path": str(self.private / "binding.json"), "content": BINDING}),
                   ("claude", "Write", {"file_path": str(self.private / "request.json"), "content": REQUEST}),
                   ("claude", "Write", {"file_path": str(self.private / "new" / "r.json"), "content": REQUEST}),
                   ("claude", "Write", {"file_path": str(self.private / "held.json"), "content": REQUEST}),
                   ("codex", "apply_patch", add_file_patch(self.private / "request-2.json", REQUEST)),
                   ("antigravity", "write_file", {"Path": str(self.private / "b.json"), "Content": BINDING,
                                                  "Overwrite": False}),
                   ("antigravity", "write_to_file", {"TargetFile": str(self.private / "r.json"),
                                                     "CodeContent": REQUEST}))
        not_gtd = (BINDING[:-1] + ', "x": "y"}', '{"request_id": "x", "operations": {}}', '{"a": 1}',
                   "[1, 2]", "not json", "")
        blocked = ([("claude", "Write", {"file_path": str(self.private / "x.json"), "content": text})
                    for text in not_gtd]
                   + [("claude", "Write", {"file_path": str(self.private / "request.txt"), "content": REQUEST}),
                      ("claude", "Write", {"file_path": str(self.lead / "request.json"), "content": REQUEST}),
                      ("claude", "Write", {"file_path": str(self.dev / "binding.json"), "content": BINDING}),
                      ("claude", "Write", {"file_path": str(self.main / ".git" / "r.json"), "content": REQUEST}),
                      ("claude", "Write", {"file_path": str(self.private / "notes.json"), "content": REQUEST}),
                      ("claude", "Write", {"file_path": str(self.private / "link.json"), "content": REQUEST}),
                      ("claude", "Write", {"file_path": str(self.private), "content": REQUEST}),
                      ("claude", "Write", {"file_path": str(self.binding), "content": BINDING}),
                      ("claude", "Write", {"file_path": str(self.binding.parent / "GTD.json"), "content": BINDING}),
                      ("claude", "Write", {"file_path": str(self.binding.parent / "r.json"), "content": REQUEST}),
                      ("claude", "Write", {"file_path": f"{self.private}/../main/r.json", "content": REQUEST}),
                      ("claude", "Write", {"file_path": f"{self.link_dir}/../main/r.json", "content": REQUEST}),
                      ("claude", "Write", {"file_path": "request.json", "content": REQUEST}),
                      ("claude", "Write", {"file_path": "~/r.json", "content": REQUEST}),
                      ("claude", "Edit", {"file_path": str(self.private / "held.json"), "old_string": "a",
                                          "new_string": "b"}),
                      ("codex", "apply_patch", {"command": add_file_patch(self.private / "a.json", REQUEST)["command"]
                                                .replace("*** Add File", "*** Update File")}),
                      ("codex", "apply_patch", {"command": add_file_patch(self.private / "a.json", REQUEST)["command"]
                                                .replace("*** End Patch", "*** Delete File: notes.md\n*** End Patch")}),
                      ("codex", "apply_patch", add_file_patch(self.main / "r.json", REQUEST)),
                      ("codex", "apply_patch", add_file_patch("~/r.json", REQUEST)),
                      ("codex", "apply_patch", add_file_patch("r.json", REQUEST)),
                      ("codex", "apply_patch", add_file_patch(self.private / "x.json", '{"a": 1}')),
                      ("codex", "apply_patch", add_file_patch(self.private / "notes.json", REQUEST)),
                      ("antigravity", "write_file", {"Path": str(self.main / "r.json"), "Content": REQUEST}),
                      ("antigravity", "write_file", {"Path": str(self.private / "x.json"), "Content": "[]"}),
                      ("antigravity", "write_to_file", {"TargetFile": str(self.private / "notes.json"),
                                                        "CodeContent": REQUEST}),
                      ("antigravity", "write_file", {"Path": str(self.private / "held.json"), "Content": REQUEST,
                                                     "Append": True}),
                      ("antigravity", "edit_file", {"Path": str(self.private / "held.json"), "Target": "a",
                                                    "Replacement": "b"})])
        self.check_gtd(allowed, blocked)
        self.assertEqual(sorted(path.name for path in self.private.iterdir()),
                         ["deep", "held.json", "link.json", "notes.json"])

    def test_a_failed_git_check_blocks_and_the_locale_does_not_matter(self):
        write = tool_payload("claude", "Write", {"file_path": str(self.private / "r.json"), "content": REQUEST},
                             self.main)
        read = tool_payload("claude", "Read", {"file_path": str(self.copy / "references" / "gtd-cloud.md")},
                            self.main)
        for payload in (write, read):
            with self.subTest(payload=payload):
                self.assert_blocks(self.run_hook("claude", payload, {"HOME": str(self.home), "PATH": "/nonexistent"}))
                self.assert_passes(self.run_hook("claude", payload, {"HOME": str(self.home),
                                                                     "LC_ALL": "de_DE.UTF-8"}))


def matcher_names(entry):
    return set(entry["matcher"].split("|"))


class HookFileTests(HookCase):
    CLAUDE_TOOLS = {"Bash", "Monitor", "Read", "Grep", "Glob", "Write", "Edit", "MultiEdit", "NotebookEdit",
                    "Agent", "Task", *READ_ISSUE["claude"], *PR_READ["claude"]}
    CODEX_TOOLS = ("Bash", "exec_command", "shell", "apply_patch", "spawn_agent", "collaborationspawn_agent")
    ANTIGRAVITY_TOOLS = {"run_command", "read_file", "view_file", "list_dir", "grep_search", "write_file",
                         "edit_file", "write_to_file", "replace_file_content", "multi_replace_file_content",
                         "invoke_subagent"}

    def load(self, relative):
        return json.loads((PLUGIN_ROOT / relative).read_text(encoding="utf-8"))

    def entries(self, events, event):
        found = [(entry, hook["command"]) for entry in events.get(event, []) for hook in entry["hooks"]
                 if "t3_project_lead_hook.py" in hook["command"]]
        self.assertEqual(len(found), 1, event)
        return found[0]

    def run_configured(self, command, host, env, cwd):
        """Run a configured command through a shell, as the host does, on a blocked call."""
        self.record()
        payload = shell_payload(host, "git status", self.main)
        process_env = dict(CLEAN_ENV, T3_PROJECT_LEAD_STATE_DIR=str(self.state), **env)
        return subprocess.run(["/bin/sh", "-c", command], input=json.dumps(payload), text=True,
                              capture_output=True, cwd=cwd, env=process_env, check=False)

    def test_claude_hook_file(self):
        events = self.load("hooks/hooks.json")["hooks"]
        entry, command = self.entries(events, "PreToolUse")
        self.assertEqual(matcher_names(entry), self.CLAUDE_TOOLS)
        # Claude Code reads a matcher of letters, digits, "_", "-", and "|" as a list of exact names.
        self.assertRegex(entry["matcher"], r"^[A-Za-z0-9_|-]+$")
        self.assertEqual(command, '[ -f "${CLAUDE_PLUGIN_ROOT}/scripts/t3_project_lead_hook.py" ] || exit 0; '
                                  'python3 "${CLAUDE_PLUGIN_ROOT}/scripts/t3_project_lead_hook.py" --host claude')
        self.assertEqual(self.entries(events, "UserPromptSubmit")[1], command)
        self.assert_blocks(self.run_configured(command, "claude", {"CLAUDE_PLUGIN_ROOT": str(PLUGIN_ROOT)},
                                               self.temp))

    def test_codex_hook_file(self):
        manifest = self.load(".codex-plugin/plugin.json")
        self.assertEqual(manifest["hooks"], "./hooks/hooks.codex.json")
        events = self.load("hooks/hooks.codex.json")["hooks"]
        entry, command = self.entries(events, "PreToolUse")
        for name in self.CODEX_TOOLS:
            with self.subTest(name=name):
                self.assertRegex(name, entry["matcher"])
        # Codex reads a matcher with other characters than letters, digits, "_", and "|" as a regular
        # expression that can match part of a name. Its environment form needs one (#545).
        for name in (*READ_ISSUE["codex"], *PR_READ["codex"]):
            with self.subTest(name=name):
                self.assertRegex(name, entry["matcher"])
        for name in ("mcp__t3_code__list_issues", "mcp__t3_code__read_issue_x", "mcp__other__read_issue",
                     "mcp__0123456789__t3_code__read_issue", "xmcp__t3_code__read_issue"):
            with self.subTest(name=name):
                self.assertNotRegex(name, entry["matcher"])
        self.assertEqual(command, '[ -f "${PLUGIN_ROOT}/scripts/t3_project_lead_hook.py" ] || exit 0; '
                                  'python3 "${PLUGIN_ROOT}/scripts/t3_project_lead_hook.py" --host codex')
        self.assertEqual(self.entries(events, "UserPromptSubmit")[1], command)
        self.assert_blocks(self.run_configured(command, "codex", {"PLUGIN_ROOT": str(PLUGIN_ROOT)}, self.temp))

    def test_antigravity_hook_file(self):
        config = self.load("hooks.json")
        self.assertEqual(set(config), {"dev-skills"})
        events = config["dev-skills"]
        self.assertNotIn("UserPromptSubmit", events)
        entry, command = self.entries(events, "PreToolUse")
        self.assertLessEqual(self.ANTIGRAVITY_TOOLS, matcher_names(entry))
        for name in matcher_names(entry):
            self.assertRegex(name, r"^[a-z_]+$")
        self.assertEqual(command, '[ -f "scripts/t3_project_lead_hook.py" ] || exit 0; '
                                  'python3 "scripts/t3_project_lead_hook.py" --host antigravity')
        # Antigravity runs each hook command from the plugin root.
        self.assert_blocks(self.run_configured(command, "antigravity", {}, PLUGIN_ROOT))

    def test_a_missing_hook_script_blocks_nothing(self):
        # Python exits 2 on a missing script, which a host reads as a block of every call.
        empty = self.temp / "no-plugin"
        empty.mkdir(exist_ok=True)
        for relative, env in (("hooks/hooks.json", {"CLAUDE_PLUGIN_ROOT": str(empty)}),
                              ("hooks/hooks.codex.json", {"PLUGIN_ROOT": str(empty)})):
            with self.subTest(relative=relative):
                _, command = self.entries(self.load(relative)["hooks"], "PreToolUse")
                result = self.run_configured(command, "claude", env, self.temp)
                self.assertEqual((result.returncode, result.stdout), (0, ""), result.stderr)
        _, command = self.entries(self.load("hooks.json")["dev-skills"], "PreToolUse")
        result = self.run_configured(command, "antigravity", {}, empty)
        self.assertEqual((result.returncode, result.stdout), (0, ""), result.stderr)

    def test_no_hook_file_runs_uv(self):
        for relative in ("hooks/hooks.json", "hooks/hooks.codex.json", "hooks.json"):
            with self.subTest(relative=relative):
                self.assertNotRegex((PLUGIN_ROOT / relative).read_text(encoding="utf-8"), r"\buv\b")


if __name__ == "__main__":
    unittest.main()
