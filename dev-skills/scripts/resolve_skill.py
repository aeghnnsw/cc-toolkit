#!/usr/bin/env python3
"""Print the SKILL.md path of each named plugin skill.

Usage: resolve_skill.py [--host claude|codex] PLUGIN:SKILL...

For each name that resolves, print "PLUGIN:SKILL /absolute/path/SKILL.md".
For each name that fails, print one stderr line that names the cause, and
continue with the next name. Exit 0 when every name resolves, 1 when any
name fails, and 2 on a usage error.

Claude Code (default): read plugins/installed_plugins.json under
CLAUDE_CONFIG_DIR (default ~/.claude). An install record for a project that
contains the current directory comes before the user-scope record. A plugin
set to false under enabledPlugins in the user settings.json is disabled.

Codex: the [plugins."PLUGIN@MARKETPLACE"] table in config.toml under
CODEX_HOME (default ~/.codex) must set enabled = true. The highest numeric
version under plugins/cache/MARKETPLACE/PLUGIN/ is used.

In the plugin root, search the skills paths of the host manifest and the
skills/ directory. In Codex, manifest skills paths replace skills/. Without
manifest skills paths, also search the whole root without the other host's
skill copies.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Callable, Iterable, NamedTuple

USAGE = "usage: resolve_skill.py [--host claude|codex] PLUGIN:SKILL..."
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


def claude_plugin_root(plugin: str) -> Path:
    """Return the Claude Code install path of PLUGIN for the current directory."""
    home = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    registry = home / "plugins" / "installed_plugins.json"
    settings = home / "settings.json"
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


class Host(NamedTuple):
    """How to find the plugin root and the skills of one host."""

    plugin_root: Callable[[str], Path]
    manifest: str
    other_copies: str  # skill folder of the other host, skipped by the search
    keeps_skills_dir: bool  # skills/ still loads when the manifest lists skills paths


HOSTS = {
    "claude": Host(claude_plugin_root, ".claude-plugin/plugin.json", "codex-skills", True),
    "codex": Host(codex_plugin_root, ".codex-plugin/plugin.json", "claude-skills", False),
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
    skip = SKIP_DIRS | {host.other_copies}
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
