# Design - Codex task-loop setup slice

Issue: #146
Parent: #140

## Goal

Make `task-loop` Codex-installable so it can be loaded and tested in Codex, while
shipping only the first supported Codex capability: setup and preflight.

This is a phased rollout. The marketplace entry is intentional even though full
autonomous task-loop execution is not ready yet. Metadata and skill text must be
honest that this slice supports setup only.

## Current State

`task-loop` is already a Claude Code plugin with:

- `.claude-plugin/plugin.json`
- `skills/setup`
- `skills/specify-aims`
- `skills/create-cycle`
- `skills/run-cycle`
- `agents/cycle-worker.md`
- the `cli/task-loop` executable and `db/schema.sql`

Codex currently has no `task-loop/.codex-plugin/plugin.json`, no
`task-loop/codex-skills/`, and no `task-loop` entry in
`.agents/plugins/marketplace.json`.

The Codex prerequisite plugin `dev-skills` now exposes:

- `goal-rubric`
- `doc-update`
- `pressure-test`

For Codex, `pressure-test` replaces the old `discuss-with-codex` dependency.

## Scope

This PR adds:

- `task-loop/.codex-plugin/plugin.json`
- `task-loop/codex-skills/setup/SKILL.md`
- a `task-loop` entry in `.agents/plugins/marketplace.json`
- a design spec and implementation plan for this setup-only slice

It also updates the parent tracking issue with the current prerequisite status.

## Out of Scope

This PR does not port:

- `specify-aims`
- `create-cycle`
- `run-cycle`
- `cycle-worker`
- Codex automation or worker dispatch

Those features should roll out one at a time in later PRs:

1. `setup`
2. `specify-aims`
3. `create-cycle`
4. `run-cycle`

## Codex Manifest

Add `task-loop/.codex-plugin/plugin.json` using the same plugin identity:

- `name`: `task-loop`
- `version`: same base version as the Claude manifest unless a Codex-specific
  cachebuster is needed later
- `skills`: `./codex-skills/`
- metadata focused on setup, Supabase configuration, CLI preflight, and phased
  task-loop rollout

The manifest should not declare hooks, MCP servers, apps, or agents.

The interface/default prompts should not imply full autonomous execution. They
should point users toward setup and preflight, for example:

- `Set up task-loop for this repo.`
- `Check task-loop prerequisites.`

## Marketplace Entry

Add `task-loop` to `.agents/plugins/marketplace.json` with the existing local
repo-marketplace shape:

```json
{
  "name": "task-loop",
  "source": {
    "source": "local",
    "path": "./task-loop"
  },
  "policy": {
    "installation": "AVAILABLE",
    "authentication": "ON_INSTALL"
  },
  "category": "Developer Tools"
}
```

Append it after the existing entries unless the file already has a different
intentional order.

## Codex Setup Skill

Create `task-loop/codex-skills/setup/SKILL.md`.

The frontmatter description must be concise and accurate. It should trigger on
task-loop setup, Supabase backend configuration, credential save, repo
registration, dependency checks, preflight, and setup smoke tests.

The skill body should be Codex-native and should not copy the Claude setup skill
verbatim. It should keep the parts that are runtime-neutral:

- verify `uv --version`
- verify `gh auth status`
- explain Supabase project creation and schema application
- run `uv run task-loop/cli/task-loop login`
- run `uv run task-loop/cli/task-loop init`
- run setup smoke test:
  - `add "setup smoke test"`
  - `status`
  - `close <seq>`

The skill should check for required Codex skills by name:

- `superpowers:brainstorming`
- `superpowers:writing-plans`
- `superpowers:test-driven-development`
- `superpowers:verification-before-completion`
- `superpowers:receiving-code-review`
- `dev-skills:pressure-test`
- `dev-skills:goal-rubric`
- `dev-skills:doc-update`

It should clearly say that Codex `specify-aims`, `create-cycle`, and `run-cycle`
are pending ports and are not enabled by this setup slice.

## Claude-Specific Text to Avoid

Codex-facing files in this slice must not mention:

- `Agent Teams`
- `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`
- `${CLAUDE_PLUGIN_ROOT}`
- `discuss-with-codex`
- `TodoWrite`

The Claude-facing plugin and skills remain unchanged.

## Validation

Run these checks:

- `jq . task-loop/.codex-plugin/plugin.json`
- `jq . .agents/plugins/marketplace.json`
- `quick_validate.py task-loop/codex-skills/setup`
- a discovery check confirming setup is the only task-loop Codex skill
- a scan confirming the Codex setup skill has no Claude-only terms
- `git diff -- task-loop/skills/setup/SKILL.md` should be empty
- `uv run task-loop/cli/task-loop status` if local credentials are available

## Acceptance Criteria

- `task-loop` is present in the Codex marketplace.
- `task-loop` has a valid Codex manifest pointing at `./codex-skills/`.
- Codex discovers exactly one task-loop skill: `setup`.
- The setup skill is concise, accurate, and Codex-native.
- The setup skill verifies setup/preflight only and does not claim full
  task-loop execution support.
- Existing Claude task-loop files are not modified.
