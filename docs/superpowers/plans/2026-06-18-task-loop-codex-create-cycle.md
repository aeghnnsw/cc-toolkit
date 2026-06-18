# Task-loop Codex Create-cycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Codex `task-loop:create-cycle` skill that renders task-loop project scaffolding after `specify-aims`.

**Architecture:** Add one Codex-specific skill folder under `task-loop/codex-skills/` with bundled assets. Reuse the Claude output contract, rewrite the process for Codex, and update only Codex-facing metadata and setup copy.

**Tech Stack:** Markdown skills, YAML frontmatter, Codex plugin manifest JSON, `quick_validate.py`, `jq`, `rg`.

## Global Constraints

- Codex-facing task-loop files must not mention `discuss-with-codex`, `CLAUDE_PLUGIN_ROOT`, `Agent Teams`, `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`, `TodoWrite`, or `Workflow`.
- `task-loop/.codex-plugin/plugin.json` must keep `"skills": "./codex-skills/"`.
- Top-level `task-loop/skills/` must remain absent.
- `run-cycle` and a Codex cycle-worker remain pending and must not be declared supported.
- The generated `task-loop.md` must explicitly say Codex `run-cycle` and worker execution are pending.
- The generated `task-loop.md` must inline the study-log/PR contract instead of referencing
  plugin-local reference files.
- Validation must cover the skill wrapper, bundled assets, and a representative rendered fixture.
- PR text must be concise, accurate, and attribution-free.

---

### Task 1: Add Codex Create-cycle Skill

**Files:**
- Create: `task-loop/codex-skills/create-cycle/SKILL.md`
- Create: `task-loop/codex-skills/create-cycle/assets/task-loop-skeleton.md`
- Create: `task-loop/codex-skills/create-cycle/assets/directions-template.md`

**Interfaces:**
- Consumes: `docs/task-loop/proposal.md`, existing Codex skill discovery via `task-loop/.codex-plugin/plugin.json`.
- Produces: a discoverable `task-loop:create-cycle` skill and its bundled output templates.

- [ ] **Step 1: Confirm baseline**

Run:

```bash
test ! -e task-loop/codex-skills/create-cycle/SKILL.md
jq -e '.skills == "./codex-skills/"' task-loop/.codex-plugin/plugin.json
test ! -e task-loop/skills
```

Expected: all commands exit 0.

- [ ] **Step 2: Create the skill directory and assets**

Create:

```text
task-loop/codex-skills/create-cycle/
task-loop/codex-skills/create-cycle/assets/
```

Expected: the new directory contains only the `SKILL.md` and `assets/` files named in this plan.

- [ ] **Step 3: Write `SKILL.md`**

Write `task-loop/codex-skills/create-cycle/SKILL.md` with:

- frontmatter `name: create-cycle`;
- a concise `description` that starts with `Use when`;
- required proposal check;
- repo detection before questions;
- `dev-skills:pressure-test` as the review dependency;
- exact outputs and rendering rules;
- `.gitignore` and log scaffold steps;
- explicit note that `run-cycle` remains pending.

Expected: the skill is concise and contains no Claude-only terms from the global constraints.

- [ ] **Step 4: Write `assets/task-loop-skeleton.md`**

Write a Codex-specific skeleton with placeholders:

```text
{{GOAL}}
{{SOURCE_DOCS}}
{{CONTRACTS}}
{{TEST_CONVENTIONS}}
{{COMPUTE_POLICY}}
{{DEFAULT_BRANCH}}
{{BRANCH_PREFIXES}}
{{BOOTSTRAP_NOTE}}
```

Expected: the skeleton instructs future workers to use Codex-compatible skills, states that Codex
`run-cycle` and worker execution are pending, ends each future worker task at an open PR, and inlines
the required study-log sections and PR body shape.

- [ ] **Step 5: Write `assets/directions-template.md`**

Write the steering-file template with:

- newest direction at the top;
- standing direction and acted-on log sections;
- conflict handling through `dev-skills:pressure-test`;
- no Claude-only terms.

Expected: the template can be copied directly to `docs/task-loop/directions.md`.

### Task 2: Update Codex Metadata and Setup Copy

**Files:**
- Modify: `task-loop/.codex-plugin/plugin.json`
- Modify: `task-loop/codex-skills/setup/SKILL.md`

**Interfaces:**
- Consumes: existing Codex manifest and setup text.
- Produces: marketplace/discovery copy that accurately says setup, specify-aims, and create-cycle are supported.

- [ ] **Step 1: Update setup support wording**

In `task-loop/codex-skills/setup/SKILL.md`:

- add `create-cycle` to supported Codex workflow steps;
- leave only `run-cycle` as pending;
- keep the required skills list unchanged unless create-cycle needs a listed skill that is missing.

Expected: setup no longer says create-cycle is pending.

- [ ] **Step 2: Update plugin manifest**

In `task-loop/.codex-plugin/plugin.json`:

- add `create-cycle`, `cycle`, and `scaffold` keywords;
- update `description`, `shortDescription`, and `longDescription` to include create-cycle;
- keep `run-cycle` pending;
- add a default prompt for creating the task-loop cycle;
- make at least one default prompt explicitly about `create-cycle`, `create cycle`, or scaffolding;
- do not add default prompts, description text, short-description text, or long-description text that
  advertises autonomous running, orchestration, execution, or run-cycle support.

Expected: `jq . task-loop/.codex-plugin/plugin.json` succeeds and `"skills"` remains `./codex-skills/`.

