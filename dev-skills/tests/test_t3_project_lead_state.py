"""Command-line checks for the lead state of t3_project_lead.py (issue #530).

Each check builds a temporary Git repository and runs the script in it, as a
project lead does. The checks read the script's output, exit status, and the
files of the lead folder: the life cycle and its refusals, UTC times, the
view, the due lines, what waits on the user, and finish. Issue #493 adds the
tasks that are ready to start: a task starts as soon as each task that it waits
for is verified, and does not wait for the rest of its batch. Issue #534 prints
the waiting list as Markdown bullets that keep the item numbers, and adds a
period only to text that does not end in ".", "?", or "!". Issue #544 binds
the lead state to its T3 thread (`T3CODE_THREAD_ID`), adds `takeover`, and
lists the lead states of the other worktrees, which the checks make with
`git worktree add`. Issue #545 tells a new lead to run `init` and the
discovery task, and names the `discover` step while no outcome is set.
Issue #555 makes the view of `start` compact, gives all paused tasks one due
line, and lets `done` and `task pause|resume|verified|settled` take several
arguments. Issue #556 records each worker's worktree, and issue #560 starts a
new batch for a work task once a PR of the highest batch merged.

Issue #568: most checks call the script's `main()` in this process, with the
check's environment and folder, because a new Python process for each of
about 530 commands made the module slow. So the script must read its
environment and folder when a command runs, not when it is imported.
`test_the_command_line_runs_as_a_process` runs the script as a process, as a
lead does.
"""

from __future__ import annotations

import contextlib
import datetime
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "t3_project_lead.py"
_SPEC = importlib.util.spec_from_file_location("t3_project_lead_under_test", SCRIPT)
LEAD = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(LEAD)
UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
WORKER = "t3-thread://v2/env/thread-{}"
# The T3 thread of the lead in each check, and another thread, such as a fork (#544).
OWNER = "thread-lead"
OTHER = "thread-fork"
TAKEOVER_LINE = ("Check for work this state does not name: t3_thread_list with includeSubagents, and "
                 "pull_request_list. Record each worker with task add and task start, or add a waiting "
                 "item.")
# The due line of a finished lead names the report rule for decisions first (#567).
FINISH_LINE = ("Every task is settled and nothing waits. Add each decision that only the user can make "
               "with wait, as t3_project_lead.py report says; then run t3_project_lead.py finish.")
# What the script says about a lead state in another worktree, and how a flagged lead recovers.
CONTINUE = ("Continue that lead in its own worktree. A lead can continue in three ways: change the provider "
            "of the lead thread; fork the lead thread; or start a thread with t3_thread_launch and "
            "workspaceStrategy existing_worktree with the worktree that the list names. In a fork or a new "
            "thread, run start, then takeover.")
RECOVERY = ("Recovery of a flagged lead: start a new thread bound to this worktree with t3_thread_launch and "
            "workspaceStrategy existing_worktree, on another model. In it, run start, then takeover. Do not "
            "fork the flagged thread: a fork copies the flagged context. Do not delete the flagged thread "
            "before the takeover.")
# Each command that changes or deletes the lead state, with arguments that it would accept.
CHANGE_COMMANDS = (
    ("outcome", "Ship it."), ("criteria", "Tests pass."), ("wait", "Approve it?"), ("done", "1"),
    ("decision", "add", "Squash."), ("decision", "drop", "D1"), ("task", "add", "b", "Task b"),
    ("task", "start", "a", WORKER.format(1)), ("task", "worker", "a", WORKER.format(2)),
    ("task", "pr", "a", "5"), ("task", "merged", "a", "5", "abcdef1"),
    ("task", "verified", "a", "--decisions", "0"),
    ("task", "settled", "a"), ("task", "cancel", "a"), ("task", "pause", "a"), ("task", "resume", "a"),
    ("finish",),
)


def words(text: str) -> str:
    """Return the text on one line, so that line wrapping does not change a match."""
    return " ".join(text.split())


