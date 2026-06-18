# Task-loop Codex Specify-aims Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the Codex `task-loop:specify-aims` skill while keeping later task-loop steps pending.

**Architecture:** Add a Codex-specific skill folder under the existing `codex-skills/` tree. Reuse the proposal template contract from the Claude skill, but rewrite instructions for Codex and use `dev-skills:pressure-test` as the adversarial review step. Update only Codex setup wording so the installed plugin accurately reports supported Codex workflow steps.

**Tech Stack:** Markdown `SKILL.md`, YAML frontmatter, Codex plugin skill discovery, `quick_validate.py`, JSON manifest validation.

## Global Constraints

- Codex-facing task-loop skills must not mention `discuss-with-codex`, `CLAUDE_PLUGIN_ROOT`, `Agent Teams`, `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`, or `TodoWrite`.
- `task-loop/.codex-plugin/plugin.json` must continue to point `skills` at `./codex-skills/`.
- Top-level `task-loop/skills/` must remain absent.
- `create-cycle` and `run-cycle` remain pending Codex ports.

---

### Task 1: Add Codex Specify-aims Skill

**Files:**
- Create: `task-loop/codex-skills/specify-aims/SKILL.md`
- Create: `task-loop/codex-skills/specify-aims/assets/proposal-template.md`
- Modify: `task-loop/.codex-plugin/plugin.json`
- Modify: `task-loop/codex-skills/setup/SKILL.md`

**Interfaces:**
- Consumes: existing Codex plugin manifest `skills: "./codex-skills/"`.
- Produces: a discoverable `task-loop:specify-aims` skill and a bundled proposal template.

- [ ] **Step 1: Confirm baseline**

Run:

```bash
test ! -e task-loop/codex-skills/specify-aims/SKILL.md
jq -e '.skills == "./codex-skills/"' task-loop/.codex-plugin/plugin.json
test ! -e task-loop/skills
```

Expected: all commands exit 0.

- [ ] **Step 2: Create the skill directory and template asset**

Create `task-loop/codex-skills/specify-aims/assets/`.

Copy the content of `task-loop/claude-skills/specify-aims/assets/proposal-template.md` to:

```text
task-loop/codex-skills/specify-aims/assets/proposal-template.md
```

Expected: the template remains byte-for-byte compatible unless a Codex-only issue is found.

- [ ] **Step 3: Write `SKILL.md`**

Create `task-loop/codex-skills/specify-aims/SKILL.md` with:

```markdown
---
name: specify-aims
description: Use when starting a task-loop project in Codex, defining project aims and stages, initializing docs/task-loop/proposal.md, re-aiming a proposal before a run starts, or planning task-loop milestones and success criteria.
---

# Specify Aims

Author or re-aim the task-loop proposal for a Codex-run project. This is the first workflow step after setup. It creates or updates `docs/task-loop/proposal.md`; `create-cycle` and `run-cycle` remain separate pending Codex ports.

## Output

Write `docs/task-loop/proposal.md` with three zones from `assets/proposal-template.md`:

- **Specific Aims & Goal:** stable, human-gated aim, success criteria, constraints, and non-goals.
- **Implementation Plan:** dependency-ordered stages, rough acceptance, milestones, and falsifiable hypotheses.
- **Living Roadmap:** progress and hypothesis ledger. Leave this initialized for later orchestrator ownership.

The template frontmatter includes `incorporated_through: 0`. Preserve it for new proposals.

## Process

1. Read the repository docs, README, existing `docs/task-loop/` files, and the user's stated direction.
2. If `docs/task-loop/proposal.md` exists, gate any re-aim before editing:
   - Parse the proposal frontmatter and read `incorporated_through`.
   - If `incorporated_through` is exactly `0`, treat the proposal as pre-run.
   - If `incorporated_through` is greater than `0`, refuse to edit Specific Aims and direct the user to steering or stop-then-re-aim.
   - If `incorporated_through` is missing or not parseable, stop and require explicit user confirmation before editing Specific Aims.
   - Also check for `docs/task-loop/task-loop.md`, `docs/task-loop/directions.md`, and task-loop CLI status when available, but do not rely on those instead of the frontmatter marker.
3. Use `superpowers:brainstorming` to clarify the aim, success criteria, constraints, non-goals, stages, milestones, and key hypotheses. Ask only for information that cannot be inferred from the repo or the user's prompt.
4. Draft dependency-ordered stages. Each stage must name its goal, dependencies, rough acceptance, and at least one falsifiable hypothesis when a real assumption exists.
5. Use `dev-skills:pressure-test` on the aim, success criteria, and stage decomposition before writing the final proposal. The pressure-test packet must include the draft proposal, repo evidence used, assumptions, and decision boundary.
6. Create `docs/task-loop/` if needed. For a new project, copy `assets/proposal-template.md` to `docs/task-loop/proposal.md`; for a pre-run re-aim, edit the existing proposal in place.
7. Fill the proposal in current-truth prose. Do not leave angle-bracket placeholders. Keep Specific Aims stable and human-gated. Initialize progress as not started and all new hypotheses as `open`.
8. Commit the proposal on a branch and open a PR with concise, attribution-free text when the user asked this skill to author durable proposal state.

## Pressure-test Focus

Ask the critic to attack:

- whether success criteria are binary or checkable;
- whether stages are ordered by real dependency;
- whether the riskiest hypotheses appear early enough;
- whether anything in Specific Aims belongs in the Implementation Plan instead;
- whether constraints or non-goals are missing enough to make later task selection unsafe.
```

