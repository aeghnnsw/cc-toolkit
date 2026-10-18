"""Command-line checks for the call limit helper of the Codex pressure-test copy.

Each test runs the helper with a small Python program as the command. A
program that must be ready before the limit writes its process ID to a file.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PLUGIN_ROOT / "codex-skills" / "pressure-test" / "scripts" / "limit_call.py"
# A command that ignores SIGTERM, writes its process ID, and sleeps.
IGNORES_TERM = """\
import os, signal, sys, time
signal.signal(signal.SIGTERM, signal.SIG_IGN)
open(sys.argv[1] + ".tmp", "w").write(str(os.getpid()))
os.replace(sys.argv[1] + ".tmp", sys.argv[1])
time.sleep(60)
"""
# A command that writes its process ID and sleeps; it ends on SIGTERM.
WRITES_PID = IGNORES_TERM.replace("signal.signal(signal.SIGTERM, signal.SIG_IGN)\n", "")
# A command that starts a child in the command's process group; the child ignores
# SIGTERM and writes its process ID. The command itself ends on SIGTERM.
STARTS_CHILD = """\
import subprocess, sys, time
subprocess.Popen([sys.executable, "-c", sys.argv[2], sys.argv[1]])
time.sleep(60)
"""
# Load the helper from sys.argv[1] as a module.
LOAD_HELPER = """\
import importlib.util, os, signal, subprocess, sys, time
spec = importlib.util.spec_from_file_location("limit_call", sys.argv[1])
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
"""
# Run the helper with a 60-second limit on the command in sys.argv[3:]. The
# helper gets SIGTERM after its command started but before Popen returned;
# the command's process ID goes to sys.argv[2].
TERM_DURING_START = LOAD_HELPER + """\
class SignaledPopen(subprocess.Popen):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        open(sys.argv[2], "w").write(str(self.pid))
        os.kill(os.getpid(), signal.SIGTERM)
        time.sleep(1)
helper.subprocess.Popen = SignaledPopen
sys.exit(helper.main(["limit_call.py", "60", *sys.argv[3:]]))
"""
# End a command that exited but is not reaped yet, as when it exits just
# after the limit; print its exit code.
END_AFTER_EXIT = LOAD_HELPER + """\
process = subprocess.Popen([sys.executable, "-c", "pass"], start_new_session=True)
while subprocess.run(["/bin/ps", "-o", "stat=", "-p", str(process.pid)], capture_output=True,
                     text=True).stdout.strip()[:1] not in ("", "Z"):
    time.sleep(0.05)
helper.end(process)
print(process.returncode)
"""


def reaped(pid: int) -> bool:
    """Return True when no process, not even a zombie, has the ID."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    return False


