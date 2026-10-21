"""Choose the directory where hooks write their logs, and append to logs."""

import json
import os
import subprocess
from pathlib import Path


def _git_toplevel():
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    toplevel = result.stdout.strip()
    if result.returncode != 0 or not toplevel:
        return None
    return Path(toplevel)


def log_dir():
    """Return the `logs` directory for this session and create it.

    Claude Code gives hooks the project root in `CLAUDE_PROJECT_DIR`. Codex
    gives no project directory and runs hooks in the session `cwd`, so use
    the Git top level of the working directory. Outside a Git repository,
    use the working directory. A `cd` into a subdirectory never moves the
    logs.
    """
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if project_dir and Path(project_dir).is_dir():
        root = Path(project_dir)
    else:
        root = _git_toplevel() or Path.cwd()
    path = root / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def append_log(name, record):
    """Append `record` as one JSON line to the log file `name`.

    The line goes to the end of the file in one `write` call on a file
    opened with `O_APPEND`. Concurrent hook runs therefore keep every line,
    and no call reads or rewrites earlier lines.
    """
    line = (json.dumps(record) + "\n").encode()
    fd = os.open(log_dir() / name, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, line)
    finally:
        os.close(fd)
