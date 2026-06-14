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

## Control plane — one live loop + two guard jobs (no local files)

`run-cycle` runs as **three cooperating jobs** — a running loop cannot reliably police its own
death, so two sibling guard jobs bound and watch it. **No local files**: all coordination state
lives in GitHub (the single control issue); schedule handles live in the scheduler itself,
recorded in the control-issue body.

1. **Running loop (loop 1)** — a **live `/loop` Agent-Teams lead session** (the orchestrator),
   **not** a scheduler job. Each turn it **heartbeats its lease into the control-issue body**,
   replays the control-issue comment log to rebuild fast state, plans → dispatches → merges, and
   **self-bounds on `stop_at`**. Teammate idle notifications are a **within-session latency
   optimization, not part of correctness** — correctness rests entirely on GitHub replay +
   idempotent respawn (see `references/`).
2. **Watchdog (loop 3)** — a **recurring scheduler job every 30 min**. It reads the control-issue
   body; if loop 1's `heartbeat` is stale **and `now < stop_at`**, loop 1 is presumed dead:
   - **Tier 0 (always — the guaranteed floor): detect + alert.** Post a **plain non-control
     comment** (no `task-loop-event` fence — invisible to the sequencer) plus a push notification
     "orchestrator down, resume needed." Recovery is then a clean **manual `/run-cycle`** (it
     rebuilds 100% from GitHub — that is the payoff of no-local-files).
   - **Tier 1 (only if a tested local supervisor is configured): unattended auto-relaunch.** A
     dead `/loop` session cannot relaunch itself and a cloud routine cannot spawn local Agent-Teams
     teammates, so true auto-resurrection needs a **named local supervisor** (OS launchd/cron, or
     a verified locally-running job) with a tested launch template (repo cwd, `CLAUDE_CODE_
     EXPERIMENTAL_AGENT_TEAMS=1`, plugin loaded, `gh` authed, `/run-cycle` under `/loop`, log
     capture). That is **setup/config, not runtime state**, but it is a real precondition — the
     Phase-0 spike must validate it before any unattended-resurrection claim. Absent it, the
     watchdog stays at Tier 0.
   The `now < stop_at` guard ensures neither tier resurrects the run after an intentional stop.
3. **Stop (loop 2)** — a **one-time scheduler job at `stop_at`**. It reads the control-issue body
   for `watchdog_schedule_id`, **cancels the watchdog (loop 3) first** (so it can't resurrect the
   run), then confirms loop 1 has drained. The clean teardown of loops 1 **and** 3.

The two guard jobs (2 & 3) and any Tier-1 relaunch must run in the **same local environment**
where Agent Teams is enabled. Their handles (`watchdog_schedule_id`, `stop_schedule_id`) live in
the **control-issue body runtime header** (orchestrator is its sole writer) so loop 2 can cancel
loop 3 — **no `orchestrator-state.json`, no flag file, nothing on local disk.**

## Setup

`run-cycle` is invoked two ways — a **fresh start** (you) or a **resubmit** (loop 3, after a
crash). Detect which **first**, and keep **all** state in GitHub — no local files:

