# Design — `task-loop` two-loop control plane (fixed-interval poll)

**Status:** design — **Codex-converged** (see `2026-06-14-task-loop-two-loop-control-plane-conclusion.md`,
6 rounds).
**Branch:** `feat-two-loop-control-plane`
**Supersedes (control-plane topology only):** the "three jobs" model in
`2026-06-13-task-loop-control-plane-conclusion.md`. All other conclusions
(seq guard, attempt-fencing, recovery artifact-semantics, merge gates) are unchanged.

## 1. Problem

`run-cycle` today runs as **three cooperating jobs**:

1. **Loop 1** — a live `/loop` Agent-Teams lead session (the orchestrator), **self-paced**:
   idle-notifications "primary," jittered `ScheduleWakeup` fallbacks, a shorter backlog wake, and a
   recovery-probe wake.
2. **Loop 2** — a one-time scheduled *stop* at `stop_at`.
3. **Loop 3** — a recurring 30-min *watchdog* that reads the lease heartbeat and, if stale, alerts or
   (Tier-1) relaunches.

Two problems:

- **The watchdog conflates two failure modes.** Its real day-to-day value was catching an orchestrator
  that is **alive but stuck** — not dispatching newly-unblocked work (the "reluctance" PR #122
  addressed). True **session death** it cannot reliably catch: a watchdog created by the orchestrator
  runs *in the orchestrator's own session* (`CronCreate` fires into the current idle REPL and dies when
  that session exits), so it cannot survive the death it was built to detect. The only true
  cross-session resurrector was always Tier-1 — an *external* OS supervisor (infrastructure, never a loop).
- **The self-paced wake model is complex and unpredictable** ("does not specify when it triggers").

## 2. Decision

**Collapse to two loops and a pure fixed 30-min poll.**

- **"Alive but stuck" between turns** is resolved *structurally* by a fixed 30-min poll that
  **re-derives the complete task frontier from GitHub every tick** — no carried-over "what next" state
  can wedge; a tick that under-dispatches is corrected by the next, seat-capped at 5.
- **"Session truly dead" or hung inside a turn** → **manual `/run-cycle` resume**, which rebuilds 100%
  from GitHub. No in-protocol liveness watch.

**Narrowed claim (Codex R1):** the fixed poll eliminates **inter-turn under-dispatch only**. An
**intra-turn hang** (a `gh`/CI/spawn call that never returns before the turn reschedules) is **not**
structurally eliminated — it has **no in-protocol detection** now, a real reduction vs the watchdog,
accepted under "manual resume only." Mitigation: **best-effort per-command deadlines** on the
orchestrator's own calls, with **reconcile-on-timeout** (re-inspect ambiguous side effects before
rescheduling) — reduces, does not eliminate.

**Locked user decisions:** pure fixed 30-min poll (no idle early-wake); manual resume only.
**Accepted tradeoff:** a worker finishing at minute 1 waits up to ~30 min for the next tick to merge,
delaying dependents — bought for a dead-simple, predictable, self-correcting control plane.

## 3. Architecture — two loops

```
   Loop A (orchestrator, /loop)         Loop B (stop early-wake)
   ┌───────────────────────────┐        ┌───────────────────────────┐
   │ every 30 min, one turn:    │       │ one-time @ stop_at:         │
   │  1 lease & rebuild (replay)│       │  wake Loop A (in-session);  │
   │  2 STOP-CHECK (sole stop   │◄──────│  the turn's Step 2 decides  │
   │    decision; → draining)   │       │  against CURRENT stop_at.   │
   │  3 ingest worker events ───┼─ "monitor team status"             │
   │  4 replan barrier          │       │  recreated by Loop A on an  │
   │  5 MERGE first (integrator)│       │  ACTIVE stop_at change.     │
   │  6 DISPATCH full frontier, │       └───────────────────────────┘
   │    seat-capped, + recovery │
   │    disposition substep     │   ← frontier re-derived from GitHub every tick
   │  7 ScheduleWakeup(1800) ───┼─┐   (fixed; or exit if drained)
   │  8 heartbeat (lease + diag)│ │
   └───────────────────────────┘ │   phase:exiting = HARD terminal guard at turn top
              ▲                    │
              └────── 30 min ──────┘
```

