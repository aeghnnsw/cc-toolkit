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
#    plan_revision,pr_head_sha,iteration,current_attempt_id}}, seen_source_uuids,
#    source_uuid_to_seq, scan_floor_ts_by_issue
```

**No local files.** The only mutable runtime cell is the **control-issue body runtime header** — a
fenced ` ```task-loop-runtime ` JSON block the orchestrator (Loop A) is the **sole writer** of.
Everything else is the append-only comment log (replayed above) or live session memory; nothing is
written to local disk. Header shape:

```json
{
  "lease": {"owner": "<id>", "expires_at": "<utc ~2x poll>"},
  "last_turn_started_at": "<utc>",
  "last_turn_completed_at": "<utc>",
  "next_wakeup_at": "<utc>",
  "phase": "dispatching|waiting|idle|draining|exiting_pending|exiting",
  "stop_at": "<utc>",
  "drain_deadline_at": null,
  "stop_schedule_id": null
}
```

`phase`/`current_plan_revision`/`active_worker_ids` are **derived** (rebuilt by `replay` + session
memory). The header is **soft, advisory, last-writer-wins**, and the orchestrator is its **sole
writer** — it persists only the lease plus diagnostics a *human or the resume preflight* reads; **no
sibling job consumes it** (there is no watchdog). `expires_at` (~2× the 1800 s poll) is the
single-coordinator TTL: a manual second `/run-cycle` start that finds it in the future exits.
`last_turn_started_at`/`last_turn_completed_at`/`next_wakeup_at` are **diagnostics** that make a manual
resume *informed* (sleeping vs hung-mid-turn vs dead) instead of guessing from one TTL — advisory
inputs, never proof. `stop_at` is the self-bound graceful-stop time; `stop_schedule_id` is the
scheduler handle the orchestrator uses to cancel/recreate **Loop B** (the stop early-wake) when
`stop_at` changes. See *Stop-time control*. Because writes are last-writer-wins and GitHub gives no
atomic CAS, the lease is a **soft** single-coordinator guard (the loser exits on the write-then-re-read
fence), not an atomic lock.

## State machine

**Two loops.** **Loop A** is this `/loop` orchestrator; every turn ends with a **fixed
`ScheduleWakeup(1800)`** (30 min). **Loop B** is a one-time stop early-wake at `stop_at` (see
*Stop-time control*). There is **no watchdog** — a fixed poll that re-derives the whole frontier each
tick makes an *alive-but-stuck* orchestrator structurally impossible *between* turns. It does **not**
cover an *intra-turn hang* (a `gh`/CI/spawn call that never returns before the turn reschedules): wrap
the orchestrator's own long calls in **best-effort command deadlines** and **reconcile any ambiguous
side effect on timeout** (re-inspect PR state before rescheduling) so a turn almost always returns to
schedule its next poll; a genuine hang or a dead session is then handled by **manual `/run-cycle`
resume** (a documented reduction vs the old watchdog).

**Dispatch is a seat-capped action, not a phase.** Every turn — *after* merging completions (§5) —
the orchestrator fills every **free worker seat** with a ready task, up to a **fixed cap of 5**
concurrent `cycle-worker` teammates (5 tasks in flight), **whether or not other workers are still
active**. It is **proactive** (a task unblocked this turn is dispatched this turn) but **bounded**
(never more than 5 *intentionally* per lead session — see §6 for the manual-double-start caveat) —
active workers never suppress dispatch of newly-ready work *as long as a seat is free*. `waiting` is
what the orchestrator does *after* it has filled every seat it can, not an alternative to dispatching.
Re-entering a turn always re-runs merge→dispatch first. The 5-seat cap is a **documented guideline in
this prompt, not a programmatically enforced limit**. **`phase: exiting` is a hard terminal guard** (a
stray/late wake reading a clean `exiting` re-audits and stops without dispatching — §7). The phases:

