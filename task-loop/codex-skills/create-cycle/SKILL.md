---
name: create-cycle
description: Use when a Codex task-loop project has docs/task-loop/proposal.md and needs create-cycle scaffolding, generated task-loop instructions, docs/task-loop/task-loop.md, directions.md, logs/.gitkeep, or goal-rubric scratch ignore setup.
---

# Create Cycle

Render the per-project task-loop cycle after `specify-aims`. This skill authors
durable scaffolding only. Codex `run-cycle` runs manual controller passes after
this file exists.

## Outputs

- `docs/task-loop/task-loop.md` from `assets/task-loop-skeleton.md`
- `docs/task-loop/directions.md` from `assets/directions-template.md`
- `docs/task-loop/logs/.gitkeep`
- `.gitignore` entry for `goal-rubric-*.md`

## Process

1. Confirm `docs/task-loop/proposal.md` exists. If missing, stop and direct the
   user to `task-loop:specify-aims`.
2. Read the proposal, repository README/docs, existing `docs/task-loop/` files,
   and the user's current direction.
3. Detect repo facts before asking:
   - default branch;
   - likely test command;
   - branch naming rules and git hooks;
   - whether a code skeleton already exists;
   - local compute constraints and available tools.
4. Resolve project parameters for the skeleton:
   - `{{GOAL}}` from the proposal's Specific Aims and success criteria;
  - `{{SOURCE_DOCS}}` from source-of-truth docs the worker should read;
   - `{{CONTRACTS}}` from correctness invariants;
   - `{{TEST_CONVENTIONS}}` from what counts as tested;
   - `{{COMPUTE_POLICY}}` from local/host constraints;
   - `{{DEFAULT_BRANCH}}`;
   - `{{BRANCH_PREFIXES}}`;
   - `{{BOOTSTRAP_NOTE}}`.
5. Ask only for unresolved parameters unless the user asked for no questions. If
   questions are disallowed, choose conservative defaults and record assumptions.
6. Use `dev-skills:pressure-test` on ambiguous parameters and the final parameter
   set before rendering. Include proposal excerpts, detected repo evidence,
   assumptions, and the decision boundary in the pressure-test packet.
7. Copy the skeleton to `docs/task-loop/task-loop.md` and replace every
   `{{PLACEHOLDER}}`. Never leave raw placeholders in the rendered project file.
8. Copy the directions template, create `docs/task-loop/logs/.gitkeep`, and add
   `goal-rubric-*.md` to `.gitignore` if absent.
9. Commit and open a concise PR when this skill authors durable project files.

## Rendering Rules

- Keep the cycle steps and general rules intact unless repo facts make a line
  objectively wrong.
- Use `n/a` for parameters that do not apply.
- Keep the Codex run-cycle support note in the rendered `task-loop.md`.
- Keep the inlined study-log and PR contract in the rendered `task-loop.md`.

## Pressure-test Focus

Ask the critic to attack:

- whether the generated cycle overstates current Codex support;
- whether source docs, contracts, or test conventions are too vague for later
  task selection;
- whether compute policy or branch rules could cause unsafe worker behavior;
- whether the rendered file is self-contained for the Codex runner.
