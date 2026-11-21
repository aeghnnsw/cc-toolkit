"""Command-line checks for the skill resolver script."""

from __future__ import annotations

import getpass
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PLUGIN_ROOT / "scripts" / "resolve_skill.py"


def write(path: Path, text: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def make_skill(root: Path, relative: str) -> Path:
    return write(root / relative / "SKILL.md", "---\nname: x\n---\n").resolve()


class ResolverCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.claude_home = self.tmp / "claude"
        self.codex_home = self.tmp / "codex"
        self.home = self.tmp / "home"
        self.workdir = self.tmp / "work"
        self.workdir.mkdir()

    def run_resolver(
        self, *args: str, cwd: Path | None = None, extra_env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess:
        # A T3 Code session sets CLAUDE_CODE_PLUGIN_CACHE_DIR; never read the real plugin folder.
        inherited = {k: v for k, v in os.environ.items() if k != "CLAUDE_CODE_PLUGIN_CACHE_DIR"}
        # HOME keeps the Antigravity lookup away from the real ~/.gemini.
        env = {
            **inherited,
            "CLAUDE_CONFIG_DIR": str(self.claude_home),
            "CODEX_HOME": str(self.codex_home),
            "HOME": str(self.home),
            **(extra_env or {}),
        }
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            capture_output=True,
            text=True,
            cwd=str(cwd or self.workdir),
            env=env,
        )

    # Claude Code fixtures

    def claude_plugin(
        self,
        name: str,
        records: list[dict],
        *,
        enabled: bool | None = True,
        market: str = "market",
        plugins_dir: Path | None = None,
    ) -> None:
        registry = (plugins_dir or self.claude_home / "plugins") / "installed_plugins.json"
        data = json.loads(registry.read_text()) if registry.exists() else {"version": 2, "plugins": {}}
        data["plugins"][f"{name}@{market}"] = records
        write(registry, json.dumps(data))
        settings = self.claude_home / "settings.json"
        current = json.loads(settings.read_text()) if settings.exists() else {"enabledPlugins": {}}
        if enabled is not None:
            current["enabledPlugins"][f"{name}@{market}"] = enabled
        write(settings, json.dumps(current))

    def install_root(self, label: str, manifest: dict | None = None) -> Path:
        root = self.tmp / "installs" / label
        write(root / ".claude-plugin" / "plugin.json", json.dumps(manifest or {"name": label}))
        return root

    # Codex fixtures

    def codex_config(self, text: str) -> None:
        write(self.codex_home / "config.toml", text)

    def codex_install(self, plugin: str, version: str, skill: str) -> Path:
        root = self.codex_home / "plugins" / "cache" / "market" / plugin / version
        write(root / ".codex-plugin" / "plugin.json", json.dumps({"name": plugin}))
        return make_skill(root, f"skills/engineering/{skill}")


class ClaudeResolveTest(ResolverCase):
    def test_manifest_skill_resolves_to_its_path(self):
        root = self.install_root("matt", {"skills": ["./skills/engineering/to-spec"]})
        expected = make_skill(root, "skills/engineering/to-spec")
        self.claude_plugin("matt", [{"scope": "user", "installPath": str(root)}])

        completed = self.run_resolver("matt:to-spec")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, f"matt:to-spec {expected}\n")

    def test_several_names_print_in_the_order_given(self):
        root = self.install_root("matt", {"skills": ["./skills/engineering/to-spec", "./skills/engineering/retro"]})
        spec = make_skill(root, "skills/engineering/to-spec")
        retro = make_skill(root, "skills/engineering/retro")
        self.claude_plugin("matt", [{"scope": "user", "installPath": str(root)}])

        completed = self.run_resolver("matt:retro", "matt:to-spec")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, f"matt:retro {retro}\nmatt:to-spec {spec}\n")

    def test_skill_is_found_by_search_without_manifest_paths(self):
        root = self.install_root("tools")
        expected = make_skill(root, "extra/nested/helper")
        self.claude_plugin("tools", [{"scope": "user", "installPath": str(root)}])

        completed = self.run_resolver("tools:helper")

        self.assertEqual(completed.stdout, f"tools:helper {expected}\n")

    def test_claude_copy_wins_over_the_codex_copy(self):
        root = self.install_root("dev")
        make_skill(root, "codex-skills/pressure-test")
        expected = make_skill(root, "skills/pressure-test")
        self.claude_plugin("dev", [{"scope": "user", "installPath": str(root)}])

        completed = self.run_resolver("dev:pressure-test")

        self.assertEqual(completed.stdout, f"dev:pressure-test {expected}\n")

    def test_project_record_for_the_current_directory_wins(self):
        user_root = self.install_root("user-copy")
        make_skill(user_root, "skills/retro")
        project_root = self.install_root("project-copy")
        expected = make_skill(project_root, "skills/retro")
        project = self.tmp / "project"
        (project / "src").mkdir(parents=True)
        self.claude_plugin(
            "matt",
            [
                {"scope": "user", "installPath": str(user_root)},
                {"scope": "project", "projectPath": str(project), "installPath": str(project_root)},
            ],
        )

        completed = self.run_resolver("matt:retro", cwd=project / "src")

        self.assertEqual(completed.stdout, f"matt:retro {expected}\n")

    def test_user_record_applies_outside_the_project(self):
        user_root = self.install_root("user-copy")
        expected = make_skill(user_root, "skills/retro")
        project_root = self.install_root("project-copy")
        make_skill(project_root, "skills/retro")
        self.claude_plugin(
            "matt",
            [
                {"scope": "project", "projectPath": str(self.tmp / "elsewhere"), "installPath": str(project_root)},
                {"scope": "user", "installPath": str(user_root)},
            ],
        )

        completed = self.run_resolver("matt:retro")

        self.assertEqual(completed.stdout, f"matt:retro {expected}\n")

    def test_disabled_plugin_fails(self):
        root = self.install_root("matt")
        make_skill(root, "skills/retro")
        self.claude_plugin("matt", [{"scope": "user", "installPath": str(root)}], enabled=False)

        completed = self.run_resolver("matt:retro")

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(completed.stdout, "")
        self.assertIn("matt:retro", completed.stderr)
        self.assertIn("disabled", completed.stderr)

    def test_plugin_missing_from_settings_counts_as_enabled(self):
        root = self.install_root("matt")
        expected = make_skill(root, "skills/retro")
        self.claude_plugin("matt", [{"scope": "user", "installPath": str(root)}], enabled=None)

        self.assertEqual(self.run_resolver("matt:retro").stdout, f"matt:retro {expected}\n")

    def test_missing_plugin_fails_and_other_names_still_print(self):
        root = self.install_root("matt")
        expected = make_skill(root, "skills/retro")
        self.claude_plugin("matt", [{"scope": "user", "installPath": str(root)}])

        completed = self.run_resolver("matt:retro", "other:retro")

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(completed.stdout, f"matt:retro {expected}\n")
        self.assertIn("other:retro", completed.stderr)
        self.assertIn("not installed", completed.stderr)

    def test_missing_skill_fails(self):
        root = self.install_root("matt")
        make_skill(root, "skills/retro")
        self.claude_plugin("matt", [{"scope": "user", "installPath": str(root)}])

        completed = self.run_resolver("matt:to-spec")

        self.assertEqual(completed.returncode, 1)
        self.assertIn("not found", completed.stderr)

    def test_manifest_path_wins_over_the_search(self):
        root = self.install_root("matt", {"skills": ["./engineering/retro"]})
        make_skill(root, "aaa/retro")
        expected = make_skill(root, "engineering/retro")
        self.claude_plugin("matt", [{"scope": "user", "installPath": str(root)}])

        self.assertEqual(self.run_resolver("matt:retro").stdout, f"matt:retro {expected}\n")

    def test_manifest_paths_add_to_the_skills_dir(self):
        root = self.install_root("matt", {"skills": ["./engineering/retro"]})
        make_skill(root, "engineering/retro")
        expected = make_skill(root, "skills/to-spec")
        make_skill(root, "extra/helper")
        self.claude_plugin("matt", [{"scope": "user", "installPath": str(root)}])

        completed = self.run_resolver("matt:to-spec", "matt:helper")

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(completed.stdout, f"matt:to-spec {expected}\n")
        self.assertIn("matt:helper", completed.stderr)
        self.assertIn("not found", completed.stderr)

    def test_search_skips_the_codex_copy(self):
        root = self.install_root("dev")
        make_skill(root, "codex-skills/helper")
        self.claude_plugin("dev", [{"scope": "user", "installPath": str(root)}])

        completed = self.run_resolver("dev:helper")

        self.assertEqual(completed.returncode, 1)
        self.assertIn("not found", completed.stderr)

    def test_record_for_another_project_is_not_used(self):
        root = self.install_root("matt")
        make_skill(root, "skills/retro")
        self.claude_plugin(
            "matt", [{"scope": "project", "projectPath": str(self.tmp / "elsewhere"), "installPath": str(root)}]
        )

        completed = self.run_resolver("matt:retro")

        self.assertEqual(completed.returncode, 1)
        self.assertIn("not installed", completed.stderr)

    def test_enabled_marketplace_wins_over_a_disabled_one(self):
        old = self.install_root("old")
        make_skill(old, "skills/retro")
        new = self.install_root("new")
        expected = make_skill(new, "skills/retro")
        self.claude_plugin("matt", [{"scope": "user", "installPath": str(old)}], enabled=False, market="a")
        self.claude_plugin("matt", [{"scope": "user", "installPath": str(new)}], market="b")

        self.assertEqual(self.run_resolver("matt:retro").stdout, f"matt:retro {expected}\n")

    def test_unreadable_settings_fail(self):
        root = self.install_root("matt")
        make_skill(root, "skills/retro")
        self.claude_plugin("matt", [{"scope": "user", "installPath": str(root)}])
        for text in ("{", '{"enabledPlugins": []}'):
            with self.subTest(text=text):
                write(self.claude_home / "settings.json", text)

                completed = self.run_resolver("matt:retro")

                self.assertEqual(completed.returncode, 1)
                self.assertIn("settings", completed.stderr)
                self.assertNotIn("Traceback", completed.stderr)

    def test_registry_with_the_wrong_shape_fails(self):
        for data in ({"plugins": []}, {"plugins": {"matt@market": {"installPath": "x"}}}):
            with self.subTest(data=data):
                write(self.claude_home / "plugins" / "installed_plugins.json", json.dumps(data))

                completed = self.run_resolver("matt:retro")

                self.assertEqual(completed.returncode, 1)
                self.assertIn("registry", completed.stderr)
                self.assertNotIn("Traceback", completed.stderr)

    def test_install_record_with_a_wrong_type_fails(self):
        root = self.install_root("matt")
        expected = make_skill(root, "skills/retro")
        self.claude_plugin("matt", [{"scope": "user", "installPath": str(root)}])
        for record in ({"scope": "user", "installPath": 5}, {"scope": "project", "projectPath": 7, "installPath": "x"}):
            with self.subTest(record=record):
                self.claude_plugin("bad", [record])

                completed = self.run_resolver("bad:retro", "matt:retro")

                self.assertEqual(completed.returncode, 1)
                self.assertEqual(completed.stdout, f"matt:retro {expected}\n")
                self.assertIn("bad:retro", completed.stderr)
                self.assertNotIn("Traceback", completed.stderr)

    def test_missing_registry_fails(self):
        completed = self.run_resolver("matt:retro")

        self.assertEqual(completed.returncode, 1)
        self.assertIn("registry", completed.stderr)


