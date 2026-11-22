#!/usr/bin/env python3
"""Check that a ticket can start matt-automode phase 4, before any coding.

Usage, from the checkout root:

    python3 dev-skills/scripts/phase_gate.py --ticket N

The script reads the current repository with `gh api graphql` and makes these
checks:

1. Ticket: issue N exists in the current repository.
2. Spec: the ticket's native GitHub parent issue, or else the issue that the
   "## Parent" section of the ticket body references, exists. When the ticket
   names no parent, it is its own spec, and the check passes.
3. Blockers: each native "blocked by" issue, and each issue that the
   "## Blocked by" section of the ticket body references, has at least one
   merged pull request that closes it. A line such as
   "None (can start immediately)" names no blocker.

A body section references an issue as "#123", or as
"https://github.com/OWNER/REPO/issues/123" of the current repository. A
reference to another repository, or a line that the script cannot read as an
issue reference, fails the check.

The script prints one line for each check, "PASS ..." or "FAIL ...", and then
a summary line.

Exit status: 0 when every check passes; 1 when a check fails or cannot be
decided, which includes any gh error; 2 for a usage error.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

# The default closing PR list has the open and merged PRs, and no closed PR
# that did not merge. A connection gives at most 100 nodes; the script fails
# when a connection has more nodes than it read.
BLOCKER = """
fragment Blocker on Issue {
  number
  repository { nameWithOwner }
  closedByPullRequestsReferences(first: 100) { totalCount nodes { number merged state } }
}"""
TICKET = """query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    nameWithOwner
    issue(number: $number) {
      number
      body
      parent { number repository { nameWithOwner } }
      blockedBy(first: 100) { totalCount nodes { ...Blocker } }
    }
  }
}""" + BLOCKER
HEADING = re.compile(r"^ {0,3}#{1,6}\s+(.*?)[\s#]*$")
BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(?:\[[ xX]\]\s+)?")
NONE = re.compile(r"^[*_`\s]*none\b", re.IGNORECASE)
REFERENCE = re.compile(r"https?://github\.com/([\w.-]+/[\w.-]+)/(issues|pull)/(\d+)\b"
                       r"|(?<![\w/#])(?:([\w.-]+/[\w.-]+))?#(\d+)\b")


class CannotDecide(Exception):
    """gh failed, so the script cannot decide a check."""


def graphql(query: str, *fields: str) -> dict:
    """Return the repository object of a gh GraphQL query.

    A missing issue comes back as None. Any other error raises CannotDecide.
    """
    command = ["gh", "api", "graphql", "-F", "owner={owner}", "-F", "name={repo}",
               *fields, "-f", f"query={query}"]
    try:
        result = subprocess.run(command, capture_output=True, text=True)
    except FileNotFoundError:
        raise CannotDecide("gh is not installed") from None
    try:
        answer = json.loads(result.stdout)
        repository, errors = answer["data"]["repository"], answer.get("errors") or []
    except (ValueError, KeyError, TypeError, AttributeError):
        repository, errors = None, [{}]
    # gh exits 1 when a named issue does not exist. It still prints the data,
    # with the issue as null and a NOT_FOUND error on the path of the issue.
    missing = all(error.get("type") == "NOT_FOUND" and len(error.get("path") or []) == 2
                  for error in errors)
    if not isinstance(repository, dict) or not missing or (result.returncode and not errors):
        detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
        raise CannotDecide("gh api graphql failed: " + " ".join(detail.split()))
    return repository


def section(body: str, title: str) -> list[str]:
    """Return the lines under the first body heading named title."""
    lines, inside = [], False
    for line in body.splitlines():
        heading = HEADING.match(line)
        if heading and inside:
            break
        if heading:
            inside = heading.group(1).lower() == title.lower()
        elif inside:
            lines.append(line)
    return lines


def references(lines: list[str], repo: str) -> tuple[list[int], list[str]]:
    """Return the issue numbers that the lines reference, and the problems."""
    numbers, problems = [], []
    for line in lines:
        text = BULLET.sub("", line).strip()
        if not text or text.startswith("<!--"):
            continue
        found = list(REFERENCE.finditer(text))
        if not found and not NONE.match(text):
            problems.append(f"cannot read an issue reference in {text!r}")
        for match in found:
            url_repo, kind, url_number, short_repo, short_number = match.groups()
            other = url_repo or short_repo
            if other and other.lower() != repo.lower():
                problems.append(f"{match.group(0)} is in another repository")
            elif kind == "pull":
                problems.append(f"{match.group(0)} is a pull request, not an issue")
            else:
                numbers.append(int(url_number or short_number))
    return list(dict.fromkeys(numbers)), problems


def issues_query(numbers: list[int]) -> str:
    """Return a query that reads each issue under the alias i<number>."""
    fields = "\n".join(f"    i{n}: issue(number: {n}) {{ ...Blocker }}" for n in numbers)
    return ("query($owner: String!, $name: String!) {\n"
            f"  repository(owner: $owner, name: $name) {{\n{fields}\n  }}\n}}" + BLOCKER)


def check(results: list[bool], passed: bool, text: str) -> None:
    results.append(passed)
    print(("PASS " if passed else "FAIL ") + text)


def gate(ticket: int, results: list[bool]) -> None:
    """Run the checks for the ticket and add one result for each check."""
    repository = graphql(TICKET, "-F", f"number={ticket}")
    repo, issue = repository["nameWithOwner"], repository["issue"]
    if not issue:
        check(results, False, f"ticket: issue #{ticket} does not exist in {repo}")
        return
    check(results, True, f"ticket: issue #{ticket} exists in {repo}")
    body = issue["body"] or ""

    parent, body_parent, parent_problems = issue["parent"], None, []
    if not parent:
        numbers, parent_problems = references(section(body, "Parent"), repo)
        if len(numbers) > 1:
            parent_problems.append("names more than one issue: "
                                   + ", ".join(f"#{n}" for n in numbers))
        elif numbers and not parent_problems:
            body_parent = numbers[0]

    native, blocker_problems = {}, []
    blocked = issue["blockedBy"]
    if blocked["totalCount"] > len(blocked["nodes"]):
        blocker_problems.append(f"ticket #{ticket} has more than {len(blocked['nodes'])} "
                                "native blockers")
    for node in blocked["nodes"]:
        other = node["repository"]["nameWithOwner"]
        if other.lower() != repo.lower():
            blocker_problems.append(f"native blocker {other}#{node['number']} is in "
                                    "another repository")
        else:
            native[node["number"]] = node
    body_blockers, problems = references(section(body, "Blocked by"), repo)
    blocker_problems += [f"## Blocked by section: {problem}" for problem in problems]

    # One more query reads the body references that the ticket query lacks.
    extra = sorted(({body_parent} | set(body_blockers)) - set(native) - {None})
    fetched = graphql(issues_query(extra)) if extra else {}
    found = {**{n: fetched.get(f"i{n}") for n in extra}, **native}

    if parent:
        other = parent["repository"]["nameWithOwner"]
        label = ("" if other.lower() == repo.lower() else other) + f"#{parent['number']}"
        check(results, True, f"spec: native parent issue {label} exists")
    elif body_parent:
        exists = found[body_parent] is not None
        check(results, exists, f"spec: parent issue #{body_parent} from the ## Parent section "
              + ("exists" if exists else f"does not exist in {repo}"))
    elif parent_problems:
        for problem in parent_problems:
            check(results, False, f"spec: ## Parent section: {problem}")
    else:
        check(results, True, f"spec: ticket #{ticket} names no parent issue, so it is its own spec")

    for problem in blocker_problems:
        check(results, False, f"blockers: {problem}")
    blockers = sorted(set(body_blockers) | set(native))
    for number in blockers:
        node = found[number]
        if node is None:
            check(results, False, f"blocker #{number}: issue #{number} does not exist in {repo}")
            continue
        prs = node["closedByPullRequestsReferences"]
        merged = [f"#{pr['number']}" for pr in prs["nodes"] if pr["merged"]]
        others = ", ".join(f"#{pr['number']} ({pr['state']})" for pr in prs["nodes"])
        if merged:
            check(results, True, f"blocker #{number}: merged PR {', '.join(merged)} closes it")
        elif prs["totalCount"] > len(prs["nodes"]):
            check(results, False, f"blocker #{number}: has more than {len(prs['nodes'])} "
                  "closing PRs, and the script cannot read them all")
        else:
            check(results, False, f"blocker #{number}: no merged PR closes it"
                  + (f"; closing PRs: {others}" if others else ""))
    if not blockers and not blocker_problems:
        check(results, True, f"blockers: ticket #{ticket} has no blockers")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ticket", type=int, required=True, metavar="N",
                        help="the issue number of the ticket")
    ticket = parser.parse_args().ticket
    results: list[bool] = []
    try:
        gate(ticket, results)
    except CannotDecide as error:
        check(results, False, f"cannot decide: {error}")
    failed = results.count(False)
    if failed:
        print(f"FAIL: do not start coding ticket #{ticket}; "
              f"{failed} of {len(results)} checks failed")
        sys.exit(1)
    print(f"PASS: ticket #{ticket} can start coding; all {len(results)} checks passed")


if __name__ == "__main__":
    main()
