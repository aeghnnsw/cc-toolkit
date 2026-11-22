#!/usr/bin/env python3
"""Print the SKILL.md path of each named plugin skill.

Usage: resolve_skill.py [--host claude|codex|antigravity] PLUGIN:SKILL...

For each name that resolves, print "PLUGIN:SKILL /absolute/path/SKILL.md".
For each name that fails, print one stderr line that names the cause, and
continue with the next name. Exit 0 when every name resolves, 1 when any
name fails, and 2 on a usage error.

Claude Code (default): read installed_plugins.json in the plugins directory.
Like Claude Code, use CLAUDE_CODE_PLUGIN_CACHE_DIR as that directory when it
is set and not empty. A value of "~", or a value that starts with "~/",
starts at the home directory; a "~name" value is not expanded. Otherwise use
plugins/ under CLAUDE_CONFIG_DIR (default ~/.claude). An install record
for a project that contains the current directory comes before the
user-scope record. A plugin set to false under enabledPlugins in the user
settings.json under CLAUDE_CONFIG_DIR is disabled.

Codex: the [plugins."PLUGIN@MARKETPLACE"] table in config.toml under
CODEX_HOME (default ~/.codex) must set enabled = true. The highest numeric
version under plugins/cache/MARKETPLACE/PLUGIN/ is used.

Antigravity: the config root is GEMINI_HOME when it is an absolute path to
a directory, as in a T3 Code profile; otherwise it is ~/.gemini. Search each
.agents/plugins/ folder from the current directory upward, nearest first.
Stop after the directory that holds .git (the Git top level) or at /. Then
search config/plugins/ in the config root. In these folders, a plugin folder
matches by the name in .antigravity-plugin/plugin.json, else by the name in
.claude-plugin/plugin.json, else by the folder name. The first enabled match
is used, so a disabled workspace plugin does not hide a global plugin of the
same name. In config/config.json in the config root, plugins.FOLDER.enabled
decides first, then plugins.PLUGIN.enabled. With neither, "disabled": true
in .antigravity-plugin/plugin.json disables the plugin.

In the plugin root, search the skills paths of the host manifest and the
skills/ directory. In Codex, manifest skills paths replace skills/. Without
manifest skills paths, also search the whole root without the skill copies
of the other hosts: codex-skills/ and antigravity-skills/ for Claude Code,
claude-skills/ and antigravity-skills/ for Codex, and codex-skills/ for
Antigravity.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Callable, Iterable, NamedTuple

USAGE = "usage: resolve_skill.py [--host claude|codex|antigravity] PLUGIN:SKILL..."
SKIP_DIRS = {".git", "node_modules", "__pycache__"}


class ResolveError(Exception):
    """A name that cannot be resolved; the message names the cause."""


def load_json(path: Path) -> dict:
    """Return the JSON object in PATH; raise OSError or ValueError."""
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("not a JSON object")
    return data


def split_key(key: str) -> tuple[str, str]:
    """Return (PLUGIN, MARKETPLACE) from a "PLUGIN@MARKETPLACE" key."""
    plugin, _, marketplace = key.partition("@")
    return plugin, marketplace


def plugin_keys(keys: Iterable[str], plugin: str) -> list[str]:
    """Return the "PLUGIN@MARKETPLACE" keys that belong to PLUGIN."""
    return [k for k in keys if split_key(k)[0] == plugin]


def is_within(child: Path, parent: Path) -> bool:
    """Return True when CHILD is PARENT or a path below it."""
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True


def claude_plugins_dir(config_dir: Path) -> Path:
    """Return the directory that holds installed_plugins.json and the plugin cache."""
    cache_dir = os.environ.get("CLAUDE_CODE_PLUGIN_CACHE_DIR")
    if not cache_dir:
        return config_dir / "plugins"
    # Claude Code expands only "~" and "~/..."; a "~name" value stays as written.
    if cache_dir == "~" or cache_dir.startswith("~/"):
        cache_dir = str(Path.home()) + cache_dir[1:]
    return Path(cache_dir)


def claude_plugin_root(plugin: str) -> Path:
    """Return the Claude Code install path of PLUGIN for the current directory."""
    config_dir = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    registry = claude_plugins_dir(config_dir) / "installed_plugins.json"
    settings = config_dir / "settings.json"
    try:
        entries = load_json(registry).get("plugins")
    except (OSError, ValueError) as error:
        raise ResolveError(f"cannot read the plugin registry {registry} ({error})") from error
    if not isinstance(entries, dict) or not all(isinstance(v, list) for v in entries.values()):
        raise ResolveError(f"the plugin registry {registry} has an unknown format")
    keys = plugin_keys(entries, plugin)
    if not keys:
        raise ResolveError(f"plugin {plugin} is not installed (registry {registry})")
    try:
        enabled = load_json(settings).get("enabledPlugins", {}) if settings.exists() else {}
    except (OSError, ValueError) as error:
        raise ResolveError(f"cannot read the settings {settings} ({error})") from error
    if not isinstance(enabled, dict):
        raise ResolveError(f"enabledPlugins in the settings {settings} is not an object")
    usable = [k for k in keys if enabled.get(k) is not False]
    if not usable:
        raise ResolveError(f"plugin {keys[0]} is disabled in {settings}")

    cwd = Path.cwd().resolve()
    records = [
        r for k in usable for r in entries[k]
        if isinstance(r, dict) and isinstance(r.get("installPath"), str) and r["installPath"]
    ]
    projects = [
        r for r in records
        if isinstance(r.get("projectPath"), str) and r["projectPath"]
        and is_within(cwd, Path(r["projectPath"]).resolve())
    ]
    projects.sort(key=lambda r: len(str(Path(r["projectPath"]).resolve())), reverse=True)
    users = [r for r in records if r.get("scope") == "user"]
    if not projects and not users:
        raise ResolveError(f"plugin {plugin} is not installed for this project or the user (registry {registry})")
    return Path((projects or users)[0]["installPath"])


def read_codex_plugins(config: Path) -> dict[str, bool]:
    """Return {"PLUGIN@MARKETPLACE": enabled} from the [plugins."..."] tables."""
    tables: dict[str, bool] = {}
    current = None
    with open(config, encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped.startswith("["):
                match = re.fullmatch(r"""\[\s*plugins\s*\.\s*(["'])([^"']+)\1\s*\]\s*(#.*)?""", stripped)
                current = match.group(2) if match else None
                if current:
                    tables.setdefault(current, False)
                continue
            match = re.fullmatch(r"enabled\s*=\s*(true|false)\s*(#.*)?", stripped)
            if current and match:
                tables[current] = match.group(1) == "true"
    return tables


def version_key(name: str) -> tuple:
    """Sort key for a cache folder: numeric versions above other names.

    A release sorts above its pre-release, so 2.0.0 is above 2.0.0-rc1.
    """
    match = re.fullmatch(r"(\d+(?:\.\d+)*)(?:[-+](.*))?", name)
    if not match:
        return (0, (), 0, name)
    numbers = tuple(int(part) for part in match.group(1).split("."))
    return (1, numbers, 0 if match.group(2) else 1, name)


def codex_plugin_root(plugin: str) -> Path:
    """Return the cache folder of the highest installed version of PLUGIN."""
    home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    config = home / "config.toml"
    try:
        tables = read_codex_plugins(config)
    except (OSError, ValueError) as error:
        raise ResolveError(f"cannot read the Codex config {config} ({error})") from error
    keys = [k for k in plugin_keys(tables, plugin) if tables[k]]
    if not keys:
        raise ResolveError(f"plugin {plugin} is not enabled in {config}")
    marketplace = split_key(keys[0])[1]
    cache = home / "plugins" / "cache" / marketplace / plugin
    versions = [p for p in cache.glob("*") if p.is_dir() and not p.name.startswith(".")]
    if not versions:
        raise ResolveError(f"plugin {keys[0]} is not installed under {cache}")
    return max(versions, key=lambda p: version_key(p.name))


def gemini_config() -> Path:
    """Return the Antigravity config folder: GEMINI_HOME/config or ~/.gemini/config.

    T3 Code sets GEMINI_HOME to a private profile for each Antigravity
    provider instance. A relative or missing GEMINI_HOME is not used.
    """
    home = os.environ.get("GEMINI_HOME", "")
    root = Path(home) if os.path.isabs(home) and os.path.isdir(home) else Path.home() / ".gemini"
    return root / "config"


def antigravity_plugin_dirs() -> list[Path]:
    """Return the Antigravity plugin folders in search order.

    Walk upward from the current directory to the Git top level (or to /),
    nearest .agents/plugins first. The global folder of the config root comes last.
    """
    folders = []
    current = Path.cwd().resolve()
    for directory in (current, *current.parents):
        folders.append(directory / ".agents" / "plugins")
        if (directory / ".git").exists():
            break
    folders.append(gemini_config() / "plugins")
    return folders


def antigravity_name(root: Path) -> str:
    """Return the plugin name: the Antigravity manifest, the Claude manifest, or the folder."""
    for manifest in (".antigravity-plugin/plugin.json", ".claude-plugin/plugin.json"):
        try:
            name = load_json(root / manifest).get("name")
        except (OSError, ValueError):
            continue
        if isinstance(name, str) and name:
            return name
    return root.name


def antigravity_disabled(root: Path, plugin: str, config: Path, entries: dict) -> str | None:
    """Return why the plugin in ROOT is disabled, or None when it is enabled."""
    for key in (root.name, plugin):
        entry = entries.get(key)
        if isinstance(entry, dict) and isinstance(entry.get("enabled"), bool):
            return None if entry["enabled"] else f"plugins.{key}.enabled is false in {config}"
    manifest = root / ".antigravity-plugin" / "plugin.json"
    try:
        disabled = load_json(manifest).get("disabled") is True
    except (OSError, ValueError):
        disabled = False
    return f'{manifest} sets "disabled": true' if disabled else None


def antigravity_plugin_root(plugin: str) -> Path:
    """Return the first enabled Antigravity plugin folder named PLUGIN."""
    matches = []
    for folder in antigravity_plugin_dirs():
        try:
            children = sorted(p for p in folder.iterdir() if p.is_dir())
        except OSError:
            continue
        matches.extend(p for p in children if antigravity_name(p) == plugin)
    if not matches:
        global_dir = gemini_config() / "plugins"
        raise ResolveError(f"plugin {plugin} is not installed in a workspace .agents/plugins folder or in {global_dir}")
    config = gemini_config() / "config.json"
    try:
        entries = load_json(config).get("plugins", {}) if config.exists() else {}
    except (OSError, ValueError) as error:
        raise ResolveError(f"cannot read the Antigravity config {config} ({error})") from error
    if not isinstance(entries, dict):
        raise ResolveError(f"plugins in the Antigravity config {config} is not an object")
    reasons = [antigravity_disabled(root, plugin, config, entries) for root in matches]
    for root, reason in zip(matches, reasons):
        if reason is None:
            return root
    raise ResolveError(f"plugin {plugin} is disabled ({reasons[0]})")


class Host(NamedTuple):
    """How to find the plugin root and the skills of one host."""

    plugin_root: Callable[[str], Path]
    manifest: str
    other_copies: frozenset[str]  # skill folders of the other hosts, skipped by the search
    keeps_skills_dir: bool  # skills/ still loads when the manifest lists skills paths


HOSTS = {
    "claude": Host(claude_plugin_root, ".claude-plugin/plugin.json",
                   frozenset({"codex-skills", "antigravity-skills"}), True),
    "codex": Host(codex_plugin_root, ".codex-plugin/plugin.json",
                  frozenset({"claude-skills", "antigravity-skills"}), False),
    "antigravity": Host(antigravity_plugin_root, ".antigravity-plugin/plugin.json",
                        frozenset({"codex-skills"}), True),
}


def manifest_dirs(root: Path, manifest: str) -> list[Path]:
    """Return the skill paths that the host manifest declares."""
    try:
        paths = load_json(root / manifest).get("skills")
    except (OSError, ValueError):
        return []
    if isinstance(paths, str):
        paths = [paths]
    return [root / p for p in paths or [] if isinstance(p, str)]


def find_skill(root: Path, skill: str, host: Host) -> Path | None:
    """Return the SKILL.md of SKILL under ROOT, or None."""
    declared = manifest_dirs(root, host.manifest)
    if not declared:
        bases = [root / "skills", root]
    elif host.keeps_skills_dir:
        bases = [*declared, root / "skills"]
    else:
        bases = declared
    for base in bases:
        for candidate in (base / "SKILL.md", base / skill / "SKILL.md"):
            if candidate.parent.name == skill and candidate.is_file():
                return candidate
    skip = SKIP_DIRS | host.other_copies
    for base in bases:
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(d for d in dirnames if d not in skip)
            if Path(dirpath).name == skill and "SKILL.md" in filenames:
                return Path(dirpath) / "SKILL.md"
    return None


def resolve(name: str, host: Host) -> Path:
    """Return the absolute SKILL.md path for "PLUGIN:SKILL"."""
    plugin, skill = name.split(":", 1)
    root = host.plugin_root(plugin)
    if not root.is_dir():
        raise ResolveError(f"install path {root} does not exist")
    path = find_skill(root, skill, host)
    if path is None:
        raise ResolveError(f"skill {skill} not found under {root}")
    return path.resolve()


def main(argv: list[str]) -> int:
    args = argv[1:]
    host = "claude"
    if args[:1] == ["--host"]:
        if len(args) < 2 or args[1] not in HOSTS:
            print(USAGE, file=sys.stderr)
            return 2
        host, args = args[1], args[2:]
    if not args or any(not re.fullmatch(r"[^:\s]+:[^:\s]+", a) for a in args):
        print(USAGE, file=sys.stderr)
        return 2
    failed = False
    for name in args:
        try:
            print(f"{name} {resolve(name, HOSTS[host])}")
        except ResolveError as error:
            print(f"resolve_skill: {name}: {error}", file=sys.stderr)
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
