#!/usr/bin/env python3
"""Prepare local transcript copies and bounded retrospective evidence."""

import argparse
from collections import deque
from contextlib import closing
from datetime import datetime, timezone
from fractions import Fraction
from functools import lru_cache
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import stat
import sys
import tempfile
from urllib.parse import unquote, urlsplit


CLAUDE_AUXILIARY = (
    "file-history-snapshot", "queue-operation", "progress", "system", "summary",
    "custom-title", "last-prompt", "agent-name", "agent-color", "mode",
    "api-request", "cost-state",
    "atis-latch", "api-request-blob", "ai-title", "permission-mode",
    "relocated", "worktree-state",
)
CODEX_AUXILIARY = (
    "token_count", "task_started", "task_complete", "turn_aborted",
    "user_message", "agent_message", "agent_reasoning", "item_started",
)
# Antigravity step types with a fixed event kind. Other step types become
# their lowercase name, for example "generic".
ANTIGRAVITY_KINDS = {"USER_INPUT": "user", "PLANNER_RESPONSE": "assistant"}
# An ISO 8601 time: date, T or space, hours and minutes, optional seconds and
# fraction digits, then Z or an offset with or without a colon. The pattern
# reads the same forms on every Python version.
TIMESTAMP = re.compile(r"(\d{4}-\d\d-\d\d[Tt ]\d\d:\d\d(?::\d\d)?)(?:[.,](\d+))?"
                       r"(?:(Z)|([+-]\d\d)(?::?(\d\d))?)?", re.ASCII)
# A timeline flags an event that starts this many seconds or more after the
# previous window event of its source.
GAP_SECONDS = 30
# Some file systems store modification times in steps of up to 2 s, rounded
# down. A source is skipped only when it was modified this many seconds or
# more before --after, so a rounded time never hides a later record.
MTIME_STEP_SECONDS = 2
# Claude Code returns a blocked tool call as an error result that starts with
# the hook event and tool, for example "PreToolUse:Bash hook error: ...".
HOOK_BLOCK = re.compile(r"\w+:\S+ hook error:")
TIMELINE_HEADER = "line\ttime\tkind\ttool\tflags\ttext\n"


def timestamp(value):
    """Return the instant of an aware ISO 8601 time as exact seconds since 1970.

    The time can be in backticks, as in a retrospective record. Every fraction
    digit counts, so an explicit cutoff never shifts the interval.
    """
    match = TIMESTAMP.fullmatch(value[1:-1] if value[:1] == value[-1:] == "`" else value)
    if not match:
        raise ValueError(f"invalid ISO 8601 time: {value!r}")
    clock, digits, utc, hours, minutes = match.groups()
    if not (utc or hours):
        raise ValueError("timestamps must include a timezone")
    # Python 3.9 and 3.10 read an offset only with a colon, and a fraction only
    # with 3 or 6 digits, so the fraction is added separately.
    parsed = datetime.fromisoformat(f"{clock}{hours or '+00'}:{minutes or '00'}")
    delta = parsed - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return delta.days * 86400 + delta.seconds + Fraction(int(digits or "0"), 10 ** len(digits or ""))


@lru_cache(maxsize=None)
def folder_missing(folder):
    """Return True when FOLDER does not exist, and False when it exists or cannot be checked."""
    try:
        return not folder.exists()
    except OSError:
        return False


def removed_worktree(path, linked_parents):
    """Return the removed worktree folder that holds the resolved PATH, or None.

    The candidate is PATH or its nearest ancestor whose parent folder holds a
    linked worktree that Git lists. The candidate is removed when it does not
    exist.
    """
    for folder in (path, *path.parents):
        if folder != folder.parent and folder.parent in linked_parents:
            return folder if folder_missing(folder) else None
    return None


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


def antigravity_events(record, unknown, ignored):
    """Return the events of one transcript_full.jsonl step.

    The content becomes one event of the step's kind. Each tool_calls entry
    becomes a tool_call event. A step with neither is an ignored record.
    """
    step_type = record.get("type")
    if not isinstance(step_type, str):
        unknown.append("record:" + type(step_type).__name__)
        return []
    content = record.get("content")
    kind = ANTIGRAVITY_KINDS.get(step_type, step_type.lower()[:100])
    events = [] if content in (None, "") else content_events(content, kind, unknown, ignored)
    calls = record.get("tool_calls") or []
    if not isinstance(calls, list):
        unknown.append("tool_calls:" + type(calls).__name__)
        calls = []
    for call in calls:
        if isinstance(call, dict):
            events.append({"kind": "tool_call", "tool": call.get("name"),
                           "call_id": call.get("id"), "text": call.get("args")})
        else:
            unknown.append("tool_call:" + type(call).__name__)
    if not events and not unknown:
        ignored.append(step_type[:100])
    return events


