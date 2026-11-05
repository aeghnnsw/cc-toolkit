# Repo Cleanup scenario review

These cases cover the planning folder rule from
[issue #358](https://github.com/aeghnnsw/cc-toolkit/issues/358). Apply each case
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

## Expected results

| Case | Next permitted action | Blocked action | Evidence needed |
| --- | --- | --- | --- |
| Completed issue | Delete `.scratch/42-cache-layer/` by its exact path and report it. | Deleting with a wildcard; deleting before the issue state is read. | Issue #42 with state closed and reason completed. |
| Not-planned issue | Keep `.scratch/43-old-idea/` and report it with the reason. | Deleting the folder. | Issue #43 with reason not planned. |
| Open issue | Keep `.scratch/44-auth/` and report it with the reason. | Deleting the folder. | Issue #44 with state open. |
| No issue key | Keep both entries and report them as having no issue key. | Deleting them; guessing an issue from the slug. | The folder names. |
| Tracker unavailable | Keep `.scratch/45-logging/`, report the tracker failure, and continue the other safe Git cleanup. | Deleting the folder without a verified issue state; reporting issue reconciliation as complete. | The `gh` error message. |

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
