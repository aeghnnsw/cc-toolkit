"""Compile production helpers with unsaved EventKit objects. Never request access or save."""
import json
import os
import pathlib
import subprocess
import tempfile
import unittest


class ReminderMutationTests(unittest.TestCase):
    def test_isolated_mutations(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        source = (root / "scripts/productivity-cli.swift").read_text()
        # Exclude command dispatch, so this test cannot request store access.
        source = source.split("let args = Array(CommandLine.arguments.dropFirst())", 1)[0]
        assertions = (root / "tests/reminder_mutations.swift").read_text()
        with tempfile.TemporaryDirectory(prefix="reminder-tests-") as temp:
            main = pathlib.Path(temp) / "main.swift"
            main.write_text(source + "\n" + assertions)
            binary = pathlib.Path(temp) / "tests"
            build = subprocess.run(["swiftc", str(main), "-o", str(binary)], capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True, env={**os.environ, "TZ": "America/New_York"})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Reminder mutation checks passed", result.stdout)


    def test_cli_rejects_invalid_mutations_before_access(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix="reminder-cli-tests-") as temp:
            binary = pathlib.Path(temp) / "productivity-cli"
            build = subprocess.run(
                ["swiftc", str(root / "scripts/productivity-cli.swift"), "-o", str(binary)],
                capture_output=True, text=True,
            )
            self.assertEqual(build.returncode, 0, build.stderr)
            cases = [
                (["complete", "--id"], "Missing value"),
                (["delete", "--id", "one", "--id", "two"], "repeated argument"),
                (["uncomplete", "--id", "one", "--title", "Task"], "exactly one"),
                (["update", "--id", "one", "--due", "2026-02-30"], "Invalid due date"),
                (["update", "--id", "one", "--due", "2026-09-07", "--clear-due"], "not both"),
                (["update", "--id", "one", "--repeat", "daily"], "Unknown"),
                (["update", "--title", "Task"], "required argument: --id"),
            ]
            for arguments, expected in cases:
                with self.subTest(arguments=arguments):
                    result = subprocess.run([str(binary), "reminders", *arguments], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 1, result.stderr)
                    self.assertIn(expected, json.loads(result.stdout)["error"])


if __name__ == "__main__":
    unittest.main()
