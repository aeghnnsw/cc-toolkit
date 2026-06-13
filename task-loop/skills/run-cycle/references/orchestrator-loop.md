# Orchestrator loop — state machine & coordination protocol

Detailed reference for `run-cycle`. The orchestrator is the **single coordinator**, **single
sequencer**, and **sole integrator**. It runs under built-in `/loop` (self-paced); each wake is
one turn. All durable truth lives in git, GitHub (the control issue + per-task issues), and the
numbered records — never only in conversation memory.

## Fast state (rebuilt every turn)

The authoritative fast state is reconstructed by replaying the control issue:

```python
import sys; sys.path.insert(0, "<plugin>/scripts")   # ${CLAUDE_PLUGIN_ROOT}/scripts when set
import control_log, gh_store
raw = gh_store.read_comments(CONTROL_ISSUE)                       # [(id, created_at, body), ...]
events = [e for (_id, _ts, body) in raw for e in control_log.parse_events(body)
          if e.get("kind") == "control"]
state = control_log.replay(events)
# -> current_plan_revision, current_proposal_sha, last_seq, tasks{task_id:{status,issue_number,
#    plan_revision,pr_head_sha}}, seen_source_uuids, source_uuid_to_seq, scan_floor_ts_by_issue
```

`orchestrator-state.json` (in `.claude/task-loop/`, gitignored) is a **cache** of this plus the
lease — never the source of truth. Shape:

```json
{
  "lease": {"owner": "<id>", "started_at": "<utc>", "expires_at": "<utc>", "heartbeat": "<utc>"},
  "phase": "dispatching|waiting|idle|draining|exiting_pending|exiting",
  "current_plan_revision": 0,
  "active_worker_ids": [],
  "next_wake_reason": "",
  "drain_deadline_at": null
}
```

## State machine

- **dispatching** — ready work exists, no stop signal → create tasks + spawn workers.
- **waiting** — active workers exist → wait on automatic teammate idle notifications.
- **idle** — no ready work, no active workers, no stop signal → long `ScheduleWakeup` (e.g.
  1200–1800 s); **do not exit** (continuous service).
- **draining** — `stop-request.json` observed → no new dispatch; wait for active workers, bounded
  by `drain_deadline_at`.
- **exiting_pending** — drain complete → record the pre-exit audit, `ScheduleWakeup` a 60–120 s
  cooldown.
- **exiting** — re-audit still clean → stop rescheduling (the run ends). If anything changed,
  revert to `dispatching`/`waiting`.

## Per-turn algorithm

### 1. Lease & rebuild
- Read `orchestrator-state.json`. If a **live** lease (`expires_at` in the future) is owned by a
  different instance → exit (never two orchestrators). Else acquire/refresh the lease
  (`owner`, `started_at`, `expires_at = now + TTL`, `heartbeat = now`).
- On resume / stale lease (`expires_at` past, or `phase: exiting` without a clean prior audit):
  take over, then **rebuild fast state from the control issue** (above). Do not trust a stale
  cache.

### 2. Stop check
- If `.claude/task-loop/stop-request.json` exists → set `phase: draining`.

### 3. Event-drain & ingest (also the pre-merge barrier)
For each known task issue (every `tasks[*].issue_number`):
- `comments = gh_store.read_comments(issue)`; `window =
  control_log.comments_at_or_after_watermark(comments, state["scan_floor_ts_by_issue"].get(issue, ""))`.
- Parse inbox events: `inbox = [e for (_i,_t,b) in window for e in control_log.parse_events(b)
  if e.get("kind")=="inbox"]`; `fresh = control_log.filter_new_inbox(inbox, state["seen_source_uuids"])`.
