"""A fake gh for the repo-cleanup and retrospective cutoff script tests.

The tests put a `gh` wrapper that runs this file first on PATH. It answers only
the read commands that the scripts use, from the JSON file that FAKE_GH_DATA
names, and appends each argument list to the file that FAKE_GH_LOG names. Any
other command fails, so a script that tries to change GitHub state fails too.

The data file has these optional keys:

- "fail": an error message; every command prints it and exits 1.
- "prs": merged PRs by head branch, for `gh pr list --head B --state merged`.
- "pr_view": PRs by the argument of `gh pr view`.
- "issues": issues by the argument of `gh issue view`, a number or a URL.
- "comments": pages of repository comments, for
  `gh api --paginate repos/{owner}/{repo}/issues/comments...`. Each page is a
  list; the pages print one after another, with no separator.
- "merged": merged PR numbers, for `gh pr list --state merged --json number`.
"""

from __future__ import annotations

import json
import os
import sys


def option(args: list[str], name: str) -> str | None:
    return args[args.index(name) + 1] if name in args[:-1] else None


def main() -> int:
    args = sys.argv[1:]
    with open(os.environ["FAKE_GH_LOG"], "a", encoding="utf-8") as log:
        log.write(json.dumps(args) + "\n")
    with open(os.environ["FAKE_GH_DATA"], encoding="utf-8") as handle:
        data = json.load(handle)
    if "fail" in data:
        print(data["fail"], file=sys.stderr)
        return 1
    merged_list = option(args, "--state") == "merged" and option(args, "--head")
    if args[:2] == ["pr", "list"] and merged_list:
        print(json.dumps(data.get("prs", {}).get(option(args, "--head"), [])))
        return 0
    merged_numbers = option(args, "--state") == "merged" and option(args, "--json") == "number"
    if args[:2] == ["pr", "list"] and merged_numbers:
        print(json.dumps([{"number": number} for number in data.get("merged", [])]))
        return 0
    comments = [arg for arg in args if arg.startswith("repos/{owner}/{repo}/issues/comments")]
    if args[:1] == ["api"] and "--paginate" in args and comments:
        sys.stdout.write("".join(json.dumps(page) for page in data.get("comments", [[]])))
        return 0
    if args[:2] == ["pr", "view"] and len(args) > 2:
        if args[2] in data.get("pr_view", {}):
            print(json.dumps(data["pr_view"][args[2]]))
            return 0
        print(f"no pull requests found for {args[2]}", file=sys.stderr)
        return 1
    if args[:2] == ["issue", "view"] and len(args) > 2:
        if args[2] in data.get("issues", {}):
            print(json.dumps(data["issues"][args[2]]))
            return 0
        print(f"GraphQL: Could not resolve to an issue or pull request ({args[2]})",
              file=sys.stderr)
        return 1
    print(f"fake gh: unsupported command: {' '.join(args)}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
