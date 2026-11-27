"""Contract checks for the t3-project-lead hook (issues #520 and #530).

The hook acts only in a session that ran `t3_project_lead.py start` from the
hook's own copy or from a copy outside every Git work tree. In that session it
allows the step script with arguments as one simple shell command and file
reads in T3 attachments. It blocks every other shell command, file read, file
edit, and native subagent call, and it reminds the lead to run `start` on each
user message. Issue #545 also blocks the T3 Code MCP calls that return issue
or PR text, in the Claude Code and Codex names. Issue #554 also blocks the
question tools of Claude Code and Codex, and a `t3_pending_request` call that
can answer a worker's question. Issue #574 also records a session for
`start` in a command list. Issue #612 records a session only at `init`,
`takeover`, and a `start` of the owner thread, and adds `unmark`. Issue #621
allows reads of the session's saved tool outputs and gtd-inbox files. Issue
#666 blocks the T3 Code MCP calls that aim a lead at another project, and
issue #659 blocks an archive of a lead thread as #645 blocks a settle. Each
test runs the hook as a process with a JSON payload on stdin, as Claude Code,
Codex, and Antigravity do, and checks the exit status, stdout, stderr, and
the state folder.
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
# The reminder also names unmark for a thread that is not the lead (#612).
REMINDER = ('This is a t3-project-lead session. Before anything else in this turn, run: '
            f'python3 "{STEP_SCRIPT}" start. When this thread is not the lead, as in a worker, run '
            f'python3 "{STEP_SCRIPT}" unmark instead.')
# The block of an unmark that the hook refuses (#612), and the start of its second line.
UNMARK_LINE = "BLOCKED: t3-project-lead: The hook keeps the lead record of this session."
UNMARK_REASON = "It removes the record only when it can tell that this thread is not the lead: "
# The second line of a blocked read (#621).
READ_LINE = ("Allowed reads: T3 attachments, the GTD binding, gtd-inbox .json files outside every Git work tree, "
             "the installed Productivity Skills plugin, and the tool outputs that Claude Code saved for this "
             "session. Print the lead state with t3_project_lead.py show.")
DAY = 24 * 60 * 60
TEXT_LINE = ("Read no issue or PR text: a lead that read issues was flagged. Allowed: list_issues, "
             'pull_request_list, and pull_request_read with sections or include, as your tool names it, set '
             'to ["checks"]. Give a triage that needs issue text to a read-only worker.')
# The blocks of a question tool and of an answer to a worker's question (#554).
QUESTION_LINE = ("Ask no question with a question tool. List in plain text and end your turn. Write a decision "
                 "that only the user can make in plain text, with your recommendation. Never ask the user to "
                 "choose which task to do. For a worker's question, run t3_project_lead.py answer.")
RESPOND_LINE = ("Do not answer a worker's question: run t3_project_lead.py answer, and give the user the worker's "
                "thread link. t3_pending_request may only list or read.")
QUESTION_TOOLS = {"claude": ("AskUserQuestion",), "codex": ("request_user_input", "request_user_input_async")}
QUESTION_INPUT = {"questions": [{"question": "Which outcome?", "options": [{"label": "A"}, {"label": "B"}]}]}
PENDING = {"claude": ("mcp__t3-code__t3_pending_request",),
           "codex": ("mcp__t3_code__t3_pending_request", "mcp__t3_code_direct__t3_pending_request",
                     "mcp__0123456789ab__t3_code__t3_pending_request")}
RESPOND = {"action": "respond", "threadId": "worker-1", "requestId": "r1", "answers": {"q1": "Remove it"}}
# Without maxCharsPerItem, t3_thread_read gives each item in pages of 500 characters (#632).
THREAD_LINE = ("Call t3_thread_read with maxCharsPerItem, such as 8000. Without it, a worker report comes in "
               "pages of 500 characters.")
THREAD_READ = {"claude": ("mcp__t3-code__t3_thread_read",),
               "codex": ("mcp__t3_code__t3_thread_read", "mcp__t3_code_direct__t3_thread_read",
                         "mcp__0123456789ab__t3_code__t3_thread_read")}
# Only the user settles a lead thread (#645). t3_thread_organize settles the calling thread when the call
# names no threadId.
ORGANIZE = {"claude": ("mcp__t3-code__t3_thread_organize",),
            "codex": ("mcp__t3_code__t3_thread_organize", "mcp__t3_code_direct__t3_thread_organize",
                      "mcp__0123456789ab__t3_code__t3_thread_organize")}
SETTLE_LINES = ["BLOCKED: t3-project-lead: Only the user settles a lead thread.",
                "Leave the lead thread open, and give its settle to no worker. To settle a worker's thread, name "
                "its threadId. When the hook blocks the settle of a worker's thread, give it to the user with "
                "t3_project_lead.py wait --settles <task>."]
# Only the user archives a lead thread (#659).
ARCHIVE_LINES = ["BLOCKED: t3-project-lead: Only the user archives a lead thread.",
                 "Leave the lead thread open: only the user archives it. To archive a worker's thread, name its "
                 "threadId."]
LEAD_THREAD = "thread:lead-1"
OWNER_THREAD = "thread:owner-1"
WORKER_THREAD = "thread:worker-1"
# The T3 Code MCP tools that can return issue or PR text, in each host's names (#545). Claude Code
# keeps the server key t3-code. Codex changes "-" to "_", puts a 12-character environment hash after
# mcp__ for a server of one environment, and its sessions also use the server key t3-code-direct.
READ_ISSUE = {"claude": ("mcp__t3-code__read_issue",),
              "codex": ("mcp__t3_code__read_issue", "mcp__t3_code_direct__read_issue",
                        "mcp__0123456789ab__t3_code__read_issue")}
PR_READ = {"claude": ("mcp__t3-code__pull_request_read",),
           "codex": ("mcp__t3_code__pull_request_read", "mcp__t3_code_direct__pull_request_read",
                     "mcp__0123456789ab__t3_code__pull_request_read")}

# A lead works only in its own project (#666). A call that names no project uses the project of the calling
# thread. The hook cannot learn the project ID of the lead, so a call that names a project blocks.
PROJECT_LINES = ["BLOCKED: t3-project-lead: A lead works only in its own project.",
                 "Leave out projectId, allProjects, and scratch: the call then uses this project. For work of "
                 "another project, report it to that project's lead with t3_thread_send, or have a worker file "
                 "an issue there. Do not list or offer that work."]
OTHER_PROJECT = "project-other"


def t3_names(tool):
    """Return the Claude Code and Codex names of the T3 Code MCP tool `tool`."""
    return {"claude": (f"mcp__t3-code__{tool}",),
            "codex": (f"mcp__t3_code__{tool}", f"mcp__t3_code_direct__{tool}",
                      f"mcp__0123456789ab__t3_code__{tool}")}


# For each tool, the calls that aim at another project, and the same calls aimed at the lead's own
# project, which name no project (#666).
OTHER_PROJECT_CALLS = {
    "delegate_task": ({"task": "Fix it.", "isolation": "worktree", "target": {"projectId": OTHER_PROJECT}},
                      {"task": "Fix it.", "target": {"projectId": OTHER_PROJECT, "model": "model-a"}}),
    "create_threads": ({"threads": [{"prompt": "Fix it.", "target": {"projectId": OTHER_PROJECT}}]},
                       {"threads": [{"prompt": "Fix it."}, {"prompt": "Check it.",
                                                            "target": {"projectId": OTHER_PROJECT}}]}),
    "t3_thread_launch": ({"title": "Fix", "message": "Fix it.", "projectId": OTHER_PROJECT},
                         {"title": "Fix", "message": "Fix it.", "scratch": True}),
    "t3_thread_list": ({"includeSubagents": True, "allProjects": True}, {"projectId": OTHER_PROJECT}),
    "list_issues": ({"projectId": OTHER_PROJECT, "state": "open"},),
}
OWN_PROJECT_CALLS = {
    "delegate_task": ({"task": "Fix it.", "isolation": "worktree"},
                      {"task": "Fix it.", "isolation": "worktree", "target": {"model": "model-a"}}),
    "create_threads": ({"threads": [{"prompt": "Fix it."}, {"prompt": "Check it.",
                                                            "target": {"model": "model-a"}}]},),
    "t3_thread_launch": ({"title": "Fix", "message": "Fix it.",
                          "workspaceStrategy": {"type": "existing_worktree", "worktreePath": "/w/lead"}},
                         {"title": "Fix", "message": "Fix it.", "scratch": False}),
    "t3_thread_list": ({"includeSubagents": True}, {"includeSubagents": True, "allProjects": False}),
    "list_issues": ({"state": "open"},),
}
# A report to another project's lead and an issue in another project's tracker are allowed (#666).
ALLOWED_PROJECT_CALLS = {
    "t3_thread_send": ({"threadId": "thread:other-lead", "projectId": OTHER_PROJECT,
                        "message": "Report: a shared script fails. Link: https://github.com/o/r/issues/1"},),
    "t3_thread_search": ({"query": "lead", "projectId": OTHER_PROJECT},),
    "create_issue": ({"projectId": OTHER_PROJECT, "title": "A shared script fails", "body": "Facts."},),
}


def project_calls(calls):
    """Return (host, name, tool input) for each Claude Code and Codex name of each tool in `calls`."""
    return [(host, name, tool_input) for tool, inputs in calls.items() for host, names in t3_names(tool).items()
            for name in names for tool_input in inputs]


def text_calls(names, inputs):
    """Return (host, name, tool input) for each Claude Code and Codex name in `names` and each input."""
    return [(host, name, tool_input) for host in ("claude", "codex") for name in names[host]
            for tool_input in inputs]
GIT = ("git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
       "-c", "commit.gpgsign=false", "-c", "init.defaultBranch=main")
# Git variables of a calling process would point the test repository elsewhere, and the T3 thread of a
# calling process would be the lead thread of each settle check (#645).
CLEAN_ENV = {key: value for key, value in os.environ.items()
             if key not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE", "T3CODE_THREAD_ID")}


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
                                         + [(name, {"sections": ["summary", "diff"]}) for name in PR_READ[host]])]
        self.check(jobs, allowed=True)
        self.assertFalse(self.state.exists())

    def test_questions_and_answers_pass(self):
        jobs = [(host, tool_payload(host, name, QUESTION_INPUT, self.main))
                for host in ("claude", "codex") for name in QUESTION_TOOLS[host]]
        jobs += [(host, tool_payload(host, name, RESPOND, self.main)) for host in ("claude", "codex")
                 for name in PENDING[host]]
        self.check(jobs, allowed=True)
        self.assertFalse(self.state.exists())

    def test_thread_reads_pass(self):
        self.check([(host, tool_payload(host, name, {"threadId": "worker-1"}, self.main))
                    for host in ("claude", "codex") for name in THREAD_READ[host]], allowed=True)
        self.assertFalse(self.state.exists())

    def test_settles_pass(self):
        self.check([(host, tool_payload(host, name, tool_input, self.main))
                    for host in ("claude", "codex") for name in ORGANIZE[host]
                    for tool_input in ({"action": "settle"}, {"action": "settle", "threadId": WORKER_THREAD},
                                       {"action": "archive"})],
                   allowed=True, env={"T3CODE_THREAD_ID": LEAD_THREAD})
        self.assertFalse(self.state.exists())

    def test_calls_of_another_project_pass(self):
        self.check([(host, tool_payload(host, name, tool_input, self.main))
                    for host, name, tool_input in project_calls(OTHER_PROJECT_CALLS)], allowed=True)
        self.assertFalse(self.state.exists())

    def test_antigravity_reads_the_conversation_id_not_a_session_id(self):
        self.record()
        payload = shell_payload("antigravity", "git status", self.main, session="other")
        payload["session_id"] = SESSION
        self.assert_passes(self.run_hook("antigravity", payload))


def write_lead_state(root, owner, name=LEAD_NAME):
    """Write a lead state in `root` that `owner` owns, or with no owner when `owner` is None."""
    state = Path(root) / ".scratch" / name / "state.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    fields = {"schema": 1, "slug": "x"}
    if owner is not None:
        fields["owner"] = owner
    state.write_text(json.dumps(fields), encoding="utf-8")
    return state


class RecordTests(HookCase):
    """A start records a session only in the thread that owns the lead state (#612). Unless a check
    names another thread, the hook runs in the owner's thread, and the main work tree and the folder of
    the installed copy each hold a lead state of that owner."""

    def setUp(self):
        super().setUp()
        self.addCleanup(shutil.rmtree, self.installed.parents[1] / ".scratch", True)
        for root in (self.main, self.installed.parents[1]):
            self.addCleanup(write_lead_state(root, OWNER_THREAD).unlink, missing_ok=True)

    def run_hook(self, host, payload, env=None):
        return super().run_hook(host, payload, {"T3CODE_THREAD_ID": OWNER_THREAD, **(env or {})})

    def assert_records(self, host, payload, env=None, recorded=True):
        shutil.rmtree(self.state, ignore_errors=True)
        self.assert_passes(self.run_hook(host, payload, env))
        self.assertEqual((self.state / SESSION).is_file(), recorded)

    def test_a_start_in_another_thread_records_nothing(self):
        """Issue #612: a worker ran start, and the hook blocked its work as a lead's."""
        start = f'python3 "{STEP_SCRIPT}" start'
        for host in HOSTS:
            # A worker in the lead's work tree, and a worker in its own worktree, with no lead state.
            for cwd, thread in ((self.main, WORKER_THREAD), (self.dev, WORKER_THREAD), (self.dev, OWNER_THREAD),
                                (self.dev, "")):
                with self.subTest(host=host, cwd=cwd, thread=thread):
                    self.assert_records(host, shell_payload(host, start, cwd), {"T3CODE_THREAD_ID": thread},
                                        recorded=False)
        self.assert_records("claude", shell_payload("claude", f"S={STEP_SCRIPT}; python3 $S start | head", self.main),
                            {"T3CODE_THREAD_ID": WORKER_THREAD}, recorded=False)

    def test_init_and_takeover_record_the_session(self):
        """Issue #612: init and takeover make a lead in any thread."""
        commands = (f"python3 {STEP_SCRIPT} init x", f"python3 {STEP_SCRIPT} init x --also",
                    f"python3 {STEP_SCRIPT} init --also x", f"python3 '{self.installed}' takeover",
                    f"S={STEP_SCRIPT}; python3 $S takeover 2>&1 | head -20",
                    f"S={STEP_SCRIPT}; python3 $S init x | head")
        for index, command in enumerate(commands):
            host = HOSTS[index % len(HOSTS)]
            for thread in (WORKER_THREAD, ""):
                with self.subTest(host=host, command=command, thread=thread):
                    self.assert_records(host, shell_payload(host, command, self.dev), {"T3CODE_THREAD_ID": thread})

    def test_init_or_takeover_with_other_words_records_nothing(self):
        for command in (f"python3 {STEP_SCRIPT} init", f"python3 {STEP_SCRIPT} init -h",
                        f"python3 {STEP_SCRIPT} init x y", f"python3 {STEP_SCRIPT} init x --also --also",
                        f"python3 {STEP_SCRIPT} takeover x", f"python3 {self.dev_script} takeover",
                        f"python3 {STEP_SCRIPT} unmark"):
            with self.subTest(command=command):
                self.assert_records("claude", shell_payload("claude", command, self.main), recorded=False)

    def test_a_start_that_the_hook_cannot_check_records_the_session(self):
        """Issue #612: the check fails closed. When a lead state may be there and the hook cannot tell its
        owner, a start records the session."""
        start = f'python3 "{STEP_SCRIPT}" start'
        self.assert_records("codex", shell_payload("codex", start, self.main), {"T3CODE_THREAD_ID": ""})
        self.assert_records("claude", shell_payload("claude", start, "relative/cwd"),
                            {"T3CODE_THREAD_ID": WORKER_THREAD})
        self.assert_records("claude", shell_payload("claude", f"cd {self.dev} && {start}", self.dev),
                            {"T3CODE_THREAD_ID": WORKER_THREAD})
        self.assert_records("claude", shell_payload("claude", start, self.main),
                            {"T3CODE_THREAD_ID": WORKER_THREAD, "PATH": "/nonexistent"})
        second = self.main / ".scratch" / "20261126-lead-two"
        self.addCleanup(shutil.rmtree, second, True)
        for owner, text in ((None, None), (OWNER_THREAD, "{not json"), (OWNER_THREAD, None)):
            state = write_lead_state(self.main, owner)
            if text is not None:
                state.write_text(text, encoding="utf-8")
            if owner is not None and text is None:
                # The third case: two lead states in one work tree.
                write_lead_state(self.main, OWNER_THREAD, second.name)
            with self.subTest(owner=owner, text=text):
                self.assert_records("antigravity", shell_payload("antigravity", start, self.main),
                                    {"T3CODE_THREAD_ID": WORKER_THREAD})

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
        cases = (("python scripts/t3_project_lead.py start", self.installed.parents[1], {}),
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
                            f"S={self.dev_script}; python3 $S start 2>&1 | head -80",
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

    def test_start_in_a_command_list_records_the_session(self):
        """Issue #574: a lead ran `start` only in command lists, and the hook kept no record."""
        commands = (f"S={STEP_SCRIPT}; python3 $S start 2>&1 | head -80",
                    f'S="{STEP_SCRIPT}" && python3 "$S" start',
                    f"export S='{self.installed}'; python3 \"${{S}}\" start > /dev/null",
                    f"python3 {STEP_SCRIPT} start | cat",
                    f"git status; python3 '{STEP_SCRIPT}' start &>/dev/null  # refresh",
                    f"cd {self.main} && python3 {STEP_SCRIPT} start\necho done")
        jobs = [(HOSTS[index % len(HOSTS)], command) for index, command in enumerate(commands)]
        jobs += [(host, commands[0]) for host in HOSTS[1:]]
        jobs += [("codex", {"command": ["bash", "-lc", commands[0]]}),
                 ("codex", {"cmd": f"bash -lc 'S={STEP_SCRIPT}; python3 \"$S\" start | head'"})]
        for host, command in jobs:
            with self.subTest(host=host, command=command):
                shutil.rmtree(self.state, ignore_errors=True)
                if isinstance(command, dict):
                    payload = tool_payload(host, "shell" if "command" in command else "exec_command", command,
                                           self.main)
                else:
                    payload = shell_payload(host, command, self.main)
                self.assert_passes(self.run_hook(host, payload))
                self.assertTrue((self.state / SESSION).is_file())

    def test_a_command_list_without_a_proven_start_records_nothing(self):
        """Issue #574: the hook records only a start that it can resolve to a qualifying script."""
        commands = (f"S={STEP_SCRIPT}; python3 $S start extra | cat",
                    f"echo 'python3 {STEP_SCRIPT} start'; true",
                    f"grep -n 'python3 {STEP_SCRIPT} start' notes.md | head",
                    f"S={STEP_SCRIPT} python3 $S start | cat",
                    f"S={STEP_SCRIPT} | python3 $S start",
                    f"S={STEP_SCRIPT} & python3 $S start",
                    f"S=$(echo {STEP_SCRIPT}); python3 $S start",
                    f"cat <(python3 {STEP_SCRIPT} start); true",
                    f"(python3 {STEP_SCRIPT} start) | cat",
                    f"{{ python3 {STEP_SCRIPT} start; }} 2>&1 | head",
                    f"cat <<EOF\npython3 {STEP_SCRIPT} start\nEOF",
                    f"python3 $LEAD_TEST_UNSET/{STEP_SCRIPT.name} start | cat",
                    f"cd {self.temp} && python scripts/t3_project_lead.py start | cat",
                    f"{{ true; python3 {STEP_SCRIPT} start; }} | cat",
                    f"{{\npython3 {STEP_SCRIPT} start\n}}",
                    f"function f {{\npython3 {STEP_SCRIPT} start\n}}",
                    f"{{ true; S={STEP_SCRIPT}; }} | cat; python3 $S start",
                    f"if false\nthen\npython3 {STEP_SCRIPT} start\nfi",
                    f"S={STEP_SCRIPT}; unset S; python3 $S start",
                    f"S={STEP_SCRIPT}; S+=x; python3 $S start",
                    f"S={STEP_SCRIPT}; IFS=/; python3 $S start",
                    f"builtin cd {self.temp} && python scripts/t3_project_lead.py start",
                    f"exit; python3 {STEP_SCRIPT} start",
                    f"python3 {STEP_SCRIPT} start ;;")
        for index, command in enumerate(commands):
            host = HOSTS[index % len(HOSTS)]
            with self.subTest(host=host, command=command):
                self.assert_passes(self.run_hook(host, shell_payload(host, command, PLUGIN_ROOT)))
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
                          f"S={STEP_SCRIPT}; python3 $S start 2>&1 | head -80",
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
        # Antigravity has no known hook payload for its question tool; the step text holds the rule (#554).
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
        # One T3 Code build names the check parameter sections (#604), and another names it include (#638).
        # Without either, a build returns its default, and the sections default holds the summary, which can
        # hold the PR body. The two parameters set to different values also block.
        values = (["summary"], ["conversation"], ["diff"], ["body"], ["comments"], ["threads"], ["checks", "summary"],
                  ["diff", "checks"], ["body", "checks", "threads", "comments", "diff"])
        inputs = ([{"number": 5, key: value} for key in ("sections", "include") for value in values]
                  + [{}, {"number": 5}, {"repository": "o/r", "includeResolved": True},
                     {"sections": ["checks"], "include": ["body"]}, {"sections": ["body"], "include": ["checks"]},
                     {"sections": ["checks"], "include": ["checks", "diff"]}])
        self.check_text_reads(text_calls(PR_READ, inputs), allowed=False)

    def test_pull_request_read_without_text_passes(self):
        # The T3 Code shape of #638 is {"number": 630, "include": ["checks"]}.
        inputs = ({"sections": ["checks"]}, {"number": 5, "sections": ["checks"]},
                  {"repository": "o/r", "includeResolved": True, "cursor": "c1", "sections": ["checks"]},
                  {"number": 630, "include": ["checks"]}, {"include": ["checks"]},
                  {"repository": "o/r", "includeResolved": True, "cursor": "c1", "include": ["checks"]},
                  {"sections": ["checks"], "include": ["checks"]})
        self.check_text_reads(text_calls(PR_READ, inputs), allowed=True)

    def test_an_unreadable_pull_request_read_is_blocked(self):
        # The hook fails closed: sections or include other than exactly ["checks"], or a tool input that is
        # not an object (Codex passes arguments that do not parse as a string).
        values = ("checks", None, [], ["checks", "checks"], [1], ["checks", None], {"checks": True}, ["Checks"],
                  ["files"])
        inputs = ([{key: value} for key in ("sections", "include") for value in values]
                  + [{"sections": ["checks"], "include": value} for value in values]
                  + [{"sections": value, "include": ["checks"]} for value in values]
                  + ["{not json", ["sections"], ["include"], None])
        self.check_text_reads(text_calls(PR_READ, inputs), allowed=False)

    def check_named(self, cases, *, allowed, line=None):
        """Check (host, name, tool input) calls; a blocked call prints `line` after the block line."""
        jobs = [(host, tool_payload(host, name, tool_input, self.main)) for host, name, tool_input in cases]
        self.check(jobs, allowed=allowed)
        if not allowed:
            for host, payload in jobs:
                with self.subTest(host=host, payload=payload):
                    self.assertEqual(self.run_hook(host, payload).stderr.splitlines()[1], line)

    def test_question_tools_are_blocked(self):
        # A lead lists in plain text and asks the user no choice question (#554).
        self.check_named(text_calls(QUESTION_TOOLS, (QUESTION_INPUT, {}, "not a dict")), allowed=False,
                         line=QUESTION_LINE)

    def test_an_answer_to_a_worker_question_is_blocked(self):
        # The hook fails closed: only list and read pass (#554).
        inputs = (RESPOND, {"action": "respond"}, {}, {"action": None}, {"action": ["list"]}, {"action": "Respond"},
                  {"action": "write"}, "not a dict", None)
        self.check_named(text_calls(PENDING, inputs), allowed=False, line=RESPOND_LINE)

    def test_a_thread_read_without_a_page_size_is_blocked(self):
        # The hook fails closed: maxCharsPerItem must be a positive integer (#632).
        inputs = ({"threadId": "worker-1"}, {"threadId": "worker-1", "itemId": "i1", "textOffset": 500},
                  *({"threadId": "worker-1", "maxCharsPerItem": value}
                    for value in (None, True, False, "8000", 0, -1, 1.5, [8000])), {}, "not a dict", None)
        self.check_named(text_calls(THREAD_READ, inputs), allowed=False, line=THREAD_LINE)

    def test_a_thread_read_with_a_page_size_passes(self):
        inputs = ({"threadId": "worker-1", "maxCharsPerItem": 8000},
                  {"threadId": "worker-1", "maxCharsPerItem": 1, "view": "activity", "limit": 5},
                  {"threadId": "worker-1", "itemId": "i1", "textOffset": 8000, "maxCharsPerItem": 20000})
        self.check_named(text_calls(THREAD_READ, inputs), allowed=True)

    def test_a_list_or_read_of_pending_requests_passes(self):
        inputs = ({"action": "list"}, {"action": "list", "threadId": "worker-1"},
                  {"action": "read", "threadId": "worker-1", "requestId": "r1"})
        self.check_named(text_calls(PENDING, inputs), allowed=True)

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


class SettleTests(HookCase):
    """A recorded session settles (#645) or archives (#659) no lead thread: only the user does."""

    def setUp(self):
        super().setUp()
        self.record()
        # A folder outside every Git work tree, with a lead state that another thread owns, as after a
        # takeover.
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.tree = Path(temp_dir.name).resolve()
        self.lead_state = self.tree / ".scratch" / "20261126-lead-y" / "state.json"
        self.lead_state.parent.mkdir(parents=True)
        self.lead_state.write_text(json.dumps({"schema": 1, "slug": "y", "owner": OWNER_THREAD}),
                                   encoding="utf-8")

    def check_settles(self, inputs, *, allowed, cwd=None, thread=LEAD_THREAD, lines=SETTLE_LINES):
        """Check each tool input with each Claude Code and Codex name of t3_thread_organize, in a session
        of the T3 thread `thread`; a blocked call prints `lines`."""
        env = {"T3CODE_THREAD_ID": thread} if thread is not None else {}
        jobs = [(host, tool_payload(host, name, tool_input, self.main if cwd is None else cwd))
                for host, names in ORGANIZE.items() for name in names for tool_input in inputs]
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda job: self.run_hook(*job, env), jobs))
        for (host, payload), result in zip(jobs, results):
            with self.subTest(host=host, payload=payload, thread=thread):
                if allowed:
                    self.assert_passes(result)
                else:
                    self.assertEqual((result.returncode, result.stdout), (2, ""), result.stderr)
                    self.assertEqual(result.stderr.splitlines(), lines)

    def test_a_settle_with_no_thread_is_blocked(self):
        # A call with no threadId settles the calling thread, the lead thread.
        inputs = ({"action": "settle"}, {"action": "settle", "environmentId": "env-1"},
                  *({"action": "settle", "threadId": value} for value in (None, "", "  ", 7, [WORKER_THREAD])))
        for thread in (LEAD_THREAD, None):
            self.check_settles(inputs, allowed=False, thread=thread)
        self.check_settles(inputs, allowed=False, cwd=self.tree)

    def test_a_settle_of_the_lead_thread_is_blocked(self):
        # The calling thread of a recorded session is a lead thread.
        self.check_settles(({"action": "settle", "threadId": LEAD_THREAD},
                            {"action": "settle", "threadId": f" {LEAD_THREAD} "},
                            {"action": " Settle", "threadId": LEAD_THREAD}), allowed=False)
        # The owner of the lead state is the lead thread, also for a session of another thread.
        for thread in (LEAD_THREAD, None):
            self.check_settles(({"action": "settle", "threadId": OWNER_THREAD},), allowed=False, cwd=self.tree,
                               thread=thread)

    def test_a_settle_of_a_worker_thread_passes(self):
        inputs = ({"action": "settle", "threadId": WORKER_THREAD},
                  {"action": "settle", "threadId": WORKER_THREAD, "environmentId": "env-1"})
        self.check_settles(inputs, allowed=True)
        self.check_settles(inputs, allowed=True, cwd=self.tree)
        self.check_settles(inputs, allowed=True, cwd=self.tree, thread=None)

    def test_a_settle_that_the_hook_cannot_check_is_blocked(self):
        # The hook fails closed: it blocks a settle when it knows no lead thread, when the call has no
        # absolute cwd, and when it cannot read the lead state.
        worker = ({"action": "settle", "threadId": WORKER_THREAD},)
        self.check_settles(worker, allowed=False, thread=None)
        self.check_settles(worker, allowed=False, cwd="relative/cwd")
        self.lead_state.write_text("{not json", encoding="utf-8")
        self.check_settles(worker, allowed=False, cwd=self.tree)
        second = self.tree / ".scratch" / "20261126-lead-z" / "state.json"
        second.parent.mkdir()
        second.write_text(json.dumps({"schema": 1, "slug": "z", "owner": OWNER_THREAD}), encoding="utf-8")
        self.lead_state.write_text(json.dumps({"schema": 1, "slug": "y", "owner": OWNER_THREAD}),
                                   encoding="utf-8")
        self.check_settles(worker, allowed=False, cwd=self.tree)
        self.check_settles(("not a dict", None, {"threadId": WORKER_THREAD},
                            *({"action": value, "threadId": WORKER_THREAD} for value in (None, ["settle"], 1))),
                           allowed=False)

    def test_an_archive_of_a_lead_thread_is_blocked(self):
        # An archive takes a thread off the user's active list, as a settle does (#659).
        blocked = ({"action": "archive"}, {"action": "archive", "environmentId": "env-1"},
                   {"action": "archive", "threadId": ""}, {"action": "archive", "threadId": LEAD_THREAD},
                   {"action": " Archive", "threadId": f" {LEAD_THREAD} "})
        for thread in (LEAD_THREAD, None):
            self.check_settles(blocked, allowed=False, thread=thread, lines=ARCHIVE_LINES)
        self.check_settles(({"action": "archive", "threadId": OWNER_THREAD},), allowed=False, cwd=self.tree,
                           lines=ARCHIVE_LINES)
        # It fails closed as a settle does: no known lead thread, or no absolute cwd.
        worker = ({"action": "archive", "threadId": WORKER_THREAD},)
        self.check_settles(worker, allowed=False, thread=None, lines=ARCHIVE_LINES)
        self.check_settles(worker, allowed=False, cwd="relative/cwd", lines=ARCHIVE_LINES)

    def test_an_archive_of_a_worker_thread_passes(self):
        inputs = ({"action": "archive", "threadId": WORKER_THREAD},)
        self.check_settles(inputs, allowed=True)
        self.check_settles(inputs, allowed=True, cwd=self.tree, thread=None)

    def test_a_lead_pins_unpins_and_unsettles_a_worker_thread(self):
        # T3 Code settles a delegated worker when its turn ends, unless the thread is pinned (#668): the lead
        # pins each worker, unpins it when its task is verified or cancelled, and unsettles a waiting worker.
        inputs = [{"action": action, "threadId": WORKER_THREAD, **extra}
                  for action in ("pin", "unpin", "unsettle") for extra in ({}, {"environmentId": "env-1"})]
        self.check_settles(inputs, allowed=True)
        self.check_settles(inputs, allowed=True, cwd=self.tree, thread=None)
        self.check_settles(inputs, allowed=True, cwd="relative/cwd")

    def test_other_actions_pass(self):
        self.check_settles(({"action": "pin"}, {"action": "unsettle"}, {"action": "mark_unread"},
                            {"action": "snooze", "snoozedUntil": "2026-11-27T09:00:00Z"},
                            {"action": "unarchive", "threadId": LEAD_THREAD}), allowed=True)


