# Matt Automode scenario review

> Superseded in part on 2026-10-27 by
> [issue #354](https://github.com/aeghnnsw/cc-toolkit/issues/354). The dated review
> records below describe earlier instructions. Their pressure-test defaults,
> early preflight, waiting rules, and retro process may differ from the current
> [Claude Code skill](../skills/matt-automode/SKILL.md) and
> [Codex skill](../codex-skills/matt-automode/SKILL.md). Keep those records as
> history; they do not validate the revised expectations below.
>
> Superseded in part on 2026-11-05 by
> [issue #358](https://github.com/aeghnnsw/cc-toolkit/issues/358): phase 1 loads
> `grill-with-research`, and Matt Automode has no pressure test. Case numbers
> in the records below refer to the earlier list.
>
> Superseded in part on 2026-11-08 by
> [issue #392](https://github.com/aeghnnsw/cc-toolkit/issues/392): the retro
> runs once after cleanup and only proposes issues. Cases 8, 14, and 18 now
> describe retro findings, cases 25 and 26 are new, and phase numbers after
> review moved down by one.

These cases cover [issue #241](https://github.com/aeghnnsw/cc-toolkit/issues/241)
and later changes from issues #302, #305, #354,
[#358](https://github.com/aeghnnsw/cc-toolkit/issues/358),
[#392](https://github.com/aeghnnsw/cc-toolkit/issues/392), and
[#388](https://github.com/aeghnnsw/cc-toolkit/issues/388). Issue #358 removes
the pressure-test cases and adds cases 23 and 24. Issue #388 adds case 27.
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
   passed code review, and its PR is open. The orchestrator wants to assign
   T2's coding to a sub-agent now.
7. **Open review findings.** Code review of a ticket reports two actionable
   Standards findings. The orchestrator wants to open the PR and fix the
   findings later.
8. **Retro edit.** All PRs of the run merged, and cleanup reported. Retro
   finds an out-of-date doc that misled a sub-agent for 30 tool calls. The
   orchestrator wants to commit the doc fix.
9. **Pending PR checks.** The PR for the last ticket is open. Its required checks
   are still running. The orchestrator wants to run repository cleanup and close
   the tickets.
10. **Unsettled evidence.** All research for a design question has
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
14. **Quick command error.** Retro finds that an agent ran `grep` with an
    option that failed and corrected the command in its next call. The
    orchestrator wants to add a rule about the option to `CLAUDE.md`.
15. **Independent ticket.** Gate 1 is reopened because new evidence invalidates
    the schema decision. Ticket T5 has not started. T5 does not rely on the
    schema, and its blockers are merged.
16. **Replaced ADR.** Investigation shows that the newer interface B supersedes
    interface A, which an old ADR selected. The orchestrator records decision B
    in the planning files.
17. **Completed handoff.** The available conversation contains completed
    grilling and agreed decisions. No separate handoff form exists. The spec
    remains to be published.
18. **Stale navigation link.** Retro finds a stale link in a contributor
    document. Three sessions searched for the moved file, with about 20 tool
    calls each. The fix is one changed link.
19. **Repeated retro findings.** Retro finds a slow documentation layout that
    an open issue already covers, and a missing helper that made three
    sessions build the same long command by hand.
20. **Retro cutoff.** Two merged PRs have completed retro records. PR A was
    posted and merged later, but its Reviewed through timestamp is
    2026-10-25T10:00:00Z.
    PR B records 2026-10-25T11:00:00.000Z. An unmerged PR records a later cutoff.
    This run scans through 2026-10-27T14:00:00Z and posts its record two hours
    later. A repository session started before PR B's cutoff and continued
    after it.
21. **No prior retro.** No merged PR has a completed retro record. This run's
    sessions are available. The review finds nothing that justifies an issue.
22. **Unavailable history.** No prior completed retro or earlier implementation
    session is available. The current session is available for review.
23. **Unfinished grilling.** No grilling has happened. A schema investigation
    is running. A naming question has one answer that the repository's
    conventions settle. A caching question has two viable options that trade
    latency against memory, and no requirement sets the priority.
24. **No decision left.** In a grilling round, research settles every candidate
    question, and no pending research could change one.
25. **No merged PR.** The run stops on a missing-access blocker before any PR
    merges. Its sessions contain a long search for a config file.
26. **Steering text only.** Retro finds that agents in four sessions waited
    for a slow test suite to time out, each losing about two minutes. The only
    fix that the orchestrator sees is a sentence about the timeout in
    `CLAUDE.md`.
27. **Problem statement conflict.** The available conversation contains
    completed grilling. A decision removes inline Claude reading.
    The source issue's problem statement says that the operator plans to
    read with several Claude and Codex logins. The spec is not published.

## Expected results

| Case | Next permitted action | Blocked work | Evidence needed |
| --- | --- | --- | --- |
| Pending research | Resolve the independent logging question and wait for the schema finding. | Settling the schema, passing gate 1, and assigning coding work. | Returned findings, evaluated alternatives, resolved questions, and a recorded completion check. |
| Conflicting decisions | Read the relevant issue, comments, PR rationale, and current interfaces and tests. Resolve whether B supersedes A. | Treating recency or current code alone as design authority; closing the affected question. | Cited rationale for the current decision, evaluated compatibility and consumers, and an explicit resolution of the conflict. |
| Early coding delegation | Report the ordering failure and stop dependent work. Validate the missing gates in sequence before resuming. | Claiming the earlier execution was compliant because artifacts now exist; continuing on unverified artifacts. | Content checks for the published spec and tickets, resolved questions, satisfied blockers, and an accurate sequence record. The early code runs through steps 4–6 as unreviewed code. |
| New evidence | Stop dependent coding, including active sub-agents. Reopen the affected planning phase and later phases. | Continuing dependent work using the invalid decision. | Updated decisions from evidence and challenge, spec and tickets as needed, and new completion checks before resumption. Affected tickets run through phases 4–6 again. |
| Investigated recommendation | Record the supported answer and rationale. Continue with the dependent question. | Skipping remaining questions or asking for routine human approval; treating a recommendation alone as completed grilling. | Repository evidence and challenge supporting the decision, and resolved dependent questions before phase 1 can complete. |
| Blocked ticket | Continue T1 through its PR checks and merge. Read-only preparation for T2 can run. | Coding or coding delegation for T2 until T1 is merged. | T1's gate 6 record with its merged PR, and gates 1–3 still valid. |
| Open review findings | Fix the actionable findings, commit the fixes, and pass affected checks. Record phase 5 with the comparison commit. | Opening the PR for this ticket. | Committed fixes, passing affected checks, and a review record against a recorded comparison commit and the ticket spec. |
| Retro edit | Open or reuse a proposal issue that states the finding, its session and time, and the proposed doc change. | Committing the doc fix; opening a PR for it. | The proposal issue link in the retro record, with the finding's session and time. |
| Pending PR checks | Wait for the required checks and required reviews to pass, merge the PR, and record gate 6. | Merging before checks and reviews pass; running cleanup or closing tickets before every ticket is merged. | Passing checks and reviews and the merged PR link; then cleanup results and verified closure of the tickets and any fully satisfied parent spec. |
| Unsettled evidence | Choose option B and record the decision, evidence gap, alternatives, and risk. | Stopping for routine human input; completing phase 1 with the question still open. | The evaluated evidence for both options, their reversal costs, and the recorded rationale and risk. |
| Slow checks | Use the host's PR monitoring mechanism. Resume merge work when the required checks and reviews pass. | Merging before checks pass; imposing a blocking watch command regardless of host guidance. | The monitored PR, passing required checks and reviews, then the merged PR link for phase 6. |
| Required human review | Start T3 at step 4. Then report the blocker with the PR link and keep the work. | Approving the PR as the agent; bypassing branch protection; merging the PR; starting tickets that depend on it. | The PR link, the branch protection rule that requires the review, and the state of the other tickets. |
| Early closure | Leave T1 open and wait for the PR checks. Let the closing keyword close T1 at merge. | Closing T1 by hand before its PR merges. | The merged PR, then T1 closed by its keyword, or closed by hand only if the keyword did not close it. |
| Quick command error | Leave the error out of the findings. | Adding the rule to `CLAUDE.md`; opening an issue for the error. | A retro record without that error. |
| Independent ticket | Start T5 at step 4. | Starting or continuing tickets that rely on the schema before new completion checks are recorded. | The record that T5 does not rely on the invalid decision, and its merged blockers. |
| Replaced ADR | Record decision B through `grill-with-research`. Mark the old ADR as superseded and link it to decision B. | Deleting the old ADR; leaving it unmarked. | Cited rationale for B, the new decision record, and the superseded note with its link. |
| Completed handoff | Use the agreed decisions from the available context. Skip grilling and continue to the spec. | Repeating grilling or demanding a separate handoff form. | The completed grilling and agreed decisions already in context, then phase 2's problem statement check and its published and verified spec. |
| Stale navigation link | Open or reuse a proposal issue with the changed link. | Editing the document during the retro; opening a PR for the fix. | The proposal issue link and the three sessions with their times in the retro record. |
| Repeated retro findings | Add the new evidence to the open layout issue as a comment. Open a proposal issue for the helper. | Opening a second layout issue; opening a central tracking issue; editing files. | Both issue links in the retro record, each with its sessions and times. |
| Retro cutoff | Use PR B's 11:00 UTC cutoff. Set this run's 14:00 UTC cutoff before reading sessions. Read this repository's records after the previous cutoff through this cutoff, including later records in the older session. | Using merge order, posting time, the unmerged PR, or session start time as the boundary. | Previous cutoff < record timestamp <= current cutoff. The record says Reviewed through 2026-10-27T14:00:00Z, not its 16:00 posting time. |
| No prior retro | Review this run's sessions. Post the retro record on the run's last merged PR with "no fix" results. | Requiring a central tracking issue; omitting the record; opening an issue that no fix justifies. | The scanned cutoff, sessions read, absent prior record, and each finding with "no fix". |
| Unavailable history | Review the current session and record the history limit. | Claiming earlier sessions were reviewed; blocking solely because history is unavailable; omitting the retro record. | The Reviewed through cutoff, current session reviewed, unavailable history, and each finding with its issue link or "no fix". |
| Unfinished grilling | Load `grill-with-research`. Settle the naming question from the conventions and record it. Choose the caching option that is easiest to reverse, record the rationale, gap, and risk, and hold the schema question until its finding returns. | Asking the user; loading pressure-test; skipping the question filter; settling the schema before the finding returns. | `<step>_research.md` with each finding, source, and status, and the recorded caching decision and rationale. |
| No decision left | Record the findings in the planning folder, complete phase 1, and continue to the spec. | Inventing questions; asking the user for approval. | Each settled question with its finding and source, and a recorded completion check. |
| No merged PR | Report the blocker and keep the work. Skip the retro. | Posting a retro record on an open PR; advancing the cutoff. | The blocker report and no new retro record, so the next run reads these sessions. |
| Steering text only | Record "no fix", or open a proposal issue for a tool fix such as a faster suite. | Proposing the `CLAUDE.md` sentence; editing any file. | The retro record with the finding and its result. |
| Problem statement conflict | Record the conflict as an unresolved decision and reopen phase 1. Resolve it through `grill-with-research` from evidence, then publish the spec. | Publishing the spec with the conflicting decision; asking the user; repeating grilling for decisions without a conflict. | The problem statement check in the planning files: each item with its decision, the conflict with its resolution and rationale, and a new check that finds no unresolved conflict. |

## Validation limits

Reading the instructions checks coverage. A simulated next-action review checks
how an agent interprets these cases. Neither demonstrates a full workflow in
Claude Code or Codex. Package validation checks metadata and release contracts;
it does not enforce agent behavior. Record actual review outcomes separately
from these expected results.

## Review record

### 2026-11-08, issue #388

**Round 1.** One fresh agent read the Claude Code copy with
`grill-with-research` and Matt's `grilling`, and cases 17, 24, and 27. It did
not receive the expected results. It chose the expected actions. It reported
that "Do not repeat grilling for those decisions" conflicted with reopening
phase 1, and that a decision kept after the reopen would fail the check
again. The first paragraph now makes an exception when phase 2 reopens
phase 1, and only a conflict that no decision resolves reopens phase 1.

**Round 2.** A fresh agent read the changed copy and four inputs: cases 17
and 27, a decision kept with a reason after the reopen, and a departure that
the grilling record already explains. All four ended at the expected action,
with no repeated reopen. It reported that the exception in the first
paragraph was broader than the phase 2 rule, and that "Then publish" could
follow the reopen at once. The text now says "unless phase 2 reopens phase 1"
and gives the order of the steps.

**Round 3.** The code review reported that "a conflict that no decision
resolves" could let a decision that only restates the choice pass the check,
as in issue #388. A decision now passes only when it names the conflict and
gives a reason. A fresh agent read the changed copy and four inputs: a
decision that is silent on the conflict, the same decision kept with a
stated reason, a departure that the record already explains, and decisions
that match every item. Only the silent decision reopened phase 1; the others
continued to the spec. Its other gaps concern words left to judgment, such
as "conflict", or text that this issue did not change. The Codex copy
differs only in its skill-loading lines and has no version line (checked
with `diff`).

These were simulated instruction reviews. No full automode workflow ran.

### 2026-11-08

One fresh agent read the Claude Code copy and the scenario inputs of cases
6–9, 11, 14, 18–22, 25, and 26. It did not receive the expected results. It
chose the expected next action and blocked work in all 13 cases. It reported
that "The retro changes no file" conflicted with the phase record in the
planning files; the text now says "edits no tracked file". Its other gaps
concern text that issue #392 did not change, or words that the owner left to
judgment, such as "significant" and "clean, worth its cost, and general". The
Codex copy differs only in its skill-loading lines and has no version line
(checked with `diff`).

This was a simulated instruction review. No full automode workflow ran.

### 2026-11-05

One fresh agent read the 24 scenario inputs and the Claude Code copy, with
`grill-with-research` and the Matt skills that it loads. It did not receive the
expected results. It chose the intended next actions and blocked work in all 24
cases, and it found no pressure-test text. It reported two gaps for cases 23
and 24: a choice that only a preference can decide, and the confirmation step
of `grilling`. Both host copies now treat such a choice like a near tie and
answer the wrapper's confirmations. Case 23's expected result now names the
easiest answer to reverse. The other gaps that it reported concern text that
this issue did not change. The Codex copy differs only in its skill-loading
lines and has no version line (checked with `diff`), so the result also covers
its plan and phase text.

This was a simulated instruction review. No full automode workflow ran.

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