- **dispatching** — creating tasks + spawning workers for ready tasks this turn. Entered whenever
  any ready task exists and `stop_at` is not reached — **including while other workers are active**
  (a §5 merge or a freed concurrency slot just unblocked it).
- **waiting** — after filling every free seat, work is in flight → the **fixed `ScheduleWakeup(1800)`**.
  Idle notifications are **no longer part of the wake model**; every non-terminal phase uses the one
  fixed cadence. `waiting` never means "stop dispatching" — the next turn re-runs §5→§6 first.
- **idle** — no ready work, no active workers, `stop_at` not reached → the same **fixed
  `ScheduleWakeup(1800)`** (capped so it never sleeps past `stop_at`); **do not exit** (continuous
  service).
- **draining** — clock reached `stop_at` → no new dispatch; wait for active workers, bounded
  by `drain_deadline_at`.
- **exiting_pending** — drain complete → record the pre-exit audit, `ScheduleWakeup` a 60–120 s
  cooldown.
- **exiting** — re-audit still clean → stop rescheduling (the run ends). If anything changed,
  revert to `dispatching`/`waiting`.

## Per-turn algorithm

### 1. Lease & rebuild
- Read the **control-issue body header**. If a **live** lease (`expires_at` in the future) is owned
  by a different instance → exit (never two orchestrators). Else acquire/refresh the lease by writing
  the header (`owner`, `expires_at = now + TTL`, and the turn diagnostics `last_turn_started_at = now`
  and the `next_wakeup_at` you intend to schedule), then **re-read the header and confirm you still own
  it** before any side effect (the **write-then-re-read fence**; GitHub gives no atomic CAS, so this is
  how a lease loser detects it lost and exits).