def gone(pid: int, wait: float = 3.0) -> bool:
    """Return True when the process ends within the wait; a zombie counts as ended."""
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        if reaped(pid):
            return True
        state = subprocess.run(["/bin/ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True).stdout
        if state.strip()[:1] in ("", "Z"):
            return True
        time.sleep(0.05)
    return False


def kill_quietly(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


class LimitCallTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.pid_file = self.root / "pid"

    def run_helper(self, *arguments: str, stdin: str = "") -> tuple[int, str, str, float]:
        """Run the helper; return its exit code, stdout, stderr, and elapsed time."""
        started = time.monotonic()
        completed = subprocess.run([sys.executable, str(SCRIPT), *arguments], input=stdin, capture_output=True,
                                   text=True, timeout=60)
        return completed.returncode, completed.stdout, completed.stderr, time.monotonic() - started

    def run_until_ready(self, *command: str) -> tuple[int, float, int]:
        """Run a command that writes its process ID; return the exit code, the overrun, and the ID.

        On a busy machine, a Python program can need more than a 1-second limit to
        start. While the program did not write its ID, run again with a doubled limit.
        """
        for seconds in (1, 2, 4, 8):
            self.pid_file.unlink(missing_ok=True)
            code, _, _, elapsed = self.run_helper(str(seconds), *command)
            if self.pid_file.exists():
                pid = int(self.pid_file.read_text())
                self.addCleanup(kill_quietly, pid)
                return code, elapsed - seconds, pid
        self.fail("the command did not start within an 8-second limit")

    def signal_helper(self, signum: int, source: str) -> tuple[int, int]:
        """Run the helper with a 60-second limit on a command that writes its process ID.

        When the command has written its ID, send signum to the helper. Return
        the helper's exit code and the command's process ID.
        """
        self.pid_file.unlink(missing_ok=True)
        helper = subprocess.Popen([sys.executable, str(SCRIPT), "60", sys.executable, "-c", source,
                                   str(self.pid_file)])
        self.addCleanup(kill_quietly, helper.pid)
        deadline = time.monotonic() + 10
        while not self.pid_file.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        pid = int(self.pid_file.read_text())
        self.addCleanup(kill_quietly, pid)
        helper.send_signal(signum)
        return helper.wait(timeout=20), pid

    def test_exit_code_stdin_stdout_and_stderr_pass_through(self):
        echo = "import sys; print(sys.stdin.read().upper()); sys.stderr.write('note'); sys.exit(3)"
        code, stdout, stderr, _ = self.run_helper("30", sys.executable, "-c", echo, stdin="packet")
        self.assertEqual((code, stdout, stderr), (3, "PACKET\n", "note"))

    def test_command_ended_by_a_signal_exits_128_plus_the_signal(self):
        suicide = "import os, signal; os.kill(os.getpid(), signal.SIGKILL)"
        self.assertEqual(self.run_helper("30", sys.executable, "-c", suicide)[0], 128 + signal.SIGKILL)

    def test_command_that_ignores_term_is_killed_and_reaped_before_the_helper_exits_124(self):
        code, overrun, pid = self.run_until_ready(sys.executable, "-c", IGNORES_TERM, str(self.pid_file))
        self.assertEqual(code, 124)
        self.assertTrue(reaped(pid), "the command still ran, or was not reaped, when the helper exited")
        self.assertGreaterEqual(overrun, 4.5, "the helper did not give the command its grace period")
        self.assertLess(overrun, 5 + 3)

    def test_command_that_ends_on_term_does_not_wait_for_the_grace_period(self):
        code, _, _, elapsed = self.run_helper("1", sys.executable, "-c", "import time; time.sleep(60)")
        self.assertEqual(code, 124)
        self.assertLess(elapsed, 1 + 3)

    def test_child_in_the_command_process_group_also_ends(self):
        code, _, pid = self.run_until_ready(sys.executable, "-c", STARTS_CHILD, str(self.pid_file), IGNORES_TERM)
        self.assertEqual(code, 124)
        self.assertTrue(gone(pid), "a child in the command's process group survived")

    def test_term_to_the_helper_ends_the_command_before_the_helper_exits(self):
        code, pid = self.signal_helper(signal.SIGTERM, IGNORES_TERM)
        self.assertEqual(code, 128 + signal.SIGTERM)
        self.assertTrue(reaped(pid), "the command outlived the helper")

    def test_int_or_hup_to_the_helper_also_ends_the_command_before_the_helper_exits(self):
        for signum in (signal.SIGINT, signal.SIGHUP):
            with self.subTest(signal=signum.name):
                code, pid = self.signal_helper(signum, WRITES_PID)
                self.assertEqual(code, 128 + signum)
                self.assertTrue(reaped(pid), "the command outlived the helper")

    def test_term_while_the_command_starts_ends_the_command_before_the_helper_exits(self):
        with open(self.root / "stderr", "w+", encoding="utf-8") as stderr:  # a file: a live command holds no pipe
            completed = subprocess.run([sys.executable, "-c", TERM_DURING_START, str(SCRIPT), str(self.pid_file),
                                        sys.executable, "-c", "import time; time.sleep(60)"],
                                       stdout=subprocess.DEVNULL, stderr=stderr, timeout=30)
            stderr.seek(0)
            pid = int(self.pid_file.read_text())
            self.addCleanup(kill_quietly, pid)
            self.assertEqual(completed.returncode, 128 + signal.SIGTERM, stderr.read())
        self.assertTrue(reaped(pid), "the command outlived the helper")

    def test_end_of_a_command_that_already_exited_reaps_it_without_an_error(self):
        completed = subprocess.run([sys.executable, "-c", END_AFTER_EXIT, str(SCRIPT)], capture_output=True,
                                   text=True, timeout=30)
        self.assertEqual((completed.returncode, completed.stdout, completed.stderr), (0, "0\n", ""))

    def test_bad_arguments_exit_2_without_running_a_command(self):
        marker = self.root / "ran"
        touch = [sys.executable, "-c", f"open({str(marker)!r}, 'w')"]
        for arguments in ([], ["5"], ["soon", *touch], ["0", *touch], ["-1", *touch]):
            with self.subTest(arguments=arguments[:1]):
                code, _, stderr, _ = self.run_helper(*arguments)
                self.assertEqual(code, 2)
                self.assertIn("usage", stderr.lower())
                self.assertFalse(marker.exists())

    def test_command_that_cannot_run_exits_126(self):
        command = self.root / "not-executable"
        command.write_text("#!/bin/sh\n", encoding="utf-8")
        code, _, stderr, _ = self.run_helper("5", str(command))
        self.assertEqual(code, 126)
        self.assertIn("cannot run", stderr)

    def test_missing_command_exits_127(self):
        code, _, stderr, _ = self.run_helper("5", str(self.root / "no-such-command"))
        self.assertEqual(code, 127)
        self.assertIn("no-such-command", stderr)


if __name__ == "__main__":
    unittest.main()
