#!/usr/bin/env python3
"""Run one read-only Codex critic call for the pressure-test skill.

Usage: python3 codex_critic.py <smoke|kickoff|resume|retry|wait> <workdir>

smoke, kickoff, resume, and retry start a critic call; wait waits for the call
that was started last. The Bash tool stops waiting for a command after at most
600 seconds, and a critic turn can take longer. So each call runs in a detached
supervisor: a process in a new session whose parent has already exited, so a
kill of the command's process group and process tree does not reach it. The
command that starts a call, and each wait, wait for the final status for at most
one wait step.

Every call runs `codex exec` from the repository root with the pinned model
and a read-only sandbox:

  smoke    effort low, the prompt "Reply with exactly: ok"
  kickoff  effort xhigh, a new thread; stdin is prompt.md and critic.txt
  resume   effort xhigh, the saved thread; stdin is prompt.md and critic.txt
  retry    the narrow retry after a time limit: a resume when thread_id names a
           thread, otherwise a kickoff; stdin is prompt.md, critic.txt, and
           narrow.txt. Each form follows the status rules of the call it makes.

Time limits: the supervisor stops a call when codex writes no output to
events.jsonl or err.log for the idle limit, 600 seconds, or when the call has
run for the total limit, 1,800 seconds. The smoke call has 60 seconds for both.
After a limit, the cleanup of the codex process tree takes at most 5 more
seconds. The wait step is 570 seconds. When the Bash tool limit, the larger of
BASH_MAX_TIMEOUT_MS (default 600000) and BASH_DEFAULT_TIMEOUT_MS (default
120000), is lower, the step is that limit minus 30 seconds, and at least 5
seconds.

Inputs in <workdir>:

  repo         absolute repository root
  model        current critic model ID
  prompt.md    pressure-test packet for kickoff, resume, and retry
  critic.txt   optional critic instructions, sent after prompt.md
  narrow.txt   narrow request for retry, sent last
  thread_id    critic thread for resume and retry; a kickoff writes it
  idle_limit, total_limit, wait_step
               optional seconds in place of the defaults

Outputs in <workdir>: msg.txt (the critic's reply; deleted first when a call
starts), events.jsonl (codex stdout), err.log (codex stderr), request.txt (the
stdin of codex), runner.log (supervisor errors), call.json and status.json (the
current call and its final status), start.lock (held while a call starts),
call.lock (held by the supervisor while it runs), and, after a kickoff,
thread_id (empty when codex reported no thread).

The script prints one line, `exit=<code> model=<model> seconds=<n> status=<status>`,
and exits 0 only for ok. seconds is the time of the call so far. The code is the
codex exit code, 124 for a time limit, 127 when codex is not on PATH, 2 when no
call starts because of an input, and - when no code exists.

Statuses of a start, before codex runs:

  error:busy             a call in <workdir> still runs, or another start holds
                         start.lock; run wait
  error:codex not found  codex is not on PATH
  error:missing FILE     a required input is missing or empty, or repo names no
                         directory
  error:bad limit        a limit file is not a positive number

Statuses of a wait (a start also waits):

  running                the wait step ended before the call; run wait
  error:no call          no call was started
  error:runner stopped   the supervisor ended without a final status, or the call
                         is more than 60 seconds past its total limit. A
                         supervisor that still runs is killed first, and then
                         the codex process of the call, when `ps` shows that it
                         is the same process.

Final statuses of a call, in order of precedence:

  flagged                an error event, an error item, or stderr reports a flag or
                         a model reroute
  error:idle             codex wrote no output for the idle limit and was killed
  error:timeout          the call reached the total limit and was killed
  error:exit N           codex exited with code N
  error:no thread id     a kickoff emitted no thread.started event
  error:no reply         msg.txt is missing or empty
  error:smoke reply      the smoke reply does not contain the word ok
  ok                     the critic replied
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import re
import resource
import shutil
import signal
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import NoReturn

SMOKE_PROMPT = "Reply with exactly: ok"
CALL_LIMITS = {"idle_limit": 600, "total_limit": 1800}
SMOKE_LIMITS = {"idle_limit": 60, "total_limit": 60}
WAIT_STEP = 570
BASH_LIMITS = {"BASH_MAX_TIMEOUT_MS": 600_000, "BASH_DEFAULT_TIMEOUT_MS": 120_000}
BASH_MARGIN = 30          # seconds between the end of a wait step and the Bash tool limit
MIN_WAIT_STEP = 5
STOPPED_MARGIN = 60       # seconds past the total limit after which a call counts as stopped
POLL_SECONDS = 0.25
TIMEOUT_EXIT = 124
INPUT_EXIT = 2
NOT_FOUND_EXIT = 127
NO_CODE = "-"
CLEANUP_SECONDS = 5       # time for the cleanup of the codex process tree after a limit
MAX_CLOSED_FD = 65536
STOP_SIGNALS = (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)
# Runs codex only after the supervisor has recorded the process and opened the
# gate pipe, so no codex process runs that a later start cannot find.
GATE = """\
import os, sys
gate = int(sys.argv[1])
opened = os.read(gate, 1) == b"1"
os.close(gate)
if not opened:
    sys.exit(1)
