# Task-loop Codex Create-cycle Design

## Goal

Add Codex support for the next task-loop workflow step: `task-loop:create-cycle`.
The skill must turn an existing `docs/task-loop/proposal.md` into durable project scaffolding for
later task execution, while keeping `run-cycle` and worker dispatch out of scope.

## Current State

Task-loop now separates runtime-specific skills:

- Claude skills live in `task-loop/claude-skills/`.
- Codex skills live in `task-loop/codex-skills/`.
- Codex currently exposes `setup` and `specify-aims`.

The Claude `create-cycle` skill already defines the durable outputs:

- `docs/task-loop/task-loop.md`
- `docs/task-loop/directions.md`
- `docs/task-loop/logs/.gitkeep`
- a `.gitignore` entry for `goal-rubric-*.md`

That source cannot be copied directly for Codex because it references Claude-only execution
mechanics (`TodoWrite`, Agent Teams, `Workflow`, `${CLAUDE_PLUGIN_ROOT}`) and
`dev-skills:discuss-with-codex`.

## Design

Create `task-loop/codex-skills/create-cycle/` with:

- `SKILL.md`
- `assets/task-loop-skeleton.md`
- `assets/directions-template.md`

The Codex skill keeps the same output contract as Claude create-cycle, but renders a Codex-facing
cycle file:

- Use `dev-skills:pressure-test` for ambiguous project parameters, rubric review, plan review, and
  PR review guidance.
- Describe the worker as a future Codex runner/worker model instead of declaring current
  `run-cycle` support.
- Keep the generated `task-loop.md` self-contained and durable so a later Codex runner can consume
  it without reopening the plugin source.
- State in the generated file that Codex `run-cycle` and worker support are pending, so the file is a
  prepared contract rather than a runnable Codex loop today.
- Inline the study-log and PR body contract from `task-loop/references/pr-findings.md` instead of
  referencing a plugin-local file that target projects do not have.
- Avoid Claude-only terms in every Codex-facing skill file and asset.

The skill remains instruction-only. It does not need a script because the rendered output depends on
repo-specific judgment: source docs, correctness contracts, test conventions, branch rules, and
compute policy.

## Scope

In scope:

- Add a discoverable Codex `create-cycle` skill.
- Add Codex-specific create-cycle assets.
- Validate the emitted contract, not only the skill wrapper.
- Instruct Codex to read `docs/task-loop/proposal.md` first and stop if it is missing.
- Instruct Codex to detect repo facts before asking for project-specific parameters.
- Render all `{{...}}` placeholders before writing `docs/task-loop/task-loop.md`.
- Scaffold `docs/task-loop/directions.md`, `docs/task-loop/logs/.gitkeep`, and `.gitignore`.
- Include the worker study-log contract directly in the rendered skeleton: `Outcome`, `Rubric`,
  `Evidence`, `Findings`, `Refs #<issue>`, and
  `Study log: docs/task-loop/logs/<NNN>_<task>.md`.
- Update Codex setup wording and plugin metadata to include create-cycle support.
- Validate skill frontmatter, manifest JSON, discovery layout, placeholder handling, and forbidden
  Claude-only terms.

Out of scope:

- Implement Codex `run-cycle`.
- Implement or declare a Codex cycle-worker agent.
- Modify Claude skill behavior.
- Rework Supabase CLI behavior.
- Make task-loop discoverable as a fully ready Codex workflow beyond the implemented slices.

## Skill Behavior

The skill should:

1. Confirm `docs/task-loop/proposal.md` exists. If missing, stop and direct the user to
   `task-loop:specify-aims`.
2. Read the proposal, repository docs, existing `docs/task-loop/` files, and user direction.
3. Detect the default branch, test command, branch naming constraints, git hooks, code skeleton state,
   and compute environment.
4. Ask only for unresolved project-specific parameters unless the user requested no questions.
   When no questions are allowed, choose conservative defaults, record assumptions, and pressure-test
   the final parameter set.
5. Use `dev-skills:pressure-test` for ambiguous project parameters and before final rendering.
6. Copy the bundled skeleton to `docs/task-loop/task-loop.md` and replace every `{{PLACEHOLDER}}`.
   Never leave raw placeholders in the rendered project file.
7. Copy the bundled directions template to `docs/task-loop/directions.md`.
8. Create `docs/task-loop/logs/.gitkeep`.
9. Add `goal-rubric-*.md` to `.gitignore` if it is not already present.
10. Commit and open a PR when the skill authors durable project state.

