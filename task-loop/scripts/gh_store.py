"""Thin gh-CLI adapter for the task-loop control protocol. The only module that
touches GitHub. `runner` is injectable so the logic is testable without gh."""
import json
import subprocess


def _default_runner(args: list, input_text=None) -> str:
    return subprocess.run(
        ["gh", *args], check=True, capture_output=True, text=True,
        input=input_text,
    ).stdout


def read_comments(issue_number, runner=_default_runner) -> list:
    """Return [(comment_id, created_at, body), ...] for an issue, sorted
    oldest-first by `createdAt`. `comment_id` is gh's opaque node-ID string and
    is carried for audit/reference only; chronological ordering and the scan
    watermark use `created_at` (ISO-8601), which sorts correctly as a string."""
    out = runner(["issue", "view", str(issue_number),
                  "--json", "comments"])
    data = json.loads(out)
    comments = sorted(data.get("comments", []),
                      key=lambda c: c.get("createdAt", ""))
    return [(c["id"], c.get("createdAt", ""), c["body"]) for c in comments]


def post_comment(issue_number, body: str, runner=_default_runner) -> None:
    """Append a comment to an issue, passing the body via stdin (--body-file -)
    so control-event JSON never appears in the command text."""
    runner(["issue", "comment", str(issue_number), "--body-file", "-"],
           input_text=body)
