"""Command-line checks for run_suite.py, the suite lock and pass record.

Each check builds a temporary Git repository and runs small python3 commands
through the script. The commands write their log outside the repository, so
the working tree stays clean. No check touches another repository.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_suite.py"

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


@unittest.skipUnless(shutil.which("git"), "needs git")
class RunSuiteTests(unittest.TestCase):
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

    def start(self, *args: str, name: str) -> subprocess.Popen:
        """Start the script in the background, with its output in files."""
        out = open(self.tmp / f"{name}.out", "w")
        err = open(self.tmp / f"{name}.err", "w")
        self.addCleanup(out.close)
        self.addCleanup(err.close)
        process = subprocess.Popen([sys.executable, str(SCRIPT), *args], cwd=self.repo,
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

    def test_second_run_waits_for_the_lock_then_reuses_the_pass(self):
        # A holds the lock until the release file exists. B has A's command,
        # and C has another command. Both start while A runs.
        first = self.start("--", *self.hold("a"), name="a")
        self.wait_for(self.log, "start a")
        same = self.start("--", *self.hold("a"), name="b")
        other = self.start("--", *self.hold("c"), name="c")
        for name in ("b", "c"):
            self.wait_for(self.tmp / f"{name}.err", "waiting for the suite lock")
        self.release.touch()
        for process in (first, same, other):
            self.assertEqual(process.wait(timeout=20), 0)

        # C started after A ended, and B did not run A's command again.
        self.assertEqual(self.log_lines(), ["start a", "end a", "start c", "end c"])
        for name in ("b", "c"):
            waiting = (self.tmp / f"{name}.err").read_text()
            self.assertIn(f"PID {first.pid} (", waiting)
            self.assertIn("-c", waiting)
            self.assertRegex(waiting, r"started \d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ")
        self.assertIn("a pass is recorded for tree", (self.tmp / "b.out").read_text())

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


if __name__ == "__main__":
    unittest.main()
