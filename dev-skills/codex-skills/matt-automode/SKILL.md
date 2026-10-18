---
name: matt-automode
description: Run the Matt planning-to-merge workflow with explicit code review and a navigation retrospective when the user delegates a task fully to the agent without human checkpoints.
---

# Matt Automode

Use for tasks the user trusts the agent to complete autonomously. The user's
request to use this mode delegates design decisions, issue publication,
implementation, code review, a navigation retrospective, PR creation, merge,
issue closure, and repository cleanup within the task scope.

## Resolve skills in Codex

The user's request to use this mode explicitly invokes every skill this file
names. Load and follow each one without a separate user invocation. Do not ask
the user to invoke them.

- If a skill appears in the available skills list, open its `SKILL.md`.
- Resolve every other skill this file names with one command. These can be
  user-invoked skills: their `agents/openai.yaml` sets
  `policy.allow_implicit_invocation: false`, so Codex omits them from the
  list. This policy does not restrict an explicit invocation or reading the
  skill file. `<plugin-root>` is the root of this `dev-skills` plugin, two
  levels above this skill folder. For example:

  ```bash
  python3 "<plugin-root>/scripts/resolve_skill.py" --host codex \
    mattpocock-skills:grill-with-docs mattpocock-skills:to-spec \
    mattpocock-skills:to-tickets mattpocock-skills:implement \
    mattpocock-skills:retro
  ```

  Each output line gives a skill name and the path of its `SKILL.md`. Read
  each `SKILL.md` and every file it references, then follow it. Resolve each
  skill that it names in the same way.
- If the command reports an error for a skill, its message names the
  cause: the Codex config is missing, or the plugin is not enabled, is not
  installed, or does not contain the skill. Report the cause as a blocker
  and stop.

## Organize the work

Before planning, use `dev-skills:step-workflow` to organize the working folder.
Treat this mode as a request for step-based organization. Apply the skill
throughout the task to planning files, scripts, outputs, tests, and documentation
where repository layout and naming conventions permit.

## Replace human checkpoints

Autonomy replaces the human decision-maker. It does not remove the
investigation, questioning, challenge, or phase order of the referenced skills.
Do not end the turn to wait for input. Treat "check with the user", "quiz the
user", "confirm the seams", and "ask for the fixed point" as decisions to make.
Make each decision only after the investigation and challenge below, and record
it in the numbered planning files. Continue between phases without routine
approval requests. Use sub-agents where a referenced skill calls for them; keep
orchestration in this session.

### Investigate before deciding

Inspect the relevant implementation, public interfaces, tests, canonical docs,
glossary, and ADRs. Read relevant issues, comments, and merged PRs to recover the
latest decisions and their rationale. Check for superseding decisions. Resolve
conflicts between historical documents and current behavior explicitly; neither
age nor current code alone proves the intended behavior. When the resolution
replaces a recorded decision, such as an ADR, record the new decision through
`grill-with-docs`. Mark the old record as superseded and link it to the new
one; do not delete it.

In the numbered planning files, separate verified facts, design decisions,
assumptions, and unresolved questions. Cite source paths, symbols, tests, or
issue and PR links for consequential factual claims.

Use parallel sub-agents for independent read-only investigations. A pending
finding that can change a design decision is an unsettled prerequisite. Continue
independent research and planning, but wait for that finding before resolving the
affected question or passing gate 1.

### Grill in rounds

Use `mattpocock-skills:grill-with-docs` to build the design tree. Work its
frontier in rounds: each round takes every question whose prerequisites are
settled. For each question, investigate the relevant repository context before
settling the answer. Trace affected behavior and consumers through
implementation, interfaces, and tests. Resolve factual gaps that could change
the answer. Record the evidence, alternatives, recommended answer, challenge,
rationale, and any unresolved items.

Treat a recommended answer as a candidate, not a decision. This includes the
grilling skill's recommendation and any answer in an existing file that this
run has not tested. Test the candidate against source evidence, constraints,
alternatives, failure cases, compatibility, and affected consumers. Change it
when that test changes its basis. For a design-critical question, first run
the pressure test below. Then record the tested answer as the decision,
recompute the frontier, and continue the next round. When evidence changes an
earlier answer, reopen its dependent questions.

If the available evidence cannot settle a design-critical question, choose the
answer that the evidence supports best. When two or more answers have about
equal support, choose the one that is easiest to reverse. Record the evidence
gap, the alternatives, and the risk with the decision. Make this choice
yourself; do not stop for human input. The pressure test below reviews it
as the current answer.

Grilling is complete when all design-critical questions are resolved and all
research that could change those decisions has returned and been evaluated.
Record any remaining nonblocking assumptions and why they are safe. A
recommended answer does not replace repository investigation or grilling
rounds. A generic checklist or a brief assumptions list does not satisfy this
gate.

### Pressure-test each grilling round

Classify each question of a grilling round before you resolve it. A question
is **design-critical** when both conditions hold:

- It has two or more viable answers. An answer is viable when the evidence
  does not rule it out.
- The choice is hard to reverse, or it changes behavior, a public interface,
  a consumer, or a recorded decision.

