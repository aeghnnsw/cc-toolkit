"""Check the opt-in SessionStart stale-install check."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "stale_install_check.py"
CLAUDE_HOOKS = ROOT / "hooks" / "hooks.json"


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


class StaleInstallCheckTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.tmp = Path(temp.name).resolve()
        self.home = self.tmp / "home"
        self.claude_config = self.tmp / "claude-config"
        self.codex_home = self.tmp / "codex"
        self.repo = self.tmp / "repo"
        for folder in (self.home, self.claude_config, self.codex_home, self.repo):
            folder.mkdir()
        self.env = dict(os.environ)
        self.env.pop("CORE_HOOKS_STALE_CHECK", None)
        self.env.update(
            HOME=str(self.home),
            CLAUDE_CONFIG_DIR=str(self.claude_config),
            CODEX_HOME=str(self.codex_home),
            GIT_CEILING_DIRECTORIES=str(self.tmp),
            GIT_CONFIG_GLOBAL=os.devnull,
            GIT_CONFIG_NOSYSTEM="1",
            GIT_AUTHOR_NAME="Test",
            GIT_AUTHOR_EMAIL="test@example.com",
            GIT_COMMITTER_NAME="Test",
            GIT_COMMITTER_EMAIL="test@example.com",
        )

    def git(self, *args):
        subprocess.run(
            ["git", "-C", str(self.repo)] + list(args),
            env=self.env, check=True, capture_output=True,
        )

    def write_manifests(self, plugins, marketplace="cc-toolkit"):
        """Write a marketplace and the manifests of `plugins` in the repo.

        `plugins` maps a plugin name to its Claude version, or to a pair of
        Claude and Codex versions.
        """
        write_json(self.repo / ".claude-plugin" / "marketplace.json", {
            "name": marketplace,
            "plugins": [
                {"name": name, "source": "./" + name} for name in plugins
            ],
        })
        for name, versions in plugins.items():
            claude, codex = versions if isinstance(versions, tuple) else (versions, None)
            write_json(self.repo / name / ".claude-plugin" / "plugin.json",
                       {"name": name, "version": claude})
            if codex:
                write_json(self.repo / name / ".codex-plugin" / "plugin.json",
                           {"name": name, "version": codex})

    def make_repo(self, plugins, marketplace="cc-toolkit"):
        """Commit the manifests and point origin/master at the commit."""
        self.git("init", "-q")
        self.write_manifests(plugins, marketplace)
        self.git("add", ".")
        self.git("commit", "-q", "-m", "manifests")
        self.git("update-ref", "refs/remotes/origin/master", "HEAD")

    def install_claude(self, config_root, installs):
        """Write installed_plugins.json with (plugin, version, scope) items."""
        write_json(config_root / "plugins" / "installed_plugins.json", {
            "version": 2,
            "plugins": {
                name + "@cc-toolkit": [{
                    "scope": scope,
                    "installPath": str(self.tmp / "install" / name),
                    "version": version,
                }]
                for name, version, scope in installs
            },
        })

    def run_check(self, command=None):
        payload = json.dumps({"hook_event_name": "SessionStart", "cwd": str(self.repo)})
        args = ["/bin/sh", "-c", command] if command else [sys.executable, str(SCRIPT)]
        result = subprocess.run(
            args, input=payload, env=self.env, cwd=str(self.tmp),
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def report(self):
        """Run the check and return the additional context it prints."""
        output = json.loads(self.run_check())
        hook_output = output["hookSpecificOutput"]
        self.assertEqual(hook_output["hookEventName"], "SessionStart")
        return hook_output["additionalContext"]

    def test_reports_stale_claude_plugins_with_update_commands(self):
        self.make_repo({"core-hooks": "1.0.27", "dev-skills": "3.52.0"})
        self.install_claude(self.claude_config, [("core-hooks", "1.0.26", "project")])
        self.install_claude(self.home / ".claude", [("dev-skills", "3.9.0", "user")])

        context = self.report()

        self.assertIn("core-hooks", context)
        self.assertIn("1.0.26", context)
        self.assertIn("1.0.27", context)
        self.assertIn("claude plugin marketplace update cc-toolkit", context)
        self.assertIn("claude plugin update core-hooks@cc-toolkit --scope project", context)
        self.assertIn("claude plugin update dev-skills@cc-toolkit --scope user", context)

    def test_ignores_current_plugins(self):
        self.make_repo({"core-hooks": "1.0.27", "dev-skills": "1.9.0"})
        # 1.10.0 is greater than 1.9.0 as numbers, but not as text.
        self.install_claude(self.home / ".claude", [
            ("core-hooks", "1.0.27", "user"), ("dev-skills", "1.10.0", "user"),
        ])

        self.assertEqual(self.run_check(), "")

    def test_reports_stale_codex_cache(self):
        self.make_repo({"core-hooks": ("1.0.27", "1.0.11")})
        cache = self.codex_home / "plugins" / "cache" / "cc-toolkit" / "core-hooks"
        for folder in ("1.0.9", "1.0.10", "not-a-version"):
            (cache / folder).mkdir(parents=True)

        context = self.report()

        self.assertIn("installed 1.0.10", context)
        self.assertIn("1.0.11", context)
        self.assertIn("codex plugin marketplace upgrade cc-toolkit", context)
        self.assertIn("codex plugin add core-hooks@cc-toolkit", context)

    def test_reference_comes_from_origin_master(self):
        self.make_repo({"core-hooks": "1.0.2"})
        # An unreleased version increase on a feature branch.
        self.write_manifests({"core-hooks": "1.0.3"})
        self.install_claude(self.home / ".claude", [("core-hooks", "1.0.1", "user")])

        context = self.report()

        self.assertIn("1.0.2", context)
        self.assertNotIn("1.0.3", context)

    def test_non_cc_toolkit_repo_prints_nothing(self):
        self.make_repo({"core-hooks": "1.0.27"}, marketplace="other")
        self.install_claude(self.home / ".claude", [("core-hooks", "1.0.1", "user")])

        self.assertEqual(self.run_check(), "")

    def test_configured_hook_skips_without_opt_in(self):
        self.make_repo({"core-hooks": "1.0.27"})
        self.install_claude(self.home / ".claude", [("core-hooks", "1.0.1", "user")])
        config = json.loads(CLAUDE_HOOKS.read_text())
        command = next(
            hook["command"]
            for entry in config["hooks"]["SessionStart"]
            for hook in entry["hooks"]
            if "stale_install_check.py" in hook["command"]
        )
        self.env["CLAUDE_PLUGIN_ROOT"] = str(ROOT)

        self.assertEqual(self.run_check(command), "")


if __name__ == "__main__":
    unittest.main()
