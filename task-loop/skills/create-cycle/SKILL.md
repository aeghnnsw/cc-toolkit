---
name: create-cycle
description: This skill should be used when the user asks to "create cycle", "create the task loop", "generate the task-loop instructions", "write the per-task playbook", "scaffold task-loop", or to turn a task-loop proposal into the per-project cycle a worker follows. It renders docs/task-loop/task-loop.md — this project's tailored step-by-step worker cycle plus its parameters (the cycle-worker agent holds only the general principles and invariants and follows this file) — from auto-detected and interviewed specifics, and scaffolds docs/task-loop/directions.md, the logs directory, .gitignore, and the loop:in-progress label.
version: 0.1.0
---

# Create Cycle

## Overview

Second step of the task-loop workflow (`specify-aims` → **`create-cycle`** → `run-cycle`).
It generates `docs/task-loop/task-loop.md` — the **per-project cycle a worker follows**: the full
step-by-step procedure (recover → confirm → worktree → rubric → spec/plan → TDD → verify →
reconcile → doc-update → open-PR → request-merge → record) with this project's parameters
interpolated into the steps — by rendering `assets/task-loop-skeleton.md`, then scaffolds the
supporting files. The `cycle-worker` agent contract holds only the **general operating principles
and non-negotiable invariants**; it reads and **follows this file strictly**. Run it once the
proposal (`docs/task-loop/proposal.md`) exists.

The cycle template (`assets/task-loop-skeleton.md`) is the **single source** of the step-by-step
procedure in the plugin; this skill renders it per project with the project's specifics. Because the
rendered `task-loop.md` is a snapshot, **re-run `create-cycle` after upgrading the task-loop plugin**
so the project's cycle stays current with the template.

## When to use / not use

- **Use** to (re)generate `docs/task-loop/task-loop.md` and scaffold a project for the loop,
  after `specify-aims` has produced the proposal — and to **refresh** it after a plugin upgrade.
- **Do not use** to run tasks — that is `run-cycle` (orchestrator) plus the `cycle-worker`
  agent. This skill only authors the cycle and scaffolding.

## Outputs

- `docs/task-loop/task-loop.md` — the rendered **per-project cycle + parameters** (from
  `assets/task-loop-skeleton.md`).
- `docs/task-loop/directions.md` — the human steering file (from
  `assets/directions-template.md`).
