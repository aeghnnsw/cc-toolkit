#!/usr/bin/env python3
"""Print the repo-cleanup plan: KEEP or REMOVE, with the reason, for each item.

repo-cleanup acts only on the REMOVE lines. This script removes nothing: it
runs git, read-only gh commands, and live_worktrees.py, which is next to it.

Each line has four tab-separated fields: KEEP or REMOVE; the kind (folder,
worktree, branch, config-section, or remote-branch); the folder path, the
worktree path as `git worktree list` prints it, the branch name, or the config
section; and the reason. The rules:

- Keep the main checkout, the Default Branch, and the worktree that the
  current session runs in: the top level of --repo.
- Keep each worktree that holds a lead state of t3-project-lead:
  .scratch/<YYYYMMDD>-lead-<slug>/state.json at its top, whatever
  --planning-location names, also with --main-only. Keep a worktree whose
  .scratch or lead folder cannot be read.
- Read each lead state, also the one in the main checkout. Keep each worktree
  whose path a task of a lead state records while the task is not settled,
  except a task that is verified or closed-out once the close-out task of its
  batch has started (#639): the batch close-out removes the worktrees of its
  verified tasks. A task matches no worktree by its branch: T3 Code renames a
  branch after the task starts. When a .scratch, a lead folder, or a lead state cannot be read,
  keep every worktree that the plan would otherwise remove, with the error.
- Keep each worktree that a T3 Code thread owns while the thread is not
  settled (#578). The t3 CLI is T3CODE_CLI_PATH when it is set, else t3 on
  PATH. Run `t3 thread list --json --project <main checkout>` once, then
  `t3 thread show --json --messages 1 <threadId>` for each row with
  `settled: false`, and match the real path of `thread.worktreePath`. Without
  a CLI, or when the list prints "No T3 Code project matches", this rule keeps
  nothing. When a t3 call fails, times out after 10 seconds, prints no JSON,
  or lacks a key or a value of the expected type, keep every worktree that the
  plan would otherwise remove, with the error. The CLI asks the running T3 Code server: while the T3 Code
  app is closed, it fails (t3 v0.1.11), so the plan keeps every such worktree.
  `thread list` hides delegate_task workers, so only a lead state keeps the
  worktree of such a worker.
- Keep each worktree whose folder contains another worktree that Git lists.
- Keep each worktree that live_worktrees.py lists, with its evidence. When
  that script fails, keep every worktree. When only session logs and
  Antigravity conversations list a worktree, the reason gives the time when
  their 60-minute window ends, or says that the end is unknown. Session logs
  and Antigravity conversations do not keep a worktree when each task that
  records its path is in an accepted state (#610): verified, closed-out, or
  settled, and not cancelled, as accepted() of t3_project_lead.py tells. The
  workers of such a task have ended their sessions. The rule for a task that
  is not settled decides first, so the #610 rule frees the worktree of a
  settled task. The plan then applies the rules below, and the reason names
  the task. A Git lock or a running process still keeps the worktree.
- Keep a worktree with a detached HEAD or with uncommitted changes.
- A branch is merged when a merged PR of the branch has the branch tip as its
  head commit (headRefOid). The plan also treats a branch as merged when its
  tip is in the Default Branch or is the head commit of any merged PR (gh api
  repos/{owner}/{repo}/commits/<tip>/pulls): such a branch has no commit of
  its own. Keep such a branch when its reflog shows that it was created less
  than 60 minutes ago, or when the reflog cannot be read. The reflog of a remote branch shows when
  this clone first had it. Keep every other branch, and each branch whose PR
  state cannot be read.
- Inspect the planning folders: the entries of --planning-location in the main
  checkout, in the current worktree, and in each worktree that the plan would
  otherwise remove. With --main-only, inspect the planning folders of the main
  checkout and of each worktree that the plan would otherwise remove, and
  remove a folder outside the main checkout only when the plan removes its
  worktree, which deletes the folder. Remove a folder whose issue is closed
  as completed. Keep the folders of open or not-planned issues, entries
  with no issue key (such as a date key), and folders whose issue state cannot
  be read. Keep each worktree that holds a kept folder, or whose planning
  folder location cannot be read.
- Keep the local and remote branch of each kept worktree, and the remote
  branch of each kept local branch: the remote branch with its name or its
  upstream. A branch's PRs are those whose head is its upstream branch, or
  the branch name when it has no upstream on the remote.
- Remove each branch.<name> section of the Git config whose local branch
  does not exist. `git branch -D` deletes a branch and exits 0 also when it
  cannot lock the Git config, for example in a sandbox, and the section then
  stays (#643). With --config-sections, print only these lines, and run none
  of the other checks.

The exit status is 0 when the plan is printed, and 1 when no plan can be
made, for example outside a repository or without a known Default Branch.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import time
from typing import NoReturn

# Python puts the folder of this script on sys.path, so the sibling modules load.
from live_worktrees import WINDOW_MINUTES
from planning_folder import Failed as PlanningFailed, entries as planning_entries
from t3_project_lead import (SETTLED, Refused as LeadStateRefused, accepted as accepted_task,
                             lead_folders, load as load_lead_state, worktree_released)

LIVE_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "live_worktrees.py")
ISSUE_KEY = re.compile(r"(\d+)-")
# `git reflog show --date=unix --format=%gd` prints <name>@{<seconds since the epoch>}.
REFLOG_TIME = re.compile(r"@\{(\d+)\}$")
KEEP, REMOVE = "KEEP", "REMOVE"
# The t3 CLI prints this for a folder outside every T3 Code project (t3 v0.1.11).
NO_T3_PROJECT = "No T3 Code project matches"
# Seconds for each t3 call, as t3_project_lead.py waits for git.
T3_TIMEOUT = 10


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

    def commit_prs(self, commit: str) -> tuple[object, str | None]:
        """Return the PRs of a commit; GitHub answers HTTP 422 for a commit that it lacks."""
        return self.read("api", f"repos/{{owner}}/{{repo}}/commits/{commit}/pulls?per_page=100")

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

    def minutes_since_creation(self, ref: str) -> tuple[int | None, str | None]:
        """Return (the minutes since the oldest reflog entry of ref, None), or (None, the error)."""
        output = git(self.repo, "reflog", "show", "--date=unix", "--format=%gd", ref, "--",
                     check=False)
        if output is None:
            return None, f"git reflog show {ref} failed"
        entries = output.split()
        if not entries:
            return None, f"the reflog of {ref} has no entry"
        match = REFLOG_TIME.search(entries[-1])
        if match is None:
            return None, f"the reflog of {ref} has no time: {entries[-1]}"
        return int((time.time() - int(match.group(1))) // 60), None

    def branch(self, name: str, tip: str, ref: str) -> tuple[str, str]:
        """Return the action and reason for a branch.

        name is the head branch of the branch's PRs, and ref is the ref whose
        reflog shows when the branch was created.
        """
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
        not_merged = f"not merged: no merged PR has the tip {tip[:7]} as its head commit{others}"
        if self.in_default(tip):
            where = "is in the Default Branch"
        else:
            pulls, error = self.github.commit_prs(tip)
            if error is not None and "No commit found" in error:
                return KEEP, not_merged
            if error is not None:
                return KEEP, f"PR state cannot be read: {error}"
            heads = [pr.get("number") for pr in pulls if isinstance(pr, dict)
                     and pr.get("merged_at") and isinstance(pr.get("head"), dict)
                     and pr["head"].get("sha") == tip] if isinstance(pulls, list) else []
            if not heads:
                return KEEP, not_merged
            where = f"is the head commit of merged PR #{heads[0]}"
        reason = f"no commit of its own: the tip {tip[:7]} {where}{others}"
        minutes, error = self.minutes_since_creation(ref)
        if error is not None:
            return KEEP, f"{reason}, but its creation time cannot be read: {error}"
        if minutes < WINDOW_MINUTES:
            return KEEP, (f"{reason}, but its reflog shows that it was created {minutes} "
                          f"minutes ago, less than {WINDOW_MINUTES} minutes ago")
        return REMOVE, reason

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


def find_lead_folders(root: str) -> tuple[list[str], str | None]:
    """Return (the lead folders at the top of root, None), or ([], the error).

    A lead folder is .scratch/<YYYYMMDD>-lead-<slug>/ with a state file.
    lead_folders of t3_project_lead.py finds them with planning_folder.py
    (#599). It fails when .scratch or a lead folder cannot be read, because the
    plan then cannot tell whether root holds a lead state.
    """
    try:
        return lead_folders(root), None
    except PlanningFailed as error:
        return [], f"cannot look for a lead state: {error}"


def lead_task_worktrees(folders: list[str]) -> tuple[dict[str, str], dict[str, str], str | None]:
    """Return the worktrees that the tasks of the lead states record (#575, #610, #639).

    The result is (kept, ended, None), with the error of the first lead state
    that cannot be read in place of None. kept maps the real path of each
    worktree that a task that is not settled records to the reason to keep it.
    ended maps the real path of each other worktree to a description of an
    accepted task that records it, when every task that records it is
    accepted. The lead accepted the final report of that task's worker, and
    settles a replaced worker at once (task worker), so their sessions have
    ended. A task whose worktree the close-out of its batch removes keeps no
    worktree (worktree_released of t3_project_lead.py).
    """
    kept: dict[str, str] = {}
    ended: dict[str, str] = {}
    not_accepted: set[str] = set()
    first_error = None
    for folder in folders:
        try:
            state = load_lead_state(folder)
            for task in state["tasks"]:
                paths = task.get("worktrees") or []
                if not isinstance(paths, list) or not all(isinstance(path, str) for path in paths):
                    raise TypeError(f"task {task['name']} has the worktrees {paths!r}")
                about = f"task {task['name']} of the lead state {folder} is {task['state']}"
                for path in map(os.path.realpath, paths):
                    if accepted_task(task):
                        ended.setdefault(path, about)
                    else:
                        not_accepted.add(path)
                    if task["state"] != SETTLED and not worktree_released(state, task):
                        kept.setdefault(path, f"{about}, not settled")
        except (OSError, ValueError, KeyError, TypeError, AttributeError,
                LeadStateRefused) as error:
            first_error = first_error or (f"cannot read the lead state {folder}: "
                                          f"{type(error).__name__}: {one_line(str(error))}")
    ended = {path: about for path, about in ended.items()
             if path not in kept and path not in not_accepted}
    return kept, ended, first_error


class T3Error(Exception):
    """A t3 call that cannot run, fails, times out, or prints no JSON."""


def t3(cli: str, *args: str) -> object:
    """Return the JSON output of a t3 call, or raise T3Error with the error."""
    name = f"t3 {args[0]} {args[1]}"
    try:
        result = subprocess.run([cli, *args], capture_output=True, text=True, timeout=T3_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise T3Error(f"{name} timed out after {T3_TIMEOUT} seconds") from None
    except OSError as error:
        raise T3Error(f"{name} cannot run: {error}") from None
    if result.returncode != 0:
        raise T3Error(f"{name} exited with status {result.returncode}: "
                      f"{one_line(result.stderr + ' ' + result.stdout)}")
    try:
        return json.loads(result.stdout)
    except ValueError:
        raise T3Error(f"{name} printed no JSON") from None


def unsettled_thread_worktrees(project: str) -> tuple[dict[str, str], str | None]:
    """Return the worktrees that the T3 Code threads of the project own while not settled (#578).

    The result is ({real path: the reason to keep it}, None), or ({}, the
    error). Without a t3 CLI, or for a repository that is no T3 Code project,
    the result is ({}, None): this source gives no evidence.
    """
    cli = os.environ.get("T3CODE_CLI_PATH") or shutil.which("t3")
    if not cli:
        return {}, None
    kept: dict[str, str] = {}
    try:
        try:
            rows = t3(cli, "thread", "list", "--json", "--project", project)
        except T3Error as error:
            if NO_T3_PROJECT in str(error):
                return {}, None
            raise
        for row in rows:
            thread_id, settled = row["threadId"], row["settled"]
            if not isinstance(settled, bool):
                raise TypeError(f"thread {thread_id} has settled {settled!r}")
            if settled:
                continue
            path = t3(cli, "thread", "show", "--json", "--messages", "1",
                      thread_id)["thread"]["worktreePath"]
            if path is not None:
                kept.setdefault(os.path.realpath(path), f"T3 thread {thread_id} is not settled")
    except T3Error as error:
        return {}, f"cannot read the T3 Code threads: {error}"
    except (KeyError, TypeError) as error:
        return {}, (f"cannot read the T3 Code threads: {type(error).__name__}: "
                    f"{one_line(str(error))}")
    return kept, None


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


def live_worktrees(repo: str) -> tuple[dict[str, tuple[str, str]], str | None]:
    """Return {worktree path: (evidence, window end)} from live_worktrees.py, or ({}, the error)."""
    result = subprocess.run([sys.executable, LIVE_SCRIPT, "--repo", repo],
                            capture_output=True, text=True)
    if result.returncode != 0:
        return {}, (f"live_worktrees.py exited with status {result.returncode}: "
                    f"{one_line(result.stderr)}")
    found = {}
    for line in result.stdout.splitlines():
        path, _, rest = line.partition("\t")
        evidence, _, end = rest.rpartition("\t")
        found[path] = (evidence, end)
    return found, None


def live_reason(evidence: str, end: str) -> str:
    """Return the reason to keep a worktree that live_worktrees.py lists."""
    window = f"{WINDOW_MINUTES}-minute window"
    if not end:
        return f"live session: {evidence}"
    if end == "unknown":
        return f"live session: {evidence}; the end of its {window} is unknown"
    return f"live session: {evidence}; its {window} ends at {end}"


def refs(repo: str, prefix: str) -> dict[str, tuple[str, str]]:
    """Return {name under prefix: (commit, upstream ref)} for each ref under prefix."""
    found = {}
    output = git(repo, "for-each-ref", "--format=%(refname)%09%(objectname)%09%(upstream)", prefix)
    for line in (output or "").splitlines():
        ref, commit, upstream = (line.split("\t") + ["", ""])[:3]
        found[ref[len(prefix):]] = (commit, upstream)
    return found


def config_sections(repo: str,
                    local: dict[str, tuple[str, str]]) -> list[tuple[str, str, str, str]]:
    """Return a REMOVE line for each branch.<name> section of the Git config with no local branch.

    A key of a branch section has a subsection, the branch name, between its
    first and last dot; a key without one, such as branch.autoSetupMerge, is a
    setting.
    """
    output = git(repo, "config", "--local", "--name-only", "-z", "--list")
    names = [key[len("branch."):key.rindex(".")] for key in (output or "").split("\0")
             if key.startswith("branch.") and key.count(".") >= 2]
    return [(REMOVE, "config-section", f"branch.{name}", f"no local branch {name}")
            for name in dict.fromkeys(names) if name not in local]


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
    parser.add_argument("--config-sections", action="store_true",
                        help="print only the config-section lines, and run none of the other "
                             "checks")
    args = parser.parse_args()

    current = os.path.realpath(git(args.repo, "rev-parse", "--show-toplevel").strip())
    local = refs(args.repo, "refs/heads/")
    if args.config_sections:
        for line in config_sections(args.repo, local):
            print("\t".join(line))
        return
    default, default_ref = default_branch(args.repo, args.remote, args.default_branch)
    worktrees = worktree_list(args.repo)
    live, live_error = live_worktrees(args.repo)
    planner = Planner(args.repo, default_ref, GitHub(current))
    lines: list[tuple[str, str, str, str]] = []
    remote_prefix = f"refs/remotes/{args.remote}/"

    def pr_head(branch: str) -> str:
        """Return the head branch name of the branch's PRs: its upstream branch, or its name."""
        upstream = local.get(branch, ("", ""))[1]
        return upstream[len(remote_prefix):] if upstream.startswith(remote_prefix) else branch

    # The worktrees that each worktree's folder contains: removing it would delete them.
    real = {tree["path"]: os.path.realpath(tree["path"]) for tree in worktrees}
    inside = {path: [other for other, other_real in real.items()
                     if other_real.startswith(top + os.sep)]
              for path, top in real.items()}

    # The lead states in each checkout, and the worktrees that their tasks record (#575).
    lead_scans = {tree["path"]: find_lead_folders(tree["path"]) for tree in worktrees}
    recorded, ended, lead_error = lead_task_worktrees(
        [folder for folders, _ in lead_scans.values() for folder in folders])
    lead_error = next((error for _, error in lead_scans.values() if error), None) or lead_error
    # The worktrees that unsettled T3 Code threads own (#578).
    thread_worktrees, thread_error = unsettled_thread_worktrees(worktrees[0]["path"])
    # The worktrees that only session logs and Antigravity conversations list, whose
    # task the lead accepted: that evidence does not keep them (#610).
    ignored = {path: (f"{ended[real[path]]}, so its session logs and Antigravity "
                      "conversations do not keep it")
               for path, (_, end) in live.items() if end and real.get(path) in ended}

    # Each worktree's action and reason, before the planning folders.
    plan: dict[str, tuple[str, str]] = {}
    for index, tree in enumerate(worktrees):
        path, head, branch = tree["path"], tree.get("HEAD", ""), tree.get("branch")
        held, scan_error = lead_scans[path]
        if index == 0:
            plan[path] = (KEEP, "the main checkout")
        elif os.path.realpath(path) == current:
            # The merged PR of this worktree is often the work that cleanup reconciles.
            merged = (f"; {planner.branch(pr_head(branch), head, f'refs/heads/{branch}')[1]}"
                      if branch and branch != default else "")
            plan[path] = (KEEP, f"the current session runs here{merged}")
        elif scan_error is not None:
            plan[path] = (KEEP, scan_error)
        elif held:
            plan[path] = (KEEP, f"holds a lead state: {held[0]}")
        elif real[path] in recorded:
            plan[path] = (KEEP, recorded[real[path]])
        elif real[path] in thread_worktrees:
            plan[path] = (KEEP, thread_worktrees[real[path]])
        elif inside[path]:
            plan[path] = (KEEP, f"contains the worktree {', '.join(inside[path])}")
        elif live_error is not None:
            plan[path] = (KEEP, f"live session check failed: {live_error}")
        elif path in live and path not in ignored:
            plan[path] = (KEEP, live_reason(*live[path]))
        else:
            if branch is None:
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
                    plan[path] = planner.branch(pr_head(branch), head, f"refs/heads/{branch}")
            if path in ignored:
                action, reason = plan[path]
                plan[path] = (action, f"{reason}; {ignored[path]}")

    # A lead state or a T3 Code thread that cannot be read may own any worktree.
    if lead_error is not None or thread_error is not None:
        for path, (action, _) in plan.items():
            if action == REMOVE:
                plan[path] = (KEEP, lead_error or thread_error)

    # The planning folders, and the worktrees that hold a kept one. With
    # --main-only, a completed folder outside the main checkout gets a REMOVE
    # line only when the plan removes its worktree, which deletes it (#577).
    main_path = worktrees[0]["path"]
    roots = [main_path] + [path for path, (action, _) in plan.items() if action == REMOVE or (
        not args.main_only and os.path.realpath(path) == current)]
    for root in dict.fromkeys(roots):
        location = os.path.join(root, args.planning_location)
        # planning_folder.py lists the location (#599), files too: a file keeps its worktree.
        try:
            paths = planning_entries(root, args.planning_location)
        except PlanningFailed as error:
            lines.append((KEEP, "folder", location, f"cannot be read: {error}"))
            if plan[root][0] == REMOVE:
                plan[root] = (KEEP, f"its planning folders cannot be read: {error}")
            continue
        entries = [(entry, *planner.folder(entry)) for entry in paths]
        for entry, action, reason in entries:
            if action == KEEP and plan[root][0] == REMOVE:
                plan[root] = (KEEP, f"holds the kept planning folder {entry}: {reason}")
        # The worktree's action is final only after all its folders are read.
        for entry, action, reason in entries:
            if action == REMOVE and args.main_only and root != main_path:
                if plan[root][0] != REMOVE:
                    continue
                reason += f"; removing the worktree {root} deletes it"
            lines.append((action, "folder", entry, reason))

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
            branches[name] = (worktree_branches.get(name)
                              or planner.branch(pr_head(name), tip, f"refs/heads/{name}"))
        action, reason = branches[name]
        lines.append((action, "branch", name, reason))
        for remote_name in dict.fromkeys((name, pr_head(name))):
            locals_of.setdefault(remote_name, []).append(name)
    lines += config_sections(args.repo, local)
    for name, (tip, _) in refs(args.repo, remote_prefix).items():
        if name in ("HEAD", default):
            continue
        kept = [owner for owner in locals_of.get(name, []) if branches[owner][0] == KEEP]
        if not kept:
            action, reason = planner.branch(name, tip, f"{remote_prefix}{name}")
        elif kept[0] == name:
            action, reason = branches[name]
        else:
            action, reason = KEEP, f"its local branch {kept[0]} is kept: {branches[kept[0]][1]}"
        lines.append((action, "remote-branch", f"{args.remote}/{name}", reason))

    for line in lines:
        print("\t".join(line))


if __name__ == "__main__":
    main()
