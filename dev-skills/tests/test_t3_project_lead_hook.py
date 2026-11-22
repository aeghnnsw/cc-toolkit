"""Contract checks for the t3-project-lead hook (issue #520).

The hook acts only in a session that ran `t3_project_lead.py start` from the
hook's own copy or from a copy outside every Git work tree. In that session it
blocks shell commands, file reads, file edits, and native subagent calls that
are not lead actions, and it reminds the lead to run `start` on each user
message. Each test runs the hook as a process with a JSON payload on stdin, as
Claude Code, Codex, and Antigravity do, and checks the exit status, stdout,
stderr, and the state folder.
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

    def check(self, jobs, *, allowed):
        """Run each (host, payload) job at once, then check that each passes or blocks."""
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda job: self.run_hook(*job), jobs))
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

    def test_a_worktree_copy_of_the_step_script_is_blocked(self):
        self.check_shell((f"python3 {self.dev_script} plan", f"python3 -c 'print(1)' {STEP_SCRIPT} plan",
                          f"python3 {STEP_SCRIPT} plan extra", f"/usr/bin/python3 {STEP_SCRIPT} plan"),
                         allowed=False)

    def test_a_simple_read_of_lead_files_runs(self):
        lead_md = f".scratch/{LEAD_NAME}/lead.md"
        self.check_shell((f"cat {lead_md}", f"cat '{self.lead_md}'", f"head -n 5 {lead_md}",
                          f"tail -n +2 {lead_md}", f"tail -3 {lead_md}", f"wc -l {lead_md} .gitignore",
                          f"ls -la .scratch/{LEAD_NAME}", f"ls .scratch/{LEAD_NAME}/",
                          f"grep -n 'a|b' {lead_md}", f"grep -rn -e Lead .scratch/{LEAD_NAME}",
                          f"sed -n '1,5p' {lead_md}", f"sed -n '/^#/p;$p' {lead_md}",
                          f"cat {self.exclude}", "cat .gitignore"),
                         allowed=True)
        # From a linked worktree, the lead folder is in the main checkout.
        self.check_shell((f"cat {self.lead_md}", f"cat {self.exclude}"), allowed=True, cwd=self.dev)

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

    def test_the_lead_can_list_names_in_scratch_but_read_no_other_folder(self):
        # A lead that lost its folder name finds it from the names in .scratch.
        scratch = self.main / ".scratch"
        self.check_shell(("ls .scratch", f"ls -1 {scratch}/"), allowed=True)
        self.check_shell(("grep -rn x .scratch", "cat .scratch/520-other/x.md", "ls .scratch/520-other"),
                         allowed=False)
        self.check_tools("claude", (("Glob", {"pattern": "*-lead-*/lead.md", "path": str(scratch)}),),
                         (("Grep", {"pattern": "x", "path": str(scratch)}),
                          ("Glob", {"pattern": "*", "path": str(scratch / "520-other")})))
        self.check_tools("antigravity", (("list_dir", {"DirectoryPath": str(scratch)}),),
                         (("grep_search", {"SearchPath": str(scratch), "Query": "x"}),))

    def test_claude_monitor_is_a_shell_tool(self):
        lead_md = f".scratch/{LEAD_NAME}/lead.md"
        self.check_tools("claude", (("Monitor", {"command": f"cat {lead_md}", "description": "x"}),),
                         (("Monitor", {"command": "ssh h1 'claude plugin update'", "description": "x"}),))

    def test_pipes_redirects_lists_and_substitutions_are_blocked(self):
        # In the lead folder each word names a lead file, so only the parser can block.
        self.check_shell(("cat lead.md | sh", "cat lead.md|sh", "cat lead.md > lead.md", "cat < lead.md",
                          "cat lead.md; sh", "cat lead.md && sh", "cat lead.md &", "cat $(echo lead.md)",
                          "cat `echo lead.md`", "cat <(sh)", "cat lead.md\nsh", "cat 'lead.md", 'cat "lead.md',
                          'cat "$(sh)"', 'cat "`sh`"', "cat {lead.md,sh}", "cat *.md", "cat lead.md # sh",
                          "bash -lc 'cat lead.md | sh'", "(cat lead.md)", "cat $LEAD_TEST_UNSET"),
                         allowed=False, cwd=self.lead)
        self.check_shell(("cat lead.md", 'cat "lead.md"', "cat 'lead'.md", "cat lead\\.md"), allowed=True,
                         cwd=self.lead)

    def test_rm_of_the_lead_folder_runs(self):
        self.check_shell((f"rm -rf {self.lead}", f"rm -r .scratch/{LEAD_NAME}/",
                          f"rm -fr .scratch/{LEAD_NAME}", f"rm -f .scratch/{LEAD_NAME}/lead.md",
                          f"rm .scratch/{LEAD_NAME}/lead.md"),
                         allowed=True)
        self.assertTrue(self.lead_md.exists())

    def test_rm_of_another_path_is_blocked(self):
        self.check_shell(("rm -rf .scratch", "rm -rf .scratch/", "rm -rf notes.md",
                          f"rm -rf .scratch/{LEAD_NAME} notes.md", "rm -rf .scratch/520-other",
                          f"rm -i .scratch/{LEAD_NAME}/lead.md", f"rm -rfv .scratch/{LEAD_NAME}",
                          f"rm -rf .scratch/{LEAD_NAME}/../520-other", "rm -rf /", "rm -rf ."),
                         allowed=False)

    def test_claude_file_reads(self):
        allowed = (("Read", {"file_path": str(self.lead_md)}), ("Read", {"file_path": str(self.main / ".gitignore")}),
                   ("Read", {"file_path": str(self.exclude)}),
                   ("Grep", {"pattern": "x", "path": str(self.lead)}),
                   ("Glob", {"pattern": "*.md", "path": str(self.lead)}))
        blocked = (("Read", {"file_path": str(self.main / "notes.md")}), ("Read", {}),
                   ("Grep", {"pattern": "x"}), ("Glob", {"pattern": "**/*.md"}),
                   ("Glob", {"pattern": "../../*", "path": str(self.lead)}),
                   ("Glob", {"pattern": "/etc/*", "path": str(self.lead)}),
                   ("Read", {"file_path": str(self.dev / ".gitignore")}))
        self.check_tools("claude", allowed, blocked)

    def test_t3_attachments_are_readable_not_editable(self):
        home = self.temp / "home"
        shot = home / ".t3" / "userdata" / "attachments" / "shot.png"
        shot.parent.mkdir(parents=True, exist_ok=True)
        shot.write_bytes(b"png")
        env = {"HOME": str(home)}
        self.assert_passes(self.run_hook("claude", tool_payload("claude", "Read", {"file_path": str(shot)},
                                                                self.main), env))
        self.assert_passes(self.run_hook("codex", shell_payload("codex", f"ls {shot.parent}", self.main), env))
        self.assert_blocks(self.run_hook("claude", tool_payload("claude", "Write", {"file_path": str(shot),
                                                                                  "content": "x"}, self.main), env))
        self.assert_blocks(self.run_hook("claude", tool_payload("claude", "Read", {"file_path": str(shot)},
                                                                self.main)))

    def test_claude_file_edits(self):
        allowed = (("Write", {"file_path": str(self.lead_md), "content": "x"}),
                   ("Edit", {"file_path": str(self.lead / "new.md"), "old_string": "a", "new_string": "b"}),
                   ("MultiEdit", {"file_path": str(self.lead_md), "edits": []}),
                   ("Edit", {"file_path": str(self.exclude), "old_string": "a", "new_string": "b"}))
        blocked = (("Write", {"file_path": str(self.main / "notes.md"), "content": "x"}),
                   ("Edit", {"file_path": str(self.main / ".gitignore"), "old_string": "a", "new_string": "b"}),
                   ("Write", {"file_path": str(self.main / ".scratch" / "520-other" / "x.md"), "content": "x"}),
                   ("Write", {"file_path": f"{self.lead}/../../notes.md", "content": "x"}),
                   ("NotebookEdit", {"notebook_path": str(self.main / "n.ipynb"), "new_source": "x"}),
                   ("Write", {"content": "x"}))
        self.check_tools("claude", allowed, blocked)

    def test_codex_apply_patch_checks_every_path(self):
        def patch(*headers):
            body = "".join(f"*** {header}\n+line\n" for header in headers)
            return {"command": f"*** Begin Patch\n{body}*** End Patch\n"}

        lead_md = f".scratch/{LEAD_NAME}/lead.md"
        allowed = (("apply_patch", patch(f"Update File: {lead_md}")),
                   ("apply_patch", patch(f"Add File: {self.lead}/new.md", f"Update File: {self.exclude}")),
                   ("apply_patch", patch(f"Delete File: {lead_md}")))
        blocked = (("apply_patch", patch(f"Update File: {lead_md}", "Update File: notes.md")),
                   ("apply_patch", patch(f"Update File: {lead_md}", "Move to: notes.md")),
                   ("apply_patch", patch("Add File: .scratch/520-other/x.md")),
                   ("apply_patch", {"command": "*** Begin Patch\n*** End Patch\n"}),
                   ("apply_patch", {}))
        self.check_tools("codex", allowed, blocked)

    def test_codex_reads_through_a_shell_wrapper_or_workdir(self):
        lead_md = f".scratch/{LEAD_NAME}/lead.md"
        allowed = (("exec_command", {"cmd": f"bash -lc 'cat {lead_md}'"}),
                   ("exec_command", {"cmd": "cat lead.md", "workdir": str(self.lead)}),
                   ("shell", {"command": ["bash", "-lc", f"sed -n 1,3p {lead_md}"]}))
        blocked = (("exec_command", {"cmd": "cat notes.md"}),
                   ("exec_command", {"cmd": "cat lead.md", "workdir": str(self.main)}),
                   ("exec_command", {"cmd": 7}))
        self.check_tools("codex", allowed, blocked)

    def test_antigravity_file_tools(self):
        allowed = (("view_file", {"AbsolutePath": str(self.lead_md)}), ("read_file", {"Path": str(self.lead_md)}),
                   ("list_dir", {"DirectoryPath": str(self.lead)}),
                   ("grep_search", {"SearchPath": str(self.lead), "Query": "x"}),
                   ("write_to_file", {"TargetFile": str(self.lead / "new.md"), "CodeContent": "x"}),
                   ("replace_file_content", {"TargetFile": str(self.exclude), "ReplacementContent": "x"}),
                   ("run_command", {"CommandLine": "cat lead.md", "Cwd": str(self.lead)}))
        blocked = (("view_file", {"AbsolutePath": str(self.main / "notes.md")}), ("view_file", {}),
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
                 ("antigravity", "ask_question"))
        self.check([(host, tool_payload(host, name, {"x": 1}, self.main)) for host, name in cases], allowed=True)

    def test_a_malformed_call_is_blocked(self):
        cases = (("claude", tool_payload("claude", "Bash", "not a dict", self.main)),
                 ("claude", tool_payload("claude", "Bash", {"command": ["cat"]}, self.main)),
                 ("claude", tool_payload("claude", "Bash", {}, self.main)),
                 ("codex", {"session_id": SESSION, "hook_event_name": "PreToolUse", "cwd": str(self.main)}),
                 ("claude", shell_payload("claude", f"cat .scratch/{LEAD_NAME}/lead.md", "relative/cwd")),
                 ("claude", shell_payload("claude", f"cat .scratch/{LEAD_NAME}/lead.md", self.temp / "missing")),
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


def matcher_names(entry):
    return set(entry["matcher"].split("|"))


class HookFileTests(HookCase):
    CLAUDE_TOOLS = {"Bash", "Monitor", "Read", "Grep", "Glob", "Write", "Edit", "MultiEdit", "NotebookEdit",
                    "Agent", "Task"}
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
