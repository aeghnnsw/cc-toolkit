"""Pure, deterministic control-protocol logic for the task-loop plugin.

No I/O. GitHub access lives in gh_store.py. Stdlib only.

Idempotency invariant (orchestrator discipline; mechanically checkable via
`unacknowledged_uuids`): every ingested worker inbox event MUST produce exactly
one *source-tagged* control event (one carrying `source_uuid`). Replying to a
MERGE_REQUEST with a bare, untagged TASK_STALE / TASK_REVISION_COMPATIBLE breaks
cold-resume dedupe, because that uuid would never be recorded in the log and the
same inbox comment would be re-ingested after a crash. Use MERGE_GRANTED /
MERGE_DENIED (both source-tagged) to answer a MERGE_REQUEST.

Watermark: `last_ingested_comment_ts_by_issue` keys on the GitHub comment
`createdAt` (ISO-8601 string), NOT the comment `id`. The `id` returned by
`gh issue view --json comments` is an opaque GraphQL node-ID string that is
neither an integer nor chronologically ordered, so it cannot be a `max()`
watermark. The UUID dedupe set (`seen_source_uuids`) is the authoritative
idempotency mechanism; the timestamp watermark is only a scan optimization.
"""
import json
import re

EVENT_FENCE = "task-loop-event"
_FENCE_RE = re.compile(r"```" + EVENT_FENCE + r"\s*\n(.*?)\n```", re.DOTALL)


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
    event. A non-empty result means the dedupe invariant would break on cold
    resume — the orchestrator must emit exactly one source-tagged control event
    per ingested inbox uuid before it relies on the log for recovery."""
    acked = {
        e.get("source_uuid")
        for e in emitted_control_events
        if e.get("source_uuid")
    }
    return [e["uuid"] for e in fresh_inbox if e["uuid"] not in acked]


_STATUS_BY_TYPE = {
    "TASK_CREATED": "ready",
    "TASK_DISPATCHED": "active",
    "MERGE_GRANTED": "merged",
    "MERGE_DENIED": "stale",
    "TASK_STALE": "stale",
    "TASK_REVISION_COMPATIBLE": "active",
}

# Required fields per control-event type (beyond kind/seq/type/ts).
_SOURCE_FIELDS = ("source_issue", "source_comment_id", "source_comment_ts",
                  "source_uuid")
_REQUIRED_FIELDS = {
    "PLAN_REVISION_BUMP": ("plan_revision", "proposal_sha"),
    "TASK_CREATED": ("task_id", "plan_revision", "issue_number"),
    "TASK_DISPATCHED": ("task_id", "plan_revision"),
    "TASK_STALE": ("task_id", "plan_revision"),
    "TASK_REVISION_COMPATIBLE": ("task_id", "plan_revision"),
    "MERGE_GRANTED": ("task_id", "plan_revision", "pr_head_sha") + _SOURCE_FIELDS,
    "MERGE_DENIED": ("task_id", "plan_revision", "pr_head_sha") + _SOURCE_FIELDS,
    "PLAN_FINDING_RECORDED": ("task_id",) + _SOURCE_FIELDS,
}
_INT_FIELDS = ("plan_revision", "issue_number")


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


def replay(control_events: list) -> dict:
    """Fold seq-ordered control events into recoverable fast state. Pure; raises
    ValueError on a schema violation or a seq gap/duplicate. Reconstructs the
    dedupe set and per-issue scan watermark FROM THE LOG, so a cold resume is
    exact."""
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
        "last_ingested_comment_ts_by_issue": {},
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
                # Discover the task issue so a cold resume scans it even before any
                # inbox event has been ingested from it ("" sorts before any ts).
                state["last_ingested_comment_ts_by_issue"].setdefault(
                    event["issue_number"], ""
                )
            if event.get("pr_head_sha"):
                task["pr_head_sha"] = event["pr_head_sha"]
        # Inbox-derived events carry source provenance -> rebuild dedupe + watermark.
        if event.get("source_uuid"):
            state["seen_source_uuids"].add(event["source_uuid"])
            state["source_uuid_to_seq"][event["source_uuid"]] = event["seq"]
            issue = event["source_issue"]
            prev = state["last_ingested_comment_ts_by_issue"].get(issue, "")
            state["last_ingested_comment_ts_by_issue"][issue] = max(
                prev, event["source_comment_ts"]
            )
        state["last_seq"] = event["seq"]
    return state
