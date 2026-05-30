---
name: goal-rubric
description: Draft a binary (pass/fail) rubric and a ready-to-paste completion condition for a Claude Code or Codex /goal command. Use when the user wants to write or design a rubric, success criteria, acceptance criteria, or a "done"/completion condition for /goal, or when a /goal loop will not close because its criteria are not measurable.
---

# Goal Rubric

Turn a one-line goal into a **binary rubric** a `/goal` grader can check against, then render it into a ready-to-paste `/goal` condition.

A `/goal` loop runs an agent turn-by-turn; after each turn a separate small/fast grader model decides whether to stop. The loop only closes when the completion condition is genuinely checkable. This skill produces a rubric that is.
