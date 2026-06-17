---
incorporated_through: 0   # seq of the last merged task reflected here (orchestrator-maintained; 0 = none yet)
---

# <Project Name> — Proposal

## Specific Aims & Goal — *stable, human-gated*

> The goal and the definition of done. The task-loop never edits this zone autonomously; changing it
> is a stop-condition-class decision escalated to you.

### Aim
<One paragraph: what this project achieves, and why it matters.>

### Success criteria (definition of done)
- <Binary / checkable where possible — e.g. "benchmark X reproduces value Y within tolerance Z".>
- <...>

### Constraints
- <Budget, compute, data access, required tech/engines, environment, no-go areas.>

### Non-goals
- <Explicitly out of scope, to stop scope creep.>

## Implementation Plan — *proposed, orchestrator-revised*

> The dependency-ordered stages and milestones planned to reach the Aim — kept rough on purpose. The
> orchestrator reconciles this each loop from merged findings when the plan changes. Each stage
> declares the falsifiable **hypotheses** it rests on — the units the loop validates, and the edges it
> reasons about when scoping an invalidation.

### Stages (dependency-ordered)

**Stage 1 — <name>**
- **Goal:** <what this stage delivers>
- **Depends on:** <prior stages / hypotheses, or "none">
- **Acceptance:** <how we will know it is done>
- **Hypotheses:** `H1.1` — <a falsifiable assumption this stage rests on>

**Stage 2 — <name>**
- **Goal:** <...>
- **Depends on:** Stage 1
- **Acceptance:** <...>
- **Hypotheses:** `H2.1` — <...>

<add stages as needed — keep them rough; the loop refines them>

### Milestones
> Coarse, demonstrable checkpoints spanning stages.
- **M1 — <name>:** <what it proves, e.g. "Stages 1–2: end-to-end run on toy input">
- **M2 — <name>:** <...>

## Living Roadmap — *progress, orchestrator-authored*

> The running status, updated as work lands. The orchestrator owns this zone during a run; it records
> progress — it is not the plan itself.

### Progress
- **Current stage:** <Stage N — short status, or "not started">
- **Milestones reached:** <M1 …, or "none yet">

### Hypothesis ledger
> Tracks the status of every `Hx.y` declared in the Implementation Plan, by ID. Statements live with
> their stage above; do not restate them here.

| ID   | Status | Evidence / disposition |
|------|--------|------------------------|
| H1.1 | open   |                        |
| H2.1 | open   |                        |

<status ∈ {open, validated, rejected}>
