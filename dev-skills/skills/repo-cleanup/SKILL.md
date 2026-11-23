---
name: repo-cleanup
version: 1.10.0
description: This skill should be used when the user asks to "clean up merged branches", "remove merged worktrees", "run repo-cleanup", or "clean up after the merge", or when a workflow or repository instructions say to run repo-cleanup after work merges. It cleans merged worktrees and branches, reconciles completed issues, deletes their planning folders, and updates the Default Branch.
---

# Repository Cleanup

Clean repository state against the Default Branch and its configured upstream
remote. Reconcile completed issues associated with the work being cleaned.
Proceed without confirmation within the requested scope.

## Make the plan

Refresh remote state with `git fetch --prune` for the upstream remote. Then
run this command from the checkout that the current session runs in:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/cleanup_plan.py"
```

The command prints the cleanup plan and removes nothing. Each line has four
tab-separated fields: `KEEP` or `REMOVE`; the kind (`folder`, `worktree`,
`branch`, or `remote-branch`); the path or branch name; and the reason. The
plan covers every worktree, local branch, and remote branch, including those
that a calling workflow did not name. A user request can limit this scope.

- Add `--main-only` when the repository documents its planning folder
  location in the main checkout. Add `--planning-location <folder>` when the
  documented location is not `.scratch`. The plan inspects the planning
  folders, `.scratch/<issue>-<slug>/` by default, in the main checkout, in
  the current worktree, and in each worktree that it would otherwise remove,
  and keeps a worktree that holds a kept folder. With `--main-only`, it does
  not inspect the current worktree, and it removes no folder outside the main
  checkout.
- Add `--remote <name>` when the upstream remote is not `origin`.
- If the command fails, remove nothing and report the error.

The plan keeps the current worktree and each worktree that another live
session may use, with the evidence: a Git lock, a running process in the
worktree, or a Claude Code or Codex session log or an Antigravity
conversation of the last 60 minutes. It keeps each worktree that holds a
lead state of t3-project-lead, `.scratch/<YYYYMMDD>-lead-<slug>/state.json`,
also with `--main-only`. It keeps a worktree whose folder contains another
worktree that Git lists. It keeps a worktree with a detached HEAD or
uncommitted changes. A branch is merged when a merged PR of the branch has
the branch tip as its head commit (`headRefOid`). The plan also treats a
branch as merged when its tip is in the Default Branch or is the head commit
of any merged PR: such a branch has no commit of its own. The plan keeps such
a branch when its reflog shows that it was created less than 60 minutes ago.
When a check cannot run, the plan keeps the item and gives the error as the
reason.

Before deleting anything, record the merged PRs that the plan names,
including the PR of the current worktree, their linked tickets, and parent
specs. Include references supplied by the calling workflow or user. Keep
unrelated backlog issues outside the cleanup scope unless the user includes
them. Report missing or ambiguous issue links instead of assuming
reconciliation is complete.

## Reconcile issues

Use the repository's configured issue tracker. If no tracker or associated issues
exist, report issue reconciliation as not applicable and continue Git cleanup.

For each associated ticket, verify its acceptance criteria and that all required
work has reached the repository's required integration branch. A merge into an
intermediate branch or a matching branch name alone is not proof of completion.
Read the ticket state. If the ticket is complete but open, close it as completed
with links to the merged PRs, then read its state again to verify closure. Keep
incomplete or unverified tickets open and report the remaining work or evidence.

After the associated tickets are complete and closed, verify each parent spec's
full scope, including additional acceptance criteria and child tickets outside
this cleanup. Close a fully satisfied open parent as completed with links to the
merged work, then verify its closed state. Preserve broader incomplete parents.
Planning instructions to preserve parents during ticket publication do not
prevent this final reconciliation after the full scope is complete.

Then run this command with the merged PRs of the cleanup:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/open_closing_issues.py" <pr>...
```

It prints each closing issue of each PR as `OPEN` or `CLOSED`, and each PR
with no closing issue as `NONE`. It exits 1 when a closing issue is still
open, and 2 when it cannot check. Report its output. For each `OPEN` line,
close the issue when it is complete, or report the remaining work.

If tracker access or closure fails, report the unresolved issue and reason.
Continue independent safe Git cleanup. Never report issue reconciliation as
complete while a required closure is unverified or the command exits nonzero.

## Clean Git state

Run the plan command again with the same options, because closures change
the issue states that the plan reads. Act only on its `REMOVE` lines, in this
order:

1. Delete each `folder` by its exact path.
2. Remove each `worktree` with `git worktree remove <path>`.
3. Delete each `branch` with `git branch -D <name>`. A squash-merged branch
   needs `-D`; the plan verified its merged PR.
4. Delete each `remote-branch` `<remote>/<name>` from the upstream remote
   with `git push <remote> --delete <name>`.

- Fast-forward a clean Default Branch when it is behind. Preserve repository data
  whenever cleanup or branch state is unsafe or uncertain.
- Report what was cleaned and retained: each `KEEP` line with its reason.
  Include issue and PR links, verified closures, and issues left open.
