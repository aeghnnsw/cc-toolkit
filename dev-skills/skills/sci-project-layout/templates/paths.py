"""Paths of this project: the store, and one new folder for each run.

docs/agents/layout.md shows how to make a run with new_run().
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator

_HERE = Path(__file__).resolve().parent  # run git here, never in the current folder
REPO = _HERE.parent.parent  # src/myproj/paths.py is two folders below the checkout
# Parts below DATA of a version folder: raw/<source>/<dataset>/<version>, processed/<dataset>/<version>
_VERSION_DEPTH = {"raw": 4, "processed": 3}


class StoreError(RuntimeError):
    """The store cannot be found. The message says how to set it."""


def _git(*args: str) -> str | None:
    """Return git's output in this checkout, or None when git fails or is not installed."""
    try:
        out = subprocess.run(["git", "-C", str(_HERE), *args], capture_output=True, text=True)
    except FileNotFoundError:
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def _absolute(value: str, source: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise StoreError(f"{source} must be an absolute path, not: {value}")
    return path


def _store_root() -> Path:
    if env := os.environ.get("MYPROJ_STORE"):
        return _absolute(env, "MYPROJ_STORE")
    if _git("rev-parse", "--is-inside-work-tree") != "true":
        raise StoreError(
            f"Cannot find the store: {_HERE} is not in a git checkout, or git is not "
            "installed. Set MYPROJ_STORE to the absolute path of the store."
        )
    if cfg := _git("config", "--local", "--get", "layout.store"):
        return _absolute(cfg, "git config layout.store")
    common = Path(_git("rev-parse", "--path-format=absolute", "--git-common-dir") or "")
    if not common.is_absolute() or common.name != ".git":
        raise StoreError("Cannot find the main checkout. Run: git config layout.store <path>")
    return common.parent


STORE = _store_root()
DATA = STORE / "data"
RESULTS = STORE / "results"


@dataclass
class Run:
    id: str
    dir: Path
    info: dict  # the run.json record; a step can add keys


def _input_entry(path: Path) -> str:
    """Return the run.json entry of a data-version folder or a run folder."""
    found = Path(path).resolve()
    data, results = DATA.resolve(), RESULTS.resolve()
    if found.is_dir() and found.is_relative_to(data):
        parts = found.relative_to(data).parts
        if parts and len(parts) == _VERSION_DEPTH.get(parts[0]):
            return "/".join(("data", *parts))
    if found.is_dir() and found.is_relative_to(results):
        parts = found.relative_to(results).parts
        if len(parts) == 2 and (found / "run.json").is_file():
            return "/".join(("results", *parts))
    raise ValueError(
        f"Not a data version or a run folder: {path}. inputs takes "
        "paths.DATA / 'raw/<source>/<dataset>/<version>', "
        "paths.DATA / 'processed/<dataset>/<version>', or paths.RESULTS / '<key>/<run-id>'. "
        "Tracked files need no entry: they are pinned by the recorded commit."
    )


def _git_state() -> dict:
    sha = _git("rev-parse", "HEAD")
    if not sha:
        return {"sha": None, "branch": None, "dirty": None}
    branch = _git("branch", "--show-current") or None
    status = _git("status", "--porcelain", "--untracked-files=normal")
    return {"sha": sha, "branch": branch, "dirty": None if status is None else bool(status)}


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _write(run: Run) -> None:
    (run.dir / "run.json").write_text(json.dumps(run.info, indent=2) + "\n")


@contextmanager
def new_run(key: str, step: str, label: str | None = None, inputs: Iterable[Path] = ()) -> Iterator[Run]:
    """Make results/<key>/<run-id>/ and record the run in run.json."""
    experiment = REPO / "experiments" / key
    if not experiment.is_dir():
        raise ValueError(f"No experiment folder: {experiment}")
    recorded = [_input_entry(path) for path in inputs]
    started = datetime.now().astimezone()
    base = started.strftime("%Y%m%d-%H%M%S") + (f"_{label}" if label else "")
    (RESULTS / key).mkdir(parents=True, exist_ok=True)
    run_id, n = base, 1
    while True:
        try:
            (RESULTS / key / run_id).mkdir()
            break
        except FileExistsError:  # a run started in the same second with the same label
            n += 1
            run_id = f"{base}-{n}"
    run = Run(run_id, RESULTS / key / run_id, {
        "run_id": run_id,
        "experiment": key,
        "step": step,
        "status": "running",
        "started_at": started.isoformat(timespec="seconds"),
        "finished_at": None,
        "argv": list(sys.argv),
        "git": _git_state(),
        "inputs": recorded,
    })
    if (experiment / "config.yaml").is_file():
        shutil.copyfile(experiment / "config.yaml", run.dir / "config.yaml")
    _write(run)
    try:
        yield run
    except BaseException:
        run.info.update(status="failed", finished_at=_now())
        _write(run)
        raise
    run.info.update(status="succeeded", finished_at=_now())
    _write(run)