class PluginCacheDirTest(ResolverCase):
    """CLAUDE_CODE_PLUGIN_CACHE_DIR names the folder of the plugin registry, as in a T3 Code session."""

    def test_registry_in_the_plugin_cache_dir_is_used(self):
        root = self.install_root("matt")
        expected = make_skill(root, "skills/retro")
        shared = self.tmp / "shared-plugins"
        write(self.claude_home / "plugins" / "installed_plugins.json", json.dumps({"version": 2, "plugins": {}}))
        self.claude_plugin("matt", [{"scope": "user", "installPath": str(root)}], plugins_dir=shared)

        completed = self.run_resolver("matt:retro", extra_env={"CLAUDE_CODE_PLUGIN_CACHE_DIR": str(shared)})

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, f"matt:retro {expected}\n")

    def test_config_dir_registry_is_not_a_fallback(self):
        # Claude Code reads only the folder in the variable, so this session does not load the plugin.
        root = self.install_root("matt")
        make_skill(root, "skills/retro")
        self.claude_plugin("matt", [{"scope": "user", "installPath": str(root)}])
        shared = self.tmp / "shared-plugins"
        write(shared / "installed_plugins.json", json.dumps({"version": 2, "plugins": {}}))

        completed = self.run_resolver("matt:retro", extra_env={"CLAUDE_CODE_PLUGIN_CACHE_DIR": str(shared)})

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(completed.stdout, "")
        self.assertIn(f"not installed (registry {shared / 'installed_plugins.json'})", completed.stderr)

    def test_leading_tilde_names_the_home_folder(self):
        home = self.tmp / "home"
        root = self.install_root("matt")
        expected = make_skill(root, "skills/retro")
        for value, folder in (("~/shared-plugins", home / "shared-plugins"), ("~", home)):
            with self.subTest(value=value):
                self.claude_plugin("matt", [{"scope": "user", "installPath": str(root)}], plugins_dir=folder)

                completed = self.run_resolver(
                    "matt:retro", extra_env={"HOME": str(home), "CLAUDE_CODE_PLUGIN_CACHE_DIR": value}
                )

                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertEqual(completed.stdout, f"matt:retro {expected}\n")

    def test_tilde_with_a_user_name_is_not_expanded(self):
        # Claude Code loads no plugin for this value, so the resolver must not find one.
        value = f"~{getpass.getuser()}/shared-plugins"

        completed = self.run_resolver("matt:retro", extra_env={"CLAUDE_CODE_PLUGIN_CACHE_DIR": value})

        self.assertEqual(completed.returncode, 1)
        self.assertIn(f"registry {value}/installed_plugins.json", completed.stderr)
        self.assertNotIn("Traceback", completed.stderr)

    def test_settings_still_come_from_the_config_dir(self):
        root = self.install_root("matt")
        make_skill(root, "skills/retro")
        shared = self.tmp / "shared-plugins"
        self.claude_plugin("matt", [{"scope": "user", "installPath": str(root)}], enabled=False, plugins_dir=shared)

        completed = self.run_resolver("matt:retro", extra_env={"CLAUDE_CODE_PLUGIN_CACHE_DIR": str(shared)})

        self.assertEqual(completed.returncode, 1)
        self.assertIn(f"disabled in {self.claude_home / 'settings.json'}", completed.stderr)

    def test_empty_value_uses_the_config_dir(self):
        root = self.install_root("matt")
        expected = make_skill(root, "skills/retro")
        self.claude_plugin("matt", [{"scope": "user", "installPath": str(root)}])

        completed = self.run_resolver("matt:retro", extra_env={"CLAUDE_CODE_PLUGIN_CACHE_DIR": ""})

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, f"matt:retro {expected}\n")


