"""Checks for sandbox_check.py, which the test modules that need ps call first."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sandbox_check import require_ps  # noqa: E402


class RequirePsTest(unittest.TestCase):
    def test_ps_that_cannot_start_raises_one_error_with_the_sandbox_and_the_fix(self):
        with tempfile.TemporaryDirectory() as folder:
            # Starting a file without the execute bit raises PermissionError,
            # as starting /bin/ps does in the Claude Code sandbox.
            (Path(folder) / "ps").write_text("#!/bin/sh\n")
            with mock.patch.dict(os.environ, {"PATH": folder}), \
                    self.assertRaises(RuntimeError) as raised:
                require_ps()

        message = str(raised.exception)
        self.assertRegex(message, r"^a sandbox blocks ps \(\[Errno \d+\] .+\), and these tests")
        self.assertIn("outside the sandbox: python3 dev-skills/scripts/run_suite.py --", message)

    def test_missing_ps_raises_nothing(self):
        # Without ps, the modules' own guards decide, as before the check.
        with tempfile.TemporaryDirectory() as folder, \
                mock.patch.dict(os.environ, {"PATH": folder}):
            require_ps()


if __name__ == "__main__":
    unittest.main()
