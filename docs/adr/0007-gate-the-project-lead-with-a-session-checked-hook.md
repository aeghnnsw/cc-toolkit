# Gate the project lead with a session-checked plugin hook

> **Superseded in part (2026-11-22, issue #530).** The step script now also
> keeps the lead state, so it no longer only prints. In a recorded session,
> the hook allows only the step script's commands and reads of T3
> attachments: the lead may no longer read, list, or remove its lead folder.
> Read [Lead state commands](#lead-state-commands) and
> [ADR 0008](0008-keep-project-lead-state-in-a-cli.md).
>
> **Extended (2026-11-22, issue #531).** In a recorded session, the hook also
> passes the calls of a gtd-inbox capture. Read
> [GTD agent captures](#gtd-agent-captures).

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

The lead may still read its lead folder and T3 attachments, which hold the
files that the user sends. It may list the names in `.scratch`, to find its
lead folder after a restart, and remove its lead folder when the project
ends. (Superseded: the lead may still read T3 attachments, but it may not
read, list, or remove its lead folder; read
[Lead state commands](#lead-state-commands).) It may not call T3 tools
through a terminal command.

The record is a file named by the session ID, in a per-user state folder
outside every repository and settings file. The hook writes it, so the step
script still only prints, and the record holds the same ID that the hook
compares later. (Superseded in part: the step script now also keeps the lead
state; read [Lead state commands](#lead-state-commands).) The ID stays the
same after T3 restarts a session, so the hook works at once after a restart.

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

## Lead state commands

Added on 2026-11-22 for
[#530](https://github.com/aeghnnsw/cc-toolkit/issues/530).

The step script now keeps the lead state in the lead's working tree, as
[ADR 0008](0008-keep-project-lead-state-in-a-cli.md) records. The lead had
kept `lead.md` by hand, and in one batch those edits took 47 of 77 lead
calls. Now the project lead changes its state only through the script's
commands.

So in a recorded session, the hook allows only
`python3 "<script>" <subcommand> [arguments...]` as one simple command, and
reads of T3 attachments. It blocks every other shell command, every other
file read, and every file edit, so it also blocks reads, edits, and `rm` of
the lead folder. A direct edit would go around the life cycle that the script
enforces. The lead needs no direct read, because `start`, `show`, and
`waiting` print the state. It also no longer needs to list or remove the
folder: the script finds it, and `finish` deletes it. As before, only a
three-word `python3 "<script>" start` records a session.

The hook still writes the session record. The record stays in the per-user
state folder, which a sandboxed shell command cannot write, and it holds the
same ID that the hook compares later.

## GTD agent captures

Added on 2026-11-22 for
[#531](https://github.com/aeghnnsw/cc-toolkit/issues/531).

A project lead keeps agent captures of what waits on the user when the user's
instructions ask for them. Its workers are child tasks, so they add none. But
the hook blocked five calls of a gtd-inbox capture: the reads of the installed
gtd-inbox files and of the GTD binding, the writes of the private binding copy
and the request file, and the `gtd_sql.py` renderer. Only the Supabase MCP call
passed.

So in a recorded session, the hook also passes exactly these calls:

- A read of the GTD binding, or of a file in an installed Productivity Skills
  copy: a folder with `scripts/gtd_sql.py` and `references/gtd-cloud.md`
  outside every Git work tree, as an installed plugin is.
- `uv run [uv options] python <copy>/scripts/gtd_sql.py [arguments...]` as one
  simple command. Only `--no-project`, `--python`, `--no-cache`, `--offline`,
  `-q`, and `--quiet` can come before `python`.
- A whole-file write with the file edit tool of a `.json` file outside every
  Git work tree. Its content is a GTD binding or a GTD request, and the file is
  new or holds one already. A write of the GTD binding itself stays blocked.

The renderer reads files only to validate them and writes none, so it gives
the lead no other read or write. The lead follows gtd-inbox as written, and
GTD, gtd-inbox, and the renderer do not change. The lead state stays
independent of GTD. Where the hook cannot decide, such as for a path that it
cannot resolve or a Git check that fails, it blocks the call.

Rejected alternatives:

- **Shell writes of the private files.** Agents wrote them with `cp`, a
  heredoc, or `python3 -c`, which the hook cannot check as one simple command.
- **The renderer writes the private files.** The hook would need no write
  exemption, but the GTD procedure would change for every user and host.
- **No private files.** The renderer could take the request inline and read the
  binding directly, but the GTD contract keeps a binding copy and a saved
  request for an exact replay.

Consequences:

- A lead writes the files where its edit tool needs no prompt, such as the
  Claude Code session scratchpad. A write in the lead's worktree stays blocked.
- In a sandboxed Codex shell, uv cannot lock its default folder, so
  `--no-cache` passes.
- The same calls also serve the other GTD skills. Only the step text limits the
  lead to agent captures.
