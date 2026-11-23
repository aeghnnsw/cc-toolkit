"""Choose the directory where hooks write their logs, and append to logs."""

import json
import os
import subprocess
from pathlib import Path

from hook_payload import ANTIGRAVITY


def _git_toplevel(cwd=None):
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            cwd=cwd,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    toplevel = result.stdout.strip()
    if result.returncode != 0 or not toplevel:
        return None
    return Path(toplevel)


def log_dir(base=None, create=True):
    """Return the `logs` directory for this session and create it.

    Claude Code gives hooks the project root in `CLAUDE_PROJECT_DIR`. Codex
    gives no project directory and runs hooks in the session `cwd`, so use
    the Git top level of the working directory. Outside a Git repository,
    use the working directory. A `cd` into a subdirectory never moves the
    logs.

    With `base`, use the Git top level of `base`, or `base` itself outside a
    Git repository, and ignore `CLAUDE_PROJECT_DIR`. With `create` false,
    return the path and do not create the directory.
    """
    if base is not None:
        root = _git_toplevel(base) or Path(base)
    else:
        project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
        if project_dir and Path(project_dir).is_dir():
            root = Path(project_dir)
        else:
            root = _git_toplevel() or Path.cwd()
    path = root / "logs"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def host_log_dir(host, input_data=None, create=True):
    """Return the `logs` directory for a hook run on `host`, or None.

    Antigravity runs hooks from the plugin root, and the hook environment
    can keep a `CLAUDE_PROJECT_DIR` of another session. So in Antigravity
    mode the logs go under the project directory in the payload `cwd`. A
    payload without an absolute `cwd` of an existing directory gives None:
    the hook writes no log. `create` is as in `log_dir()`.
    """
    if host != ANTIGRAVITY:
        return log_dir(create=create)
    cwd = input_data.get("cwd") if isinstance(input_data, dict) else None
    if not isinstance(cwd, str) or not os.path.isabs(cwd) or not os.path.isdir(cwd):
        return None
    return log_dir(cwd, create=create)


def append_log(name, record, directory=None):
    """Append `record` as one JSON line to the log file `name`.

    The file is in `directory`, or in `log_dir()` when `directory` is None.
    The line goes to the end of the file in one `write` call on a file
    opened with `O_APPEND`. Concurrent hook runs therefore keep every line,
    and no call reads or rewrites earlier lines.
    """
    if directory is None:
        directory = log_dir()
    line = (json.dumps(record) + "\n").encode()
    fd = os.open(directory / name, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, line)
    finally:
        os.close(fd)
