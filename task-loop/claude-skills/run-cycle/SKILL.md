---
name: run-cycle
description: This skill should be used when the user asks to "run cycle", "run the task loop", "start the orchestrator", "drive the autonomous loop", or to begin autonomous, orchestrated execution of a task-loop project. It runs the orchestrator under a fixed-interval loop; each tick honors human steering, merges ready PRs, diagnoses and re-attacks any failed/blocked/stuck attempt with a materially-different AIM-aligned strategy (it never gives up short of the goal or the time bound), reconciles the roadmap, and dispatches the next work. Idempotent — every tick re-derives state from the task DB + GitHub + directions.md.
version: 0.4.1
---

# Run Cycle

## Overview

Third and final step of the task-loop workflow (`specify-aims` → `create-cycle` → **`run-cycle`**).
This skill is the **orchestrator** (the main agent): sole **dispatcher / decider / merger** and the
sole **editor of `proposal.md`**. It talks to the task DB **only** via the `task-loop` CLI and to
GitHub via `gh`; `cycle-worker` teammates do the tasks.

**Idempotent durable decisions.** All durable state lives in **Supabase** (the board), **GitHub**
(PRs/issues), and the git-tracked `docs/task-loop/` files. Every tick re-derives task, PR, and proposal
decisions from `task-loop status` + GitHub + `directions.md` — there is **no** control issue, **no**
lease, and **no** local runtime files. Liveness and teammate cleanup can depend on in-session teammate
handles. **Recovery is just the next tick.**

**Relentless (never gives up).** Short of the time bound the orchestrator never abandons the goal. A
failed / blocked / stuck attempt is **diagnosed** (`dev-skills:discuss-with-codex`) and **re-attacked**
with a materially-different, AIM-aligned strategy — escalating the approach when the same obstacle
recurs, never idling on difficulty, never drifting to an easier goal. The GitHub **issue is the
persistent unit-of-work identity**; each task is one **attempt** at it. Terminal states are
**goal-met** or **`stop_at`** — nothing else. After `stop_at`, the run enters a drain-only monitor:
no new starts, but observable in-flight workers and landed PRs are processed before shutdown.

The per-tick algorithm itself lives in **`references/orchestrator-loop.md`**; each Loop A tick **reads
it and works it as a `TodoWrite`** (see *The pass*).

## When to use / not use

- **Use** to run autonomous execution once `specify-aims` + `create-cycle` produced
  `docs/task-loop/proposal.md` + `task-loop.md`, and `setup` registered the repo.
- **Do not use** to author docs or to run a single task by hand.

## Prerequisites

**Run `setup` first** — its preflight verifies everything this skill needs (Agent Teams enabled, the
required plugin skills loadable this session, the `task-loop` CLI working, `gh` authenticated). Then
confirm the scaffolding is present: `docs/task-loop/{proposal.md, task-loop.md, directions.md}`.
*Recommended:* branch protection requiring CI + an independent review check, with the orchestrator the
only identity allowed to merge.

## Control plane — Loop A, Loop B transition, Loop C drain monitor

`run-cycle` initially sets up two scheduled jobs, both named with a fresh **`run_generation`** so a
stale job can never touch a newer run. Loop C is created later by the stop transition, not at startup:

- **Loop A** — a **fixed-interval** loop (default 15 min) whose prompt tells each tick to **read
  `references/orchestrator-loop.md` and complete its pass as a `TodoWrite`**. `stop_at` and
  `run_generation` are **embedded in the prompt**, so each tick sees them with zero stored state. Named
  `task-loop-<project>-<gen>-A`. After `stop_at`, Loop A must run drain-only and must not cancel the
  generation before the Loop B/Loop C transition exists.
- **Loop B** — a **one-time** job at `stop_at` that is the stop transition. It validates its generation
  by schedule names (if a newer `task-loop-<project>-<newer-gen>-*` exists, it no-ops/cancels itself),
  then creates or ensures **Loop C**. It may run/wake one drain tick, but it never dispatches new work,
  never materializes re-attacks, and never force-stops live work. Named `...-<gen>-B`.
- **Loop C** — a **recurring drain monitor** (default ~30 min) created by Loop B and named
  `...-<gen>-C`. Each tick runs the drain subset only: steering, liveness, PR merge/classification,
  and proposal reconciliation. It skips materialize re-attacks and dispatch.

