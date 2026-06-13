---
name: run-cycle
description: This skill should be used when the user asks to "run cycle", "run the task loop", "start the orchestrator", "start the task-loop run", "drive the autonomous loop", or to begin autonomous, orchestrated execution of a task-loop project. It runs the orchestrator under built-in /loop (self-paced): each turn it computes the dependency-ordered task frontier from a single GitHub control issue, spawns one cycle-worker teammate per ready task, validates and merges their PRs (sole integrator), and terminates by a scheduled drain-signal — not an iteration cap.
version: 0.1.0
---

# Run Cycle

## Overview

Third and final step of the task-loop workflow (`specify-aims` → `create-cycle` →
**`run-cycle`**). It is the **orchestrator**: the main agent, driven by built-in **`/loop`
(self-paced)**, that plans and dispatches work and is the **sole integrator** (the only agent
that merges). It does **not** run any task's cycle itself — `cycle-worker` teammates do that,
one per task.

Each `/loop` turn the orchestrator rebuilds its state from the canonical **control issue**
(a single pinned GitHub issue holding the append-only, single-sequencer event log), ingests
worker inbox events, computes the dependency-ordered frontier, dispatches one `cycle-worker`
per ready task, merges the PRs that pass the gates, and either idles (no ready work, no stop
signal) or drains and exits (stop signal). The full state machine and coordination protocol
are in **`references/orchestrator-loop.md`** — read it before driving the loop.

## When to use / not use

- **Use** to start (or resume) autonomous execution once `specify-aims` and `create-cycle`
  have produced `docs/task-loop/proposal.md` and `docs/task-loop/task-loop.md`.
- **Do not use** to author docs (that is `specify-aims`/`create-cycle`) or to run a single
  task by hand. This skill assumes the project is scaffolded and runs unattended.

## Preconditions (fail fast)

Before starting, verify and stop with guidance if any fails:
- **Scaffolding present:** `docs/task-loop/proposal.md`, `docs/task-loop/task-loop.md`,
  `docs/task-loop/directions.md`, and the `loop:in-progress` label exist.
- **`gh` authenticated** with write access to issues and PRs.
- **No out-of-protocol merges:** the orchestrator is the *sole integrator*, so task-loop PRs must
  not be mergeable by anything else — **disable auto-merge and any merge queue**, and restrict
  merge permission to the orchestrator's own identity. (The merge gate also verifies `mergedBy`
  provenance and **halts** if it ever finds a task-loop PR merged by someone else, rather than
  laundering it as authorized — but settings should prevent that case.)

## Control plane — three coordinated loops

`run-cycle` runs as **three** cooperating loops, because a running loop cannot reliably police
its own death:

1. **Running loop (loop 1)** — *this* session under built-in `/loop` self-paced: it drives the
   orchestrator turn (plan → dispatch → merge), **heartbeats its lease every turn**, and
   self-bounds on `stop_at`.
2. **Stop loop (loop 2)** — a **one-time** scheduled job (built-in `schedule`) at `stop_at`. It
   **cancels the watchdog (loop 3) first** (so it can't resurrect the run after an intentional
   stop), then confirms loop 1 is draining. The clean teardown.
3. **Watchdog loop (loop 3)** — a **recurring** scheduled job (built-in `schedule`) **every
   30 minutes**: if loop 1's lease `heartbeat` is stale (it crashed/exited) **and
   `now < stop_at`**, it **resubmits loop 1** (re-invokes `run-cycle`, which resumes from durable
   state). The `now < stop_at` guard is a second safety so it never resurrects after the stop.

So loop 3 keeps loop 1 alive through crashes; loop 2 tears down loops 1 **and** 3 at `stop_at`.
Loops 2 & 3 are created via the built-in `schedule`; their handles live in
`orchestrator-state.json` (`stop_schedule_id`, `watchdog_schedule_id`) so loop 2 can cancel
loop 3.

## Setup

`run-cycle` is invoked two ways — a **fresh start** (you) or a **resubmit** (loop 3, after a
crash). Detect which **first**:

0. **Fresh vs resubmit:** read `orchestrator-state.json`. If it already holds a valid `stop_at`
   **and** schedule handles, this is a **resubmit/resume** — **skip the duration prompt and the
   schedule creation** (steps 5–7); the loops already exist. Otherwise it is a **fresh start**.
1. **Control issue:** find the project's single pinned control issue (labelled
   `task-loop:control`), or create it if absent (`gh issue create`, then pin + label). Its body
   names the project; all sequenced `CONTROL_EVENT` comments live here.
2. **Runtime dir:** ensure `.claude/task-loop/` exists (gitignored) for `orchestrator-state.json`.
3. **Lease:** acquire the single-coordinator lease in `orchestrator-state.json`; if a live lease
   is held by another instance, exit (do not run two orchestrators).
4. **Team:** create the agent team you will spawn `cycle-worker` teammates into (recreated on a
   resubmit, since teammates are ephemeral).
5. *(fresh only)* **Run duration (prompt for it).** **Ask the user** how long it should run —
   *"How long should the loop run before a graceful stop? (default: 24 hours)"* — accepting a
   duration or an absolute time, **default 24 hours**. This is an **interactive prompt, not a
   command-line argument**. Record the absolute `stop_at` (UTC) in `orchestrator-state.json`.
