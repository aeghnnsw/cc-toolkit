---
name: matt-automode
description: Run the Matt planning-to-merge workflow when the user delegates a task fully to the agent without human checkpoints.
---

# Matt Automode

Use for tasks the user trusts the agent to complete autonomously. The user's
request to use this mode delegates design decisions, issue publication,
implementation, PR creation, merge, and repository cleanup within the task scope.

Find the skills below in the available skills list or installed plugin skill
files. Read and follow each SKILL.md and its required references. Resolve skills
by plugin and name; do not hard-code installation paths or versions. If a required
skill is missing, report the blocker and stop.

Before planning, use `dev-skills:step-workflow` to organize the working folder.
Treat this mode as a request for step-based organization. Apply the skill
throughout the task to planning files, scripts, outputs, tests, and documentation
where repository layout and naming conventions permit.

Replace the referenced skills' human interview and approval checkpoints with
agent decisions. Research facts, choose suitable answers, and record assumptions
and decisions in the planning artifacts. Continue between phases without asking
for input or approval.

1. `mattpocock-skills:grill-with-docs`: resolve the design questions and record
   the domain terms and decisions.
2. `mattpocock-skills:to-spec`: choose the testing seams and publish the spec.
3. `mattpocock-skills:to-tickets`: choose the ticket breakdown and publish it
   with blocking dependencies.
4. `mattpocock-skills:implement`: complete every ticket in dependency order.
   Follow its testing and code-review workflow. Fix actionable findings, open
   PRs, and merge after required checks and review pass. Follow repository rules.
5. `dev-skills:repo-cleanup`: run after the implementation is merged.

Finish when all tickets are implemented and merged and cleanup has reported its
results. If progress is blocked by missing access, an enforced restriction, or
repeated failures with no viable next step, report the blocker and retain the
work. This mode does not bypass tool permissions or repository protections.
