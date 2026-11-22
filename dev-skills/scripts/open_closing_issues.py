#!/usr/bin/env python3
"""List the closing issues of merged PRs, and fail when one is still open.

repo-cleanup runs this script after it closes completed issues, with the
merged PRs of the cleanup. For each PR, gh reads its closing issue references:
the issues that a closing keyword in the PR, such as "Closes #N", names. Each
output line has three tab-separated fields:

- OPEN or CLOSED, the issue URL, and "merged PR <PR URL>"; or
- NONE, the PR URL, and "no closing issue references".

The exit status is 0 when every closing issue is closed, 1 when one is still
open, and 2 when the check cannot run: gh fails, or a PR is not merged. The
script runs only read commands.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from typing import NoReturn


def fail(message: str) -> NoReturn:
    print(f"open_closing_issues: {message}", file=sys.stderr)
    sys.exit(2)


def gh(*args: str) -> dict:
    try:
        result = subprocess.run(["gh", *args], capture_output=True, text=True)
    except FileNotFoundError:
        fail("gh is not installed")
    if result.returncode != 0:
        fail(" ".join(result.stderr.split()) or f"gh {' '.join(args[:3])} failed")
    try:
        data = json.loads(result.stdout)
    except ValueError:
        data = None
    if not isinstance(data, dict):
        fail(f"gh {' '.join(args[:3])} printed no JSON object")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("prs", nargs="+", metavar="pr", help="a PR number, URL, or branch")
    args = parser.parse_args()

    found_open = False
    for arg in args.prs:
        pr = gh("pr", "view", arg, "--json", "number,state,url,closingIssuesReferences")
        url = pr.get("url", arg)
        if pr.get("state") != "MERGED":
            fail(f"PR {url} is not merged (state {pr.get('state')})")
        references = pr.get("closingIssuesReferences") or []
        if not references:
            print(f"NONE\t{url}\tno closing issue references", flush=True)
        for reference in references:
            issue = gh("issue", "view", str(reference.get("url") or reference.get("number")),
                       "--json", "state,url")
            state = issue.get("state")
            found_open = found_open or state != "CLOSED"
            print(f"{state}\t{issue.get('url')}\tmerged PR {url}", flush=True)
    sys.exit(1 if found_open else 0)


if __name__ == "__main__":
    main()
