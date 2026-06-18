# Codex Orchestrator Loop

This is a manual single-pass controller algorithm for Codex. Re-run the skill
for another pass. Do not schedule unattended Loop A/Loop B jobs from Codex yet.

## State Sources

- Task DB through the task-loop CLI only:
  `status --json`, `add`, `claim --json`, `set-issue`, `close`, `reset`.
- GitHub through `gh` issues and PRs.
- Git-tracked project files under `docs/task-loop/`.
- Worker handoff messages observed in this Codex session.

## 0. Read State

Read `docs/task-loop/directions.md` first, then `proposal.md`,
`task-loop.md`, `status --json`, and relevant GitHub issues/PRs. If any
required project file is missing, stop before task DB mutation.

For each `working` task, find current-attempt PR candidates by:

1. `Refs #<issue>` in PR body or linked issue search; and
2. the task-specific study-log path `docs/task-loop/logs/<NNN>_`.

Issue-only matches are historical attempt candidates. Do not treat one as the
current task PR without the study-log path or an in-session worker handoff.

## 1. Honor Steering

Apply current `directions.md` constraints before irreversible actions: pause
dispatch, freeze merges, priorities, explicit blockers, or user-provided reset
instructions. A stale reset line in `directions.md` is not enough to reset; the
controller must still have positive no-live-worker evidence.

## 2. Classify Working Tasks

For each `working` task:

- **PR with `Outcome: success` and clean gates:** merge using GitHub's current
  head-SHA protection, close the GitHub issue, then `task-loop close <seq>`.
- **PR with `Outcome: blocked`:** close the attempt task, keep the issue open,
  and materialize the blocker/remnant as a new task linked by dependency.
- **PR with `Outcome: failed`, red gates, conflict, or stale pending state:**
  close the attempt task, read the attempt history for that issue, and
  materialize a materially different re-attack against the same issue.
- **Working with no PR:** reset only with positive no-live-worker evidence:
  observed in-session refusal/failure before task work or explicit human CLI
  reset. A Codex cold-start declaration is not proof that prior workers are
  dead. Otherwise surface it and move on.

Do not merge broken work because checks are green; read the study-log outcome
first.

## 3. Reconcile Proposal

If merged study-log findings change roadmap, assumptions, or milestones,
recompute the affected `proposal.md` sections from current default-branch
state plus all merged study logs not yet reflected. The controller is the only
`proposal.md` editor. Skip this step when no plan-affecting findings landed.

## 4. Materialize Tasks

Ensure the board has the next goal-driving work, but add only tasks with
durable unit identity:

- proposal hypothesis IDs such as `H1.1`;
- proposal milestone IDs such as `M1`;
- issue-backed re-attacks from classified attempts;
- direction-instructed work that names an explicit issue or durable unit marker.

Before creating an issue, search for an existing issue carrying the same unit
marker. Use a marker such as `<!-- task-loop-unit: proposal:H1.1 -->` in issue
bodies. Add tasks with `task-loop add "<title>" --issue <n> [--dep <seq>...]`.

Do not materialize free-form Findings text into tasks unless it already has a
durable marker or is part of a diagnosed re-attack/blocker flow.

## 5. Dispatch Claimable Work

Default capacity is one task per manual pass unless the user explicitly asks
for more.

Before claiming, pass the dispatch gate from `SKILL.md`. If the gate fails,
report claimable work and stop without claiming.

For each dispatch slot:

1. Run `task-loop claim --json`.
2. If it returns `null` or no task, stop dispatch.
3. Build a complete dispatch packet. If `issue` is missing, create or adopt a
   GitHub issue and run `task-loop set-issue <seq> --issue <n> --json`.
4. If the packet cannot be completed before real launch, run
   `task-loop reset <seq>`, verify with `status --json`, and report skipped
   dispatch.
5. Spawn `task_loop_cycle_worker` with the complete packet and ask it to report
   `accepted task <seq>, branch <branch>` before task work when the surface can
   expose an intermediate response.
6. If launch clearly fails before the packet reaches a worker, or the worker
   explicitly refuses before task work, reset and verify.
7. If non-terminal acceptance or final PR/outcome is observed, leave the task
   `working` for PR classification on this or the next pass.
8. If acceptance is a terminal response before task work, continue/relaunch the
   worker immediately with the same packet. If that cannot be done, reset and
   verify because no worker is live.
9. If the real packet may have reached a live worker but the result is
   ambiguous, do not reset. Report `dispatch outcome unknown`.

## 6. Goal Check And Report

Evaluate proposal success criteria using concrete commands or artifacts when
available. Do not infer success from all tasks being closed.

End the pass with:

- CLI commands run and notable results;
- tasks closed, reset, materialized, or dispatched;
- PRs merged or left pending;
- any skipped claim reason;
- ambiguous `working` tasks;
- next recommended pass action.
