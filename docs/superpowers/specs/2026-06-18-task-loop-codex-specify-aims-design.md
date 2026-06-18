# Task-loop Codex Specify-aims Design

## Goal

Add Codex support for the first task-loop workflow step after setup: `task-loop:specify-aims`.
The skill must let Codex author or re-aim `docs/task-loop/proposal.md` while keeping `create-cycle`
and `run-cycle` out of scope.

## Current State

`task-loop` now separates runtime-specific skills:

- Claude skills live in `task-loop/claude-skills/`.
- Codex skills live in `task-loop/codex-skills/`.
- There is no top-level `task-loop/skills/` directory.

Codex currently exposes only `task-loop:setup`. The Claude `specify-aims` skill already defines the
proposal shape and process, but it depends on `dev-skills:discuss-with-codex`, which is a
Claude-to-Codex workflow and is not the right Codex dependency.

## Design

Create `task-loop/codex-skills/specify-aims/SKILL.md` and copy the existing proposal template asset
to `task-loop/codex-skills/specify-aims/assets/proposal-template.md`.

The Codex skill keeps the same output contract as Claude:

- `docs/task-loop/proposal.md`
- Specific Aims & Goal
- Implementation Plan
- Living Roadmap
- `incorporated_through` frontmatter marker

The Codex skill changes the deliberation dependency:

- Use `superpowers:brainstorming` to shape the aim with the user.
- Use `dev-skills:pressure-test` to challenge the aim, success criteria, and stage decomposition.
- Do not mention or invoke `dev-skills:discuss-with-codex`.

The skill should be instruction-only. No scripts are needed for this slice because authoring the
proposal is a judgment-heavy workflow, not a deterministic transform.

## Scope

In scope:

- Add Codex `specify-aims` skill and template asset.
- Update Codex plugin metadata so marketplace text no longer describes the plugin as setup-only.
- Add `specify-aims`, proposal, aims, and planning discovery terms to Codex plugin metadata.
- Update Codex setup wording so support is no longer described as setup/preflight only.
- Update Codex setup pending-port text to list only `create-cycle` and `run-cycle`.
- Validate the new skill and guard against Claude-only terms in Codex-facing files.

Out of scope:

- Codex `create-cycle`.
- Codex `run-cycle`.
- Codex worker/subagent execution model.
- Reworking Claude skills or shared task-loop documentation.

## Skill Behavior

The skill should:

1. Confirm the repository state and read relevant project docs.
2. If `docs/task-loop/proposal.md` exists, parse its frontmatter before editing.
   `incorporated_through: 0` is the only automatic pre-run re-aim state.
   `incorporated_through > 0` refuses Specific Aims edits and directs the user
   to steering or stop-then-re-aim. Missing or unparseable frontmatter requires
   explicit user confirmation before editing Specific Aims.
3. Collaboratively clarify the goal, success criteria, constraints, non-goals, stages, and milestones.
4. Decompose the work into dependency-ordered stages with falsifiable hypotheses.
5. Pressure-test the aim and stage decomposition with `dev-skills:pressure-test`.
6. Write or update `docs/task-loop/proposal.md` using the bundled template.
7. Keep the Specific Aims stable and human-gated once a run starts.
8. Commit and open a PR when the skill is used to author durable proposal state.

## Validation

Run:

```bash
uv run --with pyyaml python /Users/steven/.codex/skills/.system/skill-creator/scripts/quick_validate.py task-loop/codex-skills/specify-aims
uv run --with pyyaml python /Users/steven/.codex/skills/.system/skill-creator/scripts/quick_validate.py task-loop/codex-skills/setup
jq . task-loop/.codex-plugin/plugin.json
jq -e '(.description | contains("setup")) and (.description | contains("specify-aims")) and (.keywords | index("specify-aims"))' task-loop/.codex-plugin/plugin.json
```

Also verify:

- `task-loop/codex-skills/specify-aims/SKILL.md` exists.
- The Codex skill tree includes `setup` and `specify-aims`.
- Codex-facing task-loop skill files do not contain `discuss-with-codex`,
  `CLAUDE_PLUGIN_ROOT`, `Agent Teams`, `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`, or `TodoWrite`.
- `task-loop/codex-skills/specify-aims/SKILL.md` contains an explicit `incorporated_through`
  re-aim guard.
