import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODEX_MANIFEST = ROOT / ".codex-plugin" / "plugin.json"
# The shells that can run a hook command: the wrappers must work in both.
SHELLS = ("/bin/sh", shutil.which("zsh")) if shutil.which("zsh") else ("/bin/sh",)


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
    ("zsh_traps.py", 0, "WARNING"),
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
        shell="/bin/sh",
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
            # Codex gives hooks no project directory.
            process_env.pop("CLAUDE_PROJECT_DIR", None)
            process_env.update(
                {
                    "PLUGIN_ROOT": str(plugin_root),
                    "UV_CACHE_DIR": str(temp_path / "uv-cache"),
                }
            )
            process_env.update(env or {})
            return subprocess.run(
                [shell, "-c", command],
                input=json.dumps(payload) if payload is not None else "{}",
                text=True,
                capture_output=True,
                cwd=temp_dir,
                env=process_env,
                check=False,
            )

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
                # zsh reserves `status`, so the wrappers use another name.
                self.assertNotIn("status=", command)

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

    def test_zsh_hook_uses_each_hosts_rewrite_contract(self):
        claude_config = json.loads((ROOT / "hooks" / "hooks.json").read_text())
        claude_command = next(
            hook["command"]
            for entry in claude_config["hooks"]["PreToolUse"]
            for hook in entry["hooks"]
            if "zsh_traps.py" in hook["command"]
        )
        cases = (
            ("claude", claude_command, {
                "CLAUDE_PLUGIN_ROOT": str(ROOT),
                "PLUGIN_ROOT": "/invalid/foreign/plugin/root",
            }),
            ("codex", command_for("zsh_traps.py"), {
                "CLAUDE_PLUGIN_ROOT": "/invalid/foreign/plugin/root",
            }),
        )
        for host, command, env in cases:
            with self.subTest(host=host):
                result = self.run_configured_command(
                    command,
                    payload={
                        "hook_event_name": "PreToolUse",
                        "tool_name": "Bash",
                        "tool_input": {"command": "echo =====CODEX"},
                    },
                    env={**env, "SHELL": "/bin/zsh"},
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                output = json.loads(result.stdout)["hookSpecificOutput"]
                self.assertEqual(
                    output.get("updatedInput"),
                    {"command": "echo '=====CODEX'"},
                )
                if host == "claude":
                    self.assertNotIn("permissionDecision", output)
                else:
                    self.assertEqual(output.get("permissionDecision"), "allow")

    def test_missing_uv_follows_each_hook_failure_policy(self):
        for shell in SHELLS:
            for script_name, expected_status, marker in POLICY_CASES:
                with self.subTest(shell=shell, script_name=script_name):
                    result = self.run_configured_command(
                        command_for(script_name), env={"PATH": ""}, shell=shell
                    )
                    self.assertEqual(result.returncode, expected_status, result.stderr)
                    self.assertIn(marker, result.stderr)

    def test_missing_scripts_follow_each_hook_failure_policy(self):
        for shell in SHELLS:
            for script_name, expected_status, marker in POLICY_CASES:
                with self.subTest(shell=shell, script_name=script_name):
                    result = self.run_configured_command(
                        command_for(script_name), missing_plugin=True, shell=shell
                    )
                    self.assertEqual(result.returncode, expected_status, result.stderr)
                    self.assertIn(marker, result.stderr)

    def test_generic_script_failures_follow_each_hook_failure_policy(self):
        # A script that exits 2 did not block: only exit 3 is a block.
        for shell in SHELLS:
            for script_exit in (2, 7):
                for script_name, expected_status, marker in POLICY_CASES:
                    with self.subTest(
                        shell=shell, script_exit=script_exit, script_name=script_name
                    ):
                        result = self.run_configured_command(
                            command_for(script_name),
                            script_exit=script_exit,
                            shell=shell,
                        )
                        self.assertEqual(
                            result.returncode, expected_status, result.stderr
                        )
                        self.assertIn(marker, result.stderr)
                        self.assertIn(f"exit {script_exit}", result.stderr)

    def test_policy_blocks_pass_through_each_wrapper_without_a_failure_line(self):
        cases = (
            ("safety_guard.py", "rm -rf *", "Reason: wildcard rm target"),
            ("pre_git_hook.py", "git add .", "git add ."),
            ("pre_git_hook.py", "gh pr merge 1 --squash", "--match-head-commit"),
        )
        for shell in SHELLS:
            for script_name, command, reason in cases:
                with self.subTest(shell=shell, script_name=script_name):
                    result = self.run_configured_command(
                        command_for(script_name),
                        payload={
                            "hook_event_name": "PreToolUse",
                            "tool_name": "exec_command",
                            "tool_input": {"cmd": command},
                        },
                        shell=shell,
                    )
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertTrue(result.stderr.startswith("BLOCKED: "), result.stderr)
                    self.assertIn(reason, result.stderr)
                    self.assertNotIn("hook failed", result.stderr)


if __name__ == "__main__":
    unittest.main()