0. **Control issue:** find the project's single pinned control issue (labelled
   `task-loop:control`), or create it if absent (`gh issue create`, then pin + label). Its
   **comments** are the append-only, sequenced `CONTROL_EVENT` log; its **body** is the mutable
   **runtime header** — a fenced ` ```task-loop-runtime ` JSON block holding `lease`, `stop_at`,
   `watchdog_schedule_id`, `stop_schedule_id`, and an advisory `phase`. The orchestrator (loop 1)
   is the header's **sole writer**; loops 2 & 3 only read it.
1. **Fresh vs resubmit:** read the body header. If it already holds a valid `stop_at` **and** both
   schedule handles, this is a **resubmit/resume** — **skip the duration prompt and schedule
   creation** (steps 4–6); the loops already exist. Otherwise it is a **fresh start**.
2. **Lease:** read the header `lease`. If a **live** lease (`expires_at` in the future) is owned by
   a different instance → **exit** (never two orchestrators). Else claim it: write the header with
   your `lease` (`owner`, `expires_at = now + TTL`, `heartbeat = now`), then **re-read and confirm
   you still own it** before any side effect (the **write-then-re-read fence** — GitHub has no
   atomic CAS). This is the only single-coordinator guard — no local lock file.
3. **Team:** create the agent team you spawn `cycle-worker` teammates into (recreated on a
   resubmit, since teammates are ephemeral).
4. *(fresh only)* **Run duration (prompt for it).** **Ask the user** *"How long should the loop run
   before a graceful stop? (default: 24 hours)"* — accept a duration or an absolute time, **default
   24 hours**. An **interactive prompt, not a command-line argument**. Write the absolute `stop_at`
   (UTC) into the body header.
5. *(fresh only)* **Create the watchdog (loop 3)** with the built-in scheduler: a recurring job
   **every 30 min** that, when the header `heartbeat` is stale and `now < stop_at`, **detects +
   alerts** (Tier 0: a plain non-control comment + push notification) and — only if a tested local
   supervisor is configured — auto-relaunches `run-cycle` (Tier 1). Write its handle into the header
   as `watchdog_schedule_id`. (See *Control plane* for the Tier-0/Tier-1 launcher contract.)
6. *(fresh only)* **Create the stop (loop 2)** with the built-in scheduler: a one-time job at
   `stop_at` that reads `watchdog_schedule_id` from the header, **cancels it**, then confirms loop 1
   has drained. Write its handle into the header as `stop_schedule_id`.
7. **Run the orchestrator turn (loop 1)** (below / `references/`). It self-bounds: each turn it
   compares the clock to `stop_at` and caps its next wake so it wakes by `stop_at` to drain — so the
   run stops even if loop 2 fails. (To run longer or stop sooner, edit `stop_at` in the header.)

## The orchestrator turn (high level)

Each `/loop` turn, in order (details in `references/orchestrator-loop.md`):
1. **Lease & rebuild:** refresh the lease; rebuild fast state by replaying the control issue
   (`control_log.replay`). On resume, take over a stale lease and rebuild from GitHub.
2. **Stop check:** if the clock has reached `stop_at` (from the control-issue body header) → enter
   `draining`.
3. **Event-drain & ingest:** read each task issue's comments at/after its scan floor, dedupe by
   UUID, **process findings before merge requests**. Ack a fresh `PLAN_FINDING` here (one
   `PLAN_FINDING_RECORDED`); a fresh `MERGE_REQUEST` is **not** acked here — it is collected as a
   *pending decision* acked only by the merge gate (§5). Advance a per-issue scan checkpoint only
   through a fully-acked prefix, so a pending merge request pins the floor and is re-ingested
   until decided.
4. **Replan barrier:** read `directions.md` (highest priority); if a finding invalidated a
   hypothesis, **materialize** a new `plan_revision` (merge the proposal-update PR to `master`,
   then emit `PLAN_REVISION_BUMP`), recompute the frontier, and halt dispatch of the stale
   subgraph.
5. **Merge first** (sole integrator): integrate completions **before** dispatching so a merge that
   finishes a dependency unblocks its dependents this same turn. **Re-confirm the lease before `gh pr
   merge` — never merge after losing it** (a same-identity second lead makes the reconcile path
   unable to tell a stale merge from a valid one). On a `MERGE_REQUEST` that is **attempt-current**
   (`attempt_id == current_attempt_id`, else `MERGE_DENIED`) and revision-compatible, validate
   against the freshly-drained state and `gh pr merge --squash --delete-branch --match-head-commit
   <SHA>`; emit `MERGE_GRANTED` (or `MERGE_DENIED` + `TASK_STALE`).
6. **Dispatch — proactive, seat-capped** (unless draining): re-confirm the lease, then from the
   **post-merge** state **select → dispatch**. The frontier and the **aging key are log-derived**
   (`ready_since` = the seq of a task's last-dependency `MERGE_GRANTED`), so **only the ≤5 selected
   tasks touch GitHub** — a 200-task frontier still creates ≤5 issues. **Dispatchable** = deps merged
   + revision-compatible + (status `ready` **or** `active` with no live worker — an orphaned attempt
   recovered via `adopt_from_branch`); a **live** worker, `merged`, or `stale` is excluded. **Select**
   up to **5 concurrent `cycle-worker` teammates** (documented guideline, not enforced) by
   `directions.md` priority, then oldest `ready_since`, then `proposal.md` Roadmap order, reserving ≥1
   seat for the oldest (starvation-free). **Active workers never suppress dispatch, but a lead never
   *intentionally* exceeds 5 in flight** (best-effort per-session cap; a watchdog false-positive
   takeover may transiently exceed it, correctness-safe via attempt fencing). **Dispatch** each
   selected task: idempotently create/reuse its `Task-Loop-Task:
   <task_id>`-marked issue, emit `TASK_CREATED{…, iteration}` (first dispatch) + `TASK_DISPATCHED{…,
   attempt_id}`, and spawn **one** `cycle-worker` teammate (`agentType: cycle-worker`) with `task_id`,
   the task issue number, `control_issue`, `spawned_plan_revision` (= current), `iteration`, a fresh
   `attempt_id`, the per-attempt branch `<branch>-attempt-<attempt_id>`, `lead_worktree_root`, and
   the scope.
7. **Wait / idle / exit:** reached only after §6 has filled every free seat it can. Teammate **idle
   notifications are the primary wake**; add a **bounded, jittered** fallback `ScheduleWakeup`
   (shorter when a capped backlog waits on a freeing seat, never a busy-loop); **idle** (long
   `ScheduleWakeup`, do **not** exit) only when the frontier is empty with no stop signal; when
   draining completes, run the recorded **pre-exit audit** and a **two-phase quiescence exit**
   (cooldown + re-audit) before stopping.

## Hard invariants

- **Sole integrator:** only the orchestrator runs `gh pr merge`. Workers end at
  `MERGE_REQUEST`.
- **Single writer:** only the orchestrator writes the **control-issue body runtime header**, emits
  sequenced `CONTROL_EVENT`s, bumps `plan_revision`, and edits `docs/task-loop/proposal.md`.
- **Merge gates:** every merge passes the **pre-merge event-drain barrier** and is
  **head-SHA-bound** (`--match-head-commit`); no revision becomes current until its
  proposal-update PR is merged to `master` (materialization).
- **Proactive, seat-capped dispatch:** each turn merges completions **first**, then dispatches ready
  tasks into free seats **up to 5 concurrent workers** (documented guideline, not enforced). Active
  workers never suppress dispatch — a task unblocked by a merge is submitted the **same turn** if a
  seat is free — but a lead never *intentionally* runs >5 (best-effort per-session cap; a watchdog
  false-positive may transiently exceed it, bounded by attempt fencing); selection is
  priority-then-oldest-ready (starvation-free).
- **Continuous service:** "no ready work" is `idle`, never exit. Termination is a scheduled
  **drain-signal**, with a bounded, non-destructive drain (overdue workers →
  `orphaned_acknowledged`).
- **Labels are a human index only;** the GitHub append-only control-event log is authoritative;
  the Agent-Teams mailbox is notification-only.

## Helpers

The control protocol is implemented in the plugin's `scripts/` (`${CLAUDE_PLUGIN_ROOT}/scripts`
when set, else the installed `task-loop/scripts/`):
`control_log` (`format_event`, `parse_events`, `filter_new_inbox`, `assign_seq`,
`unacknowledged_uuids`, `comments_at_or_after_watermark`, `replay`; plus `parse_recovery` /
`latest_recovery` for reading a worker's per-attempt recovery comments) and `gh_store`
(`read_comments`, `post_comment`). Use them — do not re-derive sequencing/dedupe/replay by hand.

## Additional resources

- **`references/orchestrator-loop.md`** — the full state machine, coordination protocol, replan
  barrier, merge gate, lease/recovery, and quiescence exit. **Read before driving the loop.**
- Design rationale: `docs/superpowers/specs/2026-06-13-task-loop-plugin-design.md` (§7, §8, §11,
  §12) and the two conclusions (`…-cycle-loop-mechanism-conclusion.md`,
  `…-living-proposal-ownership-conclusion.md`).
- Run it bounded: it is **always** bounded by a graceful stop time — Setup step 4 prompts for a
  duration (**default 24 hours**) and records an absolute `stop_at` in the control-issue body
  header; the orchestrator self-bounds (caps its next wake to `stop_at`) and drains + exits when it
  reaches `stop_at` — **no local files, no flag file, no external stopper.**
