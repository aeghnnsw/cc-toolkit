#!/usr/bin/env python3
"""Run one read-only Codex critic call for the pressure-test skill.

Usage: python3 codex_critic.py <smoke|kickoff|resume> <workdir> [--timeout SECONDS]

Every call runs `codex exec` from the repository root with the pinned model
and a read-only sandbox: smoke at effort low with the prompt "Reply with
exactly: ok", kickoff and resume at effort xhigh with the prompt on stdin.
The default timeout is 60 seconds for smoke and 570 seconds otherwise. After
a timeout, the cleanup of the codex process tree takes at most 5 more seconds.

Inputs in <workdir>:

  repo        absolute repository root
  model       current critic model ID
  prompt.md   prompt for kickoff and resume
  critic.txt  optional critic instructions, sent after prompt.md
  thread_id   critic thread for resume; kickoff writes it

Outputs in <workdir>: msg.txt (the critic's reply; deleted before each call),
events.jsonl (codex stdout), err.log (codex stderr), and, after a kickoff,
thread_id (empty when codex reported no thread).

The script prints one line, `exit=<code> model=<model> status=<status>`, and
exits 0 only for ok. The code is the codex exit code, 124 for a timeout,
127 when codex is not on PATH, and 2 for a missing input. Statuses, in
order of precedence:

  error:codex not found   codex is not on PATH; codex did not run
  error:missing FILE      a required input is missing or empty, or repo names no
                          directory; codex did not run
  flagged                 an error event or stderr reports a flag or a model reroute
  error:timeout           the call ran out of time and was killed
  error:exit N            codex exited with code N
  error:no thread id      a kickoff emitted no thread.started event
  error:no reply          msg.txt is missing or empty
  error:smoke reply       the smoke reply does not contain the word ok
  ok                      the critic replied
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

SMOKE_PROMPT = "Reply with exactly: ok"
TIMEOUTS = {"smoke": 60, "kickoff": 570, "resume": 570}
TIMEOUT_EXIT = 124
MISSING_INPUT_EXIT = 2
NOT_FOUND_EXIT = 127
# Time for the timeout cleanup. It fits in the 30 seconds between the 570-second
# call timeout and the 600-second Bash tool timeout in SKILL.md.
CLEANUP_SECONDS = 5
ERROR_TYPES = {"error", "turn.failed"}
ERROR_LINE = re.compile(r'"type" *: *"(error|turn\.failed)"')
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


def missing_input(mode: str, workdir: Path) -> str:
    """Return the first required input file that is missing or empty, or "".

    A repo file that does not name a directory counts as missing.
    """
    if not Path(read_input(workdir, "repo") or "/nonexistent").is_dir():
        return "repo"
    required = ["model"]
    if mode != "smoke":
        required.append("prompt.md")
    if mode == "resume":
        required.append("thread_id")
    return next((name for name in required if not read_input(workdir, name)), "")


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


def is_flagged(workdir: Path) -> bool:
    """Return True when an error event or stderr reports a flag or a model reroute.

    Only error and turn.failed events and stderr are searched, so words in the
    critic's reply or agent messages never count.
    """
    texts = [read_text(workdir / "err.log")]
    for line, event in event_lines(workdir / "events.jsonl"):
        if (event is None and ERROR_LINE.search(line)) or (
                isinstance(event, dict) and event.get("type") in ERROR_TYPES):
            texts.append(line)
    return bool(FLAG.search("\n".join(texts)))


def codex_command(mode: str, workdir: Path, repo: str, model: str) -> list[str]:
    """Return the codex argument list for one call."""
    effort = "low" if mode == "smoke" else "xhigh"
    options = ["--json", "--skip-git-repo-check", "-m", model, "-c", f'model_reasoning_effort="{effort}"']
    reply = ["-o", str(workdir / "msg.txt"), SMOKE_PROMPT if mode == "smoke" else "-"]
    if mode == "resume":
        # `codex exec resume` rejects -s and -C and does not keep the kickoff sandbox.
        return ["codex", "exec", "resume", read_input(workdir, "thread_id"), *options,
                "-c", 'sandbox_mode="read-only"', *reply]
    return ["codex", "exec", *options, "-s", "read-only", "-C", repo, *reply]


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
    before a scan, for example one whose parent exited, is not found.
    """
    deadline = time.monotonic() + CLEANUP_SECONDS
    stopped: set[int] = set()
    try:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(pid, signal.SIGSTOP)
        while (remaining := deadline - time.monotonic()) > 0:
            found = [target for target in descendants(pid, remaining) if target not in stopped]
            if not found:
                break
            for target in found:
                with contextlib.suppress(ProcessLookupError):
                    os.kill(target, signal.SIGSTOP)
            stopped.update(found)
    finally:
        for target in stopped:
            with contextlib.suppress(ProcessLookupError):
                os.kill(target, signal.SIGKILL)
        with contextlib.suppress(ProcessLookupError):
            os.killpg(pid, signal.SIGKILL)


