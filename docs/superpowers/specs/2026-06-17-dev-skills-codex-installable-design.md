# Design - Codex-installable dev-skills

## Goal

Make the `dev-skills` plugin installable by Codex for issue #141, while exposing
only the two skills that are in scope for the first Codex pass:

- `goal-rubric`
- `doc-update`

The Claude-facing plugin remains unchanged. Codex gets a separate skill tree so
Claude-specific instructions do not leak into Codex.

## Context

`dev-skills` currently has a Claude plugin manifest at
`dev-skills/.claude-plugin/plugin.json` and a shared `skills/` directory. Some
skills are already mostly runtime-neutral, while others mention Claude-only
capabilities or workflows such as Claude Code review behavior, `TodoWrite`, and
Claude-driven adversarial use of Codex.

Codex plugin packaging uses a separate `.codex-plugin/plugin.json` manifest. The
manifest can point `skills` at a folder, and Codex auto-discovers each child
directory that contains a `SKILL.md`.

## Scope

In scope:

- Add `dev-skills/.codex-plugin/plugin.json`.
- Add `dev-skills/codex-skills/goal-rubric/SKILL.md`.
- Add `dev-skills/codex-skills/doc-update/SKILL.md`.
- Point the Codex manifest at `./codex-skills/`.
- Add `dev-skills` to `.agents/plugins/marketplace.json`.
- Validate JSON and Codex plugin structure.

Out of scope:

- Porting `discuss-with-codex`.
- Porting `pr-feedback`, `project-eval`, `problem-solving-cycle`,
  `step-workflow`, or `discord-setup`.
- Adding placeholder or disabled Codex skills for unsupported entries.
- Declaring `task-loop` as Codex-discoverable.

## Design

Use a separate Codex skill folder:

```text
dev-skills/
|-- .claude-plugin/
|   `-- plugin.json
|-- .codex-plugin/
|   `-- plugin.json
|-- skills/
|   `-- ...
`-- codex-skills/
    |-- goal-rubric/
    |   `-- SKILL.md
    `-- doc-update/
        `-- SKILL.md
```

The Codex manifest declares the same plugin identity as the Claude plugin and
sets:

```json
{
  "skills": "./codex-skills/"
}
```

The repo-level Codex marketplace gains a `dev-skills` entry with local source
path `./dev-skills`, `AVAILABLE` installation policy, `ON_INSTALL`
authentication policy, and `Developer Tools` category.

## Skill Porting Rules

`goal-rubric` keeps its current behavior: inspect the repo read-only, draft a
binary `/goal` rubric, ask only about gaps, save the rubric file, and render the
condition for the target tool. The Codex version should default naturally to
Codex phrasing when the target is ambiguous, while still allowing the user to ask
for a Claude-formatted condition.

`doc-update` keeps its current behavior: update existing documentation to current
truth, remove backward narrative from main docs, record substantive history in a
central `CHANGELOG.md`, and audit the result against the documentation quality
rubric before reporting completion.

Both Codex skills should use Codex-oriented wording and avoid Claude-only tool
names or assumptions. They should remain instruction-only unless a later issue
proves a script is needed.

## Compatibility

This change passes only part of the `task-loop` prerequisite set. After this
issue:

- `goal-rubric` is Codex-installable.
- `doc-update` is Codex-installable.
- `discuss-with-codex` remains a pending prerequisite for Codex task-loop
  support.

That is intentional. Unsupported `dev-skills` entries stay invisible to Codex
instead of being partially exposed.

## Validation

Validation should include:

- `jq . dev-skills/.codex-plugin/plugin.json`
- `jq . .agents/plugins/marketplace.json`
- Codex plugin validation for `dev-skills`
- A file discovery check confirming only `goal-rubric` and `doc-update` exist
  under `dev-skills/codex-skills/`

No application build or runtime test is expected for this repository.
