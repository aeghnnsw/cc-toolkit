---
name: create-cycle
description: This skill should be used when the user asks to "create cycle", "create the task loop", "generate the task-loop instructions", "write the per-task playbook", "scaffold task-loop", or to turn a task-loop proposal into the project-specific cycle a worker follows. It renders docs/task-loop/task-loop.md from a generic skeleton plus this project's specifics (auto-detected and interviewed), and scaffolds docs/task-loop/directions.md, the logs directory, .gitignore, and the loop:in-progress label.
version: 0.1.0
---

# Create Cycle

## Overview

Second step of the task-loop workflow (`specify-aims` → **`create-cycle`** → `run-cycle`).
It generates the **project-specific per-task playbook** `docs/task-loop/task-loop.md` — the
file each worker reads to run one task end to end — by filling a generic cycle skeleton with
this project's specifics, and it scaffolds the supporting files. Run it once the proposal
(`docs/task-loop/proposal.md`) exists.

The generic cycle (recover → rubric → spec/plan → TDD → verify → reconcile → doc-update →
open-PR → request-merge → record) is fixed across projects and lives in
`assets/task-loop-skeleton.md`. This skill's job is to (a) discover/ask the project specifics
and (b) render them into the skeleton, then scaffold the rest.

## When to use / not use

- **Use** to (re)generate `docs/task-loop/task-loop.md` and scaffold a project for the loop,
  after `specify-aims` has produced the proposal.
- **Do not use** to run tasks — that is `run-cycle` (orchestrator) plus the `cycle-worker`
  agent. This skill only authors the instructions and scaffolding.

## Outputs

- `docs/task-loop/task-loop.md` — the rendered per-task playbook (from
  `assets/task-loop-skeleton.md`).
- `docs/task-loop/directions.md` — the human steering file (from
  `assets/directions-template.md`).
- `docs/task-loop/logs/` — the iteration-indexed record directory (with a `.gitkeep`). Each cycle
  writes **one git-tracked record** `<NNN>_<task>.md` with a **Rubric** section (binary acceptance)
  and a **Decision log** section (decisions + evidence), where `<NNN>` is a zero-padded iteration
  index from `001` (orchestrator-assigned; see the skeleton's operating principle 8).
- `.gitignore` entry for `goal-rubric-*.md` scratch (the loop keeps **no** local runtime state — all
  of it lives in the GitHub control issue).
- The `loop:in-progress` GitHub label (`gh label create loop:in-progress`).

## Process

### 1. Read the proposal
Read `docs/task-loop/proposal.md`. The Charter's Aim + Success criteria become the
**north star**; the Roadmap stages + hypotheses inform what tasks will look like. If the
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
- The **north star** phrasing → `{{NORTH_STAR}}` (from the Charter).

### 4. Render the playbook
Copy `assets/task-loop-skeleton.md` to `docs/task-loop/task-loop.md` and replace **every**
occurrence of each `{{PLACEHOLDER}}` (some appear twice — e.g. `{{CONTRACTS}}` and
`{{TEST_CONVENTIONS}}` recur in the operating principles). For an absent fill — e.g. no
bootstrap needed when a code skeleton already exists — write `n/a` or remove that bullet;
never leave a raw `{{...}}`. Leave the generic cycle steps and operating principles intact —
they are deliberately project-agnostic. Do **not** weaken the worker's control-protocol
obligations (post `MERGE_REQUEST`/`PLAN_FINDING` inbox events; never merge; never edit the
proposal).

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

- **Generic skeleton, project specifics.** Never edit the cycle *steps* per project — only
  fill the `{{...}}` placeholders. The discipline (TDD, evidence-before-done, codex
  deliberation, worker-never-merges) is constant; the contracts/tests/docs are local.
- **Detect before asking.** Pull the test command and git-hook constraints from the repo;
  reserve questions for genuinely project-specific intent.
- **Preserve the control-protocol contract.** The rendered playbook must keep the worker
  posting inbox events and deferring all merges/proposal edits to the orchestrator.

## Additional resources

- **`assets/task-loop-skeleton.md`** — the generic per-task cycle to render.
- **`assets/directions-template.md`** — the steering-file scaffold.
- Design rationale: `docs/superpowers/specs/2026-06-13-task-loop-plugin-design.md` (§5–§6)
  and the control-protocol section (§8). The worker helpers it references are
  `task-loop/scripts/control_log.py` and `gh_store.py`.
