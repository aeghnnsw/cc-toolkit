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

## Replace human checkpoints

Autonomy replaces the human decision-maker. Keep the investigation, questioning,
challenge, and phase order of the referenced skills. Answer each grilling
question with the recommended answer after the investigation and challenge
below. This replaces the human response, not the grilling process. Continue
without routine human approval requests.

### Investigate before deciding

Inspect the relevant implementation, public interfaces, tests, canonical docs,
glossary, and ADRs. Read relevant issues, comments, and merged PRs to recover the
latest decisions and their rationale. Check for superseding decisions. Resolve
conflicts between historical documents and current behavior explicitly; neither
age nor current code alone proves the intended behavior.

In the numbered planning files, separate verified facts, design decisions,
assumptions, and unresolved questions. Cite source paths, symbols, tests, or
issue and PR links for consequential factual claims.

Use parallel sub-agents for independent read-only investigations. A pending
finding that can change a design decision is an unsettled prerequisite. Continue
independent research and planning, but wait for that finding before resolving the
affected question or passing the investigation gate.

### Grill in rounds

Use `mattpocock-skills:grill-with-docs` to build the design tree. Work its frontier
in rounds: consider only questions whose prerequisites are settled. For each
question, investigate the relevant repository context before finalizing the
recommendation. Trace affected behavior and consumers through implementation,
interfaces, and tests. Resolve factual gaps that could change the answer. Record
the evidence, alternatives, recommended answer, challenge, rationale, and any
unresolved items.

Test tentative recommendations against source evidence, constraints, failure
cases, compatibility, and affected consumers. Update the recommendation when
that investigation changes its basis. Then accept the resulting recommended
answer as the autonomous response and record it as the decision. Recompute the
frontier and continue the next grilling round. When evidence changes an earlier
answer, reopen its dependent questions.

Grilling is complete when all design-critical questions are resolved and all
research that could change those decisions has returned and been evaluated.
Record any remaining nonblocking assumptions and why they are safe. Accepting
recommended answers does not replace repository investigation or grilling
rounds. A generic checklist or a brief assumptions list does not satisfy this
gate.

## Phase gates

Before each transition, record a completion check in the planning files. Include
the gate status, evidence references, remaining work, and the next permitted
action. Keep the checks in execution order. Existing artifacts can satisfy a
gate only after their content and current validity have been checked.

| Phase | Required completion check |
| --- | --- |
| 1. Investigation and grilling | Evidence supports the resolved decisions. No design-critical question or consequential research result remains open. Record domain terms and decisions through `grill-with-docs`. |
| 2. Spec | Use `mattpocock-skills:to-spec`. Publish scope and testing seams derived from the resolved decisions. Record the published spec reference and verify its content. |
| 3. Tickets | Use `mattpocock-skills:to-tickets`. Publish tickets with dependencies and acceptance criteria. Record their references and verify coverage of the spec. Track the parent spec, tickets, and PRs through completion. Preserve the parent during ticket publication. |
| 4. Implementation | Before starting each ticket, verify gates 1–3 and that ticket's blockers are satisfied. Use `mattpocock-skills:implement` and its testing and code-review workflow. Fix actionable findings. Open PRs and merge only after required checks and review pass. Follow repository rules. |
| 5. Cleanup | After implementation is merged, use `dev-skills:repo-cleanup`. Pass the tracked tickets, parent spec, and merged PRs for issue reconciliation and Git cleanup. |

Implementation includes assigning coding work to a sub-agent. Keep coding and
coding delegation blocked until gates 1–3 pass and the ticket's blockers are
satisfied. Read-only investigation and planning can run in parallel before then.
Keep orchestration in this session.

If later evidence invalidates a decision, pause dependent implementation,
including active coding sub-agents. Reopen the affected planning gate and its
downstream gates. Update decisions, the published spec, and tickets as needed.
Record new completion checks before resuming dependent work.

## Report progress accurately

Distinguish completed phases from pending or blocked work. Report each gate's
status with its supporting evidence. Artifact existence alone does not prove
completion or correct phase order. If implementation started early, report the
ordering failure, pause dependent work, and complete the missing gates before
resuming. Later publication cannot make the earlier execution compliant.

Distinguish instruction and scenario checks from demonstrated agent behavior.
Report what was actually observed and any validation limits.

## PR issue references

In each GitHub PR description, use a separate `Closes #123` reference for each
ticket the PR fully resolves. Use `Closes owner/repo#123` for another repository.
Use ordinary references for partial work. Closing keywords take effect when the
PR targets the default branch; carry them to the final integration PR for stacked
work. Follow the configured tracker's equivalent closure mechanism elsewhere.

Finish when all tickets are implemented, merged, and verified closed, any fully
satisfied parent spec is verified closed, and cleanup has reported its results.
Report issue and PR links, plus any issue left open and its remaining work.
If progress is blocked by missing access, an enforced restriction, or
repeated failures with no viable next step, report the blocker and retain the
work. This mode does not bypass tool permissions or repository protections.
