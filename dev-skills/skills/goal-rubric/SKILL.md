---
name: goal-rubric
version: 1.0.0
description: Draft a binary (pass/fail) rubric and a ready-to-paste completion condition for a Claude Code or Codex /goal command. Use when the user wants to write or design a rubric, success criteria, acceptance criteria, or a "done"/completion condition for /goal, or when a /goal loop will not close because its criteria are not measurable.
---

# Goal Rubric

Turn a one-line goal into a **binary rubric** a `/goal` grader can check against, then render it into a ready-to-paste `/goal` condition.

A `/goal` loop runs an agent turn-by-turn; after each turn a separate small/fast grader model decides whether to stop. The loop only closes when the completion condition is genuinely checkable. This skill produces a rubric that is checkable.

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

Apply these rules. Rules 1–3 and 6 are per-criterion; rules 4–5 are about the rubric as a whole:

1. Names a measurable end state.
2. States the check that proves it.
3. Captures any guardrail or constraint that must hold (when one applies).
4. The rubric has a stop clause.
5. Criteria are independent — no two overlap or double-count.
6. Every criterion is binary; "done" = all pass.

Overlay: each criterion must be **transcript-observable** (provable from the agent's surfaced output) and **small-model-judgeable** (atomic, unambiguous).

## Workflow

1. **Take the goal.** Get the one-line goal from the user.
2. **Inspect the repo (read-only).** Look at test config, build/lint commands, and file layout to infer the measurable end states and the exact commands/artifacts that prove them. Do not modify anything.
3. **Draft the binary rubric.** Write the independent criteria (end state + check + constraint each) and the stop clause, applying every rule above.
4. **Ask only about gaps.** Ask the user targeted questions ONLY for what inspection could not settle — e.g. "which command proves the feature works?", "any files that must not change?", "what turn or time cap?". Never re-ask what the repo already answered. Keep it to the minimum.
5. **Finalize.** Save the rubric file and render the `/goal` condition.

## Output

Save the rubric to `./goal-rubric-<slug>.md` in the working directory (let the user override the path). Use this structure:

```
# Goal rubric: <goal one-liner>

## Criteria (all must pass)
1. <name> — End state: <observable signal>. Check: <how it is proven in the transcript>. Constraint (if any): <what must not change>.
2. ...

## Stop clause
<turn or time cap>

## /goal condition (<tool>)
<the rendered condition — one string for Claude, or the four-part framing for Codex — in a fenced block>
```

Then render the condition for the target tool (ask which if unclear; default **Claude**):

- **Claude `/goal`** — a single condition string (keep it within the `/goal` length limit — around 4,000 chars) phrased so the proof appears in the transcript, e.g. `all tests in test/auth pass (pytest prints 0 failed) and git status is clean, without modifying any file outside src/auth/, or stop after 20 turns`.
- **Codex `/goal`** — frame it as: what to achieve / what not to change / how to validate / when to stop.

## Before you finish — self-check

- [ ] Every criterion names a measurable end state and the check that proves it.
- [ ] Every criterion is pass/fail (no scores, no "mostly").
- [ ] Every criterion's proof would actually appear in the agent's output.
- [ ] No criterion needs the grader to run a command or open a file.
- [ ] Criteria do not overlap.
- [ ] There is a stop clause.
