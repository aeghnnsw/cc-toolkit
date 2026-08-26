---
name: repo-cleanup
version: 1.0.0
description: Clean merged worktrees and branches, prune their upstream remote, and reconcile the Default Branch.
disable-model-invocation: true
---

# Repository Cleanup

Clean repository state against the Default Branch and its configured upstream
remote.

- Refresh remote state and inspect local worktrees plus local and remote branches.
- Establish that each non-default branch is merged, including squash merges.
- Remove clean merged worktrees and local branches, delete every verified-merged
  branch from the upstream remote, and prune stale remote-tracking references.
- Fast-forward a clean Default Branch when it is behind. Preserve repository data
  whenever cleanup or branch state is unsafe or uncertain.
- Proceed without confirmation, then report what was cleaned and what was retained,
  including the reason for each retained item.
