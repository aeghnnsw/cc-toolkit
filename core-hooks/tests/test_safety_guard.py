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
            ("/var", "/var/log/example", "protected system path /var"),
            (
                "/var/folders",
                "/var/folders/example",
                "protected system path /var",
            ),
            (
                "/var/log/example/T",
                "/var/log/example/T/candidate.json",
                "protected system path /var",
            ),
            ("/", "/etc/example", "protected system path /etc"),
            (
                "/private",
                "/private/var/log/example",
                "protected system path /private/var",
            ),
            (
                "/var/folders/8n/example/nested/T",
                "/var/folders/8n/example/nested/T/candidate.json",
                "protected system path /var",
            ),
        )
        for temp_root, target, reason in cases:
            with self.subTest(temp_root=temp_root):
                self.assert_blocked(
                    f"rm -rf {target}",
                    reason,
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

    def test_allows_rm_text_in_nonexecuting_arguments(self):
        commands = (
            "xargs echo rm /var/log/example",
            "timeout 5 echo rm /var/log/example",
            "sudo echo rm /var/log/example",
            'env echo -S "rm -rf /var/log/example"',
            'env echo --split-string "rm -rf /var/log/example"',
            'env -S "echo ; rm /var/log/example"',
            'fish --command="echo rm /var/log/example"',
            "gh issue create --title rm --body /var/log/example",
            "find /tmp -name rm -print",
            "watch -x echo rm /var/log/example",
            "watch -x echo ';' rm /var/log/example",
            "parallel echo rm /var/log/example ::: input",
        )
        for command in commands:
            with self.subTest(command=command):
                self.assert_allowed(command)

    def test_allows_dangerous_rm_text_in_shell_comments(self):
        commands = (
            "echo ready # rm -rf /var/log/example",
            "echo ready # $(rm -rf /var/log/example)",
        )
        for command in commands:
            with self.subTest(command=command):
                self.assert_allowed(command)

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

    def test_blocks_rm_after_sudo_options_with_values(self):
        commands = (
            "sudo -D /tmp rm -rf /var/log/example",
            "sudo -nD /tmp rm -rf /var/log/example",
            "sudo -R /tmp/root rm -rf /var/log/example",
            "sudo -T 5 rm -rf /var/log/example",
            "sudo --command-timeout 5 rm -rf /var/log/example",
        )
        for command in commands:
            with self.subTest(command=command):
                self.assert_blocked(command, "protected system path /var")

    def test_blocks_protected_system_target_through_env(self):
        commands = (
            "env MODE=test rm -rf /var/log/example",
            "env -P /bin rm -rf /var/log/example",
            "env -ivP /bin rm -rf /var/log/example",
        )
        for command in commands:
            with self.subTest(command=command):
                self.assert_blocked(command, "protected system path /var")

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
            "RM /var/log/example",
            "SUDO RM /var/log/example",
        )
        for command in commands:
            with self.subTest(command=command):
                self.assert_blocked(command, "protected system path /var")

    def test_blocks_rm_inside_shell_command_string(self):
        commands = (
            'bash -c "rm /var/log/example"',
            'sudo sh -c "rm /var/log/example"',
            'env MODE=test zsh -lc "rm /var/log/example"',
            'fish --command="rm /var/log/example"',
            'fish -C "rm /var/log/example"',
            'fish --init-command="rm /var/log/example"',
            'fish -ic "rm /var/log/example"',
            'bash +O extglob -c "rm /var/log/example"',
            'zsh +o aliases -c "rm /var/log/example"',
        )
        for command in commands:
            with self.subTest(command=command):
                self.assert_blocked(command, "protected system path /var")

    def test_blocks_rm_inside_command_string_launchers(self):
        commands = (
            'eval "rm -rf /var/log/example"',
            'env -S "rm -rf /var/log/example"',
            'env -S "rm -rf" /var/log/example',
            'env -S"rm -rf" /var/log/example',
            "env -S \"sh -c 'rm -rf /var/log/example'\"",
            'watch "rm -rf /var/log/example"',
            'xargs sh -c "rm -rf /var/log/example"',
            r'find /tmp -exec sh -c "rm -rf /var/log/example" \;',
        )
        for command in commands:
            with self.subTest(command=command):
                self.assert_blocked(command, "protected system path /var")

    def test_blocks_rm_after_wrapper_options_with_values(self):
        commands = (
            "exec -a cleanup rm -rf /var/log/example",
            "time -o /tmp/timing rm -rf /var/log/example",
            "time -f %E rm -rf /var/log/example",
        )
        for command in commands:
            with self.subTest(command=command):
                self.assert_blocked(command, "protected system path /var")

    def test_blocks_rm_invoked_by_xargs(self):
        commands = (
            "xargs -0 rm -rf /var/log/example",
            "xargs -a /tmp/input rm -rf /var/log/example",
            "xargs --arg-file /tmp/input rm -rf /var/log/example",
            "xargs -I {} rm -rf /var/log/example/{}",
            "xargs -0I {} rm -rf /var/log/example/{}",
            "xargs -J % rm -rf /var/log/example/%",
            "xargs --replace rm -rf /var/log/example",
            "xargs --eof rm -rf /var/log/example",
        )
        for command in commands:
            with self.subTest(command=command):
                self.assert_blocked(command, "protected system path /var")

    def test_blocks_rm_invoked_by_find_exec(self):
        commands = (
            (
                r"find /tmp -name example -exec rm -rf /var/log/example {} \;",
                "protected system path /var",
            ),
            (
                r"find /var/log/example -type f -exec rm -rf {} \;",
                "protected system path /var",
            ),
            (
                r"find /tmp /etc/example -type f -exec rm -rf {} \;",
                "protected system path /etc",
            ),
            (
                r"find -L /var/log/example -type f -exec rm -rf {} \;",
                "protected system path /var",
            ),
        )
        for command, reason in commands:
            with self.subTest(command=command):
                self.assert_blocked(command, reason)

    def test_allows_find_exec_rm_with_safe_placeholder_prefix(self):
        self.assert_allowed(
            r"find /var/log/example -type f "
            r"-exec rm -f /tmp/copies/{} \;"
        )

    def test_blocks_rm_through_common_process_wrappers(self):
        commands = (
            "timeout 5 rm -rf /var/log/example",
            "timeout -vk 1 5 rm -rf /var/log/example",
            "nice -n 10 rm -rf /var/log/example",
            "ionice -c 2 -n 7 rm -rf /var/log/example",
            "stdbuf -oL rm -rf /var/log/example",
            "stdbuf -o L rm -rf /var/log/example",
            "stdbuf --output L rm -rf /var/log/example",
            "chroot /tmp/root rm -rf /var/log/example",
            "watch -n 1 rm -rf /var/log/example",
            "watch -q 5 rm -rf /var/log/example",
            "watch --shotsdir /tmp rm -rf /var/log/example",
            "parallel rm -rf /var/log/example ::: input",
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

    def test_blocks_rm_inside_process_substitution(self):
        commands = (
            "cat <(rm -rf /var/log/example)",
            "cat >(rm -rf /var/log/example)",
        )
        for command in commands:
            with self.subTest(command=command):
                self.assert_blocked(command, "protected system path /var")

    def test_allows_literal_or_nondestructive_process_substitution(self):
        commands = (
            'echo "<(rm -rf /var/log/example)"',
            "echo '>(rm -rf /var/log/example)'",
            "cat <(echo rm -rf /var/log/example)",
        )
        for command in commands:
            with self.subTest(command=command):
                self.assert_allowed(command)

    def test_allows_rm_text_inside_single_quotes(self):
        commands = (
            "echo '$(rm /var/log/example)'",
            "echo '`rm /var/log/example`'",
        )
        for command in commands:
            with self.subTest(command=command):
                self.assert_allowed(command)

    def test_blocks_protected_target_after_quoted_hash_argument(self):
        self.assert_blocked(
            'rm "#placeholder" /var/log/example',
            "protected system path /var",
        )

    def test_blocks_protected_target_after_quoted_shell_punctuation(self):
        commands = (
            'rm ";" /var/log/example',
            'rm ">" /var/log/example',
            r"rm \; /var/log/example",
            'rm "\\`" /var/log/example',
            'echo "#"; rm -rf /var/log/example',
            "echo '# note' && rm -rf /var/log/example",
        )
        for command in commands:
            with self.subTest(command=command):
                self.assert_blocked(command, "protected system path /var")

    def test_blocks_protected_target_with_shell_redirections(self):
        commands = (
            "> /tmp/guard.log rm -rf /var/log/example",
            "rm -rf > /tmp/guard.log /var/log/example",
            "rm -rf 2> /dev/null /var/log/example",
        )
        for command in commands:
            with self.subTest(command=command):
                self.assert_blocked(command, "protected system path /var")

    def test_blocks_rm_split_across_line_continuation(self):
        commands = (
            "r\\\nm -rf /var/log/example",
            "rm -rf /va\\\nr/log/example",
        )
        for command in commands:
            with self.subTest(command=command):
                self.assert_blocked(command, "protected system path /var")

    def test_allows_protected_path_used_only_as_redirection(self):
        self.assert_allowed(
            "rm /tmp/candidate.json > /var/log/safety-guard-output"
        )

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
            ("rm -rf //var/log/example", "protected system path /var"),
            ("rm -rf /etc/example", "protected system path /etc"),
            ("rm -rf ///etc/example", "protected system path /etc"),
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