def run_codex(command: list[str], repo: str, workdir: Path, prompt: bytes | None, timeout: float) -> int | None:
    """Run codex from the repository root; return its exit code, or None when it timed out.

    codex runs in its own process group. A timeout kills the group and, as far
    as possible, every process below it.
    """
    (workdir / "msg.txt").unlink(missing_ok=True)  # never show a stale reply
    stdin = subprocess.DEVNULL if prompt is None else subprocess.PIPE
    with open(workdir / "events.jsonl", "wb") as events, open(workdir / "err.log", "wb") as err:
        process = subprocess.Popen(command, cwd=repo, stdin=stdin, stdout=events, stderr=err,
                                   start_new_session=True)
        try:
            process.communicate(prompt, timeout=timeout)
        except subprocess.TimeoutExpired:
            kill_tree(process.pid)
            process.communicate()
            return None
    return process.returncode


def classify(mode: str, workdir: Path, code: int | None) -> str:
    """Return the status of a finished call; code None means it timed out."""
    if is_flagged(workdir):
        return "flagged"
    if code is None:
        return "error:timeout"
    if code != 0:
        return f"error:exit {code}"
    if mode == "kickoff" and not read_input(workdir, "thread_id"):
        return "error:no thread id"
    reply = read_input(workdir, "msg.txt")
    if not reply:
        return "error:no reply"
    if mode == "smoke" and not re.search(r"\bok\b", reply, re.IGNORECASE):
        return "error:smoke reply"
    return "ok"


def report(code: int, model: str, status: str) -> int:
    """Print the status line; return 0 for ok and 1 otherwise."""
    print(f"exit={code} model={model} status={status}")
    return 0 if status == "ok" else 1


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mode", choices=("smoke", "kickoff", "resume"))
    parser.add_argument("workdir")
    parser.add_argument("--timeout", type=float, metavar="SECONDS")
    args = parser.parse_args(argv[1:])
    workdir = Path(args.workdir).absolute()
    repo, model = read_input(workdir, "repo"), read_input(workdir, "model")
    if shutil.which("codex") is None:
        return report(NOT_FOUND_EXIT, model, "error:codex not found")
    missing = missing_input(args.mode, workdir)
    if missing:
        return report(MISSING_INPUT_EXIT, model, f"error:missing {missing}")
    prompt = None
    if args.mode != "smoke":
        critic = workdir / "critic.txt"
        prompt = (workdir / "prompt.md").read_bytes() + (critic.read_bytes() if critic.exists() else b"")
    timeout = TIMEOUTS[args.mode] if args.timeout is None else args.timeout
    code = run_codex(codex_command(args.mode, workdir, repo, model), repo, workdir, prompt, timeout)
    if args.mode == "kickoff":
        (workdir / "thread_id").write_text(thread_id(workdir), encoding="utf-8")
    return report(TIMEOUT_EXIT if code is None else code, model, classify(args.mode, workdir, code))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
