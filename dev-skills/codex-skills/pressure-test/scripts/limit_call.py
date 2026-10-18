#!/usr/bin/env python3
"""Run one command with a time limit for the pressure-test skill.

Usage: python3 limit_call.py <seconds> <command> [<argument> ...]

The command runs in a new process group and shares the helper's stdin,
stdout, and stderr. When the command ends within the limit, the helper exits
with the command's exit code, or 128 + N when signal N ended it.

At the limit, the helper sends SIGTERM to the command's process group, waits
up to 5 seconds for the command to end, sends SIGKILL to the group, reaps the
command, and exits 124. When the helper gets SIGTERM, SIGINT, or SIGHUP, it
ends the command the same way and exits 128 + the signal number, also when
the signal comes while the command starts. So the helper does not exit while
the command runs, and a retry cannot overlap it. SIGKILL cannot be caught: it
ends only the helper, because the command runs in its own session.

The helper exits 2 for bad arguments, 126 when the command cannot run, and
127 when the command is not found.

The helper has no idle limit, unlike the runner of the Claude Code copy: the
Claude CLI's stream-json output gives a line about every 1.25 seconds while
the model works, and no stalled call was seen (see #310).
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
import time

TIMEOUT_EXIT = 124
USAGE_EXIT = 2
CANNOT_RUN_EXIT = 126
NOT_FOUND_EXIT = 127
GRACE_SECONDS = 5
STOP_SIGNALS = (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)
POLL_SECONDS = 0.1
received: list[int] = []  # the stop signals that the helper got; the first sets the exit code


def record_stop(signum: int, _frame: object) -> None:
    """Record a stop signal for the main loop.

    The handler raises no exception, so a signal cannot interrupt the start of
    the command or its cleanup.
    """
    received.append(signum)


def end(process: subprocess.Popen) -> None:
    """Send SIGTERM to the command's group, wait for the grace period, send SIGKILL to the group, and reap.

    A signal to a group that has ended, or that the system refuses, as macOS
    does for a group of zombies, is skipped.
    """
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(process.pid, signal.SIGTERM)
    with contextlib.suppress(subprocess.TimeoutExpired):
        process.wait(GRACE_SECONDS)
    with contextlib.suppress(ProcessLookupError, PermissionError):
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
        signal.signal(signum, record_stop)
    try:
        process = subprocess.Popen(argv[2:], start_new_session=True)
    except FileNotFoundError:
        print(f"limit_call.py: command not found: {argv[2]}", file=sys.stderr)
        return NOT_FOUND_EXIT
    except OSError as error:
        print(f"limit_call.py: cannot run {argv[2]}: {error}", file=sys.stderr)
        return CANNOT_RUN_EXIT
    deadline = time.monotonic() + seconds
    while process.poll() is None and not received and time.monotonic() < deadline:
        time.sleep(POLL_SECONDS)
    if received:
        code = 128 + received[0]
    elif process.returncode is None:
        code = TIMEOUT_EXIT
    else:
        code = 128 - process.returncode if process.returncode < 0 else process.returncode
    if process.returncode is None:  # the command still runs
        end(process)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
