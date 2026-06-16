# Task-loop orchestrator pass — Codex deliberation conclusion

**Date:** 2026-06-15
**Goal:** Improve the per-tick algorithm of the redesigned task-loop orchestrator (`run-cycle`),
starting from the operator's 6-step pass, under the decided harness (Supabase task DB + CLI;
cycle-worker teammates; idempotent/stateless orchestrator; no control issue; fixed-interval Loop A +
a Loop B to stop it).
**Method:** `dev-skills:discuss-with-codex`, 6 rounds, converged by full concession on every point.
**Companion:** the authoritative design spec
`2026-06-15-task-loop-supabase-harness-design.md` (this conclusion refines §7–§9 of it).

Codex was adversarial-correct on all four contested points; the settled design below is the operator's
6-step pass with four hard corrections folded in.

---

## Settled design

### 1. Per-tick pass order — directions FIRST
Read human steering **before** any irreversible action; it is highest-priority, so it cannot be read
after merges. Each fixed-interval tick, in order:

0. **Read state** — `task-loop status` (the board) + open PRs/issues (GitHub) + `docs/task-loop/directions.md`.
1. **Honor steering** — apply current `directions.md` constraints before acting this tick (pause/serialize
   dispatch, freeze merges, "don't merge PR #X", priorities, explicit blockers). Free-form prose; the
   orchestrator interprets it, not a rigid DSL.
2. **Liveness / progress** — for each teammate **this orchestrator spawned this session**, verify it is
   alive and ask for a progress line (skip if none dispatched).
3. **Merge** (only PRs allowed by step 1) — for each `working` task with a ready PR (CI green +
   independent review check green), merge → `gh issue close <issue>` → `task-loop close <seq>`, then
   reap the now-idle teammate.
4. **Findings → proposal (reconcile sweep)** — see §3 below.
5. **Materialize tasks** — from the freshly-reconciled proposal + merged findings + directions: create
   discovered blocker tasks, re-create blocked tasks with their dependency, create direction-instructed
   tasks, create finding-unlocked tasks driving the GOAL. Idempotent (reuse an issue carrying a task
   marker; never re-add a task whose issue already exists).
6. **Dispatch** — `task-loop claim` in a loop → spawn one cycle-worker teammate per claimed task, up to
   a soft capacity.