- `docs/task-loop/logs/` — the iteration-indexed record directory (with a `.gitkeep`). Each cycle
  writes **one git-tracked record** `<NNN>_<task>.md` with a **Rubric** section (binary acceptance)
  and a **Decision log** section (decisions + evidence), where `<NNN>` is a zero-padded iteration
  index from `001` (orchestrator-assigned; see the `cycle-worker` agent contract's operating principle 8).
- `.gitignore` entry for `goal-rubric-*.md` scratch (the loop keeps **no** local runtime state — all
  of it lives in the GitHub control issue).
- The `loop:in-progress` GitHub label (`gh label create loop:in-progress`).

## Process

### 1. Read the proposal
Read `docs/task-loop/proposal.md`. The Specific Aims (Aim + Success criteria) define the project
**goal**; the Implementation Plan's stages + hypotheses inform what tasks will look like. If the
proposal is missing, stop and direct the user to `specify-aims` first.

### 2. Auto-detect what the repo already tells you
Discover, without asking:
- **Test command** (e.g. `pytest`, `python -m unittest discover`, `npm test`, `cargo test`).
- **Lint/format** config, if any.
- **Git hooks** that constrain workflow — branch-name prefixes, attribution/word bans,
  protected `master`, staging restrictions. Check `.git/hooks/` and any `core-hooks`-style
  plugin. These become the `{{BRANCH_PREFIXES}}` and inform the commit/PR steps.
- Whether a **code skeleton exists** yet (package layout, build config) or the repo is
  docs-only (drives the `{{BOOTSTRAP_NOTE}}`).
- The **compute environment** — whether an HPC scheduler (`sinfo`/`squeue`) or GPUs
  (`nvidia-smi`) are present, and the local core count (`nproc`). This **informs** the default
  `{{COMPUTE_POLICY}}` wording (it does **not** by itself authorize cluster submission — that
  stays gated on a named account/partition, below).

### 3. Interview for the project specifics (finalize fuzzy ones with Codex)
Ask the user only for what cannot be detected, one topic at a time, and pressure-test
ambiguous answers with `dev-skills:discuss-with-codex`:
- **Source-of-truth docs** the worker must read every task (the proposal plus any spec /
  design / data docs) → `{{SOURCE_DOCS}}`.
- **Correctness contracts** — invariants that are preconditions, not polish →
  `{{CONTRACTS}}`.
- **What "tested" means** here beyond smoke tests (analytic limits, golden values,
  conservation checks, integration gates) → `{{TEST_CONVENTIONS}}`.
- A **bootstrap note** if the repo has no code yet (what the earliest scaffolding tasks are)
  → `{{BOOTSTRAP_NOTE}}`.
- The **compute policy** — how aggressively a worker should use this machine, and any account
  /partition for cluster submission → `{{COMPUTE_POLICY}}`. **Never leave it raw or invent it
  ad hoc.** Default (use unless the user states a constraint): *"Use all available **local**
  compute — every CPU core and available GPU; parallelize independent work; never run a
  parallelizable job single-threaded; background long jobs and verify their terminal state. Do
  **not** submit to a cluster/SLURM scheduler unless this policy names an allowed account
  /partition — then submit heavy jobs to compute nodes (`sbatch`/`srun`), never the shared login
  node. Note: up to 5 cycle-workers may share this host, so this aggressive default can
  oversubscribe; if you routinely run several workers at once, set a per-worker cap (e.g.
  `cores ÷ workers`) here."* Only pressure-test with `discuss-with-codex` when the project has
  shared-cluster quota/etiquette constraints (then name the account/partition and any per-worker
  cap).
- The project **goal** phrasing → `{{GOAL}}` (from the Specific Aims).

### 4. Render the cycle file
Copy `assets/task-loop-skeleton.md` to `docs/task-loop/task-loop.md` and replace each
`{{PLACEHOLDER}}` in the **Project parameters** list with this project's value. For an absent
fill — e.g. no bootstrap needed when a code skeleton already exists — write `n/a` or remove that
bullet; never leave a raw `{{...}}`. **Leave the step-by-step cycle itself verbatim** — it is the
fixed procedure; only the parameters are project-specific, and the steps reference them by name. Do
**not** edit, reorder, or weaken the cycle steps, the worktree bash, or the recovery/control-event
shapes when rendering — copying the template faithfully is what keeps the protocol correct.

### 5. Scaffold the rest
- Copy `assets/directions-template.md` to `docs/task-loop/directions.md`.
- Create `docs/task-loop/logs/.gitkeep`.
- Add a `.gitignore` entry for any `goal-rubric-*.md` scratch. The loop keeps **no** local runtime
  files (no lease file, no orchestrator state) — the lease/heartbeat, `stop_at`, and schedule
  handles all live in the GitHub control-issue body; the event log lives in its comments.
- Create the label: `gh label create loop:in-progress` (ignore "already exists").

### 6. Commit on a branch + PR
Commit the scaffolding with clean, attribution-free text via a branch + PR (`git commit -F`,
`gh pr create --body-file`). These are durable project files.

## Key principles

- **Cycle + parameters here; principles + invariants in the agent.** This skill renders the
  per-project cycle and fills the `{{...}}` parameters. The general discipline (TDD,
  evidence-before-done, codex deliberation, worker-never-merges) and the non-negotiable invariants
  live in the `cycle-worker` agent contract; the contracts/tests/compute/docs are the local values
  you fill into the cycle.
- **Detect before asking.** Pull the test command and git-hook constraints from the repo;
  reserve questions for genuinely project-specific intent.
- **Render faithfully, don't author.** Fill placeholders only; never edit the cycle steps or
  control-protocol shapes. The template is the single source of the procedure — re-running
  `create-cycle` after a plugin upgrade is how a project's cycle stays current (it is the drift
  mitigation, since the rendered file is a snapshot).

## Additional resources

- **`assets/task-loop-skeleton.md`** — the per-project cycle + parameters template to render.
- **`assets/directions-template.md`** — the steering-file scaffold.
- Design rationale: `docs/superpowers/specs/2026-06-13-task-loop-plugin-design.md` (§5–§6)
  and the control-protocol section (§8). The worker helpers it references are
  `task-loop/scripts/control_log.py` and `gh_store.py`.
