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
fenced ` ```task-loop-runtime ` JSON block the orchestrator (loop 1) is the **sole writer** of.
Everything else is the append-only comment log (replayed above) or live session memory; nothing is
written to local disk. Header shape:

```json
{
  "lease": {"owner": "<id>", "expires_at": "<utc>", "heartbeat": "<utc>"},
  "phase": "dispatching|waiting|idle|draining|exiting_pending|exiting",
  "stop_at": "<utc>",
  "drain_deadline_at": null,
  "watchdog_schedule_id": null,
  "stop_schedule_id": null
}
```

`phase`/`current_plan_revision`/`active_worker_ids` are **derived** (rebuilt by `replay` + session
memory) — the header only persists what a *sibling job* must read: the `lease` heartbeat, `stop_at`,
and the two schedule handles. The lease `heartbeat` is refreshed every turn (a `gh issue edit` of
the body); the **watchdog** (loop 3) reads the header and treats a stale `heartbeat`/`expires_at` as
"the running loop died" and resubmits it. `stop_at` is the self-bound graceful-stop time;
`watchdog_schedule_id`/`stop_schedule_id` are the built-in scheduler handles for loops 3 and 2 (so
loop 2 can cancel loop 3). See *Control plane*. Body writes are last-writer-wins, which is safe
because the lease loser exits — but two near-simultaneous writers are possible, so the lease is a
**soft** single-coordinator guard, not an atomic CAS.

## State machine

**Dispatch is a seat-capped action, not a phase.** Every turn — *after* merging completions (§5) —
the orchestrator fills every **free worker seat** with a ready task, up to a **fixed cap of 5**
concurrent `cycle-worker` teammates (5 tasks in flight), **whether or not other workers are still
active**. It is **proactive** (a task unblocked this turn is dispatched this turn) but **bounded**
(never more than 5 *intentionally* per lead session — see §6 for the watchdog-false-positive caveat)
— active workers never suppress dispatch of newly-ready work *as long as a seat is free*. `waiting` is what the orchestrator does *after* it has filled every seat it
can, not an alternative to dispatching. Re-entering a turn always re-runs merge→dispatch first.
The 5-seat cap is a **documented guideline in this prompt, not a programmatically enforced limit**.
The phases:

- **dispatching** — creating tasks + spawning workers for ready tasks this turn. Entered whenever
  any ready task exists and `stop_at` is not reached — **including while other workers are active**
  (a §5 merge or a freed concurrency slot just unblocked it).
- **waiting** — after filling every free seat, work is in flight. Teammate idle notifications are
  the **primary** wake; add a **bounded, jittered** fallback `ScheduleWakeup` — shorter only when a
  capped backlog waits on a freeing seat, never aggressive polling, never a busy-loop (see §7).
  `waiting` never means "stop dispatching" — the next turn re-runs §5→§6 first.
- **idle** — no ready work, no active workers, `stop_at` not reached → long `ScheduleWakeup`
  (capped so it never sleeps past `stop_at`); **do not exit** (continuous service).
- **draining** — clock reached `stop_at` → no new dispatch; wait for active workers, bounded
  by `drain_deadline_at`.
- **exiting_pending** — drain complete → record the pre-exit audit, `ScheduleWakeup` a 60–120 s
  cooldown.
- **exiting** — re-audit still clean → stop rescheduling (the run ends). If anything changed,
  revert to `dispatching`/`waiting`.

## Per-turn algorithm

### 1. Lease & rebuild
- Read the **control-issue body header**. If a **live** lease (`expires_at` in the future) is owned
  by a different instance → exit (never two orchestrators). Else acquire/refresh the lease by
  writing the header (`owner`, `expires_at = now + TTL`, `heartbeat = now`), then **re-read the
  header and confirm you still own it** before any side effect (the **write-then-re-read fence**;
  GitHub gives no atomic CAS, so this is how a lease loser detects it lost and exits).
- On resume / stale lease (`expires_at` past, or `phase: exiting` without a clean prior audit):
  take over, then **rebuild fast state from the control issue** (replay the comment log, above).
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
it** — a merge-then-multi-dispatch turn can run long, and a mid-turn stale heartbeat could let the
watchdog presume the lead dead and spawn a second one (the lease is a *soft* guard, §1/§"Emitting
control events"). If you've lost it, **abort the turn without emitting**. The per-emit
check-then-append seq guard still fences every individual `CONTROL_EVENT`; this fence keeps the
heartbeat fresh across the long turn so the race stays vanishingly rare. Then recompute the frontier
from the **post-merge** state and dispatch ready tasks into every **free worker seat**, up to the
**5-seat cap**. **Proactive, not reluctant — but bounded:** do **not** hold a ready task back because
other workers are still in flight (fill a free seat), and do **not** exceed 5 concurrent workers.
When a §5 merge (or a freed seat) unblocks tasks, dispatch as many as fit the free seats now, this
turn.
The turn proceeds **select → dispatch**. The frontier **and the aging key are derived from the log**,
so **no per-task side effect happens before selection** — only the ≤5 *selected* tasks touch GitHub,
keeping the side-effect batch bounded even with hundreds of ready tasks (a 200-ready frontier still
creates ≤5 issues this turn).

- **Dispatchable** = dependencies complete (each dep's `MERGE_GRANTED` is in the log → status
  `merged`), revision-compatible (`spawned_plan_revision` would be the current `plan_revision`), and
  **either** status `ready` (never dispatched) **or** status `active` with **no live worker** for its
  `current_attempt_id` (an orphaned/crashed attempt — re-dispatched as a *recovery*, branching from
  `adopt_from_branch`; see *Recovery*). **Exclude** tasks with a **live** worker, `merged`, or
  `stale`. (Status `active` alone is **not** "in flight" — on a cold resume `active_worker_ids` is
  empty, so every un-merged dispatched task is a recovery candidate, never stranded.)
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
  - **The cap is per-lead-session, not global.** Its one documented breach is a watchdog
    **false-positive takeover** (a second lead spawns while the first's workers still live, see
    *Recovery*): the new lead **cannot observe the old lead's teammates** (ephemeral, invisible across
    sessions), so it may re-dispatch their `active` tasks and transiently run up to ~2× the cap until
    the superseded attempts hit their merge-gate/lease fences and stop. That overshoot is
    **correctness-safe** (durable `current_attempt_id` + per-attempt branches mean only one attempt
    can ever merge) and **transient** — a bounded *cost* overrun, never a broken invariant. A true
    global cap would need durable per-worker liveness heartbeats; that enforcement machinery is
    deliberately **out of scope** (the cap is a guideline, not an invariant).
  - **Takeover damping** (shrinks, does not eliminate, the overshoot): on the **first** turn after
    taking over a stale lease, defer re-dispatch of `active`-status tasks by one bounded
    recovery-probe interval before reclassifying them as orphaned — so a merely-stalled prior lead
    does not instantly get its worker count doubled. Steady-state turns skip the delay.
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
work.
- **Workers active, no capped backlog** → `waiting`: automatic teammate **idle notifications are the
  primary wake** (a worker reporting done triggers §5→§6 the next turn); add only a **bounded
  heartbeat-interval fallback** `ScheduleWakeup` **with jitter**. Do **not** poll aggressively —
  active workers alone are not a reason to wake early.
- **Ready tasks remain but all 5 seats are full** → `waiting` with a **shorter, still-floored +
  jittered** fallback wake — a freeing seat also emits an idle notification, so this only backstops a
  missed one; the next turn re-runs §5→§6 to fill the freed seat. **Never busy-loop:** the floor +
  idle notifications bound the rate. Drop `active_worker_ids` entries as workers report and are merged.
- **Deferred recovery candidates exist** (first turn after a stale-lease takeover — §6 takeover
  damping is holding `active`-status tasks for one recovery-probe interval) → `waiting`: schedule the
  **bounded recovery-probe wake (jittered)**; **do not `idle` or exit**. These are *not* "frontier
  empty" — they are damped recovery work, and the very next turn (after the probe interval) §6
  reclassifies and re-dispatches them. They also fail the pre-exit audit (below), so the loop cannot
  declare quiescence while recovery is merely deferred.
- **Frontier empty, none active, `stop_at` not reached** → `idle`: long `ScheduleWakeup` (capped
  to wake by `stop_at`); **do not exit**.
- **draining** → dispatch nothing; wait for active workers until `drain_deadline_at`; past the
  deadline, mark overdue workers `orphaned_acknowledged` (record worktree/issue/PR pointers — no
  abrupt kill) and proceed.
- **Drain complete** → `exiting_pending`: run the **pre-exit audit** (below), record real command
  outputs into a decision record, `ScheduleWakeup` a 60–120 s cooldown.
- **Cooldown wake** → re-run the audit from scratch. Still clean → `exiting`: stop rescheduling.
  Anything changed → revert to `dispatching`/`waiting`.

### 8. Heartbeat
Refresh the lease `heartbeat`/`expires_at` (and advisory `phase`/`stop_at`/schedule handles) by
writing the **control-issue body header** (`gh issue edit`). This is the only durable write of the
turn besides the appended `CONTROL_EVENT` comments — there is no local cache to persist. This
end-of-turn refresh is **in addition to** the intra-turn lease re-reads §5/§6 perform before their
side-effect groups; together they keep the heartbeat fresh across a long merge-then-multi-dispatch
turn so a busy lead is never mistaken for a dead one.

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
TOCTOU window between the re-read and the append remains and is accepted (the watchdog only acts on
an already-stale heartbeat, so two live orchestrators are rare by construction). If `replay` ever
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
no live worker, i.e. a **deferred recovery candidate**, as dispatchable), `active == 0`
(`active_worker_ids` empty **and** no `active`-status task in the log awaiting (re-)dispatch, and no
open `loop:in-progress` without a merged PR), `blocked == acknowledged` (every blocked/stale task has
a follow-up), `unmerged == 0` (no open PR awaiting a `MERGE_REQUEST`). A damped/deferred recovery
candidate therefore **fails** this audit — the loop cannot declare quiescence while recovery work is
merely deferred. Re-run it after the cooldown; only an all-clear second pass permits exit.

## Recovery (cold resume)

A fresh orchestrator on clean `master` rebuilds entirely from GitHub: the control issue (replay →
revision, dedupe set, scan floors, task statuses, **`iteration`**, **`current_attempt_id`**), the
per-task **append-only recovery comments** (read via `control_log.latest_recovery(comments,
current_attempt_id)`), open
PRs, and `docs/task-loop/logs/` (audit only). Ephemeral teammates and `~/.claude/tasks/` are **not**
relied upon. Because teammates die with the lead's session a crashed loop 1 *usually* leaves no
surviving workers — but a watchdog **false-positive** (lead alive, heartbeat merely stale) can spawn
a second lead while a worker still lives, so safety must **not** depend on that: it comes from the
durable `current_attempt_id` + **per-attempt branches** (below), with ephemerality only making the
window rare. Orphaned tasks re-enter through §6's **Dispatchable** rule (status `active` with **no
live worker** for `current_attempt_id`), so a crashed/resumed task is selected and re-dispatched by
the same seat-capped frontier — never stranded, never a separate code path. Respawn follows **one
rule, the GitHub-visible-artifact line:**

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
