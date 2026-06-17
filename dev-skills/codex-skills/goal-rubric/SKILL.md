---
name: goal-rubric
description: Use when the user wants a measurable /goal rubric, success criteria, acceptance criteria, or completion condition, or when a /goal loop will not close because the criteria are not observable or binary.
---

# Goal Rubric

Turn a short goal into a binary rubric that a `/goal` grader can check, then render it as a ready-to-paste completion condition.

## Core Principle

A `/goal` loop closes only when the completion condition is observable and binary. Write criteria the working agent can prove in its own output and a small grader model can judge without running commands or reading files.

## Grader Constraints

- Transcript-only: the grader sees what the agent surfaced in the conversation. It does not run commands or inspect files.
- Small-model judgeable: each criterion must be atomic, concrete, and unambiguous.
- Binary AND: the goal is complete only when every criterion passes.

## Workflow

1. Get the goal from the user.
2. Inspect the repo read-only to identify test, build, lint, file layout, and artifact checks that can prove completion.
3. Draft independent pass/fail criteria. Each criterion must include an end state, a transcript-observable check, and any relevant guardrail.
4. Ask only about gaps that repo inspection cannot settle, such as the validating command, protected files, or turn/time cap.
5. Save the rubric to `./goal-rubric-slug.md`, replacing `slug` with a short goal-derived filename segment unless the user gives another path.
6. Render the `/goal` condition for Codex by default. If the user asks for another tool, use that tool's framing.

## Rubric Shape

```markdown
# Goal rubric: short goal statement

## Criteria (all must pass)
1. Criterion name - End state: observable signal. Check: how it is proven in the transcript. Constraint: what must not change.

## Stop clause
Turn or time cap.

## /goal condition (Codex)
Codex condition string.
```

## Codex Condition Framing

For Codex, phrase the condition with four parts:

- What to achieve.
- What not to change.
- How to validate it.
- When to stop.

Keep the condition direct enough for a small grader to answer yes or no from the transcript.

## Self-Check

Before finishing, verify:

- Every criterion names a measurable end state.
- Every criterion states the check that proves it.
- Every proof can appear in the agent transcript.
- No criterion requires the grader to run a command or open a file.
- Criteria do not overlap.
- The rubric has a stop clause.
