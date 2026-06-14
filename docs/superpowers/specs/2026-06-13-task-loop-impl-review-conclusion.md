# task-loop PR #121 — implementation review (Codex) conclusion

**Date:** 2026-06-13 · **PR:** #121 (`bugfix-worker-worktree-and-log-naming`) ·
**Outcome:** converged — fresh-thread Codex review returned `NO FURTHER OBJECTIONS`.

This reviewed the **implementation** (the committed diff), after the prior round reviewed and
converged on the **design**. Codex found concrete code/doc bugs the design review couldn't — most
notably a real protocol bug in the status reducer. All were fixed.

## Bugs found & fixed (in order surfaced)

**Round 1 (control_log + recovery protocol)**
1. **Recovery comments weren't an executable protocol** — docs said "fenced `task-loop-recovery`
   JSON" but the example was YAML-ish and there was no parser. → Added `RECOVERY_FENCE`,
   `format_recovery` / `parse_recovery` / `latest_recovery(comments, attempt_id)` (latest-wins,
   ignores other attempts; consumes `read_comments` oldest-first), with tests; skeleton example is
   now one exact fenced-JSON block.
2. **`attempt_id` not type-checked** — `_validate` only rejected None/"". → Added `_STR_FIELDS`;
   a non-string `attempt_id` now raises.
3. **Permissive replay** — `TASK_DISPATCHED` before `TASK_CREATED` produced an active task with
   `issue_number=None`. → `replay` now rejects a non-`TASK_CREATED` task event for an unestablished
   task.

**Round 2 (executability + consistency)**
4. **Per-attempt PR command wrong** — pushed the per-attempt branch but opened the PR with a bare
   `gh pr create` (would infer the wrong head). → Explicit `gh pr create --head
   <branch>-attempt-<id> --base master`; no-adoption checkout is explicit `git checkout -B <local>
   origin/master`.
5. **Doc sweep too narrow** — stale spawn payloads/examples remained (cycle-worker example blocks,
   the replay state-shape comment, run-cycle dispatch/merge summaries, helpers list). → Swept and
   fixed.
6. **"iteration assigned once" unenforced** — a duplicate `TASK_CREATED` would overwrite
   `issue_number`/`iteration`. → `replay` now rejects duplicate `TASK_CREATED`, with a test.

**Round 3 (contradiction + spec)**
7. **Failed-fence contradiction** — the worker was told both "post nothing further" and "post a
   terminal recovery comment" on a stale/superseded fence; since recovery comments are the durable
   surface, "post nothing" would strand the orchestrator. → Resolved: post **exactly one** terminal
   `task-loop-recovery` comment (`stale_revision_blocked` / `superseded_attempt`), then push/PR/post
   nothing.
8. **Design-spec stale summaries** — worker-cycle step 10, inbox-event definition, and the
   cycle-worker system-prompt summary still showed the no-attempt / issue-body / `NNN_*` model. →
   Updated. E2E test inbox fixtures now carry `attempt_id` + `spawned_plan_revision`.

**Fresh-thread verification (the highest-value catch)**
9. **`MERGE_DENIED` auto-staled the task** — `_STATUS_BY_TYPE` mapped `MERGE_DENIED → "stale"`, but
   the new model also emits `MERGE_DENIED` for a **superseded-attempt** denial, where the task is
   still active under the current attempt. Auto-staling there wrongly kills a live task (and the
   genuine-invalid path already emits an explicit `TASK_STALE`, so it was also redundant). →
   Dropped `MERGE_DENIED` from `_STATUS_BY_TYPE`; status changes only via explicit `TASK_STALE`.
   Tests split into "MERGE_DENIED alone leaves task active (still acked)" + "MERGE_DENIED +
   TASK_STALE ⇒ stale".
10. **`MERGE_GRANTED` emitted twice** — the rewritten post-merge cleanup line re-stated "emit
    `MERGE_GRANTED`" after the merge step already emitted it → duplicate `source_uuid` (which
    `replay` rejects). → Emit exactly once; the post-merge line only removes the worker + cleans the
    worktree.
11. **README test-count drift** — said "45 unit tests". → Now 58.

## Final state

- `control_log.py` is the only protocol code changed; **58 unit tests pass**.
- Live skill docs (cycle-worker, skeleton, run-cycle + orchestrator-loop, preflight, spec) are
  internally consistent with the per-attempt / recovery-comment / iteration model.
- Fresh-thread Codex verification: `NO FURTHER OBJECTIONS`.

## Process note

`codex exec resume` returned a **stale (cached) reply** on the verification turn — byte-identical to
the prior round despite the files having changed. Worked around it by spawning **fresh** `codex exec`
threads for verification (independently confirmed each fix with `grep`/tests first). Recommend
preferring fresh threads over `resume` for "re-check after edits" passes.

How it ended: **converged** — fresh-thread `NO FURTHER OBJECTIONS`.
