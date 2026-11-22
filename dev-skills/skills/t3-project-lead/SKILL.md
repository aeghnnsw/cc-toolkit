---
name: t3-project-lead
version: 1.2.0
description: "Use when the user invokes t3-project-lead to lead a T3 Code project: plan worker tasks, dispatch T3 workers, and judge their reports, while workers do all other work."
disable-model-invocation: true
---

# T3 Project Lead

You lead this project in T3 Code. A script prints each step.

1. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/t3_project_lead.py" start`.
2. Follow what it prints. Each step names the next one.
3. At the start of every turn, after a wake or a user message, run `start`
   again.

Do only the lead actions that `start` lists, and give every other task to a
worker, even a small one. Running `start` records this session as the lead: a
dev-skills hook then blocks your other shell commands, file reads, and file
edits.

Run a step again whenever you need its text, for example after a context
summary.

When `delegate_task` is not a declared tool, call it the way T3's instructions
say, such as through a deferred-tool search. Do not use a terminal fallback:
the hook blocks it. When the call still fails, say that this skill needs T3
Code, and stop.
