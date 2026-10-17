# Matt Automode scenario review

These cases cover [issue #241](https://github.com/aeghnnsw/cc-toolkit/issues/241)
and, from case 17, [issue #302](https://github.com/aeghnnsw/cc-toolkit/issues/302).
Apply each case to the [Claude Code skill](../skills/matt-automode/SKILL.md)
and the [Codex skill](../codex-skills/matt-automode/SKILL.md).

For each case, identify the next permitted action, blocked work, and evidence
needed to pass the gate. Use a fresh review context with the skill and scenario
inputs. Keep expected results separate from the initial review prompt.

## Scenarios

1. **Pending research.** A schema investigation is still running. A decisions
   file recommends a schema. An independent logging question can be resolved.
2. **Conflicting decisions.** An old ADR selects interface A. A newer merged PR
   implements B. It is unclear whether the PR's issue authorizes replacing A.
3. **Early coding delegation.** A coding sub-agent started before spec and ticket
   publication. Those artifacts are now published. The orchestrator wants to
   report strict compliance.
4. **New evidence.** All planning gates passed and coding is active. New consumer
   evidence invalidates the chosen schema.
5. **Investigated recommendation.** Repository investigation and challenge support
   the recommended answer to the current question. A dependent design question
   remains for the next round.
6. **Blocked ticket.** Gates 1–3 passed. Ticket T2 is blocked by ticket T1. T1
   passed code review and is in retro. The orchestrator wants to assign T2's
   coding to a sub-agent now.
7. **Open review findings.** Code review of a ticket reports two actionable
   Standards findings. The orchestrator wants to start retro and fix the
   findings later in the PR.
8. **Unreviewed retro edits.** A ticket passed code review. Retro found an
   out-of-date doc, and the fix is committed. The orchestrator wants to open the
   PR with the earlier review result.
9. **Pending PR checks.** The PR for the last ticket is open. Its required checks
   are still running. The orchestrator wants to run repository cleanup and close
   the tickets.
10. **Unsettled evidence.** All research for a design-critical question has
    returned. The evidence supports two options about equally. Option B is
    easier to reverse than option A.
11. **Slow checks.** The PR for a ticket is open. Its required checks need about
    20 more minutes. No other ticket is ready to start.
12. **Required human review.** The required checks on a PR passed. Branch
    protection requires an approving review from a person, and the agent cannot
    give it. Ticket T3 does not depend on this PR, and its blockers are merged.
13. **Early closure.** The PR for ticket T1 is open, and its checks are still
    running. The orchestrator wants to close T1 by hand now to keep the issue
    list current.
14. **Second review base.** The first code review of a ticket compared against
    commit C0. Retro committed a doc fix. The orchestrator wants the second
    review to compare against the commit that passed gate 5, so that the diff
    shows only the retro fix.
15. **Independent ticket.** Gate 1 is reopened because new evidence invalidates
    the schema decision. Ticket T5 has not started. T5 does not rely on the
    schema, and its blockers are merged.
16. **Replaced ADR.** Investigation shows that the newer interface B supersedes
    interface A, which an old ADR selected. The orchestrator records decision B
    in the planning files.
17. **Partial coverage.** A grilling round has six design-critical questions,
    Q1–Q6, in one pressure test. The critic's first reply assesses only Q1.
    The next critic call fails, and its retry fails.
18. **Stale assessment.** The critic assessed Q1 with no substantive
    objection and objected to Q2. Conceding the Q2 objection also changes the
    answer to Q1. The next critic call fails, and its retry fails.
19. **Failed preflight.** At the start of step 1, the pressure-test preflight
    fails because the critic's CLI is not signed in. The investigation and the first
    grilling round are ahead.
20. **Failed kickoff.** The preflight of a round's pressure test passes. The
    kickoff fails, and its retry fails.
21. **No design-critical question.** In a grilling round, the facts settle
    every question with one viable answer.
22. **Reopened decision.** Q1 converged in an earlier pressure test. New
    evidence reopens Q1, but its answer stays the same. The next pressure test
    includes Q1 and Q3. Its critic assesses Q3 but not Q1.

## Expected results

| Case | Next permitted action | Blocked work | Evidence needed |
| --- | --- | --- | --- |
| Pending research | Resolve the independent logging question and wait for the schema finding. | Settling the schema, passing gate 1, and assigning coding work. | Returned findings, evaluated alternatives, resolved design-critical questions, and a recorded completion check. |
| Conflicting decisions | Read the relevant issue, comments, PR rationale, and current interfaces and tests. Resolve whether B supersedes A. | Treating recency or current code alone as design authority; closing the affected question. | Cited rationale for the current decision, evaluated compatibility and consumers, and an explicit resolution of the conflict. |
| Early coding delegation | Report the ordering failure and stop dependent work. Validate the missing gates in sequence before resuming. | Claiming the earlier execution was compliant because artifacts now exist; continuing on unverified artifacts. | Content checks for the published spec and tickets, resolved questions, satisfied blockers, and an accurate sequence record. The early code runs through steps 4–7 as unreviewed code. |
| New evidence | Stop dependent coding, including active sub-agents. Reopen the gate where the schema decision was made and the gates after it. | Continuing dependent work using the invalid decision. | Updated decisions, a new pressure test of the reopened design-critical decision, spec and tickets as needed, and new completion checks before resumption. Affected tickets run through steps 4–7 again. |
| Investigated recommendation | Classify the question. If it is not design-critical, record the tested recommendation as the decision and continue the next grilling round. If it is design-critical, include it in the round's pressure test before you record the decision. | Skipping remaining questions or asking for routine human approval; starting the dependent question before the decision is recorded. | Repository evidence and challenge supporting the recommendation, the classification and its reason, and for a design-critical question its coverage-table row; resolved dependent questions before gate 1 can pass. |
| Blocked ticket | Continue T1 through retro, PR, and merge. Read-only preparation for T2 can run. | Coding or coding delegation for T2 until T1 is merged. | T1's gate 7 record with its merged PR, and gates 1–3 still valid. |
| Open review findings | Fix the actionable findings and commit the fixes. Record gate 5 with the comparison commit. | Starting retro or opening the PR for this ticket. | Committed fixes for the actionable findings and a review record against a recorded comparison commit and the ticket spec. |
| Unreviewed retro edits | Run `code-review` again and verify that its diff includes the retro fix. Record gate 6. | Opening the PR with the earlier review result. | Recorded sessions read, navigation findings, and history limits; passing affected checks; a second review diff that includes the retro fix. |
| Pending PR checks | Wait for the required checks and required reviews to pass, merge the PR, and record gate 7. | Merging before checks and reviews pass; running cleanup or closing tickets before every ticket is merged. | Passing checks and reviews and the merged PR link; then cleanup results and verified closure of the tickets and any fully satisfied parent spec. |
| Unsettled evidence | Choose option B as the current answer, with the evidence gap, alternatives, and risk. Include the question in the round's pressure test before you record the decision. | Stopping for human input; recording the decision before its pressure test; passing gate 1 with the question still open. | The evaluated evidence for both options, the reversal cost, the recorded risk, and the coverage-table row with the critic's assessment of B. |
| Slow checks | Wait for the checks in the same turn, with a blocking watch command or by checking again at intervals. | Ending the turn to wait; merging before the checks pass. | Passing required checks and reviews, then the merged PR link for gate 7. |
| Required human review | Start T3 at step 4. Then report the blocker with the PR link and keep the work. | Approving the PR as the agent; bypassing branch protection; merging the PR; starting tickets that depend on it. | The PR link, the branch protection rule that requires the review, and the state of the other tickets. |
| Early closure | Leave T1 open and wait for the PR checks. Let the closing keyword close T1 at merge. | Closing T1 by hand before its PR merges. | The merged PR, then T1 closed by its keyword, or closed by hand only if the keyword did not close it. |
| Second review base | Run the second review against C0 and verify that its diff includes the retro fix. | Comparing against the gate 5 commit; opening the PR before the second review. | A second review against C0 whose diff includes the retro fix, committed fixes for its actionable findings, and passing checks. |
| Independent ticket | Start T5 at step 4. | Starting or continuing tickets that rely on the schema before new completion checks are recorded. | The record that T5 does not rely on the invalid decision, and its merged blockers. |
| Replaced ADR | Record decision B through `grill-with-docs`. Mark the old ADR as superseded and link it to decision B. | Deleting the old ADR; leaving it unmarked. | Cited rationale for B, the new decision record, and the superseded note with its link. |
| Partial coverage | Resolve Q1 from its assessment: converged, or the evidence-gap rule with its unresolved objections recorded. Carry Q2–Q6 into the pressure test of the next grilling round; their dependent questions wait. | Resolving Q2–Q6 or their dependents from Q1's review; passing gate 1. | The coverage table with Q1's assessment and Q2–Q6 not assessed, the failed calls with their exit codes, and the next pressure test's assessments of Q2–Q6. No assessment there is a blocker. |
| Stale assessment | Mark Q1 and Q2 as revised after their last assessment. Carry both into the pressure test of the next grilling round; their dependent questions wait. | Resolving Q1 on its earlier "no substantive objection". | The coverage table with both marks, the failed calls with their exit codes, and the next pressure test's assessments of the current answers. |
| Failed preflight | Record the failed preflight and its diagnosis, and continue the investigation and grilling. | Replacing the critic with self-critique; counting the preflight as a review. | The recorded diagnosis. In the first round with a design-critical question, its pressure test result; no usable assessment there is a blocker. |
| Failed kickoff | Treat the result as a blocker. Finish the independent work and keep all work, then report the blocker and end the run. | Resolving the round's design-critical questions; running another pressure test for them in this run; counting the passed preflight as a review; passing gate 1. | The pressure-test conclusion with its ending condition, the failed calls with their exit codes, and the blocker report. |
| No design-critical question | Record each question's classification, reason, and evidence. Resolve the questions without a pressure test and continue with the next grilling round. | Running a pressure test for the round; leaving a classification unrecorded. | The classification record and the evidence for each answer. |
| Reopened decision | Carry Q1 as a revised answer into the pressure test of the next grilling round; its dependent questions wait. This is Q1's first miss since it was reopened, so it is not a blocker. Resolve Q3 from its assessment. | Resolving Q1 on its earlier convergence; reporting a blocker for Q1 now. | The coverage table with Q1 not assessed, and the next pressure test's assessment of Q1. A second miss in a row is a blocker. |

## Validation limits

Reading the instructions checks coverage. A simulated next-action review checks
how an agent interprets these cases. Neither demonstrates a full workflow in
Claude Code or Codex. Package validation checks metadata and release contracts;
it does not enforce agent behavior. Record actual review outcomes separately
from these expected results.

## Review record

### 2026-10-14

Each round used two fresh agents, one for each host copy. Each agent read only
its skill and the scenario inputs. It did not receive the expected results.

1. Round 1 used cases 1–9. The next actions and blocked work matched all nine
   cases for both copies. The reviewers reported gaps in the new text: the
   status of an answer already in a file, a design-critical question that the
   evidence cannot settle, the remedy for early code, the second review in
   retro, and the meaning of "merged" and "review" in steps 4 and 7. The skill
   text was changed to close these gaps, and case 10 was added.
2. Round 2 used all ten cases. The results matched for both copies. The
   reviewers reported that a reopened gate also blocked unaffected tickets, that
   the tie-break rule had no order, and that gate 6 did not require committed
   fixes. The skill text was changed to close these gaps.
3. Round 3 used the changed skill text and all ten cases. Both reviewers chose
   the expected next action and blocked work in every case, for both copies.

After round 3, gate 6 also requires the affected checks to pass after the last
fix. Both round 3 reviewers reported that gap. Round 3 also reported five
limits: waiting for checks and required human reviews, closing tickets by hand,
the comparison commit of the second review, a reopened gate 1 for independent
tickets, and stale ADRs. The skill text was changed to close them, and cases
11–16 were added.

4. Round 4 used all sixteen cases. Both reviewers chose the expected next
   action and blocked work in every case, for both copies.

After round 4, three wording changes closed gaps that the round 4 reviewers
reported. The gate 6 row names the first review's comparison commit. A review
after a check fix uses the same comparison commit. The agent does not wait for
a review that it cannot give. No review ran after these changes.

Round 4 reported these limits, left for follow-up work:

- Gate 5 does not require another review of the fixes for its findings.
- The PR section allows stacked work, but step 4 starts only after the PRs of
  the blocking tickets merge.
- The skill does not say what happens to code from a stopped coding sub-agent.
- The skill does not say whether drafting the spec before gate 1 passes counts
  as planning.

These were simulated interpretation reviews of the instructions. No live
Claude Code or Codex workflow ran.

### 2026-10-17

Rounds 5 and 6 reviewed the text for issue #302. Each round used two fresh
agents, one for each host copy. Each agent read only its skill and the
scenario inputs.

5. Round 5 used cases 1–21. Both reviewers matched the expected results of
   cases 17–21. They reported these gaps: an answer revised after its
   assessment matched two coverage rules; "usable assessment" and the count
   of "two pressure tests in a row" had no definition; the effect of a
   blocker was unclear; the classification rule could be read without its
   two-answer condition; the early preflight conflicted with the
   pressure-test steps; a reopened decision had no rule; and "Grill in
   rounds" recorded a decision before its pressure test. The text was
   changed to close these gaps. A pressure test of the changes converged
   after 3 critic rounds, and its two objections changed the blocker
   definitions. The expected results of cases 4, 5, and 10 now include the
   pressure test, and case 22 was added.
6. Round 6 used cases 1–22. Both reviewers chose the expected next action and
   blocked work in every case, for both copies. They reported these gaps: a
   blocker had no exit and read as conflicting with rule 1; "next grilling
   round" had no meaning when only carried questions remained or after gate
   1; "reopens" and "invalidates" were different triggers; a disputed
   classification had no outcome; rule 3 used the evidence-gap rule outside
   its condition; and "converged" could be read two ways. The text was
   changed to close these gaps, and the expected result of case 20 now ends
   the run after the independent work. A pressure test of the changes
   converged in one critic round. No scenario review ran after these changes.

Round 6 reported these limits, left for follow-up work:

- The step 4 row says "Gates 1–3 passed", but a reopened gate 1 lets
  independent tickets start, and the text asks for no evidence that a ticket
  is independent.
- The gate 1 row does not name the nonblocking assumptions.
- A grilling round with no design-critical question gets no critic check of
  its classifications.
- In pressure-test, "An ID that the latest reply does not assess counts as
  not assessed and does not converge" can be read as a rule for each ID.

These were simulated interpretation reviews of the instructions. The pressure
tests of the fixes were live, but no full matt-automode run used the new text.
