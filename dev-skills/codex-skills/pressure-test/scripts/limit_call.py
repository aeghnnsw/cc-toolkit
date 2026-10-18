#!/usr/bin/env python3
"""Run one command with a time limit for the pressure-test skill.

Usage: python3 limit_call.py <seconds> <command> [<argument> ...]

The command runs in a new process group and shares the helper's stdin,
stdout, and stderr. When the command ends within the limit, the helper exits
with the command's exit code, or 128 + N when signal N ended it.

At the limit, the helper sends SIGTERM to the command's process group, waits
up to 5 seconds for the command to end, sends SIGKILL to the group, reaps the
command, and exits 124. When the helper gets SIGTERM, SIGINT, or SIGHUP, it
ends the command the same way and exits 128 + the signal number. So the
helper does not exit while the command runs, and a retry cannot overlap it.

The helper exits 2 for bad arguments, 126 when the command cannot run, and
127 when the command is not found.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys

TIMEOUT_EXIT = 124
USAGE_EXIT = 2
CANNOT_RUN_EXIT = 126
NOT_FOUND_EXIT = 127
GRACE_SECONDS = 5
STOP_SIGNALS = (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)


class Stopped(Exception):
    """The helper got a stop signal."""

    def __init__(self, signum: int):
        super().__init__(signum)
        self.signum = signum


def stop(signum: int, _frame: object) -> None:
    raise Stopped(signum)


def end(process: subprocess.Popen) -> None:
    """Send SIGTERM to the command's group, wait for the grace period, send SIGKILL to the group, and reap."""
    for signum in STOP_SIGNALS:  # a second signal must not cut the cleanup short
        signal.signal(signum, signal.SIG_IGN)
    with contextlib.suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGTERM)
    with contextlib.suppress(subprocess.TimeoutExpired):
        process.wait(GRACE_SECONDS)
    with contextlib.suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGKILL)
    process.wait()


def usage(message: str) -> int:
    print(f"limit_call.py: {message}\nusage: limit_call.py <seconds> <command> [<argument> ...]", file=sys.stderr)
    return USAGE_EXIT


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        return usage("missing seconds or command")
    try:
        seconds = float(argv[1])
    except ValueError:
        seconds = 0.0
    if not seconds > 0:
        return usage(f"seconds must be a positive number: {argv[1]}")
    for signum in STOP_SIGNALS:  # set before the start, so no signal can leave the command running
        signal.signal(signum, stop)
    try:
        process = subprocess.Popen(argv[2:], start_new_session=True)
    except FileNotFoundError:
        print(f"limit_call.py: command not found: {argv[2]}", file=sys.stderr)
        return NOT_FOUND_EXIT
    except OSError as error:
        print(f"limit_call.py: cannot run {argv[2]}: {error}", file=sys.stderr)
        return CANNOT_RUN_EXIT
    except Stopped as stopped:
        return 128 + stopped.signum
    try:
        code = process.wait(seconds)
    except subprocess.TimeoutExpired:
        end(process)
        return TIMEOUT_EXIT
    except Stopped as stopped:
        end(process)
        return 128 + stopped.signum
    return 128 - code if code < 0 else code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
