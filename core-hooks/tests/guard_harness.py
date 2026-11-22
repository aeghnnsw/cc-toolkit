"""Run shell payloads through two safety guards and two real shells (#479).

Use this helper, not a probe script, to see what a payload does. Each run
uses a new temporary folder as the working directory and `HOME`. Stubs on
`PATH` replace `env`, `printenv`, `rm`, `git`, `gh`, `ssh`, `sudo`, `uv`,
and `curl`: each stub only writes its name and arguments to a marker file.
The `env` and `printenv` stubs also print the canary variable when they would
print every variable, as the real programs do. The shell builtins `set`,
`export`, `declare`, and `typeset` print the real canary. Each call reads
`/dev/null` as stdin and has a timeout.

    python3 core-hooks/tests/guard_harness.py --old origin/master FILE

FILE is a JSON list of payloads: strings, or objects with `name` and
`command`. `-c TEXT` adds one payload. Each output line names the payload,
the old and new guard results, and the blocked commands that each shell ran.
`MISS` marks a payload that a shell ran a blocked command in and the new
guard allows.
"""

import argparse
import json
import os
import secrets
import shlex
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


TESTS = Path(__file__).resolve().parent
PLUGIN = TESTS.parent
NEW_GUARD = PLUGIN / "scripts" / "safety_guard.py"
GUARD_FILES = ("safety_guard.py", "hook_logs.py", "hook_payload.py")
SHELLS = ("/bin/bash", "/bin/zsh")
STUBS = ("env", "printenv", "rm", "git", "gh", "ssh", "sudo", "uv", "curl")
CANARY_NAME = "GUARD_HARNESS_CANARY"
SYSTEM_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"
TIMEOUT = 10

# `env` and `printenv` print every variable when each argument is an option
# or, for `env`, an assignment.
PRINTING_STUB = """#!/bin/sh
printf '%s\\n' "{name} $*" >> "$GUARD_HARNESS_MARKERS"
for argument in "$@"; do
  case "$argument" in
    -*) ;;
    *=*) [ "{name}" = env ] || exit 0 ;;
    *) exit 0 ;;
  esac
done
printf '%s=%s\\n' {canary_name} "${canary_name}"
"""
STUB = """#!/bin/sh
printf '%s\\n' "{name} $*" >> "$GUARD_HARNESS_MARKERS"
"""


def old_guard(revision, folder):
    """Write the guard files of `revision` to `folder`; return the script."""
    folder = Path(folder)
    for name in GUARD_FILES:
        text = subprocess.run(
            ["git", "show", f"{revision}:core-hooks/scripts/{name}"],
            cwd=PLUGIN,
            capture_output=True,
            text=True,
            check=True,
            stdin=subprocess.DEVNULL,
            timeout=TIMEOUT,
        ).stdout
        (folder / name).write_text(text)
    return folder / "safety_guard.py"


