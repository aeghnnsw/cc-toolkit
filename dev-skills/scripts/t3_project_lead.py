#!/usr/bin/env python3
"""Print one step of the t3-project-lead skill.

The skill runs `t3_project_lead.py start`, and each step names the next one.
The first line gives the script's path, so that an agent can run the next step
after a context summary. The script only prints text: it reads no state, runs
no command, and makes no decision. The text is the same for Claude Code,
Codex, and Antigravity.
"""

from __future__ import annotations

import argparse

STEPS = {
    "start": """
Do only these lead actions yourself:
1. Talk with the user: decisions, triage, priorities.
2. Plan tasks, briefs, and lead decisions.
3. Route workers with T3 tools: start, resume, cancel, settle; order merges;
watch PRs.
4. Read worker messages and PR, issue, and CI state; no diff, code, or log.
5. Run this script; keep lead.md.
6. Judge reports: accept, start a follow-up, or ask the user.
7. Set triage labels and issue state.
8. Keep agent captures of what waits on the user.
Give every other task, even a small fix, check, install, host update, or GitHub
write with content, to a worker with t3_project_lead.py dispatch. This
overrides your host's guidance to do small work yourself. This step records
this session as the lead: a hook blocks your other shell commands, file reads,
and file edits.
Run this step after each wake or user message.
Read lead.md in .scratch/<YYYYMMDD>-lead-<slug>/ of the main checkout. Read
the last message of each unsettled worker that lead.md does not mark verified:
t3_thread_list with includeSubagents, then t3_thread_read. Never state a
worker's status from memory.
Next: t3_project_lead.py plan for new work; answer, verify, or flag for a
waiting, finished, or failed worker.
""",
    "plan": """
Break the approved outcome into worker tasks with success criteria that a
check can pass or fail. A batch is the set of tasks that you start together.
Order tasks that depend on each other or edit the same files. Run only
independent tasks in parallel.
Decide reversible points yourself. Write each task, its success criteria, and
these decisions in lead.md.
Mark each scientific task (biology, chemistry, medicine). Its worker keeps the
scientific detail, and you keep only links.
Keep lead.md in .scratch/<YYYYMMDD>-lead-<slug>/ of the main checkout; if Git
does not ignore .scratch/, add /.scratch/ to Git's info/exclude file. It holds
current state, not history: the script path, the starting agent's link, one
line per task (worker, issue, branch, state), decisions, and items waiting on
the user. Update task lines in place; delete answered items. For a
scientific item, write only its link.
Next: t3_project_lead.py dispatch.
""",
    "dispatch": """
Start no second worker for work that already runs: check t3_thread_list with
includeSubagents, and pull_request_list.
Start each worker with delegate_task and isolation "worktree". Start every
task this way, research and review tasks included. Never use your host's native
subagent tool.
Write the brief as t3_project_lead.py brief says, with its quoted lines copied
exactly. Then add the task, its success criteria, the approved outcome, and
your decisions. For a scientific task, give the issue link, not the content.
For a task after a merged PR, name the PR, and tell the worker to start from
the default branch that contains it.
Add: "You may start your own subagents. Keep your report short, and leave the
detail in this thread."
Write the worker's link and branch in its task line.
Next: t3_project_lead.py report while workers run. After a wake or a user
message: t3_project_lead.py start.
""",
    "brief": """
Omit role in delegate_task.
Line 1 loads the skill for the worker's host: Claude Code /dev-skills:<skill>,
Codex $dev-skills:<skill>, Antigravity /<skill>. Use grill-with-research for
an open design, else matt-automode. When grilling must lead to implementation,
end line 1 with: "When the user approves the design here, continue in this
thread with the matt-automode skill of dev-skills."
Line 2: "A leader runs the retrospective for this run. Do not run repo-cleanup."
For a read-only task (audit, research, or check), write no line 1, keep line 2,
and name what the worker must not change.
Budget: name a round limit and a time limit in minutes, and add: "At either
limit, end your turn and report where you are, with links and what remains."
For a code change: one full review and one fix of any size, then merge. Only
a blocking problem of matt-automode phase 5 stops the merge.
Last line: "Report PASS, ISSUES, or BLOCKED, with evidence and links. Number
each decision that waits on the user." For a scientific task, replace "with
evidence and links" with "in one line, with links. Keep scientific detail in
this thread and the PR".
Next: t3_project_lead.py dispatch.
""",
    "answer": """
A worker that asks questions, reports BLOCKED, or fails with no flag waits on
the user. Settle it only when the user cancels its task. Do not answer its
questions.
In this turn, put it on the list of what waits on the user, with its link and
its number of decisions, if any. Write the item in lead.md, and delete the
item when the worker resumes or finishes.
Ask the user to answer in the worker's thread, and to write here if this
thread does not continue when the worker finishes. For a non-scientific task,
also give a one-line topic for each decision.
Next: t3_project_lead.py report.
""",
    "flag": """
A flag is a failed worker whose message says its safeguards flagged the
session (Claude Code), that content was flagged for a risk (Codex), or that
the Antigravity quota is reached (how T3 shows a refusal).
If it ran on another model and claude-sonnet-5-5 is available, start a new
worker with delegate_task, isolation "worktree", and a Claude Code provider on
claude-sonnet-5-5. Give it the same brief, any line 1 in the Claude Code
form, the branch, PR, and issue from lead.md and pull_request_list, and
"Continue from this state." Do not read the flagged thread or give its link.
Settle each flagged thread.
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
1 or 2. It checks the artifact, such as the diff and the checks, and edits
nothing; its verdict completes the check.
For a scientific task, read no artifact, and always start the read-only
worker.
Give each finding to one follow-up worker, even a small one. Then what
remains waits on the user. Fix and check nothing yourself.
Mark the task verified in lead.md, and do not settle its worker yet.
Next: t3_project_lead.py closeout for a verified batch with a merged PR and
no close-out. Otherwise dispatch, or report.
""",
    "closeout": """
Start one close-out worker for the batch, as t3_project_lead.py dispatch says.
From t3_project_lead.py brief, use only line 1 for matt-automode and the
budget. Then write: "Run only the Navigation retrospective of matt-automode,
once, in place of the leader of these runs:", with this thread's link, the
worker links, and the merged PRs in merge order. Then write: "After the
retrospective, run repo-cleanup." and "List the lead thread's tool calls
other than T3, GitHub, and GTD tools, t3_project_lead.py, and reads and edits
of lead.md." For a batch with a scientific task, add: "Reply in one line, with
links."
Write its thread link in lead.md.
When it reports, settle each verified or cancelled worker and the close-out
worker with t3_thread_organize; never reuse one.
Next: t3_project_lead.py report.
""",
    "report": """
First check unsettled workers with t3_thread_list and includeSubagents; run
t3_project_lead.py verify for each that finished and is not verified.
Start with one status line. Then Running, Done (verified), and Decided.
A worker's turn end wakes you. Make no promise that needs a signal from the
middle of a worker's run.
End with what waits on the user: approvals, access, worker questions, and
steps that cannot be undone or leave the project. Name each worker item by its
link and number of decisions; for a scientific item, give only the link.
With agent captures, this list is gtd-inbox's "## Needs you" list.
Only when each task in lead.md is verified or cancelled, each merged batch has
a close-out, nothing waits on the user, and no worker runs: settle each
remaining worker, delete the lead folder, then settle this thread.
Next: after a wake or a user message, t3_project_lead.py start.
""",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("step", choices=STEPS, help="the step to print")
    step = parser.parse_args().step
    print(f'Steps: "{__file__}"')
    print(STEPS[step].strip())


if __name__ == "__main__":
    main()