class ProjectScopeTests(HookCase):
    """A recorded session aims no call at another project (#666)."""

    def setUp(self):
        super().setUp()
        self.record()

    def check_project(self, calls, *, allowed, env=None):
        """Check each call of `calls`; a blocked call prints the project lines."""
        jobs = [(host, tool_payload(host, name, tool_input, self.main)) for host, name, tool_input in calls]
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda job: self.run_hook(*job, env), jobs))
        for (host, payload), result in zip(jobs, results):
            with self.subTest(host=host, payload=payload):
                if allowed:
                    self.assert_passes(result)
                else:
                    self.assertEqual((result.returncode, result.stdout), (2, ""), result.stderr)
                    self.assertEqual(result.stderr.splitlines(), PROJECT_LINES)

    def test_a_call_aimed_at_another_project_is_blocked(self):
        # The check reads no T3CODE_THREAD_ID, which a Codex hook may lack (#612, #645).
        for env in (None, {"T3CODE_THREAD_ID": LEAD_THREAD}):
            self.check_project(project_calls(OTHER_PROJECT_CALLS), allowed=False, env=env)

    def test_the_same_call_aimed_at_the_own_project_passes(self):
        for env in (None, {"T3CODE_THREAD_ID": LEAD_THREAD}):
            self.check_project(project_calls(OWN_PROJECT_CALLS), allowed=True, env=env)

    def test_a_report_or_an_issue_in_another_project_passes(self):
        self.check_project(project_calls(ALLOWED_PROJECT_CALLS), allowed=True)

    def test_a_call_that_the_hook_cannot_check_is_blocked(self):
        # The hook fails closed: it cannot tell the lead's own project ID from another one, and it blocks
        # an input that it cannot read.
        self.check_project(project_calls({
            "delegate_task": ("not a dict", None, {"task": "Fix it.", "target": OTHER_PROJECT},
                              {"task": "Fix it.", "target": None}, {"task": "Fix it.", "projectId": None}),
            "create_threads": ({}, {"threads": {"prompt": "Fix it."}}, {"threads": ["Fix it."]},
                               {"threads": [{"prompt": "Fix it.", "target": [OTHER_PROJECT]}]}),
            "t3_thread_launch": ({"title": "Fix", "scratch": "false"}, {"title": "Fix", "projectId": ""}),
            "t3_thread_list": (None, {"allProjects": None}, {"allProjects": "false"}, {"allProjects": 0}),
            "list_issues": ([], {"projectId": None}),
        }), allowed=False)


