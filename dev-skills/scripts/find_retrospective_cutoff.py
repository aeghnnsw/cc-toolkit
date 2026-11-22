#!/usr/bin/env python3
"""Print the greatest Reviewed through cutoff of the merged pull requests.

A Navigation retrospective record is a comment on a merged pull request that
contains "Navigation retrospective" and a "Reviewed through:" field, such as
"**Reviewed through:** 2026-11-21T05:16:55Z". The script reads every issue and
pull request comment of the current repository with gh, through the comments
API, and keeps the records on merged pull requests. It prints the greatest
cutoff and its pull request, for example:

    2026-11-21T05:16:55Z PR #444

The field can be bold or not. The cutoff is a UTC time with "Z" or "+00:00",
with or without fractional seconds, in backticks or not. The records use these
forms:

    2026-10-27T15:02:52.722Z
    `2026-11-09T00:22:55.226+00:00`
    2026-11-21T05:16:55Z

Only the time right after the label counts. A time that does not exist, such
as 2026-11-31T00:00:00Z, does not count. The script compares the cutoffs as
times with timestamp() from retro_sessions.py, which also reads the --after
and --through options of that script. It prints the cutoff as written, with
"+00:00" changed to "Z".

matt-automode runs it from the checkout root before it reads the session logs
of a retrospective, and again before it posts the record. A later cutoff in
the second run means that another retrospective read the logs up to that time.

Exit status: 0 when a record exists; 1 when no merged pull request has a
record, or when gh fails. The message tells which.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

# Python puts the folder of this script on sys.path, so the sibling module loads.
from retro_sessions import timestamp

HEADING = "Navigation retrospective"
FIELD = re.compile(r"Reviewed through:(?:\*\*)?[ \t]*`?"
                   r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?)(?:Z|\+00:00)")
COMMENTS = "repos/{owner}/{repo}/issues/comments?per_page=100"
# gh needs a limit; this one is greater than the number of pull requests.
LIMIT = "100000"


def gh(*args: str) -> list:
    """Return the JSON lists that gh prints, or exit 1 with its error."""
    name = " ".join(arg for arg in args[:2] if not arg.startswith("-"))
    try:
        result = subprocess.run(["gh", *args], capture_output=True, text=True)
    except FileNotFoundError:
        sys.exit("FAIL: gh is not installed")
    if result.returncode:
        sys.exit(f"FAIL: gh {name} failed:\n{result.stderr.strip()}")
    # gh can print one JSON list for each page, one after another.
    decoder, text, index, items = json.JSONDecoder(), result.stdout.strip(), 0, []
    try:
        while index < len(text):
            page, index = decoder.raw_decode(text, index)
            if not isinstance(page, list):
                raise ValueError(page)
            items += page
            index = len(text) - len(text[index:].lstrip())
    except ValueError:
        sys.exit(f"FAIL: gh {name} printed no JSON list")
    return items


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.parse_args()
    found = []
    for comment in gh("api", "--paginate", COMMENTS):
        body = comment.get("body") or ""
        if HEADING in body:
            number = int(comment["issue_url"].rsplit("/", 1)[1])
            for match in FIELD.finditer(body):
                cutoff = match.group(1) + "Z"
                try:
                    found.append((timestamp(cutoff), number, cutoff))
                except ValueError:
                    continue  # The time does not exist.
    if found:
        merged = {pull["number"] for pull in gh("pr", "list", "--state", "merged",
                                                 "--limit", LIMIT, "--json", "number")}
        found = [item for item in found if item[1] in merged]
    if not found:
        sys.exit(f"No {HEADING} record with a Reviewed through cutoff on a merged pull request.")
    _, number, cutoff = max(found)
    print(f"{cutoff} PR #{number}")


if __name__ == "__main__":
    main()
