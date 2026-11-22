#!/usr/bin/env python3
"""Run a test suite one at a time per repository, and reuse a recorded pass.

Usage:

    python3 run_suite.py [--rerun] -- <command> [args...]

Lock. The script takes an exclusive lock on run-suite.lock in the Git common
folder (git rev-parse --git-common-dir), so all worktrees of one repository
share it. When another run holds the lock, the script prints one line to
stderr with the holder's PID, command, folder, and start time, and then waits.

Recorded pass. A run passes when the command exits 0. When the working tree
was clean (git status --porcelain printed nothing, untracked files included)
before and after the run, with the same HEAD^{tree}, the script records the
pass in run-suite-passes.json in the Git common folder: the tree hash, the
command, the folder relative to the worktree root, the time, and the HEAD
commit. A dirty tree records nothing.

Reuse. After it takes the lock, the script looks for a recorded pass with the
same tree, command, and relative folder. When the tree is clean and such a
pass exists, it does not run the command. It prints the time and commit of
that pass and exits 0. So a run that waited for the lock reuses the pass of
the run before it, and a squash merge whose tree equals the pull request head
reuses the pass of that head. --rerun always runs the command.

Output. The command's stdout and stderr stream together as the command runs.
Then the script prints a summary: the failing test IDs and the totals lines of
unittest and pytest output, and last the exit status. For other output, the
summary has only the exit status.

Exit status: the exit status of the command (127 when the command is not
found, 126 when it cannot run, 128 + N after signal N); 0 when the script
reuses a recorded pass; 2 outside a Git checkout or without a command.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO

LOCK = "run-suite.lock"
PASSES = "run-suite-passes.json"
# The script keeps only the newest records.
KEEP = 200

# unittest: "FAIL: test_x (pkg.mod.Class)", or "(pkg.mod.Class.test_x)" on Python 3.11 and newer.
UNITTEST_FAILURE = re.compile(r"(FAIL|ERROR): (\w+) \(([\w.]+)\)(.*)")
UNITTEST_TOTALS = re.compile(r"Ran \d+ tests? in \S+|OK|OK \(.*\)|FAILED \(.*\)")
# pytest: "FAILED tests/test_x.py::test_y - AssertionError" in the short test summary.
PYTEST_FAILURE = re.compile(r"(FAILED|ERROR) (\S.*?)(?: - .*)?")
# pytest: "==== 1 failed, 2 passed in 0.12s ====", with or without the equals signs.
PYTEST_TOTALS = re.compile(r"(?:=+ )?(?:\d+ \w+(?:, \d+ \w+)*|no tests ran) in \d[\d.]*s\b.*")


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


def take_lock(common: Path, command: list[str]) -> TextIO:
    """Take the repository lock, and wait for it when another run holds it."""
    handle = open(common / LOCK, "a+")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.seek(0)
        try:
            holder = json.loads(handle.read())
            who = (f"PID {holder['pid']} ({holder['command']}) in {holder['folder']}, "
                   f"started {holder['start']}")
        except (ValueError, KeyError, TypeError):
            who = "another run (its details are not written yet)"
        print(f"run_suite: waiting for the suite lock, held by {who}", file=sys.stderr, flush=True)
        fcntl.flock(handle, fcntl.LOCK_EX)
    # The lock file holds the details of its holder, for runs that wait.
    handle.seek(0)
    handle.truncate()
    handle.write(json.dumps({"pid": os.getpid(), "command": shlex.join(command),
                             "folder": os.getcwd(), "start": now()}))
    handle.flush()
    return handle


def load_passes(path: Path) -> list[dict]:
    try:
        passes = json.loads(path.read_text())
    except (OSError, ValueError):
        return []
    if not isinstance(passes, list):
        return []
    return [entry for entry in passes if isinstance(entry, dict)]


def record_pass(path: Path, entry: dict) -> None:
    """Add a pass to the records. The caller holds the lock."""
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
    passes_file = Path(common) / PASSES
    folder = Path(os.path.relpath(Path.cwd().resolve(), Path(top).resolve())).as_posix()

    lock = take_lock(Path(common), command)
    tree = clean_tree()
    key = {"tree": tree, "command": command, "folder": folder}
    if tree and not args.rerun:
        for entry in reversed(load_passes(passes_file)):
            if all(entry.get(name) == value for name, value in key.items()):
                print(f"run_suite: a pass is recorded for tree {tree[:12]} at {entry.get('time')} "
                      f"(commit {str(entry.get('commit'))[:12]}), so the command did not run. "
                      f"Use --rerun to run it again.", flush=True)
                sys.exit(0)
    commit = git("rev-parse", "HEAD")

    status, failures, totals = run(command)
    if status == 0:
        if tree and clean_tree() == tree:
            record_pass(passes_file, {**key, "time": now(), "commit": commit})
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
    lines.append(f"Exit status: {status}")
    print("\n".join(lines), flush=True)
    sys.exit(status)


if __name__ == "__main__":
    main()
