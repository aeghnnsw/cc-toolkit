#!/usr/bin/env python3
"""Run each test suite one at a time per repository, and reuse a recorded pass.

Usage:

    python3 run_suite.py [--rerun] -- <command> [args...]

Suite lock. A suite is a command run in a folder relative to the worktree
root. The script takes an exclusive lock for the suite: run-suite-<hash>.lock
in the Git common folder (git rev-parse --git-common-dir), where <hash> is a
short hash of the command and the relative folder. All worktrees of one
repository share each lock. So two runs of the same suite run one at a time,
and runs of different suites run in parallel. When another run holds the
suite lock, the script prints one line to stderr with the holder's PID,
command, folder, and start time, and then waits.

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
unittest and pytest output, the lock wait, and last the exit status. For other
output, the summary has no failing tests or totals. The lock wait is one line,
only after the script waited for the suite lock: "Suite lock wait: <N> s, held by
PID <pid> (<command>) in <folder>", with the wait time in whole seconds and the
holder that the stderr line names. When a later run held the lock last, the
line adds ", and last by PID <pid> (<command>) in <folder>". When the first
holder had not written its details, the line names the last holder; when
neither had, it names "another run". A run that reuses a recorded pass prints
no summary; after a wait, it prints the lock wait as its last line.

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
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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


def suite_lock(common: Path, command: list[str], folder: str) -> Path:
    """Return the lock file of a suite, named from the key of its recorded pass."""
    key = json.dumps({"command": command, "folder": folder}, sort_keys=True)
    return common / f"run-suite-{hashlib.sha256(key.encode()).hexdigest()[:16]}.lock"


def take_lock(path: Path, command: list[str]) -> tuple[TextIO, str | None]:
    """Take a suite lock, and wait for it when another run holds it.

    Return the lock file, and after a wait the lock wait line of the summary.
    """
    handle = open(path, "a+")
    wait_line = None
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        first = read_holder(handle)
        started = f", started {first['start']}" if first else ""
        print(f"run_suite: waiting for the suite lock, held by {describe(first)}{started}",
              file=sys.stderr, flush=True)
        begin = time.monotonic()
        fcntl.flock(handle, fcntl.LOCK_EX)
        seconds = round(time.monotonic() - begin)
        # Holders do not clear the lock file, so it now names the last holder.
        last = read_holder(handle)
        holders = describe(first or last)
        if first and last and last != first:
            holders += f", and last by {describe(last)}"
        wait_line = f"Suite lock wait: {seconds} s, held by {holders}".translate(
            ESCAPE_LINE_BREAKS)
    # The lock file holds the details of its holder, for runs that wait.
    handle.seek(0)
    handle.truncate()
    handle.write(json.dumps({"pid": os.getpid(), "command": shlex.join(command),
                             "folder": os.getcwd(), "start": now()}))
    handle.flush()
    return handle, wait_line


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
    common = git("rev-parse", "--path-format=absolute", "--git-common-dir")
    top = git("rev-parse", "--show-toplevel")
    if not common or not top:
        print("run_suite: not inside a Git checkout", file=sys.stderr)
        sys.exit(2)
    common = Path(common)
    folder = Path(os.path.relpath(Path.cwd().resolve(), Path(top).resolve())).as_posix()

    lock, wait_line = take_lock(suite_lock(common, command, folder), command)
    tree = clean_tree()
    key = {"tree": tree, "command": command, "folder": folder}
    if tree and not args.rerun:
        for entry in reversed(load_passes(common / PASSES)):
            if all(entry.get(name) == value for name, value in key.items()):
                print(f"run_suite: a pass is recorded for tree {tree[:12]} at {entry.get('time')} "
                      f"(commit {str(entry.get('commit'))[:12]}), so the command did not run. "
                      f"Use --rerun to run it again.", flush=True)
                if wait_line:
                    print(wait_line, flush=True)
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
    if wait_line:
        lines.append(wait_line)
    lines.append(f"Exit status: {status}")
    print("\n".join(lines), flush=True)
    sys.exit(status)


if __name__ == "__main__":
    main()
