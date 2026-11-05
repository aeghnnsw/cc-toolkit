---
name: matt-automode
description: Run the Matt planning-to-merge workflow with code review and a navigation retrospective when the user delegates a task fully to the agent without human checkpoints. Requires Matt Pocock's skills plugin.
---

# Matt Automode

This mode delegates design decisions, issue publication, implementation, review,
retro, PR merge, issue closure, and cleanup within the user's task scope.
Make routine decisions from evidence and continue without human checkpoints.
Respect tool permissions and repository protections.

**If grilling is complete, skip it.** Use the agreed decisions in the available
context. Do not repeat grilling for those decisions.

## Load skills as needed

This invocation covers the skills needed for the active phases below. Load them
when reached, including their referenced instructions. Skip skills for completed
phases.

In Codex, open listed skills' `SKILL.md` files. Explicit-only skills may be
omitted from the list; resolve their paths and read them directly:

```bash
python3 "<plugin-root>/scripts/resolve_skill.py" --host codex \
  mattpocock-skills:to-spec mattpocock-skills:to-tickets \
  mattpocock-skills:implement mattpocock-skills:retro
```

`<plugin-root>` is this plugin's root, two levels above the skill folder.
Pass only the skills needed now. Use the same resolver for nested skills.
Report a missing required skill or tracker configuration as a blocker.

## Plan and decide

Use `dev-skills:step-workflow` for numbered planning files and the session task
list, within repository layout rules. Cite sources for consequential claims.
Mark replaced decisions as superseded and link their replacements.

For unfinished grilling, use [`grill-with-research`](../grill-with-research/SKILL.md)
and answer its questions and confirmations yourself instead of asking the user.
Challenge candidate answers against evidence, alternatives, failure cases,
compatibility, and consumers. Record the decision and rationale, then take the
next round. If evidence leaves a near tie, or only a preference can decide,
choose the answer easiest to reverse and record the gap and risk. Resolve
routine checkpoints yourself, including testing seams, ticket breakdown, review
base, and retro fix selection.

## Phases and completion checks

Record each phase's completion evidence and next action in the planning files.
Existing specs and tickets can satisfy a phase after checking their content and
current validity. An existing recommendation alone does not complete grilling.
Run phases 4–7 per ticket in dependency order, then phase 8 once.

1. **Grilling — `dev-skills:grill-with-research`.** Skip if complete.
   Otherwise continue until no meaningful unresolved decision remains and no
   pending research could change one. Record domain terms, decisions, and safe
   nonblocking assumptions.
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
   text. Read the default and the active config folders when they differ.
   Claude Code stores JSONL under `projects/` in `~/.claude` or
   `$CLAUDE_CONFIG_DIR`, with `cwd` fields and subagents under
   `<session>/subagents/`. Codex stores JSONL under `sessions/` in `~/.codex`
   or `$CODEX_HOME`, with `cwd` in `session_meta`. Keep this metadata even
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
pin paths and hashes when used. Distinguish instruction checks and
simulated scenarios from demonstrated agent behavior. Stop for missing access,
enforced restrictions, or repeated failures with no viable next step; retain
the work and report the blocker.
