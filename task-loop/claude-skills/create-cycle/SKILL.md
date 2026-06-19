---
name: create-cycle
description: This skill should be used when the user asks to "create cycle", "create the task loop", "generate the task-loop instructions", "write the per-task playbook", "scaffold task-loop", or to turn a task-loop proposal into the per-project cycle a worker follows. It renders docs/task-loop/task-loop.md — this project's tailored step-by-step worker cycle, its general rules, and its parameters (the cycle-worker agent follows this file) — from auto-detected and interviewed specifics, and scaffolds docs/task-loop/directions.md and a .gitignore entry.
version: 0.2.1
---

# Create Cycle

## Overview

Second step of the task-loop workflow (`specify-aims` → **`create-cycle`** → `run-cycle`).
It generates `docs/task-loop/task-loop.md` — the **per-project cycle a worker follows**: the
step-by-step procedure (anchor → set up worktree → rubric → spec/plan → TDD → verify → reconcile →
doc-update → open PR with the study log → report), the general rules, and this project's parameters —
by rendering `assets/task-loop-skeleton.md`, then scaffolds `directions.md`. The `cycle-worker` agent
contract holds the same general rules + invariants; the worker reads and **follows this file
strictly**. Run it once the proposal (`docs/task-loop/proposal.md`) exists.

The cycle template (`assets/task-loop-skeleton.md`) is the **single source** of the procedure in the
plugin; this skill renders it per project. Because the rendered `task-loop.md` is a snapshot,
**re-run `create-cycle` after upgrading the task-loop plugin** so the cycle stays current.

## When to use / not use

- **Use** to (re)generate `docs/task-loop/task-loop.md` and scaffold a project, after `specify-aims`
  has produced the proposal — and to **refresh** it after a plugin upgrade.
- **Do not use** to run tasks — that is `run-cycle` (orchestrator) plus the `cycle-worker` agent.
  This skill only authors the cycle and scaffolding.

## Outputs

- `docs/task-loop/task-loop.md` — the rendered **per-project cycle + general rules + parameters**
  (from `assets/task-loop-skeleton.md`).
- `docs/task-loop/directions.md` — the human steering file (from `assets/directions-template.md`).
- `docs/task-loop/logs/` — the record directory (with a `.gitkeep`). Each cycle writes **one**
  git-tracked study-log record `<NNN>_<task>.md` (`<NNN>` = the task `seq`, zero-padded) with
  **Outcome**, **Rubric**, **Evidence**, and **Findings**, committed in the worker's PR.
- A `.gitignore` entry for `goal-rubric-*.md` scratch.

(There is **no** local runtime state and **no** control issue — all task state lives in the Supabase
DB, reached only by the `task-loop` CLI from the orchestrator.)

## Process

### 1. Read the proposal
Read `docs/task-loop/proposal.md`. The Specific Aims (Aim + Success criteria) define the **goal**; the
Implementation Plan's stages inform what tasks look like. If the proposal is missing, stop and direct
the user to `specify-aims` first.

### 2. Auto-detect what the repo tells you (don't ask)
- **Test command** (`pytest`, `npm test`, `cargo test`, …).
- **Default branch** (`git symbolic-ref --short refs/remotes/origin/HEAD` or the repo's main branch)
  → `{{DEFAULT_BRANCH}}`.
- **Git hooks** that constrain workflow — branch-name prefixes, attribution/word bans, protected
  default branch, staging restrictions (check `.git/hooks/` and any core-hooks plugin) →
  `{{BRANCH_PREFIXES}}` and the commit/PR steps.
- Whether a **code skeleton exists** yet or the repo is docs-only → `{{BOOTSTRAP_NOTE}}`.
- The **compute environment** — HPC scheduler (`sinfo`/`squeue`), GPUs (`nvidia-smi`), core count
  (`nproc`) — to inform `{{COMPUTE_POLICY}}` (it does not by itself authorize cluster submission).

### 3. Interview for the project specifics (finalize fuzzy ones with Codex)
Ask only for what can't be detected, one topic at a time; pressure-test ambiguous answers with
`dev-skills:discuss-with-codex`:
- **Source-of-truth docs** the worker reads every task → `{{SOURCE_DOCS}}`.
- **Correctness contracts** — invariants that are preconditions, not polish → `{{CONTRACTS}}`.
- **What "tested" means** here beyond smoke tests (analytic limits, golden values, conservation
  checks, integration gates) → `{{TEST_CONVENTIONS}}`.
- A **bootstrap note** if the repo has no code yet → `{{BOOTSTRAP_NOTE}}`.
- The **compute policy** → `{{COMPUTE_POLICY}}`. **Never leave it raw or invent it ad hoc.** Default
  (use unless the user states a constraint): *"Use all available **local** compute — every CPU core
  and available GPU; parallelize independent work; never run a parallelizable job single-threaded;
  background long jobs and verify their terminal state. Do **not** submit to a cluster/SLURM scheduler
  unless this policy names an allowed account/partition — then submit heavy jobs to compute nodes
  (`sbatch`/`srun`), never the shared login node. Note: several cycle-workers may share this host, so
  this aggressive default can oversubscribe; if you routinely run several at once, set a per-worker cap
  (e.g. `cores ÷ workers`) here."* Only pressure-test with `discuss-with-codex` for shared-cluster
  quota/etiquette constraints.
- The project **goal** phrasing → `{{GOAL}}` (from the Specific Aims).

### 4. Render the cycle file
Copy `assets/task-loop-skeleton.md` to `docs/task-loop/task-loop.md` and replace each `{{PLACEHOLDER}}`
in the **Project parameters** list with this project's value. For an absent fill — e.g. no bootstrap
needed when a code skeleton exists — write `n/a` or remove that bullet; never leave a raw `{{...}}`.
**Leave the cycle steps, the general rules, and the worktree bash verbatim** — they are the fixed
procedure; only the parameters are project-specific, and the steps reference them by name. Do **not**
edit, reorder, or weaken the steps when rendering — copying the template faithfully is what keeps the
cycle correct.

### 5. Scaffold the rest
- Copy `assets/directions-template.md` to `docs/task-loop/directions.md`.
- Create `docs/task-loop/logs/.gitkeep`.
- Add a `.gitignore` entry for `goal-rubric-*.md` scratch. The loop keeps **no** local runtime files.

### 6. Commit on a branch + PR
Commit the scaffolding with clean, attribution-free text via a branch + PR (`git commit -F`,
`gh pr create --body-file`). These are durable project files.

## Key principles

- **Cycle + general rules + parameters here; the same rules also in the agent.** This skill renders
  the per-project cycle and fills the `{{...}}` parameters. The general discipline (TDD,
  evidence-before-done, codex deliberation, worker-never-merges) and the non-negotiable invariants are
  **repeated in both** the rendered `task-loop.md` and the `cycle-worker` agent contract on
  purpose — they are load-bearing, and the worker turns `task-loop.md`'s steps + rules into its todo
  list.
- **Detect before asking.** Pull the test command, default branch, and git-hook constraints from the
  repo; reserve questions for genuinely project-specific intent.
- **Render faithfully, don't author.** Fill placeholders only; never edit the cycle steps. Re-running
  `create-cycle` after a plugin upgrade is how a project's cycle stays current (the rendered file is a
  snapshot).

## Additional resources

- **`assets/task-loop-skeleton.md`** — the per-project cycle + general rules + parameters template.
- **`assets/directions-template.md`** — the steering-file scaffold.
- **`${CLAUDE_PLUGIN_ROOT}/references/pr-findings.md`** — the PR study-log contract the cycle's
  step 8 writes and the orchestrator reads.
