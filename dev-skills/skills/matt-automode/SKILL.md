---
name: matt-automode
version: 1.9.0
description: Run the Matt planning-to-merge workflow with code review and a navigation retrospective when the user delegates a task fully to the agent without human checkpoints. Requires Matt Pocock's skills plugin.
---

# Matt Automode

This mode delegates design decisions, issue publication, implementation, review,
retro, PR merge, issue closure, and cleanup within the user's task scope.
Make routine decisions from evidence and continue without human checkpoints.
Respect tool permissions and repository protections.

**If grilling is complete, skip it.** Use the agreed decisions in the available
context. Do not repeat grilling or pressure tests for those decisions.

## Load skills as needed

This invocation covers the skills needed for the active phases below. Load them
when reached, including their referenced instructions. Skip skills for completed
phases. Pressure testing requires the separate opt-in below.

In Claude Code, invoke listed skills with the Skill tool. For missing or
user-invoked skills, resolve their paths and read their `SKILL.md` files:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/resolve_skill.py" \
  mattpocock-skills:to-spec mattpocock-skills:to-tickets \
  mattpocock-skills:implement mattpocock-skills:retro
```

Pass only the skills needed now. Use the same resolver for nested skills.
Report a missing required skill or tracker configuration as a blocker.

## Plan and decide

Use `dev-skills:step-workflow` for numbered planning files and the session task
list, within repository layout rules. Separate facts, decisions, assumptions,
and unresolved questions. Cite sources for consequential claims.

Inspect the implementation, consumers, tests, canonical docs, glossary, ADRs,
and relevant issue and PR decisions. Resolve conflicts explicitly; current code
or recency alone does not establish intent. Mark replaced decisions as
superseded and link their replacements. Use parallel read-only investigations
for independent questions. Wait for findings that could change a decision.

For unfinished grilling, use `mattpocock-skills:grill-with-docs`. Work all
questions whose prerequisites are settled in each round. Challenge candidate
answers against evidence, alternatives, failure cases, compatibility, and
consumers. Record the decision and rationale, then take the next round.
If evidence leaves a near tie, choose the answer easiest to reverse and record
the gap and risk. Resolve routine checkpoints yourself, including testing
seams, ticket breakdown, review base, and retro fix selection.

### Optional pressure tests

Pressure testing is **off by default**. Enable it only if the user asks during
grilling. Keep that choice for the same task, including reopened questions,
unless the user withdraws it. While off, skip loading, setup, preflight, and
critic calls. A completed grilling handoff needs no retrospective pressure test.

When enabled, classify each question with a reason. A design-critical question
has at least two answers the evidence permits, and its choice changes behavior,
an interface, a consumer, or a recorded decision, or is hard to reverse.
For each round with such questions, run one new
[pressure test](../pressure-test/SKILL.md) before resolving them. Run setup and
preflight as part of that test. Save its records in the planning folder. Give
each question an ID, options, evidence, and current answer. Include other
questions and their classifications so the critic can challenge them. Resolve
classification disputes from evidence; add conceded questions to the test.

Apply the first matching rule to each current answer in its coverage table:

1. **Not assessed:** carry it to the next round; its dependent questions wait.
   An answer changed after assessment is not assessed. Carried questions alone
   can form the next round.
2. **Converged:** resolve it with the assessed answer.
3. **Objections remain:** choose from the evidence and objections. Keep the
   assessed answer with its unresolved objections recorded, or carry a changed
   answer under rule 1.

Override the carry when a test reviewed none of its IDs, or a question ends two
consecutive tests without assessment of its current answer. Decide it with the
normal evidence-based challenge and continue. Count after applying rules 1–3;
revisions do not reset the count. A reopened decision starts a new count and
needs a fresh assessment even if its answer stays the same. A reviewed answer
that later became stale still counts as a reviewed ID for the first condition.
Critic failure does not block automode. Record each test's ending condition and
why an answer was not assessed. Keep assessed answers' objections instead of
claiming they were unassessed. Put these decisions, evidence, risks, and critic
limits directly in the spec and any ticket or ADR that records them; these
records must stand alone without links to disposable planning files.

## Phases and completion checks

Record each phase's completion evidence and next action in the planning files.
Existing specs and tickets can satisfy a phase after checking their content and
current validity. An existing recommendation alone does not complete grilling.
Run phases 4–7 per ticket in dependency order, then phase 8 once.

1. **Grilling — `mattpocock-skills:grill-with-docs`.** Skip if complete.
   Otherwise finish all design-critical questions and evaluate all research
   that could change them. Record domain terms, decisions, and safe nonblocking
   assumptions. Apply the optional pressure-test rules only when enabled.
2. **Spec — `mattpocock-skills:to-spec`.** After phase 1, publish and verify the
   spec with scope, decisions, and testing seams. Align any glossary entries
   added by this task with its decisions.
3. **Tickets — `mattpocock-skills:to-tickets`.** After phase 2, publish and
   verify tickets with acceptance criteria and blocking dependencies that cover
   the spec. Track the parent spec, tickets, and PRs. Order tickets that edit
   the same shared file, including manifests, registries, and changelogs. Choose
   release versions when a PR is ready, not in tickets. For pytest repositories,
   use [lean-tests](../lean-tests/SKILL.md), review mode's "Pin the requirement
   sources", before implementation. Pin the original request, spec, and tickets
   using Python 3.9 or newer; record the directory and SHA-256 values.
4. **Implement — `mattpocock-skills:implement`.** Start coding or coding
   delegation only after phases 1–3 pass and every blocking ticket's PR merges.
   Follow the testing workflow and commit the changes. Before committing,
   search new prose for glossary `_Avoid_` terms and report helpers imported
   from other modules. Complete when the ticket's tests pass and edits are
   committed for review.
5. **Review — `mattpocock-skills:code-review`.** Review against the ticket spec
   and a recorded comparison commit. This fulfills `implement`'s review step.
   Fix actionable Standards and Spec findings, commit, and pass affected checks.
6. **Retro — `mattpocock-skills:retro`.** After review, inspect earlier
   implementation sessions for slow navigation and stale docs, including after
   successful work. Follow "Navigation retrospective" below. Apply small fixes
   in this PR; commit and check them, then repeat code review against phase 5's
   original comparison commit. Verify the diff includes the retro edits. Fix
   its actionable findings and pass affected checks after the last edit.
   Complete with the retro record ready for the PR and larger findings filed.
7. **PR — `mattpocock-skills:pr`.** Open the reviewed PR with its retro record
   and issue references. Use a separate `Closes #N` for each fully resolved
   ticket; use ordinary references for partial work. Carry closure references
   to the final integration PR for stacked work. Merge after required checks
   and reviews pass, under repository rules. Record the merged PR link.
