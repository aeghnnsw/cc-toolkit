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
