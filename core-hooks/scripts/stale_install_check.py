#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.8"
# ///
"""Tell the agent which installed copies of cc-toolkit plugins are stale.

Claude Code and Codex run this script at SessionStart. It reads the
SessionStart payload on stdin. For each home on this host, it compares each
installed copy with the same plugin in the marketplace clone of that home,
and reads the working-tree files of the clone:

- Claude Code: the plugin folders in CLAUDE_CODE_PLUGIN_CACHE_DIR,
  CLAUDE_CONFIG_DIR/plugins, and ~/.claude/plugins. Each folder holds
  installed_plugins.json and the clone marketplaces/cc-toolkit.
- Codex: the homes CODEX_HOME, ~/.codex, and the sorted ~/.codex-t3/*.
  Each home holds the plugin cache plugins/cache/cc-toolkit and the clone
  .tmp/marketplaces/cc-toolkit. Homes that share both folders through links
  get one command set, which names the first of these homes.

CORE_HOOKS_STALE_CHECK=0 turns the check off. CORE_HOOKS_STALE_CHECK=1 also
compares the installed copies with the default branch of a cc-toolkit
checkout. When a copy is older, the script prints the update commands as
additional context. The check is advisory: on any error it prints nothing
and exits 0.
"""

import json
import os
import posixpath
import re
import shlex
import subprocess
import sys
from pathlib import Path


MARKETPLACE = "cc-toolkit"
# The marketplace registry and the plugin manifest folder of each host.
CLAUDE = (".claude-plugin/marketplace.json", ".claude-plugin")
CODEX = (".agents/plugins/marketplace.json", ".codex-plugin")
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


def real_folder(path):
    """Return the real path of a folder, or None when it is not a folder.

    os.path.isdir is False for a broken link or a link loop, so realpath
    never meets one. Path.resolve() would raise on a loop.
    """
    return os.path.realpath(str(path)) if os.path.isdir(str(path)) else None


def source_path(source):
    """Return the path of a local plugin source, or None.

    A source is a path string, or an object such as
    {"source": "local", "path": "./core-hooks"}.
    """
    if isinstance(source, dict) and source.get("source") == "local":
        source = source.get("path")
    return source if isinstance(source, str) else None


def host_versions(read, host):
    """Return {plugin: version} of one host in a marketplace and its manifests."""
    registry, manifest_folder = host
    marketplace = load_json(read(registry))
    plugins = marketplace.get("plugins") if isinstance(marketplace, dict) else None
    versions = {}
    for plugin in plugins if isinstance(plugins, list) else []:
        if not isinstance(plugin, dict):
            continue
        name, source = plugin.get("name"), source_path(plugin.get("source"))
        if not isinstance(name, str) or source is None:
            continue
        path = posixpath.normpath(posixpath.join(source, manifest_folder, "plugin.json"))
        manifest = load_json(read(path))
        version = parse_version(manifest.get("version")) if isinstance(manifest, dict) else None
        if version:
            versions[name] = version
    return versions


def clone_versions(clone, host):
    """Return {plugin: version} of one host in a marketplace clone, or {}."""
    if not os.path.isdir(str(clone)):
        return {}
    return host_versions(lambda path: read_file(Path(clone) / path), host)


def reference_reader(root):
    """Return the name of the reference and a function that reads its files.

    The reference is the first ref that resolves, or the working tree.
    """
    for ref in REFERENCE_REFS:
        if git(root, "rev-parse", "--verify", "--quiet", ref + "^{commit}"):
            return ref, lambda path, ref=ref: git(root, "show", ref + ":" + path)
    return "the working tree", lambda path: read_file(root / path)


def default_branch(cwd):
    """Return (ref name, Claude versions, Codex versions) of a checkout, or None.

    A folder outside a cc-toolkit checkout has no default branch.
    """
    top = git(cwd, "rev-parse", "--show-toplevel")
    if not top:
        return None
    root = Path(top.strip())
    marketplace = load_json(read_file(root / CLAUDE[0]))
    if not isinstance(marketplace, dict) or marketplace.get("name") != MARKETPLACE:
        return None
    ref, read = reference_reader(root)
    return ref, host_versions(read, CLAUDE), host_versions(read, CODEX)


