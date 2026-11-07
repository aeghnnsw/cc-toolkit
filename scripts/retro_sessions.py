#!/usr/bin/env python3
"""Prepare local transcript copies and bounded retrospective evidence."""

import argparse
from collections import deque
from datetime import datetime, timezone
from fractions import Fraction
import json
import os
from pathlib import Path
import re
import subprocess
import stat
import sys


CLAUDE_AUXILIARY = (
    "file-history-snapshot", "queue-operation", "progress", "system", "summary",
    "custom-title", "last-prompt", "agent-name", "agent-color", "mode",
    "api-request", "cost-state",
)
CODEX_AUXILIARY = (
    "token_count", "task_started", "task_complete", "turn_aborted",
    "user_message", "agent_message", "agent_reasoning", "item_started",
)


def timestamp(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise ValueError("timestamps must include a timezone")
    delta = parsed - datetime(1970, 1, 1, tzinfo=timezone.utc)
    instant = Fraction((delta.days * 86400 + delta.seconds) * 1000000 + delta.microseconds, 1000000)
    # datetime truncates precision after microseconds. Retain the remaining
    # fractional seconds so an explicit cutoff never shifts the interval.
    fraction = re.search(r"[Tt ]\d{2}:?\d{2}(?::?\d{2})?[.,](\d+)", value)
    offset = re.search(r"([+-])\d{2}(?::?\d{2})?(?::?\d{2})?[.,](\d+)$", value)
    for digits, sign in ((fraction[1] if fraction else "", 1),
                         (offset[2] if offset else "", -1 if offset and offset[1] == "+" else 1)):
        if len(digits) > 6:
            instant += sign * Fraction(int(digits[6:]), 10 ** len(digits))
    return instant


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def content_events(content, kind, unknown, ignored):
    if isinstance(content, str):
        return [{"kind": kind, "text": content}]
    events = []
    if not isinstance(content, list):
        unknown.append("content:" + type(content).__name__)
        return events
    for block in content:
        if not isinstance(block, dict):
            unknown.append("block:" + type(block).__name__)
            continue
        block_type = block.get("type")
        if block_type in ("text", "input_text", "output_text") and isinstance(block.get("text"), str):
            events.append({"kind": kind, "text": block["text"]})
        elif block_type == "tool_use":
            events.append({"kind": "tool_call", "tool": block.get("name"),
                           "call_id": block.get("id"), "text": json.dumps(block.get("input"))})
        elif block_type == "tool_result":
            for event in content_events(block.get("content"), "tool_result", unknown, ignored):
                event.update(call_id=block.get("tool_use_id"), is_error=block.get("is_error") is True)
                events.append(event)
        elif block_type in ("thinking", "redacted_thinking", "reasoning"):
            ignored.append(str(block_type))
        else:
            unknown.append("block:" + str(block_type)[:100])
    return events


def record_events(record, host, unknown, ignored):
    kind = record.get("type")
    if host == "claude":
        if kind in ("user", "assistant"):
            message = record.get("message")
            return content_events(message.get("content") if isinstance(message, dict) else None,
                                  kind, unknown, ignored)
        if kind in CLAUDE_AUXILIARY:
            ignored.append(str(kind))
        else:
            unknown.append("record:" + str(kind)[:100])
        return []
    payload = record.get("payload", {})
    if not isinstance(payload, dict):
        unknown.append("payload:" + type(payload).__name__)
        return []
    payload_type = payload.get("type")
    if kind == "response_item":
        if payload_type == "message":
            return content_events(payload.get("content"), payload.get("role", "message"), unknown, ignored)
        if payload_type in ("function_call", "custom_tool_call"):
            return [{"kind": "tool_call", "tool": payload.get("name"),
                     "call_id": payload.get("call_id"),
                     "text": payload.get("arguments", payload.get("input", ""))}]
        if payload_type in ("function_call_output", "custom_tool_call_output"):
            events = content_events(payload.get("output"), "tool_result", unknown, ignored)
            for event in events:
                event["call_id"] = payload.get("call_id")
            return events
        if payload_type == "reasoning":
            ignored.append("reasoning")
            return []
    if kind == "event_msg" and payload_type == "item_completed":
        item = payload.get("item", {})
        if not isinstance(item, dict):
            unknown.append("item:" + type(item).__name__)
            return []
        if item.get("type") == "CommandExecution":
            text = json.dumps({key: item.get(key) for key in
                               ("command", "cwd", "status", "exit_code", "aggregated_output")})
            return [{"kind": "command_execution", "call_id": item.get("id"), "text": text}]
        if item.get("type") in ("AgentMessage", "UserMessage", "Reasoning"):
            ignored.append("duplicate:" + item["type"])
            return []
        unknown.append("item:" + str(item.get("type"))[:100])
        return []
    if kind in ("session_meta", "turn_context") or (kind == "event_msg" and payload_type in CODEX_AUXILIARY):
        ignored.append(str(payload_type or kind))
    else:
        unknown.append(str(kind)[:100] + ":" + str(payload_type)[:100])
    return []


def extract(stream, host, repository_roots, after, through, max_events, max_text):
    events = []
    tail = deque(maxlen=max_events // 2)
    head_size = (max_events + 1) // 2
    eligible_events = 0
    diagnostics = []
    diagnostic_index = {}
    def diagnose(code, line, **detail):
        key = (code, detail.get("type"))
        if key not in diagnostic_index:
            item = {"code": code, "line": line, **detail}
            diagnostic_index[key] = item
            diagnostics.append(item)
            return
        item = diagnostic_index[key]
        item["count"] = item.get("count", 1) + 1
        lines = item.setdefault("lines", [item["line"]])
        if len(lines) < 20:
            lines.append(line)
        else:
            item["omitted_line_references"] = item.get("omitted_line_references", 0) + 1

    ignored_types = {}
    counts = {"records": 0, "foreign_records": 0, "outside_window_records": 0,
              "unattributed_records": 0, "ignored_records": 0, "unsupported_items": 0}
    selected = False
    cwd = None
    for line, raw in enumerate(stream, 1):
        counts["records"] += 1
        try:
            record = json.loads(raw)
        except (ValueError, UnicodeError):
            diagnose("malformed_json" if raw.endswith(b"\n") else "incomplete_tail", line)
            continue
        if not isinstance(record, dict):
            diagnose("unsupported_record", line)
            continue
        kind = record.get("type")
        if host == "claude":
            if "cwd" in record:
                cwd = record["cwd"]
        else:
            payload = record.get("payload", {})
            if kind in ("session_meta", "turn_context") and isinstance(payload, dict):
                cwd = payload.get("cwd", cwd)
        unknown, ignored = [], []
        rendered = record_events(record, host, unknown, ignored)
        if ignored:
            counts["ignored_records"] += 1
            for ignored_type in ignored:
                ignored_types[ignored_type] = ignored_types.get(ignored_type, 0) + 1
        if not rendered and not unknown:
            continue
        if not isinstance(cwd, str) or not Path(cwd).is_absolute():
            counts["unattributed_records"] += 1
            diagnose("missing_cwd", line)
            continue
        try:
            current_path = Path(cwd).resolve()
        except (OSError, ValueError, RuntimeError):
            counts["unattributed_records"] += 1
            diagnose("invalid_cwd", line)
            continue
        if not any(current_path.is_relative_to(root) for root in repository_roots):
            counts["foreign_records"] += 1
            continue
        try:
            instant = timestamp(record["timestamp"])
        except (ValueError, TypeError, KeyError, AttributeError):
            selected = True
            diagnose("invalid_timestamp", line)
            continue
        if (after is not None and instant <= after) or instant > through:
            counts["outside_window_records"] += 1
            continue
        selected = True
        for shape in unknown:
            counts["unsupported_items"] += 1
            diagnose("unsupported_content", line, type=shape)
        for event in rendered:
            eligible_events += 1
            event = {"line": line, "timestamp": record["timestamp"],
                     "cwd": cwd, "omitted_characters": 0, **event}
            bounded = bound_event(event, max_text)
            if len(events) < head_size:
                events.append(bounded)
            else:
                tail.append(bounded)
    events.extend(tail)
    counts.update(eligible_events=eligible_events, shown_events=len(events),
                  omitted_events=eligible_events - len(events),
                  clipped_characters=sum(event["omitted_characters"] for event in events))
    return {"selected": selected, "events": events, "counts": counts,
            "diagnostics": diagnostics, "ignored_types": ignored_types}


def bound_event(event, max_text):
    text = event["text"]
    if not isinstance(text, str):
        text = json.dumps(text, ensure_ascii=False)
    event["text"] = text[:max_text]
    event["omitted_characters"] = max(0, len(text) - max_text)
    for field in ("cwd", "tool", "call_id", "kind", "timestamp"):
        value = event.get(field)
        if value is not None:
            value = value if isinstance(value, str) else json.dumps(value)
            event[field] = value[:max_text]
            if len(value) > max_text:
                event.setdefault("metadata_omitted_characters", {})[field] = len(value) - max_text
    return event


def snapshot(path, destination):
    """Copy a fixed prefix. Appends beyond that prefix are outside this run."""
    diagnostics = []
    try:
        before = path.stat()
        if not stat.S_ISREG(before.st_mode):
            return 0, 0, [{"code": "source_not_regular"}]
        source = path.open("rb")
    except OSError:
        return 0, 0, [{"code": "source_unavailable"}]
    copied = 0
    boundary = before.st_size
    with source:
        opened = os.fstat(source.fileno())
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            diagnostics.append({"code": "source_replaced"})
        with destination.open("xb") as target:
            while copied < boundary:
                try:
                    block = source.read(min(1024 * 1024, boundary - copied))
                except OSError:
                    diagnostics.append({"code": "source_read_error"})
                    break
                if not block:
                    break
                target.write(block)
                copied += len(block)
        after_read = os.fstat(source.fileno())
    if copied < boundary:
        diagnostics.append({"code": "short_read"})
    if after_read.st_size < boundary:
        diagnostics.append({"code": "source_truncated"})
    elif after_read.st_size == boundary and after_read.st_mtime_ns != opened.st_mtime_ns:
        diagnostics.append({"code": "source_modified"})
    try:
        current = path.stat()
        if (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
            diagnostics.append({"code": "source_replaced"})
    except OSError:
        diagnostics.append({"code": "source_unavailable_after_copy"})
    return boundary, copied, diagnostics


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, epilog=(
        "Any explicit host root replaces all default discovery. Otherwise read "
        "default and active host config roots. A partial result retains usable "
        "evidence; inspect manifest diagnostics. Originals remain unchanged."))
    parser.add_argument("--repo", required=True, type=Path, help="target Git checkout")
    parser.add_argument("--output", required=True, type=Path, help="new directory outside transcript roots")
    parser.add_argument("--through", help="inclusive aware ISO cutoff (default: now, before discovery)")
    parser.add_argument("--after", help="exclusive aware ISO cutoff (default: no lower bound)")
    parser.add_argument("--max-events", type=int, default=60, help="head/tail events per digest (default: 60)")
    parser.add_argument("--max-text", type=int, default=300, help="characters per displayed text field (default: 300)")
    parser.add_argument("--claude-root", action="append", type=Path, default=[], help="Claude projects directory; repeatable")
    parser.add_argument("--codex-root", action="append", type=Path, default=[], help="Codex sessions directory; repeatable")
    args = parser.parse_args(argv)
    through_text = args.through if args.through is not None else datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    try:
        through = timestamp(through_text)
        after = timestamp(args.after) if args.after is not None else None
    except ValueError as error:
        parser.error(str(error))
    if after is not None and after >= through:
        parser.error("--after must be earlier than --through")
    if args.max_events < 1 or args.max_text < 1:
        parser.error("--max-events and --max-text must be positive")
    if not args.claude_root and not args.codex_root:
        args.claude_root = [Path.home() / ".claude" / "projects"]
        args.codex_root = [Path.home() / ".codex" / "sessions"]
        if os.environ.get("CLAUDE_CONFIG_DIR"):
            args.claude_root.append(Path(os.environ["CLAUDE_CONFIG_DIR"]).expanduser() / "projects")
        if os.environ.get("CODEX_HOME"):
            args.codex_root.append(Path(os.environ["CODEX_HOME"]).expanduser() / "sessions")
    args.claude_root = list(dict.fromkeys(path.expanduser().resolve() for path in args.claude_root))
    args.codex_root = list(dict.fromkeys(path.expanduser().resolve() for path in args.codex_root))
    try:
        worktrees = subprocess.check_output(
            ["git", "-C", str(args.repo), "worktree", "list", "--porcelain", "-z"],
            text=True, stderr=subprocess.PIPE)
    except (OSError, subprocess.CalledProcessError):
        parser.error("--repo must name an accessible Git checkout")
    repository_roots = list(dict.fromkeys(Path(field[9:]).resolve()
                                         for field in worktrees.split("\0") if field.startswith("worktree ")))
    if not repository_roots or "bare" in worktrees.split("\0"):
        parser.error("--repo must name a non-bare Git checkout")
    repo = repository_roots[0]
    output = args.output.expanduser().resolve()
    if args.output.exists() or args.output.is_symlink():
        parser.error("--output must be a new path")
    if any(output.is_relative_to(root) for root in args.claude_root + args.codex_root):
        parser.error("--output must be outside all transcript roots")
    output.mkdir(mode=0o700)
    (output / "raw").mkdir()
    (output / "digests").mkdir()
    sources = []
    totals = {"eligible_events": 0, "shown_events": 0, "omitted_events": 0,
              "clipped_characters": 0, "records": 0, "foreign_records": 0,
              "outside_window_records": 0, "unattributed_records": 0,
              "ignored_records": 0, "unsupported_items": 0}
    roots = []
    candidates = 0
    diagnostics = []
    seen_paths = set()
    for host, paths in (("claude", args.claude_root), ("codex", args.codex_root)):
        for root in paths:
            if not root.is_dir():
                roots.append({"host": host, "path": str(root.resolve()), "status": "unavailable", "candidates": 0})
                diagnostics.append({"code": "root_unavailable", "host": host, "path": str(root.resolve())})
                continue
            root_entry = {"host": host, "path": str(root), "status": "ok", "candidates": 0}
            roots.append(root_entry)
            def walk_error(error):
                root_entry["status"] = "partial"
                diagnostics.append({"code": "directory_unavailable", "host": host, "path": error.filename})

            files = []
            for directory, folders, names in os.walk(root, onerror=walk_error):
                folders.sort()
                files.extend(Path(directory) / name for name in sorted(names) if name.endswith(".jsonl"))
            for path in files:
                path = path.resolve()
                if path in seen_paths:
                    continue
                seen_paths.add(path)
                candidates += 1
                root_entry["candidates"] += 1
                alias = f"source-{candidates:04d}"
                copy = f"raw/{alias}.jsonl"
                digest = f"digests/{alias}.json"
                boundary, copied, copy_diagnostics = snapshot(path, output / copy)
                if not (output / copy).exists():
                    diagnostics.extend({"path": str(path), "host": host, **item} for item in copy_diagnostics)
                    continue
                with (output / copy).open("rb") as stream:
                    extracted = extract(stream, host, repository_roots, after, through,
                                        args.max_events, args.max_text)
                extracted["diagnostics"] = copy_diagnostics + extracted["diagnostics"]
                for key in totals:
                    totals[key] += extracted["counts"][key]
                if not extracted["selected"]:
                    diagnostics.extend({"path": str(path.resolve()), "host": host, **item}
                                       for item in extracted["diagnostics"])
                    (output / copy).unlink()
                    continue
                events, counts = extracted["events"], extracted["counts"]
                write_json(output / digest, {"source": alias, "host": host,
                                            "copy": copy, "events": events, "counts": counts,
                                            "diagnostics": extracted["diagnostics"],
                                            "ignored_types": extracted["ignored_types"]})
                sources.append({"host": host, "path": str(path.resolve()), "selected": True,
                                "copy": copy, "digest": digest, "boundary_bytes": boundary,
                                "copied_bytes": copied, "counts": counts,
                                "diagnostics": extracted["diagnostics"]})
    diagnostic_count = sum(item.get("count", 1) for item in diagnostics)
    diagnostic_count += sum(item.get("count", 1) for source in sources for item in source["diagnostics"])
    status = "partial" if diagnostic_count else "ok"
    manifest = {"schema_version": 1, "status": status,
                "repository": {"requested": str(args.repo.resolve()), "main": str(repo),
                               "roots": [str(root) for root in repository_roots]},
                "window": {"after": args.after, "through": through_text},
                "limits": {"max_events": args.max_events, "max_text": args.max_text},
                "roots": roots, "sources": sources, "diagnostics": diagnostics,
                "limitations": ["Removed external worktrees cannot be attributed without current Git registration.",
                                "Copies are measured byte prefixes, not atomic filesystem snapshots.",
                                "Raw copies can include records outside the repository and time window.",
                                "Digests are evidence indexes, not complete semantic reviews."],
                "counts": {"candidate_sources": candidates, "selected_sources": len(sources),
                           "skipped_sources": candidates - len(sources), **totals, "diagnostics": diagnostic_count}}
    write_json(output / "manifest.json", manifest)
    print(json.dumps({"status": status, "manifest": str(output / "manifest.json"),
                      "selected_sources": len(sources), "eligible_events": totals["eligible_events"],
                      "omitted_events": totals["omitted_events"], "diagnostics": diagnostic_count}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except OSError as error:
        print(f"retro_sessions.py: output error: {error}", file=sys.stderr)
        raise SystemExit(2)
