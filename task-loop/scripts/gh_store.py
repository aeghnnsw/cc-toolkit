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
    """Return [(comment_id, body), ...] for an issue, oldest first."""
    out = runner(["issue", "view", str(issue_number), "--json", "comments"])
    data = json.loads(out)
    return [(c["id"], c["body"]) for c in data.get("comments", [])]


def post_comment(issue_number, body: str, runner=_default_runner) -> None:
    """Append a comment to an issue, passing the body via stdin (--body-file -)
    so control-event JSON never appears in the command text."""
    runner(["issue", "comment", str(issue_number), "--body-file", "-"],
           input_text=body)