os.execvp(sys.argv[2], sys.argv[2:])
"""
ERROR_TYPES = {"error", "turn.failed"}
ERROR_LINE = re.compile('"type" *: *"(%s)"' % "|".join(re.escape(name) for name in sorted(ERROR_TYPES)))
FLAG = re.compile(r"flagged for|policy violation|cyber_policy|bio_policy|misalignment_policy|rerouted|as a fallback",
                  re.IGNORECASE)


def read_text(path: Path) -> str:
    """Return the text of a file, or "" when it is missing."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def read_input(workdir: Path, name: str) -> str:
    """Return the stripped text of a file in the work directory, or "" when it is missing."""
    return read_text(workdir / name).strip()


def read_json(path: Path) -> dict | None:
    """Return the JSON object in a file, or None when the file is missing or holds no object."""
    try:
        value = json.loads(read_text(path))
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def write_atomic(path: Path, text: str) -> None:
    """Write a file so that a reader sees either the old or the new content."""
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def limit(workdir: Path, name: str, default: float) -> float | None:
    """Return the seconds in a limit file or the default; None when the file is not a positive number."""
    text = read_input(workdir, name)
    try:
        value = float(text) if text else default
    except ValueError:
        return None
    return value if value > 0 else None


def default_wait_step() -> float:
    """Return 570 seconds, or less when the Bash tool limit leaves less than 30 seconds of margin."""
    limits = []
    for name, default in BASH_LIMITS.items():
        try:
            limits.append(float(os.environ.get(name) or default))
        except ValueError:
            limits.append(default)
    return max(MIN_WAIT_STEP, min(WAIT_STEP, max(limits) / 1000 - BASH_MARGIN))


def call_limits(mode: str, workdir: Path) -> dict[str, float] | None:
    """Return the idle limit, total limit, and wait step of a call; None when a limit file is bad."""
    defaults = dict(SMOKE_LIMITS if mode == "smoke" else CALL_LIMITS, wait_step=default_wait_step())
    limits = {name: limit(workdir, name, default) for name, default in defaults.items()}
    return None if None in limits.values() else limits


def call_form(mode: str, workdir: Path) -> str:
    """Return the call that a mode makes: smoke, kickoff, or resume."""
    if mode == "retry":
        return "resume" if read_input(workdir, "thread_id") else "kickoff"
    return mode


def missing_input(mode: str, form: str, workdir: Path) -> str:
    """Return the first required input file that is missing or empty, or "".

    A repo file that does not name a directory counts as missing.
    """
    if not Path(read_input(workdir, "repo") or "/nonexistent").is_dir():
        return "repo"
    required = ["model"]
    if mode != "smoke":
        required.append("prompt.md")
    if mode == "retry":
        required.append("narrow.txt")
    if form == "resume":
        required.append("thread_id")
    return next((name for name in required if not read_input(workdir, name)), "")


def request(mode: str, workdir: Path) -> bytes | None:
    """Return the stdin of codex for a call, or None for smoke."""
    if mode == "smoke":
        return None
    names = ["prompt.md", "critic.txt", "narrow.txt"] if mode == "retry" else ["prompt.md", "critic.txt"]
    return b"".join((workdir / name).read_bytes() for name in names if (workdir / name).exists())


def event_lines(path: Path) -> list[tuple[str, object]]:
    """Return each line of a JSON Lines file with its parsed value, or None when the line is not JSON."""
    pairs = []
    for line in read_text(path).splitlines():
        try:
            pairs.append((line, json.loads(line)))
        except json.JSONDecodeError:
            pairs.append((line, None))
    return pairs


