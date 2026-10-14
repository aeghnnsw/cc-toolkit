#!/usr/bin/env python3
"""Print the SKILL.md path of each named plugin skill.

Usage: resolve_skill.py [--host claude|codex] PLUGIN:SKILL...

For each name that resolves, print "PLUGIN:SKILL /absolute/path/SKILL.md".
For each name that fails, print one stderr line that names the cause.
Exit 0 when every name resolves, 1 when any name fails, 2 on a usage error.

Claude Code (default): read plugins/installed_plugins.json under
CLAUDE_CONFIG_DIR (default ~/.claude). An install record for a project that
contains the current directory comes before the user-scope record. A plugin
set to false under enabledPlugins in the user settings.json is disabled.

Codex: the [plugins."PLUGIN@MARKETPLACE"] table in config.toml under
CODEX_HOME (default ~/.codex) must set enabled = true. The highest version
under plugins/cache/MARKETPLACE/PLUGIN/ is used.

In the plugin root, the search order is: the host manifest's skills paths,
the conventional skills/ directory, then the whole root.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

USAGE = "usage: resolve_skill.py [--host claude|codex] PLUGIN:SKILL..."
MANIFESTS = {"claude": ".claude-plugin/plugin.json", "codex": ".codex-plugin/plugin.json"}
SKIP_DIRS = {".git", "node_modules", "__pycache__"}


class ResolveError(Exception):
    """A name that cannot be resolved; the message names the cause."""


def load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True


def claude_plugin_root(plugin: str) -> Path:
    home = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    registry = home / "plugins" / "installed_plugins.json"
    try:
        entries = load_json(registry).get("plugins") or {}
    except (OSError, ValueError) as error:
        raise ResolveError(f"cannot read the plugin registry {registry} ({error})") from error
    key = next((k for k in entries if k.split("@", 1)[0] == plugin), None)
    if key is None:
        raise ResolveError(f"plugin {plugin} is not installed (registry {registry})")
    try:
        enabled = (load_json(home / "settings.json").get("enabledPlugins") or {}).get(key)
    except (OSError, ValueError):
        enabled = None
    if enabled is False:
        raise ResolveError(f"plugin {key} is disabled in {home / 'settings.json'}")

    cwd = Path.cwd().resolve()
    records = [r for r in entries[key] if isinstance(r, dict) and r.get("installPath")]
    projects = [
        r for r in records
        if r.get("projectPath") and is_within(cwd, Path(r["projectPath"]).resolve())
    ]
    projects.sort(key=lambda r: len(str(Path(r["projectPath"]).resolve())), reverse=True)
    users = [r for r in records if r.get("scope") == "user"]
    chosen = (projects or users or records or [None])[0]
    if chosen is None:
        raise ResolveError(f"plugin {key} has no install path in {registry}")
    return Path(chosen["installPath"])


def read_codex_plugins(config: Path) -> dict[str, bool]:
    """Return {"PLUGIN@MARKETPLACE": enabled} from the [plugins."..."] tables."""
    tables: dict[str, bool] = {}
    current = None
    with open(config, encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped.startswith("["):
                match = re.fullmatch(r'\[plugins\."([^"]+)"\]', stripped)
                current = match.group(1) if match else None
                if current:
                    tables.setdefault(current, False)
                continue
            match = re.fullmatch(r"enabled\s*=\s*(true|false)\s*(#.*)?", stripped)
            if current and match:
                tables[current] = match.group(1) == "true"
    return tables


def version_key(name: str) -> tuple:
    return tuple((0, int(part), "") if part.isdigit() else (1, 0, part) for part in re.split(r"[.\-+]", name))


def codex_plugin_root(plugin: str) -> Path:
    home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    config = home / "config.toml"
    try:
        tables = read_codex_plugins(config)
    except OSError as error:
        raise ResolveError(f"cannot read the Codex config {config} ({error.strerror})") from error
    keys = [k for k, on in tables.items() if on and k.split("@", 1)[0] == plugin]
    if not keys:
        raise ResolveError(f"plugin {plugin} is not enabled in {config}")
    marketplace = keys[0].split("@", 1)[1]
    cache = home / "plugins" / "cache" / marketplace / plugin
    versions = sorted((p for p in cache.glob("*") if p.is_dir()), key=lambda p: version_key(p.name))
    if not versions:
        raise ResolveError(f"plugin {keys[0]} is not installed under {cache}")
    return versions[-1]


def manifest_dirs(root: Path, host: str) -> list[Path]:
    try:
        paths = load_json(root / MANIFESTS[host]).get("skills")
    except (OSError, ValueError):
        return []
    if isinstance(paths, str):
        paths = [paths]
    return [root / p for p in paths or [] if isinstance(p, str)]


def find_skill(root: Path, skill: str, host: str) -> Path | None:
    for base in [*manifest_dirs(root, host), root / "skills"]:
        for candidate in (base / "SKILL.md", base / skill / "SKILL.md"):
            if candidate.parent.name == skill and candidate.is_file():
                return candidate
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        if Path(dirpath).name == skill and "SKILL.md" in filenames:
            return Path(dirpath) / "SKILL.md"
    return None


def resolve(name: str, host: str) -> Path:
    plugin, skill = name.split(":", 1)
    root = claude_plugin_root(plugin) if host == "claude" else codex_plugin_root(plugin)
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
        if len(args) < 2 or args[1] not in MANIFESTS:
            print(USAGE, file=sys.stderr)
            return 2
        host, args = args[1], args[2:]
    if not args or any(not re.fullmatch(r"[^:\s]+:[^:\s]+", a) for a in args):
        print(USAGE, file=sys.stderr)
        return 2
    failed = False
    for name in args:
        try:
            print(f"{name} {resolve(name, host)}")
        except ResolveError as error:
            print(f"resolve_skill: {name}: {error}", file=sys.stderr)
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
