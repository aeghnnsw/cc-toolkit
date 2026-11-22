#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.8"
# ///
"""Tell the agent which installed cc-toolkit plugins are older than the
default branch.

Claude Code runs this script at SessionStart when the user sets
CORE_HOOKS_STALE_CHECK=1. It reads the SessionStart payload on stdin. In a
cc-toolkit checkout, it compares the installed Claude Code and Codex copies
with the manifests of the default branch. When a copy is older, it prints
the update commands as additional context. The check is advisory: on any
error it prints nothing and exits 0.
"""

import json
import os
import posixpath
import re
import subprocess
import sys
from pathlib import Path


MARKETPLACE = "cc-toolkit"
MARKETPLACE_FILE = ".claude-plugin/marketplace.json"
# Installed copies come from the GitHub default branch. A feature branch
# often has an unreleased version increase, so the working tree is the last
# choice.
REFERENCE_REFS = ("origin/HEAD", "origin/master")
VERSION = re.compile(r"(\d+)\.(\d+)\.(\d+)", re.ASCII)


def git(cwd, *args):
    """Return the output of a git command, or None when it fails."""
    try:
        result = subprocess.run(
            ["git", "-C", str(cwd)] + list(args),
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            universal_newlines=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


def parse_version(text):
    """Return a major.minor.patch version as a tuple of integers, or None."""
    match = VERSION.fullmatch(text) if isinstance(text, str) else None
    return tuple(int(part) for part in match.groups()) if match else None


def load_json(text):
    """Return parsed JSON text, or None when the text is missing or bad."""
    if text is None:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


def read_file(path):
    """Return the text of a file, or None when it cannot be read."""
    try:
        return Path(path).read_text()
    except (OSError, ValueError):
        return None


def reference_reader(root):
    """Return the name of the reference and a function that reads its files.

    The reference is the first ref that resolves, or the working tree.
    """
    for ref in REFERENCE_REFS:
        if git(root, "rev-parse", "--verify", "--quiet", ref + "^{commit}"):
            return ref, lambda path, ref=ref: git(root, "show", ref + ":" + path)
    return "the working tree", lambda path: read_file(root / path)


def manifest_version(read, source, host_folder):
    """Return the version in a plugin manifest of the reference, or None."""
    path = posixpath.normpath(posixpath.join(source, host_folder, "plugin.json"))
    manifest = load_json(read(path))
    return parse_version(manifest.get("version")) if isinstance(manifest, dict) else None


def reference_versions(root, read):
    """Return {plugin: (Claude version, Codex version)} of the reference."""
    marketplace = load_json(read(MARKETPLACE_FILE))
    plugins = marketplace.get("plugins") if isinstance(marketplace, dict) else None
    versions = {}
    for plugin in plugins if isinstance(plugins, list) else []:
        if not isinstance(plugin, dict):
            continue
        name, source = plugin.get("name"), plugin.get("source")
        if isinstance(name, str) and isinstance(source, str):
            versions[name] = (
                manifest_version(read, source, ".claude-plugin"),
                manifest_version(read, source, ".codex-plugin"),
            )
    return versions


def claude_install_files():
    """Return the installed-plugin files of Claude Code, without repeats."""
    candidates = []
    config_dir = os.environ.get("CLAUDE_CONFIG_DIR")
    if config_dir:
        candidates.append(Path(config_dir) / "plugins" / "installed_plugins.json")
    candidates.append(Path.home() / ".claude" / "plugins" / "installed_plugins.json")
    files = []
    for path in candidates:
        if path.is_file() and os.path.realpath(path) not in map(os.path.realpath, files):
            files.append(path)
    return files


def claude_installs():
    """Yield (plugin, version, scope, project path) of each Claude copy."""
    for path in claude_install_files():
        data = load_json(read_file(path))
        plugins = data.get("plugins") if isinstance(data, dict) else None
        if not isinstance(plugins, dict):
            continue
        for key, entries in plugins.items():
            plugin, _, marketplace = key.rpartition("@")
            if marketplace != MARKETPLACE or not isinstance(entries, list):
                continue
            for entry in entries:
                if isinstance(entry, dict):
                    yield (plugin, parse_version(entry.get("version")),
                           entry.get("scope") or "user", entry.get("projectPath"))


def codex_version(plugin):
    """Return the greatest version folder of a Codex plugin cache, or None."""
    codex_home = os.environ.get("CODEX_HOME") or str(Path.home() / ".codex")
    cache = Path(codex_home) / "plugins" / "cache" / MARKETPLACE / plugin
    try:
        folders = [path.name for path in cache.iterdir() if path.is_dir()]
    except OSError:
        return None
    versions = [version for version in map(parse_version, folders) if version]
    return max(versions) if versions else None


def text_of(version):
    """Return a version tuple as text."""
    return ".".join(str(part) for part in version)


def stale_report(cwd):
    """Return the report text for a checkout, or an empty string."""
    top = git(cwd, "rev-parse", "--show-toplevel")
    if not top:
        return ""
    root = Path(top.strip())
    marketplace = load_json(read_file(root / MARKETPLACE_FILE))
    if not isinstance(marketplace, dict) or marketplace.get("name") != MARKETPLACE:
        return ""
    ref, read = reference_reader(root)
    reference = reference_versions(root, read)

    lines, claude_commands, codex_commands = [], [], []
    for plugin, installed, scope, project in claude_installs():
        latest = reference.get(plugin, (None, None))[0]
        if installed and latest and installed < latest:
            where = "scope {}".format(scope)
            if project:
                where += ", project {}".format(project)
            line = "- {} (Claude Code, {}): installed {}, default branch {}.".format(
                plugin, where, text_of(installed), text_of(latest))
            command = "claude plugin update {}@{} --scope {}".format(plugin, MARKETPLACE, scope)
            if line not in lines:
                lines.append(line)
            if command not in claude_commands:
                claude_commands.append(command)
    for plugin, (_, latest) in reference.items():
        installed = codex_version(plugin)
        if installed and latest and installed < latest:
            lines.append("- {} (Codex): installed {}, default branch {}.".format(
                plugin, text_of(installed), text_of(latest)))
            codex_commands.append("codex plugin add {}@{}".format(plugin, MARKETPLACE))
    if not lines:
        return ""

    parts = [
        "core-hooks stale-install check: these installed cc-toolkit plugins "
        "are older than the default branch ({}). New sessions run the "
        "older copies until they are updated.".format(ref),
        "\n".join(lines),
    ]
    if claude_commands:
        parts.append("To update the Claude Code copies, run these commands, "
                     "then start a new session:\n" + "\n".join(
                         ["claude plugin marketplace update " + MARKETPLACE]
                         + claude_commands))
    if codex_commands:
        parts.append("To update the Codex copies, run these commands, then "
                     "start a new session:\n" + "\n".join(
                         ["codex plugin marketplace upgrade " + MARKETPLACE]
                         + codex_commands))
    return "\n\n".join(parts)


def main():
    try:
        payload = json.load(sys.stdin)
        cwd = payload.get("cwd") if isinstance(payload, dict) else None
        report = stale_report(cwd if isinstance(cwd, str) and cwd else os.getcwd())
        if report:
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": report,
            }}))
    except Exception:
        pass  # Advisory check: never block or disturb the session.
    sys.exit(0)


if __name__ == "__main__":
    main()
