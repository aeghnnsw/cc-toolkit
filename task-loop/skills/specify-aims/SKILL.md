---
name: specify-aims
description: This skill should be used when the user asks to "specify aims", "initialize the proposal", "set up the task-loop proposal", "define the project aims and stages", "plan the project stages and milestones", or "start a task-loop project" — i.e. to author the living proposal that drives a task-loop autonomous development project. It produces docs/task-loop/proposal.md with three parts — specific aims & goal, an implementation plan (stages + milestones), and a living roadmap (progress) — brainstorming the aims with the user and pressure-testing the goal and stage decomposition with discuss-with-codex.
version: 0.1.0
---

# Specify Aims

## Overview

This is the **first step** of the task-loop workflow (`specify-aims` → `create-cycle` →
`run-cycle`). It produces the project's **living spine**, `docs/task-loop/proposal.md` — a single
durable doc in **three parts**: the **Specific Aims & Goal**, the **Implementation Plan** (stages +
milestones), and the **Living Roadmap** (progress), each defined under Output below. The proposal
need not be perfect; it must state the goal clearly and decompose the work into rough,
dependency-ordered stages, which the task-loop then refines as work validates or rejects hypotheses.

This is the one task-loop step that is **collaborative with the user** — later steps run
autonomously. Brainstorm the aims with the user, and pressure-test the goal and the stage
decomposition with `dev-skills:discuss-with-codex`.

## When to use / not use

- **Use** to author a new proposal, or to re-aim one **before the loop has started** (no control
  issue yet).
- **Do not use** once the project has a **control issue** (i.e. `run-cycle` has started). From that
  point the control log holds the authoritative plan revision and **only the orchestrator** edits
  `proposal.md` (via `run-cycle`); re-aiming is then a loop-reset / plan-revision decision, not a
  `specify-aims` edit.

## Output: `docs/task-loop/proposal.md`

Three parts with different change bars (scaffold in `assets/proposal-template.md`):

- **Specific Aims & Goal (stable, human-gated):** Aim, Success criteria, Constraints, Non-goals.
  The autonomous loop never edits this; changing it later is a stop-condition-class decision
  escalated to the user.
- **Implementation Plan (proposed, orchestrator-revised):** dependency-ordered Stages — each with a
  goal, declared dependencies, rough acceptance, and the **hypotheses** it rests on — plus coarse
  **milestones**. The orchestrator revises this (bumping `plan_revision`) when a finding changes the
  plan.
- **Living Roadmap (progress, orchestrator-authored):** the running status — current stage,
  milestones reached, and a **hypothesis ledger** tracking each hypothesis as `open` / `validated` /
  `rejected`. Updated as work lands.

Frontmatter starts at `plan_revision: 1`; `run-cycle` owns later plan-revision bumps and the
plan/roadmap edits — the Specific Aims stay human-gated.

## Process

### 1. Explore the project
Read the repo: existing docs, README, prior art, and the user's stated direction. Note what
exists and what "done" might plausibly mean.

### 2. Brainstorm the aim with the user
Invoke `superpowers:brainstorming` and draw out, one question at a time:
- the **goal** and *why* it matters;
- what **done** looks like (success criteria — binary / checkable where possible);
- **constraints** (budget, compute, data access, required engines/tech, environment);
- **non-goals** (explicitly out of scope);
- the rough **stages** and their order, and the **milestones** that mark demonstrable progress.

Keep it lightweight — aim for clarity, not completeness.

### 3. Decompose into a dependency-ordered plan
For each stage, capture: goal, what it depends on (prior stages / hypotheses), rough acceptance, and
the **hypotheses** it rests on (falsifiable assumptions). Then mark a few **milestones** — coarse,
demonstrable checkpoints spanning stages. Declaring hypotheses now is what later lets the running
loop scope an invalidation to an affected subgraph instead of freezing everything.

### 4. Pressure-test with Codex
Use `dev-skills:discuss-with-codex` proactively on the aims and the decomposition. Hold a
genuine position and let Codex attack:
- Is the goal **falsifiable** — is "done" actually checkable?
- Are stages ordered by **real dependency**, or is the order arbitrary?
- What is the **riskiest hypothesis**, and is it scheduled early?
- Is anything in the Specific Aims actually an Implementation-Plan item (or vice versa)?

Fold the conclusions into the proposal; record any unresolved tension in the relevant stage.

### 5. Write the proposal
For a new project, create `docs/task-loop/` and copy `assets/proposal-template.md` to
`docs/task-loop/proposal.md` (it ships `plan_revision: 1`); to re-aim a pre-run proposal, edit the
existing file in place rather than overwriting it. Fill in the three parts in current-truth prose
(no "previously…").

### 6. Commit on a branch + PR
The proposal is durable git state. Create a branch, commit `docs/task-loop/proposal.md`, and open a
PR with clean, attribution-free text.

## Additional resources

- **`assets/proposal-template.md`** — the three-part proposal scaffold to copy into the
  project.
- Design rationale: `docs/superpowers/specs/2026-06-13-task-loop-plugin-design.md` (§4) and
  `docs/superpowers/specs/2026-06-13-living-proposal-ownership-conclusion.md`.