- **On resume / stale lease, classify the prior lead from the advisory diagnostics (tri-state):**
  - **`likely_alive`** — `next_wakeup_at` **and** `expires_at` both in the future → the prior lead is
    sleeping normally → **default refuse** the takeover, but allow an **explicit human force-takeover**
    (the header is soft, so this is never an absolute block).
  - **`likely_dead`** — `now ≫ next_wakeup_at` (the lead missed its wake → hung or dead) or
    `expires_at` well past → acquire the lease but enter **observe/reconcile first** (do **not** eagerly
    mint attempts — §6's recovery-disposition substep gates re-dispatch).
  - The diagnostics are **advisory inputs, never proof** (the header is last-writer-wins and can be
    stale either way); human force is always available.
- After takeover, **rebuild fast state from the control issue** (replay the comment log, above).
  There is no local cache to distrust — fast state is always reconstructed from GitHub.

### 2. Stop check
- If the clock has reached `stop_at` → set `phase: draining`. (The orchestrator self-bounds; it
  also caps each `ScheduleWakeup` so it wakes by `stop_at` to drain on time.)

### 3. Event-drain & ingest (also the pre-merge barrier)
For each known task issue (every `tasks[*].issue_number`):
- `comments = gh_store.read_comments(issue)`; `window =
  control_log.comments_at_or_after_watermark(comments, state["scan_floor_ts_by_issue"].get(issue, ""))`.
- Parse inbox events: `inbox = [e for (_i,_t,b) in window for e in control_log.parse_events(b)
  if e.get("kind")=="inbox"]`; `fresh = control_log.filter_new_inbox(inbox, state["seen_source_uuids"])`.
- **Process `PLAN_FINDING` before `MERGE_REQUEST`** within the batch (findings can invalidate a
  pending merge).
- **Ack findings here; defer merge requests.** A fresh `PLAN_FINDING` is acked **in this step**
  with exactly one `PLAN_FINDING_RECORDED` (carrying `source_issue`, `source_comment_id` = the gh
  comment node-id, `source_comment_ts` = the comment's `createdAt`, `source_uuid` = the inbox
  `uuid`). A fresh `MERGE_REQUEST` is **not** acked here — it is a *pending decision* acked only
  by the merge gate (§5, `MERGE_GRANTED`/`MERGE_DENIED`), because the only legal source-tagged
  events for it are merge *outcomes*. `control_log.unacknowledged_uuids(fresh, emitted)` is used
  to **list the pending merge requests**, not as a must-be-empty gate. (Findings must fully ack;
  merge requests legitimately remain pending.)
- **Advance the scan floor** for each issue only through a **fully-acked prefix**: emit
  `INBOX_SCAN_CHECKPOINT{issue_number, through_ts: T}` only when every comment with
  `createdAt <= T` on that issue has exactly one source-tagged control event. An un-acked
  (pending) `MERGE_REQUEST` therefore **pins the floor before it**, so it is re-ingested
  (re-read + `filter_new_inbox`) every turn until the merge gate decides it — which is the
  intended behavior, not a leak.

### 4. Replan barrier (before any dispatch)
- Read `docs/task-loop/directions.md` first — human steering overrides the default heuristic.
- If an ingested `PLAN_FINDING` invalidates a hypothesis: pressure-test with
  `dev-skills:discuss-with-codex`; if confirmed, **materialize** the new revision. Use a
  **deterministic proposal-bump branch** (e.g. `chore-plan-revision-<N>`) so the side effect is
  reconcilable: if that PR is **already merged to `master` by the orchestrator** (crash-after-
  merge), just emit `PLAN_REVISION_BUMP{plan_revision: N, proposal_sha: <merged SHA>}`; otherwise
  author it, `gh pr merge` it (orchestrator is the sole editor of `proposal.md`), then emit the
  bump. Never emit the bump before the proposal PR is on `master`.
- Recompute the dependency frontier from the Roadmap + declared `depends_on_tasks` /
  `depends_on_hypotheses`. Mark every task in the invalidated subgraph `TASK_STALE` and **halt
  its dispatch**. If a finding's blast radius can't be mapped confidently, **freeze broadly**.

### 5. Merge first (sole integrator, on a pending `MERGE_REQUEST`)
**Integrate completions before dispatching** so a merge that finishes a dependency unblocks its
dependents **this same turn** (§6), never a turn later. A `MERGE_REQUEST` is pending (un-acked)
from §3. This step is the **only** place it is acked, and a `MERGE_GRANTED`/`MERGE_DENIED` is
emitted **only after the outcome is durable** — never a pre-merge "granted." Crash-safe via
idempotent reconciliation.
**Lease fence (required):** refresh + re-read the lease and re-confirm you still own it **at the
start of this step and again immediately before `gh pr merge`** — `gh pr merge` is the most
dangerous (irreversible) side effect and the turn-start lease alone is insufficient on a long turn.
A second lead shares this orchestrator's GitHub identity, so the `mergedBy == self` reconcile path
below **cannot** distinguish a valid prior owner from a stale owner who merged *after* losing the
lease — therefore the only defense is **not merging once the lease is lost**. If you've lost it,
abort the turn without merging or emitting. Act in this order:
- **Reject stale attempts first:** if the `MERGE_REQUEST`'s `attempt_id` !=
  `tasks[task_id].current_attempt_id`, the worker was superseded by a later dispatch → emit
  `MERGE_DENIED` (stale attempt) and stop. A superseded attempt could only have written its own
  per-attempt branch, so it can never affect the current attempt's branch/PR. (Every worker inbox
  event carries `attempt_id`; this is the gate that makes the durable single-flight token binding.)
  **`MERGE_DENIED` only acks the request — it does NOT stale the task** (`replay` no longer maps
  `MERGE_DENIED → stale`); the task stays `active` under the current attempt. Only the
  genuine-invalid path (below) pairs `MERGE_DENIED` with an explicit `TASK_STALE`.