- [ ] **Step 4: Update setup wording**

In `task-loop/codex-skills/setup/SKILL.md`, change the overview from setup/preflight-only to setup/preflight plus specify-aims support, and list only `create-cycle` and `run-cycle` as pending Codex ports.

- [ ] **Step 5: Update Codex plugin metadata**

In `task-loop/.codex-plugin/plugin.json`:

- change `description` so it names setup, preflight, and specify-aims proposal support;
- add keywords `specify-aims`, `proposal`, `aims`, and `planning`;
- change `interface.shortDescription` so it is not setup-only;
- change `interface.longDescription` so it says setup/preflight and specify-aims are supported, while `create-cycle` and `run-cycle` remain pending;
- add a default prompt such as `Specify aims for this task-loop project.`

- [ ] **Step 6: Validate**

Run:

```bash
uv run --with pyyaml python /Users/steven/.codex/skills/.system/skill-creator/scripts/quick_validate.py task-loop/codex-skills/specify-aims
uv run --with pyyaml python /Users/steven/.codex/skills/.system/skill-creator/scripts/quick_validate.py task-loop/codex-skills/setup
jq . task-loop/.codex-plugin/plugin.json
jq -e '(.description | contains("setup")) and (.description | contains("specify-aims")) and (.keywords | index("specify-aims"))' task-loop/.codex-plugin/plugin.json
rg -q "incorporated_through" task-loop/codex-skills/specify-aims/SKILL.md
python - <<'PY'
from pathlib import Path
forbidden = ("discuss-with-codex", "CLAUDE_PLUGIN_ROOT", "Agent Teams", "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", "TodoWrite")
for path in Path("task-loop/codex-skills").glob("*/SKILL.md"):
    text = path.read_text()
    bad = [term for term in forbidden if term in text]
    if bad:
        raise SystemExit(f"{path}: forbidden Codex-facing terms {bad}")
print("codex skill text OK")
PY
```

Expected: all commands exit 0 and the final script prints `codex skill text OK`.

- [ ] **Step 7: Commit**

Run:

```bash
git add task-loop/.codex-plugin/plugin.json task-loop/codex-skills/specify-aims task-loop/codex-skills/setup/SKILL.md
git commit -m "Add Codex task-loop specify-aims skill"
```

## Self-Review

- **Spec coverage:** The task creates the new Codex skill, copies the template, replaces `discuss-with-codex` with `pressure-test`, adds an operational `incorporated_through` re-aim guard, updates setup wording and plugin metadata, and validates Codex-facing terms.
- **Placeholder scan:** The proposed skill text contains no TODO/TBD placeholders. The proposal template intentionally contains user-fillable angle-bracket placeholders because it is an output scaffold.
- **Type consistency:** File paths and skill names match the existing `codex-skills/` layout and manifest.
