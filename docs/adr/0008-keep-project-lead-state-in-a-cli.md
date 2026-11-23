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
>
> **Superseded in part (2026-11-23, issue #545).** The step script has ten
> steps: the `discover` step starts the discovery task of a new lead. Read
> [The discover step](#the-discover-step).
>
> **Superseded in part (2026-11-23, issue #528).** repo-cleanup removes a
> clean branch with no commit of its own after 60 minutes, and in every mode
> reads the planning folders of each worktree that it would remove. Read
> [Cleanup of a branch with no commit of its own](#cleanup-of-a-branch-with-no-commit-of-its-own).
>
> **Superseded in part (2026-11-23, issue #555).** `start` prints a compact
> view; `show` prints the full view. Read
> [The compact start view](#the-compact-start-view).

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
in ADR 0009. Superseded in part by #545: the script has ten steps; read
[The discover step](#the-discover-step).) The project lead changes its state
only through these commands.
This supersedes the rule of ADR 0007 that the step script only prints.

The script keeps the life cycle of each task and refuses every transition
that the life cycle does not allow. For example, it refuses to mark a task
with an open pull request verified, to start a task before each task that it
waits for (`--after`) is verified, and to settle a task of a batch with a
merged pull request before the batch's close-out task is verified. It stamps
each change with the real UTC time, refuses text over 200 characters, and
prints a short view. `start` prints the step text, the UTC time, the view,
the due lines, and the list of what waits on the user, so that the lead
copies that list and does not write it from memory. (Superseded in part by
#555: `start` prints a compact view; read
[The compact start view](#the-compact-start-view).) `finish` deletes the lead
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
  [Cleanup of a lead worktree](#cleanup-of-a-lead-worktree). Superseded in
  part by #528: repo-cleanup removes a clean branch with no commit of its own
  after 60 minutes; read
  [Cleanup of a branch with no commit of its own](#cleanup-of-a-branch-with-no-commit-of-its-own).)
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
could remove the worktree and the lead state with it. (Superseded in part by
#528: `--main-only` now reads the planning folders of each worktree that the
plan would remove; read
[Cleanup of a branch with no commit of its own](#cleanup-of-a-branch-with-no-commit-of-its-own).)

## The discover step

Added on 2026-11-23 for
[#545](https://github.com/aeghnnsw/cc-toolkit/issues/545).

A lead that read the open issues itself was flagged by the model provider's
safeguards, and a flag stops the whole lead thread. With no lead state and no
task named, `start` printed only the `init` line, so no step found open work.

So `start` tells a new lead to run `init` on its first `start`, and then the
tenth step, `discover`. Unless the user named the work, the lead adds the
discovery task and starts a read-only worker with the discovery brief that
`discover` prints. The worker collects the open issues with their labels, the
open PRs, the unsettled threads, and the worktrees or branches with
uncommitted or unpushed changes, and lists all of them in groups, with counts
and links only. The lead copies the list into its report, asks the user no
question, and adds no waiting item for it; it runs `outcome` only after the
user names the work. While the lead state has no outcome, a due line names
`discover`, or, after the discovery task is verified, says to start no second
discovery; no due line names `finish`.

The lead reads the state, labels, titles, and check counts of issues and PRs,
never their text. In a recorded session, the hook of
[ADR 0007](0007-gate-the-project-lead-with-a-session-checked-hook.md) blocks
the T3 Code MCP tool `read_issue`, and `pull_request_read` with an `include`
other than `checks`, in Claude Code and Codex. Antigravity has no known hook
payload for MCP calls, so there only the step text holds the rule.

## Cleanup of a branch with no commit of its own

Added on 2026-11-23 for
[#528](https://github.com/aeghnnsw/cc-toolkit/issues/528).

T3 Code starts each new thread branch at the commit of the checkout that
starts it: the head of a merged PR, or a commit of the Default Branch. Such a
branch has no commit of its own. Before, the plan kept it: no merged PR of
that branch had its tip as its head commit, and for a tip in the Default
Branch, a session might have just started there. One close-out kept 20
worktrees and 21 branches for this reason, and the list grew with each batch.

Now a branch has no commit of its own when its tip is in the Default Branch
or is the head commit of any merged PR. The plan finds that PR with
`gh api repos/{owner}/{repo}/commits/<tip>/pulls`, filtered to merged PRs
whose head is the tip. It treats such a branch as merged, but keeps it when
its reflog shows that it was created less than 60 minutes ago, or when the
reflog cannot be read. The live session check, and this 60-minute rule for
a session that has just started, replace the rule that kept such a branch
because a session may have just started there. The Default Branch case is
needed too: new threads start at Default Branch commits, so without it the
same `KEEP` lines would appear again.

More clean worktrees are now removal candidates, and a clean worktree can
still hold work that Git ignores. Two rules keep that work:

- The plan keeps a worktree whose folder contains another worktree that Git
  lists, and the reason names that worktree. `git worktree remove` of the
  outer worktree would delete the inner one.
- In every mode, including `--main-only`, the plan reads the planning
  folders of each worktree that it would remove, and keeps the worktree when
  one of its folders is kept. With `--main-only`, it removes no planning
  folder outside the main checkout.

A lead folder has a date key, not an issue key, so the planning folder rule
also keeps a worktree that holds one. The lead state rule above stays,
because it also applies when `--planning-location` names another folder.
`dev-skills/tests/test_cleanup_plan.py` checks each rule.

## The compact start view

Added on 2026-11-23 for
[#555](https://github.com/aeghnnsw/cc-toolkit/issues/555),
[#556](https://github.com/aeghnnsw/cc-toolkit/issues/556), and
[#560](https://github.com/aeghnnsw/cc-toolkit/issues/560).

The lead runs `start` after each wake and each user message, and `start`
printed every task that was not closed out or settled and every decision. In
one lead session, its output grew from 1,319 to 10,894 characters over 68
calls, 67% of the characters of all tool results, and the context was
compacted twice.

So `start` prints a compact view: the lines before the tasks, the running and
pr-open tasks, one line that counts the other tasks by state and the
decisions, the due lines, and the waiting list. All paused tasks share one
due line. `show` prints the full view. `done`, `task pause`, `task resume`,
`task verified`, and `task settled` take several arguments; the script makes
all their changes under one lock with one save, and appends one event for
each argument. When it refuses one argument, it saves nothing.

`task start` and `task worker` record a worker's worktree path
(`--worktree`), and `closeout` prints the paths of each worker of the batch,
also of a replaced worker, so that the close-out worker passes them to
`retro_sessions.py --worktree`. T3 Code can remove a worker's worktree
before the close-out, for example when its pull request merges, and without
the path the retrospective missed its sessions.

`task add` without `--batch` puts a work task in a new batch once a pull
request of the highest batch merged. So the close-out of a batch waits only
for the tasks that it had when its first pull request merged. Check and
close-out tasks still go to the highest batch.