- **Loop A — the orchestrator.** `/loop`-driven; each turn ends with a **fixed `ScheduleWakeup(1800)`**.
  **Step 2 stop-check is the sole stop decision** (against the current header `stop_at`). On
  drain-complete it stops rescheduling. `phase: exiting` is a **hard terminal guard** at turn top: a
  stray/late wake reading a clean `exiting` re-audits and stops without dispatching; only a changed
  state reverts to dispatching/waiting.
- **Loop B — the stop early-wake.** A one-time scheduled job at `stop_at` that **wakes Loop A**
  (fires into its session while idle); it does **not** force `phase: exiting` — the woken turn's Step 2
  decides. A stale early fire is harmless (turn continues). Loop B carries a `stop_at`/generation
  payload as stale-trigger defense. Value: bounds stop latency to ~0 at the original `stop_at`.

### Substrate: `/loop` + fixed `ScheduleWakeup`, not `CronCreate` for Loop A

Loop A stays a live `/loop` session scheduling its own fixed 1800 s wake. Reasons: `/loop` is the
existing driver (surgical change); the orchestrator must hold a live session to spawn teammates anyway;
`CronCreate` carries a silent **7-day auto-expiry** and only fires "while the REPL is idle" — coupling
we don't want on the primary loop. (Loop B *is* a one-time scheduled job, fine for a single fire.)

## 4. The per-turn algorithm (what changes)

- **Steps 1–5 unchanged** (lease & rebuild; stop-check; ingest worker events = "monitor team status";
  replan; **merge first**).
- **Step 6 (dispatch) gains a recovery-disposition substep** (§5).
- **Step 7 simplified** to a pure fixed poll: any non-terminal state → **`ScheduleWakeup(1800)`**.
  **Removed:** "idle notifications primary," jittered fallbacks, the shorter backlog wake, the
  deferred-recovery-probe wake. `draining`/`exiting_pending`/`exiting` unchanged except they no longer
  compete with idle-notification wakes. Idle notifications are **no longer part of the wake model**.
- **Step 8 (heartbeat)** writes the richer lease diagnostics (§6).

## 5. Recovery disposition substep (Codex R2/R3/R4)

Manual resume is **tri-state on advisory diagnostics, human force always available**:
`likely_alive` (`next_wakeup_at` & `expires_at` both future) → **default refuse**, allow human force;
`likely_dead` (`now ≫ next_wakeup_at` or `expires_at` well past) → acquire lease, **observe/reconcile
first**.

Before classifying an `active`-with-no-live-worker task as dispatchable, apply the **exact disposition
table**:

| Current-attempt artifact | Disposition |
|---|---|
| open PR / `merge_requesting` | **reconcile** (merge or deny); spawn no worker |
| branch, no PR | **hold if recent**; after one poll or human force → mint **new** attempt `adopt_from_branch` |
| recovery comments only | liveness hint; hold if recent; else mint **fresh from `master`** |
| nothing (no branch/PR/recent recovery) | mint **fresh** immediately |

**Invariant (unchanged):** never reuse `attempt_id` or write an existing attempt branch;
`adopt_from_branch` only **reads** the old branch.

The **"recent" gate is a pure function of canonical GitHub time:**
`hold_until = latest_recovery_comment_created_at + 1800 + skew_grace`. Worker-authored JSON `ts` and
session memory are both rejected. This requires an **additive** helper
`control_log.latest_recovery_with_metadata(comments, attempt_id) → {comment_id, created_at, recovery}`
(the existing `latest_recovery` discards `created_at`), plus unit tests. **No new event types; schema,
`replay`, dedupe, checkpoints, and the 58 existing tests unchanged.**

This **replaces takeover damping** (which existed only for the now-deleted watchdog false-positive).

## 6. Lease header (Codex R2/R4/R5)

