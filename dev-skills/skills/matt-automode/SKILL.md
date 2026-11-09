---
name: matt-automode
version: 1.11.0
description: Run the Matt planning-to-merge workflow with code review and a navigation retrospective when the user delegates a task fully to the agent without human checkpoints. Requires Matt Pocock's skills plugin.
---

# Matt Automode

This mode delegates design decisions, issue publication, implementation, review,
PR merge, issue closure, cleanup, and retro within the user's task scope.
Make routine decisions from evidence and continue without human checkpoints.
Respect tool permissions and repository protections.

**If grilling is complete, skip it.** Use the agreed decisions in the available
context. Do not repeat grilling for those decisions.

## Load skills as needed

This invocation covers the skills needed for the active phases below. Load them
when reached, including their referenced instructions. Skip skills for completed
phases.

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
list, within repository layout rules. Cite sources for consequential claims.
Mark replaced decisions as superseded and link their replacements.

For unfinished grilling, use [`grill-with-research`](../grill-with-research/SKILL.md)
and answer its questions and confirmations yourself instead of asking the user.
Challenge candidate answers against evidence, alternatives, failure cases,
compatibility, and consumers. Record the decision and rationale, then take the
next round. If evidence leaves a near tie, or only a preference can decide,
choose the answer easiest to reverse and record the gap and risk. Resolve
routine checkpoints yourself, including testing seams, ticket breakdown, review
base, and which retro findings justify a proposal issue.

## Phases and completion checks

Record each phase's completion evidence and next action in the planning files.
Existing specs and tickets can satisfy a phase after checking their content and
current validity. An existing recommendation alone does not complete grilling.
Run phases 4–6 per ticket in dependency order, then phases 7 and 8 once.

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
6. **PR — `mattpocock-skills:pr`.** Open the reviewed PR with its issue
   references. Use a separate `Closes #N` for each fully resolved
   ticket; use ordinary references for partial work. Carry closure references
   to the final integration PR for stacked work. Merge after required checks
   and reviews pass, under repository rules. Record the merged PR link.
7. **Cleanup — `dev-skills:repo-cleanup`.** After all ticket PRs merge, pass
   the tracked tickets, parent spec, and PRs to cleanup. Verify ticket closure
   and close the parent only when fully satisfied. Close tickets by hand only
   after merge if the tracker did not close them.
8. **Retro — `mattpocock-skills:retro`.** After cleanup reports, follow
   "Navigation retrospective" below once for the run. Complete when its record
   is posted.

### When work changes or waits

If evidence invalidates a decision, stop only dependent work, including active
coding agents. Reopen the affected planning phase and later phases. Update
decisions, the spec, and tickets; record completion checks before resuming.
Run affected tickets through phases 4–6 again. For merged tickets, open a new
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

The retro edits no tracked file. It proposes changes for a human to choose.

1. Find the greatest **Reviewed through** UTC timestamp in earlier
   "Navigation retrospective" records on merged PRs. Set this run's cutoff
   before reading sessions.
2. Read the sessions of this repository and its worktrees after the previous
   cutoff, or this run's sessions when no record exists. Use the repository's
   session-discovery guidance when it has some. Otherwise read the JSONL logs:
   Claude Code under `projects/` in `~/.claude` or `$CLAUDE_CONFIG_DIR`, and
   Codex under `sessions/` in `~/.codex` or `$CODEX_HOME`. Select sessions by
   their recorded `cwd`. Leave the original logs unchanged.
3. Keep findings that cost the run significant time or work, such as a long
   search, stale guidance, or a missing tool. Ignore a command error that the
   agent corrected in seconds.
4. Open or reuse a proposal issue only when a finding's fix is clean, worth
   its cost, and general. Prefer a tool fix or an automated check to new text
   in a steering file. Record each other finding as "no fix"; that result is
   correct even for every finding.
5. Post a **Navigation retrospective** comment on the run's last merged PR:
   the **Reviewed through** cutoff, the sessions read and history limits, and
   each finding with its session and time and its issue link or "no fix". A
   run that merges no PR skips the retro; the next run reads its sessions.

A proposal issue states the finding, its session and time, and the proposed
change, with the repository's "Needs triage" label. To reuse an issue, add the
new evidence as a comment. The retro stores no lesson and adds no record file.
Root `AGENTS.md` and `CLAUDE.md` hold only rules for every task and navigation
pointers. A proposal never adds a tool workaround, a host or machine fact, or a
one-off lesson to a steering file.

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
