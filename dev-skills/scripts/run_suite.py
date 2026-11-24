#!/usr/bin/env python3
"""Run each test suite one at a time per repository, and reuse a recorded pass.

Usage:

    python3 run_suite.py [--rerun] -- <command> [args...]

Suite lock. A suite is a command run in a folder relative to the worktree
root. The script takes an exclusive lock for the suite: run-suite-<hash>.lock
in the Git common folder (git rev-parse --git-common-dir), where <hash> is a
short hash of the command and the relative folder. All worktrees of one
repository share each lock. So two runs of the same suite run one at a time,
and runs of different suites run in parallel, except while a priority marker
names another worktree (see below). When another run holds the suite lock,
the script prints one line to stderr with the holder's PID, command, folder,
and start time, and then waits.

Priority marker. A repository's merge-lock tool can give the worktree that
holds its merge lock priority over the suites of the other worktrees. The
marker is run-suite-priority.json in the Git common folder: a JSON object
with two required fields, "worktree", the absolute path of the worktree
root, and "started", a UTC time in the form %Y-%m-%dT%H:%M:%SZ. The script
ignores other fields. The merge-lock tool writes the file when it takes or
renews its lock, and removes it when it releases the lock. This script only
reads it. A marker is fresh for 60 minutes from "started". While a fresh
marker names another worktree, each run waits before it takes its suite
lock, for every suite, and reads the marker again each second. After it
takes the suite lock, the script reads the marker again. When a fresh marker
names another worktree, it releases the suite lock and waits again. A run
whose command already runs is not stopped. A run in the named worktree does
not wait. The script compares the two paths after it resolves symbolic
links. A missing, unreadable, or stale marker gives no priority. So does a
marker that is not a JSON object with both fields, that has a time in
another form or after the current time, or that names a folder that does
not exist. When the marker wait starts, the script prints one line to
stderr with the named worktree and the time that the marker gives.

Recorded pass. A run passes when the command exits 0. When the working tree
was clean (git status --porcelain printed nothing, untracked files included)
before and after the run, with the same HEAD^{tree}, the script records the
pass in run-suite-passes.json in the Git common folder: the tree hash, the
command, the folder relative to the worktree root, the time, and the HEAD
commit. A dirty tree records nothing. To change the records, the script
takes a short lock on run-suite-passes.lock in the Git common folder, so
runs of different suites that end at the same time keep each other's
records. When another run holds that lock, the script prints
"run_suite: waiting for the pass-records lock" to stderr, and then waits.

Reuse. After it takes the suite lock, the script looks for a recorded pass
with the same tree, command, and relative folder. When the tree is clean and
such a pass exists, it does not run the command. It prints the time and
commit of that pass and exits 0. So a run that waited for the suite lock
reuses the pass of the run before it, and a squash merge whose tree equals
the pull request head reuses the pass of that head. --rerun always runs the
command.

Output. The command's stdout and stderr stream together as the command runs.
Then the script prints a summary: the failing test IDs and the totals lines of
unittest and pytest output, the marker wait, the lock wait, and last the exit
status. For other output, the summary has no failing tests or totals. The
marker wait is one line, only after the script waited for a priority marker:
"Priority marker wait: <N> s, for <worktree>", with the total wait time in
whole seconds and the worktree that the first stderr line names. The lock
wait is one line, only after the script waited for the suite lock:
"Suite lock wait: <N> s, held by PID <pid> (<command>) in <folder>", with the
total wait time in whole seconds and the holder that the first stderr line
names. When a later run held the lock last, the line adds
", and last by PID <pid> (<command>) in <folder>". When the first holder had
not written its details, the line names the last holder; when neither had, it
names "another run". A run that reuses a recorded pass prints no summary;
after a wait, it prints the wait lines as its last lines.

Exit status: the exit status of the command (127 when the command is not
found, 126 when it cannot run, 128 + N after signal N); 0 when the script
reuses a recorded pass; 2 outside a Git checkout or without a command.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO

PASSES = "run-suite-passes.json"
PASSES_LOCK = "run-suite-passes.lock"
PRIORITY = "run-suite-priority.json"
# A priority marker is fresh for this many seconds from its "started" time.
PRIORITY_FRESH = 60 * 60
# While it waits for a priority marker, the script reads it this often, in seconds.
PRIORITY_POLL = 1.0
TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
TIME_FORM = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ")
# The script keeps only the newest records.
KEEP = 200

# unittest: "FAIL: test_x (pkg.mod.Class)", or "(pkg.mod.Class.test_x)" on Python 3.11 and newer.
UNITTEST_FAILURE = re.compile(r"(FAIL|ERROR): (\w+) \(([\w.]+)\)(.*)")
UNITTEST_TOTALS = re.compile(r"Ran \d+ tests? in \S+|OK|OK \(.*\)|FAILED \(.*\)")
# pytest: "FAILED tests/test_x.py::test_y - AssertionError" in the short test summary.
PYTEST_FAILURE = re.compile(r"(FAILED|ERROR) (\S.*?)(?: - .*)?")
# pytest: "==== 1 failed, 2 passed in 0.12s ====", with or without the equals signs.
PYTEST_TOTALS = re.compile(r"(?:=+ )?(?:\d+ \w+(?:, \d+ \w+)*|no tests ran) in \d[\d.]*s\b.*")
# The lock wait line shows a line break of a holder's command as \n.
ESCAPE_LINE_BREAKS = str.maketrans({"\n": "\\n", "\r": "\\r"})


def now() -> str:
    return datetime.now(timezone.utc).strftime(TIME_FORMAT)


def git(*args: str) -> str | None:
    """Return the stripped output of a git command, or None when it fails."""
    try:
        result = subprocess.run(["git", *args], capture_output=True, text=True)
    except OSError:
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def clean_tree() -> str | None:
    """Return HEAD^{tree} when the working tree is clean, else None."""
    if git("status", "--porcelain", "--untracked-files=normal") != "":
        return None
    return git("rev-parse", "HEAD^{tree}")


def read_holder(handle: TextIO) -> dict | None:
    """Return the details that the last holder wrote to the lock file, or None."""
    handle.seek(0)
    try:
        holder = json.loads(handle.read())
        return {name: holder[name] for name in ("pid", "command", "folder", "start")}
    except (ValueError, KeyError, TypeError):
        return None


def describe(holder: dict | None) -> str:
    """Name a lock holder by its PID, command, and folder."""
    if holder is None:
        return "another run (its details are not written yet)"
    return f"PID {holder['pid']} ({holder['command']}) in {holder['folder']}"


def suite_lock_path(common: Path, suite: dict) -> Path:
    """Return the lock file of a suite: a short hash of its command and folder."""
    digest = hashlib.sha256(json.dumps(suite, sort_keys=True).encode()).hexdigest()
    return common / f"run-suite-{digest[:16]}.lock"


def priority_holder(common: Path, top: str) -> dict | None:
    """Return a fresh priority marker that names another worktree, or None.

    A missing, unreadable, stale, or malformed marker, and a marker that names
    a folder that does not exist or this worktree, give no priority.
    """
    try:
        marker = json.loads((common / PRIORITY).read_text())
        worktree, started = marker["worktree"], marker["started"]
        if not TIME_FORM.fullmatch(started):
            return None
        when = datetime.strptime(started, TIME_FORMAT).replace(tzinfo=timezone.utc)
    except (OSError, ValueError, KeyError, TypeError):
        return None
    age = (datetime.now(timezone.utc) - when).total_seconds()
    if not 0 <= age < PRIORITY_FRESH:
        return None
    if not isinstance(worktree, str) or not os.path.isabs(worktree) \
            or not os.path.isdir(worktree):
        return None
    if os.path.realpath(worktree) == os.path.realpath(top):
        return None
    return {"worktree": worktree, "started": started}


def wait_for_priority(common: Path, top: str) -> tuple[float, str | None]:
    """Wait while a fresh priority marker names another worktree.

    Return the seconds of the wait and the worktree that the marker named, or
    0 and None when the script did not wait.
    """
    marker = priority_holder(common, top)
    if marker is None:
        return 0.0, None
    print(f"run_suite: waiting for the priority marker, which names {marker['worktree']}, "
          f"started {marker['started']}", file=sys.stderr, flush=True)
    begin = time.monotonic()
    while priority_holder(common, top) is not None:
        time.sleep(PRIORITY_POLL)
    return time.monotonic() - begin, marker["worktree"]


def take_lock(path: Path, command: list[str], common: Path,
              top: str) -> tuple[TextIO, list[str]]:
    """Take a suite lock, after the waits for a priority marker and for the lock.

    Return the lock file, and the wait lines of the summary.
    """
    marker_seconds, marker_worktree = 0.0, None
    lock_seconds, first, last, lock_waited = 0.0, None, None, False
    while True:
        seconds, worktree = wait_for_priority(common, top)
        marker_seconds += seconds
        marker_worktree = marker_worktree or worktree
        handle = open(path, "a+")
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            holder = read_holder(handle)
            started = f", started {holder['start']}" if holder else ""
            print(f"run_suite: waiting for the suite lock, held by {describe(holder)}{started}",
                  file=sys.stderr, flush=True)
            begin = time.monotonic()
            fcntl.flock(handle, fcntl.LOCK_EX)
            lock_seconds += time.monotonic() - begin
            lock_waited = True
            first = first or holder
            # Holders do not clear the lock file, so it now names the last holder.
            last = read_holder(handle)
        # A marker can appear while the run waits for the suite lock.
        if priority_holder(common, top) is None:
            break
        handle.close()
    wait_lines = []
    if marker_worktree:
        wait_lines.append(f"Priority marker wait: {round(marker_seconds)} s, "
                          f"for {marker_worktree}")
    if lock_waited:
        holders = describe(first or last)
        if first and last and last != first:
            holders += f", and last by {describe(last)}"
        wait_lines.append(f"Suite lock wait: {round(lock_seconds)} s, held by {holders}")
    wait_lines = [line.translate(ESCAPE_LINE_BREAKS) for line in wait_lines]
    # The lock file holds the details of its holder, for runs that wait.
    handle.seek(0)
    handle.truncate()
    handle.write(json.dumps({"pid": os.getpid(), "command": shlex.join(command),
                             "folder": os.getcwd(), "start": now()}))
    handle.flush()
    return handle, wait_lines


def load_passes(path: Path) -> list[dict]:
    try:
        passes = json.loads(path.read_text())
    except (OSError, ValueError):
        return []
    if not isinstance(passes, list):
        return []
    return [entry for entry in passes if isinstance(entry, dict)]


def record_pass(common: Path, entry: dict) -> None:
    """Add a pass to the records, under the pass-records lock."""
    with open(common / PASSES_LOCK, "a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("run_suite: waiting for the pass-records lock", file=sys.stderr, flush=True)
            fcntl.flock(lock, fcntl.LOCK_EX)
        path = common / PASSES
        passes = (load_passes(path) + [entry])[-KEEP:]
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(json.dumps(passes, indent=1) + "\n")
        os.replace(temporary, path)


def parse(line: str, failures: list[str], totals: list[str]) -> None:
    """Add a failing test ID or a totals line of unittest or pytest output."""
    unittest_failure = UNITTEST_FAILURE.fullmatch(line)
    pytest_failure = PYTEST_FAILURE.fullmatch(line)
    if UNITTEST_TOTALS.fullmatch(line) or PYTEST_TOTALS.fullmatch(line):
        totals.append(line)
    elif unittest_failure:
        kind, name, owner, rest = unittest_failure.groups()
        test_id = owner if owner.endswith("." + name) else f"{owner}.{name}"
        failures.append(f"{test_id}{rest} ({kind})")
    elif pytest_failure:
        failures.append(f"{pytest_failure.group(2)} ({pytest_failure.group(1)})")


def run(command: list[str]) -> tuple[int, list[str], list[str]]:
    """Stream the command's output, and return its exit status, failures, and totals."""
    failures: list[str] = []
    totals: list[str] = []
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except FileNotFoundError:
        print(f"run_suite: command not found: {command[0]}", file=sys.stderr)
        return 127, failures, totals
    except OSError as error:
        print(f"run_suite: cannot run {command[0]}: {error}", file=sys.stderr)
        return 126, failures, totals
    # Write each chunk at once, so progress dots show before their line ends.
    out, pending = sys.stdout.buffer, b""
    while True:
        chunk = process.stdout.read1(65536)
        if not chunk:
            break
        out.write(chunk)
        out.flush()
        *lines, pending = (pending + chunk).split(b"\n")
        for raw in lines:
            parse(raw.decode(errors="replace").rstrip(), failures, totals)
    parse(pending.decode(errors="replace").rstrip(), failures, totals)
    status = process.wait()
    return (128 - status if status < 0 else status), list(dict.fromkeys(failures)), totals


