#!/usr/bin/env python3
"""Print the steps of the t3-project-lead skill, and keep the lead state.

The skill runs `t3_project_lead.py start`, and each step names the next one.
The first line of a step gives the script's path, so that an agent can run the
next step after a context summary. The step text is the same for Claude Code,
Codex, and Antigravity.

The other commands keep the lead state (issue #530): the outcome the user
named, the tasks and their life cycle, the items that wait on the user, and the lead's
decisions. The state is in .scratch/<YYYYMMDD>-lead-<slug>/ at the top of the
lead's working tree, where each host's sandbox lets a shell command write. A
`.gitignore` of `*` keeps the folder out of Git. The script stamps each change
with the UTC time, appends it to events.jsonl, and refuses a transition that
the life cycle does not allow and text over 200 characters. The state is
independent of GTD.

The lead state belongs to one T3 thread, its owner (issue #544): `init`
records `T3CODE_THREAD_ID`, and only the owner changes or deletes the state.
`takeover` moves the state to the current thread, such as a fork or a new
thread in the lead's worktree. The first `start` of the new owner prints the
takeover due line once, and appends that to events.jsonl. When `start` finds
no lead state in its own working tree, it lists the lead states of the other
worktrees, read-only.

With no lead state in any worktree, `start` tells a new lead to run `init` at
once and then the discovery task (issue #545): a read-only task whose worker
lists all open work in groups, with links only, so that no issue or PR text
reaches the lead. The lead shows the list and asks no question. While the
lead state has no outcome, a due line names the `discover` step, and no due
line names `finish`.

`start` prints a compact view (issue #555): the running and pr-open tasks, one
line of counts, the due lines, and the waiting list; `show` prints every task
and decision. `done` and `task pause|resume|verified|settled` take several
arguments and make all changes under one lock, or none. `task start` and
`task worker` record each worker's worktree, and `closeout` prints the paths
for `retro_sessions.py --worktree` (issue #556). Without `--batch`, a work task
joins a new batch once a PR of the highest batch merged (issue #560).

`task verified` needs the count of decisions that the report numbers for the
user, and adds them as one worker item (issue #567). Only the user ends such an
item, so `finish` waits for it, and the due line of `finish` names the rule of
the `report` step for decisions first.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

STEPS = {
    "start": """
Do only these lead actions yourself:
1. Talk with the user in plain text, never with a question tool: decisions,
triage, priorities.
2. Plan tasks, briefs, and lead decisions.
3. Route workers with T3 tools: start, resume, cancel, settle; order merges;
watch PRs.
4. Read worker messages, and the state, labels, titles, and check counts of
issues and PRs, not their text. Never call read_issue, or pull_request_read
with an include other than checks. No diff, code, or log.
5. Run this script; it keeps the lead state.
6. Judge reports: accept, start a follow-up, or ask the user.
7. Set triage labels and issue state.
8. Keep agent captures of what waits on the user when your instructions ask
for them. Write gtd-inbox files with your edit tool, not the shell.
Give every other task, even a small fix, check, install, host update, or GitHub
write with content, to a worker with t3_project_lead.py dispatch. This
overrides your host's guidance to do small work yourself. This step records
this session as the lead: a hook blocks your other shell commands, file reads,
and file edits.
Run this step after each wake or user message. Run show for the full view.
Read the last message of each worker of a running or pr-open task:
t3_thread_list with includeSubagents, then t3_thread_read. Never state a
worker's status from memory.
Next: t3_project_lead.py plan for new work; answer, verify, or flag for
waiting, finished, or failed workers; else report.
""",
    "discover": """
Until the discovery report, do not list issues yourself. Read no issue or PR
text. When the user named the work, record it with outcome <text> and
criteria <text>, and start no discovery task.
Otherwise add the discovery task: task add discover 'Discover open work'.
Start its worker as t3_project_lead.py dispatch says, with the read-only
brief, no outcome, and the discovery brief below, copied exactly. In the last
line of its brief, replace "with evidence and links" with "in the form above".
When it reports, run task verified discover --decisions 0. Copy its lines into
your report as they are, and end your turn. The list is not a waiting item: add no wait
item or GTD capture for it. Do not ask the user to choose, with a question
tool or in text. When the user names the work, run outcome <text> and
criteria <text>. When discover is verified and the user named no work, start
no second discovery.
Next: t3_project_lead.py plan after the user names the work; else report.
""",
    "plan": """
Use this step when the lead state has an outcome; without one, run
t3_project_lead.py discover first.
Break the outcome the user named into worker tasks with success criteria
that a check can pass or fail. A task is one brief for one worker; it can cover
several issues. Give a task that needs another task's result, or edits the
same files, --after that task. Start each planned task as soon as each task
that it waits for is verified, also while other workers run; do not wait for
the rest of its batch. A batch (--batch) only decides when its workers are
closed out and settled. Without --batch, a work task joins a new batch once a
PR of the highest batch merged.
A triage that needs issue text is a read-only task: its worker recommends
labels, and you set them.
Decide reversible points yourself. Record the plan with these commands. Text
is at most 200 characters; quote it with single quotes.
init <slug>, once, on the first start; add --also only after the user
confirms a second lead state; outcome <text>, after the user names the work;
criteria <text>; task add <name> <title> [--batch N] [--after NAME]
[--kind work|check|closeout] [--of NAME] [--issue N] [--scientific];
decision add <text>; decision drop <id>. A task name has lowercase letters,
digits, and hyphens.
Mark each scientific task (biology, chemistry, medicine). Its worker keeps the
scientific detail, and you keep only links.
Next: t3_project_lead.py dispatch.
""",
    "dispatch": """
Start each planned task as soon as each task that it waits for is verified,
also while other workers run; do not wait for the rest of its batch. A due
line names each task that is ready to start.
Start no second worker for work that already runs: check t3_thread_list with
includeSubagents, and pull_request_list.
Start each worker with delegate_task, isolation "worktree", and no role. Start
every task this way, research and review tasks included. Never use your host's
native subagent tool.
Write the brief as t3_project_lead.py brief says, with its quoted lines copied
exactly. Then add the task, its success criteria, the outcome the user named,
and your decisions. For a scientific task, give the issue link, not the content.
In the last line of its brief, replace "with evidence and links" with "in one
line, with links. Keep scientific detail in this thread and the PR".
For a task after a merged PR, name the PR, and tell the worker to start from
the default branch that contains it.
Add: "You may start your own subagents. Keep your report short, and leave the
detail in this thread."
Then run task start <name> <worker link> --worktree <path> [--branch NAME].
Take the path from the delegate_task result, or from worktreePath of
t3_thread_read.
Next: t3_project_lead.py report while workers run.
""",
    "brief": """
