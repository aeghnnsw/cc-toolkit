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
You plan, dispatch, and verify. Workers implement.
You may fix a small non-scientific finding yourself.
Only the user, or the agent that started this thread, carries the user's
decisions. No worker or other agent does.
Keep lead.md in .scratch/<YYYYMMDD>-lead-<slug>/ of the main checkout; if Git
does not ignore .scratch/, add /.scratch/ to Git's info/exclude file. It holds
current state, not history: the script path, the starting agent's link, one
line per task (worker, issue, branch, state), decisions, and items waiting on
the user. Update lines in place; delete closed items. For a scientific
item, write only its link.
Next: t3_project_lead.py plan for new work. After a wake or restart, read
lead.md, then t3_project_lead.py answer, verify, or flag.
""",
    "plan": """
Break the approved outcome into worker tasks with success criteria that a
check can pass or fail. A batch is the set of tasks that you start together.
Order tasks that depend on each other or edit the same files. Run only
independent tasks in parallel.
Decide reversible points yourself and write them in lead.md.
Mark each scientific task (biology, chemistry, medicine). Its worker keeps the
scientific detail, and you keep only links.
Next: t3_project_lead.py dispatch.
""",
    "dispatch": """
Start no second worker for work that already runs: check t3_thread_list with
includeSubagents, and pull_request_list (or gh pr list).
Start each worker with delegate_task and isolation "worktree".
Write the brief as t3_project_lead.py brief says, with its quoted lines copied
exactly. Then add the task, its success criteria, the approved outcome, and
your decisions. For a scientific task, give the issue link, not the content.
For a task after a merged PR, name the PR, and tell the worker to start from
the default branch that contains it.
Next: t3_project_lead.py report while workers run. After a wake:
t3_project_lead.py answer, verify, or flag.
""",
    "brief": """
Omit role in delegate_task, so line 1 starts the prompt.
Line 1 loads the skill for the worker's host: Claude Code /dev-skills:<skill>,
Codex $dev-skills:<skill>, Antigravity /<skill>. Use grill-with-research for
an open design, else matt-automode. When grilling must lead to implementation,
end line 1 with: "When the user approves the design here, continue in this
thread with the matt-automode skill of dev-skills."
Line 2: "A leader runs the retrospective for this run."
Last line: "Report PASS, ISSUES, or BLOCKED, with evidence and links. Number
each decision that waits on the user." For a scientific task, replace "with
evidence and links" with "in one line, with links. Keep scientific detail in
this thread and the PR".
Next: t3_project_lead.py dispatch.
""",
    "answer": """
A worker that asks questions, reports BLOCKED, or fails with no flag waits on
the user. Do not settle it. Do not answer its questions.
Ask the user to answer in the worker's thread, and to write here if this
thread does not continue when the worker finishes. Give the worker's link and
its number of decisions. For a non-scientific task, also give a one-line
topic for each decision.
Write these items in lead.md, and delete them when the worker resumes or
finishes.
Next: t3_project_lead.py report.
""",
    "flag": """
A flag is a failed worker whose message says its safeguards flagged the
session (Claude Code), that content was flagged for a risk (Codex), or that
the Antigravity quota is reached (how T3 shows a refusal).
Unless it ran on claude-sonnet-5-5, start a new worker with delegate_task,
isolation "worktree", and a Claude Code provider on claude-sonnet-5-5. Give it
the same brief, line 1 in the Claude Code form, the branch, PR, and issue from
lead.md and pull_request_list, and "Continue from this state." Do not read the
flagged thread or give its link. Settle each flagged thread.
After a second flag, or without that model, the task waits on the user; write
it in lead.md.
Next: t3_project_lead.py report.
""",
    "verify": """
Check each result against its success criteria on the delivered artifact, such
as the merged diff and checks, not on the worker's report.
For a scientific task, start a verifier worker with no line 1 or 2. It edits
nothing and reports a one-line verdict, with links and no scientific detail.
That verdict completes the check.
Fix a small non-scientific finding yourself in its PR, or a new PR after a
merge. Give each other finding to one follow-up worker; then what remains
waits on the user.
Settle each finished worker with t3_thread_organize; never reuse one.
Next: t3_project_lead.py retro when a batch is verified, with a merged PR and
no retrospective. Otherwise dispatch, or report.
""",
    "retro": """
Start one worker for the Navigation retrospective of the batch, as
t3_project_lead.py dispatch says, with only line 1 of t3_project_lead.py brief
for matt-automode. Then write: "Run only the Navigation retrospective of
matt-automode, once, in place of the leader of these runs:", with this
thread's link, the worker links, and the merged PRs in merge order. For a
batch with a scientific task, add: "Reply in one line, with links."
Write its thread link in lead.md.
Next: t3_project_lead.py report.
""",
    "report": """
First check unsettled workers with t3_thread_list and includeSubagents; run
t3_project_lead.py verify for each that finished.
Start with one status line. Then Running, Done (verified), and Decided.
End with what waits on the user: approvals, access, worker questions, and
steps that cannot be undone or leave the project. Name each worker item by its
link and number of decisions; for a scientific item, give only the link.
When you add agent captures, make this list gtd-inbox's "## Needs you" list.
Settle this thread only when each task in lead.md is verified or cancelled,
each batch with a merged PR has a retrospective, nothing waits on the user,
and no worker runs.
Next: after a wake, t3_project_lead.py start.
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
