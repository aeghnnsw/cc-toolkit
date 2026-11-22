---
name: t3-project-lead
description: "Use when the user invokes t3-project-lead to lead a T3 Code project: plan worker tasks, dispatch T3 workers, and verify their results, while workers implement."
disable-model-invocation: true
---

# T3 Project Lead

You lead this project in T3 Code. A script prints each step.

1. Run `python3 "<plugin-root>/scripts/t3_project_lead.py" start`.
   `<plugin-root>` is two levels above this folder.
2. Follow what it prints. Each step names the next one.
3. At the start of every turn, after a wake or a user message, run `start`
   again.

Run a step again whenever you need its text, for example after a context
summary.

When `delegate_task` is not a declared tool, call it the way T3's instructions
say, such as through a deferred-tool search or a terminal fallback. When that
also fails, say that this skill needs T3 Code, and stop.
