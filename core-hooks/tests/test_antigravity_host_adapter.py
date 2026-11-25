import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOOKS_PATH = ROOT / "hooks.json"
SCRIPTS = ROOT / "scripts"
ZSH = shutil.which("zsh") or "/bin/zsh"
CONVERSATION_ID = "0e1e1830-ad54-4a2e-b756-99d69967d686"
BRAIN = "/home/user/.gemini/antigravity-cli/brain/" + CONVERSATION_ID
FILE_TOOLS = (
    "read_file", "write_file", "edit_file", "view_file", "write_to_file",
    "replace_file_content", "multi_replace_file_content",
)
# Each script, the exit status of its wrapped command when the script fails,
# and the line that the wrapper writes to stderr.
POLICY_CASES = (
    ("safety_guard.py", 2, "BLOCKED: core-hooks safety hook failed"),
    ("pre_git_hook.py", 2, "BLOCKED: core-hooks git policy hook failed"),
    ("zsh_traps.py", 0, "WARNING: core-hooks zsh trap hook failed"),
    ("post_tool_use.py", 0, "WARNING: core-hooks logging hook failed"),
    ("system_notification.py", 0, "WARNING: core-hooks notification hook failed"),
)
# The shells that can run a hook command: the wrappers must work in both.
SHELLS = ("/bin/sh", ZSH) if shutil.which("zsh") else ("/bin/sh",)


def load_hook_config():
    return json.loads(HOOKS_PATH.read_text())


def configured_hooks():
    """Yield (event, matcher, command) for each command in the root hooks.json."""
    for events in load_hook_config().values():
        for event, entries in events.items():
            for entry in entries:
                if "hooks" in entry:
                    for hook in entry["hooks"]:
                        yield event, entry.get("matcher"), hook["command"]
                else:
                    # Stop entries have no matcher.
                    yield event, None, entry["command"]


def command_for(script_name):
    return next(
        command for _, _, command in configured_hooks() if script_name in command
    )


def payload(event, cwd, tool_call=None):
    """Return an Antigravity hook payload, as agy 1.5.13 sends it."""
    data = {
        "artifactDirectoryPath": BRAIN,
        "conversationId": CONVERSATION_ID,
        "cwd": str(cwd),
        "hookEventName": event,
        "lastUserInput": "Run the command.",
        "modelName": "gemini-4-neon-high",
        "stepIdx": 2,
        "transcriptPath": BRAIN + "/.system_generated/logs/transcript_full.jsonl",
        "workspacePaths": [str(cwd)],
    }
    if tool_call is not None:
        data["toolCall"] = tool_call
    if event == "PostToolUse":
        data["error"] = ""
    if event == "Stop":
        data.update({
            "continuationActive": False,
            "error": "",
            "executionNum": 0,
            "fullyIdle": True,
            "terminationReason": "NO_TOOL_CALL",
        })
    return data


def shell_call(command):
    return {
        "args": {
            "CommandLine": command,
            "WaitMsBeforeAsync": 5000,
            "toolSummary": "Run the command",
        },
        "id": "call_10821273103548836363",
        "name": "run_command",
    }


def read_file_call(cwd):
    return {
        "args": {"Path": str(Path(cwd) / "notes.txt")},
        "id": "call_16381084659485823708",
        "name": "read_file",
    }


