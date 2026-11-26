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
>
> **Superseded in part (2026-11-24, issue #567).** `task verified` needs the
> count of decisions that the report numbers for the user. With a count above
> 0, it takes one task name. Read
> [Decisions of a finished worker](#decisions-of-a-finished-worker).
>
> **Superseded in part (2026-11-24, issue #577).** With `--main-only`, the
> plan lists each planning folder that a worktree removal deletes. Read
> [The planning folders of a removed worktree](#the-planning-folders-of-a-removed-worktree).
>
> **Superseded in part (2026-11-24, issue #574).** A `start` run in a command
> list also records a session. Read
> [Start in a command list](0007-gate-the-project-lead-with-a-session-checked-hook.md#start-in-a-command-list)
> in ADR 0007.
>
> **Superseded in part (2026-11-24, issue #578).** The cleanup plan also
> keeps each worktree that an unsettled T3 Code thread owns, read with the
> `t3` CLI. Read
> [The worktrees of T3 Code threads](#the-worktrees-of-t3-code-threads).
>
> **Superseded in part (2026-11-24, issue #604).** The hook passes
> `pull_request_read` only with `sections` set to `["checks"]`, and a worker
> sets triage labels. Read
> [The sections of pull_request_read](#the-sections-of-pull_request_read).
>
> **Superseded in part (2026-11-25, issues #599, #602, and #603).** `init`
> makes the lead folder and its ignore rule with `planning_folder.py`, and
> writes a `.gitignore` of `*` only when Git's `info/exclude` file cannot be
> written. `start` prints the fixed lead steps once in each thread.
> `task start-failed` records a thread that did not start. Read
> [The lead folder, failed starts, and the steps once](#the-lead-folder-failed-starts-and-the-steps-once).
>
> **Superseded in part (2026-11-26, issues #632 and #638).** The hook passes
> `pull_request_read` with `sections` or `include` set to `["checks"]`, and
> blocks `t3_thread_read` without `maxCharsPerItem`. Read
> [Both check parameters of pull_request_read, and the page size of t3_thread_read](#both-check-parameters-of-pull_request_read-and-the-page-size-of-t3_thread_read).

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
[The compact start view](#the-compact-start-view). Superseded in part by
#603: `start` prints the fixed lead steps once in each thread; read
[The lead folder, failed starts, and the steps once](#the-lead-folder-failed-starts-and-the-steps-once).)
`finish` deletes the lead
state only when each task is in the `settled` state and nothing waits on the
user.

The lead state is in `<top of the lead's working tree>/.scratch/<YYYYMMDD>-lead-<slug>/`,
with a `.gitignore` of `*`, `state.json`, `events.jsonl` (the history), and a
lock file. (Superseded in part by #599: Git's `info/exclude` file holds the
ignore rule, and the `.gitignore` is written only when that file cannot be
written; read
[The lead folder, failed starts, and the steps once](#the-lead-folder-failed-starts-and-the-steps-once).) The script runs as a shell command, inside the host's sandbox, and
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
`python3 "<script>" start` records a session. (Superseded by #574: that
command also records a session in a command list; read
[Start in a command list](0007-gate-the-project-lead-with-a-session-checked-hook.md#start-in-a-command-list)
in ADR 0007.)

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
because it cannot tell whether the worktree holds a lead state. (Since #575,
it also keeps every other worktree that it would remove; read
[The worktrees of lead tasks](#the-worktrees-of-lead-tasks).)
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

### The worktrees of lead tasks

Added on 2026-11-24 for
[#575](https://github.com/aeghnnsw/cc-toolkit/issues/575).

The plan kept the worktree that holds a lead state, but not the worktrees of
the lead's workers. It counted a worker's worktree as live only for a Git
lock, a process, or a session log of the last 60 minutes. The plan for the
batch 13 close-out marked `REMOVE` 4 worktrees whose tasks were `verified`,
not `settled`, and a read-only check kept them by hand.

Now the plan reads each lead state, also the one in the main checkout, with
`load` of `t3_project_lead.py`. In every mode, it keeps each worktree whose
path a task records in `worktrees` while the task is not `settled`. The
reason names the task, the lead state, and the task's state. A task matches a
worktree by its recorded path only: T3 Code renames a branch after
`task start`, and 4 of 7 recorded branches no longer matched. A task without
a recorded path, such as a task from before #556, keeps no worktree by this
rule. The close-out runs repo-cleanup while the tasks of its batch are
`verified`, so it keeps their worktrees. A later repo-cleanup removes them
after the lead settles the workers.

When a lead state exists but cannot be read, the plan keeps every worktree
that it would otherwise remove, and the reason gives the error: an `OSError`,
invalid JSON, a `schema` other than 1, or a task without the expected fields.
The plan cannot tell which worktrees such a lead state records. The same rule
applies when a `.scratch` or a lead folder cannot be listed, because a lead
state may be there. So the plan finds the lead folders itself: `lead_folders`
of `t3_project_lead.py` skips a folder that it cannot read. With no lead
state, this rule keeps nothing. This follows the rule of repo-cleanup: when a
check cannot run, the plan keeps the item and gives the error as the reason.

The plan does not read the T3 Code state database, `statev2.sqlite`. One
read-only query would map each worktree to the state of its thread, but the
schema is internal to T3 Code (Beta). The fields of that state moved between
releases, from columns to JSON, and the database also holds full transcripts.
Reading it would need a new ADR. Calls of T3 Code tools from the skill would
also cover the threads that no lead manages. But only an agent inside T3 Code
has the tools, and it needs one `t3_thread_read` call for each thread.
[#578](https://github.com/aeghnnsw/cc-toolkit/issues/578) tracks that option.
Until then, an unsettled T3 Code thread that no lead state records has only
the 60-minute live session check.
(Superseded in part by #578: the plan now reads the T3 Code threads with the
`t3` CLI; read [The worktrees of T3 Code threads](#the-worktrees-of-t3-code-threads).)

### The session logs of an accepted task

Added on 2026-11-24 for
[#610](https://github.com/aeghnnsw/cc-toolkit/issues/610).

The live session check keeps each worktree with a session log of the last 60
minutes. A repo-cleanup that runs right after the workers finish finds their
logs inside that window. In one close-out on 2026-11-24, with dev-skills
3.72.0, the plan kept 6 finished worktrees for this reason only. The
close-out asked the user, and its PR waited about 4.7 hours.

Now session logs and Antigravity conversations do not keep a worktree when
each task that records its path is in an accepted state: `verified`,
`closed-out`, or `settled`, and not cancelled (`accepted` of
`t3_project_lead.py`). The lead accepted the final report of the task's
worker, and `task worker` tells the lead to settle a replaced worker at once,
so the sessions of the task's workers have ended. A cancelled task does not
count: the lead accepted no final report. A Git lock or a running process
still keeps the worktree, which protects a session that runs (#419). The
#575 rule above, which keeps the worktree of a task that is not `settled`,
decides first. So the close-out still keeps the worktrees of its `verified`
tasks, and the repo-cleanup after the lead settles the workers removes them
without the 60-minute wait.

When only session logs and Antigravity conversations keep a worktree,
`live_worktrees.py` prints the time when their 60-minute window ends, and the
plan reason gives it. repo-cleanup waits until the latest such time, runs the
plan once more, and does not ask the user. This wait covers the worktrees
that no lead state records, such as a thread outside a lead task (#578).

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
other than `checks`, in Claude Code and Codex. (Superseded by #604: the tool
takes `sections`; read
[The sections of pull_request_read](#the-sections-of-pull_request_read).
Superseded in part by #638: another build takes `include`, and the hook
passes either name.)
Antigravity has no known hook payload for MCP calls, so there only the step
text holds the rule.

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
  folder outside the main checkout. (Superseded by #577: it lists the
  folders that a worktree removal deletes; read
  [The planning folders of a removed worktree](#the-planning-folders-of-a-removed-worktree).)

A lead folder has a date key, not an issue key, so the planning folder rule
also keeps a worktree that holds one. The lead state rule above stays,
because it also applies when `--planning-location` names another folder.
`dev-skills/tests/test_cleanup_plan.py` checks each rule.

### The planning folders of a removed worktree

Added on 2026-11-24 for
[#577](https://github.com/aeghnnsw/cc-toolkit/issues/577).

With `--main-only`, the plan printed no line for a completed planning folder
in a worktree that it removed, but `git worktree remove` still deleted the
folder. In the batch 13 close-out, the plan without the flag listed 2 such
folders, and the `--main-only` plan listed neither. So the plan and the
cleanup report did not name everything that cleanup deletes.

Now, with `--main-only`, the plan prints a `REMOVE` line for each completed
folder in a worktree that it removes, and the reason adds that removing the
worktree deletes the folder. The plan decides these lines after it reads all
folders of the worktree: folder names sort as text (`12-done` before
`5-open`), and a kept folder later in the order keeps the worktree. A folder
in a kept worktree or in the current worktree gets no `REMOVE` line. The plan
without `--main-only` does not change.

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
each argument. When it refuses one argument, it saves nothing. (Superseded in
part by #567: with a count of decisions above 0, `task verified` takes one
task name; read [Decisions of a finished worker](#decisions-of-a-finished-worker).)

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

## Decisions of a finished worker

Added on 2026-11-24 for
[#567](https://github.com/aeghnnsw/cc-toolkit/issues/567).

A lead ended a run with `Waiting on you: nothing.`, and the same report listed
three decisions for the user. The worker's ISSUES report had numbered two of
them. Only the `answer` step recorded a worker's decisions with `wait`, and it
applies to a worker that waits; `verify` and `task verified` did not ask for
them. A due line then sent the lead to `finish`, which deleted the lead state.
After that, the lead could not add the items.

The script cannot read a report, so `task verified` now needs
`--decisions N`: the number of decisions that the report numbers for the
user, or 0. With several task names, N must be 0. When N is above 0, the
script adds one worker item with the worker's link, as `wait --task` does.
An item for a task that is verified, closed out, cancelled, or settled holds
decisions of a finished report. No due line offers `done` for it, because
only the user decides it, and `finish` refuses while an item waits.
`wait --task` now refuses only a task without a worker, so a lead can also
record a finished worker's decisions after the worker is settled.

The `report` step covers each decision that only the user can make. It keeps
the rule of [The discover step](#the-discover-step): the discovery list is not
a waiting item. It says to write no other list of decisions for the user. The
due line of `finish` names that rule first. `finish` prints no waiting list,
because it runs only when the list is empty.

## The worktrees of T3 Code threads

Added on 2026-11-24 for
[#578](https://github.com/aeghnnsw/cc-toolkit/issues/578).

A T3 Code thread that no lead state records had only the 60-minute live
session check. After that window, the plan removed its worktree when the
worktree was clean and its branch merged. On 2026-11-24, 1 such worktree,
`t3-6c6c2af8`, belonged to an unsettled top-level thread.

Now the plan reads the T3 Code threads with the `t3` CLI. T3 Code is not a
host; the CLI is an optional source of keep evidence. The CLI is
`T3CODE_CLI_PATH` when it is set, else `t3` on `PATH`. The plan runs
`t3 thread list --json --project <main checkout>` once. For each row with
`settled: false`, it runs `t3 thread show --json --messages 1 <threadId>`.
It keeps each worktree whose real path equals the real path of
`thread.worktreePath`, and the reason is `T3 thread <id> is not settled`. A
thread with no worktree path keeps nothing. The plan has no `--keep` flag,
because it reads the thread state itself.

When the plan finds no CLI, this rule keeps nothing, and the other rules
decide. When the list prints "No T3 Code project matches", the repository is
no T3 Code project, and this rule also keeps nothing. On any other failure,
the plan keeps every worktree that it would otherwise remove, and the reason
gives the error: a call that cannot run, a non-zero exit status (also the
launcher's 127, "T3 Code has moved or been removed"), a timeout of 10
seconds, output that is not JSON, or a missing `threadId`, `settled`, or
`thread.worktreePath`, or one of another type, such as a `settled` that is
not a boolean. When T3 Code changes the "No T3 Code project matches"
text, this rule applies too.

The CLI asks the running T3 Code server. On 2026-11-24, `t3` v0.1.11 with a
data directory that no running server used exited 1 with "No running T3 Code
server uses <dir>. Start T3 Code, then retry.", also with a stale
`server-runtime.json`. So while the T3 Code app is closed, the plan keeps
every worktree that it would otherwise remove. In the Claude Code sandbox,
`t3` also fails, but `ps` fails there too, so the plan already kept every
worktree.

The plan uses the CLI, not the MCP tools of T3 Code: the plan cannot tell a
skipped or partial agent step from "no unsettled threads", only an agent
inside T3 Code has the tools, and their prefix differs by host. It does not
read the T3 Code state database, for the reasons in
[The worktrees of lead tasks](#the-worktrees-of-lead-tasks). The CLI is a
command that T3 Code installs for users; a change to its output stops
removals and cannot make the plan remove more.

Known limit: `thread list` hides `delegate_task` workers. Only a lead state
keeps the worktree of such a worker.
`dev-skills/tests/test_cleanup_plan.py` checks each rule with a fake `t3`.

## The sections of pull_request_read

Added on 2026-11-24 for
[#604](https://github.com/aeghnnsw/cc-toolkit/issues/604).

The hook checked the `include` of `pull_request_read`, but the T3 Code tool
has no `include`. Its parameter is `sections`, a list of `summary`,
`checks`, `conversation`, and `diff`, with the default `summary` and
`checks`. So the hook blocked two lead calls that passed `include`, which
the tool does not read, and passed a call with `sections`
`["conversation", "diff"]`, which returns PR text.

Now, in a recorded session, the hook passes `pull_request_read` only when
`sections` is exactly `["checks"]`. A call without `sections` blocks,
because the default includes `summary`, which can hold the PR body. An
`include` must be absent or exactly `["checks"]` too. A call with `include`
and no `sections` blocks: the server can ignore `include` and return the
default sections, and the hook cannot tell which name a host uses. Any other
value, and a tool input that is not an object, also block. `start` tells
the lead to pass `sections` `["checks"]`.
(Superseded by #638: a T3 Code build can name the parameter `include`, and
the hook passes either name; read
[Both check parameters of pull_request_read, and the page size of t3_thread_read](#both-check-parameters-of-pull_request_read-and-the-page-size-of-t3_thread_read).)

The `start` step also said "Set triage labels and issue state". The hook
blocks `gh`, and the lead has no tool that sets labels, so a worker had to
set them. Now `start` says that the lead sets issue state and a worker sets
triage labels, and `plan` says that another worker sets the labels that a
read-only worker recommends.
`dev-skills/tests/test_t3_project_lead_hook.py` and
`dev-skills/tests/test_t3_project_lead.py` check these rules.

## The lead folder, failed starts, and the steps once

Added on 2026-11-25 for
[#599](https://github.com/aeghnnsw/cc-toolkit/issues/599),
[#602](https://github.com/aeghnnsw/cc-toolkit/issues/602), and
[#603](https://github.com/aeghnnsw/cc-toolkit/issues/603).

`init` makes the lead folder with `planning_folder.py`, which
grill-with-research and matt-automode also run, so that one script holds the
folder rules. The name stays `.scratch/<YYYYMMDD>-lead-<slug>/`, now with the
local date that the script uses. The script makes Git ignore `.scratch/` with
a line in Git's `info/exclude` file. The Codex `workspace-write` sandbox keeps
the Git common folder read-only: on 2026-11-24, `codex sandbox` of Codex
0.172.0 refused that write in a main checkout with "Operation not permitted".
So when the write fails, `init` writes the `.gitignore` of `*` in the lead
folder and prints the error. The lead script and the cleanup plan find the
lead folders and the planning folders with `planning_folder.py`. A `.scratch`
that cannot be read, or that is a file, is an error, not an empty folder, so
that no lead state is missed; the cleanup plan then keeps every worktree that
it would otherwise remove.

In one lead session, `start` ran 133 times, and its fixed lead steps were most
of the 574,000 characters that it printed. So the lead state records the
thread that saw the steps. `start` prints them without a lead state, on the
owner's first `start` after `init` or `takeover`, and with `start --steps`.
Other `start` calls print one line that names `start --steps`. A thread that
is not the owner cannot record, so it always gets the steps.

On 2026-11-24, eight new worker threads timed out while they started, and T3
showed each failure only after its start limit of 10 minutes. `task
start-failed` records such a start. While the record is open, `start` and
`dispatch` print one line: start no new thread, give each next task to an idle
worker, and ask one to find the cause. An idle worker is the worker of a
verified or closed-out task that no running, pr-open, or merged task uses. No
due line settles an idle worker while the record is open. A new thread closes
the record only after the start limit passes without a failure, because the
lead runs `task start` before T3 can show a failure. `task start` refuses a
worker that a running, pr-open, or merged task uses, and a settled worker.

## Both check parameters of pull_request_read, and the page size of t3_thread_read

Added on 2026-11-26 for
[#638](https://github.com/aeghnnsw/cc-toolkit/issues/638) and
[#632](https://github.com/aeghnnsw/cc-toolkit/issues/632).

T3 Code builds differ in the check parameter of `pull_request_read`. The
build that #604 measured has `sections`. The build of another lead session,
and of a worker session on 2026-11-26, has `include`, a list of `body`,
`checks`, `threads`, `comments`, and `diff`, and no `sections`. The hook
passed only `sections`, so it blocked every check read of a lead in an
`include` build.

Now, in a recorded session, the hook passes `pull_request_read` when
`sections` or `include` is present and each one that is present is exactly
`["checks"]`. A call with neither blocks, because a default can hold the PR
body. Any other value, the two set to different values, and a tool input
that is not an object also block. `start` tells the lead to call
`pull_request_read` only with `sections` or `include` `["checks"]`.

The worker session measured the `include` build: `include` `["checks"]`
returned the state, the check counts, and the check runs, without the body
or the comments. A call with `sections` failed with
`Unknown argument "sections"`. No session measured how a `sections` build
treats an `include`. If that build ignores `include`, a call with only
`include` `["checks"]` gets its default, `summary` and `checks`, and the
summary can hold the PR body. The hook cannot tell which build a host runs,
and it accepts this risk: the lead sends the parameter that its tool schema
names, the one build that was measured rejects an argument that it does not
have, and the old rule blocked every check read in an `include` build.

Without `maxCharsPerItem`, `t3_thread_read` gives each item in pages of 500
characters. After a context summary, a lead left the option out, read one
worker report in 8 calls, and stopped before its end. Now, in a recorded
session, the hook blocks `t3_thread_read` unless `maxCharsPerItem` is a
positive integer, and the block names 8000. The Claude Code and Codex hook
matchers select `t3_thread_read`, and `start` tells the lead to pass
`maxCharsPerItem` 8000. Antigravity has no known hook payload for MCP calls, so there only
the step text holds both rules.
`dev-skills/tests/test_t3_project_lead_hook.py` and
`dev-skills/tests/test_t3_project_lead.py` check these rules.