def main() -> None:
    parser = argparse.ArgumentParser(usage="%(prog)s [--rerun] -- <command> [args...]",
                                     description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rerun", action="store_true",
                        help="run the command even when a pass is recorded for the tree")
    parser.add_argument("command", nargs=argparse.REMAINDER,
                        help="the test command and its arguments, after --")
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("give a command after --")
    common_dir = git("rev-parse", "--path-format=absolute", "--git-common-dir")
    top = git("rev-parse", "--show-toplevel")
    if not common_dir or not top:
        print("run_suite: not inside a Git checkout", file=sys.stderr)
        sys.exit(2)
    common = Path(common_dir)
    folder = Path(os.path.relpath(Path.cwd().resolve(), Path(top).resolve())).as_posix()
    # A suite is a command in a folder: the key of its lock and of its recorded pass.
    suite = {"command": command, "folder": folder}

    lock, wait_lines = take_lock(suite_lock_path(common, suite), command, common, top)
    tree = clean_tree()
    key = {"tree": tree, **suite}
    if tree and not args.rerun:
        for entry in reversed(load_passes(common / PASSES)):
            if all(entry.get(name) == value for name, value in key.items()):
                print(f"run_suite: a pass is recorded for tree {tree[:12]} at {entry.get('time')} "
                      f"(commit {str(entry.get('commit'))[:12]}), so the command did not run. "
                      f"Use --rerun to run it again.", flush=True)
                for line in wait_lines:
                    print(line, flush=True)
                sys.exit(0)
    commit = git("rev-parse", "HEAD")

    status, failures, totals = run(command)
    if status == 0:
        if tree and clean_tree() == tree:
            record_pass(common, {**key, "time": now(), "commit": commit})
            print(f"\nrun_suite: recorded the pass for tree {tree[:12]}.")
        else:
            print("\nrun_suite: did not record the pass: the working tree was not clean, "
                  "or it changed during the run.")
    lock.close()

    lines = ["", "==== run_suite summary ===="]
    if failures:
        lines += [f"Failing tests ({len(failures)}):"] + [f"  {failure}" for failure in failures]
    if totals:
        lines += ["Totals:"] + [f"  {total}" for total in totals]
    lines += wait_lines
    lines.append(f"Exit status: {status}")
    print("\n".join(lines), flush=True)
    sys.exit(status)


if __name__ == "__main__":
    main()
