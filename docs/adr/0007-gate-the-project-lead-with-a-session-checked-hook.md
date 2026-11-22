# Gate the project lead with a session-checked plugin hook

A project lead must give every task except its own lead actions to a worker
([#520](https://github.com/aeghnnsw/cc-toolkit/issues/520)). Text alone did
not hold this rule. The lead used native research agents (#476), and on
2026-11-22 it ran SSH probes, post-merge checks, and repo-cleanup itself. The
host's own guidance, such as "Do the work yourself when it is a handful of tool
calls", won over the skill text. The Claude Code documentation says that a
rule that must always hold belongs in a hook.

dev-skills now ships one hook for Claude Code, Codex, and Antigravity. It
starts in every session that has dev-skills, but it acts only in a session
that it has recorded as a project lead. It records a session when that
session runs the `start` step of `t3_project_lead.py` from an installed copy
of the plugin. In a recorded session, it blocks shell commands, file reads,
and file edits outside the lead's actions, and native subagent calls. It also
reminds the lead to run `start` on each user message (Claude Code and Codex).
In every other session it exits at once and changes nothing.

The record is a file named by the session ID, in a per-user state folder
outside every repository and settings file. The hook writes it, so the step
script still only prints, and the record holds the same ID that the hook
compares later. The ID stays the same after T3 restarts a session, so the
hook works at once after a restart.

Rejected alternatives:

- **Hooks in the skill's frontmatter.** Claude Code runs these only in the
  session that invoked the skill, which is the exact scope. But a live test
  showed that they stop when the `claude` process ends, for example after a
  resume in a new process, and Codex and Antigravity skills cannot declare
  hooks.
- **Hooks that T3 Code passes to one thread.** Codex can load hooks for one
  session from the configuration that starts its thread, but only the app
  that starts the thread can supply them. T3 Code has no way to add them.
- **Text only, with a retrospective check.** The rule had already failed as
  text twice. The close-out worker still lists the lead's other tool calls,
  as a second check.

ADR 0005 rejected a shipped `Stop` hook partly because it would run in every
session. This hook also runs in every session, but there it only checks for
a record and exits. No session-only mechanism exists today on Codex and
Antigravity.

Consequences:

- Each tool call in each session with dev-skills starts one short process.
- When a lead changes to another provider, the new session has a new ID, and
  the hook does not act until that session runs `start`.
- Where the hook cannot decide in a recorded session, such as a command with a
  pipe or a path that it cannot resolve, it blocks the call: it fails closed.
- Antigravity has no prompt event, so it gets the block but not the reminder.