Line 1 loads the skill for the worker's host: Claude Code /dev-skills:<skill>,
Codex $dev-skills:<skill>, Antigravity /<skill>. Use grill-with-research for
an open design, else matt-automode. When grilling must lead to implementation,
end line 1 with: "When the user approves the design here, continue in this
thread with the matt-automode skill of dev-skills."
Line 2: "A leader runs the retrospective for this run. Do not run repo-cleanup."
For a read-only task (audit, research, or check), write no line 1, keep line 2,
and name what the worker must not change.
Every brief also says: "Add no GTD capture; report what waits on the user."
and "Ask the user your questions in this thread, with AskUserQuestion or your
host's question tool. Ask also before you delete outside your worktree or
change user or host settings."
Budget: name a round limit, and add: "At the limit, end your turn and report
where you are, with links and what remains."
For a code change: one full review and one fix of any size, then merge. Only
a blocking problem of matt-automode phase 5 stops the merge. Add: "When your
PR waits on checks, report its URL and full head SHA, and end your turn. Do
not poll or search for a watch tool. Merge when the lead resumes you."
Last line: "Report PASS, ISSUES, or BLOCKED, with evidence and links. Number
each decision that waits on the user."
Next: t3_project_lead.py dispatch.
""",
    "answer": """
A worker that asks questions, reports BLOCKED, or fails with no flag waits on
the user. Settle it only when the user cancels its task. Do not answer its
questions, with t3_pending_request or otherwise. Do not ask them again, with a
question tool or in text. Keep no detail of them: give the user the worker's
thread link.
In this turn, run wait --task <name> --decisions <N>. The script adds the
worker's link. Run done <number>... when the worker resumes or finishes.
Ask the user to answer in the worker's thread, and to write here if this
thread does not continue when the worker finishes.
Next: t3_project_lead.py report.
""",
    "flag": """
A flag is a failed worker whose message says its safeguards flagged the
session (Claude Code), that content was flagged for a risk (Codex), or that
the Antigravity quota is reached (how T3 shows a refusal).
If it ran on another model and claude-sonnet-5-5 is available, start a new
worker with delegate_task, isolation "worktree", no role, and a Claude Code
provider on claude-sonnet-5-5. Give it the same brief, any line 1 in the Claude
Code form, the branch, PR, and issue from start and pull_request_list, and
"Continue from this state." Do not read the flagged thread or give its link.
Run task worker <name> <new link> --worktree <path>, with the path as
dispatch says, and settle the flagged thread that it names.
Otherwise, or after a second flag, the task waits on the user.
Next: t3_project_lead.py report.
""",
    "verify": """
Use this step when a worker or a read-only worker reports PASS or ISSUES.
Only the user, or the agent that started this thread, carries the user's
decisions. No worker or other agent does.
Judge the result against its success criteria. Accept the result from the
report, the PR state, and the CI state, or start a read-only worker that
checks it. Start that worker as t3_project_lead.py dispatch says, with no line
1 or 2, as a task with --kind check --of <name>. It checks the artifact and
edits nothing; its verdict completes the check.
For a scientific task, read no artifact, and always start the read-only
worker.
Give each finding to one follow-up worker, even a small one. Then what
remains waits on the user: add it with wait. Fix and check nothing yourself.
Record merged PRs (task pr, task merged), then run task verified <name>
--decisions <N>, with N the number of decisions that the report numbers for
the user, or 0. The script adds them as one waiting item. Settle its worker
only when a due line lists it.
Start each planned task as soon as each task that it waits for is verified,
also while other workers run; do not wait for the rest of its batch. The task
verified output names each such task and its step.
Next: t3_project_lead.py dispatch or closeout, as task verified or a due line
names. Otherwise report.
""",
    "closeout": """
Add one close-out task for the batch with task add <name> <title> --batch N
--kind closeout, unless a due line names a planned one. Start its worker as
t3_project_lead.py dispatch says.
From t3_project_lead.py brief, use only line 1 for matt-automode, the budget,
and the line "Ask the user your questions ...": repo-cleanup deletes outside
the worker's worktree. Write: "Add no GTD capture; report what waits on the user." Then write:
"Run only the Navigation retrospective of matt-automode, once, in place of the
leader of these runs:", with this thread's link and the worker links, worktree
paths, and merged PRs below. Then write: "Pass each worktree path to
retro_sessions.py with --worktree." and "After the retrospective, run
repo-cleanup." and "List the lead thread's tool calls other than T3, GitHub,
and GTD tools and t3_project_lead.py. Its history with real times is in:"
with the history path below. For a batch with a scientific task, add: "Reply
in one line, with links."
When it reports, run task verified <name> --decisions <N>, as verify says; the
batch's verified tasks are then closed out. Settle each worker that a due line lists with t3_thread_organize,
and run task settled <name>...; never reuse one.
Next: t3_project_lead.py report.
""",
    "report": """