- **Inspect PR state first** (`gh pr view <N> --json state,mergedAt,mergedBy,headRefOid`).
  - **Already merged by this orchestrator** at the recorded head (`mergedBy` == the orchestrator's
    own identity **and** `headRefOid`/merge commit == the validated `pr_head_sha`): a prior turn
    merged it and crashed before logging → just emit `MERGE_GRANTED` (reconcile).
  - **Already merged by anyone else** (human / auto-merge / merge queue / workflow): this is an
    **out-of-protocol merge** — do **not** certify it as `MERGE_GRANTED` (that would launder a
    merge that never passed the gates). **Halt and escalate to the user** (a human-only blocker);
    see the repo-settings precondition in `SKILL.md` that should make this impossible.
  - **Closed/superseded**, or the worker has minted a newer attempt UUID for a different head
    (the pending one is stale): emit `MERGE_DENIED` for the stale request.
  - **Open** → validate, then merge:
- Re-confirm the task is **revision-compatible** (`spawned_plan_revision == current_plan_revision`
  or explicitly `TASK_REVISION_COMPATIBLE`) and not `TASK_STALE`.
- Confirm CI/review state and that the worker's Codex PR review had no blocking issues.
- **Re-read the lease one last time (final fence) — if you no longer own it, do NOT merge** — then
  merge bound to the validated head: `gh pr merge <N> --squash --delete-branch
  --match-head-commit <pr_head_sha>`. If the head changed since validation, the guard fails →
  re-drain and re-validate (the worker will have minted a fresh attempt UUID).