- **Process `PLAN_FINDING` before `MERGE_REQUEST`** within the batch (findings can invalidate a
  pending merge). For each fresh inbox event, **emit exactly one source-tagged control event**
  (see §Emitting), carrying `source_issue`, `source_comment_id` (the gh comment node-id),
  `source_comment_ts` (the comment's `createdAt`), and `source_uuid` (= the inbox `uuid`).
  Verify completeness with `control_log.unacknowledged_uuids(fresh, emitted)` — it must be empty.
- **Advance the scan floor** for each issue: once every comment with `createdAt <= T` on that
  issue has exactly one source-tagged control event, emit
  `INBOX_SCAN_CHECKPOINT{issue_number, through_ts: T}`. Never checkpoint past an un-acked comment.

### 4. Replan barrier (before any dispatch)
- Read `docs/task-loop/directions.md` first — human steering overrides the default heuristic.
- If an ingested `PLAN_FINDING` invalidates a hypothesis: pressure-test with
  `dev-skills:discuss-with-codex`; if confirmed, **materialize** the new revision —
  author + `gh pr merge` the proposal-update PR to `master` (orchestrator is the sole editor of
  `proposal.md`), then emit `PLAN_REVISION_BUMP{plan_revision: N, proposal_sha: <merged SHA>}`.
- Recompute the dependency frontier from the Roadmap + declared `depends_on_tasks` /
  `depends_on_hypotheses`. Mark every task in the invalidated subgraph `TASK_STALE` and **halt
  its dispatch**. If a finding's blast radius can't be mapped confidently, **freeze broadly**.

### 5. Dispatch (skip if draining)
- Choose ready tasks: dependencies complete, not currently active, and revision-compatible
  (`spawned_plan_revision` would be the current `plan_revision`). Honor `directions.md` priority.
- Cap concurrency at the **frontier width** (a small bound, e.g. ≤5). For each chosen task:
  - Ensure its GitHub task issue exists (`gh issue create`, label `loop:in-progress`).
  - Emit `TASK_CREATED{task_id, plan_revision, issue_number}` and `TASK_DISPATCHED{task_id,
    plan_revision}`.
  - Spawn **one** `cycle-worker` teammate (`agentType: cycle-worker`) with a prompt carrying
    `task_id`, `issue=<n>`, `spawned_plan_revision=<current>`, and the task scope. Record its id
    in `active_worker_ids`.

### 6. Merge (sole integrator, on a `MERGE_REQUEST`)
A `MERGE_REQUEST` was ingested in §3. Merge only after that drain, atomically:
- Re-confirm the task is **revision-compatible** (`spawned_plan_revision == current_plan_revision`
  or explicitly `TASK_REVISION_COMPATIBLE`) and not `TASK_STALE`.
- Confirm CI/review state and that the worker's Codex PR review had no blocking issues.
- Merge bound to the validated head: `gh pr merge <N> --squash --delete-branch
  --match-head-commit <pr_head_sha>`. If the head changed since validation, the guard fails →
  re-drain and re-validate (the worker will have minted a fresh attempt UUID).
- Emit `MERGE_GRANTED{task_id, plan_revision, pr_head_sha, source_*}`. If invalid, emit
  `MERGE_DENIED{... source_*}` + `TASK_STALE`, and message the worker to stop/rescope.
- After merge, set the task's `RECOVERY` / `NNN_log.md` to complete and remove the worker from
  `active_worker_ids`.

### 7. Wait / idle / exit
- **Active workers exist** → `waiting`: rely on automatic idle notifications; set a long
  `ScheduleWakeup` fallback. Drop `active_worker_ids` entries as workers report and are merged.
- **Frontier empty, none active, no stop signal** → `idle`: long `ScheduleWakeup`; **do not exit**.
- **draining** → dispatch nothing; wait for active workers until `drain_deadline_at`; past the
  deadline, mark overdue workers `orphaned_acknowledged` (record worktree/issue/PR pointers — no
  abrupt kill) and proceed.
- **Drain complete** → `exiting_pending`: run the **pre-exit audit** (below), record real command
  outputs into a decision record, `ScheduleWakeup` a 60–120 s cooldown.
- **Cooldown wake** → re-run the audit from scratch. Still clean → `exiting`: stop rescheduling.
  Anything changed → revert to `dispatching`/`waiting`.

### 8. Heartbeat
Refresh the lease `heartbeat`/`expires_at` and persist the `orchestrator-state.json` cache.

## Emitting control events

Only the orchestrator writes the control issue, and it alone assigns `seq`:

```python
stamped, new_last = control_log.assign_seq([{
    "kind": "control", "type": "MERGE_GRANTED", "task_id": "T7", "plan_revision": 3,
    "pr_head_sha": sha, "source_issue": 42, "source_comment_id": node_id,
    "source_comment_ts": created_at, "source_uuid": inbox_uuid,
    "ts": "<YYYY-MM-DDTHH:MM:SSZ>",
}], state["last_seq"])
gh_store.post_comment(CONTROL_ISSUE, control_log.format_event(stamped[0]))
```

Event types — **orchestrator-originated** (no source): `TASK_CREATED` (carries `issue_number`),
`TASK_DISPATCHED`, `PLAN_REVISION_BUMP` (carries `proposal_sha`), `TASK_STALE`,
`TASK_REVISION_COMPATIBLE`, `INBOX_SCAN_CHECKPOINT` (carries `issue_number` + `through_ts`).
**Inbox-derived** (carry `source_*`): `MERGE_GRANTED`, `MERGE_DENIED`, `PLAN_FINDING_RECORDED`.
`replay` validates the schema and raises on a seq gap/dup, a duplicate `source_uuid`, a
checkpoint for an unknown/regressing issue, or a non-canonical timestamp.

## Pre-exit audit (recorded, real outputs)

Before writing `phase: exiting`, prove with actual command output (`superpowers:verification-
before-completion`): `ready == 0` (no dispatchable tasks), `active == 0`
(`active_worker_ids` empty, no open `loop:in-progress` without a merged PR), `blocked ==
acknowledged` (every blocked/stale task has a follow-up), `unmerged == 0` (no open PR awaiting a
`MERGE_REQUEST`). Re-run it after the cooldown; only an all-clear second pass permits exit.

## Recovery (cold resume)

A fresh orchestrator on clean `master` rebuilds entirely from: the control issue (replay →
revision, dedupe set, scan floors, task statuses), per-task `RECOVERY` ledgers (issue bodies),
open PRs, and `docs/task-loop/logs/`. Ephemeral teammates and `~/.claude/tasks/` are **not**
relied upon — respawn `cycle-worker`s for still-open tasks. A worker found in `pr_open` /
`merge_requesting` (via its `RECOVERY`) is *ready but unannounced*: drive it to merge. The
planning step is idempotent — the same frontier is recomputed and only missing workers respawn.

## Deliberate with Codex

Use `dev-skills:discuss-with-codex` for: ambiguous task selection / "are these two tasks truly
independent?" / dependency ordering; confirming a hypothesis invalidation before a
`PLAN_REVISION_BUMP`; and resolving conflicting worker outcomes. Record dispositions in the
decision record.
