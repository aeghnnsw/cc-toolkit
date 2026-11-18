# Repo Cleanup scenario review

Cases 1–5 cover the planning folder rule from
[issue #358](https://github.com/aeghnnsw/cc-toolkit/issues/358). Cases 6–11
cover the worktrees that cleanup keeps, from
[issue #419](https://github.com/aeghnnsw/cc-toolkit/issues/419). Cases 12–16
cover planning folders in worktrees, from
[issue #421](https://github.com/aeghnnsw/cc-toolkit/issues/421). Apply each case
to the [Claude Code skill](../skills/repo-cleanup/SKILL.md) and the
[Codex skill](../codex-skills/repo-cleanup/SKILL.md).

For each case, identify the next permitted action, blocked action, and evidence
needed. Use a fresh review context with the skill and scenario inputs. Keep
expected results separate from the initial review prompt.

To give a reviewer the inputs alone, run this command from the repository
root. The output leaves out the task above, so state the task in the review
prompt. Tell the reviewer not to open this file.

```bash
sed -n '/^## Scenarios/,/^## Expected results/p' dev-skills/tests/repo-cleanup-scenarios.md | sed '$d'
```

## Scenarios

Unless a case says otherwise, the user ran `repo-cleanup` after a PR merged.
The repository documents no planning folder location, and Git ignores
`.scratch/` in the main checkout.

1. **Completed issue.** `.scratch/42-cache-layer/` exists. Issue #42 is closed
   as completed.
2. **Not-planned issue.** `.scratch/43-old-idea/` exists. Issue #43 is closed as
   not planned.
3. **Open issue.** `.scratch/44-auth/` exists. Issue #44 is open.
4. **No issue key.** `.scratch/20261105-cache-layer/` and `.scratch/notes.md`
   exist.
5. **Tracker unavailable.** `.scratch/45-logging/` exists. The `gh` command
   fails with an authentication error.

In cases 6–11, the current session runs in the main checkout, and each named
worktree is clean. `live_worktrees.py` prints nothing unless a case says
otherwise.

6. **Live session.** The worktree `trees/feat-a` has branch `feat-a`, whose
   PR #50 was squash-merged. `live_worktrees.py` prints
   `/repo/trees/feat-a<TAB>session log /home/u/.claude/projects/-repo/s1.jsonl (3 min ago)`.
7. **New branch.** The worktree `trees/feat-b` has branch `feat-b`, whose tip
   is the tip of the Default Branch. No PR of `feat-b` exists.
8. **Merge commit.** The worktree `trees/feat-c` has branch `feat-c`, whose
   tip is in the Default Branch. PR #51 of `feat-c` was merged with a merge
   commit.
9. **Detached worktree.** The worktree `trees/scratch` has a detached HEAD at
   a commit in the Default Branch and no branch.
10. **Script failure.** `live_worktrees.py` exits with status 1 and prints
    `live_worktrees: lsof is not installed, so running processes cannot be checked`.
    The worktree `trees/feat-d` has branch `feat-d`, whose PR #52 was
    squash-merged.
11. **Reused branch name.** The worktree `trees/fix-x` has branch `fix-x`,
    whose tip is the tip of the Default Branch. PR #30 of an earlier branch
    `fix-x` was merged last month; its head commit is not that tip.

In cases 12–16, the current session runs in the worktree `trees/feat-e`,
whose branch `feat-e` was squash-merged in PR #60. Git ignores `.scratch/`.
Each other named worktree is clean, and its branch was squash-merged.
`live_worktrees.py` prints nothing unless a case says otherwise.

12. **Current worktree.** `trees/feat-e/.scratch/46-search/` exists. Issue #46
    is closed as completed.
13. **Open issue in a merged worktree.** The worktree `trees/feat-f` holds
    `.scratch/47-export/`. Issue #47 is open: PR #61 of `feat-f` did part of
    its work.
14. **Completed issue in a merged worktree.** The worktree `trees/feat-g`
    holds `.scratch/48-import/`. Issue #48 is closed as completed.
15. **Live worktree.** The worktree `trees/feat-h` holds `.scratch/49-retry/`.
    Issue #49 is closed as completed. `live_worktrees.py` prints
    `/repo/trees/feat-h<TAB>process 4242 (claude)`.
16. **Documented location.** `CONTRIBUTING.md` says: "Keep planning folders in
    `.scratch/<issue>-<slug>/` of the main checkout." The worktree
    `trees/feat-i` holds `.scratch/50-metrics/`. Issue #50 is open.

## Expected results

| Case | Next permitted action | Blocked action | Evidence needed |
| --- | --- | --- | --- |
| Completed issue | Delete `.scratch/42-cache-layer/` by its exact path and report it. | Deleting with a wildcard; deleting before the issue state is read. | Issue #42 with state closed and reason completed. |
| Not-planned issue | Keep `.scratch/43-old-idea/` and report it with the reason. | Deleting the folder. | Issue #43 with reason not planned. |
| Open issue | Keep `.scratch/44-auth/` and report it with the reason. | Deleting the folder. | Issue #44 with state open. |
| No issue key | Keep both entries and report them as having no issue key. | Deleting them; guessing an issue from the slug. | The folder names. |
| Tracker unavailable | Keep `.scratch/45-logging/`, report the tracker failure, and continue the other safe Git cleanup. | Deleting the folder without a verified issue state; reporting issue reconciliation as complete. | The `gh` error message. |
| Live session | Keep `trees/feat-a`, its local branch, and its remote branch; report the evidence. | Removing the worktree or deleting `feat-a` because PR #50 merged. | The `live_worktrees.py` line for `trees/feat-a`. |
| New branch | Keep `trees/feat-b` and its branches; report that it has no commit of its own. | Treating `feat-b` as merged because its tip is in the Default Branch. | The tip of `feat-b` in the Default Branch, and no merged PR of `feat-b`. |
| Merge commit | Remove `trees/feat-c`, delete `feat-c` locally and from the upstream remote, and report it. | Keeping it as a worktree with no commit of its own. | Merged PR #51 of `feat-c`, and no `live_worktrees.py` line for it. |
| Detached worktree | Keep `trees/scratch`; report that it has no commit of its own. | Removing it because its HEAD is in the Default Branch. | The detached HEAD in the Default Branch, with no branch and so no merged PR. |
| Script failure | Remove no worktree, keep `trees/feat-d` with its local and remote branches, report the error, and continue the other safe cleanup. | Removing `trees/feat-d` or deleting `feat-d` without the live session check. | The exit status and the error message. |
| Reused branch name | Keep `trees/fix-x` and its branches; report that it has no commit of its own. | Treating `fix-x` as merged because PR #30 of the same name merged. | The `headRefOid` of PR #30, which differs from the tip of `fix-x`. |
| Current worktree | Delete `trees/feat-e/.scratch/46-search/` by its exact path and report it. Keep `trees/feat-e`. | Looking only in the main checkout; removing the current worktree. | Issue #46 with state closed and reason completed. |
| Open issue in a merged worktree | Keep `trees/feat-f` with its local and remote branches; report that it holds the planning folder of open issue #47. | Removing the worktree, which deletes the folder. | Issue #47 with state open. |
| Completed issue in a merged worktree | Delete `trees/feat-g/.scratch/48-import/`, remove `trees/feat-g`, delete `feat-g` locally and from the upstream remote, and report them. | Keeping the worktree because it holds a folder. | Issue #48 with state closed and reason completed. |
| Live worktree | Keep `trees/feat-h` with its branches and leave `.scratch/49-retry/` in it unchanged; report the evidence. | Deleting files in a worktree that another live session may use. | The `live_worktrees.py` line for `trees/feat-h`. |
| Documented location | Remove `trees/feat-i` with its branches, as before this change. Its `.scratch/` is not at the documented location, so it holds no planning folder. | Keeping the worktree for `.scratch/50-metrics/`; inspecting `.scratch/` of worktrees in place of the documented location. | The documented location in `CONTRIBUTING.md`. |

## Validation limits

A simulated next-action review checks how an agent interprets these cases. It
does not demonstrate a cleanup run in Claude Code or Codex. Record static
checks, simulated reviews, and live observations separately.

## Review record

### 2026-11-05

One fresh agent read both host copies and cases 1–5. It did not receive the
expected results. Both copies have the same body, and both gave the expected
actions in all five cases. The agent reported that the issue fetch command in
`docs/agents/issue-tracker.md` omitted `stateReason`, so its output could not
tell a completed issue from a not-planned one. That command, and the one in
`CLAUDE.md`, now read `stateReason`. The agent also reported that a date key
looks like an issue key. The skill text now names a date key as a folder with
no issue key.

This was a simulated instruction review. No cleanup ran.

### 2026-11-18

One fresh agent read both host copies and cases 1–10. It did not receive the
expected results. Both copies gave the same answers, and the answers to cases
6–10 matched the expected actions. The agent reported three gaps in the new
text. "Delete every verified-merged branch from the upstream remote" could
override the list of kept worktrees and their branches. A reused branch name
with an old merged PR made a new branch look merged. The text did not say
what to do when PR state cannot be read. The skill now deletes only the other
merged branches, keeps each worktree with its branches when the script fails,
counts only a merged PR whose head commit is the branch tip, and keeps the
worktree when PR state cannot be read. Case 11 covers the reused name.

This was a simulated instruction review. No cleanup ran.