- Emit `MERGE_GRANTED{task_id, plan_revision, pr_head_sha, source_*}` — **exactly once** per
  merged request (it is the durable completion marker, and re-emitting it would duplicate the
  request's `source_uuid`, which `replay` rejects). If invalid, emit `MERGE_DENIED{... source_*}` +
  `TASK_STALE`, and message the worker to stop/rescope.
- After that emit, remove the worker from `active_worker_ids` (the worker's `NNN_<task>.md` record
  is already on `master`). **Worktree cleanup:** if the worker recorded its worktree path (in its
  recovery comments) and it is local, clean, and matches this task/attempt, remove it
  (`git worktree remove`); **never** remove a path equal to `lead_worktree_root`.

### 6. Dispatch — proactive, seat-capped (skip if draining)
**Lease fence first:** before this batch, **refresh + re-read the lease and re-confirm you still own
it** — a merge-then-multi-dispatch turn can run long, and a **manual double-start** (a human
force-resuming during that long turn) could put a second lead on the same GitHub identity (the lease is
a *soft* guard, §1/§"Emitting control events"). If you've lost it, **abort the turn without emitting**.
The per-emit check-then-append seq guard still fences every individual `CONTROL_EVENT`; this fence
keeps `expires_at` fresh across the long turn so the race stays vanishingly rare. Then recompute the
frontier
from the **post-merge** state and dispatch ready tasks into every **free worker seat**, up to the
**5-seat cap**. **Proactive, not reluctant — but bounded:** do **not** hold a ready task back because
other workers are still in flight (fill a free seat), and do **not** exceed 5 concurrent workers.
When a §5 merge (or a freed seat) unblocks tasks, dispatch as many as fit the free seats now, this
turn.
The turn proceeds **select → dispatch**. The frontier **and the aging key are derived from the log**,
so **no per-task side effect happens before selection** — only the ≤5 *selected* tasks touch GitHub,
keeping the side-effect batch bounded even with hundreds of ready tasks (a 200-ready frontier still
creates ≤5 issues this turn).

- **Recovery disposition (apply before classifying an `active`-with-no-live-worker task as
  dispatchable).** Such a task is **not** unconditionally re-dispatched — first inspect its
  GitHub-visible artifacts for `current_attempt_id` and pick the exact disposition (this **replaces**
  the old watchdog-era *takeover damping*):
  - **open PR / `merge_requesting`** (latest recovery for `current_attempt_id`) → **reconcile**: drive
    it through the §5 merge gate (merge or deny). **Spawn no worker.**
  - **a per-attempt branch but no PR** → **hold if recent** (gate below); else mint a **new** attempt
    with `adopt_from_branch` = that branch.
  - **recovery comments only** (no branch, no PR) → a liveness hint only; **hold if recent**; else mint
    a **fresh** attempt from clean `master`.
  - **nothing** (no branch, no PR, no recent recovery) → mint a **fresh** attempt immediately.
  - **Invariant (unchanged):** never reuse an `attempt_id` or write an existing attempt branch; every
    re-dispatch mints a fresh `attempt_id` + its own branch, and `adopt_from_branch` only **reads** the
    old branch.
  - **"Recent" is a pure function of canonical GitHub time** (not the worker-authored JSON `ts`, not
    session memory): `hold_until = created_at + 1800 + skew_grace`, where `created_at =
    control_log.latest_recovery_with_metadata(comments, current_attempt_id)["created_at"]`. If
    `now < hold_until` → **hold** the task one poll (a merely-late live worker can finish or
    self-report) and re-evaluate next tick; human force overrides the hold.
- **Dispatchable** = dependencies complete (each dep's `MERGE_GRANTED` is in the log → status
  `merged`), revision-compatible (`spawned_plan_revision` would be the current `plan_revision`), and
  **either** status `ready` (never dispatched) **or** status `active` with **no live worker** for its
  `current_attempt_id` (an orphaned/crashed attempt — subject to the **recovery disposition** above).
  **Exclude** tasks with a **live** worker, `merged`, or `stale`. (Status `active` alone is **not** "in
  flight" — on a cold resume `active_worker_ids` is empty, so every un-merged dispatched task is a
  recovery candidate, never stranded.)
- **Aging key (log-derived, zero side effect):** `ready_since(task)` = the seq of its **last
  dependency's `MERGE_GRANTED`** (or `0` for a dependency-free root). It needs **no** per-task event
  or issue, so an unselected task costs **nothing** on GitHub and the key is a pure function of the
  replayed log — identical across resumes.
- **Select** up to the number of free seats (deterministic, starvation-free): order by (1)
  `directions.md` priority, then (2) **oldest** `ready_since`, then (3) the task/stage declaration
  order in the **`docs/task-loop/proposal.md` Roadmap** (the task source §4 computes the frontier
  from — *not* the per-task worker playbook `task-loop.md`) as the final tie-break. **Reserve ≥1 of
  the 5 seats for the oldest dispatchable task** (a max-skip rule) so a stream of high-priority work
  cannot starve it.
- **Seat cap = 5** simultaneous `cycle-worker` teammates (one task each → at most 5 in flight **per
  lead session**, **counting recovery re-dispatches**). A **documented, best-effort guideline in this prompt, not a
  programmatically enforced limit** — a lead never *intentionally* runs more than 5. Tasks beyond the
  cap are simply **not selected** this turn — they remain dispatchable (no issue, no event yet) and
  win a seat as one frees (§7's bounded wake), never abandoned.
  - **The cap is per-lead-session, not global.** Its one documented breach is a **manual double-start
    takeover** (a human runs `/run-cycle` a second time and force-takes a lease the first lead still
    holds — the startup lease check normally prevents this): the new lead **cannot observe the old
    lead's teammates** (ephemeral, invisible across sessions), so it may re-dispatch their `active`
    tasks and transiently run up to ~2× the cap until the superseded attempts hit their
    merge-gate/lease fences and stop. That overshoot is **correctness-safe** (durable
    `current_attempt_id` + per-attempt branches mean only one attempt can ever merge) and **transient**
    — a bounded *cost* overrun, never a broken invariant. A true global cap would need durable
    per-worker liveness heartbeats; that enforcement machinery is deliberately **out of scope** (the cap
    is a guideline, not an invariant).
  - The **recovery-disposition substep** (reconcile/adopt artifacts, hold-if-recent before minting) is
    what now caps that cost; it **replaces** the old watchdog-era *takeover damping*. The tri-state
    resume (§1) further refuses a takeover when the prior lead is diagnosably alive.
- **Dispatch each selected task** (≤5 — the only GitHub writes of this step):
  - **Idempotent issue creation (crash-safe):** before `gh issue create`, search for an existing
    issue carrying a `Task-Loop-Task: <task_id>` marker line and **reuse it** if found; otherwise
    create one (label `loop:in-progress`) with that marker. This makes "create issue → emit
    `TASK_CREATED`" recoverable: a crash *after* the issue exists but *before* the durable
    `TASK_CREATED` is reconciled next turn by finding the marked issue and emitting `TASK_CREATED`
    for it — **never a duplicate issue**.
  - **Iteration index** `NNN` — a zero-padded 3-digit counter from `001`, monotonic across the loop,
    **assigned once at `TASK_CREATED`** and reused on every re-dispatch (a **required `TASK_CREATED`
    field**; `replay` stores `tasks[task_id].iteration`, recovered from the control log, never from
    `docs/task-loop/logs/` (audit-only)). It names the worker's `NNN_<task>.md` record.
  - Emit `TASK_CREATED{task_id, plan_revision, issue_number, iteration}` the **first time the task is
    dispatched** (`replay` rejects a duplicate, enforcing once-only).
  - **Attempt ownership:** mint a fresh `attempt_id` (uuid) and emit
    `TASK_DISPATCHED{task_id, plan_revision, attempt_id}` (a **required field**; `replay` stores
    `current_attempt_id`, latest wins — the **durable single-flight token**). Each attempt writes only
    its own **per-attempt remote branch** `<branch>-attempt-<attempt_id>`, so two attempts can never
    write the same ref; a superseded worker can touch only its own dead branch.
  - Spawn **one** `cycle-worker` teammate (`agentType: cycle-worker`) with a prompt carrying
    `task_id`, `issue=<n>`, `control_issue=<#>`, `spawned_plan_revision=<current>`, `iteration=NNN`,
    `attempt_id`, the per-attempt branch `<branch>-attempt-<attempt_id>`, your **`lead_worktree_root`**
    (`git rev-parse --show-toplevel`, for the worker's isolation self-check), and — when
    re-dispatching a task that already has a GitHub-visible attempt — `adopt_from_branch=`the latest
    pushed attempt branch (the new attempt branches *from* it; Option-1: local-only pre-PR WIP is
    disposable). Record its id in `active_worker_ids`. The teammate declares `isolation: worktree`, so
    the harness gives it its **own** worktree — never ask it to create one; the worker self-checks
    isolation and aborts (`WORKTREE_ISOLATION_FAILED`) if its toplevel equals `lead_worktree_root`.

### 7. Wait / idle / exit
Reached **only after §6 has filled every free seat it can** — never sleep with a free seat and ready
work. The wake model is a **pure fixed poll**: every non-terminal state schedules the **same fixed
`ScheduleWakeup(1800)`** (30 min). Idle notifications are **not** relied upon; whatever a turn finds it
re-derives from GitHub and handles.
- **Workers active, a capped backlog, or the frontier empty** (`stop_at` not reached) →
  `waiting`/`idle`: schedule the **fixed `ScheduleWakeup(1800)`**, capped so it never sleeps past
  `stop_at`; **do not exit** (continuous service). One cadence for all of these — no jittered fallback,
  no shorter backlog wake, no recovery-probe wake. A held recovery candidate (§6 "hold if recent") is
  simply re-evaluated on the next fixed tick. Drop `active_worker_ids` entries as workers report and are
  merged.
- **draining** → dispatch nothing; wait for active workers until `drain_deadline_at`; past the
  deadline, mark overdue workers `orphaned_acknowledged` (record worktree/issue/PR pointers — no
  abrupt kill) and proceed.
- **Drain complete** → `exiting_pending`: run the **pre-exit audit** (below), record real command
  outputs into a decision record, `ScheduleWakeup` a 60–120 s cooldown.
- **Cooldown wake** → re-run the audit from scratch. Still clean → `exiting`: **stop rescheduling**
  (no further `ScheduleWakeup`). Anything changed → revert to `dispatching`/`waiting`.
- **Hard terminal guard.** Because the stop early-wake (Loop B) or a stray/late `ScheduleWakeup` can
  fire after exit, a turn that reads a clean `phase: exiting` at the top **re-audits and stops without
  dispatching** — a late wake can never re-enter the run; only a changed state reverts to
  `dispatching`/`waiting`.

### 8. Heartbeat
Refresh the lease `expires_at` and the diagnostics (`last_turn_completed_at = now`, and the
`next_wakeup_at` you are about to schedule) — plus advisory `phase`/`stop_at`/`stop_schedule_id` — by
writing the **control-issue body header** (`gh issue edit`). This is the only durable write of the turn
besides the appended `CONTROL_EVENT` comments — there is no local cache to persist. This end-of-turn
refresh is **in addition to** the intra-turn lease re-reads §5/§6 perform before their side-effect
groups; together they keep `expires_at` fresh across a long merge-then-multi-dispatch turn so a busy
lead is never mistaken for a stale one by a *manual* resume (the only remaining second-lead source —
there is no watchdog).

## Stop-time control (Loop B)

**Loop B** is a one-time scheduled job at `stop_at` that fires **into Loop A's own session** (the
built-in scheduler enqueues a prompt that runs while the REPL is idle, i.e. between polls). It does
**not** write the header or force `phase: exiting` itself — it simply **wakes Loop A early**, and that
turn's **Step 2 stop-check (against the *current* header `stop_at`)** is the sole stop decision. A
stale early fire is therefore harmless: the woken turn sees `now < stop_at` and continues. Loop B
carries the `stop_at` (a `stop_generation`) it was created for as **stale-trigger defense**, but Step
2's check is the real gate. Its value: it **bounds stop latency to ~0** at the scheduled `stop_at`,
versus the up-to-one-poll lag Loop A's own Step-2 check would otherwise incur.

Changing `stop_at` (run longer / stop sooner) splits into two paths:
- **Active stop update** — re-invoke `/run-cycle` (resume / stop-now / new `stop_at`): it runs **as the
  orchestrator**, acquires the lease, updates `stop_at`, **cancels the old Loop B via `stop_schedule_id`
  and creates a new one** for the new time, then runs Step 2. This is the **only** ~0-latency path for
  **shortening**, and it is sole-writer-clean.
- **Passive raw header edit** while Loop A sleeps — allowed but only **eventually observed** (≤ one
  poll, ~30 min): Loop A recreates Loop B and acts on the new `stop_at` on its next wake. Discouraged
  (it races the sole-writer model) in favor of the active path.

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

**Check-then-append guard (required).** Immediately before posting, **re-read the comment log and
confirm its true max `seq` is still `state["last_seq"]`** — only then `assign_seq` + post. If a
higher `seq` has appeared, a competing sequencer exists: re-ingest, recompute, retry; if it
persists you have lost the lease → **exit**. Together with the write-then-re-read lease fence (§1),
this is the single-sequencer guarantee under GitHub's non-CAS body writes — a vanishingly-small
TOCTOU window between the re-read and the append remains and is accepted (the only second-lead source
is a *manual* double-start, which the startup lease check normally prevents, so two live orchestrators
are rare by construction). If `replay` ever
raises on a seq gap/dup or duplicate `source_uuid`, that is **detectable corruption → halt and
escalate to a human**, never continue.

Event types — **orchestrator-originated** (no source): `TASK_CREATED` (carries `issue_number` +
`iteration`), `TASK_DISPATCHED` (carries `attempt_id`), `PLAN_REVISION_BUMP` (carries
`proposal_sha`), `TASK_STALE`, `TASK_REVISION_COMPATIBLE`, `INBOX_SCAN_CHECKPOINT` (carries
`issue_number` + `through_ts`).
**Inbox-derived** (carry `source_*`): `MERGE_GRANTED`, `MERGE_DENIED`, `PLAN_FINDING_RECORDED`.
`replay` validates the schema and raises on a seq gap/dup, a duplicate `source_uuid`, a
checkpoint for an unknown/regressing issue, or a non-canonical timestamp.

## Pre-exit audit (recorded, real outputs)

Before writing `phase: exiting`, prove with actual command output (`superpowers:verification-
before-completion`): `ready == 0` (no **dispatchable** tasks — counting any `active`-status task with
no live worker, i.e. a **recovery candidate** (§6 disposition, including one still inside a
hold-if-recent window), as dispatchable), `active == 0` (`active_worker_ids` empty **and** no
`active`-status task in the log awaiting (re-)dispatch, and no open `loop:in-progress` without a merged
PR), `blocked == acknowledged` (every blocked/stale task has a follow-up), `unmerged == 0` (no open PR
awaiting a `MERGE_REQUEST`). A held or unreconciled recovery candidate therefore **fails** this audit —
the loop cannot declare quiescence while recovery work is still pending. Re-run it after the cooldown;
only an all-clear second pass permits exit.

## Recovery (cold resume / manual resume)

Manual `/run-cycle` resume is the **death/hang recovery path** (there is no watchdog). A fresh
orchestrator on clean `master` rebuilds entirely from GitHub: the control issue (replay → revision,
dedupe set, scan floors, task statuses, **`iteration`**, **`current_attempt_id`**), the per-task
**append-only recovery comments** (read via `control_log.latest_recovery(comments,
current_attempt_id)`, with `control_log.latest_recovery_with_metadata` supplying the canonical
`created_at` for §6's hold-if-recent gate), open PRs, and `docs/task-loop/logs/` (audit only).
Ephemeral teammates and `~/.claude/tasks/` are **not** relied upon. Because teammates die with the
lead's session, a dead session *usually* leaves no surviving workers — but a **manual double-start**
(a human force-resumes a lead that is actually alive) can spawn a second lead while a worker still
lives, so safety must **not** depend on that: it comes from the durable `current_attempt_id` +
**per-attempt branches** (below), with ephemerality only making the window rare; the tri-state resume
(§1) and the recovery-disposition substep (§6) cap the *cost*. Orphaned tasks re-enter through §6's
**recovery disposition** (status `active` with **no live worker** for `current_attempt_id`), so a
crashed/resumed task is selected and re-dispatched by the same seat-capped frontier — never stranded,
never a separate code path. Respawn follows **one rule, the GitHub-visible-artifact line:**

- **No remote branch and no PR** for a dispatched task → any work was local-only pre-PR WIP, which
  is **disposable**: abandon it and **re-dispatch a fresh attempt** (new `attempt_id`) from clean
  `master`. At most one in-flight task's un-pushed WIP is lost and simply redone — zero correctness
  loss. This is what makes "resume from any session / clean checkout" honest.
- **A per-attempt branch and/or PR exists** → re-dispatch with `adopt_from_branch=`that branch so
  the new attempt branches **from** it (a *read*, never a write to it) and drives it to merge. The
  latest recovery comment for `current_attempt_id` tells *ready-but-unannounced* (`pr_open` /
  `merge_requesting`) from *still-working*.

Each attempt writes **only** its own per-attempt remote branch `<branch>-attempt-<attempt_id>` and
its own append-only recovery comments — there is **no shared writable ref or body** two attempts can
race on. A superseded worker (its `attempt_id` != `current_attempt_id`) is harmless: it can touch
only its own dead branch, and the merge gate denies its `MERGE_REQUEST`. The orchestrator merges
**only** the current attempt's PR; the durable `current_attempt_id` makes "which attempt owns this
task" a pure function of the control log, not of a fragile "one worker at a time" assumption. The
planning step is idempotent — the same frontier is recomputed and only missing workers respawn.

## Deliberate with Codex

Use `dev-skills:discuss-with-codex` for: ambiguous task selection / "are these two tasks truly
independent?" / dependency ordering; confirming a hypothesis invalidation before a
`PLAN_REVISION_BUMP`; and resolving conflicting worker outcomes. Record dispositions in the
decision record.
