# Task-loop Codex Cycle Worker Agent Plan

## Issue

#156 - Add Codex cycle-worker agent support for task-loop.

## Steps

1. Add `task-loop/codex-agents/task-loop-cycle-worker.toml`.
   - Define required Codex custom agent fields: `name`, `description`, and `developer_instructions`.
   - Use `name = "task_loop_cycle_worker"` to avoid claiming a generic global Codex agent name.
   - Keep the agent instruction focused on one task, one worktree, one PR, and no merge.
   - Replace Claude-only mechanics with Codex skills and plain checklist/reporting instructions.

2. Add the Codex agent sync script.
   - Create `task-loop/scripts/sync_codex_agents.py`.
   - Derive plugin root from the script location.
   - Parse source TOML to get the Codex agent name.
   - Copy rendered TOML from `codex-agents/` into `~/.codex/agents/`.
   - Prefix synced files with a task-loop management marker.
   - Detect unmanaged destination filename conflicts and duplicate TOML-name conflicts before writing.
   - Support `--project-root <path>` and detect duplicate TOML-name conflicts in `<path>/.codex/agents/` before writing global files.
   - Emit JSON status for each synced agent and exit non-zero on conflicts.

3. Add the Codex SessionStart hook.
   - Create `task-loop/hooks/codex-session-start.py`.
   - Create `task-loop/hooks/codex-hooks.json`.
   - Run the sync script on `startup|resume`.
   - Use `uv run --no-project` in the hook command and wrapper so hook startup is isolated from the active repository's Python project.
   - Make failures non-fatal and concise.

4. Update Codex plugin metadata.
   - Add `"hooks": "./hooks/codex-hooks.json"` to `task-loop/.codex-plugin/plugin.json`.
   - Update description, keywords, and interface text to mention cycle-worker agent sync without implying `run-cycle` is implemented.

5. Update the setup skill.
   - Add agent sync to setup readiness.
   - Tell Codex to derive `REPO_ROOT="$(git rev-parse --show-toplevel)"`.
   - Tell Codex to run the sync script idempotently with `uv run --no-project` and `--project-root "$REPO_ROOT"` in both checkout and installed plugin-root command forms.
   - Report agent sync status in the setup result and stop readiness on conflicts.
   - Note that a new or restarted Codex session may be required for first use.

6. Validate.
   - JSON/TOML parse checks.
   - Python compile checks.
   - Temporary-home sync and hook smoke tests.
   - Temporary-home sync conflict tests for unmanaged destination file, duplicate TOML name in another global file, duplicate TOML name in project-local `.codex/agents/` via `--project-root`, managed-current, and managed-updated cases.
   - Hook conflict test confirming sync non-zero is reported as concise non-fatal hook output.
   - Sync and hook smoke tests from a temporary cwd with a broken `pyproject.toml` to prove `uv run --no-project` isolation.
   - Setup skill validation for frontmatter plus grep/assert checks for the agent sync section, checkout and plugin-root `uv run --no-project` command forms with `--project-root "$REPO_ROOT"`, non-zero conflict readiness behavior, result status, and restart/new-session note.
   - Forbidden Claude-only term scan in Codex-facing worker files.

7. Commit, push, and open a concise PR.
