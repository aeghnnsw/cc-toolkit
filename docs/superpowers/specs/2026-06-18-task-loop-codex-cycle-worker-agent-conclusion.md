# Task-loop Codex Cycle Worker Agent Pressure-Test Conclusion

## Settled Position

Implement Codex cycle-worker agent support by storing a namespaced custom agent in the task-loop plugin, syncing it into Codex's user-global custom-agent directory through an idempotent script, and wiring that script into setup plus a non-fatal SessionStart hook.

This PR prepares the worker for future Codex `run-cycle` dispatch. It does not implement `run-cycle`, seat guards, parallel dispatch, task DB changes, or full Codex task-loop discoverability.

## Key Decisions

- Use `task_loop_cycle_worker` as the Codex agent `name` and `task-loop-cycle-worker.toml` as the source/destination filename.
- Treat Codex agent names as global user configuration, not plugin-local names.
- Add `sync_codex_agents.py` with global duplicate-name detection, unmanaged destination conflict detection, task-loop managed markers, and optional `--project-root` duplicate-name checks for project `.codex/agents/`.
- Make setup pass `--project-root "$REPO_ROOT"` and fail readiness on sync conflicts.
- Use `uv run --no-project` in setup commands, hook config, and hook wrapper calls so sync does not inherit an arbitrary repository Python project.
- Keep SessionStart sync non-fatal; setup is the target-repo readiness gate.

## Objections And Dispositions

Round 1 objection: `cycle_worker` and `cycle-worker.toml` were too generic for user-global `~/.codex/agents/`.
Disposition: conceded. The design now uses `task_loop_cycle_worker` and `task-loop-cycle-worker.toml`, plus conflict detection.

Round 2 objection: conflict handling was central but not validated.
Disposition: conceded. Validation now covers unmanaged destination conflicts, duplicate global TOML names, managed current/update paths, and hook conflict behavior.

Round 3 objection: setup readiness validation only covered metadata, not the readiness flow.
Disposition: conceded. Validation now checks setup content for the sync section, commands, conflict behavior, result status, and restart/new-session note.

Round 4 objection: hook and setup command forms could inherit a broken active project through bare `uv run`.
Disposition: conceded. Commands now use `uv run --no-project`, and validation includes a broken `pyproject.toml` cwd.

Round 5 objection: global conflict detection ignored project-local `.codex/agents/`.
Disposition: conceded. The sync script now has a setup-only `--project-root` check and validation includes project-local duplicate-name conflicts.

Round 6 result: `NO SUBSTANTIVE OBJECTION.`

## Unresolved Tensions

- Codex does not yet document plugin-bundled agents as a first-class manifest field. Syncing into `~/.codex/agents/` remains a pragmatic compatibility path until Codex exposes plugin-native agents.
- A newly synced custom agent may require a new or restarted Codex session before it can be spawned.

## Ending Condition

Converged at round 6, the configured round cap.
