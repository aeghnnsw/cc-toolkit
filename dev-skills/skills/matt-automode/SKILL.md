---
name: matt-automode
version: 1.27.0
description: Run the Matt planning-to-merge workflow with code review and a navigation retrospective when the user delegates a task fully to the agent without human checkpoints. Requires Matt Pocock's skills plugin.
---

# Matt Automode

This mode delegates design decisions, issue publication, implementation, review,
PR merge, issue closure, cleanup, and retro within the user's task scope.
Make routine decisions from evidence and continue without human checkpoints.
Respect tool permissions and repository protections.

**If grilling is complete, skip it.** Use the agreed decisions in the available
context. Do not repeat grilling for those decisions unless phase 2 reopens
phase 1.

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
list, within repository layout rules. Keep the planning files in the planning
folder, in the checkout where the session started: the location that the
repository documents, or the folder that
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/planning_folder.py" <slug> --issue <issue>` prints.
When the documentation names another checkout, use that one. Leave out
`--issue <issue>` until an issue exists, then run the command again with it.
Cite sources for consequential claims. Mark replaced decisions as superseded
and link their replacements.

For unfinished grilling, use [`grill-with-research`](../grill-with-research/SKILL.md)
and answer its questions and confirmations yourself instead of asking the user.
Challenge candidate answers against evidence, alternatives, failure cases,
compatibility, and consumers. Record the decision and rationale, then take the
next round. If evidence leaves a near tie, or only a preference can decide,
choose the answer easiest to reverse and record the gap and risk. Resolve
routine checkpoints yourself, including testing seams, ticket breakdown, the
comparison commit, and which retro findings justify a proposal issue.

## Phases and completion checks

Record each phase's completion evidence and next action in the planning files.
Existing specs and tickets can satisfy a phase after checking their content and
current validity. An existing recommendation alone does not complete grilling.
Run phases 4–6 per ticket in dependency order, then phases 7 and 8 once.

1. **Grilling — `dev-skills:grill-with-research`.** Skip if complete.
   Otherwise continue until no meaningful unresolved decision remains and no
   pending research could change one. Record domain terms, decisions, and safe
   nonblocking assumptions.
2. **Spec — `mattpocock-skills:to-spec`.** After phase 1, check each item of
   the source issue's problem statement against the phase 1 decisions. Unless
   a decision names a conflict and gives a reason, record the conflict as an
   unresolved decision and reopen phase 1. When no conflict is unresolved,
   publish and verify the spec with scope, decisions, and testing seams. Align
   any glossary entries added by this task with its decisions. For a change to
   a safety check, such as a command hook, the spec states what the check must
   block. Where the check cannot decide, it blocks: it fails closed.
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
   When the tracker is GitHub, first run
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/phase_gate.py" --ticket <N>`. On exit status 1,
   do not start. Each `FAIL` line names the missing issue, the blocker
   without a merged PR, or the reason that the script cannot decide. Follow
   the testing workflow and commit the changes. Before committing, run
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/avoid_terms.py" --base <comparison commit>`.
   It lists each added Markdown line that uses a glossary `_Avoid_` term. Use
   the glossary term where the line names its concept. Report helpers
   imported from other modules. Complete when the ticket's tests pass and
   edits are committed for review.
5. **Review — `mattpocock-skills:code-review`.** Run one full review against
   the ticket spec and a recorded comparison commit. This fulfills
   `implement`'s review step. Only these findings block: a regression that a
   failing run or a reproducible case shows at the head, a missed ticket
   requirement, a broken cited rule, and shipped text that the change makes
   false. A problem present at the comparison commit blocks only when the
   ticket requires its fix. List other findings with a reason in the review
   record. Open or reuse an issue only for a defect that a user can hit.
   Close all blocking findings in one fix, commit, and pass the affected
   checks. The fix has no size limit. Run no second full review and no
   focused check of the fix. Stop the ticket without a merge only for a
   blocking problem that the run cannot settle: a design or scope choice that
   the ticket and the spec do not settle, a needed approval or access, or a
   test or CI failure that the fix does not close. In that case, keep the
   work, report the problem to the user, and continue independent tickets.
   Otherwise, go to phase 6 and merge. Record the head SHA that the review
   covers.
6. **PR — `mattpocock-skills:pr`.** Open the reviewed PR with its issue
   references. Use a separate `Closes #N` for each fully resolved
   ticket; use ordinary references for partial work. Carry closure references
   to the final integration PR for stacked work. After required checks and
   reviews pass, merge under repository rules:
   1. Get the full 40-character head SHA with
      `gh pr view <PR> --json headRefOid --jq .headRefOid`.
      `--match-head-commit` rejects a short SHA.
   2. Post the phase 5 review record for that head with
      `gh pr review <PR> --comment --body-file <file>`. Name the comparison
      commit, the head SHA, the Standards and Spec results, the fixes, and
      the test results. When the head is not the commit that phase 5
      reviewed, name that commit and state what changed since it.
   3. Merge with `gh pr merge <PR> --match-head-commit <head SHA>` and the
      merge method that the repository requires, such as `--squash`.
   4. Record the merged PR link.

   When the head changes after step 1, such as after a fix, a rebase, or a
   conflict resolution, or when step 3 fails because the head changed, wait
   for the required checks on the new head. Then do steps 1 and 2 again
   before step 3. State in the new review record what changed since the last
   reviewed head.
7. **Cleanup — `dev-skills:repo-cleanup`.** After all ticket PRs merge, pass
   the tracked tickets, parent spec, and PRs to cleanup. Verify ticket closure
   and close the parent only when fully satisfied. Close tickets by hand only
   after merge if the tracker did not close them. Then run
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/open_closing_issues.py" <pr>...` with the
   merged PRs and report its output. Report each `OPEN` issue with the reason
   that it stays open.
