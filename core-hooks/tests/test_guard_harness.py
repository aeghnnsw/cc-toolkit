"""Tests for `guard_harness.py`, the helper that runs payloads safely (#479)."""

import tempfile
import time
import unittest
from pathlib import Path

import guard_harness
from test_safety_guard import HOME_RM, ISSUE_479_CASES


SHELLS = [shell for shell in guard_harness.SHELLS if Path(shell).exists()]


@unittest.skipUnless(SHELLS, "needs /bin/bash or /bin/zsh")
class GuardHarnessTests(unittest.TestCase):
    def test_stubs_record_blocked_commands_and_change_nothing(self):
        for shell in SHELLS:
            with self.subTest(shell=shell):
                self.assertEqual(guard_harness.run_shell(shell, "env")["ran"], ["env"])
                self.assertEqual(guard_harness.run_shell(shell, "set")["ran"], ["env"])
                self.assertEqual(
                    guard_harness.run_shell(shell, "env | cut -d= -f1")["ran"], []
                )
                result = guard_harness.run_shell(shell, f"{HOME_RM} && ls ~")
                self.assertEqual(len(result["ran"]), 1)
                self.assertTrue(result["ran"][0].startswith("rm -rf /"))
                self.assertEqual(result["status"], 0)
                result = guard_harness.run_shell(shell, "git commit -m x; gh pr list")
                self.assertEqual(result["calls"], ["git commit -m x", "gh pr list"])

    def test_runs_no_shell_for_a_program_that_no_stub_replaces(self):
        for command in ("/bin/rm -f x", "command -p rm -f x", "/usr/bin/env"):
            with self.subTest(command=command):
                result = guard_harness.run_shell(SHELLS[0], command)
                self.assertTrue(result["skipped"])
                self.assertEqual(result["status"], None)

    def test_calls_read_no_input_and_time_out(self):
        shell = SHELLS[0]
        start = time.monotonic()
        self.assertFalse(guard_harness.run_shell(shell, "cat")["timed_out"])
        self.assertTrue(
            guard_harness.run_shell(shell, "sleep 5", timeout=0.5)["timed_out"]
        )
        self.assertLess(time.monotonic() - start, 4)

    def test_compares_the_old_and_new_guard(self):
        with tempfile.TemporaryDirectory() as folder:
            old_script = guard_harness.old_guard("HEAD", folder)
            row = guard_harness.compare("env", old_script)
        self.assertEqual((row["old"], row["new"], row["miss"]), ("blocked", "blocked", False))

    def test_a_shell_runs_a_blocked_command_in_each_issue_479_case(self):
        for case, command, _ in ISSUE_479_CASES:
            if case == 6:
                continue
            with self.subTest(case=case, command=command):
                ran = [guard_harness.run_shell(shell, command)["ran"] for shell in SHELLS]
                self.assertTrue(any(ran), ran)


if __name__ == "__main__":
    unittest.main()
