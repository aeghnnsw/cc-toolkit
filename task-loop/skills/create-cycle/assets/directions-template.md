# Task-loop — steering / directions

**This file is the human steering channel for the task-loop.** Write free-form direction
here at any time. Every planning round of `run-cycle` reads this file **first** and treats it
as the **highest-priority input**, above the loop's own task-selection heuristic.

How to use it:

- **Priorities / next task** — say what to work on next ("do Stage 2 before anything else",
  "pause new stages, harden tests first").
- **Constraints / no-go** — what not to touch, budgets, conventions to follow.
- **Course corrections** — react to a finished PR or a result.
- **Answers to escalations** — when the loop pauses for a human-only blocker, put the
  decision here.

Conventions:

- Newest direction at the top; keep it short and imperative.
- Date each note. Strike through or delete a note once the loop has acted on it, so the file
  reflects only *current* standing direction.
- A note here overrides the loop's defaults but **not** the Specific Aims or the correctness
  contracts — if a direction conflicts with those, the loop flags it (via
  `discuss-with-codex`) rather than silently breaking them.

---

## Standing direction

<newest first; e.g. "2026-06-13 — Build Stage 1 first; defer Stage 3 until the benchmark data lands.">

## Log of past directions (acted on)

> _(move dated notes here once handled, for traceability)_