def claude_plugin_folders():
    """Return the Claude Code plugin folders, without repeats.

    Like Claude Code, a CLAUDE_CODE_PLUGIN_CACHE_DIR value of "~", or one
    that starts with "~/", starts at the home folder; "~name" stays as
    written. An empty value counts as unset.
    """
    candidates = []
    cache_dir = os.environ.get("CLAUDE_CODE_PLUGIN_CACHE_DIR")
    if cache_dir:
        if cache_dir == "~" or cache_dir.startswith("~/"):
            cache_dir = str(Path.home()) + cache_dir[1:]
        candidates.append(Path(cache_dir))
    config_dir = os.environ.get("CLAUDE_CONFIG_DIR")
    if config_dir:
        candidates.append(Path(config_dir) / "plugins")
    candidates.append(Path.home() / ".claude" / "plugins")
    folders, seen = [], set()
    for folder in candidates:
        real = real_folder(folder)
        if real and real not in seen:
            seen.add(real)
            folders.append(folder)
    return folders


def claude_installs(folder):
    """Yield (plugin, version, scope, project path) of each Claude copy."""
    data = load_json(read_file(Path(folder) / "installed_plugins.json"))
    plugins = data.get("plugins") if isinstance(data, dict) else None
    if not isinstance(plugins, dict):
        return
    for key, entries in plugins.items():
        plugin, _, marketplace = key.rpartition("@")
        if marketplace != MARKETPLACE or not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, dict):
                yield (plugin, parse_version(entry.get("version")),
                       entry.get("scope") or "user", entry.get("projectPath"))


def codex_homes():
    """Return CODEX_HOME, ~/.codex, and the sorted ~/.codex-t3/* homes."""
    homes = []
    if os.environ.get("CODEX_HOME"):
        homes.append(Path(os.environ["CODEX_HOME"]))
    homes.append(Path.home() / ".codex")
    try:
        homes.extend(sorted(
            path for path in (Path.home() / ".codex-t3").iterdir()
            if not path.name.startswith(".")
        ))
    except OSError:
        pass
    unique = []
    for home in homes:
        if os.path.abspath(str(home)) not in map(os.path.abspath, map(str, unique)):
            unique.append(home)
    return unique


def codex_groups():
    """Return (home, plugin cache, clone or None) for each group of homes.

    Homes that share the plugin cache and the marketplace clone through
    links are one group. The group keeps the first home in the order of
    codex_homes(). A home without a plugin cache has no installed copy.
    """
    groups, seen = [], set()
    for home in codex_homes():
        cache = home / "plugins" / "cache" / MARKETPLACE
        clone = home / ".tmp" / "marketplaces" / MARKETPLACE
        real_cache = real_folder(cache)
        if not real_cache:
            continue
        key = (real_cache, real_folder(clone))
        if key not in seen:
            seen.add(key)
            groups.append((home, cache, clone if key[1] else None))
    return groups


def codex_version(cache, plugin):
    """Return the greatest version folder of a Codex plugin, or None."""
    try:
        folders = [path.name for path in (cache / plugin).iterdir() if path.is_dir()]
    except OSError:
        return None
    versions = [version for version in map(parse_version, folders) if version]
    return max(versions) if versions else None


def codex_prefix(home):
    """Return the command prefix that names a Codex home."""
    if os.path.abspath(str(home)) == os.path.abspath(str(Path.home() / ".codex")):
        return ""
    return "CODEX_HOME={} ".format(shlex.quote(str(home)))


def version_text(version):
    """Return a version tuple as text."""
    return ".".join(str(part) for part in version)


def add(items, item):
    """Append an item to a list once."""
    if item not in items:
        items.append(item)


