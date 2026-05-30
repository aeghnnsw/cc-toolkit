---
name: goal-rubric
description: Draft a binary (pass/fail) rubric and a ready-to-paste completion condition for a Claude Code or Codex /goal command. Use when the user wants to write or design a rubric, success criteria, acceptance criteria, or a "done"/completion condition for /goal, or when a /goal loop will not close because its criteria are not measurable.
---

# Goal Rubric

Turn a one-line goal into a **binary rubric** a `/goal` grader can check against, then render it into a ready-to-paste `/goal` condition.

A `/goal` loop runs an agent turn-by-turn; after each turn a separate small/fast grader model decides whether to stop. The loop only closes when the completion condition is genuinely checkable. This skill produces a rubric that is.

## How the grader works (why these rules exist)

The grader is not the agent doing the work. It is constrained:

- **Transcript-only.** It reads only what the agent surfaced in the conversation. It does NOT run commands or read files itself. → every criterion must be provable from the agent's own output.
- **Small/fast model** (Haiku-class by default), returning yes/no plus a short reason. → every criterion must be atomic and unambiguous.

Write criteria the agent can *demonstrate in its output* and a small model can *judge at a glance*.

## What a good rubric contains

The rubric is a set of independent **pass/fail** criteria joined by AND — the goal is done only when every criterion passes. Each criterion has:

- **End state** — one measurable, observable signal (a test result, a build/exit code, a file count, an empty queue).
- **Check** — how that end state is proven *in the agent's output* (e.g. "`pytest test/auth` printed `0 failed`").
- **Constraint** — what must not change on the way there (e.g. "no file outside `src/auth/` is modified"), when relevant.

Plus one overall **stop clause** — a turn or time cap (e.g. "or stop after 20 turns").

Apply these rules to every criterion:

1. Names a measurable end state.
2. States the check that proves it.
3. Captures any guardrail/constraint that must hold.
4. The rubric has a stop/budget clause.
5. Criteria are independent — no two overlap or double-count.
6. Every criterion is binary; "done" = all pass.

Overlay: each criterion must be **transcript-observable** (provable from the agent's surfaced output) and **small-model-judgeable** (atomic, unambiguous).
