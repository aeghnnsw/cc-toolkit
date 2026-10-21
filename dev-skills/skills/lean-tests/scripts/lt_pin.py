"""pin: record pinned requirement sources, and check a pin record.

Imported by lean_tests.py; never run directly. A pinned requirement source
is the user's request, or a spec or issue text, recorded with its SHA-256
hash before implementation starts. pin writes a new pin record and never
changes one. pin --check recomputes the hash of each pinned text, and with
--quote finds the pinned requirement sources that contain a quote.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path

from lt_common import UsageError, load_json, sha256


def pin_command(args) -> dict:
    if args.record:
        if args.quote is not None:
            raise UsageError("--quote goes with --check")
        return pin_sources(Path(args.record).resolve(), args.source)
    if args.source:
        raise UsageError("--source goes with --record")
    return check_pins(Path(args.check).resolve(), args.quote)


def pin_sources(record: Path, specs: list[str]) -> dict:
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
    pinned_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        with open(record, "x", encoding="utf-8") as handle:
            json.dump({"pinned_at": pinned_at, "sources": sources}, handle, indent=1)
    except FileExistsError as error:
        raise UsageError(f"the pin record {record} exists; pin writes a new record and never changes one") from error
    except OSError as error:
        raise UsageError(f"cannot write the pin record {record}: {error.strerror}") from error
    return {
        "summary": {
            "record": str(record),
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