Record each question's classification and its reason in the planning files.
A question that the facts settle with one viable answer needs no pressure
test.

When a grilling round has design-critical questions, run one new pressure
test over them before you record their decisions. Open the
[pressure-test skill](../pressure-test/SKILL.md) and follow it. Direct its
session record and conclusion into the numbered planning folder. In its
pressure-test packet, give each design-critical question an ID, its OPTIONS
with their evidence, and the recommended answer as its current answer. Add
the round's other questions and their classifications to the evidence, so
that the critic can dispute a classification. Handle a dispute like any
other objection: concede it and add the question with an ID, or rebut it
with evidence. A grilling round with no design-critical question runs no
pressure test.

Resolve each design-critical question from the coverage table of the
conclusion. Apply the first rule that matches:

1. If the critic did not assess the current answer, the question carries
   into the pressure test of the next grilling round, and its dependent
   questions wait. An answer revised after its last assessment counts as
   not assessed. When only carried questions remain, they form the next
   grilling round.
2. If the ID is converged, as the pressure-test session record defines the
   term, the question resolves with its current answer.
3. Otherwise, the critic still objects to the assessed answer. Choose the
   answer that the evidence and the objections support best, and break a
   near tie as the evidence-gap rule in "Grill in rounds" does. If you keep
   the assessed answer, the question resolves with it; record the
   unresolved objections with the decision. If you choose another answer,
   the question carries under rule 1 with the new answer.

When later evidence changes the basis of a design-critical decision, reopen
the decision. A reopened decision carries as a revised answer, even when its
answer stays the same. After gate 1, a reopened decision is invalid under
"Phase gates" until it resolves again under these rules. The reopened gate 1
resumes the grilling rounds.

A critic failure does not stop the run. Two results are critic failures. One
is a pressure test with no usable assessment: none of its IDs is reviewed,
as the pressure-test session record defines the term. A reviewed ID counts
even when a later revision made its assessment stale. The other is a
question whose current answer is not assessed at the end of two pressure
tests in a row that include it. A revision does not reset this count; a
reopened decision starts a new one.

A critic failure overrides the carry in rule 1. Resolve each affected
question without the critic: decide it with the challenge in "Grill in
rounds", and break a near tie as the evidence-gap rule does. Record with the
decision that the critic did not assess it, and the ending condition of the
pressure test. Then continue: its dependent questions proceed, and each
later grilling round runs its own pressure test. List these decisions in the
final report.

At the start of step 1, run only the Setup and Preflight steps of
pressure-test as an early check. This check is not a pressure test: it
writes no conclusion, and a failed preflight does not stop step 1. Record
the result and any diagnosis in the planning
files. Each later pressure test runs its own preflight. A successful
preflight is not a review: only the critic's assessment of a question's
current answer counts.

The spec states each pressure-tested decision with its evidence, objection
dispositions, unresolved risks, and ending condition. The record of a
decision that the critic did not assess says so. A ticket or ADR that
records such a decision states the same record. Each record stands alone
and cites no planning file.

Other decisions that this mode makes in place of a human keep the challenge
in "Grill in rounds" without a pressure test: the testing seams, the ticket
breakdown, the code-review fixed point, and the retro fix selection.

## Phases

Run steps 4–7 for each ticket in dependency order. Run cleanup after all tickets
are merged.

1. `mattpocock-skills:grill-with-docs`: pressure-test the design-critical
   questions, resolve the design questions, and record the domain terms and
   decisions.
2. `mattpocock-skills:to-spec`: choose the testing seams and publish the spec.
3. `mattpocock-skills:to-tickets`: choose the ticket breakdown and publish it
   with blocking dependencies. Track the parent spec, all task tickets, and their
   PRs through completion. Preserve the parent during ticket publication.
4. `mattpocock-skills:implement`: complete the next ready ticket. Follow its
   testing workflow and commit the changes for review.
5. `mattpocock-skills:code-review`: review the changes against a fixed comparison
   commit and the ticket spec. This phase fulfills `implement`'s code-review
   requirement. Fix actionable Standards and Spec findings before continuing.
6. `mattpocock-skills:retro`: run after code review, including successful
   implementations. Use this prompt:

   > use retro skill read previous implementation sessions and find ways to make my repo easier to navigate. Find where agents take too long to find relevant information, or rely on out-of-date docs.
   > Improving navigability is such an underrated way to save tokens and update docs.

   Select this repository's implementation sessions, including worktrees, by
   recorded workspace or repository metadata before searching their text. Use
   task prompts and actions to judge relevance. Report the sessions read,
   navigation findings, and any unavailable history. If previous sessions are
   unavailable, report that limit and review the current implementation session.
   Apply in-scope navigation and documentation fixes, run affected checks, and
   commit those edits. Run `code-review` again against the same comparison
   commit and verify that its diff includes those edits before the PR phase.
   Report other candidates as follow-up work.
7. `mattpocock-skills:pr`: write the PR body and open the PR for the reviewed
   changes. Merge after required checks and review pass. Follow repository rules.
