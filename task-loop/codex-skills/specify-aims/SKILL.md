---
name: specify-aims
description: Use when starting a task-loop project in Codex, defining project aims and stages, initializing docs/task-loop/proposal.md, re-aiming a proposal before a run starts, or planning task-loop milestones and success criteria.
---

# Specify Aims

Author or re-aim the task-loop proposal for a Codex-run project. This is the
first workflow step after setup. It creates or updates
`docs/task-loop/proposal.md`; `create-cycle` and `run-cycle` remain separate
Codex steps.

## Output

Write `docs/task-loop/proposal.md` with three zones from
`assets/proposal-template.md`:

- **Specific Aims & Goal:** stable, human-gated aim, success criteria,
  constraints, and non-goals.
- **Implementation Plan:** dependency-ordered stages, rough acceptance,
  milestones, and falsifiable hypotheses.
- **Living Roadmap:** progress and hypothesis ledger. Leave this initialized
  for later orchestrator ownership.

The template frontmatter includes `incorporated_through: 0`. Preserve it for new
proposals.

## Process

1. Read the repository docs, README, existing `docs/task-loop/` files, and the
   user's stated direction.
2. If `docs/task-loop/proposal.md` exists, gate any re-aim before editing:
   - Parse the proposal frontmatter and read `incorporated_through`.
   - If `incorporated_through` is exactly `0`, treat the proposal as pre-run.
   - If `incorporated_through` is greater than `0`, refuse to edit Specific
     Aims and direct the user to steering or stop-then-re-aim.
   - If `incorporated_through` is missing or not parseable, stop and require
     explicit user confirmation before editing Specific Aims.
   - Also check for `docs/task-loop/task-loop.md`, `docs/task-loop/directions.md`,
     and task-loop CLI status when available, but do not rely on those instead
     of the frontmatter marker.
3. Use `superpowers:brainstorming` to clarify the aim, success criteria,
   constraints, non-goals, stages, milestones, and key hypotheses. Ask only for
   information that cannot be inferred from the repo or the user's prompt.
4. Draft dependency-ordered stages. Each stage must name its goal,
   dependencies, rough acceptance, and at least one falsifiable hypothesis when
   a real assumption exists.
5. Use `dev-skills:pressure-test` on the aim, success criteria, and stage
   decomposition before writing the final proposal. The pressure-test packet
   must include the draft proposal, repo evidence used, assumptions, and
   decision boundary.
6. Create `docs/task-loop/` if needed. For a new project, copy
   `assets/proposal-template.md` to `docs/task-loop/proposal.md`; for a pre-run
   re-aim, edit the existing proposal in place.
7. Fill the proposal in current-truth prose. Do not leave angle-bracket
   placeholders. Keep Specific Aims stable and human-gated. Initialize progress
   as not started and all new hypotheses as `open`.
8. Commit the proposal on a branch and open a PR with concise,
   attribution-free text when the user asked this skill to author durable
   proposal state.

## Pressure-test Focus

Ask the critic to attack:

- whether success criteria are binary or checkable;
- whether stages are ordered by real dependency;
- whether the riskiest hypotheses appear early enough;
- whether anything in Specific Aims belongs in the Implementation Plan instead;
- whether constraints or non-goals are missing enough to make later task
  selection unsafe.