def record_events(record, host, unknown, ignored):
    kind = record.get("type")
    if host == "antigravity":
        return antigravity_events(record, unknown, ignored)
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


def timeline_cell(value, max_text):
    """Return VALUE as one line without tabs, clipped to MAX_TEXT characters."""
    if value is None:
        return "-"
    text = " ".join((value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)).split())
    if len(text) > max_text:
        return f"{text[:max_text]} [+{len(text) - max_text} chars]"
    return text or "-"


def timeline_line(line, time, event, tool, gap, max_text):
    """Return the timeline line of one window event.

    GAP is the number of seconds since the previous window event of the
    source, or None for the first one.
    """
    flags = []
    if gap is not None and gap >= GAP_SECONDS:
        flags.append(f"gap={int(gap)}s")
    if event.get("is_error") is True:
        flags.append("error")
        if isinstance(event["text"], str) and HOOK_BLOCK.match(event["text"]):
            flags.append("hook_block")
    time, kind, tool, text = (timeline_cell(value, max_text) for value in (time, event["kind"], tool, event["text"]))
    return "\t".join([str(line), time, kind, tool, ",".join(flags) or "-", text]) + "\n"


def extract(stream, host, repository_roots, after, through, max_events, max_text, cwd=None,
            linked_parents=frozenset()):
    """Return the bounded digest and the timeline of one transcript.

    CWD is the starting working folder. Antigravity records carry no cwd, so
    the caller gives the matched workspace folder. LINKED_PARENTS holds the
    parent folder of each linked worktree that Git lists; a foreign record in
    the window whose cwd is in a removed folder there gets a removed_worktree
    diagnostic.
    """
    timeline = []
    tool_names = {}
    previous_instant = None
    events = []
    tail = deque(maxlen=max_events // 2)
    head_size = (max_events + 1) // 2
    eligible_events = 0
    diagnostics = []
    diagnostic_index = {}
    def diagnose(code, line, **detail):
        key = (code, detail.get("type"), detail.get("worktree"))
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
    time_field = "created_at" if host == "antigravity" else "timestamp"
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
        elif host == "codex":
            payload = record.get("payload", {})
            if kind in ("session_meta", "turn_context") and isinstance(payload, dict):
                cwd = payload.get("cwd", cwd)
        unknown, ignored = [], []
        rendered = record_events(record, host, unknown, ignored)
        for event in rendered:
            if event["kind"] == "tool_call" and isinstance(event.get("call_id"), str):
                tool_names[event["call_id"]] = event.get("tool")
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
            worktree = removed_worktree(current_path, linked_parents)
            if worktree is not None:
                try:
                    instant = timestamp(record[time_field])
                except (ValueError, TypeError, KeyError, AttributeError):
                    instant = None
                if instant is not None and (after is None or instant > after) and instant <= through:
                    diagnose("removed_worktree", line, worktree=str(worktree),
                             message="Pass this worktree path with --worktree to select these records.")
            continue
        try:
            instant = timestamp(record[time_field])
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
            call_id = event.get("call_id")
            if event["kind"] == "tool_call":
                tool = event.get("tool")
            else:
                tool = tool_names.get(call_id) if isinstance(call_id, str) else None
            timeline.append(timeline_line(line, record[time_field], event, tool,
                                          None if previous_instant is None else instant - previous_instant, max_text))
            previous_instant = instant
            event = {"line": line, "timestamp": record[time_field],
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
    return {"selected": selected, "events": events, "timeline": timeline, "counts": counts,
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


def repository_workspace(uris, repository_roots):
    """Return the first file:// workspace path in URIS inside a repository root, or None."""
    workspaces = json.loads(uris)
    if not isinstance(workspaces, list):
        raise ValueError("workspace_uris is not a list")
    for uri in workspaces:
        parts = urlsplit(uri) if isinstance(uri, str) else None
        if parts is None or parts.scheme != "file" or parts.netloc not in ("", "localhost"):
            continue
        path = unquote(parts.path)
        if Path(path).is_absolute() and any(Path(path).resolve().is_relative_to(root) for root in repository_roots):
            return path
    return None


def antigravity_sources(root, repository_roots):
    """Return ([(transcript, workspace)], diagnostics) for the repository's conversations.

    Read a temporary copy of conversation_summaries.db and its -wal and -shm
    files, so a live or locked database stays unchanged. A conversation
    belongs to the repository when one of its workspace_uris, resolved, is a
    repository root or is inside one.
    """
    database = root / "conversation_summaries.db"
    with tempfile.TemporaryDirectory() as folder:
        for suffix in ("", "-wal", "-shm"):
            source = database.with_name(database.name + suffix)
            try:
                shutil.copyfile(source, Path(folder) / source.name)
            except OSError as error:
                if suffix and isinstance(error, FileNotFoundError):
                    continue  # A database without a write-ahead log is complete.
                return [], [{"code": "database_unavailable", "host": "antigravity", "path": str(source)}]
        try:
            with closing(sqlite3.connect(Path(folder) / database.name)) as connection:
                rows = connection.execute("SELECT conversation_id, workspace_uris FROM conversation_summaries "
                                          "ORDER BY conversation_id").fetchall()
        except sqlite3.Error:
            return [], [{"code": "database_unreadable", "host": "antigravity", "path": str(database)}]
    sources, diagnostics = [], []
    for conversation, uris in rows:
        try:
            workspace = repository_workspace(uris, repository_roots)
        except (ValueError, TypeError, OSError, RuntimeError):
            diagnostics.append({"code": "invalid_workspace", "host": "antigravity", "path": str(database),
                                "conversation_id": str(conversation)[:100]})
            continue
        if workspace is None:
            continue
        if not isinstance(conversation, str) or conversation in ("", ".", "..") or Path(conversation).name != conversation:
            diagnostics.append({"code": "invalid_conversation_id", "host": "antigravity", "path": str(database),
                                "conversation_id": str(conversation)[:100]})
            continue
        transcript = root / "brain" / conversation / ".system_generated" / "logs" / "transcript_full.jsonl"
        sources.append((transcript, workspace))
    return sources, diagnostics


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
        "A root option replaces only the default roots of its own host; the "
        "other hosts keep theirs. Default roots: Claude Code reads projects/ in "
        "~/.claude, in each ~/.claude-t3/<profile> folder, and in "
        "CLAUDE_CONFIG_DIR; Codex reads sessions/ in ~/.codex and in CODEX_HOME; "
        "Antigravity reads ~/.gemini/antigravity-cli, ~/.gemini/antigravity, and "
        "antigravity-acp in each ~/.t3/userdata/providers/antigravity/<profile> "
        "folder. The manifest lists each root with its status. "
        "The repository roots are the worktrees that git worktree list shows and "
        "each --worktree path. Without --worktree, a Claude Code or Codex source "
        "with a record in the window whose cwd is in a missing folder in the same "
        "parent folder as a linked worktree that Git lists gets a removed_worktree "
        "diagnostic; its worktree field names the folder to pass with --worktree. "
        f"With --after, a source modified {MTIME_STEP_SECONDS} s or more before that "
        "cutoff is not copied or read; counts.unchanged_sources counts it. "
        "Each selected source has a digest and a timeline: one tab-separated "
        "line for each window event, with its line, time, kind, tool, flags, "
        f"and clipped text. Flags mark gaps of {GAP_SECONDS} s or more, and the "
        "is_error results and hook blocks of Claude Code. "
        "A partial result retains usable evidence; inspect manifest diagnostics. "
        "Originals remain unchanged."))
    parser.add_argument("--repo", required=True, type=Path, help="target Git checkout")
    parser.add_argument("--output", required=True, type=Path, help="new directory outside transcript roots")
    parser.add_argument("--through", help=(
        "inclusive cutoff: an ISO 8601 time with Z or an offset, in backticks or not, such as "
        "2026-11-21T05:16:55Z, 2026-10-27T15:02:52.722Z, or `2026-11-09T00:22:55.226+00:00` "
        "(default: now, before discovery)"))
    parser.add_argument("--after", help=(
        "exclusive cutoff in the forms of --through, such as a Reviewed through cutoff "
        "copied from a retrospective record (default: no lower bound)"))
    parser.add_argument("--worktree", action="append", type=Path, default=[], metavar="PATH", help=(
        "worktree path that Git no longer lists, such as one that T3 Code removed; repeatable; "
        "adds the path to the repository roots"))
    parser.add_argument("--max-events", type=int, default=60, help="head/tail events per digest (default: 60)")
    parser.add_argument("--max-text", type=int, default=300, help="characters per displayed text field (default: 300)")
    parser.add_argument("--claude-root", action="append", type=Path, default=[],
                        help="Claude projects directory; repeatable; replaces the Claude Code default roots")
    parser.add_argument("--codex-root", action="append", type=Path, default=[],
                        help="Codex sessions directory; repeatable; replaces the Codex default roots")
    parser.add_argument("--antigravity-root", action="append", type=Path, default=[],
                        help="Antigravity directory with conversation_summaries.db and brain/; repeatable; "
                             "replaces the Antigravity default roots")
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
    # A root option replaces only the default roots of its own host.
    home = Path.home()
    if not args.claude_root:
        # T3 Code runs Claude Code with a config folder for each profile in
        # ~/.claude-t3. Read only its projects folder; a profile without one
        # is left out instead of reported.
        args.claude_root = [home / ".claude" / "projects",
                            *sorted(path for path in (home / ".claude-t3").glob("*/projects") if path.is_dir())]
        if os.environ.get("CLAUDE_CONFIG_DIR"):
            args.claude_root.append(Path(os.environ["CLAUDE_CONFIG_DIR"]).expanduser() / "projects")
    if not args.codex_root:
        args.codex_root = [home / ".codex" / "sessions"]
        if os.environ.get("CODEX_HOME"):
            args.codex_root.append(Path(os.environ["CODEX_HOME"]).expanduser() / "sessions")
    if not args.antigravity_root:
        # Antigravity has a CLI folder and an app folder; a user often has one
        # of them. T3 Code runs Antigravity with a private profile for each
        # provider instance and keeps its sessions in antigravity-acp there.
        # A missing default folder is left out instead of reported.
        t3_antigravity_roots = sorted((home / ".t3" / "userdata" / "providers" / "antigravity").glob("*/antigravity-acp"))
        args.antigravity_root = [path for path in (home / ".gemini" / "antigravity-cli",
                                                   home / ".gemini" / "antigravity", *t3_antigravity_roots)
                                 if path.is_dir()]
    args.claude_root = list(dict.fromkeys(path.expanduser().resolve() for path in args.claude_root))
    args.codex_root = list(dict.fromkeys(path.expanduser().resolve() for path in args.codex_root))
    args.antigravity_root = list(dict.fromkeys(path.expanduser().resolve() for path in args.antigravity_root))
    try:
        worktrees = subprocess.check_output(
            ["git", "-C", str(args.repo), "worktree", "list", "--porcelain", "-z"],
            text=True, stderr=subprocess.PIPE)
    except (OSError, subprocess.CalledProcessError):
        parser.error("--repo must name an accessible Git checkout")
    git_roots = list(dict.fromkeys(Path(field[9:]).resolve()
                                  for field in worktrees.split("\0") if field.startswith("worktree ")))
    if not git_roots or "bare" in worktrees.split("\0"):
        parser.error("--repo must name a non-bare Git checkout")
    # Git lists the main worktree first. Its parent folder often holds
    # unrelated projects, so only linked worktrees name the folders where a
    # removed worktree is looked for.
    repo = git_roots[0]
    linked_parents = frozenset(root.parent for root in git_roots[1:])
    added_worktrees = list(dict.fromkeys(path.expanduser().resolve() for path in args.worktree))
    repository_roots = list(dict.fromkeys(git_roots + added_worktrees))
    output = args.output.expanduser().resolve()
    if args.output.exists() or args.output.is_symlink():
        parser.error("--output must be a new path")
    if any(output.is_relative_to(root) for root in args.claude_root + args.codex_root + args.antigravity_root):
        parser.error("--output must be outside all transcript roots")
    output.mkdir(mode=0o700)
    (output / "raw").mkdir()
    (output / "digests").mkdir()
    (output / "timelines").mkdir()
    sources = []
    unchanged = 0
    totals = {"eligible_events": 0, "shown_events": 0, "omitted_events": 0,
              "clipped_characters": 0, "records": 0, "foreign_records": 0,
              "outside_window_records": 0, "unattributed_records": 0,
              "ignored_records": 0, "unsupported_items": 0}
    roots = []
    candidates = 0
    diagnostics = []
    seen_paths = set()
    for host, paths in (("claude", args.claude_root), ("codex", args.codex_root),
                        ("antigravity", args.antigravity_root)):
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
            if host == "antigravity":
                files, database_diagnostics = antigravity_sources(root, repository_roots)
                if database_diagnostics:
                    root_entry["status"] = "partial"
                    diagnostics.extend(database_diagnostics)
            else:
                for directory, folders, names in os.walk(root, onerror=walk_error):
                    folders.sort()
                    files.extend((Path(directory) / name, None) for name in sorted(names) if name.endswith(".jsonl"))
            for path, workspace in files:
                path = path.resolve()
                if path in seen_paths:
                    continue
                seen_paths.add(path)
                candidates += 1
                root_entry["candidates"] += 1
                alias = f"source-{candidates:04d}"
                copy = f"raw/{alias}.jsonl"
                digest = f"digests/{alias}.json"
                timeline = f"timelines/{alias}.tsv"
                # A record is written after its time, so a source modified
                # before --after holds no record after it. A source that
                # cannot be read here goes on to snapshot(), which reports it.
                try:
                    modified = Fraction(path.stat().st_mtime_ns, 10 ** 9)
                except OSError:
                    modified = None
                if after is not None and modified is not None and modified + MTIME_STEP_SECONDS <= after:
                    unchanged += 1
                    continue
                boundary, copied, copy_diagnostics = snapshot(path, output / copy)
                if not (output / copy).exists():
                    diagnostics.extend({"path": str(path), "host": host, **item} for item in copy_diagnostics)
                    continue
                with (output / copy).open("rb") as stream:
                    extracted = extract(stream, host, repository_roots, after, through,
                                        args.max_events, args.max_text, workspace, linked_parents)
                extracted["diagnostics"] = copy_diagnostics + extracted["diagnostics"]
                for key in totals:
                    totals[key] += extracted["counts"][key]
                if not extracted["selected"]:
                    diagnostics.extend({"path": str(path.resolve()), "host": host, **item}
                                       for item in extracted["diagnostics"])
                    (output / copy).unlink()
                    continue
                events, counts = extracted["events"], extracted["counts"]
                with (output / timeline).open("x", encoding="utf-8", errors="backslashreplace") as stream:
                    stream.write(TIMELINE_HEADER)
                    stream.writelines(extracted["timeline"])
                write_json(output / digest, {"source": alias, "host": host,
                                            "copy": copy, "timeline": timeline, "events": events, "counts": counts,
                                            "diagnostics": extracted["diagnostics"],
                                            "ignored_types": extracted["ignored_types"]})
                sources.append({"host": host, "path": str(path.resolve()), "selected": True,
                                "copy": copy, "digest": digest, "timeline": timeline, "boundary_bytes": boundary,
                                "copied_bytes": copied, "counts": counts,
                                "diagnostics": extracted["diagnostics"]})
    diagnostic_count = sum(item.get("count", 1) for item in diagnostics)
    diagnostic_count += sum(item.get("count", 1) for source in sources for item in source["diagnostics"])
    status = "partial" if diagnostic_count else "ok"
    manifest = {"schema_version": 1, "status": status,
                "repository": {"requested": str(args.repo.resolve()), "main": str(repo),
                               "roots": [str(root) for root in repository_roots],
                               "added_worktrees": [str(path) for path in added_worktrees]},
                "window": {"after": args.after, "through": through_text},
                "limits": {"max_events": args.max_events, "max_text": args.max_text},
                "roots": roots, "sources": sources, "diagnostics": diagnostics,
                "limitations": ["A worktree that Git no longer lists is read only when --worktree names it. "
                                "Without that option, a Claude Code or Codex record in the window whose cwd is "
                                "in a missing folder in the same parent folder as a linked worktree that Git "
                                "lists gets a removed_worktree diagnostic; other removed worktrees and "
                                "Antigravity conversations get none.",
                                "Copies are measured byte prefixes, not atomic filesystem snapshots.",
                                f"A source modified {MTIME_STEP_SECONDS} s or more before --after is not read; "
                                f"a record more than {MTIME_STEP_SECONDS} s later than its file's modification "
                                "time, such as after a clock change, is missed.",
                                "Raw copies can include records outside the repository and time window.",
                                "Antigravity records carry no cwd; their events show the matched workspace folder as cwd.",
                                "Digests are evidence indexes, not complete semantic reviews."],
                "counts": {"candidate_sources": candidates, "selected_sources": len(sources),
                           "skipped_sources": candidates - len(sources), "unchanged_sources": unchanged,
                           **totals, "diagnostics": diagnostic_count}}
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