@unittest.skipUnless(shutil.which("git"), "needs git")
class LeadStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = self.tmp / "repo"
        (self.repo / "sub").mkdir(parents=True)
        self.env = dict(os.environ, GIT_CONFIG_GLOBAL=str(self.tmp / "gitconfig"),
                        GIT_CONFIG_NOSYSTEM="1", GIT_CEILING_DIRECTORIES=str(self.tmp),
                        T3CODE_THREAD_ID=OWNER)
        subprocess.run(["git", "init", "-q"], cwd=self.repo, env=self.env, check=True)

    def run_lead(self, *args: str, cwd: Path | None = None, thread: str | None = OWNER,
                 path: str | None = None, process: bool = False) -> subprocess.CompletedProcess[str]:
        """Run the script in the T3 thread `thread`; None runs it without T3CODE_THREAD_ID. `path`
        replaces PATH. The script's `main()` runs in this process, with the environment and the folder
        of a process (#568); `process` runs the script as a process instead."""
        env = {key: value for key, value in self.env.items() if key != "T3CODE_THREAD_ID"}
        if thread is not None:
            env["T3CODE_THREAD_ID"] = thread
        if path is not None:
            env["PATH"] = path
        if process:
            return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd or self.repo,
                                  env=env, capture_output=True, text=True, check=False)
        stdout, stderr = io.StringIO(), io.StringIO()
        folder = os.getcwd()
        try:
            os.chdir(cwd or self.repo)
            # argparse names the program from sys.argv[0], and newer Pythons from the spec of __main__,
            # which is None when a script runs as a process.
            with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(sys, "argv", [str(SCRIPT)]), \
                    mock.patch.object(sys.modules["__main__"], "__spec__", None, create=True), \
                    contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                try:
                    code = LEAD.main(list(args))
                except SystemExit as exit_:
                    # As a process: None exits 0, and another value that is not a number prints and exits 1.
                    code = 0 if exit_.code is None else exit_.code if isinstance(exit_.code, int) else 1
                    if not isinstance(exit_.code, (int, type(None))):
                        print(exit_.code, file=sys.stderr)
        finally:
            os.chdir(folder)
        return subprocess.CompletedProcess([str(SCRIPT), *args], code, stdout.getvalue(), stderr.getvalue())

    def ok(self, *args: str, cwd: Path | None = None, thread: str | None = OWNER) -> str:
        result = self.run_lead(*args, cwd=cwd, thread=thread)
        self.assertEqual(result.returncode, 0, f"{args}: {result.stderr}")
        return result.stdout

    def refused(self, *args: str, reason: str, thread: str | None = OWNER) -> str:
        before = (self.state_text(), self.events())
        result = self.run_lead(*args, thread=thread)
        self.assertEqual(result.returncode, 1, f"{args}: {result.stdout}")
        self.assertIn(reason, words(result.stderr))
        self.assertEqual((self.state_text(), self.events()), before, "a refused command changed the state")
        return words(result.stderr)

    def worktree(self, name: str) -> Path:
        """Add a linked worktree of the repository, as T3 Code makes for a new thread."""
        if not subprocess.run(["git", "rev-parse", "-q", "--verify", "HEAD"], cwd=self.repo, env=self.env,
                              capture_output=True, check=False).stdout:
            subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q",
                            "--allow-empty", "-m", "init"], cwd=self.repo, env=self.env, check=True)
        path = self.tmp / name
        subprocess.run(["git", "worktree", "add", "-q", "-b", name, str(path)], cwd=self.repo,
                       env=self.env, check=True)
        return path

    def folder(self) -> Path:
        (folder,) = (self.repo / ".scratch").glob("*-lead-*")
        return folder

    def state_text(self) -> str:
        return (self.folder() / "state.json").read_text(encoding="utf-8")

    def task(self, name: str) -> dict:
        state = json.loads(self.state_text())
        return next(task for task in state["tasks"] if task["name"] == name)

    def events(self) -> list[dict]:
        lines = (self.folder() / "events.jsonl").read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines]

    def merged_task(self, name: str, pr: str, batch: str = "1") -> None:
        """Add a task and take it to verified through one merged PR."""
        self.ok("task", "add", name, f"Title of {name}", "--batch", batch)
        self.ok("task", "start", name, WORKER.format(name))
        self.ok("task", "pr", name, pr)
        self.ok("task", "merged", name, pr, "abcdef1")
        self.ok("task", "verified", name, "--decisions", "0")

    def test_the_command_line_runs_as_a_process(self) -> None:
        # The other checks call main() in this process (#568). This one runs the script as a lead does,
        # and checks that each exit status and stream of the process matches the in-process call.
        for args in (("init", "demo"), ("task", "add", "a", "Title")):
            result = self.run_lead(*args, process=True)
            self.assertEqual((result.returncode, result.stderr), (0, ""), args)
        start = self.run_lead("start", process=True)
        self.assertEqual((start.returncode, start.stderr), (0, ""))
        self.assertEqual(start.stdout.splitlines()[0], f'Steps: "{SCRIPT}"')
        self.assertIn("\nOther tasks: 1 planned. Decisions: 0.", start.stdout)
        for args, code in ((("waiting",), 0), (("task", "start", "missing", WORKER.format(1)), 1),
                           (("merge",), 2)):
            with self.subTest(args=args):
                result = self.run_lead(*args, process=True)
                inside = self.run_lead(*args)
                self.assertEqual((result.returncode, inside.returncode), (code, code), result.stderr)
                self.assertEqual((result.stdout, result.stderr), (inside.stdout, inside.stderr))
                self.assertTrue(result.stderr if code else result.stdout)

    def test_start_without_a_lead_state_prints_how_to_create_one(self) -> None:
        other = self.worktree("b")
        for where in (self.repo, other):
            with self.subTest(where=where.name):
                output = self.ok("start", cwd=where)
                self.assertIn("Do only these lead actions yourself:", output)
                self.assertIn(f'python3 "{SCRIPT}" init <slug>', output)
                self.assertIn("On this first start, run: ", output)
                self.assertIn("start the discovery task as t3_project_lead.py discover says, and come to the "
                              "user only with its list of open work.", words(output))
                self.assertNotIn("other worktrees", output)

    def test_a_git_failure_prints_a_listing_problem_and_refuses_init(self) -> None:
        no_git = self.tmp / "no-git"
        no_git.mkdir()
        output = self.run_lead("start", path=str(no_git)).stdout
        self.assertIn("Could not list the worktrees: ", output)
        self.assertIn(f'python3 "{SCRIPT}" init <slug>', output)
        result = self.run_lead("init", "demo", path=str(no_git))
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("could not list the worktrees, so another one may hold a lead state", result.stderr)
        self.assertIn("Only after the user confirms a second lead state, run init demo --also.",
                      words(result.stderr))
        self.assertFalse((self.repo / ".scratch").exists())

    def test_a_folder_outside_git_has_no_other_worktree(self) -> None:
        plain = self.tmp / "plain"
        plain.mkdir()
        output = self.ok("start", cwd=plain)
        self.assertIn(f'python3 "{SCRIPT}" init <slug>', output)
        self.assertNotIn("Could not list", output)
        self.assertIn("Lead state created: ", self.ok("init", "demo", cwd=plain))
        self.assertIn("Lead state: demo, ", self.ok("show", cwd=plain))

    def test_start_in_another_worktree_lists_the_lead_state_and_offers_no_init(self) -> None:
        self.ok("init", "demo")
        for name in ("a", "b", "c"):
            self.ok("task", "add", name, f"Task {name}")
        self.ok("task", "cancel", "c")
        self.ok("task", "settled", "c")
        self.ok("wait", "Approve the release?")
        other = self.worktree("b")
        output = self.ok("start", cwd=other)
        line = (f"- {self.folder()}: slug demo, owner {OWNER}, last change {self.events()[-1]['time']}, "
                f"2 open tasks, 1 waiting item. Worktree: {self.repo}")
        self.assertIn(line + "\n", output)
        self.assertIn(f"{CONTINUE} Do not run init here.", words(output))
        self.assertNotIn("init <slug>", output)
        self.assertFalse((other / ".scratch").exists(), "the lookup wrote to the new worktree")
        shutil.copytree(self.folder(), self.folder().with_name("20260101-lead-old"))
        self.assertIn(f"- More than one lead state in {self.repo / '.scratch'}: ",
                      self.ok("start", cwd=other))

    def test_init_refuses_a_second_lead_state_without_also(self) -> None:
        self.ok("init", "demo")
        other = self.worktree("b")
        result = self.run_lead("init", "second", cwd=other)
        self.assertEqual(result.returncode, 1, result.stdout)
        for text in ("another worktree holds a lead state", f"- {self.folder()}: slug demo, owner {OWNER}",
                     f"{CONTINUE} Only after the user confirms a second lead state, run init second --also."):
            with self.subTest(text=text):
                self.assertIn(text, words(result.stderr))
        self.assertFalse((other / ".scratch").exists())
        self.assertIn("Lead state created: ", self.ok("init", "second", "--also", cwd=other))
        self.assertIn("Lead state: second, ", self.ok("start", cwd=other))
        self.assertIn("Lead state: demo, ", self.ok("start"))

    def test_a_command_in_another_worktree_names_its_lead_state_not_init(self) -> None:
        self.ok("init", "demo")
        other = self.worktree("b")
        for args in (("takeover",), ("show",), ("outcome", "Ship it.")):
            with self.subTest(args=args):
                result = self.run_lead(*args, cwd=other, thread=OTHER)
                self.assertEqual(result.returncode, 1, result.stdout)
                stderr = words(result.stderr)
                self.assertIn("no lead state in this working tree. Lead states in other worktrees of this "
                              f"repository: - {self.folder()}: slug demo, owner {OWNER}", stderr)
                self.assertIn(CONTINUE, stderr)
                self.assertNotIn("run init", stderr)
        self.assertFalse((other / ".scratch").exists())
        self.assertEqual(json.loads(self.state_text())["owner"], OWNER)

    def test_init_and_takeover_need_the_t3_thread_id(self) -> None:
        for thread in (None, "", " "):
            with self.subTest(thread=thread):
                result = self.run_lead("init", "demo", thread=thread)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn("init needs T3CODE_THREAD_ID", result.stderr)
                self.assertFalse((self.repo / ".scratch").exists())
        self.ok("init", "demo")
        self.assertEqual(json.loads(self.state_text())["owner"], OWNER)
        for thread in (None, ""):
            with self.subTest(thread=thread):
                self.refused("takeover", thread=thread, reason="takeover needs T3CODE_THREAD_ID")

    def test_only_the_owner_changes_the_state_until_a_takeover(self) -> None:
        self.ok("init", "demo")
        self.ok("task", "add", "a", "Task a")
        for args in CHANGE_COMMANDS:
            with self.subTest(args=args):
                stderr = self.refused(*args, thread=OTHER, reason=f"its owner is thread {OWNER}")
                self.assertIn("To move the lead to this thread, run takeover.", stderr)
                self.assertIn(RECOVERY, stderr)
        self.assertIn("Lead state: demo", self.ok("show", thread=OTHER))
        self.ok("waiting", thread=OTHER)
        self.assertIn(f"Lead state taken over: owner {OTHER}, was {OWNER}.",
                      self.ok("takeover", thread=OTHER))
        self.assertEqual(json.loads(self.state_text())["owner"], OTHER)
        event = self.events()[-1]
        self.assertEqual({key: event[key] for key in ("command", "old_owner", "owner")},
                         {"command": "takeover", "old_owner": OWNER, "owner": OTHER})
        for args in CHANGE_COMMANDS:
            with self.subTest(args=args, after="takeover"):
                self.refused(*args, reason=f"its owner is thread {OTHER}")
        self.ok("outcome", "Ship it.", thread=OTHER)

    def test_the_first_start_after_a_takeover_names_the_work_to_check(self) -> None:
        self.ok("init", "demo")
        self.assertIn(f"Owner: {OWNER}\n", self.ok("start"))
        self.assertNotIn(TAKEOVER_LINE, words(self.ok("start")))
        before = (self.state_text(), self.events())
        self.assertIn("This thread already owns the lead state; nothing changed.", self.ok("takeover"))
        self.assertEqual((self.state_text(), self.events()), before)
        self.ok("takeover", thread=OTHER)
        # The earlier owner reads the state, but only the owner sees the due line, which it can act on.
        view = words(self.ok("start"))
        self.assertIn(f"Owner: {OTHER} This thread is not the owner: it can read the lead state but not "
                      "change it. To move the lead to this thread, run takeover.", view)
        self.assertNotIn(TAKEOVER_LINE, view)
        self.assertEqual(self.events()[-1]["command"], "takeover")
        self.assertIn(f"- {TAKEOVER_LINE}", words(self.ok("start", thread=OTHER)))
        event = self.events()[-1]
        self.assertEqual({key: event[key] for key in ("command", "shown")},
                         {"command": "start", "shown": "takeover due line"})
        view = self.ok("start", thread=OTHER)
        self.assertNotIn(TAKEOVER_LINE, words(view))
        self.assertNotIn("is not the owner", view)
        self.assertEqual(self.events()[-1], event)

    def test_a_state_without_an_owner_needs_one_takeover(self) -> None:
        self.ok("init", "demo")
        state = json.loads(self.state_text())
        del state["owner"]
        (self.folder() / "state.json").write_text(json.dumps(state), encoding="utf-8")
        self.assertIn("Owner: none", self.ok("start"))
        stderr = self.refused("outcome", "Ship it.", reason="it has no owner")
        self.assertIn("run takeover", stderr)
        self.assertIn(f"Lead state taken over: owner {OWNER}, was none.", self.ok("takeover"))
        self.assertIsNone(self.events()[-1]["old_owner"])
        self.ok("outcome", "Ship it.")

    def test_init_creates_one_folder_that_git_ignores(self) -> None:
        self.ok("init", "demo")
        folder = self.folder()
        today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d")
        self.assertEqual(folder.name, f"{today}-lead-demo")
        self.assertEqual((folder / ".gitignore").read_text(encoding="utf-8"), "*\n")
        status = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"],
                                cwd=self.repo, env=self.env, capture_output=True, text=True, check=True)
        self.assertEqual(status.stdout, "")
        result = self.run_lead("init", "other", cwd=self.repo / "sub")
        self.assertEqual(result.returncode, 1)
        self.assertIn("a lead state already exists here", result.stderr)
        self.assertIn("Lead state: demo", self.ok("show"))

    def test_a_command_from_a_subfolder_finds_the_lead_state(self) -> None:
        self.ok("init", "demo")
        result = self.run_lead("outcome", "Ship it.", cwd=self.repo / "sub")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Outcome: Ship it.", self.ok("show"))

    def test_a_command_without_a_lead_state_is_refused(self) -> None:
        result = self.run_lead("task", "add", "a", "Title")
        self.assertEqual(result.returncode, 1)
        self.assertIn("run init <slug> first", result.stderr)

    def test_a_task_runs_its_life_cycle_with_utc_times(self) -> None:
        self.ok("init", "demo")
        self.ok("task", "add", "fix-503", "Fix the lean-tests history check", "--issue", "503")
        self.ok("task", "start", "fix-503", WORKER.format(1), "--branch", "fix-503")
        self.ok("task", "pr", "fix-503", "540")
        self.ok("task", "pr", "fix-503", "541")
        self.ok("task", "merged", "fix-503", "540", "abcdef1")
        self.assertEqual(self.task("fix-503")["state"], "pr-open")
        self.ok("task", "merged", "fix-503", "541", "abcdef2")
        self.assertEqual(self.task("fix-503")["state"], "merged")
        self.ok("task", "verified", "fix-503", "--decisions", "0")
        self.ok("task", "add", "closeout-1", "Close out batch 1", "--kind", "closeout")
        self.ok("task", "start", "closeout-1", WORKER.format(2))
        output = self.ok("task", "verified", "closeout-1", "--decisions", "0")
        self.assertIn("Batch 1 is closed out: fix-503.", output)
        self.assertEqual(self.task("fix-503")["state"], "closed-out")
        self.ok("task", "settled", "fix-503")
        self.ok("task", "settled", "closeout-1")
        events = self.events()
        self.assertEqual([event["command"] for event in events][:3], ["init", "task add", "task start"])
        self.assertEqual([event.get("to") for event in events if event.get("task") == "fix-503"],
                         ["planned", "running", "pr-open", "pr-open", "pr-open", "merged", "verified",
                          "settled"])
        now = datetime.datetime.now(datetime.timezone.utc)
        for event in events:
            self.assertRegex(event["time"], UTC)
            stamped = datetime.datetime.strptime(event["time"], "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=datetime.timezone.utc)
            self.assertLess(abs((now - stamped).total_seconds()), 120)

    def test_illegal_transitions_are_refused(self) -> None:
        self.ok("init", "demo")
        self.ok("task", "add", "a", "Task a")
        self.refused("task", "pr", "a", "5", reason="a is planned; task pr needs running or pr-open")
        self.refused("task", "verified", "a", "--decisions", "0", reason="a is planned")
        self.refused("task", "resume", "a", reason="task resume needs paused")
        self.refused("task", "start", "a", "two words", reason="the worker link must be one word")
        self.ok("task", "start", "a", WORKER.format(1))
        self.refused("task", "start", "a", WORKER.format(1), reason="a is running")
        self.ok("task", "pr", "a", "5")
        self.refused("task", "pr", "a", "5", reason="not a new positive PR number")
        self.refused("task", "verified", "a", "--decisions", "0",
                     reason="a has an open PR; verify it after task merged")
        self.refused("task", "merged", "a", "6", "abcdef1", reason="not an open PR of a")
        self.refused("task", "merged", "a", "5", "XYZ", reason="a commit is 7 to 40")
        self.refused("task", "settled", "a", reason="settle needs closed-out, cancelled, or verified")
        self.ok("task", "merged", "a", "5", "abcdef1")
        self.ok("task", "verified", "a", "--decisions", "0")
        self.refused("task", "cancel", "a", reason="a is verified")
        self.refused("task", "verified", "missing", "--decisions", "0", reason="no task named missing")

    def test_settle_waits_for_the_close_out_of_a_batch_with_a_merged_pr(self) -> None:
        self.ok("init", "demo")
        self.merged_task("a", "5")
        self.refused("task", "settled", "a", reason="batch 1 has a merged PR; settle a after the batch's "
                                                    "close-out task is verified")
        self.ok("task", "add", "close-1", "Close out batch 1", "--kind", "closeout")
        self.ok("task", "start", "close-1", WORKER.format(9))
        self.refused("task", "settled", "a", reason="close-out task is verified")
        self.ok("task", "verified", "close-1", "--decisions", "0")
        self.ok("task", "settled", "a")

    def test_a_batch_with_no_pr_settles_when_every_task_is_verified(self) -> None:
        self.ok("init", "demo")
        self.ok("task", "add", "research", "Research the cache")
        self.ok("task", "add", "audit", "Audit the hooks")
        self.ok("task", "start", "research", WORKER.format(1))
        self.ok("task", "verified", "research", "--decisions", "0")
        self.refused("task", "settled", "research", reason="batch 1 still has open tasks")
        self.ok("task", "start", "audit", WORKER.format(2))
        self.ok("task", "verified", "audit", "--decisions", "0")
        self.ok("task", "settled", "research")

    def test_after_blocks_the_start_until_the_task_is_verified(self) -> None:
        self.ok("init", "demo")
        self.ok("task", "add", "research", "Research the cache")
        self.ok("task", "add", "impl", "Build the cache", "--after", "research")
        self.refused("task", "start", "impl", WORKER.format(2), reason="impl waits for research to be "
                                                                      "verified")
        self.ok("task", "start", "research", WORKER.format(1))
        self.refused("task", "start", "impl", WORKER.format(2), reason="waits for research")
        self.ok("task", "verified", "research", "--decisions", "0")
        self.ok("task", "start", "impl", WORKER.format(2))

    def test_a_task_is_ready_when_the_task_that_it_waits_for_is_verified(self) -> None:
        self.ok("init", "demo")
        self.ok("task", "add", "a", "Task a")
        self.ok("task", "add", "b", "Task b")
        self.ok("task", "add", "c", "Task c", "--after", "a")
        self.ok("task", "add", "d", "Task d", "--after", "c")
        view = self.ok("show")
        for name in ("a", "b"):
            self.assertIn(f"- {name} is ready to start: run t3_project_lead.py dispatch for it now.", view)
        self.assertNotIn("c is ready", view)
        self.ok("task", "start", "a", WORKER.format("a"))
        self.ok("task", "start", "b", WORKER.format("b"))
        self.assertNotIn("is ready to start", self.ok("show"))
        self.ok("task", "pr", "a", "5")
        self.ok("task", "merged", "a", "5", "abcdef1")
        # b of the same batch still runs: c is ready now, and d still waits for c.
        self.assertEqual(self.ok("task", "verified", "a", "--decisions", "0").strip(), "a is verified. c is ready to "
                         "start: run t3_project_lead.py dispatch for it now.")
        view = self.ok("show")
        self.assertIn("- c is ready to start: run t3_project_lead.py dispatch for it now.", view)
        self.assertNotIn("d is ready", view)
        self.assertEqual(self.task("b")["state"], "running")
        self.ok("task", "start", "c", WORKER.format("c"))
        self.assertNotIn("is ready to start", self.ok("show"))

    def test_a_ready_close_out_task_names_the_closeout_step(self) -> None:
        self.ok("init", "demo")
        self.ok("task", "add", "a", "Task a")
        self.ok("task", "add", "close-1", "Close out batch 1", "--kind", "closeout")
        self.ok("task", "start", "a", WORKER.format("a"))
        self.ok("task", "pr", "a", "5")
        self.ok("task", "merged", "a", "5", "abcdef1")
        line = "close-1 is ready to start: run t3_project_lead.py closeout for it now."
        self.assertEqual(self.ok("task", "verified", "a", "--decisions", "0").strip(), f"a is verified. {line}")
        view = self.ok("show")
        self.assertIn(f"- {line}", view)
        self.assertNotIn("dispatch for it now", view)

    def test_a_close_out_starts_only_for_a_verified_batch_with_a_merged_pr(self) -> None:
        self.ok("init", "demo")
        self.ok("task", "add", "close-1", "Close out batch 1", "--kind", "closeout")
        self.refused("task", "add", "close-again", "Second close-out", "--kind", "closeout",
                     reason="batch 1 already has a close-out task")
        self.ok("task", "add", "a", "Task a")
        self.ok("task", "start", "a", WORKER.format(1))
        self.refused("task", "start", "close-1", WORKER.format(9), reason="batch 1 still has tasks")
        self.ok("task", "verified", "a", "--decisions", "0")
        self.refused("task", "start", "close-1", WORKER.format(9), reason="batch 1 has no merged PR")
        self.merged_task("b", "7")
        self.ok("task", "start", "close-1", WORKER.format(9))
        self.ok("task", "verified", "close-1", "--decisions", "0")
        self.refused("task", "add", "late", "Late task", "--batch", "1",
                     reason="the close-out of batch 1 has started; use --batch 2")
        self.refused("task", "add", "far", "Far task", "--batch", "3", reason="the batch must be from 1 to 2")
        self.ok("task", "add", "next", "Next task", "--batch", "2")

    def test_a_task_opens_its_next_pr_after_one_merges(self) -> None:
        self.ok("init", "demo")
        self.ok("task", "add", "tickets", "Two matt-automode tickets")
        self.ok("task", "start", "tickets", WORKER.format(1))
        self.ok("task", "pr", "tickets", "11")
        self.ok("task", "merged", "tickets", "11", "abcdef1")
        self.assertEqual(self.task("tickets")["state"], "merged")
        self.ok("task", "pr", "tickets", "12")
        self.assertEqual(self.task("tickets")["state"], "pr-open")
        self.refused("task", "verified", "tickets", "--decisions", "0", reason="tickets has an open PR")
        self.ok("task", "merged", "tickets", "12", "abcdef2")
        self.ok("task", "verified", "tickets", "--decisions", "0")

    def test_a_cancelled_task_does_not_release_a_task_after_it(self) -> None:
        self.ok("init", "demo")
        self.ok("task", "add", "research", "Research the cache")
        self.ok("task", "add", "impl", "Build the cache", "--after", "research")
        self.ok("task", "cancel", "research")
        self.ok("task", "settled", "research")
        self.refused("task", "start", "impl", WORKER.format(2), reason="impl waits for research")
        self.assertNotIn("impl is ready", self.ok("show"))

    def test_no_task_joins_a_batch_whose_close_out_has_started(self) -> None:
        self.ok("init", "demo")
        self.merged_task("w", "5")
        self.ok("task", "add", "co", "Close out batch 1", "--kind", "closeout")
        self.ok("task", "start", "co", WORKER.format(9))
        self.refused("task", "add", "late", "Late task", "--batch", "1",
                     reason="the close-out of batch 1 has started; use --batch 2")
        self.assertIn("Task late added to batch 2.", self.ok("task", "add", "late", "Late task"))
        self.ok("task", "verified", "co", "--decisions", "0")
        self.ok("task", "settled", "w")
        self.ok("task", "settled", "co")

    def test_a_cancelled_close_out_lets_the_batch_add_another(self) -> None:
        self.ok("init", "demo")
        self.merged_task("w", "5")
        self.ok("task", "add", "co", "Close out batch 1", "--kind", "closeout")
        self.ok("task", "cancel", "co")
        self.ok("task", "settled", "co")
        self.ok("task", "add", "co-2", "Close out batch 1 again", "--kind", "closeout", "--batch", "1")
        self.ok("task", "start", "co-2", WORKER.format(9))
        self.ok("task", "verified", "co-2", "--decisions", "0")
        self.assertEqual(self.task("w")["state"], "closed-out")

    def test_names_and_text_are_checked(self) -> None:
        self.ok("init", "demo")
        self.refused("task", "add", "Fix", "Title", reason="a task name has lowercase letters")
        self.refused("task", "add", "a" * 25, "Title", reason="at most 24 characters")
        self.refused("task", "add", "a", "x" * 201, reason="the title has 201 characters; the limit is 200")
        self.refused("decision", "add", "x" * 201, reason="the limit is 200")
        self.refused("wait", "x" * 201, reason="the limit is 200")
        self.refused("outcome", "x" * 201, reason="the limit is 200")
        self.ok("task", "add", "a", "x" * 200)
        self.refused("task", "add", "a", "Title", reason="a task named a already exists")
        self.refused("task", "add", "c", "Check", "--kind", "check", reason="a check task needs --of")
        self.refused("task", "add", "c", "Check", "--of", "a", reason="only a check task takes --of")
        self.refused("task", "add", "c", "Check", "--after", "missing", reason="no task named missing")

    def test_waiting_items_keep_their_numbers_and_point_to_the_worker(self) -> None:
        self.ok("init", "demo")
        self.ok("task", "add", "grill", "Design the cache")
        self.ok("task", "start", "grill", WORKER.format(1))
        self.assertIn("Item 1 added: [grill] 5 decisions. " + WORKER.format(1),
                      self.ok("wait", "--task", "grill", "--decisions", "5"))
        self.ok("wait", "Triage #503", "--recommend", "ready-for-agent")
        self.ok("done", "1")
        self.refused("done", "1", reason="no waiting item 1")
        self.ok("wait", "Delete the backup files?", "--link", "https://example.com/x")
        # Each item is a bullet with its number as text: a renderer renumbers a numbered list (#534).
        waiting = ["Waiting on you (2):",
                   "- 2: Triage #503. Lead recommends: ready-for-agent.",
                   "- 3: Delete the backup files? https://example.com/x"]
        self.assertEqual(self.ok("waiting").splitlines(), waiting)
        for command in ("start", "show", "report"):
            with self.subTest(command=command):
                self.assertTrue(self.ok(command).endswith("\n\n" + "\n".join(waiting) + "\n"))
        self.refused("wait", "--decisions", "2", reason="give the item's text, or --task")

    def test_a_view_adds_a_period_only_to_text_without_end_punctuation(self) -> None:
        self.ok("init", "demo")
        for name, title in (("a", "Fix the cache"), ("b", "Fix the cache."), ("c", "Is the cache fast?"),
                            ("d", "Ship it!")):
            self.ok("task", "add", name, title)
        self.ok("wait", "Approve the release", "--recommend", "Ship it")
        self.ok("wait", "Delete the backup files?", "--recommend", "Keep them!")
        self.ok("wait", "Rotate the key.", "--recommend", "Today.")
        view = self.ok("show")
        for line in ("- a (batch 1) planned: Fix the cache.", "- b (batch 1) planned: Fix the cache.",
                     "- c (batch 1) planned: Is the cache fast?", "- d (batch 1) planned: Ship it!",
                     "- 1: Approve the release. Lead recommends: Ship it.",
                     "- 2: Delete the backup files? Lead recommends: Keep them!",
                     "- 3: Rotate the key. Lead recommends: Today."):
            with self.subTest(line=line):
                self.assertIn(line + "\n", view)

    def test_a_worker_item_holds_no_detail_of_the_decisions(self) -> None:
        self.ok("init", "demo")
        self.ok("task", "add", "grill", "Design the cache")
        self.refused("wait", "--task", "grill", "--decisions", "2",
                     reason="grill has no worker; add the item without --task")
        self.ok("task", "start", "grill", WORKER.format(1))
        for extra in (["Choose JSON or SQLite"], ["--recommend", "SQLite"], ["--link", "https://x"]):
            with self.subTest(extra=extra):
                self.refused("wait", "--task", "grill", "--decisions", "2", *extra,
                             reason="a worker item takes only --decisions")

    def test_task_verified_records_the_decisions_of_the_report(self) -> None:
        # The script cannot read a report, so the lead gives the count of its numbered decisions (#567).
        self.ok("init", "demo")
        self.ok("outcome", "Report the status.")
        for name in ("survey", "audit"):
            self.ok("task", "add", name, f"Title of {name}")
            self.ok("task", "start", name, WORKER.format(name))
        self.refused("task", "verified", "survey", reason="task verified needs --decisions N: the number of "
                     "decisions that its report numbers for the user, or 0")
        self.refused("task", "verified", "survey", "--decisions", "-1", reason="the number of decisions is "
                     "0 or more")
        self.refused("task", "verified", "survey", "audit", "--decisions", "2",
                     reason="a count above 0 takes one task name")
        self.assertEqual(self.ok("task", "verified", "survey", "--decisions", "2").strip(),
                         "survey is verified. Item 1 added: [survey] 2 decisions. " + WORKER.format("survey"))
        self.assertEqual(self.ok("task", "verified", "audit", "--decisions", "0").strip(), "audit is verified.")
        self.assertEqual([(event["task"], event["decisions"]) for event in self.events()
                          if event["command"] == "task verified"], [("survey", 2), ("audit", 0)])
        self.ok("task", "settled", "survey", "audit")
        view = self.ok("show")
        # Only the user ends the item: no due line offers done, and finish waits for it.
        self.assertNotIn("Run done 1", view)
        self.assertTrue(json.loads(self.state_text())["items"][0]["from_report"])
        self.assertNotIn("run t3_project_lead.py finish", view)
        self.assertIn("- 1: [survey] 2 decisions. " + WORKER.format("survey"), view)
        self.refused("finish", reason="items that wait: 1")
        self.ok("done", "1")
        self.assertIn(FINISH_LINE, self.ok("show"))

    def test_the_due_line_of_a_check_names_the_count_of_decisions(self) -> None:
        self.ok("init", "demo")
        self.ok("task", "add", "a", "Task a")
        self.ok("task", "start", "a", WORKER.format("a"))
        self.ok("task", "add", "chk", "Check a", "--kind", "check", "--of", "a")
        self.ok("task", "start", "chk", WORKER.format("chk"))
        self.ok("task", "verified", "chk", "--decisions", "0")
        self.assertIn("- Check chk is verified: run task verified a --decisions <N> when its verdict passes.",
                      self.ok("show"))

    def test_wait_records_the_decisions_of_a_finished_worker(self) -> None:
        # A lead that records a finished worker's decisions late still points to its thread (#567).
        self.ok("init", "demo")
        self.ok("task", "add", "a", "Task a")
        self.ok("task", "add", "b", "Task b")
        self.ok("task", "start", "a", WORKER.format("a"))
        self.ok("task", "start", "b", WORKER.format("b"))
        self.ok("task", "verified", "a", "b", "--decisions", "0")
        self.ok("task", "settled", "a")
        self.assertIn("Item 1 added: [a] 2 decisions. " + WORKER.format("a"),
                      self.ok("wait", "--task", "a", "--decisions", "2"))
        self.ok("wait", "--task", "b", "--decisions", "1")
        view = self.ok("show")
        self.assertNotIn("Run done", view)
        self.assertIn("- 2: [b] 1 decision. " + WORKER.format("b"), view)
        self.ok("task", "add", "c", "Task c")
        self.refused("wait", "--task", "c", "--decisions", "1", reason="c has no worker; add the item "
                     "without --task")

    def test_the_view_hides_settled_tasks_and_counts_closed_out_tasks(self) -> None:
        self.ok("init", "demo")
        self.merged_task("a", "5")
        self.merged_task("b", "6")
        self.ok("task", "add", "close-1", "Close out batch 1", "--kind", "closeout")
        self.ok("task", "start", "close-1", WORKER.format(9))
        self.ok("task", "verified", "close-1", "--decisions", "0")
        self.ok("task", "settled", "a")
        self.ok("task", "add", "c", "Task c", "--batch", "2")
        self.ok("task", "start", "c", WORKER.format(3))
        view = self.ok("show")
        self.assertNotIn("- a (", view)
        self.assertNotIn("- b (", view)
        self.assertIn("Closed out, worker not settled: 1 task.", view)
        self.assertRegex(view, r"- c \(batch 2\) running, 0 min: Task c\. Worker: t3-thread://")
        self.assertRegex(view, r"Now: " + UTC.pattern)

    def test_due_lines_name_the_next_mechanical_steps(self) -> None:
        self.ok("init", "demo")
        # A lead finishes only after the user named the work (#545).
        self.ok("outcome", "Ship it.")
        self.ok("task", "add", "a", "Title of a")
        self.ok("task", "start", "a", WORKER.format("a"))
        # The worker waits on the user while it runs, as the answer step records.
        self.ok("wait", "--task", "a", "--decisions", "1")
        self.ok("task", "pr", "a", "5")
        self.ok("task", "merged", "a", "5", "abcdef1")
        self.ok("task", "verified", "a", "--decisions", "0")
        view = self.ok("show")
        self.assertIn("- Batch 1: every task is verified; merged PRs #5. Run t3_project_lead.py "
                      "closeout.", view)
        self.assertIn("- Item 1: task a is verified. Run done 1, or keep it.", view)
        closeout = self.ok("closeout")
        self.assertIn("Workers: " + WORKER.format("a"), closeout)
        self.assertIn("Merged PRs in merge order: #5", closeout)
        self.assertIn(f"History: {self.folder() / 'events.jsonl'}", closeout)
        self.ok("task", "add", "close-1", "Close out batch 1", "--kind", "closeout")
        self.ok("task", "start", "close-1", WORKER.format(9))
        self.ok("task", "verified", "close-1", "--decisions", "0")
        view = self.ok("show")
        self.assertIn("- Settle the worker of a, then run task settled a: " + WORKER.format("a"), view)
        self.assertIn("- Settle the worker of close-1, then run task settled close-1:", view)
        self.ok("task", "settled", "a")
        self.ok("task", "settled", "close-1")
        self.ok("done", "1")
        self.assertIn(FINISH_LINE,
                      self.ok("show"))

    def test_a_state_without_an_outcome_names_the_discover_step(self) -> None:
        # A wake after the discovery worker reports leads to the discover step (#545).
        due = "- No outcome yet: run t3_project_lead.py discover."
        # After the report, only the user starts the work: no second discovery.
        done = ("- No outcome yet, and discover is verified: start no second discovery. Wait until the user "
                "names the work.")
        self.ok("init", "demo")
        self.assertIn(due, self.ok("start"))
        self.ok("task", "add", "discover", "Discover open work")
        self.ok("task", "start", "discover", WORKER.format(1))
        self.assertIn(due, self.ok("show"))
        self.ok("task", "verified", "discover", "--decisions", "0")
        view = self.ok("start")
        self.assertIn(done, view)
        self.assertNotIn(due, view)
        self.ok("task", "settled", "discover")
        # A settled discovery task does not finish a lead whose user has not named the work.
        view = self.ok("start")
        self.assertIn(done, view)
        self.assertNotIn("run t3_project_lead.py finish", view)
        self.ok("outcome", "Fix the audit themes.")
        view = self.ok("start")
        self.assertNotIn("No outcome yet", view)
        self.assertIn(FINISH_LINE, view)

    def test_merge_order_follows_the_merge_times(self) -> None:
        self.ok("init", "demo")
        self.ok("task", "add", "a", "Task a")
        self.ok("task", "start", "a", WORKER.format(1))
        self.ok("task", "pr", "a", "9")
        self.ok("task", "pr", "a", "3")
        self.ok("task", "merged", "a", "9", "abcdef1")
        state = json.loads(self.state_text())
        state["tasks"][0]["prs"][0]["merged"] = "2026-01-01T00:00:00Z"
        (self.folder() / "state.json").write_text(json.dumps(state), encoding="utf-8")
        self.ok("task", "merged", "a", "3", "abcdef2")
        self.ok("task", "verified", "a", "--decisions", "0")
        self.assertIn("Merged PRs in merge order: #9, #3", self.ok("closeout"))

    def test_a_replaced_worker_is_named_once_to_settle(self) -> None:
        self.ok("init", "demo")
        self.ok("task", "add", "a", "Task a")
        self.ok("task", "start", "a", WORKER.format(1))
        output = self.ok("task", "worker", "a", WORKER.format(2))
        self.assertIn("Settle the replaced worker now: " + WORKER.format(1), output)
        self.assertEqual(self.task("a")["worker"], WORKER.format(2))
        self.assertNotIn(WORKER.format(1), self.ok("show"))

    def test_pause_resume_and_cancel(self) -> None:
        self.ok("init", "demo")
        self.ok("task", "add", "a", "Task a")
        self.ok("task", "pause", "a")
        paused = "- Paused: a. Run task resume <name>... to plan them again, or task cancel <name>."
        self.assertIn(paused, self.ok("start"))
        view = self.ok("show")
        self.assertIn("- a (batch 1) paused: Task a.", view)
        self.assertIn(paused, view)
        self.refused("task", "start", "a", WORKER.format(1), reason="a is paused")
        self.ok("task", "resume", "a")
        self.assertNotIn(paused, self.ok("show"))
        self.assertIn("It has no worker: run task settled a.", self.ok("task", "cancel", "a"))
        self.assertEqual(self.task("a")["state"], "cancelled")
        self.assertIn("- a has no worker: run task settled a.", self.ok("show"))
        self.ok("task", "settled", "a")
        self.ok("task", "add", "b", "Task b")
        self.ok("task", "start", "b", WORKER.format(2))
        self.ok("task", "cancel", "b")
        self.assertIn("- Settle the worker of b, then run task settled b:", self.ok("show"))
        self.ok("task", "settled", "b")

    def test_start_prints_a_compact_view_that_does_not_grow(self) -> None:
        # The start view keeps the running and pr-open tasks, the due lines, and the waiting list, and
        # counts the other tasks and the decisions on one line (#555).
        self.ok("init", "demo")
        self.ok("outcome", "Ship it.")
        self.ok("task", "add", "run", "Running task")
        self.ok("task", "start", "run", WORKER.format("run"))
        self.ok("task", "add", "pr", "Task with a PR")
        self.ok("task", "start", "pr", WORKER.format("pr"))
        self.ok("task", "pr", "pr", "4")
        self.ok("task", "add", "next", "Ready task", "--batch", "1")
        self.ok("wait", "Approve the release?")
        before = self.ok("start").splitlines()
        for index in range(10):
            self.merged_task(f"v{index}", str(10 + index))
            self.ok("decision", "add", f"Decision {index}.")
        after = self.ok("start").splitlines()
        self.assertEqual(len(after), len(before))
        view = "\n".join(after)
        self.assertRegex(view, r"\n- run \(batch 1\) running, \d+ min: Running task\. Worker: ")
        self.assertRegex(view, r"\n- pr \(batch 1\) pr-open, \d+ min: Task with a PR\. PRs: #4 open\. ")
        self.assertIn("\nOther tasks: 1 planned, 10 verified. Decisions: 10. Run show to list them.\n", view)
        self.assertIn("\n- next is ready to start: run t3_project_lead.py dispatch for it now.\n", view)
        self.assertTrue(view.endswith("\n\nWaiting on you (1):\n- 1: Approve the release?"))
        # A task line, not the bare name: the view also prints the random temporary path (#591).
        self.assertNotRegex(view, r"(?m)^- v\d \(")
        self.assertNotIn("Decision 0", view)
        # show still lists every task and decision.
        full = self.ok("show")
        for index in range(10):
            with self.subTest(index=index):
                self.assertIn(f"- v{index} (batch 1) verified: Title of v{index}.", full)
                self.assertIn(f"- D{index + 1} Decision {index}.", full)
        self.assertIn("- next (batch 1) planned: Ready task.", full)

    def test_several_arguments_change_under_one_lock(self) -> None:
        # done and the task state commands take one or more arguments, with one event each (#555).
        self.ok("init", "demo")
        for name in ("a", "b", "c"):
            self.ok("task", "add", name, f"Task {name}")
        self.ok("wait", "First?")
        self.ok("wait", "Second?")
        self.ok("wait", "Third?")
        self.assertEqual(self.ok("done", "1", "3").strip(), "Item 1 is done. Item 3 is done.")
        self.assertEqual([item["number"] for item in json.loads(self.state_text())["items"]], [2])
        self.assertEqual(self.ok("task", "pause", "a", "b").strip(), "a is paused. b is paused.")
        self.ok("task", "resume", "a", "b")
        self.ok("task", "start", "a", WORKER.format("a"))
        self.ok("task", "start", "b", WORKER.format("b"))
        self.assertEqual(self.ok("task", "verified", "a", "b", "--decisions", "0").strip(),
                         "a is verified. b is verified. c is "
                         "ready to start: run t3_project_lead.py dispatch for it now.")
        self.ok("task", "start", "c", WORKER.format("c"))
        self.ok("task", "verified", "c", "--decisions", "0")
        self.ok("task", "settled", "a", "b")
        self.assertEqual([self.task(name)["state"] for name in ("a", "b", "c")], ["settled", "settled", "verified"])
        changes = [(event["command"], event.get("task", event.get("item"))) for event in self.events()
                   if event["command"] in ("done", "task pause", "task resume", "task verified", "task settled")]
        self.assertEqual(changes, [("done", 1), ("done", 3), ("task pause", "a"), ("task pause", "b"),
                                   ("task resume", "a"), ("task resume", "b"), ("task verified", "a"),
                                   ("task verified", "b"), ("task verified", "c"), ("task settled", "a"),
                                   ("task settled", "b")])

    def test_a_refused_argument_of_several_changes_nothing(self) -> None:
        self.ok("init", "demo")
        self.ok("task", "add", "a", "Task a")
        self.ok("task", "add", "b", "Task b")
        self.ok("task", "start", "b", WORKER.format("b"))
        self.ok("wait", "First?")
        self.refused("done", "1", "9", reason="no waiting item 9")
        self.refused("task", "pause", "a", "missing", reason="no task named missing")
        self.refused("task", "pause", "a", "b", reason="b is running; task pause needs planned")
        self.refused("task", "verified", "b", "a", "--decisions", "0", reason="a is planned")
        self.refused("task", "settled", "b", "a", reason="b is running")
        self.assertEqual(self.task("a")["state"], "planned")

    def test_task_verified_names_each_ready_task_once(self) -> None:
        self.ok("init", "demo")
        self.ok("task", "add", "a", "Task a")
        self.ok("task", "add", "b", "Task b")
        self.ok("task", "add", "c", "Task c", "--after", "a", "--after", "b")
        self.ok("task", "start", "a", WORKER.format("a"))
        self.ok("task", "start", "b", WORKER.format("b"))
        self.assertEqual(self.ok("task", "verified", "a", "b", "--decisions", "0").strip(),
                         "a is verified. b is verified. c is "
                         "ready to start: run t3_project_lead.py dispatch for it now.")

    def test_a_worker_records_its_worktree(self) -> None:
        # The close-out reads the sessions of each worktree, also of a replaced worker (#556).
        self.ok("init", "demo")
        self.ok("task", "add", "a", "Task a")
        self.assertEqual(self.task("a")["worktrees"], [])
        for path in ("relative/path", "/two\nlines", "/" + "x" * 600):
            with self.subTest(path=path):
                self.refused("task", "start", "a", WORKER.format(1), "--worktree", path,
                             reason="the worktree must be an absolute path of at most 600 characters on one line")
        self.ok("task", "start", "a", WORKER.format(1), "--worktree", "/wt/a1")
        self.assertEqual(self.events()[-1]["worktree"], "/wt/a1")
        self.ok("task", "worker", "a", WORKER.format(2))
        self.ok("task", "worker", "a", WORKER.format(3), "--worktree", "/wt/a3")
        self.refused("task", "worker", "a", WORKER.format(4), "--worktree", "wt", reason="an absolute path")
        self.assertEqual(self.task("a")["worktrees"], ["/wt/a1", "/wt/a3"])
        self.assertEqual(self.events()[-1]["worktree"], "/wt/a3")

    def test_a_work_task_joins_a_new_batch_after_a_merge(self) -> None:
        # A batch stops growing when its first PR merges (#560).
        self.ok("init", "demo")
        self.ok("task", "add", "a", "Task a")
        self.ok("task", "start", "a", WORKER.format("a"))
        self.ok("task", "pr", "a", "5")
        self.assertIn("Task b added to batch 1.", self.ok("task", "add", "b", "Task b"))
        self.ok("task", "merged", "a", "5", "abcdef1")
        # Check and close-out tasks keep the highest batch.
        self.assertIn("Task k added to batch 1.", self.ok("task", "add", "k", "Check a", "--kind", "check",
                                                         "--of", "a"))
        # --batch with the highest batch, which has a merged PR, still adds to it.
        self.assertIn("Task d added to batch 1.", self.ok("task", "add", "d", "Task d", "--batch", "1"))
        self.assertIn("Task c added to batch 2.", self.ok("task", "add", "c", "Task c"))
        self.assertEqual(self.task("c")["batch"], 2)
        # Batch 2 has no merged PR, so the next work task joins it.
        self.assertIn("Task e added to batch 2.", self.ok("task", "add", "e", "Task e"))

    def test_decisions_are_added_and_dropped_by_id(self) -> None:
        self.ok("init", "demo")
        self.assertIn("Decision D1 added.", self.ok("decision", "add", "Squash each merge."))
        self.ok("decision", "add", "Merge one PR at a time.")
        self.ok("decision", "drop", "D1")
        self.refused("decision", "drop", "D1", reason="no decision D1")
        self.assertIn("Decision D3 added.", self.ok("decision", "add", "Workers start from master."))
        view = self.ok("show")
        self.assertNotIn("D1 ", view)
        self.assertIn("- D2 Merge one PR at a time.", view)

    def test_finish_deletes_the_state_only_when_everything_is_settled(self) -> None:
        self.ok("init", "demo")
        self.ok("task", "add", "a", "Task a")
        self.ok("wait", "Approve the release?")
        self.refused("finish", reason="tasks not settled: a; items that wait: 1")
        self.ok("task", "cancel", "a")
        self.refused("finish", reason="tasks not settled: a")
        self.ok("task", "settled", "a")
        self.ok("done", "1")
        folder = self.folder()
        self.assertIn("Settle this thread.", self.ok("finish"))
        self.assertFalse(folder.exists())

    def test_each_change_appends_one_event(self) -> None:
        self.ok("init", "demo")
        self.ok("outcome", "Ship the cache.")
        self.ok("criteria", "Tests pass.")
        self.ok("task", "add", "a", "Task a")
        self.run_lead("task", "verified", "a", "--decisions", "0")
        self.ok("show")
        self.assertEqual([event["command"] for event in self.events()],
                         ["init", "outcome", "criteria", "task add"])


if __name__ == "__main__":
    unittest.main()