## Codex Skeleton Requirements

The bundled skeleton should preserve the cycle shape but use Codex-safe language:

- Anchor on `directions.md`, `proposal.md`, and project source docs.
- Require an isolated worktree before edits.
- Use `dev-skills:goal-rubric` for binary acceptance criteria.
- Use `dev-skills:pressure-test` for hard decisions, rubrics, plans, and PR review.
- Use `superpowers:brainstorming`, `superpowers:writing-plans`,
  `superpowers:test-driven-development`, and `superpowers:verification-before-completion`.
- End each task at an open PR; never merge from the worker cycle.
- Treat `failed` and `blocked` outcomes as evidence-backed last resorts.
- Keep long jobs backgrounded with explicit status and log checks.
- Avoid `discuss-with-codex`, `TodoWrite`, `Workflow`, Agent Teams, and Claude plugin variables.
- Include an explicit pending-support note: Codex `run-cycle` and worker execution are not implemented
  yet.
- Inline the PR handoff contract so a future runner does not need access to plugin reference files.

## Metadata Updates

Update `task-loop/.codex-plugin/plugin.json` so the installed Codex plugin advertises:

- setup and preflight;
- `specify-aims`;
- `create-cycle`;
- `run-cycle` still pending, and not as a default prompt or supported short description.

Update `task-loop/codex-skills/setup/SKILL.md` so setup readiness text lists create-cycle as
supported and only `run-cycle` as pending.

## Validation

Run:

```bash
uv run --with pyyaml python /Users/steven/.codex/skills/.system/skill-creator/scripts/quick_validate.py task-loop/codex-skills/create-cycle
uv run --with pyyaml python /Users/steven/.codex/skills/.system/skill-creator/scripts/quick_validate.py task-loop/codex-skills/specify-aims
uv run --with pyyaml python /Users/steven/.codex/skills/.system/skill-creator/scripts/quick_validate.py task-loop/codex-skills/setup
jq . task-loop/.codex-plugin/plugin.json
jq -e '(.description | contains("create-cycle")) and (.keywords | index("create-cycle")) and (.interface.defaultPrompt | any(test("create-cycle|create cycle|scaffold"; "i"))) and (.interface.defaultPrompt | all(test("run-cycle|run cycle|run the task loop|autonomous|orchestrator|execute|execution|drive"; "i") | not)) and ((.description + " " + .interface.shortDescription) | test("run-cycle|autonomous|orchestrator|execute|execution|drive"; "i") | not) and (.interface.longDescription | contains("create-cycle") and contains("run-cycle") and contains("pending")) and (.interface.longDescription | test("autonomous|orchestrator|execute|execution|drive"; "i") | not)' task-loop/.codex-plugin/plugin.json
rg -qF 'setup, preflight, `specify-aims`, and `create-cycle`' task-loop/codex-skills/setup/SKILL.md
rg -qF '`run-cycle`' task-loop/codex-skills/setup/SKILL.md
rg -qF 'pending' task-loop/codex-skills/setup/SKILL.md
find task-loop/codex-skills -mindepth 2 -maxdepth 2 -name SKILL.md | sort
rg -n 'discuss-with-codex|CLAUDE_PLUGIN_ROOT|Agent Teams|CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS|TodoWrite|Workflow' task-loop/codex-skills
rg -n '\{\{[A-Z_]+\}\}' docs/task-loop/task-loop.md
git diff --check
```

Expected:

- all quick validations pass;
- manifest JSON is valid and includes create-cycle metadata;
- manifest prompts positively advertise create-cycle/scaffolding, do not advertise runner execution,
  long description mentions create-cycle support and says `run-cycle` is pending without runner
  execution language;
- setup wording says setup, preflight, `specify-aims`, and `create-cycle` are supported while
  `run-cycle` is pending;
- the skill list includes setup, specify-aims, and create-cycle;
- the forbidden-term scan returns no matches for Codex-facing skill files or assets;
- a representative rendered `task-loop.md` fixture has no raw placeholders and no forbidden
  Claude-only terms;
- the rendered fixture contains every required study-log/PR contract string:
  `**Outcome:**`, `### Rubric`, `### Evidence`, `### Findings`, `Refs #<issue>`, and
  `Study log: docs/task-loop/logs/<NNN>_<task>.md`;
- `git diff --check` returns clean.