class CodexResolveTest(ResolverCase):
    def test_enabled_plugin_resolves_from_the_highest_version(self):
        self.codex_install("matt", "1.9.0", "retro")
        expected = self.codex_install("matt", "1.10.0", "retro")
        self.codex_config('[plugins."matt@market"]\nenabled = true\n')

        completed = self.run_resolver("--host", "codex", "matt:retro")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, f"matt:retro {expected}\n")

    def test_numeric_versions_win_over_other_folder_names(self):
        for extra in ("local", "latest", ".staging", "1.10.0-rc1"):
            with self.subTest(extra=extra):
                self.codex_install("matt", "1.9.0", "retro")
                expected = self.codex_install("matt", "1.10.0", "retro")
                self.codex_install("matt", extra, "retro")
                self.codex_config('[plugins."matt@market"]\nenabled = true\n')

                self.assertEqual(self.run_resolver("--host", "codex", "matt:retro").stdout, f"matt:retro {expected}\n")

    def test_a_single_named_folder_is_used(self):
        expected = self.codex_install("matt", "local", "retro")
        self.codex_config('[plugins."matt@market"]\nenabled = true\n')

        self.assertEqual(self.run_resolver("--host", "codex", "matt:retro").stdout, f"matt:retro {expected}\n")

    def test_table_header_forms_are_read(self):
        expected = self.codex_install("matt", "1.0.0", "retro")
        for header in ("[plugins.'matt@market'] # note", '[ plugins."matt@market" ]', '[plugins. "matt@market"]'):
            with self.subTest(header=header):
                self.codex_config(f"{header}\nenabled = true\n")

                self.assertEqual(self.run_resolver("--host", "codex", "matt:retro").stdout, f"matt:retro {expected}\n")

    def test_config_that_is_not_utf8_fails(self):
        self.codex_install("matt", "1.0.0", "retro")
        (self.codex_home / "config.toml").write_bytes(b'[plugins."matt@market"]\nenabled = true\n# \xff\xfe\n')

        completed = self.run_resolver("--host", "codex", "matt:retro")

        self.assertEqual(completed.returncode, 1)
        self.assertIn("Codex config", completed.stderr)
        self.assertNotIn("Traceback", completed.stderr)

    def test_codex_manifest_path_wins_over_the_claude_copy(self):
        root = self.codex_home / "plugins" / "cache" / "market" / "dev" / "1.0.0"
        write(root / ".codex-plugin" / "plugin.json", json.dumps({"skills": "./codex-skills/"}))
        make_skill(root, "skills/pressure-test")
        expected = make_skill(root, "codex-skills/pressure-test")
        self.codex_config('[plugins."dev@market"]\nenabled = true\n')

        completed = self.run_resolver("--host", "codex", "dev:pressure-test")

        self.assertEqual(completed.stdout, f"dev:pressure-test {expected}\n")

    def test_claude_copy_is_not_used_when_the_manifest_names_skill_paths(self):
        root = self.codex_home / "plugins" / "cache" / "market" / "dev" / "1.0.0"
        write(root / ".codex-plugin" / "plugin.json", json.dumps({"skills": "./codex-skills/"}))
        make_skill(root, "codex-skills/pressure-test")
        make_skill(root, "skills/project-eval")
        self.codex_config('[plugins."dev@market"]\nenabled = true\n')

        completed = self.run_resolver("--host", "codex", "dev:project-eval")

        self.assertEqual(completed.returncode, 1)
        self.assertIn("not found", completed.stderr)

    def test_missing_config_fails(self):
        self.codex_install("matt", "1.0.0", "retro")

        completed = self.run_resolver("--host", "codex", "matt:retro")

        self.assertEqual(completed.returncode, 1)
        self.assertIn("Codex config", completed.stderr)

    def test_enabled_plugin_without_a_cache_fails(self):
        self.codex_config('[plugins."matt@market"]\nenabled = true\n')

        completed = self.run_resolver("--host", "codex", "matt:retro")

        self.assertEqual(completed.returncode, 1)
        self.assertIn("not installed", completed.stderr)

    def test_missing_codex_skill_fails(self):
        self.codex_install("matt", "1.0.0", "retro")
        self.codex_config('[plugins."matt@market"]\nenabled = true\n')

        completed = self.run_resolver("--host", "codex", "matt:to-spec")

        self.assertEqual(completed.returncode, 1)
        self.assertIn("not found", completed.stderr)

    def test_plugin_that_is_not_enabled_fails(self):
        self.codex_install("matt", "1.0.0", "retro")
        for config in ('[plugins."matt@market"]\nenabled = false\n', '[plugins."other@market"]\nenabled = true\n'):
            with self.subTest(config=config):
                self.codex_config(config)

                completed = self.run_resolver("--host", "codex", "matt:retro")

                self.assertEqual(completed.returncode, 1)
                self.assertIn("not enabled", completed.stderr)

    def test_enabled_flag_belongs_to_its_own_table(self):
        self.codex_install("matt", "1.0.0", "retro")
        self.codex_config('[plugins."matt@market"]\n\n[plugins."other@market"]\nenabled = true\n')

        completed = self.run_resolver("--host", "codex", "matt:retro")

        self.assertEqual(completed.returncode, 1)
        self.assertIn("not enabled", completed.stderr)


