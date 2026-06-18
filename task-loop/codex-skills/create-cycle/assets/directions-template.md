# Task-loop — steering / directions

**This file is the human steering channel for the task-loop.** Write free-form
direction here at any time. Every planning round reads this file first and
treats it as the highest-priority input after task-loop invariants.

Use it for:

- **Priorities / next task** — what to work on next.
- **Constraints / no-go** — what not to touch, budgets, conventions to follow.
- **Course corrections** — reactions to finished PRs or results.
- **Answers to escalations** — decisions for human-only blockers.

Conventions:

- Newest direction at the top; keep it short and imperative.
- Date each note.
- Strike through, delete, or move a note once the loop has acted on it, so this
  file reflects current standing direction.
- A note here overrides defaults but not the Specific Aims or correctness
  contracts. If a direction conflicts with those, pressure-test the conflict
  with `dev-skills:pressure-test` before acting.

---

## Standing Direction

<newest first; e.g. "2026-06-18 - Build Stage 1 first; defer Stage 3 until benchmark data lands.">

## Log Of Past Directions

> _(move dated notes here once handled, for traceability)_
