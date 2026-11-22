---
name: goal-rubric
version: 1.1.0
description: Draft a binary (pass/fail) rubric and a ready-to-paste completion condition for a Claude Code, Codex, or Antigravity /goal command. Use when the user wants to write or design a rubric, success criteria, acceptance criteria, or a "done"/completion condition for /goal, or when a /goal loop will not close because its criteria are not measurable.
---

# Goal Rubric

Turn a short goal into a binary (pass/fail) rubric that a `/goal` loop can check, then render it as a ready-to-paste completion condition.

## Core Principle

A `/goal` loop closes correctly only when the completion condition is observable and binary. Write criteria that the working agent can prove in its own output. A criterion that needs an opinion, such as "the code is clean", is not binary.

## How Each Tool Checks Completion

- Claude Code and Codex: a separate small, fast grader model decides whether the goal is complete. It reads only what the agent surfaced in the transcript. It does not run commands or inspect files.
- Antigravity: `/goal` has no grader model. When the agent tries to stop, a goal stop hook prompts it again. The agent makes its own deliverables checklist from the condition and decides itself when the goal is complete. Antigravity sets no turn limit, so the condition must say when to stop. A conversation has one goal, so put all criteria in one condition.

## Criterion Rules

The rubric is a set of independent pass/fail criteria joined by AND: the goal is complete only when every criterion passes. Each criterion has these parts:

- End state: one measurable, observable signal, such as a test result, an exit code, a file count, or an empty queue.
- Check: how the agent's output proves the end state, such as "`pytest test/auth` printed `0 failed`".
- Constraint: what must not change on the way, such as "no file outside `src/auth/` changes". Add it when one applies.

Each criterion must also be:

- Transcript-observable: the agent shows the proof in its output, such as a command and its printed result. The user can then check each claim from the conversation, and so can a grader.
- Atomic: it checks one concrete, unambiguous end state, so the answer is yes or no.
- Independent: it does not overlap another criterion or count the same thing twice.

The rubric also has one stop clause: a turn or time cap, such as "or stop after 20 turns".

## Workflow

1. Get the goal from the user.
2. Inspect the repo read-only. Find the test, build, and lint commands, the file layout, and the artifacts that can prove completion. Do not change a file.
3. Draft the criteria and the stop clause. Apply every criterion rule above.
4. Ask the user only about gaps that repo inspection cannot settle, such as the command that proves the change works, the files that must not change, or the turn or time cap. Do not ask about what the repo answers.
5. Save the rubric to `./goal-rubric-<slug>.md` in the working directory, unless the user gives another path. Replace `<slug>` with a short name from the goal.
6. Render the `/goal` condition for the tool that the user names, or for Claude Code when the user names none. Use the framing for that tool in [Condition Framing](#condition-framing).

## Rubric Shape

```markdown
# Goal rubric: <short goal statement>

## Criteria (all must pass)
1. <name> - End state: <observable signal>. Check: <how the transcript proves it>. Constraint: <what must not change, if any>.
2. ...

## Stop clause
<turn or time cap>

## /goal condition (<tool>)
<the condition, framed for the tool>
```

## Condition Framing

- Claude Code: one condition string. Keep it within the `/goal` length limit, around 4,000 characters. Phrase it so that the proof appears in the transcript, for example: `all tests in test/auth pass (pytest prints 0 failed) and git status is clean, without modifying any file outside src/auth/, or stop after 20 turns`.
- Codex and Antigravity: a condition in four parts:
  1. What to achieve: the criteria, each named so that it is one item of a checklist.
  2. What not to change: the constraints.
  3. How to validate it: the command or artifact that proves each criterion, and the output that the agent must show for it.
  4. When to stop: every criterion passes with its proof shown, or the turn or time cap is reached, or a blocker needs the user.

For Codex, keep the condition direct enough for a small grader to answer yes or no from the transcript. For Antigravity, the agent checks its own work and makes its deliverables checklist from the criteria. So tell it to show the proof of each criterion in its output before it stops, and to report each criterion that does not pass.

## Self-Check

Before finishing, verify:

- Every criterion names a measurable end state and the check that proves it.
- Every criterion is pass/fail: no scores, no "mostly".
- No criterion depends on an opinion.
- Every proof would appear in the agent's output.
- For Claude Code and Codex, no criterion needs the grader to run a command or open a file.
- Criteria do not overlap.
- The rubric has a stop clause.