6. *(fresh only)* **Create the watchdog (loop 3)** with the built-in `schedule`: a recurring job
   **every 30 min** that resubmits `run-cycle` when loop 1's lease `heartbeat` is stale and
   `now < stop_at`. Store its handle as `watchdog_schedule_id`.
7. *(fresh only)* **Create the stop (loop 2)** with the built-in `schedule`: a one-time job at
   `stop_at` that **cancels `watchdog_schedule_id`** then confirms loop 1 has drained. Store its
   handle as `stop_schedule_id`.
8. **Start `/loop` self-paced** (loop 1) and run the orchestrator turn (below / `references/`).
   It self-bounds: each turn it compares the clock to `stop_at` and caps its `ScheduleWakeup` so
   it wakes by `stop_at` to drain — so the run stops even if loop 2 fails. (To run longer or stop
   sooner, edit `stop_at`.)

## The orchestrator turn (high level)

Each `/loop` turn, in order (details in `references/orchestrator-loop.md`):
1. **Lease & rebuild:** refresh the lease; rebuild fast state by replaying the control issue
   (`control_log.replay`). On resume, take over a stale lease and rebuild from GitHub.
2. **Stop check:** if the clock has reached `stop_at` (from `orchestrator-state.json`) → enter
   `draining`.
3. **Event-drain & ingest:** read each task issue's comments at/after its scan floor, dedupe by
   UUID, **process findings before merge requests**. Ack a fresh `PLAN_FINDING` here (one
   `PLAN_FINDING_RECORDED`); a fresh `MERGE_REQUEST` is **not** acked here — it is collected as a
   *pending decision* acked only by the merge gate (§6). Advance a per-issue scan checkpoint only
   through a fully-acked prefix, so a pending merge request pins the floor and is re-ingested
   until decided.
4. **Replan barrier:** read `directions.md` (highest priority); if a finding invalidated a
   hypothesis, **materialize** a new `plan_revision` (merge the proposal-update PR to `master`,
   then emit `PLAN_REVISION_BUMP`), recompute the frontier, and halt dispatch of the stale
   subgraph.
5. **Dispatch** (unless draining): for each ready task (deps satisfied, not active,
   revision-compatible), up to the frontier-width cap, emit `TASK_CREATED`/`TASK_DISPATCHED` and
   spawn **one** `cycle-worker` teammate (`agentType: cycle-worker`) with `task_id`, the task
   issue number, `spawned_plan_revision` (= current), and the scope.
6. **Merge** (sole integrator): on a revision-compatible `MERGE_REQUEST`, validate against the
   freshly-drained state and `gh pr merge --squash --delete-branch --match-head-commit <SHA>`;
   emit `MERGE_GRANTED` (or `MERGE_DENIED` + `TASK_STALE`).
7. **Wait / idle / exit:** wait on teammate idle notifications while workers are active; **idle**
   (long `ScheduleWakeup`, do **not** exit) when the frontier is empty with no stop signal;
   when draining completes, run the recorded **pre-exit audit** and a **two-phase quiescence
   exit** (cooldown + re-audit) before stopping.

## Hard invariants

- **Sole integrator:** only the orchestrator runs `gh pr merge`. Workers end at
  `MERGE_REQUEST`.
- **Single writer:** only the orchestrator writes `orchestrator-state.json`, emits sequenced
  `CONTROL_EVENT`s, bumps `plan_revision`, and edits `docs/task-loop/proposal.md`.
- **Merge gates:** every merge passes the **pre-merge event-drain barrier** and is
  **head-SHA-bound** (`--match-head-commit`); no revision becomes current until its
  proposal-update PR is merged to `master` (materialization).
- **Continuous service:** "no ready work" is `idle`, never exit. Termination is a scheduled
  **drain-signal**, with a bounded, non-destructive drain (overdue workers →
  `orphaned_acknowledged`).
- **Labels are a human index only;** the GitHub append-only control-event log is authoritative;
  the Agent-Teams mailbox is notification-only.

## Helpers

The control protocol is implemented in the plugin's `scripts/` (`${CLAUDE_PLUGIN_ROOT}/scripts`
when set, else the installed `task-loop/scripts/`):
`control_log` (`format_event`, `parse_events`, `filter_new_inbox`, `assign_seq`,
`unacknowledged_uuids`, `comments_at_or_after_watermark`, `replay`) and `gh_store`
(`read_comments`, `post_comment`). Use them — do not re-derive sequencing/dedupe/replay by hand.

## Additional resources

- **`references/orchestrator-loop.md`** — the full state machine, coordination protocol, replan
  barrier, merge gate, lease/recovery, and quiescence exit. **Read before driving the loop.**
- Design rationale: `docs/superpowers/specs/2026-06-13-task-loop-plugin-design.md` (§7, §8, §11,
  §12) and the two conclusions (`…-cycle-loop-mechanism-conclusion.md`,
  `…-living-proposal-ownership-conclusion.md`).
- Run it bounded: it always runs under `/loop` self-paced and is **always** bounded by a
  graceful stop time — Setup step 5 prompts for a duration (**default 24 hours**) and records an
  absolute `stop_at`; the orchestrator self-bounds via the built-in `ScheduleWakeup` (no flag
  file, no external stopper) and drains + exits when it reaches `stop_at`.
