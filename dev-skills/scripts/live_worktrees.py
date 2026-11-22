#!/usr/bin/env python3
"""List the worktrees of a repository that another live session may use.

repo-cleanup runs this script before it removes worktrees. Each output line is
a worktree path, as `git worktree list` prints it, a tab, and the evidence:
a Git lock, a running process with its working directory in the worktree,
a Claude Code or Codex session log, changed in the last 60 minutes, that
records a working directory in the worktree, or an Antigravity conversation,
changed in the last 60 minutes, that started in the worktree. The main
checkout is never listed, because cleanup never removes it.

Antigravity conversations are the rows of conversation_summaries.db in
~/.gemini/antigravity-cli (CLI), ~/.gemini/antigravity (app), and the
antigravity-acp folder of each T3 Code profile in
~/.t3/userdata/providers/antigravity/. The script reads a temporary copy of
each database. A conversation counts for the worktree that holds one of its
workspace_uris paths when its last_modified_time is in the window. When that
time cannot be read, the worktree is listed with "time unknown".

The current session is left out: this process, its ancestors, and the logs
named by CLAUDE_CODE_SESSION_ID or CODEX_THREAD_ID. An Antigravity
conversation of the current session is not left out. The exit status is 0
when the check ran and 1 when it could not run, for example without lsof or
ps, or with an Antigravity folder, database, or recent conversation that
cannot be read.

Limit: a session with no process in the worktree and no log change in the
last 60 minutes is not found, for example a Codex thread, whose app server
runs in another folder, that waits for an hour. An Antigravity conversation
that started in another folder and moved into the worktree is not found.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from contextlib import closing
from datetime import datetime
from typing import NoReturn
from urllib.parse import unquote, urlsplit

WINDOW_MINUTES = 60
TAIL = 4 * 1024 * 1024
CONFIG_VAR = re.compile(r"(?:^|\s)(CLAUDE_CONFIG_DIR|CODEX_HOME)=(\S+)")
# Antigravity writes last_modified_time as text, for example
# "2026-11-21 04:59:57.48579+00:00".
ANTIGRAVITY_TIME = re.compile(r"(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})(?:[.,]\d+)?(Z|[+-]\d{2}:?\d{2})")


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


def antigravity_dirs() -> list[str]:
    """Return the Antigravity folders that can hold conversation_summaries.db."""
    home = os.path.expanduser("~")
    profiles = os.path.join(home, ".t3", "userdata", "providers", "antigravity")
    try:
        names = sorted(os.listdir(profiles))
    except (FileNotFoundError, NotADirectoryError):
        names = []
    except OSError as error:
        fail(f"cannot list the T3 Code Antigravity profiles in {profiles} ({error})")
    return [os.path.join(home, ".gemini", "antigravity-cli"), os.path.join(home, ".gemini", "antigravity"),
            *(os.path.join(profiles, name, "antigravity-acp") for name in names)]


def conversations(folder: str) -> list[tuple]:
    """Return (conversation_id, workspace_uris, last_modified_time) for each row in folder.

    Read a temporary copy of conversation_summaries.db and its -wal and -shm
    files, so that a live database stays unchanged. A folder without the
    database has no rows. A database that cannot be read stops the script.
    """
    database = os.path.join(folder, "conversation_summaries.db")
    try:
        os.stat(database)
    except (FileNotFoundError, NotADirectoryError):
        return []
    except OSError as error:  # For example, a folder that cannot be searched.
        fail(f"cannot read the Antigravity database {database} ({error})")
    with tempfile.TemporaryDirectory() as copy:
        for suffix in ("", "-wal", "-shm"):
            try:
                shutil.copyfile(database + suffix, os.path.join(copy, "conversation_summaries.db" + suffix))
            except OSError as error:
                if suffix and isinstance(error, FileNotFoundError):
                    continue  # A database without a write-ahead log is complete.
                fail(f"cannot copy the Antigravity database {database + suffix} ({error})")
        try:
            with closing(sqlite3.connect(os.path.join(copy, "conversation_summaries.db"))) as connection:
                return connection.execute(
                    "SELECT conversation_id, workspace_uris, last_modified_time FROM conversation_summaries"
                ).fetchall()
        except sqlite3.Error as error:
            fail(f"cannot read the Antigravity database {database} ({error})")


def changed_at(value: object) -> float | None:
    """Return a last_modified_time value in seconds since the epoch, or None.

    The fraction of a second is dropped, because Python before 3.11 reads only
    3 or 6 digits of it.
    """
    match = ANTIGRAVITY_TIME.fullmatch(value.strip()) if isinstance(value, str) else None
    if match is None:
        return None
    zone = "+00:00" if match.group(3) == "Z" else match.group(3)
    if ":" not in zone:
        zone = f"{zone[:3]}:{zone[3:]}"
    try:
        return datetime.fromisoformat(f"{match.group(1)}T{match.group(2)}{zone}").timestamp()
    except ValueError:
        return None


def workspace_paths(uris: object) -> list[str]:
    """Return the absolute local paths in a workspace_uris JSON list; raise ValueError.

    A URI of another scheme or host, such as a remote workspace, has no local
    path. An entry that is not a URI cannot be read.
    """
    if not isinstance(uris, str):
        raise ValueError("workspace_uris is not text")
    workspaces = json.loads(uris)
    if not isinstance(workspaces, list):
        raise ValueError("workspace_uris is not a list")
    paths = []
    for uri in workspaces:
        parts = urlsplit(uri) if isinstance(uri, str) else None
        if parts is None or not parts.scheme:
            raise ValueError("an entry is not a URI")
        if parts.scheme == "file" and parts.netloc in ("", "localhost"):
            path = unquote(parts.path)
            if not os.path.isabs(path):
                raise ValueError("a file URI has no absolute path")
            paths.append(path)
    return paths


def antigravity_evidence(roots: dict[str, str], now: float) -> list[tuple[str, str]]:
    """Return (worktree, evidence) for each recent Antigravity conversation, newest first.

    A conversation whose time cannot be read counts as recent, and one whose
    workspace_uris cannot be read stops the script, so that no live worktree
    is missed.
    """
    found = []
    since = now - WINDOW_MINUTES * 60
    for folder in antigravity_dirs():
        for conversation, uris, modified in conversations(folder):
            changed = changed_at(modified)
            if changed is not None and changed < since:
                continue
            try:
                paths = workspace_paths(uris)
            except ValueError as error:
                fail(f"cannot read workspace_uris of Antigravity conversation {conversation} in {folder} ({error})")
            age = "time unknown" if changed is None else f"{(now - changed) / 60:.0f} min ago"
            for path in {owner(workspace, roots) for workspace in paths} - {None}:
                item = f"Antigravity conversation {conversation} in {folder} ({age})"
                found.append((float("inf") if changed is None else changed, path, item))
    found.sort(key=lambda entry: -entry[0])
    return [(path, item) for _, path, item in found]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default=".", help="repository checkout (default: .)")
    args = parser.parse_args()

    # For each linked worktree, the evidence of each kind, in report order.
    evidence = {
        path: {"lock": locks, "process": [], "log": [], "antigravity": []}
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
    for path, item in antigravity_evidence(roots, now):
        evidence[path]["antigravity"].append(item)
    for path, kinds in evidence.items():
        # Name the first item of each kind and count the others; the newest
        # log and the newest conversation come first.
        found = [
            items[0] + (f" and {len(items) - 1} more" if len(items) > 1 else "")
            for items in kinds.values() if items
        ]
        if found:
            print(f"{path}\t{'; '.join(found)}")

if __name__ == "__main__":
    main()
