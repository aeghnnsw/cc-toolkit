---
name: matt-automode
description: Run the Matt planning-to-merge workflow when the user delegates a task fully to the agent without human checkpoints.
---

# Matt Automode

Use for tasks the user trusts the agent to complete autonomously. The user's
request to use this mode delegates design decisions, issue publication,
implementation, PR creation, merge, issue closure, and repository cleanup within
the task scope.

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
   with blocking dependencies. Track the parent spec, all task tickets, and their
   PRs through completion. Preserve the parent during ticket publication.
4. `mattpocock-skills:implement`: complete every ticket in dependency order.
   Follow its testing and code-review workflow. Fix actionable findings, open
   PRs, and merge after required checks and review pass. Follow repository rules.
5. Reconcile issue state using the rules below.
6. `dev-skills:repo-cleanup`: run after the implementation is merged.

## Issue closure

In each GitHub PR description, use a separate `Closes #123` reference for each
ticket the PR fully resolves. Use `Closes owner/repo#123` for another repository.
Use ordinary references for partial work. Closing keywords take effect when the
PR targets the default branch; carry them to the final integration PR for stacked
work. Follow the configured tracker's equivalent closure mechanism elsewhere.

After each merge, verify that the ticket's acceptance criteria are met and all
required work has reached the repository's required integration branch. A merge
into an intermediate branch is not completion. Read the ticket state from the
tracker. If a completed ticket remains open, close it as completed with links to
the merged PRs, then read its state again. Keep incomplete tickets open.

After all task tickets are complete and closed, verify the full parent spec,
including any additional acceptance criteria or child tickets. Close the parent
as completed with links to the merged work, then verify its closed state. The
`to-tickets` rule to preserve the parent applies during ticket publication; this
final reconciliation closes it only when its full scope is satisfied.

Finish when all tickets are implemented, merged, and verified closed, any fully
satisfied parent spec is verified closed, and cleanup has reported its results.
Report issue and PR links, plus any issue left open and its remaining work.
If progress is blocked by missing access, an enforced restriction, or
repeated failures with no viable next step, report the blocker and retain the
work. This mode does not bypass tool permissions or repository protections.
