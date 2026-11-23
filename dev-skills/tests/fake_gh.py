"""A fake gh for the repo-cleanup, retrospective cutoff, and phase gate tests.

The tests put a `gh` wrapper that runs this file first on PATH. It answers only
the read commands that the scripts use, from the JSON file that FAKE_GH_DATA
names, and appends each argument list to the file that FAKE_GH_LOG names. Any
other command fails, so a script that tries to change GitHub state fails too.

The data file has these optional keys:

- "fail": an error message; every command prints it and exits 1.
- "prs": merged PRs by head branch, for `gh pr list --head B --state merged`.
- "commit_prs": the PRs of each commit, by its full SHA, for
  `gh api repos/{owner}/{repo}/commits/<sha>/pulls...`. A commit that is not
  a key gets the HTTP 422 error of GitHub for a commit that it lacks.
- "pr_view": PRs by the argument of `gh pr view`.
- "issues": issues by the argument of `gh issue view`, a number or a URL.
- "comments": pages of repository comments, for
  `gh api --paginate repos/{owner}/{repo}/issues/comments...`. Each page is a
  list; the pages print one after another, with no separator.
- "merged": merged PR numbers, for `gh pr list --state merged --json number`.
- "graphql": the repository for `gh api graphql`, as {"nameWithOwner": "o/r",
  "issues": {"12": issue}}. Each `issue(number: N)` field of the query, with
  an optional alias, gets the issue of N, whatever fields the query asks for.
  N can be a literal or `$number`, from `-F number=N`. A missing issue is null
  with a NOT_FOUND error, and gh exits 1, as the real gh does.
"""

from __future__ import annotations

import json
import os
import re
import sys


def option(args: list[str], name: str) -> str | None:
    return args[args.index(name) + 1] if name in args[:-1] else None


def graphql(args: list[str], repository: dict) -> int:
    """Answer each issue(number: N) field of a GraphQL query from the issue data."""
    fields = dict(args[i + 1].split("=", 1) for i, arg in enumerate(args[:-1])
                  if arg in ("-F", "-f"))
    answer, errors = {"nameWithOwner": repository["nameWithOwner"]}, []
    for alias, number in re.findall(r"(?:(\w+):\s*)?issue\(number:\s*(\$number|\d+)\)",
                                    fields["query"]):
        key, number = alias or "issue", fields["number"] if number == "$number" else number
        answer[key] = repository["issues"].get(number)
        if answer[key] is None:
            errors.append({"type": "NOT_FOUND", "path": ["repository", key],
                           "message": f"Could not resolve to an Issue with the number of {number}."})
    print(json.dumps({"data": {"repository": answer}, **({"errors": errors} if errors else {})}))
    if errors:
        print("gh: " + errors[0]["message"], file=sys.stderr)
    return 1 if errors else 0


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
    commit = re.fullmatch(r"repos/\{owner\}/\{repo\}/commits/([0-9a-f]{40})/pulls(\?.*)?",
                          args[1]) if args[:1] == ["api"] and len(args) == 2 else None
    if commit and commit.group(1) in data.get("commit_prs", {}):
        print(json.dumps(data["commit_prs"][commit.group(1)]))
        return 0
    if commit:
        print(f"gh: No commit found for SHA: {commit.group(1)} (HTTP 422)", file=sys.stderr)
        return 1
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
    if args[:2] == ["api", "graphql"] and "graphql" in data:
        return graphql(args, data["graphql"])
    print(f"fake gh: unsupported command: {' '.join(args)}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
