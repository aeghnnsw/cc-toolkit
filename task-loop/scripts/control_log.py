"""Pure, deterministic control-protocol logic for the task-loop plugin.

No I/O. GitHub access lives in gh_store.py. Stdlib only.
"""
import json
import re

EVENT_FENCE = "task-loop-event"
_FENCE_RE = re.compile(
    r"```" + EVENT_FENCE + r"\s*\n(.*?)\n```", re.DOTALL
)


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


_STATUS_BY_TYPE = {
    "TASK_CREATED": "ready",
    "TASK_DISPATCHED": "active",
    "MERGE_GRANTED": "merged",
    "MERGE_DENIED": "stale",
    "TASK_STALE": "stale",
    "TASK_REVISION_COMPATIBLE": "active",
}

# Required fields per control-event type (beyond kind/seq/type/ts).
_REQUIRED_FIELDS = {
    "PLAN_REVISION_BUMP": ("plan_revision", "proposal_sha"),
    "TASK_CREATED": ("task_id", "plan_revision", "issue_number"),
    "TASK_DISPATCHED": ("task_id", "plan_revision"),
    "TASK_STALE": ("task_id", "plan_revision"),
    "TASK_REVISION_COMPATIBLE": ("task_id", "plan_revision"),
    "MERGE_GRANTED": ("task_id", "plan_revision", "pr_head_sha",
                      "source_issue", "source_comment_id", "source_uuid"),
    "MERGE_DENIED": ("task_id", "plan_revision", "pr_head_sha",
                     "source_issue", "source_comment_id", "source_uuid"),
    "PLAN_FINDING_RECORDED": ("task_id", "source_issue", "source_comment_id",
                              "source_uuid"),
}


def _validate(event):
    """Raise ValueError if a control event is malformed for its type."""
    if event.get("kind") != "control":
        raise ValueError("not a control event: kind=%r" % (event.get("kind"),))
    etype = event.get("type")
    if etype not in _REQUIRED_FIELDS:
        raise ValueError("unknown control event type: %r" % (etype,))
    if "ts" not in event:
        raise ValueError("control event missing ts at seq=%r" % (event.get("seq"),))
    for field in _REQUIRED_FIELDS[etype]:
        if event.get(field) in (None, ""):
            raise ValueError("%s missing required field %r" % (etype, field))


def replay(control_events: list) -> dict:
    """Fold seq-ordered control events into recoverable fast state. Pure; raises
    ValueError on a seq gap/duplicate or a schema violation. Reconstructs the dedupe
    set and per-issue scan watermark FROM THE LOG, so a cold resume is exact."""
    events = sorted(control_events, key=lambda e: e["seq"])
    state = {
        "current_plan_revision": 0,
        "current_proposal_sha": None,
        "last_seq": 0,
        "tasks": {},
        "seen_source_uuids": set(),
        "source_uuid_to_seq": {},
        "last_ingested_comment_id_by_issue": {},
    }
    expected = 0
    for event in events:
        expected += 1
        if event["seq"] != expected:
            raise ValueError(
                "non-contiguous control log: expected seq %d, got %d"
                % (expected, event["seq"])
            )
        _validate(event)
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
                # inbox event has been ingested from it.
                state["last_ingested_comment_id_by_issue"].setdefault(
                    event["issue_number"], 0
                )
            if event.get("pr_head_sha"):
                task["pr_head_sha"] = event["pr_head_sha"]
        # Inbox-derived events carry source provenance -> rebuild dedupe + watermark.
        if event.get("source_uuid"):
            state["seen_source_uuids"].add(event["source_uuid"])
            state["source_uuid_to_seq"][event["source_uuid"]] = event["seq"]
            issue = event["source_issue"]
            prev = state["last_ingested_comment_id_by_issue"].get(issue, 0)
            state["last_ingested_comment_id_by_issue"][issue] = max(
                prev, event["source_comment_id"]
            )
        state["last_seq"] = event["seq"]
    return state