class UnmarkTests(HookCase):
    """`unmark` removes the record of a session whose thread is not a lead (#612). The main work tree holds
    a lead state that the lead thread owns; the developer's worktree is a worker's worktree."""

    def setUp(self):
        super().setUp()
        self.record()
        self.lead_state = write_lead_state(self.main, OWNER_THREAD)
        self.addCleanup(self.lead_state.unlink, missing_ok=True)
        self.unmark = f'python3 "{STEP_SCRIPT}" unmark'

    def check_unmark(self, cwd, thread, reason=None, extra=None):
        """Run unmark in `cwd` in a session of T3 thread `thread`, with the variables `extra` added; with a
        `reason`, check that the hook blocks it with that reason and keeps the record."""
        before = self.lead_state.read_bytes() if self.lead_state.exists() else None
        for host in HOSTS:
            with self.subTest(host=host, cwd=cwd, thread=thread):
                self.record()
                result = self.run_hook(host, shell_payload(host, self.unmark, cwd),
                                       {"T3CODE_THREAD_ID": thread, **(extra or {})})
                if reason is None:
                    self.assert_passes(result)
                    self.assertFalse((self.state / SESSION).exists())
                else:
                    self.assertEqual((result.returncode, result.stdout), (2, ""), result.stderr)
                    first, second = result.stderr.splitlines()
                    self.assertEqual(first, UNMARK_LINE)
                    self.assertTrue(second.startswith(UNMARK_REASON), second)
                    self.assertIn(reason, second)
                    self.assertTrue((self.state / SESSION).is_file())
        self.assertEqual(self.lead_state.read_bytes() if self.lead_state.exists() else None, before)

    def test_unmark_removes_the_record_of_a_worker(self):
        self.check_unmark(self.dev, WORKER_THREAD)
        self.check_unmark(self.main, WORKER_THREAD)

    def test_unmark_keeps_the_record_of_a_lead(self):
        # The owner of a lead state, also in another worktree of the repository.
        self.check_unmark(self.main, OWNER_THREAD, "this thread owns the lead state")
        self.check_unmark(self.dev, OWNER_THREAD, "this thread owns the lead state")
        # A lead after finish: only the user settles a lead thread, so the hook keeps its record.
        self.lead_state.unlink()
        self.check_unmark(self.dev, WORKER_THREAD, "no worktree of this repository holds a lead state")

    def test_an_unmark_that_the_hook_cannot_check_keeps_the_record(self):
        self.check_unmark(self.dev, "", "no T3CODE_THREAD_ID")
        self.check_unmark("relative/cwd", WORKER_THREAD, "the call has no absolute cwd")
        write_lead_state(self.main, None)
        self.check_unmark(self.dev, WORKER_THREAD, "has no owner")
        self.lead_state.write_text("{not json", encoding="utf-8")
        self.check_unmark(self.dev, WORKER_THREAD, "cannot read the lead states")
        write_lead_state(self.main, OWNER_THREAD)
        self.check_unmark(self.dev, WORKER_THREAD, "could not check the lead states", extra={"PATH": "/nonexistent"})

    def test_an_unmark_in_another_folder_keeps_the_record(self):
        # The record covers the whole session, and a Codex workdir or an Antigravity Cwd can name a folder of
        # another repository, so the call must run in the session's cwd.
        cases = (("codex", "exec_command", {"cmd": self.unmark, "workdir": str(self.dev)}),
                 ("antigravity", "run_command", {"CommandLine": self.unmark, "Cwd": str(self.dev)}))
        for host, name, tool_input in cases:
            with self.subTest(host=host):
                result = self.run_hook(host, tool_payload(host, name, tool_input, self.main),
                                       {"T3CODE_THREAD_ID": WORKER_THREAD})
                self.assertEqual((result.returncode, result.stdout), (2, ""), result.stderr)
                self.assertEqual(result.stderr.splitlines(), [
                    UNMARK_LINE, UNMARK_REASON + "the call names a folder other than the session's cwd."])
                self.assertTrue((self.state / SESSION).is_file())
        same = tool_payload("codex", "exec_command", {"cmd": self.unmark, "workdir": str(self.main)}, self.main)
        self.assert_passes(self.run_hook("codex", same, {"T3CODE_THREAD_ID": WORKER_THREAD}))
        self.assertFalse((self.state / SESSION).exists())

    def test_unmark_with_more_words_is_no_unmark(self):
        self.check([(host, shell_payload(host, f"{self.unmark} now", self.dev)) for host in HOSTS], allowed=True,
                   env={"T3CODE_THREAD_ID": WORKER_THREAD})
        self.assertTrue((self.state / SESSION).is_file())


