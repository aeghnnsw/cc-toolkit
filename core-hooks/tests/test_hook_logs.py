import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
LOGGING_HOOKS = (
    ("post_tool_use.py", "post_tool_use.json"),
    ("safety_guard.py", "pre_tool_use.json"),
)
PAYLOAD = {
    "hook_event_name": "PreToolUse",
    "tool_name": "Bash",
    "tool_input": {"command": "pwd"},
}


class HookLogDirectoryTests(unittest.TestCase):
    def setUp(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.temp = Path(temp_dir.name).resolve()

    def run_hook(self, script_name, cwd, project_dir=None):
        env = os.environ.copy()
        env.pop("CLAUDE_PROJECT_DIR", None)
        # Stop Git from finding a repository that contains the temp directory.
        env["GIT_CEILING_DIRECTORIES"] = str(self.temp)
        if project_dir is not None:
            env["CLAUDE_PROJECT_DIR"] = str(project_dir)
        return subprocess.run(
            [sys.executable, str(SCRIPTS / script_name)],
            input=json.dumps(PAYLOAD),
            text=True,
            capture_output=True,
            cwd=cwd,
            env=env,
            check=False,
        )

    def make_repo(self):
        repo = self.temp / "repo"
        subdir = repo / "plugin" / "skills"
        subdir.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        return repo, subdir

    def assert_logs_in(self, root, cwd, project_dir=None):
        for script_name, log_name in LOGGING_HOOKS:
            with self.subTest(script_name=script_name):
                result = self.run_hook(script_name, cwd, project_dir)
                self.assertEqual(result.returncode, 0, result.stderr)
                log_path = root / "logs" / log_name
                self.assertEqual(json.loads(log_path.read_text()), [PAYLOAD])
        if cwd != root:
            self.assertFalse((cwd / "logs").exists())

    def test_claude_project_dir_holds_logs_from_a_subdirectory(self):
        project = self.temp / "project"
        subdir = project / "plugin" / "skills"
        subdir.mkdir(parents=True)

        self.assert_logs_in(project, subdir, project_dir=project)

    def test_git_top_level_holds_logs_without_a_project_dir(self):
        repo, subdir = self.make_repo()

        self.assert_logs_in(repo, subdir)

    def test_git_top_level_holds_logs_when_the_project_dir_is_missing(self):
        repo, subdir = self.make_repo()
        missing = self.temp / "missing"

        self.assert_logs_in(repo, subdir, project_dir=missing)
        self.assertFalse(missing.exists())

    def test_working_directory_holds_logs_outside_a_git_repository(self):
        workdir = self.temp / "workdir"
        workdir.mkdir()

        self.assert_logs_in(workdir, workdir)


if __name__ == "__main__":
    unittest.main()
