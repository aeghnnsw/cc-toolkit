---
name: repo-cleanup
version: 1.14.0
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
`branch`, `config-section`, or `remote-branch`); the path, branch name, or
config section; and the reason. The plan covers every worktree, local branch,
and remote branch, including those that a calling workflow did not name. A
user request can limit this scope.

- Add `--main-only` when the repository documents its planning folder
  location in the main checkout. Add `--planning-location <folder>` when the
  documented location is not `.scratch`. The plan inspects the planning
  folders, `.scratch/<issue>-<slug>/` by default, in the main checkout, in
  the current worktree, and in each worktree that it would otherwise remove,
  and keeps a worktree that holds a kept folder. With `--main-only`, it does
  not inspect the current worktree. Outside the main checkout, it then removes
  only the folders of a worktree that it removes, because the worktree
  removal deletes them.
- Add `--remote <name>` when the upstream remote is not `origin`.
- If the command fails, remove nothing and report the error.

The plan keeps the current worktree and each worktree that another live
session may use, with the evidence: a Git lock, a running process in the
worktree, or a Claude Code or Codex session log or an Antigravity
conversation of the last 60 minutes. When only session logs and Antigravity
conversations keep a worktree, the reason gives the time when their 60-minute
window ends, or says that the end is unknown. It keeps each worktree that
holds a lead state of t3-project-lead,
`.scratch/<YYYYMMDD>-lead-<slug>/state.json`, also with `--main-only`. It
reads each lead state, also the one in the main checkout, and keeps each
worktree whose path a task records while the task is not `settled`. Session
logs and Antigravity conversations do not keep a worktree when each task that
records its path is in an accepted state: `verified`, `closed-out`, or
`settled`, and not cancelled. The workers of such a task have ended their
sessions. The rule for a task that is not `settled` decides first, so the
accepted-state rule frees the worktree of a `settled` task. A Git lock or a
running process still keeps the worktree. When a `.scratch` folder, a lead
folder, or a lead state cannot be read, the plan keeps every worktree that it
would otherwise remove.
It reads the T3 Code threads of the repository with the `t3` CLI,
`T3CODE_CLI_PATH` or else `t3` on `PATH`, and keeps each worktree that a
thread owns while the thread is not `settled`. Without the CLI, or for a
repository that is no T3 Code project, this rule keeps nothing. When the CLI
fails, for example while the T3 Code app is closed, the plan keeps every
worktree that it would otherwise remove.
It keeps a worktree whose folder contains another worktree that Git lists. It
keeps a worktree with a detached HEAD or uncommitted changes. A branch is
merged when a merged PR of the branch has the branch tip as its head commit
(`headRefOid`). The plan also treats a branch as merged when its tip is in
the Default Branch or is the head commit of any merged PR: such a branch has
no commit of its own. The plan keeps such a branch when its reflog shows that
it was created less than 60 minutes ago. When a check cannot run, the plan
keeps the item and gives the error as the reason.
The plan removes each `branch.<name>` section of the Git config whose local
branch does not exist. `git branch -D` deletes a branch and exits 0 also when
it cannot lock the Git config, for example in a sandbox. It then prints
`could not lock config file`, and the section `branch.<name>` stays.

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
4. Remove the `branch.<name>` sections of the Git config:
   1. Run the plan command again with `--config-sections`. It prints only the
      `config-section` lines, also one for each section that step 3 left.
   2. Remove each section that it lists with
      `git config --remove-section <section>`. The output `no such section`
      means that the section is already gone.
   3. When the output is `could not lock config file`, Git cannot lock the
      Git config, for example in a sandbox. Remove no other section. Report
      each section that stays with the error, which names the file of the
      Git config. Then go on with step 5.
5. Delete each `remote-branch` `<remote>/<name>` from the upstream remote
   with `git push <remote> --delete <name>`.

- When the reason of a kept worktree gives the time when its 60-minute window
  ends, do not ask the user to remove the worktree. Do these steps once:
  1. Wait until the latest such time.
  2. Run the plan command again with the same options.
  3. Act on its new `REMOVE` lines in the order above.
- Fast-forward a clean Default Branch when it is behind. Preserve repository data
  whenever cleanup or branch state is unsafe or uncertain.
- Report what was cleaned and retained: each `KEEP` line with its reason.
  Include issue and PR links, verified closures, and issues left open.
