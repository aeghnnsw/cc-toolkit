"""Pure, deterministic control-protocol logic for the task-loop plugin.

No I/O. GitHub access lives in gh_store.py. Stdlib only.

Two state primitives, deliberately decoupled:

* **Dedupe (authoritative).** `seen_source_uuids` is rebuilt from the
  *source-tagged* control events (MERGE_GRANTED / MERGE_DENIED /
  PLAN_FINDING_RECORDED) in any order. Every ingested worker inbox event MUST
  produce exactly one source-tagged control event: at-least-one is checked at
  emit time by `unacknowledged_uuids`; at-most-one is enforced by `replay`
  raising on a duplicate `source_uuid`.

* **Scan floor (optimization).** `scan_floor_ts_by_issue` is advanced ONLY by
  explicit `INBOX_SCAN_CHECKPOINT{issue_number, through_ts}` events — never by an
  acked comment timestamp. This avoids the prefix hole: the pre-merge barrier may
  ack a later-timestamp finding before an earlier-timestamp merge request, so
  `max(acked_ts)` is not a valid floor. The orchestrator (Phase 2) emits a
  checkpoint through `T` for an issue ONLY after every comment with
  `createdAt <= T` on that issue has exactly one source-tagged control event; a
  crash before the checkpoint leaves the old floor, so an inclusive rescan
  (`comments_at_or_after_watermark`, `>=`) plus UUID dedupe recovers safely.

Timestamps (`source_comment_ts`, `through_ts`) are GitHub canonical UTC,
`YYYY-MM-DDTHH:MM:SSZ` with NO fractional seconds, so lexical `>=` is
chronological (a fractional form like `...00.100Z` sorts before `...00Z`).
"""
import datetime
import json
import re

EVENT_FENCE = "task-loop-event"
_FENCE_RE = re.compile(r"```" + EVENT_FENCE + r"\s*\n(.*?)\n```", re.DOTALL)
_TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"  # GitHub canonical UTC, second granularity


def format_event(event: dict) -> str:
    """Serialize one event as a fenced ```task-loop-event JSON block."""
    return "```{fence}\n{body}\n```".format(
        fence=EVENT_FENCE, body=json.dumps(event, sort_keys=True)
    )


def parse_events(comment_body: str) -> list:
    """Extract all task-loop-event JSON objects from a comment body, in order."""
    return [json.loads(m.group(1)) for m in _FENCE_RE.finditer(comment_body)]


def filter_new_inbox(inbox_events: list, seen_uuids) -> list:
    """Return inbox events whose uuid has not been seen, in order, deduping
    repeats within the batch. `seen_uuids` is any container supporting `in`."""
    seen = set(seen_uuids)
    fresh = []
    for event in inbox_events:
        uuid = event["uuid"]
        if uuid in seen:
            continue
        seen.add(uuid)
        fresh.append(event)
    return fresh


def assign_seq(events: list, last_seq: int):
    """Stamp each event with a monotonically increasing integer `seq` starting
    at last_seq+1. Returns (stamped_events, new_last_seq). Does not mutate input."""
    stamped = []
    seq = last_seq
    for event in events:
        seq += 1
        stamped.append({**event, "seq": seq})
    return stamped, seq


def unacknowledged_uuids(fresh_inbox: list, emitted_control_events: list) -> list:
    """uuids of fresh inbox events that did NOT receive a source-tagged control
    event (the 'at least one' half of the exactly-one invariant). The CALLER
    decides whether a non-empty result is a problem: the orchestrator acks every
    PLAN_FINDING in the drain (a leftover there *would* break cold-resume dedupe),
    but a MERGE_REQUEST is legitimately *pending* until the merge gate decides it,
    so its uuid stays unacked (and pins the issue scan floor) by design."""
    acked = {
        e.get("source_uuid")
        for e in emitted_control_events
        if e.get("source_uuid")
    }
    return [e["uuid"] for e in fresh_inbox if e["uuid"] not in acked]


def comments_at_or_after_watermark(comments: list, watermark_ts: str) -> list:
    """Inclusive scan floor: keep comments whose created_at is >= watermark_ts
    (or all of them when the floor is empty). `comments` are (id, created_at,
    body) triples from gh_store.read_comments. The `>=` (not `>`) is required so
    that same-second comments at the boundary are not skipped; the caller then
    UUID-dedupes the result against `seen_source_uuids`."""
    if not watermark_ts:
        return list(comments)
    return [c for c in comments if c[1] >= watermark_ts]


_STATUS_BY_TYPE = {
    "TASK_CREATED": "ready",
    "TASK_DISPATCHED": "active",
    "MERGE_GRANTED": "merged",
    "MERGE_DENIED": "stale",
    "TASK_STALE": "stale",
    "TASK_REVISION_COMPATIBLE": "active",
}

_SOURCE_FIELDS = ("source_issue", "source_comment_id", "source_comment_ts",
                  "source_uuid")
