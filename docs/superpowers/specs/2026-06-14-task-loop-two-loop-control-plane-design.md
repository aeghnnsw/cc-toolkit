# Design — `task-loop` two-loop control plane (fixed-interval poll)

**Status:** design (brainstorming output, pre-Codex)
**Branch:** `feat-two-loop-control-plane`
**Supersedes (control-plane topology only):** the "three jobs" model in
`2026-06-13-task-loop-control-plane-conclusion.md`. All other conclusions
(seq guard, attempt-fencing, recovery semantics, merge gates) are unchanged.

## 1. Problem

`run-cycle` today runs as **three cooperating jobs**:

1. **Loop 1** — a live `/loop` Agent-Teams lead session (the orchestrator). It **self-paces**:
   teammate idle-notifications are the "primary wake," with jittered `ScheduleWakeup` fallbacks and
   a separate shorter wake when a capped backlog waits on a freeing seat.
2. **Loop 2** — a one-time scheduled *stop* at `stop_at`.
3. **Loop 3** — a recurring 30-min *watchdog* that reads the lease heartbeat and, if stale, alerts
   ("orchestrator down, resume needed") or (Tier-1, optional) relaunches.

Two problems motivate the change:

- **The watchdog conflates two different failure modes.** Its real day-to-day value was catching an
  orchestrator that is **alive but stuck** — not dispatching newly-unblocked work (the same
  "reluctance" PR #122 addressed). Genuine **session death** it cannot reliably catch anyway: a
  watchdog created by the orchestrator runs *in the orchestrator's own session* (`CronCreate` fires
  into the current idle REPL and dies when that session exits), so it cannot survive the death it was
  built to detect. The only true cross-session resurrector was always Tier-1 — an *external* OS
  supervisor, i.e. infrastructure, never one of the loops.
- **The self-paced wake model is complex and unpredictable.** "Idle-notification primary + jittered
  fallback + backlog-shorter + deferred-recovery probe" is a lot of machinery, and its trigger timing
  is hard to reason about ("does not specify when it triggers").

## 2. Decision

**Collapse to two loops and a fixed-interval poll.**

- **"Alive but stuck"** is resolved *structurally* by a **fixed 30-min poll that re-derives the
  complete task frontier from GitHub every tick.** There is no carried-over "what to do next" state
  that can wedge; a tick that under-dispatches is fully corrected by the next tick's fresh
  full-frontier re-evaluation, seat-capped at 5.
- **"Session truly dead"** is resolved by **manual `/run-cycle` resume**, which rebuilds 100% from
  GitHub (the no-local-files payoff). This is an explicit, accepted tradeoff: no in-protocol liveness
  watch. (Decided 2026-06-14.)

**Locked constraints (user decisions):**
- **Pure fixed 30-min poll** — *not* a hybrid with idle-notification early-wake. Predictability over
  latency.
- **Manual resume only** for session death — no mandatory external supervisor, no in-protocol alert.

**Accepted tradeoff:** a worker that finishes at minute 1 waits up to ~30 min for the next tick to
merge its PR, delaying its dependents. Bought in exchange for a dead-simple, predictable,
self-correcting control plane.

## 3. Architecture — two loops

```
                          stop_at
   Loop A (orchestrator, /loop)        Loop B (stop event)
   ┌───────────────────────────┐       ┌──────────────────┐
   │ every 30 min, one turn:    │       │ one-time @ stop_at │
   │  1 lease & rebuild (replay)│       │  confirm drained   │
   │  2 stop-check (→ draining)  │      │  end the run       │
   │  3 ingest worker events ────┼──◄── "monitor team status"
   │  4 replan barrier          │       └──────────────────┘
   │  5 MERGE first (integrator)│
   │  6 DISPATCH full frontier, │   ← re-derived from GitHub every tick;
   │    seat-capped at 5        │     this is what makes "stuck" impossible
   │  7 ScheduleWakeup(1800) ───┼─┐   (fixed 30-min; or exit if drained)
   │  8 heartbeat (refresh lease)│ │
   └───────────────────────────┘ │
              ▲                    │
              └────── 30 min ──────┘
```

- **Loop A — the orchestrator.** Driven by built-in `/loop`. Each turn ends with a **fixed
  `ScheduleWakeup(1800)`** (30 min). It still **self-bounds**: a turn that finds the clock at/after
  `stop_at` enters `draining`, and on drain-complete it stops rescheduling (the run ends from inside
  Loop A as the primary stop path).
- **Loop B — the stop event.** A one-time scheduled job at `stop_at`. With no watchdog to cancel, its
  job shrinks to: confirm Loop A has drained and the run has ended — a **decoupled "time's up"
  teardown** that does not depend on Loop A self-bounding correctly on every tick.

### Substrate: `/loop` + fixed `ScheduleWakeup`, not `CronCreate`

Loop A stays a live `/loop` session that schedules its own next wake at a fixed 1800 s, rather than
becoming a recurring `CronCreate` job. Reasons:

- `/loop` is the existing driver — this is a surgical change to the *cadence*, not the substrate.
- The orchestrator must hold a live local session to spawn Agent-Teams teammates regardless;
  `CronCreate` firing into that same session adds a second mechanism for no gain.
- `CronCreate` carries a silent **7-day auto-expiry** that would kill a long run, and only fires
  "while the REPL is idle" — coupling we don't want on the primary loop.

`ScheduleWakeup` with a fixed delay *is* the fixed interval.

## 4. The per-turn algorithm (what changes)

