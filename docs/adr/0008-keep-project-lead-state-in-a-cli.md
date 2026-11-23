# Keep the lead state in the step script

> **Superseded in part (2026-11-22, issue #531).** In a recorded session, the
> hook also passes the calls of a gtd-inbox capture. Read
> [GTD agent captures](0007-gate-the-project-lead-with-a-session-checked-hook.md#gtd-agent-captures)
> in ADR 0007.
>
> **Superseded in part (2026-11-23, issue #543).** repo-cleanup keeps each
> worktree that holds a lead state by a rule of its own, in every mode, and a
> test checks the rule. Read
> [Cleanup of a lead worktree](#cleanup-of-a-lead-worktree).
>
> **Superseded in part (2026-11-23, issue #544).** `start` also changes the
> lead state once after a takeover: it removes the takeover mark and appends
> one event. Read
> [`start` after a takeover](0009-bind-the-lead-state-to-its-t3-thread.md#start-after-a-takeover)
> in ADR 0009.

A project lead kept its state in `lead.md`, which it changed by hand with
Read, Edit, and Write. The `plan` step said that the file "holds current
state, not history". That rule existed only as text, and under load the lead
broke it: in one lead run, `lead.md` grew to 193 lines with per-PR detail,
answered items, and old decisions. The
[retrospective of the fifth batch](https://github.com/aeghnnsw/cc-toolkit/pull/521#issuecomment-7082983484)
counted 47 of 77 lead calls only to keep `lead.md` current, and found that
the lead's clock times were guesses, 6 to 27 minutes ahead of UTC. The file
was in `.scratch/` of the main checkout, which a sandboxed lead in a T3
worktree cannot write, so about 45 of those calls ran with the sandbox off
([#511](https://github.com/aeghnnsw/cc-toolkit/issues/511)).

`t3_project_lead.py` now owns the lead state
([#530](https://github.com/aeghnnsw/cc-toolkit/issues/530)). Its nine steps
still print text, and new commands change the state: `init`, `outcome`,
`criteria`, `task`, `wait`, `done`, `decision`, `show`, `waiting`, and
`finish`. (Superseded in part by #544: `start` also changes the state once
after a takeover; read
[`start` after a takeover](0009-bind-the-lead-state-to-its-t3-thread.md#start-after-a-takeover)
in ADR 0009.) The project lead changes its state only through these commands.
This supersedes the rule of ADR 0007 that the step script only prints.

The script keeps the life cycle of each task and refuses every transition
that the life cycle does not allow. For example, it refuses to mark a task
with an open pull request verified, to start a task before each task that it
waits for (`--after`) is verified, and to settle a task of a batch with a
merged pull request before the batch's close-out task is verified. It stamps
each change with the real UTC time, refuses text over 200 characters, and
prints a short view. `start` prints the step text, the UTC time, the view,
the due lines, and the list of what waits on the user, so that the lead
copies that list and does not write it from memory. `finish` deletes the lead
state only when each task is in the `settled` state and nothing waits on the
user.

The lead state is in `<top of the lead's working tree>/.scratch/<YYYYMMDD>-lead-<slug>/`,
with a `.gitignore` of `*`, `state.json`, `events.jsonl` (the history), and a
lock file. The script runs as a shell command, inside the host's sandbox, and
each host lets a sandboxed command write a different set of folders:

- Claude Code: the working directory, `$TMPDIR` (a different path inside and
  outside the sandbox), and the Git common folder of a linked worktree.
- Codex (`workspace-write`): the working directory except `.git`, `.agents`,
  and `.codex`; `/tmp`; and `$TMPDIR`. The Git common folder is read-only.
- Antigravity (Default and Auto): project folders, temporary folders, and
  build caches.

So the lead's own working tree is the only folder that every host lets the
script write and that lasts as long as the lead. The Claude Code and Codex
rules were read from the
[Claude Code sandbox documentation](https://code.claude.com/docs/en/sandboxing)
and the Codex source
([`permissions.rs`](https://github.com/openai/codex/blob/main/codex-rs/protocol/src/permissions.rs)).
The Antigravity rule comes from the
[Antigravity sandbox documentation](https://antigravity.google/docs/sandbox.md)
only; it was not tested.

In a recorded session, the hook of ADR 0007 now allows only
`python3 "<script>" <subcommand> [arguments...]` as one simple command, and
reads of T3 attachments, also through one simple read command such as `cat`.
It blocks every other shell command, every other file read, and every file
edit, so it also blocks reads, edits, and `rm` of the lead folder.
(Superseded in part by #531: the hook also passes the calls of a gtd-inbox
capture.) So the
lead state changes only through the script. Only a three-word
`python3 "<script>" start` records a session.

The lead state is independent of GTD: the script reads and writes no GTD
data. Some users of the skill use GTD and some do not, and the lead state
must not rely on, change, or conflict with their GTD inbox.

Rejected alternatives:

- **Text rules only.** The rule that `lead.md` holds current state was
  already text, and the lead broke it under load. Text also cannot give the
  lead the real time.
- **A `lead.md` view that the script writes.** A second copy of the state can
  differ from the state, and the lead can still edit it by hand. `start` and
  `show` print the view instead.
- **The Git common folder**, as #511 proposed. Claude Code lets a sandboxed
  command write it, but it is read-only in a sandboxed Codex session.
- **A per-user state folder**, such as `~/.local/state`, where the hook keeps
  its session records. A hook runs outside the sandbox, but the script runs
  inside it, and no host's sandbox lets a shell command write there without
  a per-host allowlist.
- **GTD for the lead state.** The user wants the lead state independent of
  GTD, because not every user of the skill uses GTD.
- **A second script for the state.** It keeps the rule that the step script
  only prints, but the hook must then allow a second command form, and each
  turn needs one more call, because `start` cannot print the state.
- **A hook that reads worker reports to find what waits on the user.**
  Reports are free text, so a parser can miss a wait or find one that is not
  there. The lead reads each report anyway, and records a wait with one
  command.

Consequences:

- A working tree holds one lead state: `init` refuses a second. Two leads
  need two working trees.
- The lead state is lost when the lead's worktree is removed before `finish`.
  repo-cleanup keeps a worktree with a live session, and keeps a branch that
  no merged PR has as its head, so it keeps a lead worktree. This comes from
  the repo-cleanup text; it was not tested. (Superseded: repo-cleanup keeps
  each worktree that holds a lead state, in every mode; read
  [Cleanup of a lead worktree](#cleanup-of-a-lead-worktree).)
- The script cannot see T3 threads. The lead still records each wait itself
  with `wait`, and ends it with `done`.
- No command imports `lead.md`. A live lead enters its open state once, with
  the state commands, after the plugin update.
- The close-out brief names the history file, so the retrospective reads real
  times. `finish` deletes the history with the lead folder.
- GTD agent captures from a lead session wait for
  [#531](https://github.com/aeghnnsw/cc-toolkit/issues/531): the hook blocks
  the commands that a capture needs. (Superseded: the hook now passes the
  calls of a gtd-inbox capture, and the script still reads and writes no GTD
  data; read
  [GTD agent captures](0007-gate-the-project-lead-with-a-session-checked-hook.md#gtd-agent-captures)
  in ADR 0007.)

## Cleanup of a lead worktree

Added on 2026-11-23 for
[#543](https://github.com/aeghnnsw/cc-toolkit/issues/543).

`cleanup_plan.py`, the plan that repo-cleanup acts on, keeps each worktree
that holds `.scratch/<YYYYMMDD>-lead-<slug>/state.json` at its top, in every
mode, including `--main-only`. The reason is "holds a lead state". When the
plan cannot read that `.scratch` or a lead folder, it keeps the worktree,
because it cannot tell whether the worktree holds a lead state.
`dev-skills/tests/test_cleanup_plan.py` checks the rule.

A lead edits no tracked file, so Git reports its worktree as clean. Before,
two other rules kept a lead worktree that no session had used in the last 60
minutes: no merged PR had its branch tip as its head, and its date-named
folder had no issue key. #528 would mark such a branch as merged, and
`--main-only` does not read the planning folders of a worktree. Then cleanup
could remove the worktree and the lead state with it.