`directions.md` is also an **exogenous trigger**: a tick does real work whenever directions OR findings
introduce change — not only when a worker finished. (Codex round 1: "only real work when an agent
finished" was too strong.)

### 2. Reset rule (liveness authority) — the central correction
`task-loop claim` protects `open → working` (atomic, `FOR UPDATE SKIP LOCKED`) but **not**
`working → open`. A PR is a durable artifact (merge is safe for any orchestrator); a PR-absent
`working` task is **ambiguous** — without a durable ownership/liveness marker you cannot distinguish
"alive but pre-PR" from "dead". So **reset has exactly two triggers**:

- **(a) In-session observed death** — this orchestrator spawned the teammate this session and saw it
  die / finish without a PR → auto `reset`. Always safe.
- **(b) Human direct CLI** — the operator runs `task-loop reset <seq>` out-of-band (only the human
  knows whether another orchestrator is live).

A **cold / fresh / foreign** tick **never** auto-resets an opaque `working`-no-PR task — it only
**surfaces** it ("`012` looks orphaned; if no orchestrator is live, run `task-loop reset 012`"). It
still merges PR-present tasks and dispatches claimable. `directions.md` **never** triggers reset (it is
standing steering, not a consumable queue; a stale `reset 012` line would re-fire and kill a new live
worker). **No lease / heartbeat / attempt-id / timer / ownership marker is added.**

**Accepted cost:** running multiple concurrent orchestrators on one project loses *automatic* recovery
of pre-PR orphans (a human `reset` handles the rare stuck one). Single-orchestrator operation —
including sequential cross-machine (stop here, start there) — keeps full auto-recovery, because
Agent-Teams teammates die with their session, so the spawning session is the only one that ever has a
live teammate to observe.

### 3. Proposal update is a reconcile sweep, not a patch
The orchestrator is the sole editor of `proposal.md`. Concurrent orchestrators patching it from a stale
base can merge **cleanly in text yet incoherently in meaning** ("H2.1 rejected" + "Stage 3 unlocked").
So:

- Every proposal PR is computed from **(current default-branch `proposal.md`) + (the complete set of
  merged study-logs/findings not yet reflected in it)** — never one orchestrator's stale local patch.
- Merge a proposal PR only if its base is the current default; if default moved, **discard and
  regenerate**.
- Task materialization (step 5) reads the freshly-reconciled proposal, so it never spawns work from a
  stale interpretation.

Study-logs are git-tracked on the default branch, so "complete merged evidence" is a readable set; the
proposal may carry an "incorporated through task `<seq>`" marker to make "not yet reflected" cheap. No
lock needed — the reconcile sweep is convergent.

### 4. Stop model — Loop B is a non-destructive nudge; Loop A self-stops
- **Loop A** = the fixed-interval `/loop` running the pass. Its tick is the **sole stop decision**:
  when `now ≥ stop_at` and the board is drained, Loop A cancels **its own** schedule id and stops.
- **Loop B** = a one-time job at `stop_at` that **wakes/nudges Loop A** so it stops at ~`stop_at`
  instead of up to one interval late. It is **non-destructive** — it never force-stops or deletes
  anything, so a **stale Loop B fire is harmless** (the woken tick re-checks the current `stop_at` and
  continues if it was extended).
- **`stop_at` is embedded as a literal in Loop A's recurring `/loop` prompt** — every tick self-checks
  it with zero stored state.
- Jobs carry a **`run_generation`** literal in their names (`task-loop-<project>-<gen>-A` / `-B`), so a
  stale job touches only its own generation, never "whatever A exists for this project." Re-invoking
  `/run-cycle` best-effort cancels all `task-loop-<project>-*` and creates a fresh generation.
- **No Supabase runtime cell, no stored schedule handle, no local file** — generation + naming +
  embedded `stop_at` suffice.

---

## Strongest objections Codex raised, and how each resolved

1. **`directions.md` read too late** (R1) → moved to the first action; it gates the tick and is an
   exogenous trigger. *Conceded.*
2. **Liveness unsound under concurrency** (R2) — a foreign orchestrator resets a live-but-pre-PR task →
   duplicate work. *Conceded;* reset restricted to PR-present-merge-safe + the two reset triggers.
3. **"Sole-orchestrator" is an off-ledger promise** (R3) — not derivable from state. *Conceded;* auto
   reset only on in-session death; cold sessions hold.
4. **`directions.md` is not a consumable command queue** (R4) — a standing `reset` line re-fires. *Conceded;*
   reset is in-session or direct CLI only; directions only surface.
5. **Git serializes text, not planning semantics** (R5) — clean-merge-incoherent-meaning. *Conceded;*
   proposal update is a reconcile sweep from current default + complete evidence.
6. **A destructive Loop B with a fixed name kills a newer run** (R6) → Loop B non-destructive +
   `run_generation` naming; Loop A self-stops on its own schedule id. *Conceded.*

## Unresolved tensions
None substantive. The one residual is **operational, not a bug**: concurrent multi-orchestrator
deployments trade automatic pre-PR orphan recovery for a human `reset`. This is the honest price of
"no lease / no marker / no timer" and is documented, not hidden.

**How it ended:** converged by full concession after 6 rounds (the round cap), with no live
disagreement remaining.

---

## Addendum — closure / termination verification (2026-06-15)

A second Codex deliberation independently verified that the loop **drives the team to the goal and
terminates** (no infinite spin, no silent stall). Codex found a real hole in *every* round; each fix
tightened the design until it converged on **NO FURTHER OBJECTIONS**. (The `codex exec resume` thread
hung twice mid-turn; fresh `codex exec` threads were used instead — a tooling issue, not a
disagreement.)

Holes found → fixes (all now in `run-cycle` SKILL + `references/orchestrator-loop.md` and §8–§9 above):

1. **Stuck / never-mergeable PR spins forever** — the worker opens a PR then idles, so a red/stuck PR
   is never repaired; "something `working` = progress" masked it, and `stop_at` draining ("stop when no
   `working` remains") never fired. → **Real-progress predicate** (a gate-failed/stuck working task is
   *not* progress) + step-3 PR classification; drain waits only for real-progress.
2. **Livelock guard needs durable per-unit retry accounting the DB lacks** — re-materializing a failed
   unit as a new task looks "fresh" each time, so a K-failure guard can't fire. → **No auto-recreation;
   the GitHub issue is the durable per-unit identity** (1:1, never duplicated). Gate-failed/stuck →
   label `needs-human`, leave the task; retry is human-only.
3. **"Unmet + board empty" is a *planning* gap with no task → silent terminal stall** (nothing
   surfaced). → before idling, **guarantee a durable surfaced blocker**: per-unit `needs-human` issues,
   plus a proposal-level `needs-human: proposal-unmet-no-planned-work` for a planning gap. Also
   **head-SHA-atomic merge** (`--match-head-commit`) to defeat a green→red flap between classify and merge.
4. **Gate-green but merge-blocked** (PR conflicted / behind a required base after `main` moved) — the
   atomic merge rejects for a non-head reason and nothing surfaces it → per-unit stall. → **`MERGEABLE`
   includes GitHub merge-state (clean, not behind)**; any deterministic merge rejection →
   `needs-human: merge-blocked`. **PR classification is now total** over states.

**Settled closure invariant:** every tick, a `working` task is exactly one of *merge-and-close*,
*pending-within-a-bound*, or *`needs-human` (surfaced, not progress, not blocking drain)*; the board is
never left empty short of the goal without a durable surfaced blocker; nothing failed is auto-recreated.
⟹ every tick **advances a task, finishes the goal, or has durably asked for help** — and the run always
terminates (goal-met, or surfaced-and-idle, or `stop_at`). Codex: converged, no further objections.
