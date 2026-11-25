# Matt Automode scenario review

These cases cover [issue #241](https://github.com/aeghnnsw/cc-toolkit/issues/241)
and later changes from issues #302, #305, #354,
[#358](https://github.com/aeghnnsw/cc-toolkit/issues/358),
[#392](https://github.com/aeghnnsw/cc-toolkit/issues/392),
[#388](https://github.com/aeghnnsw/cc-toolkit/issues/388),
[#420](https://github.com/aeghnnsw/cc-toolkit/issues/420),
[#421](https://github.com/aeghnnsw/cc-toolkit/issues/421),
[#432](https://github.com/aeghnnsw/cc-toolkit/issues/432),
[#409](https://github.com/aeghnnsw/cc-toolkit/issues/409),
[#475](https://github.com/aeghnnsw/cc-toolkit/issues/475),
[#504](https://github.com/aeghnnsw/cc-toolkit/issues/504),
[#608](https://github.com/aeghnnsw/cc-toolkit/issues/608), and
[#609](https://github.com/aeghnnsw/cc-toolkit/issues/609).
Apply each case to the [Claude Code skill](../skills/matt-automode/SKILL.md),
the [Codex skill](../codex-skills/matt-automode/SKILL.md), and the
[Antigravity skill](../antigravity-skills/matt-automode/SKILL.md).

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
28. **Cutoff script.** The dev-skills script `find_retrospective_cutoff.py`
    prints `2026-11-18T06:04:17Z PR #512`. A comment on PR #498 mentions
    "Reviewed through 2026-11-18T06:30:00Z" outside a retro record. The
    run's PRs merged, and cleanup reported.
29. **Newer cutoff before the post.** In case 28, the run set its cutoff to
    2026-11-18T07:00:00Z and read the sessions after 06:04:17Z. It has
    findings at 06:20 and 06:50. Before it opens proposal issues, the script
    prints `2026-11-18T06:40:00Z PR #515`.
30. **Leader runs the retro.** The task says that the leader session runs
    the navigation retrospective for this run. The run's PR merged, and
    cleanup reported.
31. **No repository cutoff script.** The repository has no
    `scripts/find-retrospective-cutoff.py` and no other cutoff script. Two
    merged PRs have retro records. The run's PRs merged, and cleanup
    reported.
32. **Script cannot reach GitHub.** The dev-skills script
    `find_retrospective_cutoff.py` exits with status 1 and prints
    `FAIL: gh api failed:` with a network error. The run's PRs merged,
    and cleanup reported.
33. **Leader retro with no earlier record.** A leader started three runs of
    this repository. All three finished, and two merged PRs. No merged PR has
    a retro record. The leader now runs the retrospective for its runs.
34. **Planning folder in a worktree.** A run for issue #77 started in the
    worktree `trees/feat-77`. The repository documents no planning folder
    location. The run is about to write its first planning file.
35. **Documented planning folder.** As case 34, but `docs/agents/plans.md`
    says: "Keep planning files in `docs/plans/<issue>/`, which Git ignores."
36. **Run in the main checkout.** As case 34, but the run started in the
    main checkout. It creates the worktree `trees/feat-77` for its change in
    phase 4.
37. **Antigravity sessions.** The previous record's cutoff is
    2026-11-20T09:00:00Z, and the run set its cutoff to
    2026-11-21T04:00:00Z. The repository gives no session-discovery
    guidance. In `~/.gemini/antigravity-cli`, `conversation_summaries.db`
    lists four sessions. The `workspace_uris` of three sessions name the
    worktree `trees/feat-77` of this repository, the folder that contains
    the repository, and another repository; all three were modified after
    the previous cutoff. The fourth names the repository root and was last
    modified at 2026-11-19T15:00:00Z.
38. **Merge with no record on the PR.** Phase 5 passed for ticket T1, and the
    planning files record it. The PR is #41. Its required checks and reviews
    passed. The PR has no phase 5 review record. The repository allows only
    squash merges. The run is about to run `gh pr merge 41 --squash`.
39. **Rebase after the record.** As case 38, but the run posted the phase 5
    review record for head A. Before the merge, another PR merges. The run
    rebases T1, resolves a `CHANGELOG.md` conflict, and force-pushes head B.
40. **Fix after the review.** As case 38, but phase 5 reviewed head A. Then
    a required check failed, and the run pushed a fix as head C. The
    required checks passed on head C.
41. **Request for a focused check.** The full review of ticket T1 found two
    regressions, each with a failing run. The run fixed them in one large
    fix as head B, and the affected checks pass on head B. The project lead
    asks for a focused check of the fix diff before the merge.
42. **Old problem in the full review.** Ticket T1 changes a command hook.
    The full review reports one regression with a failing run. It also
    reports a dangerous command that the ticket does not name and that the
    hook allows at the comparison commit too, with a reproduction, and a
    Standards finding that prefers another helper name and cites no rule.
43. **Fix for a failing check.** PR #41 for ticket T1 is open after phase 5.
    A required lint check fails. The run pushes a fix as head C.
44. **Fix that needs a scope choice.** The full review of ticket T1 finds a
    missed ticket requirement. Two fixes can close it: one changes the hook
    interface, and one adds a second hook. The ticket and the spec name
    neither.
45. **Requirement pins.** The repository runs its tests with pytest. Phase 3
    published ticket T1 for spec S. The run is about to pin the original
    request, S, and T1 before phase 4.
46. **Implement step.** Phases 1–3 passed for ticket T1, and the phase gate
    passed. The spec names two test seams. In Claude Code,
    `mattpocock-skills:implement` sets `disable-model-invocation: true`.
47. **Pin record in the task.** An earlier batch pinned the request and issue 12, and
    left issue 12 open. This run's task continues issue 12 and names the
    earlier pin record. The temporary source folder of the earlier batch is
    gone.

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
| Slow checks | Use the host's PR monitoring mechanism; in Antigravity, run `gh pr checks` and check again later. Resume merge work when the required checks and reviews pass. | Merging before checks pass; imposing a blocking watch command regardless of host guidance. | The monitored PR, passing required checks and reviews, then the merged PR link for phase 6. |
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
| Cutoff script | Run the dev-skills `find_retrospective_cutoff.py` from the checkout root and use 2026-11-18T06:04:17Z as the previous cutoff. Set this run's cutoff before reading sessions. | Searching PR comments by hand; using the PR #498 mention as a cutoff. | The script output. |
| Newer cutoff before the post | Drop the 06:20 finding, keep the 06:50 finding, and post the record with Reviewed through 07:00:00Z. Name PR #515's cutoff in the record. | Posting the 06:20 finding again; changing this run's cutoff to 06:40. | Both script outputs and the finding times. |
| Leader runs the retro | Skip phase 8 and give the leader the merged PR link. | Reading sessions or posting a retro record in this run. | The task text and the sent PR link. |
| No repository cutoff script | Run the dev-skills `find_retrospective_cutoff.py` from the checkout root and use its cutoff, then post the record as before. | Searching PR comments by hand; running `scripts/find-retrospective-cutoff.py`; stopping the retro because the repository has no script. | The script output. |
| Script cannot reach GitHub | Post no record and report the retro as blocked with the error. | Treating the failure as "no record" and reading only this run's sessions; posting a cutoff. | The exit status and the `gh` error. |
| Leader retro with no earlier record | Read the sessions of the leader and of all three runs, and post one record on the later of the two merged PRs. | Reading only the leader's own session; posting one record for each run. | The three runs' sessions and the two merged PR links. |
| Planning folder in a worktree | Write the planning files in `trees/feat-77/.scratch/77-<slug>/`. | Writing them in the main checkout, the session scratchpad, or a tracked folder; searching for another location. | The folder path, and that Git ignores it or the `info/exclude` line that the run added. |
| Documented planning folder | Write the planning files in `trees/feat-77/docs/plans/77/`. | Using `.scratch/` in place of the documented location. | The documented location. |
| Run in the main checkout | Write the planning files in `.scratch/77-<slug>/` of the main checkout, and keep them there after phase 4 creates `trees/feat-77`. | Moving or splitting the planning files into the new worktree. | The checkout where the session started. |
| Antigravity sessions | Run the dev-skills `retro_sessions.py` from the checkout root with `--after 2026-11-20T09:00:00Z` and a new `--output` path. Read the timeline of the `trees/feat-77` session only, which holds its records after 2026-11-20T09:00:00Z and at or before the run's cutoff. | Reading the database or the transcripts by hand; reading the sessions of the containing folder, the other repository, or the 2026-11-19 session; changing the database or a transcript. | The manifest's `window` and `sources`, and the sessions read in the retro record. |
| Merge with no record on the PR | Get the full 40-character head SHA with `gh pr view 41 --json headRefOid --jq .headRefOid`. Post the phase 5 review record for that head with `gh pr review 41 --comment`. Then run `gh pr merge 41 --squash --match-head-commit <head SHA>`. | Merging with no record for the head on the PR; a merge without `--match-head-commit`; a short SHA. | The PR review that names the comparison commit, the full head SHA, the Standards and Spec results, the fixes, and the test results; then the merged PR link. |
| Rebase after the record | Check the resolved file and the versions that Git merged without conflict. The resolution changes only `CHANGELOG.md`, so rerun locally only the version and changelog checks. Wait for the required checks on head B. Get the SHA of head B, post a new record for head B that states what changed since head A, and merge with `--match-head-commit` on head B. | Merging head B on the record for head A; merging with the SHA of head A; rerunning a full suite locally. | Both records on the PR, the second with the SHA of head B and the rebase change, and the merge command with that SHA. |
| Fix after the review | Get the SHA of head C. Post the phase 5 review record for head C. Name head A as the commit that phase 5 reviewed, and state the fix since head A. Then merge with `--match-head-commit` on head C. | A record for head C that does not name head A or the fix; merging with the SHA of head A. | The record with the SHAs of heads A and C and the fix, and the merge command with the SHA of head C. |
| Request for a focused check | Go to phase 6 with head B. Open the PR, and after the required checks pass, post the record for head B and merge with `--match-head-commit` on head B. | A focused check or a second full review of the fix; stopping T1 because the fix is large. | The record for head B with the fixes and the test results, and the merge command with the SHA of head B. |
| Old problem in the full review | Fix the regression, commit, and pass the affected checks. List the old hook gap and the naming finding with a reason in the review record. Open or reuse an issue for the hook gap. Then go to phase 6. | Fixing the hook gap or the name in T1; a focused check or a second full review. | The review record with each finding that is not blocking and its reason, and the issue link. |
| Fix for a failing check | Run no review of the fix. When the checks pass on head C, post the record for head C, then merge with `--match-head-commit` on head C. When the lint check still fails on head C, stop T1 without a merge, keep the branch, and report the failure to the user. | A focused check or a new full review of the fix; merging before the checks pass. | The passing checks, the record for head C, and the merge command with the SHA of head C; or the failing check and the report. |
| Fix that needs a scope choice | Stop T1 without a merge, keep the branch, and report the choice and both fixes to the user. Continue independent tickets. | Choosing a fix for the user; merging T1. | The finding, the two fixes, the kept branch, and the report. |
| Requirement pins | Write the request, S, and T1 to files in a temporary folder as the lean-tests "Pin the requirement sources" section says. Run `lean_tests.py pin --record --project <project>` with one `--source NAME=PATH` for each file. Record the `record` path that it prints and each SHA-256 value. | Writing `pins.json` with another script, such as inline `python3` with `hashlib`; writing the record into the temporary folder. | A record in `lean-tests-pins/` of the Git common folder that `lean_tests.py pin --check` accepts, and the recorded values. |
| Implement step | Use `mattpocock-skills:tdd` at the two seams. When the repository has a typecheck, run it often. Run single test files often, and the full suite once at the end, then `avoid_terms.py`, and commit. Go to phase 5. | Calling the Skill tool with `mattpocock-skills:implement`; reading its `SKILL.md` by path; skipping `tdd` at a seam. | The `tdd` cycles at both seams, the full-suite result, and the commit. |
| Pin record in the task | Run `lean_tests.py pin --check` on the named record before phase 4, and use its hashes. Pin only a new source, such as a new ticket, in a new record. Report each record path and its SHA-256 values at the end, after `pin --check` passes. | Pinning the request or issue 12 again; rebuilding the sources from history; stopping because the source folder is gone. | The `pin --check` output with the earlier `pinned_at`, and the record paths in the report. |

## Validation limits

Reading the instructions checks coverage. A simulated next-action review checks
how an agent interprets these cases. Neither demonstrates a full workflow in
Claude Code, Codex, or Antigravity. Package validation checks metadata and
release contracts; it does not enforce agent behavior. Record actual review
outcomes separately from these expected results.

## Review record

### 2026-11-22, issue #504

**Static checks.** `test_matt_automode.py` now requires in every copy that
phase 5 makes one fix of any size, runs no second full review and no focused
check, and stops the ticket only for a blocking problem that the run cannot
settle. It also requires that a fix for a failing check gets no review, that
"focused check" occurs only as "no focused check", and that the review record
names no focused check. These checks fail on the 953103b copies and pass after
the change. No simulated review of cases 40–44 ran.

### 2026-11-25, issues #608 and #609

**Static checks.** `test_matt_automode.py` now requires in every copy that
phase 3 names the lean-tests pin section and `lean_tests.py pin --record`,
and forbids another script. It also requires that phase 4 names no skill in
its heading and states the `tdd`, test cadence, and commit steps, and that no
copy names `mattpocock-skills:implement`. These checks fail on the 2a6d840
copies and pass after the change. No simulated review of cases 45 and 46 ran.

### 2026-11-25, issue #623

**Static checks.** `test_matt_automode.py` now requires in every copy that
phase 3 records the pin record path, checks a pin record that the task
names, and does not pin its sources again, and that Finish reports the path
of each checked pin record, also of a received one. `test_lean_tests.py` pins into the default record,
removes the source folder and the worktree, and passes `pin --check`. These
checks fail on the 007727c copies and pass after the change. No simulated
review of cases 45 and 47 ran.