8. **Cleanup — `dev-skills:repo-cleanup`.** After all ticket PRs merge, pass
   the tracked tickets, parent spec, and PRs to cleanup. Verify ticket closure
   and close the parent only when fully satisfied. Close tickets by hand only
   after merge if the tracker did not close them. Finish after cleanup reports.

### When work changes or waits

If evidence invalidates a decision, stop only dependent work, including active
coding agents. Reopen the affected planning phase and later phases. Update
decisions, the spec, and tickets; record completion checks before resuming.
Run affected tickets through phases 4–7 again. For merged tickets, open a new
ticket. Record why independent tickets can continue with their prior gates.

If coding started early, report the ordering failure and stop dependent work.
Complete the missing phases and treat that code as unreviewed. Later artifacts
do not make the earlier order compliant.

Use the host's PR monitoring mechanism for pending checks. Fix failures on the
PR branch; code changes need review against the same comparison commit before
merge. For a rebase, give the agent a resolution rule per conflicted file and
the required final versions; recheck versions that Git merged without conflict.
If a required human review cannot be supplied, continue independent tickets,
then report the blocker and keep the work. Respect branch protection.

## Navigation retrospective

Use the repository's session-discovery guidance. Store each completed retro in
its own PR, rather than a central tracking issue.

1. Find the latest completed "Navigation retrospective" record in merged PRs
   by its **Reviewed through** UTC timestamp. Read existing documentation issues
   to reuse relevant follow-ups. Set this run's cutoff before copying sessions.
2. Select sessions by recorded repository and worktree metadata before searching
   text. Claude Code stores JSONL under `~/.claude/projects/` with `cwd` fields
   and subagents under `<session>/subagents/`. Codex stores JSONL under
   `~/.codex/sessions/` with `cwd` in `session_meta`. Keep this metadata even
   when it precedes the cutoff. Read records after the previous cutoff through
   this run's cutoff, including later records in sessions that started earlier.
   Compare parsed
   timestamps, or normalize all UTC timestamps to millisecond precision.
   Without a prior record, use relevant earlier implementation sessions. If
   unavailable, review the current session and report the limit.
3. Process transcript copies in one `mktemp -d` directory. Give agents those
   paths, preserve the originals, and remove the temporary directory by path.
4. Apply local fixes that need no new design decision or substantial scope
   increase in this PR. Create or reuse a separate issue for each larger
   finding. Block the PR only if a finding affects the current change's
   correctness; otherwise link the follow-up and continue.
5. Add a short **Navigation retrospective** record to the PR: **Reviewed
   through** cutoff, sessions read, skipped or unavailable history, findings,
   fixes, and follow-up issue links. Use the scanned cutoff, not posting time.
   Prepare it in phase 6 and publish it in phase 7, even if no fix was needed.

## Sub-agent briefs

Give each agent a self-contained task, owned files, and relevant planning-file
sections by path and line. Keep plan and task-list tools in this session.
Allow only one full test suite at a time; other agents can run focused tests.
State the repository search rules in reviewer briefs, including excluded paths.
Require measured evidence for claims about external tool behavior.

## Finish

Report completed and blocked phases accurately, with evidence, review results,
retro history limits, issue and PR links, and remaining work. Include requirement
pin paths and hashes when used. For enabled pressure tests, list decisions whose
current answers the critic did not assess. Distinguish instruction checks and
simulated scenarios from demonstrated agent behavior. Stop for missing access,
enforced restrictions, or repeated failures with no viable next step; retain
the work and report the blocker.