class ToolResultReadTests(HookCase):
    """A recorded session reads the tool outputs that Claude Code saved for it (#621): a lead could not
    read a long `show` output."""

    def setUp(self):
        super().setUp()
        self.record()
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.project = Path(temp_dir.name).resolve() / "projects" / "-repo"
        self.transcript = self.project / f"{SESSION}.jsonl"
        self.results = self.project / SESSION / "tool-results"
        self.saved = self.results / "btcdkaz4q.txt"
        self.other = self.project / "other-session" / "tool-results" / "b1.txt"
        for path in (self.transcript, self.saved, self.other):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("Lead state: x\n", encoding="utf-8")

    def check_reads(self, cases, *, allowed, transcript=None):
        jobs = []
        for host, name, tool_input in cases:
            payload = tool_payload(host, name, tool_input, self.main)
            payload["transcript_path"] = str(self.transcript) if transcript is None else transcript
            if transcript is False:
                payload.pop("transcript_path")
            jobs.append((host, payload))
        self.check(jobs, allowed=allowed)

    def test_a_saved_tool_output_of_this_session_is_readable(self):
        self.check_reads((("claude", "Read", {"file_path": str(self.saved)}),
                          ("claude", "Read", {"file_path": str(self.saved), "offset": 200, "limit": 200}),
                          ("claude", "Bash", {"command": f"head -c 4000 {self.saved}"}),
                          ("claude", "Bash", {"command": f"sed -n 1,80p '{self.saved}'"}),
                          ("claude", "Bash", {"command": f"ls {self.results}"}),
                          ("claude", "Grep", {"pattern": "Decisions", "path": str(self.results)}),
                          ("codex", "Bash", {"command": f"cat {self.saved}"})), allowed=True)

    def test_other_saved_outputs_are_blocked(self):
        blocked = (("claude", "Read", {"file_path": str(self.other)}),
                   ("claude", "Read", {"file_path": str(self.transcript)}),
                   ("claude", "Read", {"file_path": f"{self.results}/../../other-session/tool-results/b1.txt"}),
                   ("claude", "Bash", {"command": f"cat {self.saved} | head"}))
        self.check_reads(blocked, allowed=False)
        payload = tool_payload("claude", "Read", {"file_path": str(self.other)}, self.main)
        payload["transcript_path"] = str(self.transcript)
        self.assertEqual(self.run_hook("claude", payload).stderr.splitlines(), [BLOCK_LINE, READ_LINE])
        mine = (("claude", "Read", {"file_path": str(self.saved)}), ("codex", "Bash", {"command": f"cat {self.saved}"}))
        # The rule needs the transcript path of this session, as Claude Code gives it.
        for transcript in (False, str(self.project / "other-session.jsonl"), f"{SESSION}.jsonl", 7):
            with self.subTest(transcript=transcript):
                self.check_reads(mine, allowed=False, transcript=transcript)
        self.check([("antigravity", tool_payload("antigravity", "view_file", {"AbsolutePath": str(self.saved)},
                                                 self.main))], allowed=False)


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

    def test_reads_of_gtd_files_outside_git_pass(self):
        """Issue #621: a lead could not read the binding copy and request files that it wrote."""
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        folder = Path(temp_dir.name).resolve() / "gtd-31"
        folder.mkdir()
        for name, text in (("binding.json", BINDING), ("request.json", REQUEST), ("other.json", '{"a": 1}'),
                           ("request.txt", REQUEST), ("broken.json", REQUEST[:-1])):
            (folder / name).write_text(text, encoding="utf-8")
        (folder / "link.json").symlink_to(self.main / "notes.json")
        inside = self.main / "r.json"
        inside.write_text(REQUEST, encoding="utf-8")
        self.addCleanup(inside.unlink)
        allowed = (("claude", "Read", {"file_path": str(folder / "binding.json")}),
                   ("claude", "Read", {"file_path": str(folder / "request.json")}),
                   ("codex", "Bash", {"command": f"cat {folder}/request.json"}),
                   ("antigravity", "view_file", {"AbsolutePath": str(folder / "binding.json")}))
        blocked = [("claude", "Read", {"file_path": str(folder / name)})
                   for name in ("other.json", "request.txt", "broken.json", "link.json", "missing.json")]
        blocked += [("claude", "Read", {"file_path": str(inside)}), ("codex", "Bash", {"command": f"ls {folder}"}),
                    ("codex", "Bash", {"command": f"cat {folder}/request.json {self.main}/notes.md"})]
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
                    "Agent", "Task", "AskUserQuestion", *READ_ISSUE["claude"], *PR_READ["claude"],
                    *PENDING["claude"], *THREAD_READ["claude"], *ORGANIZE["claude"],
                    *(name for tool in OTHER_PROJECT_CALLS for name in t3_names(tool)["claude"])}
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
        for name in (*READ_ISSUE["codex"], *PR_READ["codex"], *PENDING["codex"], *QUESTION_TOOLS["codex"],
                     *THREAD_READ["codex"], *ORGANIZE["codex"],
                     *(name for tool in OTHER_PROJECT_CALLS for name in t3_names(tool)["codex"])):
            with self.subTest(name=name):
                self.assertRegex(name, entry["matcher"])
        for name in ("mcp__t3_code__list_issues_x", "mcp__t3_code__read_issue_x", "mcp__other__read_issue",
                     "mcp__0123456789__t3_code__read_issue", "xmcp__t3_code__read_issue",
                     "mcp__t3_code__t3_pending_requests", "mcp__other__t3_pending_request", "request_user_input_x",
                     "x_request_user_input", "mcp__t3_code__t3_thread_read_x", "mcp__other__t3_thread_read",
                     "mcp__t3_code__t3_thread_list_x", "mcp__t3_code__t3_thread_organize_x",
                     "mcp__other__t3_thread_organize", "mcp__other__delegate_task", "mcp__t3_code__t3_thread_send",
                     "mcp__t3_code__t3_thread_search", "mcp__t3_code__create_issue"):
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
