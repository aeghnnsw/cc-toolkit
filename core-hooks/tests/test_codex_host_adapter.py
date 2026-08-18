import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODEX_MANIFEST = ROOT / ".codex-plugin" / "plugin.json"


def load_manifest():
    return json.loads(CODEX_MANIFEST.read_text())


def load_hook_config():
    manifest = load_manifest()
    hooks_path = ROOT / manifest["hooks"].removeprefix("./")
    return json.loads(hooks_path.read_text())


def configured_commands():
    return [
        hook["command"]
        for entries in load_hook_config()["hooks"].values()
        for entry in entries
        for hook in entry["hooks"]
    ]


def command_for(script_name):
    return next(
        command for command in configured_commands() if script_name in command
    )


POLICY_CASES = (
    ("safety_guard.py", 2, "BLOCKED"),
    ("pre_git_hook.py", 2, "BLOCKED"),
    ("post_tool_use.py", 0, "WARNING"),
    ("system_notification.py", 0, "WARNING"),
)


class CodexHostAdapterTests(unittest.TestCase):
    def run_configured_command(
        self,
        command,
        *,
        payload=None,
        env=None,
        missing_plugin=False,
        script_exit=None,
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            plugin_root = temp_path / "missing-plugin" if missing_plugin else ROOT
            if script_exit is not None:
                plugin_root = temp_path / "failing-plugin"
                scripts_dir = plugin_root / "scripts"
                scripts_dir.mkdir(parents=True)
                failing_script = (
                    "# /// script\n"
                    '# requires-python = ">=3.8"\n'
                    "# ///\n"
                    "import sys\n"
                    f"sys.exit({script_exit})\n"
                )
                for script_name, _, _ in POLICY_CASES:
                    (scripts_dir / script_name).write_text(failing_script)
            process_env = os.environ.copy()
            process_env.update(
                {
                    "PLUGIN_ROOT": str(plugin_root),
                    "UV_CACHE_DIR": str(temp_path / "uv-cache"),
                }
            )
            process_env.update(env or {})
            return subprocess.run(
                command,
                shell=True,
                input=json.dumps(payload) if payload is not None else "{}",
                text=True,
                capture_output=True,
                cwd=temp_dir,
                env=process_env,
                check=False,
            )

    def test_codex_adapter_has_the_1_0_12_release_version(self):
        self.assertEqual(load_manifest()["version"], "1.0.12")

    def test_manifest_selects_only_the_codex_hook_configuration(self):
        manifest = load_manifest()
        self.assertEqual(manifest["hooks"], "./hooks/hooks.codex.json")

        commands = configured_commands()

        self.assertTrue(commands)
        for command in commands:
            with self.subTest(command=command):
                self.assertIn('"${PLUGIN_ROOT}/scripts/', command)
                self.assertNotIn("CLAUDE_PLUGIN_ROOT", command)
                self.assertNotIn("GROK_PLUGIN_ROOT", command)
                self.assertNotIn("/.claude/", command)
                self.assertNotIn("/.grok/", command)

    def test_safety_hook_executes_from_codex_root_with_poisoned_foreign_root(self):
        result = self.run_configured_command(
            command_for("safety_guard.py"),
            payload={
                "hook_event_name": "PreToolUse",
                "tool_name": "exec_command",
                "tool_input": {"cmd": "pwd"},
            },
            env={"CLAUDE_PLUGIN_ROOT": "/invalid/foreign/plugin/root"},
        )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_safety_hooks_block_when_uv_is_unavailable(self):
        for script_name in ("safety_guard.py", "pre_git_hook.py"):
            with self.subTest(script_name=script_name):
                result = self.run_configured_command(
                    command_for(script_name), env={"PATH": ""}
                )
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("BLOCKED", result.stderr)

    def test_noncritical_hooks_warn_but_succeed_when_uv_is_unavailable(self):
        for script_name in ("post_tool_use.py", "system_notification.py"):
            with self.subTest(script_name=script_name):
                result = self.run_configured_command(
                    command_for(script_name), env={"PATH": ""}
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("WARNING", result.stderr)

    def test_missing_scripts_follow_each_hook_failure_policy(self):
        for script_name, expected_status, marker in POLICY_CASES:
            with self.subTest(script_name=script_name):
                result = self.run_configured_command(
                    command_for(script_name), missing_plugin=True
                )
                self.assertEqual(result.returncode, expected_status, result.stderr)
                self.assertIn(marker, result.stderr)

    def test_generic_script_failures_follow_each_hook_failure_policy(self):
        for script_name, expected_status, marker in POLICY_CASES:
            with self.subTest(script_name=script_name):
                result = self.run_configured_command(
                    command_for(script_name), script_exit=7
                )
                self.assertEqual(result.returncode, expected_status, result.stderr)
                self.assertIn(marker, result.stderr)
                self.assertIn("exit 7", result.stderr)

    def test_safety_hook_preserves_an_intentional_policy_rejection(self):
        result = self.run_configured_command(
            command_for("safety_guard.py"),
            payload={
                "hook_event_name": "PreToolUse",
                "tool_name": "exec_command",
                "tool_input": {"cmd": "rm -rf *"},
            },
        )

        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("Reason: wildcard rm target", result.stderr)


if __name__ == "__main__":
    unittest.main()
