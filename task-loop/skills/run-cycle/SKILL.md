---
name: run-cycle
description: This skill should be used when the user asks to "run cycle", "run the task loop", "start the orchestrator", "drive the autonomous loop", or to begin autonomous, orchestrated execution of a task-loop project. It runs the orchestrator under a fixed-interval loop; each tick honors human steering, reconciles working tasks (merge/close; reset only its own dead workers), reconciles the roadmap, and dispatches claimable tasks. Idempotent — every tick re-derives state from the task DB + GitHub + directions.md.
version: 0.2.0
---

# Run Cycle

## Overview

Third and final step of the task-loop workflow (`specify-aims` → `create-cycle` → **`run-cycle`**).
This skill is the **orchestrator** (the main agent): sole **dispatcher / decider / merger** and the
sole **editor of `proposal.md`**. It talks to the task DB **only** via the `task-loop` CLI and to
GitHub via `gh`; `cycle-worker` teammates do the tasks.

**Idempotent & stateless.** All durable state lives in **Supabase** (the board), **GitHub**
(PRs/issues), and the git-tracked `docs/task-loop/` files. Every tick re-derives from
`task-loop status` + GitHub + `directions.md` and takes the same action — there is **no** control
issue, **no** lease, and **no** local runtime files. **Recovery is just the next tick.**

The full per-tick algorithm is in **`references/orchestrator-loop.md`** — read it before driving.
This design was pressure-tested with Codex:
`docs/superpowers/specs/2026-06-15-task-loop-orchestrator-pass-conclusion.md`.

## When to use / not use

- **Use** to run autonomous execution once `specify-aims` + `create-cycle` produced
  `docs/task-loop/proposal.md` + `task-loop.md`, and `setup` registered the repo.
- **Do not use** to author docs or to run a single task by hand.

## Preconditions (fail fast)

- **Agent Teams enabled** — `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` (cycle-workers are teammates).
- **Required skills loadable this session** — the 8 skills the harness invokes appear in the
  available-skills list: `superpowers:{brainstorming, writing-plans, test-driven-development,
  verification-before-completion, receiving-code-review}` and `dev-skills:{discuss-with-codex,
  goal-rubric, doc-update}`. Skill availability is **session/project state** (a disabled plugin would
  otherwise surface only mid-task, after a worker claimed), so re-check it **every run** before
  scheduling Loop A — not just at `setup`.
- **The CLI works** — `task-loop status` succeeds (setup done: `login` + schema + `init`).
- **`gh` authenticated** with write to issues and PRs.
- **Scaffolding present** — `docs/task-loop/task-loop.md`, `proposal.md`, `directions.md`.
- **Merge backstop (recommended)** — branch protection requires CI + an independent review check, and
  the orchestrator is the only identity allowed to merge.

## Control plane — fixed-interval Loop A, non-destructive Loop B

`run-cycle` sets up two scheduled jobs, both named with a fresh **`run_generation`** so a stale job can
never touch a newer run:

- **Loop A** — a **fixed-interval** loop (default 15 min) that runs **the pass** below. `stop_at` and
  `run_generation` are **embedded in its prompt**, so each tick sees them with zero stored state. Named
  `task-loop-<project>-<gen>-A`.
- **Loop B** — a **one-time** job at `stop_at` that **wakes Loop A to run a tick promptly**. It is
  **non-destructive** — it never force-stops anything — so a stale fire is harmless: the woken tick
  re-checks the *current* `stop_at` and continues if it was extended. Named `…-<gen>-B`.

**Stopping is Loop A's own decision:** a tick stops the run (cancels its own `-A`/`-B` schedules) once
the board is drained and **either** the proposal's **Success criteria are met** (goal achieved — the
natural finish) **or** `now ≥ stop_at` (the time bound). To change the bound, re-invoke
`/run-cycle` — it mints a new generation, best-effort cancels every `task-loop-<project>-*` job, and
recreates both. No DB cell, no stored handle, no local file.

## Setup (on invocation)

1. Verify preconditions. 2. Ask the run duration (default 24h) → compute `stop_at` (UTC); mint
`run_generation` (`date -u +%s`). 3. Best-effort cancel stale `task-loop-<project>-*` jobs. 4. Ensure
the cycle-worker **team** exists (recreate on a fresh session — teammates are ephemeral). 5. Create
Loop A + Loop B (above). Loop A then runs unattended.

## The pass (each Loop A tick — details in `references/orchestrator-loop.md`)

0. **Read state** — `task-loop status` + open PRs/issues + `docs/task-loop/directions.md`.
   **Stop check:** `now ≥ stop_at` → *draining* (skip dispatch; drain working tasks; when none remain,
   cancel the `-A`/`-B` schedules and stop).
1. **Honor steering** — apply `directions.md` constraints *first* (pause/freeze, "don't merge #X",
   priorities, blockers). Steering can trigger a tick on its own — not only when a worker finished.
