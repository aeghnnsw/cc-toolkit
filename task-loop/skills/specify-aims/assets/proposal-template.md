---
plan_revision: 1
status: active
---

# <Project Name> — Proposal

## Charter (stable — human-gated)

> The north star. Changes to this zone are a stop-condition-class decision; the
> task-loop never edits the Charter autonomously.

### Aim
<One paragraph: what this project is trying to achieve, and why it matters.>

### Success criteria (what "done" looks like)
- <Binary / checkable where possible — e.g. "benchmark X reproduces value Y within tolerance Z".>
- <...>

### Constraints
- <Budget, compute, data access, required tech/engines, environment, no-go areas.>

### Non-goals
- <Explicitly out of scope, to stop scope creep.>

## Roadmap (living — orchestrator-authored)

> Dependency-ordered stages and their hypotheses. The orchestrator updates this
> zone via dedicated, codex-reviewed PRs as work validates or rejects hypotheses.
> Each `plan_revision` bump is materialized here before dependent tasks dispatch.

### Stage 1 — <name>
- **Goal:** <what this stage delivers>
- **Depends on:** <prior stages / hypotheses, or "none">
- **Rough acceptance:** <how we will know it is done>
- **Hypotheses:**
  - `H1.1` (open): <a falsifiable assumption this stage rests on>

### Stage 2 — <name>
- **Goal:** <...>
- **Depends on:** Stage 1
- **Rough acceptance:** <...>
- **Hypotheses:**
  - `H2.1` (open): <...>

<add stages as needed — keep them rough; the loop refines them>

## Hypothesis ledger

> The **canonical roll-up** of every `Hx.y` declared inline under the stages above. Every
> inline hypothesis must appear here; this table is authoritative for status. The orchestrator
> updates `Status` as findings land.

| ID | Statement | Status | Evidence / disposition |
|------|-----------|--------|------------------------|
| H1.1 | <falsifiable assumption> | open | |
| H2.1 | <falsifiable assumption> | open | |

<status ∈ {open, validated, rejected}>
