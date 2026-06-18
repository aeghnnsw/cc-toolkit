---
name: run-cycle
description: Use when running task-loop in Codex, starting the Codex controller, dispatching task_loop_cycle_worker, processing task-loop task DB state, or executing a manual task-loop orchestration pass after setup, specify-aims, and create-cycle.
---

# Run Cycle

Run one conservative Codex task-loop controller pass. The main Codex thread is
the controller; do not create a separate orchestrator agent. Full unattended
scheduling remains pending.

## Preconditions

- `task-loop:setup`, `task-loop:specify-aims`, and `task-loop:create-cycle`
  have already run.
- `uv`, authenticated `gh`, and the task-loop CLI work from the repo root.
- `docs/task-loop/proposal.md`, `docs/task-loop/task-loop.md`, and
  `docs/task-loop/directions.md` exist.
- The `task_loop_cycle_worker` custom agent is synced and spawnable in this
  active Codex session. Setup sync alone is not proof; a restarted session may
  be required.

## Required References

Read these before taking controller actions:

1. `references/orchestrator-loop.md`
2. `<plugin-root>/references/pr-findings.md`
3. `docs/task-loop/directions.md`
4. `docs/task-loop/proposal.md`
5. `docs/task-loop/task-loop.md`

## Controller Contract

- The controller alone uses `task-loop` CLI commands, merges PRs, edits
  `proposal.md`, and decides issue/task transitions.
- Workers never use the task-loop CLI, merge PRs, or choose new task scope.
- `claim --json` is the only dispatch lock.
- Reset only with positive evidence that no live worker owns the task.
- A GitHub issue is the durable unit identity; a task is one attempt.
- A current-attempt PR must match both `Refs #<issue>` and the task-specific
  study-log path `docs/task-loop/logs/<NNN>_...md`.

## Dispatch Gate

Before any `claim --json`, prove dispatch is observable in this session:

1. Dry-run spawn `task_loop_cycle_worker` with an availability-check prompt.
   Intentionally omit seq, title, issue, and branch. Tell it not to edit files
   or run mutating commands.
2. Continue only if the observed reply is the expected missing-input refusal.
3. Confirm the active Codex surface can observe real worker acceptance or final
   completion. If not, reconcile/materialize/report only; do not claim.

After claim, build a complete dispatch packet before real launch:

- seq;
- title or scope;
- GitHub issue number;
- branch name, normally `tl/<NNN>`;
- repository root;
- paths to `directions.md`, `proposal.md`, and `task-loop.md`;
- reminder that the worker never uses task-loop CLI and never merges.

If the claimed task lacks an issue, create or adopt one, then run
`task-loop set-issue <seq> --issue <n> --json`. If the packet cannot be
completed before real launch, run `task-loop reset <seq>`, verify with
`status --json`, and report the skipped dispatch.

Real dispatch succeeds only when the worker reports a non-terminal
`accepted task <seq>, branch <branch>` and continues, or completes with a
PR/outcome. If acceptance is a terminal response before task work, immediately
continue/relaunch the worker with the same packet; if that cannot be done, reset
and verify because no worker is live. If launch clearly fails before the task
reaches a worker, or the worker explicitly refuses before task work, reset and
verify. If the task packet may have reached a live worker but the result is
ambiguous, do not reset; leave the task `working` and report
`dispatch outcome unknown`.

## Process

1. Locate the plugin root. In this repository use
   `uv run --script task-loop/cli/task-loop ...`; from an installed plugin use
   `uv run --script <plugin-root>/cli/task-loop ...`.
2. Read the required references and current project docs.
3. Work `references/orchestrator-loop.md` step by step.
4. Stop after one pass and report actions taken, skipped claims, dispatches,
   ambiguous working tasks, and remaining claimable work.
