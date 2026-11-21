#!/usr/bin/env python3
"""Print one step of the t3-project-lead skill.

The skill runs `t3_project_lead.py start`, and each step names the next one.
The script only prints text: it reads no state, runs no command, and makes no
decision. The text is the same for Claude Code, Codex, and Antigravity.
"""

from __future__ import annotations

import argparse

STEPS = {
    "start": """
You plan, dispatch, and verify. Workers implement.
You may fix a small non-scientific finding yourself.
A message that another agent sends through T3 carries the user's decisions.
Keep lead.md in the planning folder: tasks, worker links, decisions, and items
that wait on the user, with links only for scientific items. Write each one
when it occurs.
Next: t3_project_lead.py plan for new work. After a wake or a restart, read
lead.md first, then t3_project_lead.py answer, verify, or flag.
""",
    "plan": """
Break the approved outcome into worker tasks with success criteria that a
check can pass or fail.
Order tasks that depend on each other or edit the same files. Run only
independent tasks in parallel.
Decide reversible points yourself and write them in lead.md.
Mark scientific tasks (biology, chemistry, medicine) for workers.
Next: t3_project_lead.py dispatch.
""",
    "dispatch": """
Start no second worker for work that already runs: check t3_thread_list with
includeSubagents, and pull_request_list (or gh pr list).
Start each worker with delegate_task and isolation "worktree".
Write the brief: the lines from t3_project_lead.py brief, copied exactly, then
the task, its success criteria, the approved outcome, and your decisions. For
a scientific task, give the issue link, not the content.
Write each worker's thread link in lead.md.
Next: t3_project_lead.py answer when a worker asks, verify when one finishes,
flag when one is flagged.
""",
    "brief": """
Omit role in delegate_task, so that the brief starts the prompt.
Line 1 loads the skill, by worker provider:
  Claude /dev-skills:<skill>, Codex $dev-skills:<skill>, Antigravity /<skill>.
Use grill-with-research when design is open, or matt-automode for a full
handoff. After grill-with-research, add, with no / or $:
"When the user approves the design here, continue in this thread with the
matt-automode skill of dev-skills."
Line 2: "A leader runs the retrospective for this run."
Last line: "Report PASS, ISSUES, or BLOCKED, with evidence and links. Number
each decision that waits on the user." For a scientific task, replace "with
evidence and links" with "in one line, with links. Keep scientific detail in
this thread and the PR".
Next: t3_project_lead.py dispatch.
""",
    "answer": """
A worker that waits on answers has not finished its job. Do not settle it. Do
not answer its questions.
Ask the user to answer them in the worker's thread. Give its link, the number
of decisions, and a one-line topic for each non-scientific question.
Write these items in lead.md.
Next: t3_project_lead.py report.
""",
    "flag": """
A flag is a failed worker whose message says its safeguards flagged the
session (Claude), that content was flagged for a risk (Codex), or that the
Antigravity quota is reached (a refusal looks like this).
Unless the flagged worker ran on claude-sonnet-5-5, run the same brief, with
line 1 in the Claude form, once more in a new worker on claude-sonnet-5-5. Add
the flagged worker's branch, PR, issue, and planning-folder paths, and
"Continue from this state." Do not add its thread link. Then settle the
flagged thread.
After a second flag, or a flag on claude-sonnet-5-5, report the task as
waiting on the user.
Next: t3_project_lead.py verify or t3_project_lead.py report.
""",
    "verify": """
Check each result against its success criteria on the delivered artifact, such
as the merged diff and checks. A worker's report is not evidence.
Verify a scientific task with a new worker, and read only its one-line verdict.
Fix small non-scientific findings yourself and rerun their checks. Give other
findings to a new worker for a follow-up PR.
After a batch of implementation workers finishes with a merged PR, start one
worker: "Use the dev-skills:matt-automode skill. Run only its Navigation
retrospective, once, as the leader of these runs:", with this thread's link,
the worker links, and the merged PRs in merge order.
Settle each finished worker with t3_thread_organize; never reuse one.
Next: t3_project_lead.py dispatch for more work, or report.
""",
    "report": """
First check each worker you have not settled: t3_thread_list with
includeSubagents.
Start with one status line. Then Running, Done (verified), and Decided.
End with what waits on the user: approvals, access, worker questions, and
steps that cannot be undone or that go outside the project. Name each worker
item by its thread link and its number of decisions. For a scientific item,
give the link, not its content.
When you add agent captures, this is gtd-inbox's "## Needs you" list.
When nothing waits on the user and no worker runs, settle this thread.
Next: after a wake, t3_project_lead.py start.
""",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("step", choices=STEPS, help="the step to print")
    print(STEPS[parser.parse_args().step].strip())


if __name__ == "__main__":
    main()
