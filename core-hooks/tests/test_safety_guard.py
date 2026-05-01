import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "safety_guard.py"
CODEX_HOOKS = ROOT / "hooks" / "hooks.codex.json"


def run_hook(payload):
    with tempfile.TemporaryDirectory() as temp_dir:
        return subprocess.run(
            [sys.executable, str(SCRIPT)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            cwd=temp_dir,
            check=False,
        )


class SafetyGuardTests(unittest.TestCase):
    def test_blocks_dangerous_codex_exec_command_rm(self):
        result = run_hook(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "exec_command",
                "tool_input": {"cmd": "rm -rf *"},
            }
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("BLOCKED", result.stderr)

    def test_codex_hooks_match_exec_command_for_safety_guard(self):
        hooks = json.loads(CODEX_HOOKS.read_text())
        matchers = [
            entry["matcher"]
            for entry in hooks["hooks"]["PreToolUse"]
            for hook in entry["hooks"]
            if "safety_guard.py" in hook["command"]
        ]

        self.assertTrue(
            any("exec_command" in matcher for matcher in matchers),
            f"safety_guard.py matcher should include exec_command, got {matchers}",
        )


if __name__ == "__main__":
    unittest.main()