def thread_id(workdir: Path) -> str:
    """Return the thread_id of the first thread.started event, or ""."""
    for _, event in event_lines(workdir / "events.jsonl"):
        if isinstance(event, dict) and event.get("type") == "thread.started":
            return str(event.get("thread_id") or "")
    return ""


def is_error(line: str, event: object) -> bool:
    """Return True for an error or turn.failed event, or an event that carries an error item.

    Codex sends some warnings as {"type": "item.completed", "item": {"type": "error", ...}}.
    A line that is not JSON counts when it contains an error type.
    """
    if not isinstance(event, dict):
        return event is None and bool(ERROR_LINE.search(line))
    item = event.get("item")
    return event.get("type") in ERROR_TYPES or (isinstance(item, dict) and item.get("type") == "error")


def is_flagged(workdir: Path) -> bool:
    """Return True when an error event, an error item, or stderr reports a flag or a model reroute.

    Only errors and stderr are searched, so words in the critic's reply or
    agent messages never count.
    """
    texts = [read_text(workdir / "err.log")]
    texts += [line for line, event in event_lines(workdir / "events.jsonl") if is_error(line, event)]
    return bool(FLAG.search("\n".join(texts)))


def codex_command(form: str, workdir: Path, repo: str, model: str) -> list[str]:
    """Return the codex argument list for one call."""
    effort = "low" if form == "smoke" else "xhigh"
    options = ["--json", "--skip-git-repo-check", "-m", model, "-c", f'model_reasoning_effort="{effort}"']
    output = ["-o", str(workdir / "msg.txt"), SMOKE_PROMPT if form == "smoke" else "-"]
    if form == "resume":
        # `codex exec resume` rejects -s and -C and does not keep the kickoff sandbox.
        return ["codex", "exec", "resume", read_input(workdir, "thread_id"), *options,
                "-c", 'sandbox_mode="read-only"', *output]
    return ["codex", "exec", *options, "-s", "read-only", "-C", repo, *output]


def descendants(pid: int, timeout: float) -> list[int]:
    """Return the IDs of all processes below pid, from one `ps` snapshot; [] when `ps` fails."""
    try:
        table = subprocess.run(["ps", "-A", "-o", "pid=,ppid="], capture_output=True, text=True,
                               timeout=timeout).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    children: dict[int, list[int]] = {}
    for line in table.splitlines():
        fields = line.split()
        if len(fields) == 2 and all(field.isdigit() for field in fields):
            children.setdefault(int(fields[1]), []).append(int(fields[0]))
    found, stack = [], [pid]
    while stack:
        for child in children.get(stack.pop(), []):
            found.append(child)
            stack.append(child)
    return found


def kill_tree(pid: int) -> None:
    """Kill the codex process group and every process below it, as far as possible.

    Codex starts shell tool calls in their own sessions, so killing its group
    alone can leave them running. Each process found is stopped first, and the
    tree is scanned again until a scan finds no new process, so no found process
    can start a child before the kill. The scans end after CLEANUP_SECONDS, and
    the kill always runs. This is best effort: a process that left the tree
    before a scan, for example one whose parent exited, is not found, and a
    signal that the system refuses, as macOS does for a group of zombies, is
    skipped.
    """
    deadline = time.monotonic() + CLEANUP_SECONDS
    stopped: set[int] = set()
    try:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(pid, signal.SIGSTOP)
        while (remaining := deadline - time.monotonic()) > 0:
            found = [target for target in descendants(pid, remaining) if target not in stopped]
            if not found:
                break
            for target in found:
                with contextlib.suppress(ProcessLookupError, PermissionError):
                    os.kill(target, signal.SIGSTOP)
            stopped.update(found)
    finally:
        for target in stopped:
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.kill(target, signal.SIGKILL)
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(pid, signal.SIGKILL)


class Stopped(Exception):
    """The supervisor got a stop signal."""


def raise_stopped(_signum: int, _frame: object) -> None:
    raise Stopped


def process_start(pid: int) -> str:
    """Return the start time of a process as `ps` prints it, or "" when `ps` fails."""
    try:
        return subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True,
                              timeout=CLEANUP_SECONDS).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def record_codex(workdir: Path, pid: int) -> bool:
    """Add the codex process ID and its start time to call.json; return True when it did.

    Return False, and write nothing, when call.json names another supervisor.
    """
    start = process_start(pid)
    call = read_json(workdir / "call.json") or {}
    if call.get("pid") != os.getpid():
        return False
    write_atomic(workdir / "call.json", json.dumps(dict(call, codex=pid, codex_start=start)))
    return True


