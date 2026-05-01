import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "pre_git_hook.py"
CODEX_HOOKS = ROOT / "hooks" / "hooks.codex.json"


def run_hook(payload):
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, f"Hook failed (exit {result.returncode}): {result.stderr}"
    return json.loads(result.stdout)


class PreGitHookTests(unittest.TestCase):
    def test_blocks_invalid_codex_exec_command_branch_name(self):
        response = run_hook(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "exec_command",
                "tool_input": {"cmd": "git switch -c codex-plugin-support"},
            }
        )

        self.assertEqual(response["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("codex-plugin-support", response["systemMessage"])

    def test_codex_hooks_match_exec_command_for_git_guard(self):
        hooks = json.loads(CODEX_HOOKS.read_text())
        matchers = [
            entry["matcher"]
            for entry in hooks["hooks"]["PreToolUse"]
            for hook in entry["hooks"]
            if "pre_git_hook.py" in hook["command"]
        ]

        self.assertTrue(
            any("exec_command" in matcher for matcher in matchers),
            f"pre_git_hook.py matcher should include exec_command, got {matchers}",
        )


if __name__ == "__main__":
    unittest.main()
