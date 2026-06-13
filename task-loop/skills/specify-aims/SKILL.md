---
name: specify-aims
description: This skill should be used when the user asks to "specify aims", "initialize the proposal", "set up the task-loop proposal", "define the project goal and stages", "start a task-loop project", or "write the charter" — i.e. to create the living proposal/implementation doc that drives a task-loop autonomous development project. It produces docs/task-loop/proposal.md (a Charter + Roadmap), brainstorming the aims with the user and pressure-testing the goal and stage decomposition with discuss-with-codex.
version: 0.1.0
---

# Specify Aims

## Overview

This is the **first step** of the task-loop workflow (`specify-aims` → `create-cycle` →
`run-cycle`). It produces the **living research spine** for a project:
`docs/task-loop/proposal.md`, a single durable doc with two zones — a **Charter** (stable
aims / success criteria / constraints / non-goals) and a **Roadmap** (living stages + a
hypothesis ledger). The proposal does not need to be perfect; it must state the goal
clearly and decompose the work into rough, dependency-ordered stages. The task-loop refines
the Roadmap as work validates or rejects hypotheses.

This is the one task-loop step that is **collaborative with the user** — later steps run
autonomously. Brainstorm the aims with the user, and pressure-test the goal and the stage
decomposition with `dev-skills:discuss-with-codex`.

## When to use / not use

- **Use** to initialize (or substantially re-aim) a task-loop project's proposal.
- **Do not use** to edit a Roadmap during an active run. Once the loop is running, **only
  the orchestrator** edits `proposal.md` (via `run-cycle`), because the proposal is the
  durable narrative — not the live coordination primitive. This skill owns only the initial
  authoring.

## Output: `docs/task-loop/proposal.md`

Two zones with different change bars (scaffold in `assets/proposal-template.md`):

- **Charter (stable, human-gated):** Aim, Success criteria, Constraints, Non-goals. This is
  the north star; the autonomous loop never edits it. Changing it later is a
  stop-condition-class decision escalated to the user.
- **Roadmap (living, orchestrator-authored):** dependency-ordered Stages — each with a goal,
  declared dependencies, rough acceptance, and **hypotheses** — plus a **hypothesis ledger**
  (`open` / `validated` / `rejected`). The orchestrator updates this zone as the project
  progresses.

Frontmatter carries `plan_revision: 1` — the materialized revision counter the control
protocol keys on.

## Process

### 1. Explore the project
Read the repo: existing docs, README, prior art, and the user's stated direction. Note what
exists and what "done" might plausibly mean.

### 2. Brainstorm the aim with the user
Invoke `superpowers:brainstorming` and draw out, one question at a time:
- the **north-star goal** and *why* it matters;
- what **done** looks like (success criteria — binary / checkable where possible);
- **constraints** (budget, compute, data access, required engines/tech, environment);
- **non-goals** (explicitly out of scope);
- the rough **stages/phases** and their order.

Keep it lightweight — aim for clarity, not completeness.

### 3. Decompose into dependency-ordered stages
For each stage, capture: goal, what it depends on (prior stages / hypotheses), rough
acceptance, and the **hypotheses** it rests on (falsifiable assumptions). Declaring
hypotheses now is what later lets the running loop scope an invalidation to an affected
subgraph instead of freezing everything.

### 4. Pressure-test with Codex
Use `dev-skills:discuss-with-codex` proactively on the aims and the decomposition. Hold a
genuine position and let Codex attack:
- Is the goal **falsifiable** — is "done" actually checkable?
- Are stages ordered by **real dependency**, or is the order arbitrary?
- What is the **riskiest hypothesis**, and is it scheduled early?
- Is anything in the Charter actually a Roadmap item (or vice versa)?

Fold the conclusions into the proposal; record any unresolved tension in the relevant stage.

### 5. Write the proposal
Copy `assets/proposal-template.md` to `docs/task-loop/proposal.md` and fill it in. Write
current-truth prose only (no "previously…"). Set frontmatter `plan_revision: 1`,
`status: active`.

### 6. Commit on a branch + PR
The proposal is durable git state. Create a branch, commit `docs/task-loop/proposal.md`, and
open a PR with clean, attribution-free text. After this PR, the proposal is owned by the
orchestrator — direct human/agent edits stop here.

## Key principles

- **Clear, not perfect.** A crisp goal plus rough stages beats an exhaustive plan the loop
  will rewrite anyway.
- **Charter is sacred; Roadmap is fluid.** Put stable intent in the Charter and evolving
  plans in the Roadmap; keeping them separate is what stops the goal from drifting every
  time the plan adjusts.
- **Declare hypotheses.** They are the units the loop validates/rejects and the edges it
  reasons about when scoping invalidation.
- **Deliberate, don't hand-wave.** Route every fuzzy aim or decomposition question through
  `discuss-with-codex`.

## Additional resources

- **`assets/proposal-template.md`** — the two-zone proposal scaffold to copy into the
  project.
- Design rationale: `docs/superpowers/specs/2026-06-13-task-loop-plugin-design.md` (§4) and
  `docs/superpowers/specs/2026-06-13-living-proposal-ownership-conclusion.md` (why the
  Charter is not the live coordination primitive, and why only the orchestrator edits the
  proposal once the loop runs).
