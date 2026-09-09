---
name: repo-cleanup
description: Clean merged worktrees and branches, reconcile completed issues, and update the Default Branch.
---

# Repository Cleanup

Clean repository state against the Default Branch and its configured upstream
remote. Reconcile completed issues associated with the work being cleaned.
Proceed without confirmation within the requested scope.

## Identify the work

- Refresh remote state and inspect local worktrees plus local and remote branches.
- Establish that each non-default branch is merged, including squash merges.
- Before deleting branches or worktrees, record their merged PRs, linked tickets,
  and parent specs. Include references supplied by the calling workflow or user.
  In standalone use, discover these from the verified merged work. Keep unrelated
  backlog issues outside the cleanup scope unless the user includes them.
  Report missing or ambiguous issue links instead of assuming reconciliation is
  complete.

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

If tracker access or closure fails, report the unresolved issue and reason.
Continue independent safe Git cleanup. Never report issue reconciliation as
complete while a required closure is unverified.

## Clean Git state

- Remove clean merged worktrees and local branches, delete every verified-merged
  branch from the upstream remote, and prune stale remote-tracking references.
- Fast-forward a clean Default Branch when it is behind. Preserve repository data
  whenever cleanup or branch state is unsafe or uncertain.
- Report what was cleaned and retained, with a reason for each retained item.
  Include issue and PR links, verified closures, and issues left open.