def end_orphan(call: dict) -> None:
    """Kill the codex process tree of a stopped call, when `ps` shows the same process as at its start.

    A supervisor that was killed leaves its codex call running with no limit.
    The start time check keeps a reused process ID from being killed.
    """
    pid, start = call.get("codex"), call.get("codex_start")
    if isinstance(pid, int) and pid > 0 and start and alive(pid) and process_start(pid) == start:
        kill_tree(pid)


def output_size(workdir: Path) -> int:
    """Return the total size of the codex stdout and stderr files."""
    size = 0
    for name in ("events.jsonl", "err.log"):
        with contextlib.suppress(OSError):
            size += (workdir / name).stat().st_size
    return size


def run_codex(workdir: Path, job: dict) -> tuple[int | None, str]:
    """Run codex from the repository root until it ends or reaches a limit.

    Return its exit code and "", or None and the limit that it reached: "idle"
    or "timeout". codex runs in its own process group. It starts behind a gate:
    a small launcher execs codex only after its process ID and start time are in
    call.json, and exits when the supervisor dies first or call.json names
    another supervisor. At a limit, or when the supervisor fails or gets a stop
    signal, the group and, as far as possible, every process below it are
    killed, and codex is reaped before this returns.
    """
    with contextlib.ExitStack() as files:
        stdin = (subprocess.DEVNULL if job["form"] == "smoke"
                 else files.enter_context(open(workdir / "request.txt", "rb")))
        stdout = files.enter_context(open(workdir / "events.jsonl", "wb"))
        stderr = files.enter_context(open(workdir / "err.log", "wb"))
        gate_read, gate_write = os.pipe()
        try:
            process = subprocess.Popen([sys.executable, "-I", "-c", GATE, str(gate_read), *job["command"]],
                                       cwd=job["repo"], stdin=stdin, stdout=stdout, stderr=stderr,
                                       pass_fds=(gate_read,), start_new_session=True)
        finally:
            os.close(gate_read)
        started = last_output = time.monotonic()
        try:
            if record_codex(workdir, process.pid):
                os.write(gate_write, b"1")
            os.close(gate_write)
            size = 0
            while process.poll() is None:
                now = time.monotonic()
                if (current := output_size(workdir)) != size:
                    size, last_output = current, now
                reason = ("timeout" if now - started >= job["total"]
                          else "idle" if now - last_output >= job["idle"] else "")
                if reason:
                    kill_tree(process.pid)
                    process.wait()
                    return None, reason
                time.sleep(POLL_SECONDS)
        except BaseException:
            for signum in STOP_SIGNALS:  # a second signal must not cut the cleanup short
                signal.signal(signum, signal.SIG_IGN)
            if process.poll() is None:
                kill_tree(process.pid)
                process.wait()
            raise
    return process.returncode, ""


def classify(form: str, workdir: Path, code: int | None, reason: str) -> str:
    """Return the final status of a call; code None means that it reached the limit named by reason."""
    if is_flagged(workdir):
        return "flagged"
    if code is None:
        return f"error:{reason}"
    if code != 0:
        return f"error:exit {code}"
    if form == "kickoff" and not read_input(workdir, "thread_id"):
        return "error:no thread id"
    reply = read_input(workdir, "msg.txt")
    if not reply:
        return "error:no reply"
    if form == "smoke" and not re.search(r"\bok\b", reply, re.IGNORECASE):
        return "error:smoke reply"
    return "ok"