class Report:
    """Collect the stale copies and the commands that update them."""

    def __init__(self, branch_ref):
        self.branch_ref = branch_ref
        self.clone_lines, self.branch_lines = [], []
        self.claude_commands, self.codex_commands = [], []

    def compare(self, label, installed, clone, branch):
        """Record a copy older than the clone or the default branch.

        Return True when the copy is older than either.
        """
        stale = False
        for latest, lines, source in ((clone, self.clone_lines, "marketplace clone"),
                                      (branch, self.branch_lines, "default branch")):
            if installed and latest and installed < latest:
                add(lines, "- {}: installed copy {}, {} {}.".format(
                    label, version_text(installed), source, version_text(latest)))
                stale = True
        return stale

    def text(self):
        """Return the report text, or an empty string."""
        if not (self.clone_lines or self.branch_lines):
            return ""
        parts = ["core-hooks stale-install check: a session runs the "
                 "installed copy of each plugin that it loaded at start. "
                 "New sessions run these older copies until they are updated."]
        if self.clone_lines:
            parts.append("Stale installs: these installed copies are older than "
                         "the same plugin in the marketplace clone of the same "
                         "home.\n" + "\n".join(self.clone_lines))
        if self.branch_lines:
            parts.append("These installed copies are older than the default "
                         "branch of this checkout ({}).\n".format(self.branch_ref)
                         + "\n".join(self.branch_lines))
        if self.claude_commands:
            parts.append("To update the Claude Code copies, run these commands, "
                         "then start a new session:\n" + "\n".join(self.claude_commands))
        if self.codex_commands:
            parts.append("To update the Codex copies, run these commands, then "
                         "start a new session. `codex plugin add` removes the old "
                         "version folder, so a running Codex session must "
                         "restart:\n" + "\n".join(self.codex_commands))
        return "\n\n".join(parts)


def stale_report(cwd, opt_in=False):
    """Return the report text, or an empty string.

    With opt_in, also compare with the default branch when cwd is in a
    cc-toolkit checkout.
    """
    branch = default_branch(cwd) if opt_in else None
    ref, branch_claude, branch_codex = branch or (None, {}, {})
    report = Report(ref)

    for folder in claude_plugin_folders():
        try:
            clone = clone_versions(folder / "marketplaces" / MARKETPLACE, CLAUDE)
            for plugin, installed, scope, project in claude_installs(folder):
                label = "{} (Claude Code, scope {}".format(plugin, scope)
                label += ", project {})".format(project) if project else ")"
                if report.compare(label, installed, clone.get(plugin),
                                  branch_claude.get(plugin)):
                    add(report.claude_commands,
                        "claude plugin marketplace update " + MARKETPLACE)
                    add(report.claude_commands, "claude plugin update {}@{} --scope {}".format(
                        plugin, MARKETPLACE, scope))
        except (OSError, ValueError):
            continue  # A broken folder does not drop the other folders.

    for home, cache, clone_folder in codex_groups():
        try:
            clone = clone_versions(clone_folder, CODEX) if clone_folder else {}
            prefix = codex_prefix(home)
            for plugin in sorted(set(clone) | set(branch_codex)):
                label = "{} (Codex, home {})".format(plugin, home)
                if report.compare(label, codex_version(cache, plugin),
                                  clone.get(plugin), branch_codex.get(plugin)):
                    add(report.codex_commands,
                        prefix + "codex plugin marketplace upgrade " + MARKETPLACE)
                    add(report.codex_commands, prefix + "codex plugin add {}@{}".format(
                        plugin, MARKETPLACE))
        except (OSError, ValueError):
            continue  # A broken home does not drop the other homes.
    return report.text()


def main():
    setting = os.environ.get("CORE_HOOKS_STALE_CHECK", "")
    if setting == "0":
        sys.exit(0)  # The user turned the whole check off.
    try:
        payload = json.load(sys.stdin)
        cwd = payload.get("cwd") if isinstance(payload, dict) else None
        report = stale_report(cwd if isinstance(cwd, str) and cwd else os.getcwd(),
                              opt_in=setting == "1")
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
