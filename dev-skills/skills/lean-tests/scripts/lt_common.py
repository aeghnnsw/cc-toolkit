"""Shared helpers for lean_tests.py. Imported only; never run directly."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


EXAMPLES = 5
# The errors of reading and parsing a Python file; UnicodeDecodeError is a ValueError.
PARSE_ERRORS = (OSError, SyntaxError, ValueError)


class UsageError(Exception):
    """A usage or environment error. lean_tests.py prints it and exits with 2."""

    def __init__(self, message: str, **extra: object) -> None:
        super().__init__(message)
        self.extra = extra


def load_json(path: str, what: str) -> dict:
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except OSError as error:
        raise UsageError(f"cannot read {what} {path}: {error.strerror}") from error
    except json.JSONDecodeError as error:
        raise UsageError(f"{what} {path} is not JSON: {error}") from error
    if not isinstance(data, dict):
        raise UsageError(f"{what} {path} is not a JSON object")
    return data


def read_node_ids(path: str) -> list[str]:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as error:
        raise UsageError(f"cannot read node ID file {path}: {error.strerror}") from error
    return [line.strip() for line in text.splitlines() if line.strip()]


def suite_node_ids(data: dict) -> list[str]:
    """The collected node IDs of a suite output, or the IDs of its test records."""
    collected = data.get("collected") or []
    return list(collected) if collected else [test["nodeid"] for test in data.get("tests", [])]


def rel(path: Path, base: Path) -> str:
    """`path` relative to `base` in POSIX form, or absolute when it is on another drive."""
    try:
        return Path(os.path.relpath(path, base)).as_posix()
    except ValueError:
        return path.as_posix()


def node_file(nodeid: str) -> str:
    return nodeid.split("::", 1)[0]


def tail(text: str, count: int) -> list[str]:
    return text.splitlines()[-count:]


def parse_failure(error: Exception) -> str:
    """The reason, for the output, that a Python file could not be read or parsed."""
    if isinstance(error, SyntaxError):
        version = f"{sys.version_info[0]}.{sys.version_info[1]}"
        return f"syntax error at line {error.lineno} under Python {version}: {error.msg}"
    if isinstance(error, UnicodeDecodeError):
        return "the file is not UTF-8 text"
    if isinstance(error, OSError):
        return f"cannot read the file: {error.strerror}"
    return str(error)


def git(project: Path, *args: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            ["git", "-C", str(project), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as error:
        raise UsageError(f"cannot run git: {error.strerror}") from error