def detach(workdir: Path, keep: tuple[int, ...]) -> None:
    """Connect stdin to /dev/null and stdout and stderr to runner.log; close every other inherited file but keep.

    The supervisor then holds none of the command's pipes, so the command ends
    when its own process ends.
    """
    null = os.open(os.devnull, os.O_RDONLY)
    log = os.open(workdir / "runner.log", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    os.dup2(null, 0)
    os.dup2(log, 1)
    os.dup2(log, 2)
    soft = resource.getrlimit(resource.RLIMIT_NOFILE)[0]
    highest = MAX_CLOSED_FD if soft in (resource.RLIM_INFINITY, -1) else min(soft, MAX_CLOSED_FD)
    low = 3
    for fd in sorted(keep):
        os.closerange(low, fd)
        low = fd + 1
    os.closerange(low, max(low, highest))


def hold_call_lock(workdir: Path) -> None:
    """Lock a new call.lock until this process exits.

    The file is locked under a temporary name and then renamed, so no reader
    sees an unlocked call.lock of this call. The descriptor is not inherited:
    codex and the processes that the supervisor starts never hold the lock.
    """
    temporary = workdir / f".call.lock.{os.getpid()}.tmp"
    lock = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    fcntl.flock(lock, fcntl.LOCK_EX)
    os.replace(temporary, workdir / "call.lock")


def supervisor_ended(workdir: Path) -> bool:
    """Return True when no process holds call.lock.

    The kernel releases the lock when the supervisor exits, also while the
    supervisor stays a zombie that no process reaps, and a process that
    reuses the supervisor's ID does not hold it.
    """
    try:
        lock = os.open(workdir / "call.lock", os.O_RDONLY)
    except OSError:
        return True
    try:
        fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
    except BlockingIOError:
        return False
    finally:
        os.close(lock)
    return True


def supervise(workdir: Path, job: dict, ready: int, lock: int) -> NoReturn:
    """Run one codex call and write its final status; never returns.

    The supervisor keeps its copy of the start lock until it has written
    call.json, so a kill of the starting command cannot release the lock
    earlier. It holds call.lock until it exits. The status, and a kickoff's
    thread_id, are written only while call.json still names this supervisor,
    so a supervisor that a later call replaced writes nothing.
    """
    code = 1
    try:
        for signum in STOP_SIGNALS:
            signal.signal(signum, raise_stopped)
        detach(workdir, (ready, lock))
        hold_call_lock(workdir)
        call = {"pid": os.getpid(), "model": job["model"], "started": time.time(), "total": job["total"]}
        write_atomic(workdir / "call.json", json.dumps(call))
        with contextlib.suppress(OSError):  # the starting command can be gone; the call still runs
            os.write(ready, b"started")
        os.close(ready)
        os.close(lock)
        started = time.monotonic()
        exit_code, reason = run_codex(workdir, job)
        seconds = round(time.monotonic() - started)
        if (read_json(workdir / "call.json") or {}).get("pid") == os.getpid():
            if job["form"] == "kickoff":
                write_atomic(workdir / "thread_id", thread_id(workdir))
            final = {"exit": TIMEOUT_EXIT if exit_code is None else exit_code, "model": job["model"],
                     "seconds": seconds, "status": classify(job["form"], workdir, exit_code, reason)}
            write_atomic(workdir / "status.json", json.dumps(final))
        code = 0
    except BaseException:
        traceback.print_exc()
    finally:
        os._exit(code)


def launch(workdir: Path, job: dict, lock: int) -> bool:
    """Start the supervisor of a call as a detached process; return True when it wrote call.json.

    The first child starts a new session, forks the supervisor, and exits at
    once. So the supervisor is in no process group of the command, and its
    parent is gone before any kill of the command's process tree can find it.
    """
    sys.stdout.flush()
    ready_read, ready_write = os.pipe()
    child = os.fork()
    if child == 0:
        try:
            os.close(ready_read)
            os.setsid()
            if os.fork() == 0:
                supervise(workdir, job, ready_write, lock)
        finally:
            os._exit(0)
    os.close(ready_write)
    os.waitpid(child, 0)
    with os.fdopen(ready_read, "rb") as ready:
        return ready.read() == b"started"


def alive(pid: int) -> bool:
    """Return True when a process has the ID."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def current_call(workdir: Path) -> dict | None:
    """Return the record of the call that was started last, or None when it is missing or not valid."""
    call = read_json(workdir / "call.json")
    if call is None:
        return None
    valid = (isinstance(call.get("pid"), int) and call["pid"] > 0 and isinstance(call.get("model"), str)
             and all(isinstance(call.get(name), (int, float)) for name in ("started", "total")))
    return call if valid else None


def end_call(workdir: Path, call: dict) -> bool:
    """End a stopped call: kill its supervisor while it holds call.lock, then its codex process tree.

    A supervisor past its total limit and the margin can still run, for example
    when it was stopped, and could later write its status into another call.
    While it holds call.lock it is alive, so its process ID is not reused.
    Return False when it still holds call.lock after the kill.
    """
    if not supervisor_ended(workdir):
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.kill(call["pid"], signal.SIGKILL)
        deadline = time.monotonic() + CLEANUP_SECONDS
        while not supervisor_ended(workdir):
            if time.monotonic() >= deadline:
                return False
            time.sleep(POLL_SECONDS)
    end_orphan(call)
    return True


def stopped(workdir: Path, call: dict) -> bool:
    """Return True when the supervisor of a call ended, or the call is too far past its total limit."""
    return supervisor_ended(workdir) or time.time() - call["started"] > call["total"] + STOPPED_MARGIN


def running(workdir: Path) -> bool:
    """Return True when a call in the work directory still runs."""
    call = current_call(workdir)
    return call is not None and not (workdir / "status.json").exists() and not stopped(workdir, call)


def report_final(final: dict) -> int:
    return report(final.get("exit", NO_CODE), final.get("model", ""), final.get("seconds", 0),
                  final.get("status", "error:runner stopped"))


def wait(workdir: Path, step: float) -> int:
    """Wait for at most one step for the final status of the current call, and print it or running."""
    deadline = time.monotonic() + step
    while True:
        final = read_json(workdir / "status.json")
        if final is not None:
            return report_final(final)
        call = current_call(workdir)
        if call is None:
            return report(INPUT_EXIT, read_input(workdir, "model"), 0, "error:no call")
        seconds = round(time.time() - call["started"])
        if stopped(workdir, call):
            end_call(workdir, call)
            final = read_json(workdir / "status.json")  # the supervisor can write it just before it ends
            if final:
                return report_final(final)
            return report(NO_CODE, call["model"], seconds, "error:runner stopped")
        if time.monotonic() >= deadline:
            return report(NO_CODE, call["model"], seconds, "running")
        time.sleep(min(POLL_SECONDS, max(0.0, deadline - time.monotonic())))


def start(mode: str, workdir: Path) -> int:
    """Check the inputs, start a call in a supervisor, and wait for one step.

    The start, and then its supervisor, hold start.lock from the busy check
    until the supervisor has written call.json, so of two starts at the same
    time, one is busy.
    """
    model = read_input(workdir, "model")
    try:
        lock = open(workdir / "start.lock", "a")
    except OSError:
        return report(INPUT_EXIT, model, 0, "error:missing repo")
    with lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return report(INPUT_EXIT, model, 0, "error:busy")
        result = start_locked(mode, workdir, model, lock.fileno())
    return result if isinstance(result, int) else wait(workdir, result["wait_step"])


def start_locked(mode: str, workdir: Path, model: str, lock: int) -> int | dict[str, float]:
    """Start a call while start.lock is held; return the limits, or the exit code when no call started."""
    if running(workdir):
        return report(INPUT_EXIT, model, 0, "error:busy")
    call = current_call(workdir)
    if call and not (workdir / "status.json").exists() and not end_call(workdir, call):
        return report(INPUT_EXIT, model, 0, "error:busy")  # the earlier call stopped without a final status
    for name in ("msg.txt", "status.json", "call.json"):  # never show a stale reply or status
        (workdir / name).unlink(missing_ok=True)
    if shutil.which("codex") is None:
        return report(NOT_FOUND_EXIT, model, 0, "error:codex not found")
    form = call_form(mode, workdir)
    missing = missing_input(mode, form, workdir)
    if missing:
        return report(INPUT_EXIT, model, 0, f"error:missing {missing}")
    limits = call_limits(mode, workdir)
    if limits is None:
        return report(INPUT_EXIT, model, 0, "error:bad limit")
    repo = read_input(workdir, "repo")
    stdin = request(mode, workdir)
    if stdin is None:
        (workdir / "request.txt").unlink(missing_ok=True)
    else:
        (workdir / "request.txt").write_bytes(stdin)
    if form == "kickoff":
        (workdir / "thread_id").unlink(missing_ok=True)
    job = {"form": form, "model": model, "repo": repo, "command": codex_command(form, workdir, repo, model),
           "idle": limits["idle_limit"], "total": limits["total_limit"]}
    if not launch(workdir, job, lock):
        return report(NO_CODE, model, 0, "error:runner stopped")
    return limits


def report(code: int | str, model: str, seconds: int, status: str) -> int:
    """Print the status line; return 0 for ok and 1 otherwise."""
    print(f"exit={code} model={model} seconds={seconds} status={status}", flush=True)
    return 0 if status == "ok" else 1


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mode", choices=("smoke", "kickoff", "resume", "retry", "wait"))
    parser.add_argument("workdir")
    args = parser.parse_args(argv[1:])
    workdir = Path(args.workdir).absolute()
    if args.mode != "wait":
        return start(args.mode, workdir)
    step = limit(workdir, "wait_step", default_wait_step())
    if step is None:
        return report(INPUT_EXIT, read_input(workdir, "model"), 0, "error:bad limit")
    return wait(workdir, step)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
