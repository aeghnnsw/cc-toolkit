#!/usr/bin/env python3
"""Print the repo-cleanup plan: KEEP or REMOVE, with the reason, for each item.

repo-cleanup acts only on the REMOVE lines. This script removes nothing: it
runs git, read-only gh commands, and live_worktrees.py, which is next to it.

Each line has four tab-separated fields: KEEP or REMOVE; the kind (folder,
worktree, branch, or remote-branch); the folder path, the worktree path as
`git worktree list` prints it, or the branch name; and the reason. The rules:

- Keep the main checkout, the Default Branch, and the worktree that the
  current session runs in: the top level of --repo.
- Keep each worktree that holds a t3-project-lead state:
  .scratch/<YYYYMMDD>-lead-<slug>/state.json, as t3_project_lead.py names it.
  This rule applies in every mode, including --main-only.
- Keep each worktree that live_worktrees.py lists, with its evidence. When
  that script fails, keep every worktree.
- Keep a worktree with a detached HEAD or with uncommitted changes.
- A branch is merged only when a merged PR of the branch has the branch tip
  as its head commit (headRefOid). Keep a branch whose tip is in the Default
  Branch without such a PR: it has no commit of its own, and a session may
  have just started there. Keep every other unmerged branch, and each branch
  whose PR state cannot be read.
- Inspect the planning folders: the entries of --planning-location in the main
  checkout, in the current worktree, and in each worktree that the plan would
  otherwise remove. With --main-only, inspect the main checkout alone. Remove
  a folder whose issue is closed as completed. Keep the folders of open or
  not-planned issues, entries with no issue key (such as a date key), and
  folders whose issue state cannot be read. Keep each worktree that holds a
  kept folder.
- Keep the local and remote branch of each kept worktree, and the remote
  branch of each kept local branch: the remote branch with its name or its
  upstream. A branch's PRs are those whose head is its upstream branch, or
  the branch name when it has no upstream on the remote.

The exit status is 0 when the plan is printed, and 1 when no plan can be
made, for example outside a repository or without a known Default Branch.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from typing import NoReturn

# Python puts the folder of this script on sys.path, so the sibling module loads.
from t3_project_lead import FOLDER as LEAD_FOLDER, STATE_FILE as LEAD_STATE_FILE

LIVE_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "live_worktrees.py")
ISSUE_KEY = re.compile(r"(\d+)-")
KEEP, REMOVE = "KEEP", "REMOVE"


def fail(message: str) -> NoReturn:
    print(f"cleanup_plan: {message}", file=sys.stderr)
    sys.exit(1)


def one_line(text: str) -> str:
    return " ".join(text.split())


def git(repo: str, *args: str, check: bool = True) -> str | None:
    """Return the output of a git command; on failure, exit or return None."""
    try:
        result = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    except FileNotFoundError:
        fail("git is not installed")
    if result.returncode == 0:
        return result.stdout
    if check:
        fail(one_line(result.stderr) or f"git {args[0]} failed")
    return None


class GitHub:
    """Read merged PRs and issue states with gh, once for each branch or issue."""

    def __init__(self, repo: str) -> None:
        self.repo = repo
        self.cache: dict[tuple[str, ...], tuple[object, str | None]] = {}

    def read(self, *args: str) -> tuple[object, str | None]:
        """Return (the JSON output, None), or (None, the error)."""
        if args not in self.cache:
            try:
                result = subprocess.run(["gh", *args], cwd=self.repo, capture_output=True,
                                        text=True)
            except FileNotFoundError:
                self.cache[args] = (None, "gh is not installed")
            else:
                if result.returncode != 0:
                    self.cache[args] = (None, one_line(result.stderr) or f"gh {args[0]} failed")
                else:
                    try:
                        self.cache[args] = (json.loads(result.stdout), None)
                    except ValueError:
                        self.cache[args] = (None, "gh printed no JSON")
        return self.cache[args]

    def merged_prs(self, branch: str) -> tuple[object, str | None]:
        return self.read("pr", "list", "--head", branch, "--state", "merged",
                         "--json", "number,headRefOid", "--limit", "100")

    def issue(self, number: int) -> tuple[object, str | None]:
        return self.read("issue", "view", str(number), "--json", "state,stateReason")


class Planner:
    def __init__(self, repo: str, default_ref: str, github: GitHub) -> None:
        self.repo = repo
        self.default_ref = default_ref
        self.github = github

    def in_default(self, commit: str) -> bool:
        return git(self.repo, "merge-base", "--is-ancestor", commit, self.default_ref,
                   check=False) is not None

    def branch(self, name: str, tip: str) -> tuple[str, str]:
        """Return the action and reason for a branch, from its merged PRs."""
        prs, error = self.github.merged_prs(name)
        if error is not None:
            return KEEP, f"PR state cannot be read: {error}"
        prs = [pr for pr in prs if isinstance(pr, dict)] if isinstance(prs, list) else []
        for pr in prs:
            if pr.get("headRefOid") == tip:
                return REMOVE, (f"merged PR #{pr.get('number')} has the tip {tip[:7]} "
                                "as its head commit")
        others = "".join(
            f"; merged PR #{pr.get('number')} has head {str(pr.get('headRefOid'))[:7]}"
            for pr in prs)
        if self.in_default(tip):
            return KEEP, (f"no commit of its own: the tip {tip[:7]} is in the Default Branch, "
                          f"and no merged PR has it as its head commit{others}")
        return KEEP, f"not merged: no merged PR has the tip {tip[:7]} as its head commit{others}"

    def folder(self, path: str) -> tuple[str, str]:
        """Return the action and reason for an entry of a planning folder location."""
        name = os.path.basename(path)
        match = ISSUE_KEY.match(name)
        if match is None:
            return KEEP, "no issue key"
        digits = match.group(1)
        if len(digits) == 8:
            try:
                datetime.datetime.strptime(digits, "%Y%m%d")
                return KEEP, f"no issue key: {digits} is a date"
            except ValueError:
                pass
        if not os.path.isdir(path):
            return KEEP, "a file, not a planning folder"
        number = int(digits)
        issue, error = self.github.issue(number)
        if error is not None or not isinstance(issue, dict):
            return KEEP, f"issue #{number} state cannot be read: {error}"
        state, reason = issue.get("state"), str(issue.get("stateReason") or "")
        if state == "OPEN":
            return KEEP, f"issue #{number} is open"
        if state == "CLOSED" and reason == "COMPLETED":
            return REMOVE, f"issue #{number} is closed as completed"
        if state == "CLOSED":
            closed_as = reason.lower().replace("_", " ") or "unknown"
            return KEEP, f"issue #{number} is closed as {closed_as}"
        return KEEP, f"issue #{number} has state {state}"


def worktree_list(repo: str) -> list[dict[str, str]]:
    """Return each worktree with its path, HEAD, and branch; the main checkout comes first."""
    found: list[dict[str, str]] = []
    for line in (git(repo, "worktree", "list", "--porcelain") or "").splitlines():
        key, _, value = line.partition(" ")
        if key == "worktree":
            found.append({"path": value})
        elif found and key in ("HEAD", "branch", "detached", "bare"):
            found[-1][key] = value[len("refs/heads/"):] if key == "branch" else value
    return found


def lead_state(root: str) -> str | None:
    """Return the first t3-project-lead folder with a state file in root/.scratch, or None."""
    scratch = os.path.join(root, ".scratch")
    try:
        names = sorted(os.listdir(scratch))
    except OSError:
        return None
    for name in names:
        folder = os.path.join(scratch, name)
        if LEAD_FOLDER.fullmatch(name) and os.path.isfile(os.path.join(folder, LEAD_STATE_FILE)):
            return folder
    return None


def default_branch(repo: str, remote: str, given: str | None) -> tuple[str, str]:
    """Return the Default Branch and the ref that shows what is in it."""
    name = given
    if name is None:
        head = git(repo, "symbolic-ref", "--quiet", f"refs/remotes/{remote}/HEAD", check=False)
        if head is None:
            fail(f"cannot find the Default Branch: refs/remotes/{remote}/HEAD is not set. "
                 f"Run `git remote set-head {remote} --auto`, or pass --default-branch.")
        name = head.strip()[len(f"refs/remotes/{remote}/"):]
    for ref in (f"refs/remotes/{remote}/{name}", f"refs/heads/{name}"):
        if git(repo, "rev-parse", "--verify", "--quiet", ref, check=False) is not None:
            return name, ref
    fail(f"cannot find the Default Branch: no branch {name}")


def live_worktrees(repo: str) -> tuple[dict[str, str], str | None]:
    """Return {worktree path: evidence} from live_worktrees.py, or ({}, the error)."""
    result = subprocess.run([sys.executable, LIVE_SCRIPT, "--repo", repo],
                            capture_output=True, text=True)
    if result.returncode != 0:
        return {}, (f"live_worktrees.py exited with status {result.returncode}: "
                    f"{one_line(result.stderr)}")
    found = {}
    for line in result.stdout.splitlines():
        path, _, evidence = line.partition("\t")
        found[path] = evidence
    return found, None


def refs(repo: str, prefix: str) -> dict[str, tuple[str, str]]:
    """Return {name under prefix: (commit, upstream ref)} for each ref under prefix."""
    found = {}
    output = git(repo, "for-each-ref", "--format=%(refname)%09%(objectname)%09%(upstream)", prefix)
    for line in (output or "").splitlines():
        ref, commit, upstream = (line.split("\t") + ["", ""])[:3]
        found[ref[len(prefix):]] = (commit, upstream)
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default=".",
                        help="the checkout that the current session runs in (default: .)")
    parser.add_argument("--remote", default="origin", help="the upstream remote (default: origin)")
    parser.add_argument("--default-branch", help="the Default Branch, when the remote names none")
    parser.add_argument("--planning-location", default=".scratch",
                        help="the planning folder location in each checkout (default: .scratch)")
    parser.add_argument("--main-only", action="store_true",
                        help="the repository documents the planning folder location "
                             "in the main checkout")
    args = parser.parse_args()

    current = os.path.realpath(git(args.repo, "rev-parse", "--show-toplevel").strip())
    default, default_ref = default_branch(args.repo, args.remote, args.default_branch)
    worktrees = worktree_list(args.repo)
    live, live_error = live_worktrees(args.repo)
    planner = Planner(args.repo, default_ref, GitHub(current))
    lines: list[tuple[str, str, str, str]] = []
    remote_prefix = f"refs/remotes/{args.remote}/"
    local = refs(args.repo, "refs/heads/")

    def pr_head(branch: str) -> str:
        """Return the head branch name of the branch's PRs: its upstream branch, or its name."""
        upstream = local.get(branch, ("", ""))[1]
        return upstream[len(remote_prefix):] if upstream.startswith(remote_prefix) else branch

    # Each worktree's action and reason, before the planning folders.
    plan: dict[str, tuple[str, str]] = {}
    for index, tree in enumerate(worktrees):
        path, head, branch = tree["path"], tree.get("HEAD", ""), tree.get("branch")
        if index == 0:
            plan[path] = (KEEP, "the main checkout")
        elif os.path.realpath(path) == current:
            # The merged PR of this worktree is often the work that cleanup reconciles.
            merged = (f"; {planner.branch(pr_head(branch), head)[1]}"
                      if branch and branch != default else "")
            plan[path] = (KEEP, f"the current session runs here{merged}")
        elif (lead := lead_state(path)) is not None:
            # An idle lead edits no tracked file, and no live session protects it (issue #543).
            plan[path] = (KEEP, f"holds a lead state: {lead}")
        elif live_error is not None:
            plan[path] = (KEEP, f"live session check failed: {live_error}")
        elif path in live:
            plan[path] = (KEEP, f"live session: {live[path]}")
        elif branch is None:
            plan[path] = (KEEP, f"detached HEAD {head[:7]}" + (
                ": no commit of its own, because it is in the Default Branch"
                if planner.in_default(head) else ", which is not in the Default Branch"))
        else:
            status = git(path, "status", "--porcelain", check=False)
            if status is None:
                plan[path] = (KEEP, "its status cannot be read")
            elif status.strip():
                plan[path] = (KEEP, "uncommitted changes")
            else:
                plan[path] = planner.branch(pr_head(branch), head)

    # The planning folders, and the worktrees that hold a kept one.
    roots = [worktrees[0]["path"]]
    if not args.main_only:
        roots += [path for path, (action, _) in plan.items()
                  if os.path.realpath(path) == current or action == REMOVE]
    for root in dict.fromkeys(roots):
        location = os.path.join(root, args.planning_location)
        if not os.path.isdir(location):
            continue
        for name in sorted(os.listdir(location)):
            entry = os.path.join(location, name)
            action, reason = planner.folder(entry)
            lines.append((action, "folder", entry, reason))
            if action == KEEP and plan[root][0] == REMOVE:
                plan[root] = (KEEP, f"holds the kept planning folder {entry}: {reason}")

    # The worktrees, then their branches and the other branches.
    worktree_branches: dict[str, tuple[str, str]] = {}
    for tree in worktrees:
        action, reason = plan[tree["path"]]
        lines.append((action, "worktree", tree["path"], reason))
        if tree.get("branch"):
            worktree_branches[tree["branch"]] = (action, reason)
    branches = {}
    # The local branches of each remote branch: the same name, or an upstream.
    locals_of: dict[str, list[str]] = {}
    for name, (tip, _) in local.items():
        if name == default:
            branches[name] = (KEEP, "the Default Branch")
        else:
            branches[name] = worktree_branches.get(name) or planner.branch(pr_head(name), tip)
        action, reason = branches[name]
        lines.append((action, "branch", name, reason))
        for remote_name in dict.fromkeys((name, pr_head(name))):
            locals_of.setdefault(remote_name, []).append(name)
    for name, (tip, _) in refs(args.repo, remote_prefix).items():
        if name in ("HEAD", default):
            continue
        kept = [owner for owner in locals_of.get(name, []) if branches[owner][0] == KEEP]
        if not kept:
            action, reason = planner.branch(name, tip)
        elif kept[0] == name:
            action, reason = branches[name]
        else:
            action, reason = KEEP, f"its local branch {kept[0]} is kept: {branches[kept[0]][1]}"
        lines.append((action, "remote-branch", f"{args.remote}/{name}", reason))

    for line in lines:
        print("\t".join(line))


if __name__ == "__main__":
    main()