def load_script_module(name):
    spec = importlib.util.spec_from_file_location(
        Path(name).stem, SCRIPTS / name
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_hook_payload_module():
    return load_script_module("hook_payload.py")


class AntigravityHostAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temp_dir = tempfile.TemporaryDirectory()
        cls.addClassCleanup(temp_dir.cleanup)
        cls.class_temp = Path(temp_dir.name).resolve()
        cls.uv_cache = cls.class_temp / "uv-cache"
        # A relocated copy shows that the hooks need no repository path, and
        # keeps a stray log out of the checkout.
        cls.plugin_root = cls.class_temp / "core-hooks"
        shutil.copytree(
            SCRIPTS,
            cls.plugin_root / "scripts",
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        shutil.copy2(HOOKS_PATH, cls.plugin_root / "hooks.json")

    def setUp(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.temp = Path(temp_dir.name).resolve()
        self.project = self.temp / "project"
        self.project.mkdir()

    def run_hook(self, command, data, *, plugin_root=None, env=None, shell="/bin/sh"):
        """Run one configured command as Antigravity does: through a shell,
        from the plugin root, with the payload on stdin. A string payload
        goes to stdin as it is."""
        plugin_root = plugin_root or self.plugin_root
        process_env = os.environ.copy()
        process_env.pop("CLAUDE_PROJECT_DIR", None)
        process_env.update({
            "PLUGIN_ROOT": str(plugin_root),
            "ANTIGRAVITY_CONVERSATION_ID": CONVERSATION_ID,
            "UV_CACHE_DIR": str(self.uv_cache),
            # zsh_traps.py checks a command only when the user's shell is zsh.
            "SHELL": ZSH,
            # Stop Git from finding a repository that contains the temp directory.
            "GIT_CEILING_DIRECTORIES": str(self.temp),
        })
        process_env.update(env or {})
        result = subprocess.run(
            [shell, "-c", command],
            input=data if isinstance(data, str) else json.dumps(data),
            text=True,
            capture_output=True,
            cwd=plugin_root,
            env=process_env,
            check=False,
            timeout=60,
        )
        # An allow decision skips the Antigravity permission checks.
        self.assertNotIn("allow", result.stdout)
        return result

    def run_shell_hook(self, script_name, command, **kwargs):
        return self.run_hook(
            command_for(script_name),
            payload("PreToolUse", self.project, shell_call(command)),
            **kwargs,
        )

    def plugin_copy(self, name, script_exit=None):
        """Return a plugin root with only hooks.json, or with each script
        replaced by one that exits with `script_exit`."""
        plugin_root = self.temp / name
        scripts = plugin_root / "scripts"
        scripts.mkdir(parents=True)
        shutil.copy2(HOOKS_PATH, plugin_root / "hooks.json")
        if script_exit is not None:
            failing_script = (
                "# /// script\n"
                '# requires-python = ">=3.8"\n'
                "# ///\n"
                "import sys\n"
                f"sys.exit({script_exit})\n"
            )
            for script_name, _, _ in POLICY_CASES:
                (scripts / script_name).write_text(failing_script)
        return plugin_root

    def test_root_hooks_json_runs_each_shared_script_in_antigravity_mode(self):
        config = load_hook_config()
        self.assertEqual(list(config), ["core-hooks"])
        self.assertEqual(
            sorted(config["core-hooks"]), ["PostToolUse", "PreToolUse", "Stop"]
        )
        hooks = list(configured_hooks())
        scripts = {name for name, _, _ in POLICY_CASES}
        self.assertEqual(
            {name for name in scripts for _, _, command in hooks if name in command},
            scripts,
        )
        for event, matcher, command in hooks:
            with self.subTest(command=command):
                self.assertIn("--host antigravity", command)
                self.assertRegex(command, r'^uv run --no-project "scripts/\w+\.py"')
                self.assertNotIn("PLUGIN_ROOT", command)
                # zsh reserves `status`, so the wrappers use another name.
                self.assertNotIn("status=", command)
        safety_matcher = next(
            matcher for _, matcher, command in hooks if "safety_guard.py" in command
        )
        self.assertEqual(
            safety_matcher.split("|"), ["run_command", *FILE_TOOLS]
        )
        for script_name in ("pre_git_hook.py", "zsh_traps.py"):
            with self.subTest(script_name=script_name):
                matcher = next(
                    matcher for _, matcher, command in hooks if script_name in command
                )
                self.assertEqual(matcher, "run_command")

    def test_shell_command_payload_is_read_with_type_guards(self):
        hook_payload = load_hook_payload_module()
        self.assertEqual(
            hook_payload.get_shell_command(payload("PreToolUse", "/", shell_call("ls"))),
            "ls",
        )
        for tool_call in (
            None,
            [],
            {"name": "run_command", "args": None},
            {"name": "run_command", "args": ["ls"]},
            {"name": "run_command", "args": {"CommandLine": 42}},
            {"name": "run_command", "args": {"Command": "ls"}},
            {"name": "read_file", "args": {"CommandLine": "ls"}},
            {"name": ["run_command"], "args": {"CommandLine": "ls"}},
        ):
            with self.subTest(tool_call=tool_call):
                data = payload("PreToolUse", "/")
                data["toolCall"] = tool_call
                self.assertEqual(hook_payload.get_shell_command(data), "")

    def test_policy_violations_block_with_a_reason_and_no_stdout(self):
        cases = (
            ("safety_guard.py", "rm -rf ~", "Reason: home directory target"),
            ("safety_guard.py", "env", "env | cut -d= -f1"),
            ("safety_guard.py", "export -p", "env | cut -d= -f1"),
            ("pre_git_hook.py", "git add .", "Use specific file names"),
            ("pre_git_hook.py", "git checkout -b wip", "Branch name 'wip' is invalid"),
            ("pre_git_hook.py", "git add -- .", "Use specific file names"),
            ("pre_git_hook.py", "gh pr merge 1 --squash", "--match-head-commit"),
            (
                "pre_git_hook.py",
                'gh issue create --title x --body "Generated with Claude Code"',
                "AI tool attribution detected",
            ),
            ("pre_git_hook.py", 'gh pr edit 1 --body "## Test plan"', "Test plan"),
            ("zsh_traps.py", "echo =====CODEX", "echo '=====CODEX'"),
            ("zsh_traps.py", "echo ok; echo =====", "echo ok; echo '====='"),
            ("zsh_traps.py", "echo ok; echo ===== | cat", "Run it as it is:\necho ok; echo \\===== | cat"),
        )
        for script_name, command, reason in cases:
            with self.subTest(command=command):
                result = self.run_shell_hook(script_name, command)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(result.stdout, "")
                self.assertIn(reason, result.stderr)
                self.assertNotIn("hook failed", result.stderr)

    def test_pipefail_and_bsd_option_warnings_do_not_block(self):
        # GNU head and cat accept these options, so the hook must not block them.
        for command in ("pytest -q | tail -20", "head -n 0 a.txt", "cat -A a.txt"):
            with self.subTest(command=command):
                result = self.run_shell_hook("zsh_traps.py", command)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr, "")

    def test_unmatched_glob_is_allowed_because_files_can_appear_first(self):
        result = self.run_shell_hook("zsh_traps.py", "touch a.md && ls *.md")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")

    def test_zsh_rewrite_names_the_corrected_command_as_the_fix(self):
        result = self.run_shell_hook("zsh_traps.py", "echo -n =====CODEX done")

        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("echo -n '=====CODEX' done", result.stderr)
        self.assertNotIn("WARNING", result.stderr)

    def test_plain_commands_and_file_tools_are_allowed_silently(self):
        for script_name in ("safety_guard.py", "pre_git_hook.py", "zsh_traps.py"):
            for command in ("echo hello", "echo ${(f)x}"):
                with self.subTest(script_name=script_name, command=command):
                    result = self.run_shell_hook(script_name, command)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout, "")
        (self.project / "notes.txt").write_text("rm -rf ~\n")
        result = self.run_hook(
            command_for("safety_guard.py"),
            payload("PreToolUse", self.project, read_file_call(self.project)),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")

    def test_git_reminders_have_no_channel_and_print_nothing(self):
        for command in (
            "gh pr merge 123 --match-head-commit 0123456789abcdef0123456789abcdef01234567",
            'git commit -m "Fix the typo"',
            "git checkout -b feat-430-antigravity",
        ):
            with self.subTest(command=command):
                result = self.run_shell_hook("pre_git_hook.py", command)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "")

    def test_logs_go_under_the_payload_cwd_not_the_plugin_or_claude_project(self):
        repo = self.project / "repo"
        subdir = repo / "src"
        subdir.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        plain = self.project / "plain"
        plain.mkdir()
        claude_project = self.temp / "claude-project"
        claude_project.mkdir()
        env = {"CLAUDE_PROJECT_DIR": str(claude_project)}
        for cwd, log_root in ((subdir, repo), (plain, plain)):
            pre = payload("PreToolUse", cwd, read_file_call(cwd))
            post = payload("PostToolUse", cwd, shell_call("pwd"))
            for script_name, data, log_name in (
                ("safety_guard.py", pre, "pre_tool_use.jsonl"),
                ("post_tool_use.py", post, "post_tool_use.jsonl"),
            ):
                with self.subTest(cwd=cwd.name, script_name=script_name):
                    result = self.run_hook(command_for(script_name), data, env=env)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout, "")
                    lines = (log_root / "logs" / log_name).read_text().splitlines()
                    self.assertEqual([json.loads(line) for line in lines], [data])
        self.assertFalse((subdir / "logs").exists())
        self.assertFalse((self.plugin_root / "logs").exists())
        self.assertFalse((claude_project / "logs").exists())

    def test_stop_notification_accepts_the_host_argument_and_prints_nothing(self):
        # A fake `chime` records the sound instead of playing it.
        fake = self.temp / "fake-chime"
        fake.mkdir()
        record = self.temp / "sounds.txt"
        (fake / "chime.py").write_text(
            "def theme(name):\n    pass\n\n"
            "def success(sync=False):\n"
            f"    open({str(record)!r}, 'a').write('success\\n')\n"
        )
        env = os.environ.copy()
        env["PYTHONPATH"] = str(fake)
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "system_notification.py"),
             "--success", "--host", "antigravity"],
            input=json.dumps(payload("Stop", self.project)),
            text=True,
            capture_output=True,
            env=env,
            check=False,
            timeout=60,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        if load_script_module("system_notification.py").has_audio_output():
            self.assertEqual(record.read_text(), "success\n")
        else:
            # A Linux host without a playback device, such as a CI runner,
            # plays no sound.
            self.assertFalse(record.exists())
        self.assertIn("--success --host antigravity", command_for("system_notification.py"))

    def test_script_failures_follow_each_hook_failure_policy(self):
        failures = (
            ("exit 1", {"plugin_root": self.plugin_copy("exit-1", script_exit=1)}),
            ("exit 2", {"plugin_root": self.plugin_copy("exit-2", script_exit=2)}),
            # uv exits 2 when it cannot start a missing script.
            ("missing script", {"plugin_root": self.plugin_copy("missing")}),
            ("no uv", {"env": {"PATH": ""}}),
        )
        data = payload("PreToolUse", self.project, shell_call("echo hello"))
        for shell in SHELLS:
            for failure, kwargs in failures:
                for script_name, expected_status, marker in POLICY_CASES:
                    with self.subTest(shell=shell, failure=failure, script_name=script_name):
                        result = self.run_hook(
                            command_for(script_name), data, shell=shell, **kwargs
                        )
                        self.assertEqual(result.returncode, expected_status, result.stderr)
                        self.assertEqual(result.stdout, "")
                        self.assertIn(marker, result.stderr)

    def test_unreadable_payload_blocks_the_safety_and_git_policy_hooks(self):
        for script_name, expected_status, marker in POLICY_CASES[:2]:
            with self.subTest(script_name=script_name):
                result = self.run_hook(command_for(script_name), "not json")
                self.assertEqual(result.returncode, expected_status, result.stderr)
                self.assertEqual(result.stdout, "")
                self.assertIn(marker, result.stderr)

    def test_blocks_pass_through_each_wrapper_without_a_failure_line(self):
        cases = (
            ("safety_guard.py", "rm -rf ~"),
            ("pre_git_hook.py", "git add ."),
            ("zsh_traps.py", "echo =====CODEX"),
        )
        for shell in SHELLS:
            for script_name, command in cases:
                with self.subTest(shell=shell, script_name=script_name):
                    result = self.run_shell_hook(script_name, command, shell=shell)
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertTrue(result.stderr.startswith("BLOCKED: "), result.stderr)
                    self.assertNotIn("hook failed", result.stderr)


if __name__ == "__main__":
    unittest.main()