2. **Liveness** — for each teammate **you spawned this session**, confirm it's alive and ask one
   progress line (skip if none).
3. **Merge / classify** (only PRs steering allows) — per `working` task's PR: **mergeable** (CI +
   review green **and** GitHub merge-state clean — no conflict/behind) → `gh pr merge --squash
   --match-head-commit <SHA>` (atomic; a green→red flap is rejected) → `gh issue close <issue>` →
   `task-loop close <seq>` → reap the idle teammate. **Gate-failed / merge-blocked / stuck** (required
   check red, review failed, conflict/behind/blocked, a deterministic merge rejection, or pending past
   the bound / never posts) → label the issue `needs-human`, surface once, and **leave the task** — the
   idle worker won't repair it, and closing+recreating would spin (retry is human-only). **Pending**
   (within bound) → leave for next tick.
4. **Findings → proposal (reconcile sweep)** — if merged findings change the roadmap, recompute
   `proposal.md` from *current default + all merged findings not yet reflected* (never a stale patch),
   PR it, merge it.
5. **Materialize tasks (the goal-driver)** — ensure the board carries the next work toward the
   **Success criteria**: the proposal's **planned stages not yet turned into tasks** (the initial seed
   on an empty board *and* ongoing decomposition), discovered blockers, blocked re-creation (`--dep`),
   direction- and finding-driven tasks. Idempotent (reuse a marked issue; never duplicate). While the
   goal is unmet this always adds the next task(s) — or flags that the gap needs a human (step 7).
6. **Dispatch** (skip if draining) — `task-loop claim` in a loop → spawn one cycle-worker per claim
   (seq, title, issue, branch), record its id, up to your soft capacity.
7. **Goal check / terminate** — evaluate the **Success criteria** against the repo (run them; don't
   infer from "tasks closed"). **Met** → done: drain + stop. **Unmet + real progress** (a `working`
   task whose worker is advancing or whose PR is mergeable/genuinely-pending, *or* a `claimable` task)
   → continue. **Unmet + no real progress + nothing claimable** → before idling, **ensure a durable
   surfaced blocker exists**: per-unit `needs-human` issues (step 3), plus — for a *planning* gap
   (empty board / deadlock / criteria stricter than any task) — a proposal-level
   `needs-human: proposal-unmet-no-planned-work` issue. Then idle ("asked for help"); never idle on an
   unmet goal with nothing surfaced. Drain waits only for real-progress tasks, so `stop_at` always fires.

## Reset rule (the one subtle invariant)

`task-loop claim` makes `open → working` atomic but **not** `working → open`. A PR is durable (any
orchestrator may merge it); a PR-absent `working` task is **ambiguous** (can't tell live-pre-PR from
dead). So **reset only when you positively know no live worker owns it:**

- **(a)** you spawned that teammate **this session** and saw it die / finish without a PR →
  `task-loop reset <seq>`; or
- **(b)** the human runs `task-loop reset <seq>` directly.

A cold / fresh / foreign tick **never** auto-resets an opaque `working`-no-PR task — it only
**surfaces** it ("`012` looks orphaned; if no orchestrator is live, run `task-loop reset 012`"). It
still merges PR-present tasks and dispatches claimable. `directions.md` **never** triggers reset (it is
standing steering, not a consumable queue). Concurrent multi-orchestrator therefore trades automatic
pre-PR orphan recovery for a human reset; single / sequential-cross-machine operation keeps it.

## Hard invariants

- **Sole merger, sole CLI user, sole `proposal.md` editor.**
- **`task-loop claim` is the only dispatch lock** — no lease, no other guard.
- **Idempotent passes:** reset only via (a)/(b); proposal updates are **reconcile sweeps, never stale
  patches**; task/issue creation is idempotent.
- **Branch protection is the structural merge backstop**; a task-loop-specific merge hook is not part
  of this harness.

## Helpers — the `task-loop` CLI (the only DB access)

`task-loop status | add "<title>" [--dep N…] [--issue N] | claim | close SEQ | reset SEQ` — run via
`uv run ${CLAUDE_PLUGIN_ROOT}/cli/task-loop …`. Project (`owner/repo`) auto-detected from the git
remote. GitHub (issues / PRs / merge) via `gh`. Never bypass the CLI to touch the DB.

## Additional resources

- **`references/orchestrator-loop.md`** — the full per-tick algorithm, reset rule, proposal reconcile,
  stop model, recovery, and multi-orchestrator notes. **Read before driving.**
- **`${CLAUDE_PLUGIN_ROOT}/references/pr-findings.md`** — the study-log contract the orchestrator reads.
- Design: `docs/superpowers/specs/2026-06-15-task-loop-supabase-harness-design.md`; deliberation:
  `…-2026-06-15-task-loop-orchestrator-pass-conclusion.md`.
