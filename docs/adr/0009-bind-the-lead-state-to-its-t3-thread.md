# Bind the lead state to its T3 thread, and find it in any worktree

A project lead keeps its lead state in `.scratch/` of its own working tree
([ADR 0008](0008-keep-project-lead-state-in-a-cli.md)). `t3_project_lead.py`
looked for a lead state only there. A new T3 Code session usually gets a new
worktree, so its `start` printed "No lead state", and `init` there made a
second lead state while the first one still had running tasks and waiting
items. Nothing tied a lead state to one lead: a T3 fork keeps its source's
worktree, so two threads could change one state. A flagged lead had no way to
recover ([#544](https://github.com/aeghnnsw/cc-toolkit/issues/544)).

These facts come from the T3 Code source, pingdotgg/t3code `main` at
`a3323d4`:

- A fork copies `worktreePath` and gets a new thread ID
  (`ThreadForkService.ts`).
- A provider change keeps the thread and its worktree (`RuntimePolicy.ts:87`).
- T3 sets `T3CODE_THREAD_ID` for Claude Code, Codex, and Antigravity
  (`ClaudeAdapterV2.ts:1597`, `CodexAdapterV2.ts:1659`,
  `provider-acp/src/server/adapter.ts:1099`).

No real fork was observed.

Decisions:

1. **Lookup.** When `start` finds no lead state in its own working tree, it
   lists the lead states of every other worktree of the repository, from
   `git worktree list --porcelain`, with the folder rule of ADR 0008. For each
   state it prints the path, slug, owner thread, last change (UTC), the number
   of open tasks and waiting items, and the worktree. It tells the lead to
   continue that lead in its own worktree and not to run `init`. Three ways
   continue a lead: a provider change of the lead thread, a fork of the lead
   thread, or a new thread from `t3_thread_launch` with `workspaceStrategy`
   `existing_worktree`. The lookup only reads. When Git cannot list the
   worktrees, `start` prints the problem and the `init` line.
2. **Second lead.** `init` refuses while another worktree holds a lead state,
   and lists the states. `init <slug> --also` creates the state anyway. The
   refusal and the `plan` step say to pass `--also` only after the user
   confirms.
3. **Owner.** `init` records the value of `T3CODE_THREAD_ID` as the `owner` of
   the lead state. `init` and `takeover` refuse when the variable is not set or
   is empty. Each command that changes or deletes the state refuses when the
   current thread is not the owner, or when the state has no owner. The
   refusal names the owner and `takeover`. `show`, `waiting`, and the steps do
   not check the owner. The view of `start` and `show` names the owner, and
   says so when the current thread is not the owner. The schema stays 1:
   `owner` is a new optional field, so older code still reads the state.

Rejected alternatives:

- **A command that copies the lead state into the new worktree.** Each host's
  sandbox lets the script write only its own working tree (ADR 0008), so it
  cannot remove the old copy, and two copies would remain.
- **The Git common folder**, which every worktree shares. It is read-only in
  a sandboxed Codex session (ADR 0008).
- **The provider session ID as the owner.** It changes at each provider change
  and restart, so the lead would need a takeover after each one.
- **No owner.** Two threads in one worktree, such as a fork and its source,
  could both change the state.

Consequences:

- `takeover` makes the current thread the owner, and appends one event with
  the old and the new owner. A takeover by the owner changes nothing. A lead
  state made before this change has no owner and needs one `takeover`.
- The first `start` of the new owner after a takeover prints a due line: check
  `t3_thread_list` with `includeSubagents` and `pull_request_list` for work
  that the state does not name, such as a worker that started just before the
  takeover, and record it. So `start` clears a flag in the state once.
- A provider change keeps the thread ID, so it needs no step.
- A flagged lead recovers in a new thread bound to the lead's worktree, with
  `t3_thread_launch` and `existing_worktree`, on another model. That thread
  runs `start`, then `takeover`. A fork of the flagged thread would copy the
  flagged context.
- With `worktreeOnDelete`, T3 removes a thread's worktree when the thread is
  deleted. A fork and a thread bound to the lead's worktree use the same
  worktree. So the skill and the README say to delete the lead thread only
  after `finish`.
- `cleanup_plan.py` already keeps each worktree that holds a lead state (ADR
  0008, [#543](https://github.com/aeghnnsw/cc-toolkit/issues/543)).
- The hook of ADR 0007 already allows `takeover` and `init <slug> --also`,
  because it allows `python3 "<script>" <subcommand> [arguments...]`.
