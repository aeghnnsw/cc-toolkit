#!/usr/bin/env python3
"""List the worktrees of a repository that another live session may use.

repo-cleanup runs this script before it removes worktrees. Each output line is
a worktree path, as `git worktree list` prints it, a tab, and the evidence:
a Git lock, a running process with its working directory in the worktree, or
a Claude Code or Codex session log, changed in the last 60 minutes, that
records a working directory in the worktree. The main checkout is never
listed, because cleanup never removes it.

The current session is left out: this process, its ancestors, and the logs
named by CLAUDE_CODE_SESSION_ID or CODEX_THREAD_ID. The exit status is 0 when
the check ran and 1 when it could not run, for example without lsof or ps.

Limit: a session with no process in the worktree and no log change in the
last 60 minutes is not found, for example a Codex thread, whose app server
runs in another folder, that waits for an hour.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from typing import NoReturn

WINDOW_MINUTES = 60
TAIL = 4 * 1024 * 1024
CONFIG_VAR = re.compile(r"(?:^|\s)(CLAUDE_CONFIG_DIR|CODEX_HOME)=(\S+)")


def fail(message: str) -> NoReturn:
    print(f"live_worktrees: {message}", file=sys.stderr)
    sys.exit(1)


def linked_worktrees(repo: str) -> dict[str, list[str]]:
    """Return each linked worktree path, without the main worktree, with its lock."""
    try:
        result = subprocess.run(
            ["git", "-C", repo, "worktree", "list", "--porcelain"],
            capture_output=True, text=True,
        )
    except FileNotFoundError:
        fail("git is not installed")
    if result.returncode != 0:
        fail(result.stderr.strip() or "git worktree list failed")
    found: dict[str, list[str]] = {}
    path = None
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            path = line[9:]
            found[path] = []
        elif path is not None and (line == "locked" or line.startswith("locked ")):
            reason = line[7:].strip()
            found[path].append(f"locked: {reason}" if reason else "locked")
    main = next(iter(found), None)
    found.pop(main, None)
    return found


def owner(path: str, roots: dict[str, str]) -> str | None:
    """Return the worktree whose resolved root is the deepest one that contains path."""
    path = os.path.realpath(path)
    best = None
    for root in roots:
        if path == root or path.startswith(root.rstrip(os.sep) + os.sep):
            if best is None or len(root) > len(best):
                best = root
    return roots[best] if best else None


def current_session_pids() -> set[str]:
    """Return this process and its ancestors, which belong to the current session."""
    pids, pid = {str(os.getpid())}, str(os.getppid())
    try:
        result = subprocess.run(["ps", "-A", "-o", "pid=,ppid="], capture_output=True, text=True)
        parent = dict(line.split() for line in result.stdout.splitlines() if len(line.split()) == 2)
    except FileNotFoundError:
        parent = {}
    while pid and pid != "0" and pid not in pids:
        pids.add(pid)
        pid = parent.get(pid, "")
    return pids


def process_dirs(skip: set[str]) -> list[tuple[str, str, str]]:
    """Return (pid, command, working directory) for each visible process outside skip."""
    try:
        proc = subprocess.Popen(["lsof", "-w", "-d", "cwd", "-Fpcn"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except FileNotFoundError:
        fail("lsof is not installed, so running processes cannot be checked")
    output, error = proc.communicate()
    if not output and proc.returncode != 0:
        fail(error.strip() or "lsof failed")
    skip = skip | {str(proc.pid)}
    found, pid, command = [], "", ""
    for line in output.splitlines():
        field, value = line[:1], line[1:]
        if field == "p":
            pid, command = value, ""
        elif field == "c":
            command = value
        elif field == "n" and pid not in skip:
            found.append((pid, command, value))
    return found


def config_dirs() -> dict[str, set[str]]:
    """Return the Claude Code and Codex config folders of this and the running sessions.

    `ps axeww` prints the environment of the processes of the same user on
    macOS and Linux. A folder path with a space is not found this way.
    """
    home = os.path.expanduser("~")
    found = {
        "CLAUDE_CONFIG_DIR": {os.path.join(home, ".claude"), os.environ.get("CLAUDE_CONFIG_DIR", "")},
        "CODEX_HOME": {os.path.join(home, ".codex"), os.environ.get("CODEX_HOME", "")},
    }
    try:
        result = subprocess.run(["ps", "axeww", "-o", "command="], capture_output=True, text=True)
    except FileNotFoundError:
        fail("ps is not installed, so the config folders of running sessions cannot be found")
    if result.returncode != 0:
        fail(result.stderr.strip() or "ps axeww failed")
    for name, value in CONFIG_VAR.findall(result.stdout):
        found[name].add(value)
    return {name: values - {""} for name, values in found.items()}


def recent_logs(roots: list[str], since: float) -> list[tuple[str, float]]:
    """Return (path, change time) for each JSONL log under roots changed after since."""
    found = {}
    for root in roots:
        for folder, _, names in os.walk(root):
            for name in names:
                if not name.endswith(".jsonl"):
                    continue
                path = os.path.join(folder, name)
                try:
                    changed = os.stat(path).st_mtime
                except OSError:
                    continue
                if changed >= since:
                    found[os.path.realpath(path)] = changed
    return sorted(found.items(), key=lambda item: -item[1])


def own_log(path: str, idents: list[str]) -> bool:
    """Tell whether a log belongs to the current session.

    Claude Code names a session log <id>.jsonl and keeps subagent logs under
    <id>/. A Codex rollout file name ends with -<thread id>.jsonl.
    """
    parts = path.split(os.sep)
    name = parts[-1]
    return any(
        ident in parts[:-1] or name == f"{ident}.jsonl" or name.endswith(f"-{ident}.jsonl")
        for ident in idents
    )


def log_dirs(path: str) -> set[str]:
    """Return the working directories that a session log records.

    Claude Code records cwd on each entry. Codex records it in the payload of
    its session_meta and turn_context entries. Only the first line and the
    last TAIL bytes are read, because a log can be large.
    """
    dirs = set()
    try:
        with open(path, "rb") as handle:
            lines = [handle.readline()]
            size = handle.seek(0, os.SEEK_END)
            handle.seek(max(0, size - TAIL))
            lines += handle.read().splitlines()
    except OSError:
        return dirs
    for line in lines:
        if b'"cwd"' not in line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if not isinstance(record, dict):
            continue
        payload = record.get("payload")
        for cwd in (record.get("cwd"), payload.get("cwd") if isinstance(payload, dict) else None):
            if isinstance(cwd, str):
                dirs.add(cwd)
    return dirs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default=".", help="repository checkout (default: .)")
    args = parser.parse_args()

    # For each linked worktree, the evidence of each kind, in report order.
    evidence = {
        path: {"lock": locks, "process": [], "log": []}
        for path, locks in linked_worktrees(args.repo).items()
    }
    roots = {os.path.realpath(path): path for path in evidence}
    for pid, command, cwd in process_dirs(current_session_pids()):
        path = owner(cwd, roots)
        if path is not None:
            evidence[path]["process"].append(f"process {pid} ({command})")
    config = config_dirs()
    log_roots = ([os.path.join(d, "projects") for d in config["CLAUDE_CONFIG_DIR"]]
                 + [os.path.join(d, "sessions") for d in config["CODEX_HOME"]])
    now = time.time()
    idents = [os.environ.get(name, "") for name in ("CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID")]
    idents = [ident for ident in idents if ident]
    for log, changed in recent_logs(log_roots, now - WINDOW_MINUTES * 60):
        if own_log(log, idents):
            continue
        for path in {owner(cwd, roots) for cwd in log_dirs(log)} - {None}:
            evidence[path]["log"].append(f"session log {log} ({(now - changed) / 60:.0f} min ago)")
    for path, kinds in evidence.items():
        # Name the first item of each kind and count the others; the newest
        # log comes first.
        found = [
            items[0] + (f" and {len(items) - 1} more" if len(items) > 1 else "")
            for items in kinds.values() if items
        ]
        if found:
            print(f"{path}\t{'; '.join(found)}")

if __name__ == "__main__":
    main()
