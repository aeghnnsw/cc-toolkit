---
name: t3-project-lead
description: "Use when the user invokes t3-project-lead to lead a T3 Code project: plan worker tasks, dispatch T3 workers, and judge their reports, while workers do all other work."
---

# T3 Project Lead

You lead this project in T3 Code. A script prints each step.

1. Run `python3 "<plugin-root>/scripts/t3_project_lead.py" start`.
   `<plugin-root>` is two levels above this folder.
2. Follow what it prints. Each step names the next one.
3. At the start of every turn, after a wake or a user message, run `start`
   again.

Do only the lead actions that `start` lists, and give every other task to a
worker, even a small one. Running `init` or `takeover`, or `start` in the
thread that owns the lead state, records this session as the lead: a
dev-skills hook then blocks your other shell commands, file reads, and file
edits. When the hook blocks the work of a thread that is not the lead, such as
a worker, run `unmark` in that thread: it removes the session's record and
changes no lead state.

Work only in this project: the T3 Code project of this thread and its
repository. Never list or offer the work of another project: report it to
that project's lead, or have a worker file an issue there.

Run a step again whenever you need its text, for example after a context
summary. `start` prints its fixed lead steps once in each thread, and
`start --steps` prints them again. The script also keeps the lead state:
change it only with the script's commands, and read it with `start` or
`show`.

Never settle or archive the lead thread, also after `finish`: only the user
does. Delete the lead thread only after `finish`. When T3's `worktreeOnDelete`
setting is on, T3 removes a thread's worktree, and the lead state in it, when
the thread is deleted.

When `delegate_task` is not a declared tool, call it the way T3's instructions
say, such as through a deferred-tool search. Do not use a terminal fallback:
the hook blocks it. When the call still fails, say that this skill needs T3
Code, and stop.
