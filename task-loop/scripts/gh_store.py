"""Thin gh-CLI adapter for the task-loop control protocol. The only module that
touches GitHub. `runner` is injectable so the logic is testable without gh."""
import json
import subprocess


def _default_runner(args: list) -> str:
    return subprocess.run(
        ["gh", *args], check=True, capture_output=True, text=True
    ).stdout


def read_comments(issue_number, runner=_default_runner) -> list:
    """Return [(comment_id, body), ...] for an issue, oldest first."""
    out = runner(["issue", "view", str(issue_number), "--json", "comments"])
    data = json.loads(out)
    return [(c["id"], c["body"]) for c in data.get("comments", [])]