### Task 3: Validate and Commit

**Files:**
- Validate all files changed by Tasks 1 and 2.
- Commit all issue #154 changes.

**Interfaces:**
- Consumes: skill folders and manifest.
- Produces: a pushed branch and PR.

- [ ] **Step 1: Run skill validation**

Run:

```bash
uv run --with pyyaml python /Users/steven/.codex/skills/.system/skill-creator/scripts/quick_validate.py task-loop/codex-skills/create-cycle
uv run --with pyyaml python /Users/steven/.codex/skills/.system/skill-creator/scripts/quick_validate.py task-loop/codex-skills/specify-aims
uv run --with pyyaml python /Users/steven/.codex/skills/.system/skill-creator/scripts/quick_validate.py task-loop/codex-skills/setup
```

Expected: each command exits 0.

- [ ] **Step 2: Run manifest and discovery validation**

Run:

```bash
jq . task-loop/.codex-plugin/plugin.json
jq -e '(.description | contains("create-cycle")) and (.keywords | index("create-cycle")) and (.interface.defaultPrompt | any(test("create-cycle|create cycle|scaffold"; "i"))) and (.interface.defaultPrompt | all(test("run-cycle|run cycle|run the task loop|autonomous|orchestrator|execute|execution|drive"; "i") | not)) and ((.description + " " + .interface.shortDescription) | test("run-cycle|autonomous|orchestrator|execute|execution|drive"; "i") | not) and (.interface.longDescription | contains("create-cycle") and contains("run-cycle") and contains("pending")) and (.interface.longDescription | test("autonomous|orchestrator|execute|execution|drive"; "i") | not)' task-loop/.codex-plugin/plugin.json
rg -qF 'setup, preflight, `specify-aims`, and `create-cycle`' task-loop/codex-skills/setup/SKILL.md
rg -qF '`run-cycle`' task-loop/codex-skills/setup/SKILL.md
rg -qF 'pending' task-loop/codex-skills/setup/SKILL.md
find task-loop/codex-skills -mindepth 2 -maxdepth 2 -name SKILL.md | sort
test ! -e task-loop/skills
```

Expected: JSON validates, metadata includes create-cycle, default prompts positively advertise
create-cycle/scaffolding, description and prompt surfaces do not advertise runner execution, long
description names create-cycle and leaves run-cycle pending without runner execution language, setup
wording says only run-cycle is pending, skill list includes create-cycle/setup/specify-aims, and no
top-level `skills/` directory exists.

- [ ] **Step 3: Run forbidden-term, rendered-fixture, and diff checks**

Run:

```bash
! rg -n 'discuss-with-codex|CLAUDE_PLUGIN_ROOT|Agent Teams|CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS|TodoWrite|Workflow' task-loop/codex-skills
tmp="$(mktemp -d)"
cp task-loop/codex-skills/create-cycle/assets/task-loop-skeleton.md "$tmp/task-loop.md"
perl -0pi -e 's/\{\{GOAL\}\}/Ship the documented task-loop goal/g; s/\{\{SOURCE_DOCS\}\}/README.md/g; s/\{\{CONTRACTS\}\}/Preserve public CLI behavior/g; s/\{\{TEST_CONVENTIONS\}\}/Run quick validation and JSON checks/g; s/\{\{COMPUTE_POLICY\}\}/Use local CPU only/g; s/\{\{DEFAULT_BRANCH\}\}/master/g; s/\{\{BRANCH_PREFIXES\}\}/feat-, bugfix-, doc-, refactor-, chore-, test-/g; s/\{\{BOOTSTRAP_NOTE\}\}/n\/a/g' "$tmp/task-loop.md"
! rg -n '\{\{[A-Z_]+\}\}|discuss-with-codex|CLAUDE_PLUGIN_ROOT|Agent Teams|CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS|TodoWrite|Workflow' "$tmp/task-loop.md"
for s in '**Outcome:**' '### Rubric' '### Evidence' '### Findings' 'Refs #<issue>' 'Study log: docs/task-loop/logs/<NNN>_<task>.md'; do
  rg -qF "$s" "$tmp/task-loop.md"
done
git diff --check
```

Expected: all commands exit 0. The rendered fixture proves the emitted contract has no leftover
placeholders or Claude-only terms and includes the durable study-log/PR contract.

- [ ] **Step 4: Commit**

Run:

```bash
git add docs/superpowers/specs/2026-06-18-task-loop-codex-create-cycle-design.md docs/superpowers/plans/2026-06-18-task-loop-codex-create-cycle.md task-loop/.codex-plugin/plugin.json task-loop/codex-skills/setup/SKILL.md task-loop/codex-skills/create-cycle
git commit -m "Add Codex task-loop create-cycle skill"
```

Expected: one attribution-free commit.

- [ ] **Step 5: Push and create PR**

Run:

```bash
git push -u origin feat-154-codex-create-cycle
gh pr create --title "Add Codex task-loop create-cycle support" --body "Adds Codex create-cycle support for task-loop scaffolding after specify-aims.\n\nRefs #154"
```

Expected: a PR is created and the session stops before merge.

## Self-Review

- **Spec coverage:** Tasks add the skill, assets, metadata, setup copy, inlined output contract,
  output-level validation, commit, push, and PR.
- **Placeholder scan:** The plan contains no TODO/TBD placeholders. The skeleton placeholders are intentional bundled template variables.
- **Type consistency:** Paths match the existing `task-loop/codex-skills/` layout and manifest discovery path.