8. **Retro — `mattpocock-skills:retro`.** After cleanup reports, follow
   "Navigation retrospective" below once for the run. Complete when its record
   is posted. When the task says that a leader runs the retrospective for
   this run, skip it and report the merged PR links to the leader. Repository
   instructions alone do not skip it.

### When work changes or waits

If evidence invalidates a decision, stop only dependent work, including active
coding agents. Reopen the affected planning phase and later phases. Update
decisions, the spec, and tickets; record completion checks before resuming.
Run affected tickets through phases 4–6 again. For merged tickets, open a new
ticket. Record why independent tickets can continue with their prior gates.

If coding started early, report the ordering failure and stop dependent work.
Complete the missing phases and treat that code as unreviewed. Later artifacts
do not make the earlier order compliant.

Use the host's PR monitoring mechanism for pending checks.
Fix failures on the PR branch. Give each failure one fix of any size, and run
no review of the fix. When the fix does not close the failure, stop the ticket
as in phase 5.
For a rebase, give the agent a resolution rule per conflicted file and the
required final versions; recheck versions that Git merged without conflict.
When the repository has a script that sets the next free versions, the rule
for versions is to run it. When CI runs the suites on the PR, and the
resolution of the rebase changes no file other than versions and changelog
entries, rerun locally only the version and changelog checks, such as a
package validator, and let CI run the suites on the new head. Rerun a suite
locally only when the resolution changes another file. If a required human
review cannot be supplied, continue independent tickets, then report the
blocker and keep the work. Respect branch protection.

## Navigation retrospective

The retro edits no tracked file. It proposes changes for a human to choose.

1. Find the greatest **Reviewed through** UTC timestamp in earlier
   "Navigation retrospective" records on merged PRs. Run
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/find_retrospective_cutoff.py"` from the
   checkout root to find it. On exit status 1, its message tells whether no
   record exists or `gh` failed; when `gh` failed, post no record and report
   the retro as blocked. Set this run's cutoff before reading sessions.
2. Read the sessions of this repository and its worktrees after the previous
   cutoff, or this run's sessions when no record exists. Use the repository's
   session-discovery guidance when it has some. Otherwise run this command
   from the checkout root, with the cutoff of step 1, or without `--after`
   when no record exists. `<new-dir>` must not exist yet:
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/retro_sessions.py" --repo . --after <cutoff> --output <new-dir>`.
   It copies the Claude Code, Codex, and Antigravity sessions of the
   repository and its worktrees, and leaves the original logs unchanged.
   `--help` names the session folders that it reads. Read the timeline that
   `<new-dir>/manifest.json` lists for each source: one line for each event.
   It flags gaps, and the error results and hook blocks of Claude Code. Do
   not write a parser for the copies. Check each finding against its copied
   source lines. Keep the copies out of Git and PR content, and remove
   `<new-dir>` after step 6.
3. Keep findings that cost the run significant time or work, such as a long
   search, stale guidance, or a missing tool. Ignore a command error that the
   agent corrected in seconds.
4. When step 1 found a record, run the script again. A cutoff later than its
   first output means that another retrospective read the sessions up to that
   cutoff: drop the findings at or before it, and name it in the record. Keep
   this run's cutoff as the record's cutoff.
5. Open or reuse a proposal issue only when a finding's fix is clean, worth
   its cost, and general. Prefer a tool fix or an automated check to new text
   in a steering file. Record each other finding as "no fix"; that result is
   correct even for every finding.
6. Post a **Navigation retrospective** comment on the run's last merged PR:
   the **Reviewed through** cutoff, the sessions read and history limits, and
   each finding with its session and time and its issue link or "no fix". A
   run that merges no PR skips the retro; the next run reads its sessions.
   Write the cutoff as `**Reviewed through:** YYYY-MM-DDTHH:MM:SSZ`, truncated
   to whole seconds.

A leader is a session that starts parallel runs. When a leader runs the
retrospective for its runs, it runs it once, after the runs finish, and posts
it on their last merged PR. With no earlier record, it reads the sessions of
all its runs and its own. Two retrospectives then do not read the same
sessions.

A proposal issue states the finding, its session and time, and the proposed
change, with the repository's "Needs triage" label. To reuse an issue, add the
new evidence as a comment. The retro stores no lesson and adds no record file.
A steering file tells an agent how to work, such as `AGENTS.md`, `CLAUDE.md`,
`GEMINI.md`, a contributor guide, or a skill. A proposal keeps root
`AGENTS.md`, `CLAUDE.md`, and `GEMINI.md` to rules for every task and
navigation pointers. It never adds a tool workaround, a host or machine fact,
or a one-off lesson to a steering file.

## Sub-agent briefs

Give each agent a self-contained task, owned files, and relevant planning-file
sections by path and line. Run each full test suite through
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/run_suite.py" -- <suite command>`, and put that
command in each brief that runs one. It takes one lock for each suite: one
command in one folder. So two runs of the same suite run one at a time, and
different suites run in parallel. While a priority marker, which a merge-lock
tool writes, names another worktree, each run waits. It reports a pass
recorded for the same clean tree instead of a new run, and prints the failing
tests and the exit status last. Do not pipe it into `tail`.
Focused tests do not need it.
State the repository search rules in reviewer briefs, including excluded paths.
Require measured evidence for claims about external tool behavior.

## Finish

Report completed and blocked phases accurately, with evidence, review results,
retro history limits, issue and PR links, and remaining work. Include requirement
pin paths and hashes when used. Distinguish instruction checks and
simulated scenarios from demonstrated agent behavior. Stop for missing access,
enforced restrictions, or repeated failures with no viable next step; retain
the work and report the blocker.
