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
- **Agent Teams enabled:** `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` and Claude Code ≥ v2.1.32.
- **Prerequisite plugins** installed: `superpowers` and `dev-skills` (workers need them).
- **Scaffolding present:** `docs/task-loop/proposal.md`, `docs/task-loop/task-loop.md`,
  `docs/task-loop/directions.md`, and the `loop:in-progress` label exist.
- **`gh` authenticated** with write access to issues and PRs.

## Setup (run once at the start of a run)

1. **Control issue:** find the project's single pinned control issue (labelled
   `task-loop:control`), or create it if absent (`gh issue create`, then pin + label). Its body
   names the project; all sequenced `CONTROL_EVENT` comments live here.
2. **Runtime dir:** ensure `.claude/task-loop/` exists (gitignored) for
   `orchestrator-state.json` (the lease + fast-state cache) and `stop-request.json`.
3. **Lease:** acquire the single-coordinator lease in `orchestrator-state.json`; if a live lease
   is held by another instance, exit (do not run two orchestrators).
4. **Team:** create the agent team you will spawn `cycle-worker` teammates into.
5. **Start `/loop` self-paced** and run the orchestrator turn (below / `references/`).

## The orchestrator turn (high level)

Each `/loop` turn, in order (details in `references/orchestrator-loop.md`):
1. **Lease & rebuild:** refresh the lease; rebuild fast state by replaying the control issue
   (`control_log.replay`). On resume, take over a stale lease and rebuild from GitHub.
2. **Stop check:** if `.claude/task-loop/stop-request.json` exists → enter `draining`.
3. **Event-drain & ingest:** read each task issue's comments at/after its scan floor, dedupe by
   UUID, **process findings before merge requests**, emit a source-tagged `CONTROL_EVENT` for
   each ingested inbox event, and advance per-issue scan checkpoints.
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
- Run it bounded: drive the orchestrator under `/loop` self-paced; set the stop time with a
  scheduled writer of `.claude/task-loop/stop-request.json` (see the Phase 0 spike for the
  available primitive).
