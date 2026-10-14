"""Command-line checks for the skill resolver script."""

from __future__ import annotations

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
        self.workdir = self.tmp / "work"
        self.workdir.mkdir()

    def run_resolver(self, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
        env = dict(os.environ, CLAUDE_CONFIG_DIR=str(self.claude_home), CODEX_HOME=str(self.codex_home))
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            capture_output=True,
            text=True,
            cwd=str(cwd or self.workdir),
            env=env,
        )

    # Claude Code fixtures

    def claude_plugin(
        self, name: str, records: list[dict], *, enabled: bool | None = True, market: str = "market"
    ) -> None:
        registry = self.claude_home / "plugins" / "installed_plugins.json"
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

    def test_skill_outside_the_manifest_list_is_found_by_search(self):
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

    def test_missing_registry_fails(self):
        completed = self.run_resolver("matt:retro")

        self.assertEqual(completed.returncode, 1)
        self.assertIn("registry", completed.stderr)


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
        for header in ("[plugins.'matt@market'] # note", '[ plugins."matt@market" ]'):
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


class UsageTest(ResolverCase):
    def test_bad_arguments_are_a_usage_error(self):
        for args in ((), ("no-colon",), ("--host", "other", "matt:retro"), (":retro",)):
            with self.subTest(args=args):
                self.assertEqual(self.run_resolver(*args).returncode, 2)


if __name__ == "__main__":
    unittest.main()
