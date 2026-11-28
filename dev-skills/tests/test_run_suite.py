"""Command-line checks for run_suite.py, the suite locks, pass records, and priority marker.

Each check builds a temporary Git repository and runs small python3 commands
through the script. The commands write their log outside the repository, so
the working tree stays clean. No check touches another repository.
"""

from __future__ import annotations

import contextlib
import fcntl
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_suite.py"
_spec = importlib.util.spec_from_file_location("run_suite", SCRIPT)
RUN_SUITE = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(RUN_SUITE)

# Log "start <tag>", wait until the release file exists, then log "end <tag>".
HOLD = """
import pathlib, sys, time
log, tag, release = sys.argv[1:]
with open(log, "a") as f: f.write(f"start {tag}\\n")
deadline = time.time() + 10
while not pathlib.Path(release).exists() and time.time() < deadline: time.sleep(0.02)
with open(log, "a") as f: f.write(f"end {tag}\\n")
"""

DEMO_TESTS = """
import unittest

class Demo(unittest.TestCase):
    def test_pass(self):
        pass

    def test_fail(self):
        self.assertEqual(1, 2)

    def test_error(self):
        raise RuntimeError("boom")
"""

ROOT_TESTS = """
import unittest

class Root(unittest.TestCase):
    def test_pass(self):
        pass
"""