Steps 1–6 are **unchanged** from the current `orchestrator-loop.md` (lease & rebuild; stop check;
event-drain & ingest; replan barrier; **merge first**; proactive seat-capped dispatch over the
full re-derived frontier). The "monitor team status" the user described **is** step 3 (ingest worker
events: progress, PR opened, merge requested) feeding steps 5–6.

**Step 7 (Wait / idle / exit) is simplified** to a pure fixed poll:

- Not draining (workers active, capped backlog, *or* empty frontier) → **`ScheduleWakeup(1800)`**.
  One cadence for every non-terminal state. **Removed:** "idle notifications are the primary wake,"
  jittered fallbacks, the shorter backlog wake, and the deferred-recovery-probe wake.
- `draining` → dispatch nothing; wait for active workers until `drain_deadline_at`; past it, mark
  overdue workers `orphaned_acknowledged` (unchanged).
- Drain complete → `exiting_pending` (record pre-exit audit, short cooldown wake) → re-audit clean →
  `exiting` (stop rescheduling). Unchanged except it no longer competes with idle-notification wakes.

Idle notifications are **no longer part of the wake model.** They may still arrive, but the loop does
not depend on them; every turn is idempotent and re-derives state from GitHub, so whatever a turn
finds, it handles.

## 5. Cascading simplifications (in scope)

1. **Delete the watchdog (Loop 3) entirely** — the recurring job, the `watchdog_schedule_id` header
   field, and the Tier-0 detect+alert / Tier-1 auto-relaunch machinery. The SKILL "Control plane"
   section becomes *one live fixed-interval loop + one stop job*. Death recovery is documented
   honestly as manual `/run-cycle` resume.
2. **Drop takeover damping** (orchestrator-loop §6). It existed specifically to shrink the
   **watchdog false-positive** two-lead window (a second lead spawned while the first's workers still
   lived). With no watchdog, that spawn source is gone.
3. **Simplify Setup** — drop the "create watchdog" step; keep "create stop." The body runtime header
   loses `watchdog_schedule_id`.
4. **`Continuous service` / wake invariants** updated to the fixed-poll model.

## 6. Deliberately kept (orthogonal correctness machinery)

These are **not** touched — they are hard-won and independent of loop topology:

- **The lease** as the single-coordinator guard. Its remaining job is narrower: catch a **manual
  double-start** (a human running `/run-cycle` twice). A second start reads the lease; if
  `expires_at` is in the future it exits. Refreshed each tick (step 8).
- **Attempt-fencing** (`current_attempt_id` + per-attempt branches) — the durable single-flight
  correctness backstop for *any* two-lead window, including a forced manual double-start.
- **The check-then-append seq guard** and **all merge gates** (pre-merge drain barrier, head-SHA
  binding, `mergedBy` provenance halt).

## 7. Open questions to pressure-test with Codex

1. **Lease `heartbeat` field.** Its only consumer was the watchdog. With manual-resume-only, is
   `expires_at` (refreshed each tick) sufficient for the single-coordinator guard, letting us drop the
   separate `heartbeat` field — or does removing it lose something?
2. **Intra-turn lease fences (PR #122).** The re-read-before-merge, final-fence-before-`gh pr merge`,
   and re-read-before-dispatch fences were added partly because the watchdog could spawn a second lead
   *mid-run*. With that source gone (only manual double-start remains, caught at startup), can these
   relax to a single per-turn lease check — or are they cheap insurance worth keeping for
   defense-in-depth (and any future re-introduction of auto-relaunch)? **Default: keep them** unless
   Codex shows they're pure dead weight.
3. **Is dropping takeover damping safe** on a *manual* stale-lease takeover? The human resumes only
   when they believe the prior session is dead, so its teammates are gone — but is there a residual
   "stalled-but-alive prior lead" risk a human could trip?
4. **Loop B necessity.** Given Loop A self-bounds every tick, is the separate stop event a meaningful
   backstop or pure ceremony? (User asked for it explicitly; the question is whether to frame it as a
   guarantee or note it as redundant-but-cheap.)

## 8. Files affected

- `task-loop/skills/run-cycle/SKILL.md` — Control plane section (3 jobs → 2), Setup (drop watchdog),
  high-level turn §7, Hard invariants.
- `task-loop/skills/run-cycle/references/orchestrator-loop.md` — Fast-state header JSON (drop
  `watchdog_schedule_id`, maybe `heartbeat`), State machine (drop watchdog, fixed-poll wake), §1 lease,
  §7 wait/idle/exit (fixed poll), §6 (drop takeover damping), Recovery (manual resume = death path),
  Control plane subsection.
- `docs/superpowers/specs/2026-06-13-task-loop-plugin-design.md` — §12 watchdog / control-plane prose.
- `task-loop/.claude-plugin/plugin.json` — version bump 0.8.1 → 0.9.0 (notable control-plane change).
- New: `docs/superpowers/specs/2026-06-14-task-loop-two-loop-control-plane-conclusion.md` (Codex
  deliberation outcome).
- `task-loop/scripts/control_log.py` — **no change expected** (loop topology is prose; the protocol
  is untouched). 58 tests must stay green.

## 9. Out of scope

- Re-introducing any external supervisor or unattended auto-relaunch (explicitly deferred — manual
  resume only).
- Changing the control protocol, attempt-fencing, recovery semantics, or merge gates.
- Re-introducing idle-notification reactivity (rejected in favor of the pure fixed poll).