# Required fields per control-event type (beyond kind/seq/type/ts).
_REQUIRED_FIELDS = {
    "PLAN_REVISION_BUMP": ("plan_revision", "proposal_sha"),
    "TASK_CREATED": ("task_id", "plan_revision", "issue_number"),
    "TASK_DISPATCHED": ("task_id", "plan_revision"),
    "TASK_STALE": ("task_id", "plan_revision"),
    "TASK_REVISION_COMPATIBLE": ("task_id", "plan_revision"),
    "INBOX_SCAN_CHECKPOINT": ("issue_number", "through_ts"),
    "MERGE_GRANTED": ("task_id", "plan_revision", "pr_head_sha") + _SOURCE_FIELDS,
    "MERGE_DENIED": ("task_id", "plan_revision", "pr_head_sha") + _SOURCE_FIELDS,
    "PLAN_FINDING_RECORDED": ("task_id",) + _SOURCE_FIELDS,
}
_INT_FIELDS = ("plan_revision", "issue_number", "source_issue")
_TS_FIELDS = ("source_comment_ts", "through_ts")


def _is_canonical_utc(value) -> bool:
    """True iff value is canonical UTC `YYYY-MM-DDTHH:MM:SSZ` (no fractional
    seconds, no offset), validated for range as well as shape."""
    if not isinstance(value, str):
        return False
    try:
        datetime.datetime.strptime(value, _TS_FORMAT)
        return True
    except ValueError:
        return False


def _validate(event):
    """Raise ValueError if a control event is malformed for its type."""
    if event.get("kind") != "control":
        raise ValueError("not a control event: kind=%r" % (event.get("kind"),))
    etype = event.get("type")
    if etype not in _REQUIRED_FIELDS:
        raise ValueError("unknown control event type: %r" % (etype,))
    seq = event.get("seq")
    if isinstance(seq, bool) or not isinstance(seq, int) or seq < 1:
        raise ValueError("control event has invalid seq: %r" % (seq,))
    if "ts" not in event:
        raise ValueError("control event missing ts at seq=%r" % (seq,))
    required = _REQUIRED_FIELDS[etype]
    for field in required:
        if event.get(field) in (None, ""):
            raise ValueError("%s missing required field %r" % (etype, field))
    for intf in _INT_FIELDS:
        if intf in required:
            val = event.get(intf)
            if isinstance(val, bool) or not isinstance(val, int):
                raise ValueError("%s.%s must be an int, got %r" % (etype, intf, val))
    for tsf in _TS_FIELDS:
        if tsf in required and not _is_canonical_utc(event.get(tsf)):
            raise ValueError(
                "%s.%s must be canonical UTC YYYY-MM-DDTHH:MM:SSZ, got %r"
                % (etype, tsf, event.get(tsf))
            )


def replay(control_events: list) -> dict:
    """Fold seq-ordered control events into recoverable fast state. Pure; raises
    ValueError on a schema violation, a seq gap/duplicate, a duplicate
    `source_uuid`, or a checkpoint for an unknown / regressing issue. Rebuilds the
    dedupe set and per-issue scan floor FROM THE LOG, so a cold resume is exact."""
    for event in control_events:
        _validate(event)
    events = sorted(control_events, key=lambda e: e["seq"])
    state = {
        "current_plan_revision": 0,
        "current_proposal_sha": None,
        "last_seq": 0,
        "tasks": {},
        "seen_source_uuids": set(),
        "source_uuid_to_seq": {},
        "scan_floor_ts_by_issue": {},
    }
    expected = 0
    for event in events:
        expected += 1
        if event["seq"] != expected:
            raise ValueError(
                "non-contiguous control log: expected seq %d, got %d"
                % (expected, event["seq"])
            )
        etype = event["type"]
        if etype == "PLAN_REVISION_BUMP":
            state["current_plan_revision"] = event["plan_revision"]
            state["current_proposal_sha"] = event["proposal_sha"]
        elif etype == "INBOX_SCAN_CHECKPOINT":
            issue = event["issue_number"]
            if issue not in state["scan_floor_ts_by_issue"]:
                raise ValueError(
                    "checkpoint for unestablished issue %r (no TASK_CREATED)" % (issue,)
                )
            through = event["through_ts"]
            if through < state["scan_floor_ts_by_issue"][issue]:
                raise ValueError(
                    "checkpoint through_ts regresses for issue %r" % (issue,)
                )
            state["scan_floor_ts_by_issue"][issue] = through
        else:
            task = state["tasks"].setdefault(
                event["task_id"],
                {"status": None, "plan_revision": None, "issue_number": None,
                 "pr_head_sha": None},
            )
            task["status"] = _STATUS_BY_TYPE.get(etype, task["status"])
            if event.get("plan_revision") is not None:
                task["plan_revision"] = event["plan_revision"]
            if etype == "TASK_CREATED":
                task["issue_number"] = event["issue_number"]
                # Discover the task issue so a cold resume scans it; "" = scan all
                # until a checkpoint advances the floor.
                state["scan_floor_ts_by_issue"].setdefault(event["issue_number"], "")
            if event.get("pr_head_sha"):
                task["pr_head_sha"] = event["pr_head_sha"]
        # Source-tagged events rebuild the dedupe set (NOT the scan floor).
        if event.get("source_uuid"):
            uuid = event["source_uuid"]
            if uuid in state["seen_source_uuids"]:
                raise ValueError("duplicate source_uuid in control log: %r" % (uuid,))
            state["seen_source_uuids"].add(uuid)
            state["source_uuid_to_seq"][uuid] = event["seq"]
        state["last_seq"] = event["seq"]
    return state
