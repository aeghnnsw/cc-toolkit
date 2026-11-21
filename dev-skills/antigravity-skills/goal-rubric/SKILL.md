---
name: goal-rubric
description: Use when the user wants a measurable /goal rubric, success criteria, acceptance criteria, or completion condition for an Antigravity, Claude Code, or Codex /goal command, or when a /goal loop will not close because the criteria are not observable or binary.
---

# Goal Rubric

Turn a short goal into a binary rubric that a `/goal` loop can check, then render it as a ready-to-paste completion condition.

## Core Principle

A `/goal` loop closes correctly only when the completion condition is observable and binary. Write criteria that the working agent can prove in its own output. A criterion that needs an opinion, such as "the code is clean", is not binary.

## How Each Tool Checks Completion

- Antigravity: `/goal` has no grader model. When the agent tries to stop, a goal stop hook prompts it again. The agent makes its own deliverables checklist from the condition and decides itself when the goal is complete. Antigravity sets no turn limit, so the condition must say when to stop. A conversation has one goal, so put all criteria in one condition.
- Claude Code and Codex: a separate small grader model decides. It reads only what the agent surfaced in the transcript. It does not run commands or inspect files.

## Criterion Rules

- Transcript-observable: the agent shows the proof of each criterion in its output, such as a command and its printed result. The user can then check each claim from the conversation, and so can a grader.
- Atomic: each criterion checks one concrete, unambiguous end state, so the answer is yes or no.
- Binary AND: the goal is complete only when every criterion passes.

## Workflow

1. Get the goal from the user.
2. Inspect the repo read-only to identify test, build, lint, file layout, and artifact checks that can prove completion.
3. Draft independent pass/fail criteria. Each criterion must include an end state, a transcript-observable check, and any relevant guardrail.
4. Ask only about gaps that repo inspection cannot settle, such as the validating command, protected files, or turn/time cap.
5. Save the rubric to `./goal-rubric-slug.md`, replacing `slug` with a short goal-derived filename segment unless the user gives another path.
6. Render the `/goal` condition for Antigravity by default. If the user asks for another tool, use that tool's framing.

## Rubric Shape

```markdown
# Goal rubric: short goal statement

## Criteria (all must pass)
1. Criterion name - End state: observable signal. Check: how it is proven in the transcript. Constraint: what must not change.

## Stop clause
Turn or time cap.

## /goal condition (Antigravity)
Antigravity condition in four parts.
```

## Antigravity Condition Framing

For Antigravity, phrase the condition with four parts:

- What to achieve: the criteria, each named so that it becomes one item of the agent's deliverables checklist.
- What not to change.
- How to validate it: the command or artifact that proves each criterion, and the output that the agent must show for it.
- When to stop: every criterion passes with its proof shown, or the turn or time cap is reached, or a blocker needs the user.

The agent checks its own work. So tell it to show the proof of each criterion in its output before it stops, and to report each criterion that does not pass.

## Other Tools

- Claude Code `/goal`: a single condition string (keep it within the `/goal` length limit, around 4,000 characters) phrased so the proof appears in the transcript, e.g. `all tests in test/auth pass (pytest prints 0 failed) and git status is clean, without modifying any file outside src/auth/, or stop after 20 turns`.
- Codex `/goal`: the same four parts. Keep the condition direct enough for a small grader to answer yes or no from the transcript.

## Self-Check

Before finishing, verify:

- Every criterion names a measurable end state.
- Every criterion states the check that proves it.
- Every proof can appear in the agent transcript.
- No criterion depends on an opinion of the agent.
- For Claude Code and Codex, no criterion requires the grader to run a command or open a file.
- Criteria do not overlap.
- The rubric has a stop clause.
