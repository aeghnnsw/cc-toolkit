# Task-loop proactive seat-capped dispatch — Codex deliberation conclusion

**Date:** 2026-06-13 · **Method:** `dev-skills:discuss-with-codex` (adversarial), 6 rounds (round cap).
**Outcome:** Goal converged — Codex never disputed the thesis, only hardened the implementation;
every objection was applied. No `control_log.py` change; **58 unit tests pass** throughout.

## Problem

The orchestrator was "reluctant" to dispatch newly-unblocked tasks: it dispatched **before** merging
and framed `waiting` (active workers exist) as an alternative to `dispatching`. Because
`MERGE_GRANTED` is the only event that flips a dependency to `merged` (`control_log.py` status map),
a task unblocked by a merge could not be dispatched until the *next* turn, and the loop preferred to
wait on in-flight workers. User directive: when a task is unblocked, submit all possible unblocked
jobs — but cap concurrency at **5** team agents, as a **documented, not-enforced** guideline.

## Settled position

- **Merge-first → proactive, seat-capped dispatch.** Each turn merges completions (§5) **before**
  dispatch (§6), so a merge that finishes a dependency unblocks its dependents the **same turn**.
  Dispatch is proactive (fills free seats with newly-ready tasks, active workers never suppress it)
  but bounded by a **best-effort, per-lead-session, documented-not-enforced cap of 5** concurrent
  `cycle-worker` teammates.
- **`select → dispatch` with a log-derived aging key** (no materialize-first): the frontier and
  `ready_since(task)` (= seq of the task's last-dependency `MERGE_GRANTED`; `0` for a root) are
  computed from the replayed log, so **only the ≤5 selected tasks touch GitHub** (a 200-ready
  frontier still creates ≤5 issues/turn). Order: `directions.md` priority → oldest `ready_since` →
  `proposal.md` Roadmap declaration order; **reserve ≥1 seat for the oldest** (starvation-free,
  identical across resumes).
- **Lease fences within the (now-longer) turn:** re-read + re-confirm the lease before the merge
  side-effect, **again immediately before `gh pr merge`** (the irreversible action — a same-identity
  second lead defeats the `mergedBy==self` reconcile, so the only defense is not merging once the
  lease is lost), and before the dispatch batch. The per-emit check-then-append seq guard still
  fences each `CONTROL_EVENT`.
- **Idempotent issue creation:** reuse a `Task-Loop-Task: <task_id>`-marked issue before creating, so
  a crash between `gh issue create` and the `issue_number`-bearing `TASK_CREATED` never duplicates.
- **Recovery unified with selection:** orphaned-active tasks (status `active`, no live worker for
  `current_attempt_id`) are **Dispatchable** through the same frontier. **Takeover damping** defers
  their re-dispatch by one bounded recovery-probe interval on the first post-takeover turn; §7 has an
  explicit **deferred-recovery wait state** (bounded jittered probe wake, never long-idle); the
  pre-exit audit **fails** on deferred recovery candidates so the loop cannot declare false
  quiescence.
- **Waking:** idle notifications are primary; fallback is a **bounded, jittered** wake (no aggressive
  polling) — shorter (still floored/jittered) only for a capped backlog.

## Key decisions

1. Reorder the turn to **merge-before-dispatch** (was dispatch-before-merge).
2. Dispatch reframed from a *phase* to a *proactive seat-capped action* — active workers never
   suppress dispatch of newly-ready work while a seat is free.
3. Cap = **5, documented-not-enforced, best-effort per-lead-session** (user directive). It is a
   **cost** guideline, not a correctness invariant.
4. Aging key is **log-derived `ready_since`** — rejected both materialize-first (unbounds GitHub
   writes + create-before-event hazard) and a new `TASK_READY` event (control-log noise + code).
5. Correctness under the two-lead window rests on durable `attempt_id` + per-attempt branches, **not**
   on the worker count.

## Objections raised and how each resolved

1. **(R1) "No new races" too strong — merge-first lengthens the turn, stressing the soft lease.**
   Applied: intra-turn lease fence before each side-effect group (not just turn start) + end-of-turn
   heartbeat note.
2. **(R1) §7 short-wake on active-only = aggressive polling.** Applied: idle-primary + bounded
   jittered fallback; short wake reserved for a capped backlog.
3. **(R1) Priority needs a deterministic tie-break/aging.** Applied: priority → oldest `ready_since`
   → Roadmap order, reserved seat.
4. **(R2) The claimed §5 merge lease-fence wasn't actually in §5** — `gh pr merge` protected only by
   the turn-start lease; same-identity reconcile can't tell a stale merge from a valid one. Applied:
   real §5 fence at step start **and** immediately before `gh pr merge`.
5. **(R2) Starvation key undefined** — `TASK_CREATED` seq doesn't exist for unchosen tasks. Initially
   adopted Codex's materialize-first suggestion…
6. **(R3) …which overcorrected:** materialize-first bounds workers but **unbounds** GitHub issue
   creation (200 ready → 200 issues) and adds a create-before-`TASK_CREATED` duplicate hazard.
   Applied: **reverted** to a log-derived `ready_since` key (zero side effect for unselected tasks) +
   idempotent issue creation.
7. **(R3) Recovery/selection misalign** — a crashed task stays status `active`; §6 selected only
   `ready`. Applied: **Dispatchable** explicitly includes "active with no live worker"; Recovery
   section links to it.
8. **(R4) "Never exceed 5" is false in the documented watchdog-false-positive window** (two leads,
   each can't see the other's ephemeral teammates → transient ~2×). Applied: reframed the cap as
   **best-effort per-lead-session**, correctness-safe via attempt fencing; added **takeover damping**;
   declined durable worker-heartbeat enforcement as out-of-scope (user set the cap not-enforced).
9. **(R5) Takeover damping had no §7 wait state** — deferred recovery candidates could fall through to
   long idle / pass the pre-exit audit. Applied: explicit §7 deferred-recovery case + audit gate.
10. **(R6) Tie-break cited the wrong file** — `task-loop.md` is the per-task worker playbook, not the
    task roadmap. Applied: tie-break now uses the **`proposal.md` Roadmap** declaration order (the
    source §4 already computes the frontier from); SKILL.md + design spec updated to match.

## Accepted (residual) tension

The 5-worker cap is **not globally enforced**: a watchdog false-positive takeover can transiently run
up to ~2× the cap until the superseded attempts hit their merge-gate/lease fences and stop. This is
accepted as a **correctness-safe, transient cost overrun** (only one attempt can ever merge, by
durable `current_attempt_id` + per-attempt branches), consistent with the user's directive that the
cap be a documented-not-enforced guideline. Takeover damping shrinks but does not eliminate the
window. A true global cap would require durable per-worker liveness heartbeats — deliberately out of
scope.

## How it ended

Round cap (6) reached. Objections narrowed monotonically from broad hardening (R1) to a single
file-reference correction (R6); the thesis (merge-first proactive seat-capped dispatch) was never
disputed. The final objection was applied, so the goal is considered **converged**, with the residual
cap tension explicitly recorded above.