class AntigravityResolveTest(ResolverCase):
    """Workspace plugins in .agents/plugins/, then global plugins in ~/.gemini/config/plugins/."""

    def setUp(self):
        super().setUp()
        (self.workdir / ".git").mkdir()  # The work folder is the Git top level, so the upward walk stops there.
        self.workspace_plugins = self.workdir / ".agents" / "plugins"
        self.global_plugins = self.home / ".gemini" / "config" / "plugins"

    def agy_plugin(self, plugins_dir: Path, folder: str, manifest: dict | None = None, *, claude: dict | None = None) -> Path:
        root = plugins_dir / folder
        root.mkdir(parents=True)
        if manifest is not None:
            write(root / ".antigravity-plugin" / "plugin.json", json.dumps(manifest))
        if claude is not None:
            write(root / ".claude-plugin" / "plugin.json", json.dumps(claude))
        return root

    def agy_config(self, plugins: dict) -> None:
        write(self.home / ".gemini" / "config" / "config.json", json.dumps({"plugins": plugins}))

    def run_agy(self, *names: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
        return self.run_resolver("--host", "antigravity", *names, cwd=cwd)

    def test_workspace_plugin_wins_over_the_global_plugin(self):
        workspace = self.agy_plugin(self.workspace_plugins, "matt", {"name": "matt"})
        expected = make_skill(workspace, "skills/retro")
        make_skill(self.agy_plugin(self.global_plugins, "matt", {"name": "matt"}), "skills/retro")
        helper = make_skill(self.agy_plugin(self.global_plugins, "tools", {"name": "tools"}), "skills/helper")

        completed = self.run_agy("matt:retro", "tools:helper")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, f"matt:retro {expected}\ntools:helper {helper}\n")

    def test_upward_walk_finds_the_nearest_workspace_plugin(self):
        make_skill(self.agy_plugin(self.workspace_plugins, "matt", {"name": "matt"}), "skills/retro")
        helper = make_skill(self.agy_plugin(self.workspace_plugins, "tools", {"name": "tools"}), "skills/helper")
        nearer = self.agy_plugin(self.workdir / "pkg" / ".agents" / "plugins", "matt", {"name": "matt"})
        expected = make_skill(nearer, "skills/retro")
        deep = self.workdir / "pkg" / "src" / "deep"
        deep.mkdir(parents=True)

        completed = self.run_agy("matt:retro", "tools:helper", cwd=deep)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, f"matt:retro {expected}\ntools:helper {helper}\n")

    def test_upward_walk_stops_at_the_git_top_level(self):
        outer = self.tmp / "outer"
        make_skill(self.agy_plugin(outer / ".agents" / "plugins", "matt", {"name": "matt"}), "skills/retro")
        repo = outer / "repo"
        write(repo / ".git", "gitdir: /elsewhere/.git/worktrees/repo\n")  # A linked worktree has a .git file.
        (repo / "src").mkdir()

        completed = self.run_agy("matt:retro", cwd=repo / "src")

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(completed.stdout, "")
        self.assertIn("not installed", completed.stderr)

    def test_enabled_state_follows_folder_key_then_name_key_then_manifest(self):
        cases = [
            ("folder key disables", {"matt-dir": {"enabled": False}, "matt": {"enabled": True}}, {}, False),
            ("folder key enables", {"matt-dir": {"enabled": True}, "matt": {"enabled": False}}, {"disabled": True}, True),
            ("name key disables", {"matt": {"enabled": False}}, {}, False),
            ("name key enables", {"matt": {"enabled": True}}, {"disabled": True}, True),
            ("manifest disables", {}, {"disabled": True}, False),
            ("no entry enables", {}, {}, True),
        ]
        for label, plugins, extra, enabled in cases:
            with self.subTest(label):
                shutil.rmtree(self.global_plugins, ignore_errors=True)
                root = self.agy_plugin(self.global_plugins, "matt-dir", {"name": "matt", **extra})
                expected = make_skill(root, "skills/retro")
                self.agy_config(plugins)

                completed = self.run_agy("matt:retro")

                if enabled:
                    self.assertEqual(completed.returncode, 0, completed.stderr)
                    self.assertEqual(completed.stdout, f"matt:retro {expected}\n")
                else:
                    self.assertEqual(completed.returncode, 1)
                    self.assertEqual(completed.stdout, "")
                    self.assertIn("matt:retro", completed.stderr)
                    self.assertIn("disabled", completed.stderr)

    def test_disabled_workspace_plugin_falls_through_to_the_global_plugin(self):
        make_skill(self.agy_plugin(self.workspace_plugins, "matt-ws", {"name": "matt"}), "skills/retro")
        expected = make_skill(self.agy_plugin(self.global_plugins, "matt", {"name": "matt"}), "skills/retro")
        self.agy_config({"matt-ws": {"enabled": False}})

        completed = self.run_agy("matt:retro")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, f"matt:retro {expected}\n")

    def test_plugin_matches_by_manifest_name_before_the_folder_name(self):
        both = self.agy_plugin(self.global_plugins, "renamed-dir", {"name": "matt"}, claude={"name": "claude-name"})
        retro = make_skill(both, "skills/retro")
        helper = make_skill(self.agy_plugin(self.global_plugins, "claude-dir", claude={"name": "tools"}), "skills/helper")
        task = make_skill(self.agy_plugin(self.global_plugins, "bare"), "skills/task")

        completed = self.run_agy("matt:retro", "tools:helper", "bare:task", "claude-name:retro", "renamed-dir:retro")

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(completed.stdout, f"matt:retro {retro}\ntools:helper {helper}\nbare:task {task}\n")
        self.assertIn("claude-name:retro: plugin claude-name is not installed", completed.stderr)
        self.assertIn("renamed-dir:retro: plugin renamed-dir is not installed", completed.stderr)

    def test_declared_skills_paths_come_before_the_skills_dir(self):
        root = self.agy_plugin(self.global_plugins, "dev", {"name": "dev", "skills": "./antigravity-skills/"})
        make_skill(root, "skills/pressure-test")
        expected = make_skill(root, "antigravity-skills/pressure-test")
        claude_only = make_skill(root, "skills/project-eval")  # Antigravity always scans skills/.

        completed = self.run_agy("dev:pressure-test", "dev:project-eval")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, f"dev:pressure-test {expected}\ndev:project-eval {claude_only}\n")

    def test_search_skips_the_codex_copy(self):
        root = self.agy_plugin(self.global_plugins, "dev", {"name": "dev"})
        make_skill(root, "codex-skills/helper")  # Sorts first, so only the skip keeps it out.
        expected = make_skill(root, "extra/helper")

        completed = self.run_agy("dev:helper")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, f"dev:helper {expected}\n")

    def test_unreadable_config_fails(self):
        make_skill(self.agy_plugin(self.global_plugins, "matt", {"name": "matt"}), "skills/retro")
        for text in ("{", '{"plugins": []}'):
            with self.subTest(text=text):
                write(self.home / ".gemini" / "config" / "config.json", text)

                completed = self.run_agy("matt:retro")

                self.assertEqual(completed.returncode, 1)
                self.assertIn("Antigravity config", completed.stderr)
                self.assertNotIn("Traceback", completed.stderr)

    def test_missing_plugin_fails(self):
        completed = self.run_agy("matt:retro")

        self.assertEqual(completed.returncode, 1)
        self.assertIn("not installed", completed.stderr)


class UsageTest(ResolverCase):
    def test_bad_arguments_are_a_usage_error(self):
        for args in ((), ("no-colon",), ("--host", "other", "matt:retro"), (":retro",)):
            with self.subTest(args=args):
                self.assertEqual(self.run_resolver(*args).returncode, 2)

    def test_usage_error_for_an_unknown_host_names_every_host(self):
        completed = self.run_resolver("--host", "gemini", "matt:retro")

        self.assertEqual(completed.returncode, 2)
        self.assertIn("--host claude|codex|antigravity", completed.stderr)


if __name__ == "__main__":
    unittest.main()
