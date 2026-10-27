# Matt Automode scenario review

> Superseded in part on 2026-10-27 by
> [issue #354](https://github.com/aeghnnsw/cc-toolkit/issues/354). The dated review
> records below describe earlier instructions. Their pressure-test defaults,
> early preflight, waiting rules, and retro process may differ from the current
> [Claude Code skill](../skills/matt-automode/SKILL.md) and
> [Codex skill](../codex-skills/matt-automode/SKILL.md). Keep those records as
> history; they do not validate the revised expectations below.

These cases cover [issue #241](https://github.com/aeghnnsw/cc-toolkit/issues/241)
and, from case 17, [issue #302](https://github.com/aeghnnsw/cc-toolkit/issues/302).
[Issue #305](https://github.com/aeghnnsw/cc-toolkit/issues/305) changed the
results when the critic cannot assess an answer and added cases 23–25.
Issue #354 changes the defaults and adds cases 26–33.
Apply each case to the [Claude Code skill](../skills/matt-automode/SKILL.md)
and the [Codex skill](../codex-skills/matt-automode/SKILL.md).

For each case, identify the next permitted action, blocked work, and evidence
needed to pass the gate. Use a fresh review context with the skill and scenario
inputs. Keep expected results separate from the initial review prompt.

To give a reviewer the inputs alone, run this command from the repository
root. The output leaves out the task above, so state the task in the review
prompt. Tell the reviewer not to open this file.

```bash
sed -n '/^## Scenarios/,/^## Expected results/p' dev-skills/tests/matt-automode-scenarios.md | sed '$d'
```

## Scenarios

Unless a case says otherwise, the user has not opted into pressure testing.
Cases 17–25 each assume that the user explicitly requested pressure tests
during grilling for this task and has not withdrawn that choice.

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
19. **Failed preflight.** A round with design-critical questions reaches its
    pressure test. That test's preflight fails because the critic's CLI is not
    signed in. No question in the test received an assessment.
20. **Failed kickoff.** The preflight of a round's pressure test passes. The
    kickoff fails, and its retry fails.
21. **No design-critical question.** In a grilling round, the facts settle
    every question with one viable answer.
22. **Reopened decision.** Q1 converged in an earlier pressure test. New
    evidence reopens Q1, but its answer stays the same. The next pressure test
    includes Q1 and Q3. Its critic assesses Q3 but not Q1.
23. **Second miss.** Q2 carried from the previous pressure test because the
    critic did not assess it. The next pressure test includes Q2, and its
    critic again does not assess the current answer of Q2. Q4 depends on Q2.
24. **Revised twice.** The critic assessed Q5 and still objects. Under rule 3,
    the agent chooses another answer, so Q5 carries. In the next pressure
    test, the critic assesses the new answer and still objects, and the agent
    again chooses another answer.
25. **Kept after a miss.** The previous pressure test did not assess Q6, so
    Q6 carried. The next pressure test assesses the current answer of Q6, and
    the critic still objects. The agent keeps that answer under rule 3.
26. **Completed handoff.** The available conversation contains completed
    grilling and agreed decisions. No separate handoff form exists. The spec
    remains to be published.
27. **No opt-in.** An unfinished grilling round has a design-critical choice
    between two viable interfaces. The pressure-test skill is available, but
    the user has not requested it. The critic's CLI setup is unknown.
28. **Persistent opt-in.** The user requested pressure tests during grilling.
    Later in the same task, new evidence reopens a design-critical question.
    The user has not repeated or withdrawn the request.
29. **Small retro fix.** Retro finds a stale navigation link. Its local fix
    needs no new design decision or substantial scope increase. The first
    code review compared against C0.
30. **Large retro findings.** Retro finds an unrelated documentation redesign
    and a broader interface problem that makes the current change incorrect.
    An existing issue covers the redesign.
31. **Retro cutoff.** Two merged PRs have completed retro records. PR A was
    posted and merged later, but its Reviewed through timestamp is
    2026-10-25T10:00:00Z.
    PR B records 2026-10-25T11:00:00.000Z. An unmerged PR records a later cutoff.
    This run scans through 2026-10-27T14:00:00Z and posts its PR two hours later.
    A repository session started before PR B's cutoff and continued after it.
32. **No prior retro.** No merged PR has a completed retro record. Relevant
    earlier implementation sessions are available. The review finds no fix.
33. **Unavailable history.** No prior completed retro or earlier implementation
    session is available. The current session is available for review.

## Expected results

| Case | Next permitted action | Blocked work | Evidence needed |
| --- | --- | --- | --- |
| Pending research | Resolve the independent logging question and wait for the schema finding. | Settling the schema, passing gate 1, and assigning coding work. | Returned findings, evaluated alternatives, resolved design-critical questions, and a recorded completion check. |
| Conflicting decisions | Read the relevant issue, comments, PR rationale, and current interfaces and tests. Resolve whether B supersedes A. | Treating recency or current code alone as design authority; closing the affected question. | Cited rationale for the current decision, evaluated compatibility and consumers, and an explicit resolution of the conflict. |
| Early coding delegation | Report the ordering failure and stop dependent work. Validate the missing gates in sequence before resuming. | Claiming the earlier execution was compliant because artifacts now exist; continuing on unverified artifacts. | Content checks for the published spec and tickets, resolved questions, satisfied blockers, and an accurate sequence record. The early code runs through steps 4–7 as unreviewed code. |
| New evidence | Stop dependent coding, including active sub-agents. Reopen the affected planning phase and later phases. | Continuing dependent work using the invalid decision. | Updated decisions from evidence and challenge, spec and tickets as needed, and new completion checks before resumption. Pressure testing stays off. Affected tickets run through phases 4–7 again. |
| Investigated recommendation | Record the supported answer and rationale. Continue with the dependent question. | Skipping remaining questions or asking for routine human approval; treating a recommendation alone as completed grilling. | Repository evidence and challenge supporting the decision, and resolved dependent questions before phase 1 can complete. Pressure testing stays off. |
| Blocked ticket | Continue T1 through retro, PR, and merge. Read-only preparation for T2 can run. | Coding or coding delegation for T2 until T1 is merged. | T1's gate 7 record with its merged PR, and gates 1–3 still valid. |
| Open review findings | Fix the actionable findings, commit the fixes, and pass affected checks. Record phase 5 with the comparison commit. | Starting retro or opening the PR for this ticket. | Committed fixes, passing affected checks, and a review record against a recorded comparison commit and the ticket spec. |
| Unreviewed retro edits | Run `code-review` again against the original comparison commit. Verify that its diff includes the retro fix. Complete phase 6. | Opening the PR with the earlier review result. | Passing affected checks after the last edit, a second review diff with the retro fix, and the PR retro record with its Reviewed through cutoff, sessions, findings, fixes, and history limits. |
| Pending PR checks | Wait for the required checks and required reviews to pass, merge the PR, and record gate 7. | Merging before checks and reviews pass; running cleanup or closing tickets before every ticket is merged. | Passing checks and reviews and the merged PR link; then cleanup results and verified closure of the tickets and any fully satisfied parent spec. |
| Unsettled evidence | Choose option B and record the decision, evidence gap, alternatives, and risk. | Stopping for routine human input; completing phase 1 with the question still open. | The evaluated evidence for both options, their reversal costs, and the recorded rationale and risk. Pressure testing stays off. |
| Slow checks | Use the host's PR monitoring mechanism. Resume merge work when the required checks and reviews pass. | Merging before checks pass; imposing a blocking watch command regardless of host guidance. | The monitored PR, passing required checks and reviews, then the merged PR link for phase 7. |
| Required human review | Start T3 at step 4. Then report the blocker with the PR link and keep the work. | Approving the PR as the agent; bypassing branch protection; merging the PR; starting tickets that depend on it. | The PR link, the branch protection rule that requires the review, and the state of the other tickets. |
| Early closure | Leave T1 open and wait for the PR checks. Let the closing keyword close T1 at merge. | Closing T1 by hand before its PR merges. | The merged PR, then T1 closed by its keyword, or closed by hand only if the keyword did not close it. |
| Second review base | Run the second review against C0 and verify that its diff includes the retro fix. | Comparing against the gate 5 commit; opening the PR before the second review. | A second review against C0 whose diff includes the retro fix, committed fixes for its actionable findings, and passing checks. |
| Independent ticket | Start T5 at step 4. | Starting or continuing tickets that rely on the schema before new completion checks are recorded. | The record that T5 does not rely on the invalid decision, and its merged blockers. |
| Replaced ADR | Record decision B through `grill-with-docs`. Mark the old ADR as superseded and link it to decision B. | Deleting the old ADR; leaving it unmarked. | Cited rationale for B, the new decision record, and the superseded note with its link. |
| Partial coverage | Resolve Q1 from its assessment: rule 2 if it converged, or rule 3 with its unresolved objections recorded. Carry Q2–Q6 into the pressure test of the next grilling round; their dependent questions wait. | Resolving Q2–Q6 or their dependents from Q1's review; passing gate 1. | The coverage table with Q1's assessment and Q2–Q6 not assessed, the failed calls with their exit codes, and the next pressure test's assessments of Q2–Q6. A question that this test also does not assess resolves without the critic. |
| Stale assessment | Carry Q1 and any revised Q2 answer into the next pressure test; their dependent questions wait. If Q2 keeps its assessed answer, resolve it with the remaining objections recorded. | Resolving a changed answer on its earlier assessment. | The final answers, coverage table, failed calls, and fresh assessments for carried questions. |
| Failed preflight | Record this test's failed preflight and diagnosis. Resolve its questions with the evidence-based challenge in "Plan and decide" because no ID was assessed. Continue grilling. | Blocking automode or carrying these questions solely for this failure; adding a separate early preflight; skipping a later eligible round's pressure test. | The test's ending condition, diagnosis, unassessed answers and decisions, and their entry in the final report. The passed or failed preflight is not an assessment. |
| Failed kickoff | Resolve the round's design-critical questions without the critic: decide each with the challenge in "Plan and decide", and record that the critic did not assess it and why: the ending condition, and that no reply came. Continue the grilling: the dependent questions proceed, and the next grilling round with design-critical questions runs its own pressure test. | Ending the run or stopping the dependent work; carrying the questions; recording the challenge as a critic assessment; counting the passed preflight as a review. | The pressure-test conclusion with its ending condition, the failed calls with their exit codes, each decision's record that the critic did not assess it, and the list of these decisions in the final report. |
| No design-critical question | Record each question's classification, reason, and evidence. Resolve the questions without a pressure test and continue with the next grilling round. | Running a pressure test for the round; leaving a classification unrecorded. | The classification record and the evidence for each answer. |
| Reopened decision | Carry Q1 as not assessed into the pressure test of the next grilling round; its dependent questions wait. This is Q1's first miss since it was reopened, so Q1 carries. Resolve Q3 from its assessment. | Resolving Q1 on its earlier convergence; resolving Q1 without the critic now. | The coverage table with Q1 not assessed, and the next pressure test's assessment of Q1. After a second miss in a row, Q1 resolves without the critic. |
| Second miss | Resolve Q2 without the critic: decide it with the challenge in "Plan and decide", and record that the critic did not assess it and why: the ending conditions of both pressure tests, and that the critic skipped its ID. Continue: Q4 proceeds. | Carrying Q2 again; ending the run; keeping Q4 waiting. | The coverage tables of both pressure tests, the record of Q2, and its entry in the final report. |
| Revised twice | Resolve Q5 without the critic: the end of two pressure tests in a row leaves its current answer not assessed. Decide it with the challenge in "Plan and decide", and record that the critic did not assess the last answer and why: the answer changed after the last assessment. The dependent questions of Q5 proceed. | Carrying Q5 a third time; recording the last answer as assessed or converged. | Both coverage tables with the critic's objections, the two rule 3 choices, the record of Q5, and its entry in the final report. |
| Kept after a miss | Resolve Q6 under rule 3 with its current answer, and record the critic's unresolved objections with the decision. | Resolving Q6 without the critic; counting a second miss; recording that the critic did not assess Q6. | The coverage table with the critic's objection to Q6, and the decision record with its unresolved objections. |
| Completed handoff | Use the agreed decisions from the available context. Skip grilling and continue to the spec. | Repeating grilling, demanding a separate handoff form, or running a retrospective pressure test. | The completed grilling and agreed decisions already in context, then phase 2's published and verified spec. |
| No opt-in | Challenge the options against evidence, record the decision, and continue. | Loading pressure-test, checking critic setup, running preflight, or calling the critic without opt-in. | The options, evidence, decision, and rationale. No critic record is required. |
| Persistent opt-in | Keep pressure testing enabled. Run a fresh test for the reopened question before resolving it under the coverage rules. | Asking the user to opt in again; treating the prior assessment as current; silently disabling pressure tests. | The original opt-in, the reopened question, and its new coverage record. A reopened question starts a new miss count. |
| Small retro fix | Apply and commit the link fix in this PR. Pass affected checks and repeat code review against C0. | Sending the fix to a separate ticket by default; opening the PR before checks and the second review. | The reviewed diff includes the fix. The PR retro record gives the cutoff, sessions, finding, fix, and history limits. |
| Large retro findings | Reuse the redesign issue and create or reuse a separate issue for the interface problem. Link both follow-ups. Resolve the current correctness problem before merge. | Adding the unrelated redesign to this PR; blocking on that redesign; merging while the current change remains incorrect. | Follow-up issue links, each finding's effect on current correctness, and checks and review for any current-PR fix. |
| Retro cutoff | Use PR B's 11:00 UTC cutoff. Set this run's 14:00 UTC cutoff before copying sessions. Read matching repository and worktree records after the previous cutoff through this cutoff, including later records in the older session. | Using merge order, posting time, the unmerged PR, or session start time as the boundary. | Parsed timestamps or normalized millisecond timestamps; previous cutoff < record timestamp <= current cutoff. This PR records Reviewed through 2026-10-27T14:00:00Z, not its 16:00 posting time. |
| No prior retro | Review relevant earlier implementation sessions. Publish a retro record in this PR even though no fix is needed. | Requiring a central tracking issue; omitting the record because there is no prior cutoff or finding. | The scanned cutoff, sessions read, absent prior record, findings, and no-fix outcome. |
| Unavailable history | Review the current session and continue with the history limit recorded. | Claiming earlier sessions were reviewed; blocking solely because history is unavailable; omitting the PR retro record. | The Reviewed through cutoff, current session reviewed, unavailable history, findings, and any fixes or follow-ups. |

## Validation limits

Reading the instructions checks coverage. A simulated next-action review checks
how an agent interprets these cases. Neither demonstrates a full workflow in
Claude Code or Codex. Package validation checks metadata and release contracts;
it does not enforce agent behavior. Record actual review outcomes separately
from these expected results.

## Review record

### 2026-10-27

Two fresh agents read the 33 scenario inputs and one host copy each. They did
not receive the expected results. Both chose the intended next actions and
blocked work. Neither found a contradictory skill instruction. Both treated
Q2 in case 18 according to whether its answer changed; the expected result now
states that condition. No skill behavior changed after this review.

These were simulated instruction reviews. No full automode workflow ran.

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
   converged in one critic round. No scenario review ran after these changes,
   or after the code-review fixes that followed them.

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

### 2026-10-18

Rounds 7 and 8 reviewed the text for issue #305. Each round used two fresh
agents, one for each host copy. Each agent read only its skill, the
pressure-test skill, and the scenario inputs.

7. Round 7 used cases 17–23. Both reviewers chose the expected next action in
   every case, and no case stopped the run. They reported these gaps: the term
   "critic failure" also named a miss that the agent's own revision caused;
   the record gave one ending condition, but a second miss spans two pressure
   tests; "Finish" did not list the decisions that the critic did not assess;
   and "Grill in rounds" recorded a decision before the pressure-test rules
   resolved it. The text was changed to close these gaps. A pressure test of
   the changes converged after 3 critic rounds. Its two objections changed how
   a rule 3 answer counts, and cases 24 and 25 were added.
8. Round 8 used cases 17–25. Both reviewers chose the expected next action in
   every case, for both copies. They reported these gaps: "Finish" could still
   read as a stop rule for a critic that fails in every round; the reasons in
   the record left out a failed call with no reply; and a decision on an
   answer that the critic assessed would carry a false record. The text was
   changed to close these gaps. No scenario review or pressure test ran after
   these changes.

Round 8 reported these limits, left for follow-up work:

- In pressure-test, the status `error:no thread id` has no ending condition,
  and the retry rule for a failed kickoff is unclear.
- The early check writes no conclusion, although pressure-test says to always
  save one.