def run_guard(script, command, tool_name="Bash"):
    """Return "blocked", "allowed", or "error <status>" for `command`."""
    input_key = "cmd" if tool_name == "exec_command" else "command"
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": tool_name,
        "tool_input": {input_key: command},
    }
    with tempfile.TemporaryDirectory() as folder:
        environment = dict(os.environ, CLAUDE_PROJECT_DIR=folder)
        result = subprocess.run(
            [sys.executable, str(script)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            cwd=folder,
            env=environment,
            timeout=TIMEOUT,
            check=False,
        )
    if result.returncode == 2 and result.stderr.startswith("BLOCKED"):
        return "blocked"
    if result.returncode == 0:
        return "allowed"
    return f"error {result.returncode}"


def _write_stubs(folder, canary_name):
    for name in STUBS:
        template = PRINTING_STUB if name in ("env", "printenv") else STUB
        stub = folder / name
        stub.write_text(
            template.replace("{name}", name).replace("{canary_name}", canary_name)
        )
        stub.chmod(0o755)


def run_shell(shell, command, timeout=TIMEOUT):
    """Run `command` with `shell -c` in a new temporary folder with stubs.

    Return a dict: `ran` lists the blocked commands that ran ("env" when the
    canary value reached the output, a file, or the arguments of a stub, and
    "rm <arguments>" for each `rm` call); `calls` lists every stub call;
    `timed_out` and `status` tell how the shell ended.
    """
    with tempfile.TemporaryDirectory() as root:
        root = Path(root).resolve()
        stubs = root / "stubs"
        work = root / "work"
        stubs.mkdir()
        work.mkdir()
        _write_stubs(stubs, CANARY_NAME)
        markers = root / "markers"
        markers.touch()
        canary = secrets.token_hex(16)
        environment = {
            "PATH": f"{stubs}:{SYSTEM_PATH}",
            "HOME": str(work),
            "TMPDIR": str(root),
            # zsh writes heredoc bodies to `$TMPPREFIX*`, by default `/tmp/zsh*`.
            "TMPPREFIX": str(root / "zsh"),
            "LC_ALL": "C",
            "GUARD_HARNESS_MARKERS": str(markers),
            CANARY_NAME: canary,
        }
        timed_out = False
        try:
            result = subprocess.run(
                [shell, "-c", command],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                cwd=work,
                env=environment,
                timeout=timeout,
                check=False,
            )
            output = result.stdout + result.stderr
            status = result.returncode
        except subprocess.TimeoutExpired as error:
            timed_out = True
            output = (error.stdout or b"") + (error.stderr or b"")
            status = None
        calls = markers.read_text().splitlines()
        # The canary can reach the output, a file, or a stub's arguments.
        printed = canary.encode() in output or any(
            path.is_file() and canary.encode() in path.read_bytes()
            for path in [markers, *work.rglob("*")]
        )
    ran = (["env"] if printed else []) + [
        call for call in calls if call.split(" ", 1)[0] == "rm"
    ]
    return {"ran": ran, "calls": calls, "timed_out": timed_out, "status": status}


def compare(command, old_script, new_script=NEW_GUARD, shells=SHELLS):
    """Run `command` through both guards and each shell that exists."""
    row = {
        "old": run_guard(old_script, command) if old_script else None,
        "new": run_guard(new_script, command),
    }
    for shell in shells:
        if Path(shell).exists():
            row[Path(shell).name] = run_shell(shell, command)
    ran = any(row[Path(shell).name]["ran"] for shell in shells if Path(shell).name in row)
    row["miss"] = ran and row["new"] != "blocked"
    return row


def _payloads(arguments):
    payloads = []
    for path in arguments.files:
        for index, item in enumerate(json.loads(Path(path).read_text())):
            if isinstance(item, str):
                item = {"name": f"{Path(path).name}:{index}", "command": item}
            payloads.append(item)
    for index, command in enumerate(arguments.command):
        payloads.append({"name": f"-c:{index}", "command": command})
    return payloads


def _describe(name, row):
    shells = " ".join(
        f"{key}={','.join(row[key]['ran']) or '-'}"
        + (" (timeout)" if row[key]["timed_out"] else "")
        for key in ("bash", "zsh")
        if key in row
    )
    flag = "MISS " if row["miss"] else ""
    return f"{flag}{name}: old={row['old']} new={row['new']} {shells}"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("files", nargs="*", help="JSON list of payloads")
    parser.add_argument("-c", "--command", action="append", default=[])
    parser.add_argument(
        "--old", default="origin/master",
        help="Git revision of the old guard; 'none' skips it",
    )
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 1)
    parser.add_argument("--json", action="store_true", help="print JSON lines")
    arguments = parser.parse_args(argv)
    payloads = _payloads(arguments)
    with tempfile.TemporaryDirectory() as folder:
        old_script = None
        if arguments.old != "none":
            old_script = old_guard(arguments.old, folder)
        with ThreadPoolExecutor(max_workers=max(1, arguments.jobs)) as pool:
            rows = list(pool.map(
                lambda item: compare(item["command"], old_script), payloads
            ))
    for item, row in zip(payloads, rows):
        if arguments.json:
            print(json.dumps(dict(row, name=item["name"], command=item["command"])))
        else:
            print(_describe(item["name"], row))
    return 1 if any(row["miss"] for row in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
