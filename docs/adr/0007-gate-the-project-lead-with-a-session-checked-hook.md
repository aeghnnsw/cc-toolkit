# Gate the project lead with a session-checked plugin hook

> **Superseded in part (2026-11-22, issue #530).** The step script now also
> keeps the lead state, so it no longer only prints. In a recorded session,
> the hook allows only the step script's commands and reads of T3
> attachments (superseded in part by #531; read
> [GTD agent captures](#gtd-agent-captures)): the lead may no longer read,
> list, or remove its lead folder.
> Read [Lead state commands](#lead-state-commands) and
> [ADR 0008](0008-keep-project-lead-state-in-a-cli.md).
>
> **Superseded in part (2026-11-22, issue #531).** In a recorded session, the
> hook also passes the calls of a gtd-inbox capture: reads of the GTD binding
> and of the installed Productivity Skills plugin, the `gtd_sql.py` renderer,
> and whole-file writes of GTD JSON files outside every Git work tree. Read
> [GTD agent captures](#gtd-agent-captures).
>
> **Superseded in part (2026-11-24, issue #574).** A `start` run in a command
> list also records a session, as in `S=<script>; python3 $S start 2>&1 |
> head -80`. Read [Start in a command list](#start-in-a-command-list).
>
> **Superseded in part (2026-11-26, issues #612 and #621).** Only `init`,
> `takeover`, and a `start` of the thread that owns the lead state record a
> session, and `unmark` removes a wrong record. In a recorded session, the
> lead may also read the tool outputs that Claude Code saved for the session,
> and its gtd-inbox files. Read [Lead threads only](#lead-threads-only).

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
of the plugin. (Superseded by #612: only `init`, `takeover`, and a `start` of
the owner thread record a session; read [Lead threads only](#lead-threads-only).)
In a recorded session, it blocks shell commands, file reads,
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
the lead folder. (Superseded in part: the hook also passes the calls of a
gtd-inbox capture; read [GTD agent captures](#gtd-agent-captures).)
(Superseded in part by #621: it also allows reads of the saved tool outputs
of the session and of gtd-inbox files; read
[Lead threads only](#lead-threads-only).) A direct edit would go around the life cycle that the script
enforces. The lead needs no direct read, because `start`, `show`, and
`waiting` print the state. It also no longer needs to list or remove the
folder: the script finds it, and `finish` deletes it. As before, only a
three-word `python3 "<script>" start` records a session. (Superseded: that
command also records a session in a command list; read
[Start in a command list](#start-in-a-command-list).) (Superseded by #612:
`start` records only the owner thread, and `init` and `takeover` also
record; read [Lead threads only](#lead-threads-only).)

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
  plugin: a folder with `scripts/gtd_sql.py` and `references/gtd-cloud.md`
  outside every Git work tree.
- `uv run --no-project [uv options] python <plugin>/scripts/gtd_sql.py
  [arguments...]` as one simple command. Only `--python <version>`,
  `--no-cache`, `--offline`, `-q`, and `--quiet` can also come before
  `python`. Without `--no-project`, uv creates an environment in a project
  folder, and a `--python` value other than a version can name any program.
- A whole-file write with the file edit tool of a `.json` file at an absolute
  path outside every Git work tree. Its content is a GTD binding or a GTD
  request, and the file is new or holds one already. A write in the folder of
  the GTD binding stays blocked, because only gtd-setup changes the binding. A
  relative path, `~`, or a `..` that a host can resolve in another way also
  stays blocked.

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

## Start in a command list

Added on 2026-11-24 for
[#574](https://github.com/aeghnnsw/cc-toolkit/issues/574).

After a change of provider, a lead had a new session ID and ran `start` only
in command lists, such as `S=<script>; python3 $S start 2>&1 | head -80`.
The hook recorded nothing, and the gate was off for 36 minutes.

So the hook also reads a call in a session without a record as a command
list: simple commands joined by `;`, `&&`, `||`, `|`, `|&`, `&`, or a new
line. It drops redirects, their targets, and comments. It records the
session when one simple command is exactly `python3 "<script>" start` and
the script passes the same check as before: the hook's own copy, or a copy
outside every Git work tree. (Superseded in part by #612: such a `start`
records only the owner thread, and `init` and `takeover` also record; read
[Lead threads only](#lead-threads-only).) A command of only variable assignments, also
after `export`, sets them for the later commands, as in bash. An assignment
in a pipeline, one that runs with `&`, or one before a command word does
not.

A record must name a qualifying script, so the hook records nothing when it
cannot resolve the path. It reads no list with a subshell, a group, a
command or process substitution, a here-document, a reserved word such as
`if` or `while`, or a builtin that changes variables or runs other code,
such as `unset`, `declare`, `eval`, or `source`. It reads no command after
`exit` or `exec`. A word with a glob or an unset variable cannot match, and
after `cd`, `pushd`, `popd`, or an unknown command word a relative path
cannot match. A wider match would gate a session that is not
a lead, and the gate blocks the `rm` of its record. A record only turns the
gate on. The gate does not change: in a recorded session it allows one
simple command, so it blocks the same command list from the next call, and
only the three-word `start` refreshes the record.

## Lead threads only

Added on 2026-11-26 for
[#612](https://github.com/aeghnnsw/cc-toolkit/issues/612) and
[#621](https://github.com/aeghnnsw/cc-toolkit/issues/621).

A worker thread ran `start` when the skill's command reached it. The hook
recorded the worker's session and blocked its work
([#612](https://github.com/aeghnnsw/cc-toolkit/issues/612)). The user chose
to keep `start` open to every thread and to change what records a session.

Now `init <slug>`, with an optional `--also`, and `takeover` record a
session in any thread: each makes a lead. A `start` records a session only
when `T3CODE_THREAD_ID` in the hook's environment is the owner of the lead
state in the Git working tree of the call's cwd. A working tree without a
lead state records nothing, so a worker in its own worktree is never
recorded. The command forms of
[Start in a command list](#start-in-a-command-list) still apply.

The check fails closed. When a lead state may be there and the hook cannot
tell its owner, `start` records the session: without `T3CODE_THREAD_ID` or
an absolute cwd, or with a lead state that the hook cannot read or that has
no owner. On 2026-11-26, the Claude Code process that T3 Code started had
`T3CODE_THREAD_ID` in its environment, which its hooks inherit. The Codex
app-server daemons had none, so a Codex hook may lack it. Then a `start` in
the lead's working tree records the session of any thread.

`t3_project_lead.py unmark` removes a wrong record. In a recorded session,
the hook removes the record before the script runs, only when it can tell
that the thread is not the lead: the hook has `T3CODE_THREAD_ID`, the
worktrees of the repository of the session's cwd hold a lead state, and
another thread owns each one. Otherwise it blocks the call with the reason
and keeps the record. The record covers the whole session, so a call whose
Codex `workdir` or Antigravity `Cwd` names another folder also keeps it. A
repository without a lead state, as after `finish`, keeps the record too: a
finished lead thread is still a lead thread, and only the user settles it.
The script makes the same check and changes no lead state. The reminder on
each user message names `unmark` for a thread that is not the lead.

In a recorded session, the read rule also allows the tool outputs that
Claude Code saved for the session, and gtd-inbox files
([#621](https://github.com/aeghnnsw/cc-toolkit/issues/621)). Claude Code
saves an output over its inline limit in `<folder>/<session>/tool-results/`,
next to the transcript `<folder>/<session>.jsonl` that the payload names,
and shows a preview, so a lead could not read a long `show` output. A
payload without such a transcript path, as from Codex and Antigravity,
allows no saved output. A gtd-inbox file is a `.json` file outside every Git
work tree whose content is a GTD binding or request, by the content check
of the write rule.