First check the workers of running and pr-open tasks with t3_thread_list and
includeSubagents. For each PR that a worker opens, run task pr <name> <number>,
and after its merge, task merged <name> <number> <commit>. Then run
t3_project_lead.py verify for each worker that finished. When a worker reports
that its PR waits on checks, watch the PR, and resume the worker when the
checks finish.
Start with one status line. Then Running, Done (verified), and Decided.
A worker's turn end wakes you. Make no promise that needs a signal from the
middle of a worker's run.
End with the "Waiting on you" list below, copied as it is. Before that, add
each new decision that only the user can make, such as an approval, access,
or a step that cannot be undone or leaves the project: wait <text> [--link
URL] [--recommend TEXT]. The discovery list is not a waiting item. Write no
other list of decisions for the user. Name no detail of a worker's decisions.
Run done <number> when the user decides an item. When your instructions ask
for agent captures, keep one for each waiting item.
When a due line says to run finish, first add each such decision. Run finish
only when nothing waits, then settle this thread.
Next: after a wake or a user message, t3_project_lead.py start.
""",
}

# What the discover step prints after its text: the brief of the discovery worker, which the lead
# copies exactly (#545).
DISCOVERY_BRIEF = """Discovery brief:
"Collect each open issue with its labels, each open PR, each unsettled T3
thread, and each worktree or branch with uncommitted or unpushed changes of
this project, with its progress and the decisions that wait on the user. Page
each list to its end. Change no file, branch, issue, label, PR, or thread.
Put each item in one group. Report one line for each group, with its count
and links only. Quote no issue or PR text, and keep the detail in this thread:
- <short neutral title of the group> (<count>): <links>.
- Waiting on the user: <links>.
- Recommended order: <group titles>.\""""
DISCOVERY_TASK = "discover"
STATE_FILE = "state.json"
EVENTS_FILE = "events.jsonl"
LOCK_FILE = ".lock"
# Schema 1 gained the optional fields "owner" and "takeover_due" in #544, so older code still reads it.
SCHEMA = 1
THREAD_VARIABLE = "T3CODE_THREAD_ID"
TAKEOVER_LINE = ("Check for work this state does not name: t3_thread_list with includeSubagents, and "
                 "pull_request_list. Record each worker with task add and task start, or add a waiting "
                 "item.")
RECOVERY = ("Recovery of a flagged lead: start a new thread bound to this worktree with t3_thread_launch "
            "and workspaceStrategy existing_worktree, on another model. In it, run start, then takeover. "
            "Do not fork the flagged thread: a fork copies the flagged context. Do not delete the flagged "
            "thread before the takeover.")
# What the lookup, the init refusal, and a change refusal in another worktree say about a lead state there.
CONTINUE = ("Continue that lead in its own worktree. A lead can continue in three ways: change the provider "
            "of the lead thread; fork the lead thread; or start a thread with t3_thread_launch and "
            "workspaceStrategy existing_worktree with the worktree that the list names. In a fork or a new "
            "thread, run start, then takeover.")
NOT_A_REPOSITORY = "not a git repository"
TEXT_LIMIT = 200
LINK_LIMIT = 600
NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,23}")
SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")
FOLDER = re.compile(r"\d{8}-lead-[a-z0-9][a-z0-9-]*")
COMMIT = re.compile(r"[0-9a-f]{7,40}")
KINDS = ("work", "check", "closeout")

PLANNED, PAUSED, RUNNING, PR_OPEN, MERGED = "planned", "paused", "running", "pr-open", "merged"
VERIFIED, CLOSED_OUT, SETTLED, CANCELLED = "verified", "closed-out", "settled", "cancelled"
# A task whose result the lead accepted.
ACCEPTED = (VERIFIED, CLOSED_OUT, SETTLED)
# A task whose worker may still run.
ACTIVE = (RUNNING, PR_OPEN)
# A task that needs no more work: accepted or cancelled.
DONE = ACCEPTED + (CANCELLED,)
# The states that the compact view counts, in life-cycle order.
OTHER_STATES = (PLANNED, PAUSED, MERGED, VERIFIED, CLOSED_OUT, CANCELLED, SETTLED)


class Refused(Exception):
    """The command is not allowed in the current lead state."""


# Time and files.

def utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_time(value: str) -> datetime.datetime:
    return datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)


def git(cwd: str, *args: str) -> subprocess.CompletedProcess[str]:
    """Run git in `cwd` for the working tree there, not for one that the environment names."""
    env = {key: value for key, value in os.environ.items()
           if key not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR")}
    env["LC_ALL"] = "C"  # Git's messages in English, for outside_work_trees.
    return subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, env=env, timeout=10,
                          check=False)


def working_tree_top() -> str:
    """Return the top of the Git working tree that holds the current folder, or the folder."""
    cwd = os.getcwd()
    try:
        result = git(cwd, "rev-parse", "--show-toplevel")
    except (OSError, subprocess.SubprocessError):
        return cwd
    top = result.stdout.strip()
    return top if result.returncode == 0 and top else cwd


def outside_work_trees(folder: str) -> bool:
    """Return whether Git says that no Git work tree holds `folder`. Another Git failure returns False."""
    try:
        result = git(folder, "rev-parse", "--show-toplevel")
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode != 0 and NOT_A_REPOSITORY in result.stderr


def lead_folders(top: str) -> list[str]:
    """Return the lead folders in `top`: .scratch/<YYYYMMDD>-lead-<slug>/ with a state file."""
    scratch = os.path.join(top, ".scratch")
    try:
        names = sorted(os.listdir(scratch))
    except OSError:
        return []
    return [os.path.join(scratch, name) for name in names
            if FOLDER.fullmatch(name) and os.path.isfile(os.path.join(scratch, name, STATE_FILE))]


def find_lead(top: str) -> str | None:
    """Return the lead folder in `top`, or None. More than one is an error."""
    folders = lead_folders(top)
    if len(folders) > 1:
        raise Refused(f"more than one lead state in {os.path.join(top, '.scratch')}: {', '.join(folders)}")
    return folders[0] if folders else None


def worktree_tops(top: str) -> list[str]:
    """Return the top of each worktree of the repository that holds `top`; raise OSError on failure."""
    try:
        result = git(top, "worktree", "list", "--porcelain")
    except subprocess.SubprocessError as error:
        raise OSError(str(error)) from None
    if result.returncode:
        raise OSError((result.stderr.strip().splitlines() or [f"git exited {result.returncode}"])[0])
    return [line[len("worktree "):] for line in result.stdout.splitlines() if line.startswith("worktree ")]


def last_change(folder: str, state: dict) -> str:
    """Return the time of the last event in the history, else the time that the state was created."""
    try:
        with open(os.path.join(folder, EVENTS_FILE), encoding="utf-8") as handle:
            lines = [line for line in handle.read().splitlines() if line.strip()]
        return json.loads(lines[-1])["time"]
    except (OSError, IndexError, KeyError, TypeError, ValueError):
        return state.get("created") or "unknown"


def plural(count: int, noun: str) -> str:
    return f"{count} {noun}{'' if count == 1 else 's'}"


def summary_line(folder: str, tree: str) -> str:
    """Return one line on the lead state in `folder` of worktree `tree`, for the lookup."""
    try:
        state = load(folder)
        owner = state.get("owner") or "no owner"
        open_tasks = sum(task["state"] not in (CLOSED_OUT, SETTLED) for task in state["tasks"])
        return (f"- {folder}: slug {state['slug']}, owner {owner}, last change {last_change(folder, state)}, "
                f"{plural(open_tasks, 'open task')}, {plural(len(state['items']), 'waiting item')}. "
                f"Worktree: {tree}")
    except (OSError, ValueError, KeyError, TypeError, AttributeError, Refused) as error:
        return f"- {folder}: cannot read the lead state ({error!r}). Worktree: {tree}"


def other_lead_lines(top: str) -> list[str]:
    """Return one line for each lead state in the other worktrees of the repository, read-only.

    A folder outside every Git work tree has no other worktree. Raise OSError when Git cannot list the
    worktrees.
    """
    if outside_work_trees(top):
        return []
    lines = []
    here = os.path.realpath(top)
    for tree in worktree_tops(top):
        if os.path.realpath(tree) == here:
            continue
        folders = lead_folders(tree)
        if len(folders) > 1:
            lines.append(f"- More than one lead state in {os.path.join(tree, '.scratch')}: "
                         f"{', '.join(folders)}. Worktree: {tree}")
        elif folders:
            lines.append(summary_line(folders[0], tree))
    return lines


def load(folder: str) -> dict:
    with open(os.path.join(folder, STATE_FILE), encoding="utf-8") as handle:
        state = json.load(handle)
    if state.get("schema") != SCHEMA:
        raise Refused(f"unknown lead state schema in {folder}")
    return state


def save(folder: str, state: dict) -> None:
    descriptor, temporary = tempfile.mkstemp(dir=folder, prefix=".state.", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=1)
            handle.write("\n")
        os.replace(temporary, os.path.join(folder, STATE_FILE))
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temporary)
        raise


def append_event(folder: str, event: dict) -> None:
    with open(os.path.join(folder, EVENTS_FILE), "a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")


@contextlib.contextmanager
def locked(folder: str):
    import fcntl

    with open(os.path.join(folder, LOCK_FILE), "a", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


# Checks of input.

def current_thread() -> str:
    """Return the T3 thread ID of this session, or an empty string."""
    return os.environ.get(THREAD_VARIABLE, "").strip()


def require_thread(command: str) -> str:
    thread = current_thread()
    if not thread:
        raise Refused(f"{command} needs {THREAD_VARIABLE}, the ID of the T3 Code thread; run it in the "
                      "lead's T3 Code thread")
    return thread


def check_owner(state: dict) -> None:
    """Refuse a change unless this thread owns the lead state."""
    owner, thread = state.get("owner"), current_thread()
    if owner and thread == owner:
        return
    who = f"thread {thread}" if thread else f"a session without {THREAD_VARIABLE}"
    owned = f"its owner is thread {owner}" if owner else "it has no owner, because an older script made it"
    raise Refused(f"{who} cannot change this lead state: {owned}. To move the lead to this thread, run "
                  f"takeover. {RECOVERY}")


def text(value: str, what: str) -> str:
    value = " ".join(value.split())
    if not value:
        raise Refused(f"the {what} is empty")
    if len(value) > TEXT_LIMIT:
        raise Refused(f"the {what} has {len(value)} characters; the limit is {TEXT_LIMIT}")
    return value


def link(value: str, what: str) -> str:
    if not value or len(value) > LINK_LIMIT or any(char.isspace() for char in value):
        raise Refused(f"the {what} must be one word of at most {LINK_LIMIT} characters")
    return value


def worker_link(value: str) -> str:
    return link(value, "worker link")


def worktree_path(value: str) -> str:
    """Return the worktree path of a worker, for the close-out (#556)."""
    if not os.path.isabs(value) or len(value) > LINK_LIMIT or any(char in value for char in "\n\r"):
        raise Refused(f"the worktree must be an absolute path of at most {LINK_LIMIT} characters on one line")
    return value


def find_task(state: dict, name: str) -> dict:
    for task in state["tasks"]:
        if task["name"] == name:
            return task
    raise Refused(f"no task named {name}")


def accepted(task: dict) -> bool:
    """Return whether the lead accepted the task's result; a cancelled task never counts."""
    return task["state"] in ACCEPTED and not task.get("cancelled")


def require(task: dict, states: tuple[str, ...], action: str) -> None:
    if task["state"] not in states:
        raise Refused(f"{task['name']} is {task['state']}; {action} needs {' or '.join(states)}")


# Batches.

def batch_tasks(state: dict, batch: int) -> list[dict]:
    return [task for task in state["tasks"] if task["batch"] == batch]


def merged_prs(state: dict, batch: int) -> list[dict]:
    """Return the merged PRs of a batch in merge order."""
    prs = [pr for task in batch_tasks(state, batch) for pr in task["prs"] if pr["merged"]]
    return sorted(prs, key=lambda pr: (pr["merged"], pr["number"]))


def closeout_task(state: dict, batch: int) -> dict | None:
    for task in batch_tasks(state, batch):
        if task["kind"] == "closeout" and not task.get("cancelled"):
            return task
    return None


def batch_closed(state: dict, batch: int) -> bool:
    task = closeout_task(state, batch)
    return task is not None and task["state"] in ACCEPTED


def closeout_started(state: dict, batch: int) -> bool:
    """Return whether the batch's close-out task has started, so no task may join the batch."""
    task = closeout_task(state, batch)
    return task is not None and task["state"] not in (PLANNED, PAUSED)


def batch_done(state: dict, batch: int) -> bool:
    """Return whether each task of the batch, other than a close-out, is accepted or cancelled."""
    return all(task["state"] in DONE for task in batch_tasks(state, batch) if task["kind"] != "closeout")


def needs_closeout(state: dict, batch: int) -> bool:
    return batch_done(state, batch) and bool(merged_prs(state, batch)) and closeout_task(state, batch) is None


def settle_refusal(state: dict, task: dict) -> str | None:
    """Return why the task's worker cannot be settled yet, or None when it can."""
    if task["state"] in (CLOSED_OUT, CANCELLED):
        return None
    if task["state"] != VERIFIED:
        return f"{task['name']} is {task['state']}; settle needs closed-out, cancelled, or verified"
    if task["kind"] == "closeout":
        return None
    batch = task["batch"]
    if merged_prs(state, batch):
        return (f"batch {batch} has a merged PR; settle {task['name']} after the batch's close-out "
                "task is verified")
    if not batch_done(state, batch):
        return f"batch {batch} still has open tasks; settle {task['name']} when they are verified"
    return None


# Commands that change the state.

def cmd_init(args) -> str:
    slug = args.slug
    if not SLUG.fullmatch(slug):
        raise Refused("a slug has lowercase letters, digits, and hyphens, at most 40 characters")
    owner = require_thread("init")
    top = working_tree_top()
    existing = find_lead(top)
    if existing:
        raise Refused(f"a lead state already exists here: {existing}. Start this lead in its own "
                      "T3 worktree.")
    if not args.also:
        confirm = f"Only after the user confirms a second lead state, run init {slug} --also."
        try:
            others = other_lead_lines(top)
        except OSError as error:
            raise Refused(f"could not list the worktrees, so another one may hold a lead state: {error}. "
                          f"{confirm}") from None
        if others:
            raise Refused("\n".join(["another worktree holds a lead state:", *others,
                                     f"{CONTINUE} {confirm}"]))
    time = utc_now()
    folder = os.path.join(top, ".scratch", f"{time[:10].replace('-', '')}-lead-{slug}")
    if os.path.exists(folder):
        raise Refused(f"{folder} already exists")
    os.makedirs(folder)
    with open(os.path.join(folder, ".gitignore"), "w", encoding="utf-8") as handle:
        handle.write("*\n")
    state = {"schema": SCHEMA, "slug": slug, "created": time, "owner": owner, "outcome": None,
             "criteria": None, "tasks": [], "items": [], "next_item": 1, "decisions": [], "next_decision": 1}
    save(folder, state)
    append_event(folder, {"time": time, "command": "init", "slug": slug, "owner": owner})
    return f"Lead state created: {folder}"


def cmd_takeover(args) -> str:
    thread = require_thread("takeover")
    folder = require_lead()
    with locked(folder):
        state = load(folder)
        old = state.get("owner")
        if old == thread:
            return "This thread already owns the lead state; nothing changed."
        state["owner"] = thread
        # The takeover mark: the first start of the new owner prints the takeover due line.
        state["takeover_due"] = True
        time = utc_now()
        save(folder, state)
        append_event(folder, {"time": time, "command": "takeover", "old_owner": old, "owner": thread})
    return f"Lead state taken over: owner {thread}, was {old or 'none'}. Run start."


def change_outcome(state, args, time):
    state["outcome"] = text(args.text, "outcome")
    return "Outcome set.", {"text": state["outcome"]}


def change_criteria(state, args, time):
    state["criteria"] = text(args.text, "criteria")
    return "Criteria set.", {"text": state["criteria"]}


def change_task_add(state, args, time):
    name = args.name
    if not NAME.fullmatch(name):
        raise Refused("a task name has lowercase letters, digits, and hyphens, at most 24 characters")
    if any(task["name"] == name for task in state["tasks"]):
        raise Refused(f"a task named {name} already exists")
    title = text(args.title, "title")
    highest = max((task["batch"] for task in state["tasks"]), default=1)
    if args.batch is not None:
        batch = args.batch
    elif closeout_started(state, highest) or (args.kind == "work" and merged_prs(state, highest)):
        # A batch stops growing when its first PR merges (#560), so its close-out waits only for the
        # tasks that it had then. Check and close-out tasks keep the highest batch.
        batch = highest + 1
    else:
        batch = highest
    if not 1 <= batch <= highest + 1:
        raise Refused(f"the batch must be from 1 to {highest + 1}")
    if closeout_started(state, batch):
        raise Refused(f"the close-out of batch {batch} has started; use --batch {highest + 1}")
    if args.kind == "check":
        if not args.of:
            raise Refused("a check task needs --of <task>")
        find_task(state, args.of)
    elif args.of:
        raise Refused("only a check task takes --of")
    if args.kind == "closeout" and closeout_task(state, batch):
        raise Refused(f"batch {batch} already has a close-out task")
    for other in args.after:
        find_task(state, other)
    if any(issue < 1 for issue in args.issue):
        raise Refused("an issue number is positive")
    task = {"name": name, "title": title, "kind": args.kind, "of": args.of, "batch": batch,
            "after": list(dict.fromkeys(args.after)), "issues": list(dict.fromkeys(args.issue)),
            "scientific": args.scientific, "state": PLANNED, "worker": None, "branch": None,
            "worktrees": [], "started": None, "prs": [], "changed": time}
    state["tasks"].append(task)
    return f"Task {name} added to batch {batch}.", {"task": name, "to": PLANNED, "batch": batch,
                                                     "kind": args.kind}


def move(task: dict, new: str, time: str, **fields) -> dict:
    event = {"task": task["name"], "from": task["state"], "to": new, **fields}
    task["state"] = new
    task["changed"] = time
    return event


def start_refusal(state: dict, task: dict) -> str | None:
    """Return why a planned task cannot start yet, or None when it can start now."""
    waiting = [other for other in task["after"] if not accepted(find_task(state, other))]
    if waiting:
        return f"{task['name']} waits for {', '.join(waiting)} to be verified"
    if task["kind"] == "closeout":
        batch = task["batch"]
        if not batch_done(state, batch):
            return f"batch {batch} still has tasks that are not verified or cancelled"
        if not merged_prs(state, batch):
            return f"batch {batch} has no merged PR, so it needs no close-out"
    return None


def ready_lines(state: dict) -> list[str]:
    """Name each planned task that can start now, with the step that starts it.

    No task waits for its batch (#493). A close-out task needs the close-out brief, so its line
    names the closeout step.
    """
    lines = []
    for task in state["tasks"]:
        if task["state"] == PLANNED and start_refusal(state, task) is None:
            step = "closeout" if task["kind"] == "closeout" else "dispatch"
            lines.append(f"{task['name']} is ready to start: run t3_project_lead.py {step} for it now.")
    return lines


def change_task_start(state, args, time):
    task = find_task(state, args.name)
    require(task, (PLANNED,), "task start")
    reason = start_refusal(state, task)
    if reason:
        raise Refused(reason)
    task["worker"] = worker_link(args.worker)
    task["branch"] = link(args.branch, "branch") if args.branch else None
    worktree = worktree_path(args.worktree) if args.worktree else None
    task["worktrees"] = [worktree] if worktree else []
    task["started"] = time
    event = move(task, RUNNING, time, worker=task["worker"], branch=task["branch"], worktree=worktree)
    return f"{task['name']} is running.", event


def change_task_worker(state, args, time):
    task = find_task(state, args.name)
    require(task, ACTIVE, "task worker")
    worktree = worktree_path(args.worktree) if args.worktree else None
    old, task["worker"] = task["worker"], worker_link(args.worker)
    # The replaced worker's path stays: the close-out reads its sessions too (#556).
    paths = task.get("worktrees") or []
    task["worktrees"] = paths + [worktree] if worktree and worktree not in paths else paths
    event = {"task": task["name"], "from": task["state"], "to": task["state"], "old_worker": old,
             "worker": task["worker"], "worktree": worktree}
    return f"{task['name']} has a new worker. Settle the replaced worker now: {old}", event


def change_task_pr(state, args, time):
    task = find_task(state, args.name)
    require(task, ACTIVE + (MERGED,), "task pr")
    if args.number < 1 or any(pr["number"] == args.number for pr in task["prs"]):
        raise Refused(f"PR #{args.number} is not a new positive PR number for {task['name']}")
    task["prs"].append({"number": args.number, "commit": None, "merged": None})
    return f"{task['name']}: PR #{args.number} is open.", move(task, PR_OPEN, time, pr=args.number)


def change_task_merged(state, args, time):
    task = find_task(state, args.name)
    require(task, (PR_OPEN,), "task merged")
    pr = next((pr for pr in task["prs"] if pr["number"] == args.number), None)
    if pr is None or pr["merged"]:
        raise Refused(f"PR #{args.number} is not an open PR of {task['name']}")
    if not COMMIT.fullmatch(args.commit):
        raise Refused("a commit is 7 to 40 lowercase hexadecimal characters")
    pr["commit"], pr["merged"] = args.commit, time
    new = MERGED if all(item["merged"] for item in task["prs"]) else PR_OPEN
    event = move(task, new, time, pr=args.number, commit=args.commit)
    return f"{task['name']}: PR #{args.number} merged; the task is {new}.", event


def change_task_verified(state, args, time):
    task = find_task(state, args.name)
    if task["state"] == PR_OPEN:
        raise Refused(f"{task['name']} has an open PR; verify it after task merged")
    if task["state"] == RUNNING and task["prs"]:
        raise Refused(f"{task['name']} has a PR that is not merged")
    require(task, (RUNNING, MERGED), "task verified")
    event = move(task, VERIFIED, time, decisions=args.decisions)
    message = f"{task['name']} is verified."
    if task["kind"] == "closeout":
        closed = [other for other in batch_tasks(state, task["batch"])
                  if other["state"] == VERIFIED and other["kind"] != "closeout"]
        for other in closed:
            other["state"], other["changed"] = CLOSED_OUT, time
        event["closed_out"] = [other["name"] for other in closed]
        message += f" Batch {task['batch']} is closed out: {', '.join(event['closed_out']) or 'no task'}."
    if args.decisions:
        # The report's numbered decisions wait on the user until the lead runs done (#567).
        item = add_item(state, time, task=task, decisions=args.decisions)
        event["item"] = item["number"]
        message += f" Item {item['number']} added: {item_text(item)}"
    return message, event


def check_decisions(args) -> None:
    """Refuse a task verified without a count of the report's decisions, or with one count for several
    tasks (#567). The script cannot read a report, so the lead gives the count."""
    if args.decisions is None:
        raise Refused("task verified needs --decisions N: the number of decisions that its report numbers "
                      "for the user, or 0")
    if args.decisions < 0:
        raise Refused("the number of decisions is 0 or more")
    if args.decisions and len(set(args.name)) > 1:
        raise Refused("a count above 0 takes one task name: verify each task with decisions by itself")


def change_task_settled(state, args, time):
    task = find_task(state, args.name)
    reason = settle_refusal(state, task)
    if reason:
        raise Refused(reason)
    return f"{task['name']} is settled.", move(task, SETTLED, time)


def change_task_cancel(state, args, time):
    task = find_task(state, args.name)
    require(task, (PLANNED, PAUSED) + ACTIVE, "task cancel")
    task["cancelled"] = True
    if task["worker"] is None:
        return (f"{task['name']} is cancelled. It has no worker: run task settled {task['name']}.",
                move(task, CANCELLED, time))
    return f"{task['name']} is cancelled. Settle its worker.", move(task, CANCELLED, time)


def change_task_pause(state, args, time):
    task = find_task(state, args.name)
    require(task, (PLANNED,), "task pause")
    return f"{task['name']} is paused.", move(task, PAUSED, time)


def change_task_resume(state, args, time):
    task = find_task(state, args.name)
    require(task, (PAUSED,), "task resume")
    return f"{task['name']} is planned again.", move(task, PLANNED, time)


def change_wait(state, args, time):
    task = find_task(state, args.task) if args.task else None
    if task is not None:
        if args.text is not None or args.recommend or args.link:
            raise Refused("a worker item takes only --decisions: it holds no detail of the "
                          "worker's decisions, and it points to the worker's thread")
        if not task["worker"]:
            raise Refused(f"{task['name']} has no worker; add the item without --task")
    if args.text is None and task is None:
        raise Refused("give the item's text, or --task for a worker that waits")
    if args.decisions is not None and args.decisions < 1:
        raise Refused("the number of decisions is positive")
    item = add_item(state, time, body=text(args.text, "item text") if args.text is not None else None,
                    task=task, decisions=args.decisions,
                    item_link=link(args.link, "link") if args.link else None,
                    recommend=text(args.recommend, "recommendation") if args.recommend else None)
    return f"Item {item['number']} added: {item_text(item)}", {"item": item["number"], "to": "open",
                                                              "task": item["task"]}


def add_item(state: dict, time: str, body: str | None = None, task: dict | None = None,
             decisions: int | None = None, item_link: str | None = None, recommend: str | None = None) -> dict:
    """Add a waiting item. A worker item points to the worker's thread.

    An item for a task that is verified, closed out, cancelled, or settled holds decisions of the
    worker's final report (#567): no due line offers done for it, because only the user ends it.
    """
    if body is None:
        body = f"{decisions} decision{'s' if decisions > 1 else ''}" if decisions else "waits on you"
    item = {"number": state["next_item"], "text": body, "task": task["name"] if task else None,
            "link": item_link or (task["worker"] if task else None), "decisions": decisions,
            "recommend": recommend, "opened": time}
    if task is not None and task["state"] in DONE:
        item["report"] = True
    state["items"].append(item)
    state["next_item"] += 1
    return item


def change_done(state, args, time):
    for item in state["items"]:
        if item["number"] == args.number:
            state["items"].remove(item)
            return f"Item {args.number} is done.", {"item": args.number, "to": "done"}
    raise Refused(f"no waiting item {args.number}")


def change_decision_add(state, args, time):
    decision = {"id": f"D{state['next_decision']}", "text": text(args.text, "decision"), "added": time}
    state["decisions"].append(decision)
    state["next_decision"] += 1
    return f"Decision {decision['id']} added.", {"decision": decision["id"], "to": "added"}


def change_decision_drop(state, args, time):
    for decision in state["decisions"]:
        if decision["id"] == args.id:
            state["decisions"].remove(decision)
            return f"Decision {args.id} dropped.", {"decision": args.id, "to": "dropped"}
    raise Refused(f"no decision {args.id}")


def run_change(args) -> str:
    """Make the change for each argument, then save once; a refusal of one argument saves nothing."""
    folder = require_lead()
    if args.label == "task verified":
        check_decisions(args)
    key = SEVERAL.get(args.label)
    calls = ([argparse.Namespace(**{**vars(args), key: value}) for value in dict.fromkeys(getattr(args, key))]
             if key else [args])
    with locked(folder):
        state = load(folder)
        check_owner(state)
        time = utc_now()
        results = [args.change(state, call, time) for call in calls]
        messages = [message for message, _ in results]
        if args.label == "task verified":
            messages += ready_lines(state)
        save(folder, state)
        for _, event in results:
            append_event(folder, {"time": time, "command": args.label, **event})
    return " ".join(messages)


def require_lead() -> str:
    top = working_tree_top()
    folder = find_lead(top)
    if folder is not None:
        return folder
    try:
        others = other_lead_lines(top)
    except OSError as error:
        raise Refused(f"no lead state in this working tree; the worktrees could not be listed: "
                      f"{error}") from None
    if others:
        raise Refused("\n".join(["no lead state in this working tree. Lead states in other worktrees of this "
                                 "repository:", *others, CONTINUE]))
    raise Refused("no lead state in this working tree; run init <slug> first")


def cmd_finish(args) -> str:
    folder = require_lead()
    with locked(folder):
        state = load(folder)
        check_owner(state)
        open_tasks = [task["name"] for task in state["tasks"] if task["state"] != SETTLED]
        if open_tasks or state["items"]:
            items = [str(item["number"]) for item in state["items"]]
            raise Refused(f"not finished: tasks not settled: {', '.join(open_tasks) or 'none'}; "
                          f"items that wait: {', '.join(items) or 'none'}")
    shutil.rmtree(folder)
    return f"Lead state deleted: {folder}. Settle this thread."


# Views.

def with_period(value: str) -> str:
    """Return the text with a period added, unless it already ends in ".", "?", or "!"."""
    return value if value.endswith((".", "?", "!")) else value + "."


def item_text(item: dict) -> str:
    """Return a waiting item without its number."""
    line = (f"[{item['task']}] " if item["task"] else "") + with_period(item["text"])
    if item["decisions"] and not item["text"].endswith(("decision", "decisions")):
        line += f" Decisions: {item['decisions']}."
    if item["recommend"]:
        line += f" Lead recommends: {with_period(item['recommend'])}"
    if item["link"]:
        line += f" {item['link']}"
    return line


def waiting_lines(state: dict) -> list[str]:
    """Return the waiting list. Each item is a bullet that keeps its number as text (#534): a
    Markdown renderer renumbers a numbered list from its first number."""
    items = state["items"]
    if not items:
        return ["Waiting on you: nothing."]
    return [f"Waiting on you ({len(items)}):"] + [f"- {item['number']}: {item_text(item)}" for item in items]


def task_line(task: dict, now: datetime.datetime) -> str:
    kind = "" if task["kind"] == "work" else f", {task['kind']}"
    of = f" of {task['of']}" if task["of"] else ""
    line = f"- {task['name']} (batch {task['batch']}{kind}{of}) {task['state']}"
    if task["state"] in ACTIVE and task["started"]:
        minutes = int((now - parse_time(task["started"])).total_seconds() // 60)
        line += f", {minutes} min"
    line += f": {with_period(task['title'])}"
    if task["scientific"]:
        line += " Scientific."
    if task["issues"]:
        line += " Issues: " + " ".join(f"#{issue}" for issue in task["issues"]) + "."
    if task["after"]:
        line += f" After: {', '.join(task['after'])}."
    if task["prs"]:
        line += " PRs: " + ", ".join(f"#{pr['number']} {'merged' if pr['merged'] else 'open'}"
                                     for pr in task["prs"]) + "."
    if task["branch"]:
        line += f" Branch: {task['branch']}."
    if task["worker"] and task["state"] != SETTLED:
        line += f" Worker: {task['worker']}"
    return line


def due_lines(state: dict) -> list[str]:
    # Only the owner can act on the takeover due line.
    lines = [TAKEOVER_LINE] if state.get("takeover_due") and current_thread() == state.get("owner") else []
    if not state["outcome"]:
        # A wake after the discovery worker reports leads to the discover step, not to verify; after
        # the report, only the user starts the work (#545).
        if any(task["name"] == DISCOVERY_TASK and accepted(task) for task in state["tasks"]):
            lines.append("No outcome yet, and discover is verified: start no second discovery. Wait until "
                         "the user names the work.")
        else:
            lines.append("No outcome yet: run t3_project_lead.py discover.")
    for batch in sorted({task["batch"] for task in state["tasks"]}):
        if needs_closeout(state, batch):
            prs = " ".join(f"#{pr['number']}" for pr in merged_prs(state, batch))
            lines.append(f"Batch {batch}: every task is verified; merged PRs {prs}. Run "
                         "t3_project_lead.py closeout.")
    lines += ready_lines(state)
    # One line for all paused tasks, so that the view does not grow with them (#555).
    paused = [task["name"] for task in state["tasks"] if task["state"] == PAUSED]
    if paused:
        lines.append(f"Paused: {', '.join(paused)}. Run task resume <name>... to plan them again, or task "
                     "cancel <name>.")
    for task in state["tasks"]:
        if task["state"] == SETTLED:
            continue
        if task["state"] in (VERIFIED, CLOSED_OUT, CANCELLED) and settle_refusal(state, task) is None:
            if task["worker"]:
                lines.append(f"Settle the worker of {task['name']}, then run task settled "
                             f"{task['name']}: {task['worker']}")
            else:
                lines.append(f"{task['name']} has no worker: run task settled {task['name']}.")
        if task["kind"] == "check" and task["state"] in ACCEPTED:
            target = find_task(state, task["of"])
            if target["state"] not in DONE:
                lines.append(f"Check {task['name']} is verified: run task verified {target['name']} "
                             "when its verdict passes.")
    tasks = {task["name"]: task for task in state["tasks"]}
    for item in state["items"]:
        task = tasks.get(item["task"])
        if task is not None and task["state"] in DONE and not item.get("report"):
            lines.append(f"Item {item['number']}: task {task['name']} is {task['state']}. Run done "
                         f"{item['number']}, or keep it.")
    # A lead state without an outcome has not started its work: a settled discovery task is not the end.
    if (state["outcome"] and state["tasks"] and not state["items"]
            and all(task["state"] == SETTLED for task in state["tasks"])):
        # The report step holds the rule for each decision that only the user can make (#567).
        lines.append("Every task is settled and nothing waits. Add each decision that only the user can make "
                     "with wait, as t3_project_lead.py report says; then run t3_project_lead.py finish.")
    return lines


def header_lines(state: dict, folder: str, time: str) -> list[str]:
    """Return the lines that each view prints before its tasks."""
    owner = state.get("owner") or None
    lines = [f"Lead state: {state['slug']}, {folder}", f"Owner: {owner or 'none'}"]
    if current_thread() != owner:
        lines.append("This thread is not the owner: it can read the lead state but not change it. To move "
                     "the lead to this thread, run takeover.")
    return lines + [f"Now: {time}", f"Outcome: {state['outcome'] or '(none)'}",
                    f"Criteria: {state['criteria'] or '(none)'}"]


def end_lines(state: dict) -> list[str]:
    """Return the due lines and the waiting list, which each view prints last."""
    due = due_lines(state)
    lines = ["Due:", *(f"- {line}" for line in due)] if due else []
    # The empty line ends the list above, so that Markdown does not join the waiting list to it.
    return lines + [""] + waiting_lines(state)


def view_lines(state: dict, folder: str) -> list[str]:
    """Return the full view that `show` prints: every task that is not closed out or settled, and
    every decision."""
    time = utc_now()
    now = parse_time(time)
    lines = header_lines(state, folder, time) + ["Tasks:"]
    shown = [task for task in state["tasks"] if task["state"] not in (CLOSED_OUT, SETTLED)]
    lines += [task_line(task, now) for task in shown] or ["- (none)"]
    closed = sum(task["state"] == CLOSED_OUT for task in state["tasks"])
    if closed:
        lines.append(f"Closed out, worker not settled: {closed} task{'s' if closed > 1 else ''}.")
    lines.append("Decisions:")
    lines += [f"- {decision['id']} {decision['text']}" for decision in state["decisions"]] or ["- (none)"]
    return lines + end_lines(state)


def compact_lines(state: dict, folder: str) -> list[str]:
    """Return the compact view that `start` prints (#555): the running and pr-open tasks, and one
    line that counts the other tasks by state and the decisions, so that it does not grow with
    them."""
    time = utc_now()
    now = parse_time(time)
    lines = header_lines(state, folder, time) + ["Running and pr-open tasks:"]
    lines += [task_line(task, now) for task in state["tasks"] if task["state"] in ACTIVE] or ["- (none)"]
    others = [task["state"] for task in state["tasks"] if task["state"] not in ACTIVE]
    counts = ", ".join(f"{others.count(name)} {name}" for name in OTHER_STATES if name in others)
    lines.append(f"Other tasks: {counts or 'none'}. Decisions: {len(state['decisions'])}. Run show to list "
                 "them.")
    return lines + end_lines(state)


def closeout_lines(state: dict, folder: str) -> list[str]:
    lines = []
    for batch in sorted({task["batch"] for task in state["tasks"]}):
        closeout = closeout_task(state, batch)
        if not merged_prs(state, batch) or not batch_done(state, batch) or batch_closed(state, batch):
            continue
        workers = [task["worker"] for task in batch_tasks(state, batch)
                   if task["worker"] and task is not closeout]
        # A state from before #556 has no worktree paths.
        paths = dict.fromkeys(path for task in batch_tasks(state, batch) if task is not closeout
                              for path in task.get("worktrees") or [])
        prs = ", ".join(f"#{pr['number']}" for pr in merged_prs(state, batch))
        lines += [f"Batch {batch}:", f"Workers: {' '.join(workers) or '(none)'}",
                  f"Worktrees: {' '.join(shlex.quote(path) for path in paths) or '(none recorded)'}",
                  f"Merged PRs in merge order: {prs}"]
    if lines:
        lines.append(f"History: {os.path.join(folder, EVENTS_FILE)}")
    return lines or ["No batch needs a close-out."]


def print_step(name: str) -> None:
    print(f'Steps: "{__file__}"')
    print(STEPS[name].strip())
    if name == "discover":
        print()
        print(DISCOVERY_BRIEF)
    if name not in ("start", "report", "closeout"):
        return
    top = working_tree_top()
    folder = find_lead(top)
    if folder is None:
        if name == "start":
            print()
            print("\n".join(lookup_lines(top)))
        return
    state = load(folder)
    lines = {"start": compact_lines, "report": lambda s, f: waiting_lines(s), "closeout": closeout_lines}
    print()
    print("\n".join(lines[name](state, folder)))
    if name == "start" and state.get("takeover_due") and current_thread() == state.get("owner"):
        # The owner saw the takeover due line once; a failed write only prints it again at the next start.
        with contextlib.suppress(OSError), locked(folder):
            state = load(folder)
            if state.pop("takeover_due", None) and current_thread() == state.get("owner"):
                save(folder, state)
                append_event(folder, {"time": utc_now(), "command": "start", "shown": "takeover due line"})


def lookup_lines(top: str) -> list[str]:
    """Return what `start` prints when its own working tree holds no lead state."""
    init = (f"No lead state in {top}. On this first start, run: "
            f'python3 "{__file__}" init <slug>, with a slug that names the project or repository. '
            "Then, unless the user named the work, start the discovery task as t3_project_lead.py discover "
            "says, and come to the user only with its list of open work.")
    try:
        others = other_lead_lines(top)
    except OSError as error:
        return [f"Could not list the worktrees: {error}", init]
    if not others:
        return [init]
    return [f"No lead state in {top}. Lead states in other worktrees of this repository:", *others,
            f"{CONTINUE} Do not run init here."]


# Arguments.

CHANGES = {
    "outcome": change_outcome, "criteria": change_criteria, "wait": change_wait, "done": change_done,
}
TASK_CHANGES = {
    "add": change_task_add, "start": change_task_start, "worker": change_task_worker,
    "pr": change_task_pr, "merged": change_task_merged, "verified": change_task_verified,
    "settled": change_task_settled, "cancel": change_task_cancel, "pause": change_task_pause,
    "resume": change_task_resume,
}
DECISION_CHANGES = {"add": change_decision_add, "drop": change_decision_drop}
# The commands that take one or more arguments (#555), with the name of the argument.
SEVERAL = {"done": "number", "task pause": "name", "task resume": "name", "task verified": "name",
           "task settled": "name"}


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = root.add_subparsers(dest="command", required=True, metavar="command")
    for name in STEPS:
        commands.add_parser(name, help=f"print the {name} step")
    init = commands.add_parser("init", help="create the lead state")
    init.add_argument("slug")
    init.add_argument("--also", action="store_true",
                      help="create it while another worktree holds a lead state, after the user confirms")
    commands.add_parser("show", help="print the lead state")
    commands.add_parser("waiting", help="print what waits on the user")
    commands.add_parser("finish", help="delete the lead state when the project is done")
    commands.add_parser("takeover", help="make this T3 thread the owner of the lead state")
    for name in ("outcome", "criteria"):
        commands.add_parser(name, help=f"set the {name}").add_argument("text")
    wait = commands.add_parser("wait", help="add an item that waits on the user")
    wait.add_argument("text", nargs="?")
    wait.add_argument("--task")
    wait.add_argument("--decisions", type=int)
    wait.add_argument("--link")
    wait.add_argument("--recommend")
    commands.add_parser("done", help="remove answered items").add_argument("number", type=int, nargs="+")

    task = commands.add_parser("task", help="change a task").add_subparsers(
        dest="action", required=True, metavar="action")
    add = task.add_parser("add")
    add.add_argument("name")
    add.add_argument("title")
    add.add_argument("--batch", type=int)
    add.add_argument("--after", action="append", default=[])
    add.add_argument("--kind", choices=KINDS, default="work")
    add.add_argument("--of")
    add.add_argument("--issue", type=int, action="append", default=[])
    add.add_argument("--scientific", action="store_true")
    start = task.add_parser("start")
    start.add_argument("name")
    start.add_argument("worker")
    start.add_argument("--branch")
    start.add_argument("--worktree")
    worker = task.add_parser("worker")
    worker.add_argument("name")
    worker.add_argument("worker")
    worker.add_argument("--worktree")
    pr = task.add_parser("pr")
    pr.add_argument("name")
    pr.add_argument("number", type=int)
    merged = task.add_parser("merged")
    merged.add_argument("name")
    merged.add_argument("number", type=int)
    merged.add_argument("commit")
    for name in ("verified", "settled", "pause", "resume"):
        task.add_parser(name).add_argument("name", nargs="+")
    task.choices["verified"].add_argument("--decisions", type=int,
                                          help="the number of decisions that the report numbers for the user")
    task.add_parser("cancel").add_argument("name")

    decision = commands.add_parser("decision", help="add or drop a decision").add_subparsers(
        dest="action", required=True, metavar="action")
    decision.add_parser("add").add_argument("text")
    decision.add_parser("drop").add_argument("id")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command in STEPS:
            print_step(args.command)
            return 0
        if args.command == "init":
            print(cmd_init(args))
        elif args.command == "finish":
            print(cmd_finish(args))
        elif args.command == "takeover":
            print(cmd_takeover(args))
        elif args.command in ("show", "waiting"):
            folder = require_lead()
            state = load(folder)
            print("\n".join(view_lines(state, folder) if args.command == "show" else waiting_lines(state)))
        else:
            if args.command == "task":
                args.change, args.label = TASK_CHANGES[args.action], f"task {args.action}"
            elif args.command == "decision":
                args.change, args.label = DECISION_CHANGES[args.action], f"decision {args.action}"
            else:
                args.change, args.label = CHANGES[args.command], args.command
            print(run_change(args))
    except Refused as refused:
        print(f"t3_project_lead: {refused}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
