# Task-loop Codex Cycle Worker Agent Design

## Goal

Make the task-loop cycle worker available to Codex as a custom agent while keeping the current Codex rollout incremental. This slice prepares the worker for future `run-cycle` dispatch; it does not implement the Codex orchestrator.

## Current Constraints

- Codex custom agents are standalone TOML files loaded from `~/.codex/agents/` or project `.codex/agents/`.
- The Codex plugin manifest supports skills and bundled hooks, but there is no documented plugin manifest field that directly exposes custom agents.
- Task-loop already has Codex `setup`, `specify-aims`, and `create-cycle` skills. The generated `docs/task-loop/task-loop.md` is already framed as the future worker contract.
- The existing Claude worker depends on Claude-only mechanics such as Agent Teams, `TodoWrite`, `Workflow`, `CLAUDE_PLUGIN_ROOT`, and `discuss-with-codex`. The Codex worker must not carry those requirements forward.

## Design

Add a Codex-specific agent source file at `task-loop/codex-agents/task-loop-cycle-worker.toml`. Its `name` is `task_loop_cycle_worker`, because Codex identifies custom agents by the TOML `name` field and agents installed under `~/.codex/agents/` share a user-global namespace. The source and destination filename stay namespaced as `task-loop-cycle-worker.toml` to avoid overwriting an unrelated user agent.

The agent is a thin executor. It receives one task's seq, title or scope, issue number, and branch; reads `docs/task-loop/directions.md` and `docs/task-loop/task-loop.md`; creates its own task worktree before any edit; follows the project cycle once; opens a PR with the required study log; reports the PR and outcome; and never merges. If required inputs or project cycle files are missing, it stops and reports the gap to the controller.

Add `task-loop/scripts/sync_codex_agents.py`. It derives the plugin root from its own path, reads `task-loop/codex-agents/*.toml`, parses each TOML file to get the Codex agent `name`, renders any `<plugin_root>` placeholders, and writes the files into `~/.codex/agents/` only when changed. Synced files include a task-loop management marker comment. Before writing, the script scans existing `~/.codex/agents/*.toml`; if an unmanaged file already has the same TOML `name`, or if the destination filename exists but is not task-loop managed and differs from the rendered content, the script reports a conflict and exits non-zero instead of overwriting user configuration. The script also accepts `--project-root <path>` for setup-time readiness checks; when supplied, it scans `<path>/.codex/agents/*.toml` and treats a project-local agent with the same TOML `name` as a conflict before writing global files. The script reports JSON statuses: `installed`, `updated`, `current`, or `conflict`.

Add a Codex SessionStart hook wrapper at `task-loop/hooks/codex-session-start.py` and hook config at `task-loop/hooks/codex-hooks.json`. The hook command uses `uv run --no-project ${PLUGIN_ROOT}/hooks/codex-session-start.py` so startup does not inherit a random repository's Python project. The wrapper invokes the sync script with `uv run --no-project <sync-script>` for the same reason. The hook runs the sync script on `startup|resume`, emits a concise `additionalContext` summary when agents sync, and treats sync failures as non-fatal. The plugin manifest declares `"hooks": "./hooks/codex-hooks.json"` so installed Codex plugins can expose the hook through Codex's hook trust flow.

Update `task-loop/codex-skills/setup/SKILL.md` so setup always runs the idempotent sync script as part of readiness. The setup commands derive `REPO_ROOT="$(git rev-parse --show-toplevel)"` and use `uv run --no-project task-loop/scripts/sync_codex_agents.py --project-root "$REPO_ROOT"` for repository checkout use or `uv run --no-project <plugin-root>/scripts/sync_codex_agents.py --project-root "$REPO_ROOT"` for installed plugin-cache use. The setup result must report agent sync status, fail readiness on conflicts, and note that a new or restarted Codex session may be required before the newly synced custom agent can be spawned.

## Scope Boundary

In scope:

- Codex custom agent definition.
- Idempotent agent sync script.
- SessionStart hook for sync.
- Codex plugin manifest hook declaration.
- Setup skill readiness guidance for the agent.

Out of scope:

- Codex `run-cycle`.
- Worker dispatch logic.
- Seat guards or parallel worker limits.
- Task DB or CLI changes.
- Declaring task-loop fully ready or discoverable as a complete Codex run-cycle plugin.

## Validation

- Parse the plugin manifest and hook JSON.
- Parse the custom agent TOML.
- Compile the Python sync and hook scripts.
- Run the sync script with a temporary `HOME` and verify the agent file appears under the temporary `~/.codex/agents/`.
- Run sync conflict tests with a temporary `HOME`:
  - unmanaged destination filename with different content returns non-zero, reports `conflict`, and is not overwritten;
  - unmanaged different filename with TOML `name = "task_loop_cycle_worker"` returns non-zero and does not install;
  - project-local `.codex/agents/*.toml` under `--project-root` with TOML `name = "task_loop_cycle_worker"` returns non-zero and does not install or update the global copy;
  - managed destination with identical rendered content returns `current`;
  - managed destination with stale content returns `updated`.
- Run the SessionStart hook with a temporary `HOME` and verify it emits Codex-compatible JSON or empty stdout on non-fatal failure.
- Run the SessionStart hook against a temporary conflict setup and verify sync non-zero becomes concise non-fatal hook output.
- Run sync and hook smoke tests from a temporary cwd containing a deliberately broken `pyproject.toml` to prove `uv run --no-project` isolates the commands from the active project.
- Validate the updated setup skill frontmatter and readiness content:
  - it contains a dedicated Codex agent sync section;
  - it shows the sync command for repo checkout use and installed plugin-root use, including `--project-root "$REPO_ROOT"`;
  - it states that non-zero sync means task-loop is not ready and conflict details must be reported;
  - its Result section includes agent sync status and the restart/new-session note.
- Scan Codex-facing files for Claude-only worker dependencies.
