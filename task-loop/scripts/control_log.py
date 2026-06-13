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