class GitRepoTestCase(unittest.TestCase):
    """A temporary Git repository, and helpers that run the script in it."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = self.tmp / "repo"
        (self.repo / "sub").mkdir(parents=True)
        (self.repo / "sub" / "file.txt").write_text("one\n")
        self.log = self.tmp / "log.txt"
        self.release = self.tmp / "release"
        self.env = dict(os.environ, GIT_CONFIG_GLOBAL=str(self.tmp / "gitconfig"),
                        GIT_CONFIG_NOSYSTEM="1", GIT_CEILING_DIRECTORIES=str(self.tmp),
                        GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
                        GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")
        self.git("init", "-q")
        self.git("add", ".")
        self.git("commit", "-qm", "one")

    def git(self, *args: str) -> str:
        return subprocess.run(["git", *args], cwd=self.repo, env=self.env, check=True,
                              capture_output=True, text=True).stdout.strip()

    def hold(self, tag: str = "a") -> list[str]:
        return [sys.executable, "-c", HOLD, str(self.log), tag, str(self.release)]

    def run_suite(self, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd or self.repo,
                              env=self.env, capture_output=True, text=True, timeout=30)

    def start(self, *args: str, name: str, cwd: Path | None = None) -> subprocess.Popen:
        """Start the script in the background, with its output in files."""
        out = open(self.tmp / f"{name}.out", "w")
        err = open(self.tmp / f"{name}.err", "w")
        self.addCleanup(out.close)
        self.addCleanup(err.close)
        process = subprocess.Popen([sys.executable, str(SCRIPT), *args], cwd=cwd or self.repo,
                                   env=self.env, stdout=out, stderr=err)
        self.addCleanup(process.kill)
        return process

    def wait_for(self, path: Path, text: str) -> None:
        deadline = time.time() + 10
        while time.time() < deadline:
            if path.exists() and text in path.read_text():
                return
            time.sleep(0.02)
        self.fail(f"{path.name} has no {text!r}")

    def log_lines(self) -> list[str]:
        return self.log.read_text().splitlines() if self.log.exists() else []

    def use_fake_ps(self, body: str) -> None:
        """Put a fake ps that runs this shell body first on the PATH of the script."""
        folder = self.tmp / "bin"
        folder.mkdir(exist_ok=True)
        ps = folder / "ps"
        ps.write_text(f"#!/bin/sh\n{body}\n")
        ps.chmod(0o755)
        self.env = dict(self.env, PATH=f"{folder}{os.pathsep}{os.environ.get('PATH', '')}")

    def suite_lock_path(self, command: list[str], folder: str = ".") -> Path:
        """Return the lock file of a suite, as run_suite.py names it."""
        return RUN_SUITE.suite_lock_path(self.repo / ".git",
                                         {"command": command, "folder": folder})


@unittest.skipUnless(shutil.which("git"), "needs git")
class RunSuiteTests(GitRepoTestCase):
    def test_same_suite_waits_then_reuses_the_pass_and_another_folder_does_not_wait(self):
        # A holds its suite lock until the release file exists. B has A's
        # command and folder, so it waits. C has A's command in folder sub,
        # which is another suite, so it runs while A holds its lock.
        first = self.start("--", *self.hold("a"), name="a")
        self.wait_for(self.log, "start a")
        same = self.start("--", *self.hold("a"), name="b")
        other = self.start("--", *self.hold("a"), name="c", cwd=self.repo / "sub")
        self.wait_for(self.tmp / "b.err", "waiting for the suite lock")
        self.wait_for(self.log, "start a\nstart a\n")
        self.release.touch()
        for process in (first, same, other):
            self.assertEqual(process.wait(timeout=20), 0)

        # B did not run A's command again: only A and C ran it.
        self.assertEqual(sorted(self.log_lines()), ["end a", "end a", "start a", "start a"])
        waiting = (self.tmp / "b.err").read_text()
        self.assertIn(f"PID {first.pid} (", waiting)
        self.assertIn("-c", waiting)
        self.assertRegex(waiting, r"started \d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ")
        self.assertNotIn("waiting for the suite lock", (self.tmp / "c.err").read_text())

        # B reused A's pass, so the wait line is its last line, for tail.
        out = {name: (self.tmp / f"{name}.out").read_text().splitlines() for name in "abc"}
        folder = re.escape(str(self.repo.resolve()))
        wait_line = rf"Suite lock wait: \d+ s, held by PID {first.pid} \(.+\) in {folder}"
        self.assertIn("a pass is recorded for tree", out["b"][-2])
        self.assertRegex(out["b"][-1], f"^{wait_line}$")
        for name in ("a", "c"):
            self.assertFalse([line for line in out[name] if line.startswith("Suite lock wait")])
            self.assertEqual(out[name][-1], "Exit status: 0")

    def test_root_suite_runs_while_a_dev_skills_suite_holds_its_lock(self):
        (self.repo / "tests").mkdir()
        (self.repo / "tests" / "test_root.py").write_text(ROOT_TESTS)
        dev_skills = [sys.executable, "-m", "unittest", "discover", "-s", "dev-skills/tests",
                      "-p", "test_*.py"]
        with open(self.suite_lock_path(dev_skills), "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            result = self.run_suite("--", sys.executable, "-m", "unittest", "discover",
                                    "-s", "tests", "-p", "test_*.py")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Ran 1 test", result.stdout)
        self.assertNotIn("waiting for the suite lock", result.stderr)
        self.assertNotIn("Suite lock wait", result.stdout)

    def test_pass_waits_for_the_pass_records_lock_and_keeps_the_other_records(self):
        self.release.touch()
        passes = self.repo / ".git" / "run-suite-passes.json"
        earlier = {"tree": "earlier", "command": ["x"], "folder": ".", "time": "t1",
                   "commit": "c1"}
        passes.write_text(json.dumps([earlier]))
        with open(self.repo / ".git" / "run-suite-passes.lock", "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            run = self.start("--", *self.hold(), name="r")
            self.wait_for(self.tmp / "r.err", "waiting for the pass-records lock")
            self.assertIsNone(run.poll())
            # Another suite records its pass while it holds the lock.
            concurrent = {**earlier, "tree": "concurrent", "time": "t2"}
            passes.write_text(json.dumps([earlier, concurrent]))
        self.assertEqual(run.wait(timeout=20), 0)
        records = json.loads(passes.read_text())
        self.assertEqual(records[:2], [earlier, concurrent])
        self.assertEqual([entry["tree"] for entry in records[2:]],
                         [self.git("rev-parse", "HEAD^{tree}")])

    def test_wait_line_names_the_first_and_the_last_holder(self):
        # The test holds the lock, and before it releases the lock it writes the
        # details of a later holder, as when runs queue. "" is not written yet.
        first = {"pid": 11, "command": "first suite", "folder": "/first", "start": "s1"}
        last = {"pid": 22, "command": "last suite", "folder": "/last", "start": "s2"}
        cases = [(first, "PID 11 (first suite) in /first, and last by PID 22 (last suite) in /last"),
                 (None, "PID 22 (last suite) in /last")]
        self.release.touch()
        for index, (details, holders) in enumerate(cases):
            with open(self.suite_lock_path(self.hold()), "w") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                lock.write(json.dumps(details) if details else "")
                lock.flush()
                waiting = self.start("--rerun", "--", *self.hold(), name=f"w{index}")
                self.wait_for(self.tmp / f"w{index}.err", "waiting for the suite lock")
                lock.seek(0)
                lock.truncate()
                lock.write(json.dumps(last))
            self.assertEqual(waiting.wait(timeout=20), 0)
            out = (self.tmp / f"w{index}.out").read_text().splitlines()
            self.assertRegex(out[-2], rf"^Suite lock wait: \d+ s, held by {re.escape(holders)}$")

    def test_dirty_tree_runs_every_time_and_records_nothing(self):
        (self.repo / "untracked.txt").write_text("new\n")
        self.release.touch()
        for _ in range(2):
            result = self.run_suite("--", *self.hold())
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("did not record the pass", result.stdout)
        self.assertEqual(self.log_lines(), ["start a", "end a"] * 2)
        self.assertFalse((self.repo / ".git" / "run-suite-passes.json").exists())

    def test_reuse_matches_tree_command_and_folder_and_rerun_runs_again(self):
        self.release.touch()
        commit = self.git("rev-parse", "HEAD")
        self.assertIn("recorded the pass", self.run_suite("--", *self.hold()).stdout)

        # Another commit with the same tree, as after a squash merge, reuses the pass.
        self.git("commit", "-q", "--allow-empty", "-m", "same tree")
        reused = self.run_suite("--", *self.hold())
        self.assertEqual(reused.returncode, 0)
        self.assertIn(f"(commit {commit[:12]})", reused.stdout)
        self.assertIn("--rerun", reused.stdout)
        self.assertEqual(len(self.log_lines()), 2)

        self.assertEqual(self.run_suite("--rerun", "--", *self.hold()).returncode, 0)
        self.assertEqual(self.run_suite("--", *self.hold(), cwd=self.repo / "sub").returncode, 0)
        self.assertEqual(self.run_suite("--", *self.hold("other")).returncode, 0)
        self.assertEqual(self.log_lines().count("start a"), 3)
        self.assertEqual(self.log_lines()[-2:], ["start other", "end other"])

    def test_summary_lists_failing_tests_and_totals_and_passes_the_exit_status(self):
        tests = self.tmp / "demo"
        tests.mkdir()
        (tests / "test_demo.py").write_text(DEMO_TESTS)
        result = self.run_suite("--", sys.executable, "-m", "unittest", "discover",
                                "-s", str(tests))
        self.assertEqual(result.returncode, 1)
        summary = result.stdout.split("==== run_suite summary ====\n")[1]
        self.assertEqual(summary.splitlines(), [
            "Failing tests (2):",
            "  test_demo.Demo.test_error (ERROR)",
            "  test_demo.Demo.test_fail (FAIL)",
            "Totals:",
            summary.splitlines()[4],
            "  FAILED (failures=1, errors=1)",
            "Exit status: 1",
        ])
        self.assertRegex(summary.splitlines()[4], r"^  Ran 3 tests in \S+s$")
        # The unittest report on stderr streams into stdout.
        self.assertIn("RuntimeError: boom", result.stdout)

        code = ("import sys; print('FAILED t.py::test_x - assert 0'); "
                "print('=== 1 failed in 0.1s ==='); sys.exit(3)")
        pytest_like = self.run_suite("--", sys.executable, "-c", code)
        self.assertEqual(pytest_like.returncode, 3)
        self.assertIn("  t.py::test_x (FAILED)\nTotals:\n  === 1 failed in 0.1s ===\n"
                      "Exit status: 3\n", pytest_like.stdout)

        missing = self.run_suite("--", "no-such-command-for-run-suite")
        self.assertEqual(missing.returncode, 127)
        self.assertIn("command not found: no-such-command-for-run-suite", missing.stderr)
        outside = self.tmp / "outside"
        outside.mkdir()
        self.assertEqual(self.run_suite("--", "true", cwd=outside).returncode, 2)
        self.assertEqual(self.run_suite("--rerun").returncode, 2)

    def test_summary_names_the_sandbox_when_a_failing_run_reports_a_denied_operation(self):
        # The Claude Code sandbox blocks /bin/ps, so starting it raises this error.
        denied = [
            "PermissionError: [Errno 1] Operation not permitted: '/bin/ps'",
            "FATAL: could not create shared memory segment: Operation not permitted",
            "PermissionError: [Errno 1] Operation not permitted (while attempting to bind)",
            "OSError: [Errno 1] Operation not permitted: 'fourth'",
        ]
        script = ("import sys; lines = sys.argv[2:]; print(lines[0]); print('\\n'.join(lines)); "
                  "sys.exit(int(sys.argv[1]))")
        failing = self.run_suite("--", sys.executable, "-c", script, "1", *denied)
        self.assertEqual(failing.returncode, 1)
        summary = failing.stdout.split("==== run_suite summary ====\n")[1]
        self.assertEqual(summary.splitlines(), [
            'Sandbox: 5 output lines report "Operation not permitted", for example:',
            *[f"  {line}" for line in denied[:3]],
            "A sandbox probably blocks the suite, so these failures may not come from the change.",
            "Run the same command again outside the sandbox (in Claude Code: the Bash tool "
            "with dangerouslyDisableSandbox).",
            "Exit status: 1",
        ])

        passing = self.run_suite("--", sys.executable, "-c", script, "0", *denied)
        self.assertEqual(passing.returncode, 0)
        self.assertNotIn("Sandbox:", passing.stdout)

    def test_dev_skills_suite_runs_no_command_when_ps_cannot_list_process_1(self):
        # In the Claude Code sandbox, ps cannot read the processes of other commands.
        self.use_fake_ps("exit 1")
        # Git does not track the empty folder, so the working tree stays clean.
        (self.repo / "dev-skills" / "tests").mkdir(parents=True)
        write = [sys.executable, "-c", "import sys; open(sys.argv[1], 'a').write('ran\\n')",
                 str(self.log)]
        for cwd, folder in ((self.repo, "dev-skills/tests"), (self.repo / "sub", "../dev-skills/tests"),
                            (self.repo, "--start-directory=dev-skills/tests")):
            with self.subTest(cwd=cwd.name, folder=folder):
                blocked = self.run_suite("--", *write, folder, cwd=cwd)
                self.assertEqual(blocked.returncode, 2)
                self.assertEqual(blocked.stderr, (
                    "run_suite: a sandbox blocks ps (ps -o pid= -p 1 exited 1: no output), and the "
                    "dev-skills suite needs it, so no test ran. Run the same command again outside "
                    "the sandbox (in Claude Code: the Bash tool with dangerouslyDisableSandbox).\n"))
                self.assertEqual(self.log_lines(), [])

        other = self.run_suite("--", *write, "tests")
        self.assertEqual(other.returncode, 0, other.stderr)
        self.assertEqual(self.log_lines(), ["ran"])

        self.use_fake_ps("echo '    1'")
        allowed = self.run_suite("--", *write, "dev-skills/tests")
        self.assertEqual(allowed.returncode, 0, allowed.stderr)
        self.assertEqual(self.log_lines(), ["ran", "ran"])

    def test_ps_check_blocks_a_ps_that_cannot_start_and_passes_a_missing_ps(self):
        denied = PermissionError(1, "Operation not permitted", "/bin/ps")
        with mock.patch.object(RUN_SUITE.subprocess, "run", side_effect=denied):
            self.assertEqual(RUN_SUITE.ps_block(), "[Errno 1] Operation not permitted: '/bin/ps'")
        with mock.patch.object(RUN_SUITE.subprocess, "run", side_effect=FileNotFoundError(2, "ps")):
            self.assertIsNone(RUN_SUITE.ps_block())


def marker_time(age: timedelta) -> str:
    """Return the marker form of the time that is age before now."""
    return (datetime.now(timezone.utc) - age).strftime("%Y-%m-%dT%H:%M:%SZ")


class FakeClock:
    """The time module of run_suite.py: sleep moves the clock and runs the due events."""

    def __init__(self, events: list[tuple[float, Callable[[], object]]]):
        self.now = 0.0
        self.events = sorted(events, key=lambda event: event[0])

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds
        while self.events and self.events[0][0] <= self.now:
            self.events.pop(0)[1]()


@unittest.skipUnless(shutil.which("git"), "needs git")
class PriorityMarkerTests(GitRepoTestCase):
    """Two worktrees of one repository: the main checkout and other."""

    def setUp(self):
        super().setUp()
        self.other = self.tmp / "other"
        self.git("worktree", "add", "-q", str(self.other))
        self.marker = self.repo / ".git" / "run-suite-priority.json"

    def write_marker(self, worktree: object, started: object, **extra: object) -> None:
        self.marker.write_text(json.dumps({"worktree": worktree, "started": started, **extra}))

    def summary(self, name: str) -> list[str]:
        out = (self.tmp / f"{name}.out").read_text()
        return out.split("==== run_suite summary ====\n")[1].splitlines()

    def test_fresh_marker_makes_each_suite_of_another_worktree_wait(self):
        # The marker names the main checkout, 58 minutes after its start. Two
        # different suites in the other worktree wait for it; a run in the
        # named worktree, through a path with a symbolic link, does not.
        self.release.touch()
        named = self.tmp / "named"
        named.symlink_to(self.repo)
        self.write_marker(str(named), marker_time(timedelta(minutes=58)), branch="b", pid=1)
        root = self.start("--", *self.hold("root"), name="root", cwd=self.other)
        sub = self.start("--", *self.hold("sub"), name="sub", cwd=self.other / "sub")
        for name in ("root", "sub"):
            self.wait_for(self.tmp / f"{name}.err",
                          f"waiting for the priority marker, which names {named}, started ")
        holder = self.run_suite("--", *self.hold("holder"))
        self.assertEqual(holder.returncode, 0, holder.stderr)
        self.assertNotIn("priority marker", holder.stderr + holder.stdout.lower())
        self.assertEqual(self.log_lines(), ["start holder", "end holder"])
        self.assertIsNone(root.poll())
        self.assertIsNone(sub.poll())

        # The merge lock passes to the other worktree, which ends its waits at once.
        self.write_marker(str(self.other), marker_time(timedelta(0)))
        for name, process in (("root", root), ("sub", sub)):
            self.assertEqual(process.wait(timeout=20), 0)
            self.assertRegex(self.summary(name)[-2],
                             rf"^Priority marker wait: \d+ s, for {re.escape(str(named))}$")
            self.assertEqual(self.summary(name)[-1], "Exit status: 0")
        self.assertEqual(sorted(self.log_lines()[2:]),
                         ["end root", "end sub", "start root", "start sub"])

    def test_marker_gives_no_priority_when_missing_stale_malformed_or_gone(self):
        self.release.touch()
        repo, fresh = str(self.repo), marker_time(timedelta(0))
        cases = {
            "missing": None,
            "stale": {"worktree": repo, "started": marker_time(timedelta(minutes=60))},
            "after now": {"worktree": repo, "started": marker_time(-timedelta(hours=2))},
            "not JSON": "{",
            "a list": [repo, fresh],
            "no started": {"worktree": repo},
            "no worktree": {"started": fresh},
            "another time form": {"worktree": repo, "started": fresh.replace("T", " ")},
            "a relative path": {"worktree": "repo", "started": fresh},
            "deeply nested JSON": "[" * 200000 + "]" * 200000,
            "a gone worktree": {"worktree": str(self.tmp / "gone"), "started": fresh},
            "this worktree": {"worktree": str(self.other), "started": fresh},
            # On a file system that ignores letter case, this names this worktree.
            "this worktree in capitals": {"worktree": str(self.other.with_name("OTHER")),
                                          "started": fresh},
            "unreadable": "a folder",
        }
        for case, marker in cases.items():
            with self.subTest(case):
                if marker == "a folder":
                    self.marker.mkdir()
                elif marker is not None:
                    self.marker.write_text(marker if isinstance(marker, str)
                                           else json.dumps(marker))
                try:
                    result = self.run_suite("--rerun", "--", *self.hold(), cwd=self.other)
                finally:
                    if self.marker.is_dir():
                        self.marker.rmdir()
                    elif self.marker.exists():
                        self.marker.unlink()
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotIn("priority marker", result.stderr + result.stdout.lower())
        self.assertEqual(self.log_lines(), ["start a", "end a"] * len(cases))

    def test_run_that_takes_the_lock_after_the_marker_appears_releases_it_and_waits(self):
        # The run in the other worktree queues for the suite lock before the
        # marker exists. When it takes the lock, it finds the marker, releases
        # the lock, and waits without running its command.
        self.release.touch()
        lock_path = self.suite_lock_path(self.hold("queued"))
        with open(lock_path, "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            queued = self.start("--", *self.hold("queued"), name="queued", cwd=self.other)
            self.wait_for(self.tmp / "queued.err", "waiting for the suite lock")
            self.write_marker(str(self.repo), marker_time(timedelta(0)))
        self.wait_for(self.tmp / "queued.err", "waiting for the priority marker")
        with open(lock_path, "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.assertEqual(self.log_lines(), [])
        self.assertIsNone(queued.poll())

        self.write_marker(str(self.other), marker_time(timedelta(0)))
        self.assertEqual(queued.wait(timeout=20), 0)
        self.assertEqual(self.log_lines(), ["start queued", "end queued"])
        summary = self.summary("queued")
        self.assertRegex(summary[-3],
                         rf"^Priority marker wait: \d+ s, for {re.escape(str(self.repo))}$")
        self.assertRegex(summary[-2], r"^Suite lock wait: \d+ s, held by another run ")
        self.assertEqual(summary[-1], "Exit status: 0")

    def test_run_in_the_named_worktree_waits_for_a_suite_lock_that_another_worktree_holds(self):
        # Case 1 of #641: a run of the other worktree took the suite lock
        # before the marker named the main checkout. The run in the main
        # checkout does not take the lock while that run holds it.
        self.release.touch()
        command = self.hold("named")
        self.write_marker(str(self.repo), marker_time(timedelta(0)))
        with open(self.suite_lock_path(command), "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            named = self.start("--", *command, name="named")
            self.wait_for(self.tmp / "named.err", "waiting for the suite lock")
            self.assertEqual(self.log_lines(), [])
            self.assertIsNone(named.poll())
        self.assertEqual(named.wait(timeout=20), 0)
        self.assertEqual(self.log_lines(), ["start named", "end named"])
        summary = self.summary("named")
        self.assertRegex(summary[-2], r"^Suite lock wait: \d+ s, held by another run ")
        self.assertNotIn("priority marker", (self.tmp / "named.err").read_text())
        self.assertNotIn("Priority marker wait", summary)

    def take_lock(self, events: list[tuple[float, Callable[[], object]]]
                  ) -> tuple[float, list[str], str]:
        """Take a suite lock for the other worktree in this process, with a fake clock.

        Check that the lock is held, and release it. Return the clock time when
        the lock was taken, the wait lines, and stderr.
        """
        command = self.hold()
        lock_path = self.suite_lock_path(command)
        clock, stderr = FakeClock(events), io.StringIO()
        with mock.patch.object(RUN_SUITE, "time", clock), contextlib.redirect_stderr(stderr):
            handle, wait_lines = RUN_SUITE.take_lock(lock_path, command, self.repo / ".git",
                                                     str(self.other))
        with handle, open(lock_path, "a") as lock, self.assertRaises(BlockingIOError):
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return clock.now, wait_lines, stderr.getvalue()

    def test_run_whose_marker_is_gone_waits_for_a_new_marker_then_takes_the_lock(self):
        # A removed, stale, or malformed marker counts as gone.
        ends = {"removed": self.marker.unlink,
                "stale": lambda: self.write_marker(str(self.repo),
                                                   marker_time(timedelta(minutes=60))),
                "malformed": lambda: self.marker.write_text("{")}
        for case, end in ends.items():
            with self.subTest(case):
                self.write_marker(str(self.repo), marker_time(timedelta(0)))
                taken, wait_lines, stderr = self.take_lock([(3, end)])
                self.assertEqual(taken, 3 + RUN_SUITE.HANDOVER_WAIT)
                self.assertIn(f"waiting for the priority marker, which names {self.repo}",
                              stderr)
                self.assertEqual(wait_lines,
                                 [f"Priority marker wait: {round(taken)} s, for {self.repo}"])

    def test_new_marker_for_another_worktree_in_the_handover_wait_continues_the_wait(self):
        # Case 2 of #641: the merge lock passes from the main checkout to a
        # third worktree. Its marker comes at the last read of the handover
        # wait, 15 s after the first read that found no marker.
        third = self.tmp / "third"
        third.mkdir()
        self.write_marker(str(self.repo), marker_time(timedelta(0)))
        events = [(3, self.marker.unlink),
                  (3 + RUN_SUITE.HANDOVER_WAIT,
                   lambda: self.write_marker(str(third), marker_time(timedelta(0)))),
                  (40, self.marker.unlink)]
        taken, wait_lines, _ = self.take_lock(events)
        self.assertEqual(taken, 40 + RUN_SUITE.HANDOVER_WAIT)
        self.assertEqual(wait_lines, [f"Priority marker wait: {round(taken)} s, for {self.repo}"])

    def test_new_marker_for_this_worktree_ends_the_wait_at_once(self):
        self.write_marker(str(self.repo), marker_time(timedelta(0)))
        events = [(3, self.marker.unlink),
                  (5, lambda: self.write_marker(str(self.other), marker_time(timedelta(0))))]
        taken, wait_lines, _ = self.take_lock(events)
        self.assertEqual(taken, 5)
        self.assertEqual(wait_lines, [f"Priority marker wait: 5 s, for {self.repo}"])


if __name__ == "__main__":
    unittest.main()