```json
{
  "owner": "<id>", "expires_at": "<utc ~2x poll>",
  "last_turn_started_at": "<utc>", "last_turn_completed_at": "<utc>", "next_wakeup_at": "<utc>",
  "phase": "dispatching|waiting|idle|draining|exiting_pending|exiting",
  "stop_at": "<utc>", "drain_deadline_at": null, "stop_schedule_id": null
}
```

Soft/advisory/last-writer-wins, **sole-written** by the orchestrator. **Dropped:** `watchdog_schedule_id`
and the single `heartbeat` field. **Kept:** `stop_schedule_id` (so the orchestrator can cancel/recreate
Loop B). The diagnostics make manual resume **informed** (sleeping vs hung-mid-turn vs dead) instead of
guessing from one TTL; no watchdog consumes them — a human/preflight does.

## 7. Stop-time control (Codex R6)

- **Active stop update** — re-invoke `/run-cycle` (resume / stop-now / new `stop_at`): runs **as the
  orchestrator**, acquires the lease, updates `stop_at`, **cancels+recreates Loop B immediately**, runs
  Step 2. The only ~0-latency path for **shortening**, and sole-writer-clean.
- **Passive raw header edit** while Loop A sleeps: allowed but **eventually observed** (≤ one poll,
  ~30 min); Loop B recreated on next wake. Discouraged (races sole-writer) vs the active path.
- ~0 stop latency holds at the **original** `stop_at` via Loop B.

## 8. Cascading simplifications (in scope)

1. **Delete the watchdog (Loop 3)** — job, `watchdog_schedule_id`, Tier-0/Tier-1 alert/relaunch
   machinery. SKILL "Control plane" → *one live fixed-interval loop + one stop early-wake*. Death/hang
   recovery documented honestly as manual `/run-cycle` resume.
2. **Replace takeover damping** with the artifact-aware recovery disposition substep (§5).
3. **Simplify Setup** — drop "create watchdog"; keep "create stop." Header loses `watchdog_schedule_id`.
4. **Simplify Step 7 wake** and the `Continuous service`/wake invariants to the fixed-poll model.

## 9. Deliberately kept (orthogonal correctness machinery)

Untouched — hard-won and independent of loop topology: **intra-turn lease fences** (they guard a manual
double-start's same-identity irreversible merge, *not* the watchdog), **attempt-fencing** +
per-attempt branches, the **check-then-append seq guard**, all **merge gates**, and the
`control_log.py` **event schema** + its 58 tests.

## 10. Files affected

- `task-loop/skills/run-cycle/SKILL.md` — Control plane (3 jobs → 2), Setup (drop watchdog; keep stop),
  high-level turn §7, Hard invariants, stop-time control note.
- `task-loop/skills/run-cycle/references/orchestrator-loop.md` — header JSON (drop `watchdog_schedule_id`
  + `heartbeat`, add diagnostics, keep `stop_schedule_id`), State machine (drop watchdog, fixed-poll
  wake, `phase: exiting` hard terminal guard), §1 lease + tri-state resume, §6 recovery-disposition
  substep + table, §7 fixed-poll wait/idle/exit, Recovery (manual resume = death/hang path; disposition
  table), Control plane subsection, Loop B early-wake + stop-time control.
- `task-loop/scripts/control_log.py` — **additive** `latest_recovery_with_metadata` helper (no schema
  change).
- `task-loop/tests/` — new tests for `latest_recovery_with_metadata`; **58 existing stay green**.
- `docs/superpowers/specs/2026-06-13-task-loop-plugin-design.md` — §12 watchdog / control-plane prose.
- `task-loop/.claude-plugin/plugin.json` — version 0.8.1 → 0.9.0 (notable control-plane change).
- New conclusion: `2026-06-14-task-loop-two-loop-control-plane-conclusion.md` (already written).

## 11. Out of scope

- Any external supervisor / unattended auto-relaunch (manual resume only).
- Changing the control-event schema, attempt-fencing, recovery artifact-semantics, or merge gates.
- Re-introducing idle-notification reactivity (rejected for the pure fixed poll).
