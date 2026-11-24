"""Check the SessionStart stale-install check."""

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
CODEX_HOOKS = ROOT / "hooks" / "hooks.codex.json"


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def write_marketplace(root, plugins, marketplace="cc-toolkit", string_source=False):
    """Write both marketplace registries and the manifests of `plugins`.

    `plugins` maps a plugin name to its Claude version, or to a pair of
    Claude and Codex versions. The Codex registry uses the object `source`
    form, or the string form when `string_source` is set.
    """
    write_json(root / ".claude-plugin" / "marketplace.json", {
        "name": marketplace,
        "plugins": [{"name": name, "source": "./" + name} for name in plugins],
    })
    write_json(root / ".agents" / "plugins" / "marketplace.json", {
        "name": marketplace,
        "plugins": [
            {"name": name, "source": "./" + name if string_source
             else {"source": "local", "path": "./" + name}}
            for name in plugins
        ],
    })
    for name, versions in plugins.items():
        claude, codex = versions if isinstance(versions, tuple) else (versions, None)
        write_json(root / name / ".claude-plugin" / "plugin.json",
                   {"name": name, "version": claude})
        if codex:
            write_json(root / name / ".codex-plugin" / "plugin.json",
                       {"name": name, "version": codex})


def configured_command(path):
    """Return the SessionStart command of the check in a hook file."""
    config = json.loads(path.read_text())
    return next(
        hook["command"]
        for entry in config["hooks"].get("SessionStart", [])
        for hook in entry["hooks"]
        if "stale_install_check.py" in hook["command"]
    )


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
        # A T3 Code session sets these; never read the real plugin folders.
        for name in ("CORE_HOOKS_STALE_CHECK", "CLAUDE_CODE_PLUGIN_CACHE_DIR"):
            self.env.pop(name, None)
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
        write_marketplace(self.repo, plugins, marketplace)

    def make_repo(self, plugins, marketplace="cc-toolkit"):
        """Commit the manifests and point origin/master at the commit."""
        self.git("init", "-q")
        self.write_manifests(plugins, marketplace)
        self.git("add", ".")
        self.git("commit", "-q", "-m", "manifests")
        self.git("update-ref", "refs/remotes/origin/master", "HEAD")

    def install_claude(self, plugin_folder, installs):
        """Write installed_plugins.json with (plugin, version, scope) items."""
        write_json(plugin_folder / "installed_plugins.json", {
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

    def install_codex(self, home, plugin, *versions):
        """Make the version folders of a plugin in a Codex plugin cache."""
        for version in versions:
            (home / "plugins" / "cache" / "cc-toolkit" / plugin / version).mkdir(parents=True)

    def codex_clone(self, home, plugins, string_source=False):
        write_marketplace(home / ".tmp" / "marketplaces" / "cc-toolkit", plugins,
                          string_source=string_source)

    def link_shadow_home(self, name, real_home, links):
        """Make ~/.codex-t3/<name> with links to the named items of real_home."""
        shadow = self.home / ".codex-t3" / name
        shadow.mkdir(parents=True)
        for item in links:
            (shadow / item).symlink_to(real_home / item)
        return shadow

    def run_check(self, command=None):
        payload = json.dumps({"hook_event_name": "SessionStart", "cwd": str(self.repo)})
        args = ["/bin/sh", "-c", command] if command else [sys.executable, str(SCRIPT)]
        result = subprocess.run(
            args, input=payload, env=self.env, cwd=str(self.tmp),
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def report(self, command=None):
        """Run the check and return the additional context it prints."""
        output = json.loads(self.run_check(command))
        hook_output = output["hookSpecificOutput"]
        self.assertEqual(hook_output["hookEventName"], "SessionStart")
        return hook_output["additionalContext"]

    def test_reports_stale_claude_plugins_with_update_commands(self):
        self.env["CORE_HOOKS_STALE_CHECK"] = "1"
        self.make_repo({"core-hooks": "1.0.27", "dev-skills": "3.52.0"})
        self.install_claude(self.claude_config / "plugins", [("core-hooks", "1.0.26", "project")])
        self.install_claude(self.home / ".claude" / "plugins", [("dev-skills", "3.9.0", "user")])

        context = self.report()

        self.assertIn("core-hooks", context)
        self.assertIn("1.0.26", context)
        self.assertIn("1.0.27", context)
        self.assertIn("claude plugin marketplace update cc-toolkit", context)
        self.assertIn("claude plugin update core-hooks@cc-toolkit --scope project", context)
        self.assertIn("claude plugin update dev-skills@cc-toolkit --scope user", context)

    def test_ignores_current_plugins(self):
        self.env["CORE_HOOKS_STALE_CHECK"] = "1"
        self.make_repo({"core-hooks": "1.0.27", "dev-skills": "1.9.0"})
        # 1.10.0 is greater than 1.9.0 as numbers, but not as text.
        self.install_claude(self.home / ".claude" / "plugins", [
            ("core-hooks", "1.0.27", "user"), ("dev-skills", "1.10.0", "user"),
        ])

        self.assertEqual(self.run_check(), "")

    def test_reports_stale_install_outside_a_checkout(self):
        plugins = self.home / ".claude" / "plugins"
        self.install_claude(plugins, [("dev-skills", "3.68.0", "user")])
        write_marketplace(plugins / "marketplaces" / "cc-toolkit",
                          {"dev-skills": ("3.72.0", "1.59.0")})
        default_home = self.home / ".codex"
        self.install_codex(default_home, "dev-skills", "1.55.0")
        self.codex_clone(default_home, {"dev-skills": ("3.72.0", "1.59.0")})

        context = self.report()

        self.assertIn("Stale installs", context)
        self.assertIn("dev-skills (Claude Code, scope user): installed copy 3.68.0, "
                      "marketplace clone 3.72.0.", context)
        self.assertIn("dev-skills (Codex, home {}): installed copy 1.55.0, "
                      "marketplace clone 1.59.0.".format(default_home), context)
        self.assertNotIn("default branch", context)
        self.assertIn("claude plugin update dev-skills@cc-toolkit --scope user", context)
        # ~/.codex gets bare commands.
        self.assertIn("\ncodex plugin marketplace upgrade cc-toolkit\n"
                      "codex plugin add dev-skills@cc-toolkit", context)
        self.assertIn("a running Codex session must restart", context)

    def test_reads_the_claude_plugin_cache_dir(self):
        # T3 Code shares one plugin folder through this variable.
        self.env["CLAUDE_CODE_PLUGIN_CACHE_DIR"] = "~/shared-plugins"
        plugins = self.home / "shared-plugins"
        self.install_claude(plugins, [("core-hooks", "1.0.1", "user")])
        write_marketplace(plugins / "marketplaces" / "cc-toolkit", {"core-hooks": "1.0.2"})

        context = self.report()

        self.assertIn("core-hooks (Claude Code, scope user): installed copy 1.0.1, "
                      "marketplace clone 1.0.2.", context)

    def test_reports_stale_codex_cache(self):
        cache = self.codex_home / "plugins" / "cache" / "cc-toolkit" / "core-hooks"
        for folder in ("1.0.9", "1.0.10", "not-a-version"):
            (cache / folder).mkdir(parents=True)
        # The object `source` form of the Codex registry.
        self.codex_clone(self.codex_home, {"core-hooks": ("1.0.27", "1.0.11")})

        context = self.report()

        self.assertIn("installed copy 1.0.10, marketplace clone 1.0.11", context)
        prefix = "CODEX_HOME={} ".format(self.codex_home)
        self.assertIn(prefix + "codex plugin marketplace upgrade cc-toolkit", context)
        self.assertIn(prefix + "codex plugin add core-hooks@cc-toolkit", context)

    def test_reads_the_string_source_form(self):
        self.install_codex(self.codex_home, "core-hooks", "1.0.1")
        self.codex_clone(self.codex_home, {"core-hooks": ("1.0.27", "1.0.2")},
                         string_source=True)

        self.assertIn("installed copy 1.0.1, marketplace clone 1.0.2", self.report())

    def test_linked_shadow_home_gives_one_command_set(self):
        del self.env["CODEX_HOME"]
        real_home = self.home / ".codex"
        self.install_codex(real_home, "core-hooks", "1.0.1")
        self.codex_clone(real_home, {"core-hooks": ("1.0.27", "1.0.2")})
        (real_home / "config.toml").write_text("")
        self.link_shadow_home("codex-2", real_home, ("plugins", "config.toml", ".tmp"))

        context = self.report()

        self.assertEqual(context.count("codex plugin add core-hooks@cc-toolkit"), 1)
        self.assertEqual(context.count("codex plugin marketplace upgrade"), 1)
        self.assertNotIn("CODEX_HOME=", context)
        self.assertIn("(Codex, home {})".format(real_home), context)
        self.assertNotIn("codex-2", context)

    def test_partly_linked_home_gets_its_own_command_set(self):
        del self.env["CODEX_HOME"]
        real_home = self.home / ".codex"
        self.install_codex(real_home, "core-hooks", "1.0.1")
        self.codex_clone(real_home, {"core-hooks": ("1.0.27", "1.0.2")})
        partial = self.link_shadow_home("codex-3", real_home, ("plugins",))
        self.codex_clone(partial, {"core-hooks": ("1.0.27", "1.0.3")})

        context = self.report()

        self.assertIn("\ncodex plugin add core-hooks@cc-toolkit", context)
        self.assertIn("CODEX_HOME={} codex plugin add core-hooks@cc-toolkit".format(partial),
                      context)
        self.assertIn("installed copy 1.0.1, marketplace clone 1.0.3", context)

    def test_broken_link_or_link_loop_keeps_the_other_homes(self):
        shadows = self.home / ".codex-t3"
        shadows.mkdir()
        (shadows / "a-broken").symlink_to(self.tmp / "missing")
        (shadows / "b-loop").symlink_to(shadows / "b-loop")
        loop_plugins = shadows / "c-loop-plugins"
        loop_plugins.mkdir()
        (loop_plugins / "plugins").symlink_to(loop_plugins / "plugins")
        # CODEX_HOME comes first; a link loop there must not stop the check.
        self.env["CODEX_HOME"] = str(shadows / "b-loop")
        good = shadows / "d-good"
        self.install_codex(good, "core-hooks", "1.0.1")
        self.codex_clone(good, {"core-hooks": ("1.0.27", "1.0.2")})

        context = self.report()

        self.assertIn("CODEX_HOME={} codex plugin add core-hooks@cc-toolkit".format(good),
                      context)
        self.assertEqual(context.count("codex plugin add core-hooks@cc-toolkit"), 1)

    def test_home_without_clone_reports_nothing(self):
        self.install_codex(self.codex_home, "core-hooks", "1.0.1")
        self.install_claude(self.home / ".claude" / "plugins", [("core-hooks", "1.0.1", "user")])

        self.assertEqual(self.run_check(), "")

    def test_zero_turns_the_check_off(self):
        self.install_codex(self.codex_home, "core-hooks", "1.0.1")
        self.codex_clone(self.codex_home, {"core-hooks": ("1.0.27", "1.0.2")})
        self.assertIn("marketplace clone 1.0.2", self.report())

        self.env["CORE_HOOKS_STALE_CHECK"] = "0"

        self.assertEqual(self.run_check(), "")

    def test_one_adds_the_default_branch_comparison(self):
        self.make_repo({"core-hooks": ("1.0.27", "1.0.12")})
        self.install_claude(self.home / ".claude" / "plugins", [("core-hooks", "1.0.26", "user")])
        self.install_codex(self.codex_home, "core-hooks", "1.0.11")
        # The clone is not newer, so only the default branch is.
        self.codex_clone(self.codex_home, {"core-hooks": ("1.0.26", "1.0.11")})
        self.assertEqual(self.run_check(), "")

        self.env["CORE_HOOKS_STALE_CHECK"] = "1"
        context = self.report()

        self.assertIn("default branch of this checkout (origin/master)", context)
        self.assertIn("core-hooks (Claude Code, scope user): installed copy 1.0.26, "
                      "default branch 1.0.27.", context)
        self.assertIn("installed copy 1.0.11, default branch 1.0.12.", context)
        self.assertNotIn("Stale installs", context)
        self.assertIn("claude plugin update core-hooks@cc-toolkit --scope user", context)
        self.assertIn("CODEX_HOME={} codex plugin add core-hooks@cc-toolkit".format(
            self.codex_home), context)

    def test_reference_comes_from_origin_master(self):
        self.env["CORE_HOOKS_STALE_CHECK"] = "1"
        self.make_repo({"core-hooks": "1.0.2"})
        # An unreleased version increase on a feature branch.
        self.write_manifests({"core-hooks": "1.0.3"})
        self.install_claude(self.home / ".claude" / "plugins", [("core-hooks", "1.0.1", "user")])

        context = self.report()

        self.assertIn("1.0.2", context)
        self.assertNotIn("1.0.3", context)

    def test_non_cc_toolkit_repo_prints_nothing(self):
        # Even with the opt-in, another repository is no default branch.
        self.env["CORE_HOOKS_STALE_CHECK"] = "1"
        self.make_repo({"core-hooks": ("1.0.27", "1.0.27")}, marketplace="other")
        self.install_claude(self.home / ".claude" / "plugins", [("core-hooks", "1.0.1", "user")])
        self.install_codex(self.codex_home, "core-hooks", "1.0.1")

        self.assertEqual(self.run_check(), "")

    def test_configured_hooks_run_without_opt_in(self):
        # Each host runs the check at SessionStart, and the variable is unset.
        self.install_codex(self.codex_home, "core-hooks", "1.0.1")
        self.codex_clone(self.codex_home, {"core-hooks": ("1.0.27", "1.0.2")})
        self.env["UV_CACHE_DIR"] = str(self.tmp / "uv-cache")
        for path, variable in ((CLAUDE_HOOKS, "CLAUDE_PLUGIN_ROOT"),
                               (CODEX_HOOKS, "PLUGIN_ROOT")):
            with self.subTest(hooks=path.name):
                command = configured_command(path)
                self.env[variable] = str(ROOT)

                self.assertIn("marketplace clone 1.0.2", self.report(command))


if __name__ == "__main__":
    unittest.main()
