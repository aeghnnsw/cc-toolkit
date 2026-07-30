import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "safety_guard.py"
CODEX_HOOKS = ROOT / "hooks" / "hooks.codex.json"


def run_hook(payload, env=None):
    process_env = os.environ.copy()
    process_env.update(env or {})
    with tempfile.TemporaryDirectory() as temp_dir:
        return subprocess.run(
            [sys.executable, str(SCRIPT)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            cwd=temp_dir,
            env=process_env,
            check=False,
        )


class SafetyGuardTests(unittest.TestCase):
    def run_command(self, command, tool_name="exec_command", env=None):
        input_key = "command" if tool_name == "Bash" else "cmd"
        return run_hook(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": tool_name,
                "tool_input": {input_key: command},
            },
            env=env,
        )

    def assert_allowed(self, command, tool_name="exec_command", env=None):
        result = self.run_command(command, tool_name=tool_name, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)

    def assert_blocked(self, command, reason, tool_name="exec_command", env=None):
        result = self.run_command(command, tool_name=tool_name, env=env)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("BLOCKED", result.stderr)
        self.assertIn(f"Reason: {reason}", result.stderr)

    def test_blocks_dangerous_codex_exec_command_rm(self):
        self.assert_blocked(
            "rm -rf *",
            "wildcard rm target",
        )

    def test_allows_explicit_file_beneath_macos_tmpdir(self):
        temp_root = "/var/folders/8n/example/T"
        self.assert_allowed(
            f"rm {temp_root}/candidate.json",
            env={"TMPDIR": temp_root},
        )

    def test_blocks_macos_tmpdir_root_itself(self):
        temp_root = "/var/folders/8n/example/T"
        self.assert_blocked(
            f"rm -rf {temp_root}",
            "temporary directory root",
            env={"TMPDIR": temp_root},
        )

    def test_blocks_parent_traversal_from_macos_tmpdir(self):
        temp_root = "/var/folders/8n/example/T"
        self.assert_blocked(
            f"rm {temp_root}/../outside",
            "parent directory reference",
            env={"TMPDIR": temp_root},
        )

    def test_does_not_trust_broad_protected_tmpdir(self):
        cases = (
            ("/var", "/var/log/example"),
            ("/var/folders", "/var/folders/example"),
            ("/var/log/example/T", "/var/log/example/T/candidate.json"),
        )
        for temp_root, target in cases:
            with self.subTest(temp_root=temp_root):
                self.assert_blocked(
                    f"rm -rf {target}",
                    "protected system path /var",
                    env={"TMPDIR": temp_root},
                )

    def test_does_not_allow_macos_tmpdir_sibling_prefix(self):
        temp_root = "/var/folders/8n/example/T"
        self.assert_blocked(
            f"rm -rf {temp_root}-other/candidate.json",
            "protected system path /var",
            env={"TMPDIR": temp_root},
        )

    def test_allows_glob_in_later_command(self):
        self.assert_allowed("rm /tmp/a.txt /tmp/b.txt && ls /tmp/prefix*")

    def test_allows_rm_text_in_quoted_issue_title(self):
        self.assert_allowed(
            'gh issue create --title "safety_guard blocks rm under /var/folders"'
        )

    def test_blocks_wildcard_owned_by_rm(self):
        self.assert_blocked(
            "rm -rf /tmp/prefix*",
            "wildcard rm target",
        )

    def test_blocks_protected_system_target_after_separator(self):
        self.assert_blocked(
            "echo ready && rm -rf /var/log/example",
            "protected system path /var",
        )

    def test_blocks_protected_system_target_through_sudo(self):
        self.assert_blocked(
            "sudo rm -rf /var/log/example",
            "protected system path /var",
        )

    def test_blocks_protected_system_target_through_env(self):
        self.assert_blocked(
            "env MODE=test rm -rf /var/log/example",
            "protected system path /var",
        )

    def test_blocks_rm_after_shell_boundaries(self):
        commands = (
            "echo ready && rm /var/log/example",
            "false || rm /var/log/example",
            "echo ready; rm /var/log/example",
            "echo ready | rm /var/log/example",
            "echo ready\nrm /var/log/example",
            "(rm /var/log/example)",
            "echo `rm /var/log/example`",
        )
        for command in commands:
            with self.subTest(command=command):
                self.assert_blocked(command, "protected system path /var")

    def test_blocks_supported_rm_program_forms(self):
        commands = (
            "command rm /var/log/example",
            "/bin/rm /var/log/example",
            "MODE=test rm /var/log/example",
        )
        for command in commands:
            with self.subTest(command=command):
                self.assert_blocked(command, "protected system path /var")

    def test_blocks_rm_inside_shell_command_string(self):
        commands = (
            'bash -c "rm /var/log/example"',
            'sudo sh -c "rm /var/log/example"',
            'env MODE=test zsh -lc "rm /var/log/example"',
        )
        for command in commands:
            with self.subTest(command=command):
                self.assert_blocked(command, "protected system path /var")

    def test_blocks_rm_inside_shell_group_or_function(self):
        commands = (
            "{ rm /var/log/example; }",
            "cleanup() { rm /var/log/example; }; cleanup",
            "function cleanup { rm /var/log/example; }; cleanup",
        )
        for command in commands:
            with self.subTest(command=command):
                self.assert_blocked(command, "protected system path /var")

    def test_blocks_rm_inside_double_quoted_command_substitution(self):
        commands = (
            'echo "$(rm /var/log/example)"',
            'echo "`rm /var/log/example`"',
        )
        for command in commands:
            with self.subTest(command=command):
                self.assert_blocked(command, "protected system path /var")

    def test_allows_rm_text_inside_single_quotes(self):
        commands = (
            "echo '$(rm /var/log/example)'",
            "echo '`rm /var/log/example`'",
        )
        for command in commands:
            with self.subTest(command=command):
                self.assert_allowed(command)

    def test_blocks_malformed_rm_shell_text(self):
        self.assert_blocked(
            'rm "/var/log/example',
            "unparseable rm command",
        )

    def test_allows_explicit_tmp_file_for_claude_bash(self):
        self.assert_allowed(
            "rm /tmp/candidate.json",
            tool_name="Bash",
        )

    def test_blocks_existing_protected_target_categories(self):
        cases = (
            ("rm -rf /", "root directory"),
            ("rm -rf .", "current directory target"),
            ("rm -rf ..", "parent directory reference"),
            ("rm -rf ~", "home directory target"),
            ("rm -rf $HOME/work", "home directory target"),
            ("rm -rf /usr/local/example", "protected system path /usr"),
            ("rm -rf /var/log/example", "protected system path /var"),
            ("rm -rf /etc/example", "protected system path /etc"),
            ("rm -rf /bin/example", "protected system path /bin"),
            ("rm -rf /sbin/example", "protected system path /sbin"),
            ("rm -rf /lib/example", "protected system path /lib"),
            ("rm -rf /opt/example", "protected system path /opt"),
            ("rm -rf /sys/example", "protected system path /sys"),
            ("rm -rf /proc/example", "protected system path /proc"),
            ("rm -rf /dev/example", "protected system path /dev"),
            ("rm -rf /boot/example", "protected system path /boot"),
        )
        for command, reason in cases:
            with self.subTest(command=command):
                self.assert_blocked(command, reason)

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
