"""pin: record pinned requirement sources, and check a pin record.

Imported by lean_tests.py; never run directly. A pinned requirement source
is the user's request, or a spec or issue text, recorded with its SHA-256
hash before implementation starts. pin writes a new pin record and never
changes one. pin --check recomputes the hash of each pinned text, and with
--quote finds the pinned requirement sources that contain a quote.

pin --record without a file writes the record in lean-tests-pins/ of the Git
common folder of --project (#623). That folder lasts after a temporary folder
or a worktree is removed, each worktree of the clone can read it, and Git never
commits or pushes it. The record holds each source text, so pin --check needs
only the record.
"""

from __future__ import annotations

import datetime
import json
import os
import tempfile
from pathlib import Path

from lt_common import UsageError, git, load_json, sha256

PIN_FOLDER = "lean-tests-pins"


def pin_command(args) -> dict:
    if args.record is not None:
        if args.quote is not None:
            raise UsageError("--quote goes with --check")
        return pin_sources(args.record, args.source, Path(args.project))
    if args.source:
        raise UsageError("--source goes with --record")
    return check_pins(Path(args.check).resolve(), args.quote)


def pin_folder(project: Path) -> Path:
    """Return the private folder for pin records in the Git common folder of project, and make it."""
    result = git(project, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if result.returncode != 0:
        raise UsageError(
            f"pin --record without a file needs a Git checkout, and {project} is not one: "
            f"{result.stderr.strip()}; give --project or a record file"
        )
    folder = Path(result.stdout.strip()) / PIN_FOLDER
    try:
        folder.mkdir(mode=0o700, exist_ok=True)
    except OSError as error:
        raise UsageError(f"cannot make the pin folder {folder}: {error.strerror}") from error
    return folder


def write_record(record: str, project: Path, data: dict, stamp: str) -> Path:
    """Write data to a new record: the file record, or a new private file in the pin folder of project."""
    if record:
        path = Path(record).resolve()
        try:
            with open(path, "x", encoding="utf-8") as handle:
                json.dump(data, handle, indent=1)
        except FileExistsError as error:
            raise UsageError(f"the pin record {path} exists; pin writes a new record and never changes one") from error
        except OSError as error:
            raise UsageError(f"cannot write the pin record {path}: {error.strerror}") from error
        return path
    folder = pin_folder(project)
    try:
        # mkstemp makes a new file that only the user can read and write.
        handle, name = tempfile.mkstemp(prefix=f"pins-{stamp}-", suffix=".json", dir=folder)
    except OSError as error:
        raise UsageError(f"cannot write a pin record in {folder}: {error.strerror}") from error
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=1)
    except OSError as error:
        os.unlink(name)
        raise UsageError(f"cannot write the pin record {name}: {error.strerror}") from error
    return Path(name)


def pin_sources(record: str, specs: list[str], project: Path) -> dict:
    """Write each source's text and SHA-256 hash to a new pin record."""
    if not specs:
        raise UsageError("pin --record needs at least one --source NAME=PATH")
    sources = []
    for spec in specs:
        name, sep, path = spec.partition("=")
        if not (sep and name and path):
            raise UsageError(f"--source {spec!r} is not NAME=PATH")
        if any(source["name"] == name for source in sources):
            raise UsageError(f"the source name {name} appears twice")
        try:
            data = Path(path).read_bytes()
        except OSError as error:
            raise UsageError(f"cannot read the source {path}: {error.strerror}") from error
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as error:
            raise UsageError(f"the source {path} is not UTF-8 text") from error
        sources.append({
            "name": name, "path": str(Path(path).resolve()), "sha256": sha256(data), "bytes": len(data), "text": text,
        })
    now = datetime.datetime.now(datetime.timezone.utc)
    pinned_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    path = write_record(record, project, {"pinned_at": pinned_at, "sources": sources}, now.strftime("%Y%m%dT%H%M%SZ"))
    return {
        "summary": {
            "record": str(path),
            "pinned_at": pinned_at,
            "sources": len(sources),
            "sha256": {source["name"]: source["sha256"] for source in sources},
        },
        "sources": [{k: v for k, v in source.items() if k != "text"} for source in sources],
    }


def check_pins(record: Path, quote: str | None) -> dict:
    """Recompute the hash of each pinned text, and find the pinned requirement sources that contain a quote."""
    data = load_json(str(record), "pin record")
    sources = data.get("sources")
    if not isinstance(sources, list) or not all(
        isinstance(s, dict) and isinstance(s.get("text"), str) and "name" in s and "sha256" in s for s in sources
    ):
        raise UsageError(f"{record} is not a pin record")
    entries = [
        {"name": s["name"], "sha256": s["sha256"], "intact": sha256(s["text"].encode("utf-8")) == s["sha256"]}
        for s in sources
    ]
    changed = [entry["name"] for entry in entries if not entry["intact"]]
    found = None
    if quote is not None:
        needle = " ".join(quote.split())
        if not needle:
            raise UsageError("--quote is empty")
        found = [{"name": s["name"], "sha256": s["sha256"]} for s in sources if needle in " ".join(s["text"].split())]
    return {
        "summary": {
            "passed": not changed and (found is None or bool(found)),
            "record": str(record),
            "pinned_at": data.get("pinned_at"),
            "sources": len(entries),
            "changed": changed,
            "quote_found_in": None if found is None else [entry["name"] for entry in found],
        },
        "sources": entries,
        "quote": None if quote is None else {"text": quote, "found_in": found},
    }