**Stopping after `stop_at` is Loop C's decision:** `stop_at` means "stop starting new work," not
"abandon work already launched." Loop C cancels the generation's `-A`/`-B`/`-C` schedules and stops
only when no positively live in-session worker or monitored detached job remains for open/working tasks
in this generation and no PR-present `working` task still needs merge/classification; before canceling,
it runs the final closed-teammate cleanup audit from the reference. Opaque `working`-no-PR rows without
positive live ownership follow the reset rule in the reference and never block Loop C forever. To
change the bound, re-invoke `/run-cycle` — it mints a new generation, best-effort cancels every
`task-loop-<project>-*` job, and recreates Loop A + Loop B. No DB cell, no stored handle, no local file.

## Setup (on invocation)

1. Confirm prerequisites (above). 2. Ask the run duration (default 24h) → compute `stop_at` (UTC); mint
`run_generation` (`date -u +%s`). 3. Best-effort cancel stale `task-loop-<project>-*` jobs. 4. Ensure
the cycle-worker **team** exists for this session. 5. Create Loop A + Loop B only; Loop B's prompt
creates Loop C at `stop_at`. Loop A's prompt carries `stop_at` + `run_generation` and the instruction
to **read `references/orchestrator-loop.md` and work it as a `TodoWrite` each tick**. Loop A then runs
unattended.

## The pass (each Loop A tick)

**Read `references/orchestrator-loop.md` and work its pass as a `TodoWrite`** — one todo per step,
completed in order, every tick. Re-read the reference each tick (it is the single source of the
algorithm and may have changed); never rely on a baked-in copy. In one line the pass is:

> read state + phase-check → honor steering → liveness → merge / classify (read the **Outcome**; never
> merge broken work) → reconcile `proposal.md` → materialize the next work while active (incl.
> **diagnosed re-attacks**, escalating recurring obstacles, AIM-fidelity-checked) → dispatch while
> active → goal-check / drain / terminate.

The reference also holds the reset rule, proposal-reconcile detail, stop model, recovery, and
multi-orchestrator notes.

## Hard invariants

- **Sole merger, sole CLI user, sole `proposal.md` editor.**
- **`task-loop claim` is the only dispatch lock** — no lease, no other guard.
- **Never give up short of the goal** — every non-mergeable attempt is diagnosed and re-attacked with a
  materially-different, escalated, AIM-aligned strategy; the run ends only at **goal-met** or **`stop_at`**.
- **After `stop_at`, no new starts** — Loop B installs Loop C; Loop C drains observable in-flight
  workers/monitored jobs for open/working tasks and PR-present work, runs the final closed-teammate
  cleanup audit, then cancels the generation. It does not dispatch or materialize re-attacks.
- **Reset only with positive "no live owner" knowledge** — in-session observed death, a human
  `task-loop reset <seq>`, or an explicit operator assertion that the prior Agent Teams session is
  terminated and no other orchestrator owns the task. A fresh session alone is not proof. Opaque
  `working`-no-PR rows without positive evidence are surfaced, never blindly reset. `directions.md`
  never triggers reset. Full rule in the reference.
- **Idempotent passes:** proposal updates are reconcile sweeps, never stale patches; task/issue creation
  is idempotent.
- **Branch protection is the structural merge backstop**; a task-loop-specific merge hook is not part
  of this harness.

## Helpers — the `task-loop` CLI (the only DB access)

`task-loop status [--json] | add "<title>" [--dep N…] [--issue N] | claim [--json] |
task-loop set-issue SEQ --issue N [--json] | task-loop set-seq N [--force] [--json] |
task-loop close SEQ | reset SEQ`
— run via `uv run --script ${CLAUDE_PLUGIN_ROOT}/cli/task-loop …`. Use `--json` when the
orchestrator needs durable `seq`/`status`/`title`/`deps`/`issue` state. `set-issue` is
compare-and-set only: it fills a missing task issue without overwriting an existing unit identity.
`set-seq` adjusts the repo-scoped next task sequence and refuses collisions unless `--force` is
explicit. Project (`owner/repo`) auto-detected from the git remote. GitHub (issues / PRs / merge) via
`gh`. Never bypass the CLI to touch the DB.

## Additional resources

- **`references/orchestrator-loop.md`** — the full per-tick algorithm (read + `TodoWrite` each tick),
  reset rule, proposal reconcile, stop model, recovery, and multi-orchestrator notes.
- **`${CLAUDE_PLUGIN_ROOT}/references/pr-findings.md`** — the study-log contract the orchestrator reads.
