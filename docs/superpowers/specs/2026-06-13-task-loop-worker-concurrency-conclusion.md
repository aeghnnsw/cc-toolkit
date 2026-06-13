# task-loop worker isolation & per-cycle records — Codex deliberation conclusion

**Date:** 2026-06-13 · **PR:** #121 (`bugfix-worker-worktree-and-log-naming`) ·
**Outcome:** converged after 6 rounds (Codex: `NO FURTHER OBJECTIONS`).

Pressure-test of two fixes — (1) declared `isolation: worktree` for the worker + drop manual
worktree creation, (2) consolidate the per-cycle rubric+log into one iteration-indexed record.
The review went well past the diff and exposed five concurrency/correctness holes in the broader
worker↔orchestrator protocol. The throughline: **stop protecting shared mutable state with
assumptions; either make state durable in the sequenced log, or give each attempt its own
non-shared surface.**

## Settled position — what PR #121 (and its follow-ups) must contain

**A. Worker worktree isolation — declared *and* verified.**
- `cycle-worker` declares `isolation: worktree`; the worker never creates one manually.
- **Runtime self-check (defense against silent non-isolation):** the orchestrator passes
  `lead_worktree_root` (its own `git rev-parse --show-toplevel`) in every spawn prompt. The
  worker runs `git rev-parse --show-toplevel` **before any checkout**; if it equals the lead
  root, it **stops and escalates `WORKTREE_ISOLATION_FAILED`** — never edits/pushes (prevents
  cross-task filesystem/index races the head-SHA merge gate cannot detect).
- **Phase-0 isolation probe** (hard READY gate): spawn two plugin-provided isolated probe
  teammates; require distinct `--show-toplevel` values, both ≠ lead root. "Agent Teams enabled"
  alone is **not** READY.

**B. Per-attempt surfaces — no shared writable refs or bodies.**
- **Per-attempt remote branches:** each attempt pushes only to `<det>-attempt-<attempt_id>`.
  Unique names mean a superseded worker can physically only touch its own dead branch — it can
  never clobber the current attempt's branch. (Replaces the earlier *shared* deterministic
  branch, which a stale worker or a check-then-act fence could not protect.)
- **PR per attempt;** the orchestrator merges **only the current attempt's** PR (`attempt_id ==
  current_attempt_id`) and denies stale-attempt `MERGE_REQUEST`s (on top of UUID dedupe +
  `--match-head-commit`).
- **Continuity without sharing:** a new attempt may branch *from* the latest GitHub-visible
  attempt branch when the orchestrator passes `adopt_from_branch` (Option-1 still holds:
  local-only pre-PR WIP is disposable; only pushed/PR'd work is adopted). Adoption is a *read* of
  another branch, never a *write* to it.
- **RECOVERY is per-attempt append-only comments** (attempt_id-tagged, non-control, no seq) —
  not a shared last-writer-wins issue body. The orchestrator reads the latest recovery comment
  for the current attempt. (This removes the body-overwrite race.)

**C. Durable attempt ownership (the fence — now defense-in-depth, not the safety basis).**
- `attempt_id` is a **required field on the sequenced `TASK_DISPATCHED`**; `replay()` stores
  `state["tasks"][task_id]["current_attempt_id"]` (latest dispatch wins).
- The worker re-checks `attempt_id == current_attempt_id` before every side effect (the existing
  `spawned_plan_revision` boundary check, extended to attempts); if superseded it records
  `superseded_attempt` and stops. Inbox events carry `attempt_id`; the orchestrator ignores/denies
  stale ones. Safety now comes from **unique per-attempt surfaces + current-attempt-only merge**,
  with the fence avoiding wasted work.
- **Phase-0 ephemerality** ("teammates die with the lead") is a **hard READY gate** — it keeps
  the two-workers-coexist window rare; the per-attempt surfaces make it *safe* when it occurs.

**D. Iteration index — a real protocol field (not prose).**
- Add `iteration` to `_REQUIRED_FIELDS["TASK_CREATED"]` and `_INT_FIELDS`; `replay()` stores
  `state["tasks"][task_id]["iteration"]`. Add replay tests (cold replay preserves it;
  missing/non-int raises). Docs: `TASK_CREATED{task_id, plan_revision, issue_number, iteration}`.
- `NNN` is the zero-padded iteration index from `001`, **assigned once at `TASK_CREATED`**,
  recovered by `replay()`, **reused on re-dispatch** (per-task slot, not per-attempt). This
  dissolves the earlier circularity (an abandoned no-artifact task still has its NNN in the log).
- **`docs/task-loop/logs/` is audit-only, not a recovery source.** One record per cycle,
  `<NNN>_<task>.md`, with a **Rubric** section (authoritative) and a **Decision log** section;
  the issue-posted rubric is a verbatim published copy, the file is the source of truth.

## Strongest objections & how each resolved

1. **Iteration index unrecoverable** — `replay()` never stored it; the logs/ fallback was
   circular. → Make `iteration` a real required/int/replay-stored field; logs/ audit-only.
2. **Stale worktree holds the branch hostage** — `git checkout -B <det>` fails if another
   worktree has `<det>` checked out (reproduced). → Decouple local (attempt-scoped) from remote
   branch; ultimately → per-attempt remote branches.
3. **`isolation: worktree` is an unverified SPOF** — silent non-isolation → workers race the lead
   cwd; merge gate can't catch cross-task contamination. → Runtime self-check vs `lead_worktree_root`
   + Phase-0 probe (hard gate).
4. **Remote branch ownership not durably exclusive** — "one worker per task" was session memory.
   → Durable `attempt_id` fence on the sequenced log.
5. **Fence is check-then-act, not atomic on shared surfaces** — a superseded worker can push/
   overwrite before its next check. → Eliminate shared surfaces: per-attempt branches +
   append-only per-attempt recovery comments.

## Unresolved tensions

None at protocol level. Remaining work is implementation + test coverage (Codex's closing words).

## Scope note (essential-vs-follow-up)

PR #121's *original* intent (worktree isolation + one-file record) should land with the items it
directly depends on: **A** (isolation declared+verified), the **iteration field D** (small,
tested `control_log.py` change), and the **per-attempt branch** core of **B**. The fuller
**attempt-ownership protocol (C)** and **RECOVERY-as-append-only-comments** touch the merged
#118/#120 protocol broadly and are best staged as a focused follow-up PR rather than silently
ballooning #121 — but the design above is the agreed target.

How it ended: **converged after 6 rounds** — `NO FURTHER OBJECTIONS`.