8. `dev-skills:repo-cleanup`: run after all tickets are merged. Pass the
   tracked tickets, parent spec, and merged PRs so cleanup can reconcile issue
   state and verify closure alongside Git cleanup.

## Phase gates

Each step has a start condition and a completion check. Gate N is the
completion check of step N. Before each transition, record the completion check
in the numbered planning files. Include the gate status, evidence references,
remaining work, and the next permitted action. Keep the checks in execution
order. Existing artifacts can satisfy a gate only after their content and
current validity have been checked.

| Step | Start only when | Complete when |
| --- | --- | --- |
| 1. Investigation and grilling | The working folder is organized. | Evidence supports the resolved decisions. No design-critical question or research result that could change a decision remains open. The grilling record is in the numbered planning files, with each question's classification and its reason. Each design-critical question resolved under "Pressure-test each grilling round": its current answer converged, the decision records the critic's unresolved objections, or the decision records that the critic did not assess it. `grill-with-docs` has recorded the domain terms and decisions. |
| 2. Spec | Gate 1 passed. | The spec is published with scope and testing seams derived from the resolved decisions. Its reference is recorded and its content verified. |
| 3. Tickets | Gate 2 passed. | Tickets are published with blocking dependencies and acceptance criteria. Their references are recorded, and their coverage of the spec is verified. |
| 4. Implement | Gates 1–3 passed, and the PR of every ticket that blocks this ticket is merged. | The ticket's tests pass under `implement`'s testing workflow, and the changes are committed for review. |
| 5. Code review | Gate 4 passed for this ticket. | The review ran against a recorded comparison commit and the ticket spec. Fixes for actionable Standards and Spec findings are committed, and the tests pass after the fixes. |
| 6. Retro | Gate 5 passed for this ticket. | The sessions read, navigation findings, and history limits are recorded. If retro made in-scope fixes, they are committed, their affected checks pass, a second `code-review` against the first review's comparison commit includes them in its diff, and fixes for its actionable findings are committed. The affected checks pass after the last fix. |
| 7. PR | Gate 6 passed for this ticket. | The PR is open with its issue references, the required checks and required reviews pass, and the PR is merged. Its link is recorded. |
| 8. Cleanup | Gate 7 passed for every ticket. | Cleanup reported its results. The tickets and any fully satisfied parent spec are verified closed. |

Steps 4–7 are the implementation of one ticket. Implementation includes
assigning coding work to a sub-agent and fixing review or retro findings. Keep
coding and coding delegation for a ticket blocked until the step 4 start
condition holds for that ticket. Read-only investigation and planning can run in
parallel before then.

In step 7, wait for running checks and reviews without ending the turn. Use a
blocking watch command, such as `gh pr checks <number> --watch` on GitHub, or
check again at intervals. Fix a failed check on the PR branch and commit the
fix. When the fix changes code, run `code-review` again against the same
comparison commit before the merge. A required review that the agent cannot
give, such as a human approval under branch protection, is an enforced
restriction. Do not wait for it, approve your own PR, or bypass the protection.
Continue the tickets that do not depend on that PR, then report the blocker
with the PR link and keep the work.

If later evidence invalidates a decision, stop dependent work, including active
coding sub-agents. Dependent work is any ticket, code, or decision that relies
on the invalid decision. Reopen the planning gate where that decision was made
and the gates after it. Update decisions, the published spec, and tickets as
needed. Record new completion checks before resuming dependent work, and run
each affected ticket through steps 4–7 again. For a ticket that is already
merged, publish a new ticket for the change. A reopened gate blocks only
dependent work. For a ticket that does not rely on the invalid decision, gates
1–3 still count as passed, whether or not the ticket has started.

## Report progress accurately

Distinguish completed phases from pending or blocked work. Report each gate's
status with its supporting evidence. Artifact existence alone does not prove
completion or correct phase order. If implementation started early, report the
ordering failure, stop dependent work, including coding sub-agents, and
complete the missing gates before resuming. Treat code written early as
unreviewed: check it against the decisions, spec, and ticket, and run its
ticket through steps 4–7. Later publication cannot make the earlier execution
compliant.

Distinguish instruction and scenario checks from demonstrated agent behavior.
Report what was actually observed and any validation limits.

## PR issue references

In each GitHub PR description, use a separate `Closes #123` reference for each
ticket the PR fully resolves. Use `Closes owner/repo#123` for another repository.
Use ordinary references for partial work. Closing keywords take effect when the
PR targets the default branch; carry them to the final integration PR for stacked
work. Follow the configured tracker's equivalent closure mechanism elsewhere.
Do not close a ticket by hand before the PR that resolves it merges. Do not
close the parent spec before the PR of every ticket merges. After a merge,
close by hand only a ticket that its closing keyword did not close.

## Finish

Finish when all tickets have completed implementation, code review, retro, and
PR merge, all tickets and any fully satisfied parent spec are verified
closed, and cleanup has reported its results. Report review results, retro
findings and session-history limits, issue and PR links, and any issue left open
with its remaining work.
If progress is blocked by missing access, an enforced restriction, or
repeated failures with no viable next step, report the blocker and retain the
work. This mode does not bypass tool permissions or repository protections.
