# Dev Skills Codex Installable Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `dev-skills` installable by Codex while exposing only the Codex ports of `goal-rubric` and `doc-update`.

**Architecture:** Keep Claude and Codex skill surfaces separate. Add a Codex manifest at `dev-skills/.codex-plugin/plugin.json`, add Codex-only skill files under `dev-skills/codex-skills/`, and advertise `dev-skills` from the repo Codex marketplace.

**Tech Stack:** JSON plugin manifests, Markdown `SKILL.md` files with YAML frontmatter, `jq`, shell validation, Codex CLI 0.140.0.

## Global Constraints

- Work on branch `feat-141-codex-dev-skills` for issue #141.
- Do not modify the existing Claude skill files under `dev-skills/skills/`.
- Expose only `goal-rubric` and `doc-update` to Codex in this issue.
- Do not port `discuss-with-codex`, `pr-feedback`, `project-eval`, `problem-solving-cycle`, `step-workflow`, or `discord-setup`.
- Do not declare `task-loop` as Codex-discoverable in this issue.
- Use `.codex-plugin/plugin.json`, not `.codex_plugin/plugin.json`.
- Use `dev-skills/codex-skills/` as the Codex skill root and declare it with `"skills": "./codex-skills/"`.
- Keep issue, commit, and PR text free of Codex attribution boilerplate.
- Do not include a test plan section in the PR body.

---

## File Structure

- Create `dev-skills/.codex-plugin/plugin.json`: Codex plugin manifest for `dev-skills`.
- Create `dev-skills/codex-skills/goal-rubric/SKILL.md`: Codex-facing goal rubric skill.
- Create `dev-skills/codex-skills/doc-update/SKILL.md`: Codex-facing documentation update skill.
- Modify `.agents/plugins/marketplace.json`: add `dev-skills` as a local `Developer Tools` plugin.

No scripts or assets are added.

### Task 1: Red Checks For Missing Codex Support

**Files:**
- Inspect: `dev-skills/.codex-plugin/plugin.json`
- Inspect: `dev-skills/codex-skills/`
- Inspect: `.agents/plugins/marketplace.json`

**Interfaces:**
- Consumes: current worktree state.
- Produces: failing checks that prove the requested support is currently absent.

- [ ] **Step 1: Verify the Codex manifest is absent**

Run:

```bash
test ! -f dev-skills/.codex-plugin/plugin.json
```

Expected: exits `0`.

- [ ] **Step 2: Verify the Codex skill root is absent**

Run:

```bash
test ! -d dev-skills/codex-skills
```

Expected: exits `0`.

- [ ] **Step 3: Verify the Codex marketplace does not expose dev-skills**

Run:

```bash
! jq -e '.plugins[] | select(.name == "dev-skills")' .agents/plugins/marketplace.json >/dev/null
```

Expected: exits `0`.

### Task 2: Add Codex Plugin Wiring

**Files:**
- Create: `dev-skills/.codex-plugin/plugin.json`
- Modify: `.agents/plugins/marketplace.json`

**Interfaces:**
- Consumes: approved design at `docs/superpowers/specs/2026-06-17-dev-skills-codex-installable-design.md`.
- Produces: a Codex plugin manifest and marketplace entry pointing at `./dev-skills`.

- [ ] **Step 1: Create `dev-skills/.codex-plugin/plugin.json`**

Create this exact JSON:

```json
{
  "name": "dev-skills",
  "version": "1.0.0",
  "description": "Development workflow skills for Codex.",
  "author": {
    "name": "Steven",
    "email": "aeghnnsw@users.noreply.github.com"
  },
  "repository": "https://github.com/aeghnnsw/cc-toolkit",
  "license": "MIT",
  "keywords": [
    "development",
    "documentation",
    "goal",
    "rubric",
    "workflow"
  ],
  "skills": "./codex-skills/",
  "interface": {
    "displayName": "Dev Skills",
    "shortDescription": "Codex-ready development workflow skills.",
    "longDescription": "Use Dev Skills for selected development workflows, including measurable goal rubrics and current-truth documentation updates.",
    "developerName": "Steven",
    "category": "Developer Tools",
    "capabilities": [
      "Read",
      "Write"
    ],
    "defaultPrompt": [
      "Draft a measurable /goal rubric.",
      "Update existing documentation to current truth."
    ]
  }
}
```

- [ ] **Step 2: Add `dev-skills` to `.agents/plugins/marketplace.json`**

Append this object after the existing `core-hooks` entry:

```json
{
  "name": "dev-skills",
  "source": {
    "source": "local",
    "path": "./dev-skills"
  },
  "policy": {
    "installation": "AVAILABLE",
    "authentication": "ON_INSTALL"
  },
  "category": "Developer Tools"
}
```

- [ ] **Step 3: Verify JSON syntax and key manifest fields**

Run:

```bash
jq -e '.name == "dev-skills" and .skills == "./codex-skills/"' dev-skills/.codex-plugin/plugin.json
jq -e '.plugins[] | select(.name == "dev-skills" and .source.path == "./dev-skills" and .category == "Developer Tools")' .agents/plugins/marketplace.json
```

Expected: both commands exit `0`.

### Task 3: Add Codex Goal Rubric Skill

**Files:**
- Create: `dev-skills/codex-skills/goal-rubric/SKILL.md`

**Interfaces:**
- Consumes: `dev-skills/skills/goal-rubric/SKILL.md`.
- Produces: a Codex-facing skill with the same core behavior and no Claude-only default.

- [ ] **Step 1: Create `dev-skills/codex-skills/goal-rubric/SKILL.md`**

Use this content:

```markdown
---
name: goal-rubric
description: Use when the user wants a measurable /goal rubric, success criteria, acceptance criteria, or completion condition, or when a /goal loop will not close because the criteria are not observable or binary.
---

# Goal Rubric

Turn a short goal into a binary rubric that a `/goal` grader can check, then render it as a ready-to-paste completion condition.

## Core Principle

A `/goal` loop closes only when the completion condition is observable and binary. Write criteria the working agent can prove in its own output and a small grader model can judge without running commands or reading files.

## Grader Constraints

- Transcript-only: the grader sees what the agent surfaced in the conversation. It does not run commands or inspect files.
- Small-model judgeable: each criterion must be atomic, concrete, and unambiguous.
- Binary AND: the goal is complete only when every criterion passes.

## Workflow

1. Get the goal from the user.
2. Inspect the repo read-only to identify test, build, lint, file layout, and artifact checks that can prove completion.
3. Draft independent pass/fail criteria. Each criterion must include an end state, a transcript-observable check, and any relevant guardrail.
4. Ask only about gaps that repo inspection cannot settle, such as the validating command, protected files, or turn/time cap.
5. Save the rubric to `./goal-rubric-slug.md`, replacing `slug` with a short goal-derived filename segment unless the user gives another path.
6. Render the `/goal` condition for Codex by default. If the user asks for another tool, use that tool's framing.

## Rubric Shape

```markdown
# Goal rubric: short goal statement

## Criteria (all must pass)
1. Criterion name - End state: observable signal. Check: how it is proven in the transcript. Constraint: what must not change.

## Stop clause
Turn or time cap.

## /goal condition (Codex)
Codex condition string.
```

## Codex Condition Framing

For Codex, phrase the condition with four parts:

- What to achieve.
- What not to change.
- How to validate it.
- When to stop.

Keep the condition direct enough for a small grader to answer yes or no from the transcript.

## Self-Check

Before finishing, verify:

- Every criterion names a measurable end state.
- Every criterion states the check that proves it.
- Every proof can appear in the agent transcript.
- No criterion requires the grader to run a command or open a file.
- Criteria do not overlap.
- The rubric has a stop clause.
```

- [ ] **Step 2: Verify frontmatter and discovery**

Run:

```bash
test -f dev-skills/codex-skills/goal-rubric/SKILL.md
sed -n '1,12p' dev-skills/codex-skills/goal-rubric/SKILL.md
```

Expected: the file exists, starts with YAML frontmatter, and includes `name: goal-rubric` and a `description` beginning with `Use when`.

### Task 4: Add Codex Doc Update Skill

**Files:**
- Create: `dev-skills/codex-skills/doc-update/SKILL.md`

**Interfaces:**
- Consumes: `dev-skills/skills/doc-update/SKILL.md`.
- Produces: a Codex-facing documentation update skill with current-truth and changelog rules preserved.

- [ ] **Step 1: Create `dev-skills/codex-skills/doc-update/SKILL.md`**

Use this content:

```markdown
---
name: doc-update
description: Use when the user asks to update docs, refresh documentation, fix stale README content, audit documentation quality, remove outdated prose, or bring existing documentation in line with current project truth.
---

# Doc Update

Update existing documentation so it reflects the current project truth, then audit the result before finishing.

## Core Principle

Main documentation contains current truth only. Do not narrate backward history in instructions, README content, or conceptual docs. Put substantive history in a central `CHANGELOG.md`.

Forward-looking pointers are allowed when they describe current reality, such as "`oldFn` is deprecated; use `newFn`."

## When To Use

Use this skill to refresh, correct, clean up, or audit existing documentation. Do not use it to author brand-new documentation from scratch.

## Workflow

1. Locate target docs from the user's paths. If none are given, inspect standard docs: `README.md`, `docs/`, top-level Markdown files, and `SKILL.md` or `AGENTS.md` only when the request mentions skills, agents, or Codex configuration.
2. Read each target fully before editing.
3. Classify each doc by Diataxis type: tutorial, how-to guide, reference, or explanation.
4. Establish current truth from the user's new information and the codebase. Verify checkable claims such as commands, paths, APIs, configuration, and version numbers.
5. Apply safe updates in place: correct stale claims, remove backward narrative, deduplicate facts, improve clarity, make references self-contained, and trim filler.
6. Propose structural changes before applying them when the update would split, rename, move, or heavily reorganize docs.
7. Record substantive meaning changes under `## [Unreleased]` in a central `CHANGELOG.md`. Create the changelog if needed. Do not log wording-only edits.
8. Audit the updated docs against the quality gate below. Auto-fix safe residual issues once, then re-check.
9. Report files changed, changelog entry status, audit results, and any deferred structural changes or unverifiable claims.

## Quality Gate

Every updated doc must pass or have a clearly reported out-of-scope gap:

| # | Dimension | Pass check |
|---|---|---|
| 1 | Accuracy and currency | Every statement matches present reality; each fact has one canonical statement. |
| 2 | Type purity | The doc stays within its Diataxis type. |
| 3 | Findability and structure | Title and heading hierarchy are clear; each section has one job. |
| 4 | Self-containment | Sections make sense when read alone; references are explicit. |
| 5 | Clarity | Prose uses plain language, active voice, present tense, and defined terms. |
| 6 | Conciseness | Redundancy, filler, and marketing language are removed. |
| 7 | Completeness | Prerequisites, happy path, examples, and important edge cases are covered when in scope. |
| 8 | Consistency | Terminology, names, commands, and formatting match across the doc set. |
| 9 | No embedded history | Backward narrative is removed from main docs and substantive history is in the changelog. |

## Changelog Rules

- Append only.
- Use a single central `CHANGELOG.md` at the repo root, or under `docs/` if documentation is centered there.
- Log substantive changes in meaning, behavior, instructions, or facts.
- Do not log typo, formatting, wording, or reordering-only edits.

Example:

```markdown
## [Unreleased]
### Changed
- README: install steps now use pnpm instead of npm.
```

## Safety Rules

- Do not delete content whose correctness cannot be assessed; flag it instead.
- Respect the doc's existing voice and structure unless they violate the quality gate.
- Confirm before large deletions, file splits, renames, or moves.
- Never invent facts to make a doc feel complete.
```

- [ ] **Step 2: Verify frontmatter and discovery**

Run:

```bash
test -f dev-skills/codex-skills/doc-update/SKILL.md
sed -n '1,12p' dev-skills/codex-skills/doc-update/SKILL.md
```

Expected: the file exists, starts with YAML frontmatter, and includes `name: doc-update` and a `description` beginning with `Use when`.

### Task 5: Validate And Commit

**Files:**
- Inspect: `dev-skills/.codex-plugin/plugin.json`
- Inspect: `.agents/plugins/marketplace.json`
- Inspect: `dev-skills/codex-skills/goal-rubric/SKILL.md`
- Inspect: `dev-skills/codex-skills/doc-update/SKILL.md`

**Interfaces:**
- Consumes: tasks 2-4.
- Produces: committed implementation ready for PR.

- [ ] **Step 1: Validate JSON**

Run:

```bash
jq . dev-skills/.codex-plugin/plugin.json >/dev/null
jq . .agents/plugins/marketplace.json >/dev/null
```

Expected: both commands exit `0`.

- [ ] **Step 2: Validate manifest and marketplace semantics**

Run:

```bash
jq -e '.name == "dev-skills" and .version == "1.0.0" and .skills == "./codex-skills/"' dev-skills/.codex-plugin/plugin.json
jq -e '.plugins[] | select(.name == "dev-skills" and .source.source == "local" and .source.path == "./dev-skills" and .policy.installation == "AVAILABLE" and .policy.authentication == "ON_INSTALL" and .category == "Developer Tools")' .agents/plugins/marketplace.json
```

Expected: both commands exit `0`.

- [ ] **Step 3: Validate Codex skill discovery scope**

Run:

```bash
find dev-skills/codex-skills -mindepth 2 -maxdepth 2 -name SKILL.md | sort
```

Expected output:

```text
dev-skills/codex-skills/doc-update/SKILL.md
dev-skills/codex-skills/goal-rubric/SKILL.md
```

- [ ] **Step 4: Validate skill frontmatter names**

Run:

```bash
for file in dev-skills/codex-skills/*/SKILL.md; do
  sed -n '1,8p' "$file"
done
```

Expected: each file has closed YAML frontmatter, a `name`, and a `description` that starts with `Use when`.

- [ ] **Step 5: Validate declared Codex skill root**

Run:

```bash
uv run --with pyyaml python - <<'PY'
from pathlib import Path
import json

manifest = json.loads(Path("dev-skills/.codex-plugin/plugin.json").read_text())
assert manifest["skills"] == "./codex-skills/"

skills_root = Path("dev-skills") / manifest["skills"].removeprefix("./").rstrip("/")
assert skills_root.is_dir()

skill_names = sorted(path.parent.name for path in skills_root.glob("*/SKILL.md"))
assert skill_names == ["doc-update", "goal-rubric"], skill_names
print(skill_names)
PY
```

Expected: prints `['doc-update', 'goal-rubric']` and exits `0`.

- [ ] **Step 6: Confirm unsupported skills are not exposed to Codex**

Run:

```bash
test ! -e dev-skills/codex-skills/discuss-with-codex
test ! -e dev-skills/codex-skills/pr-feedback
test ! -e dev-skills/codex-skills/project-eval
test ! -e dev-skills/codex-skills/problem-solving-cycle
test ! -e dev-skills/codex-skills/step-workflow
test ! -e dev-skills/codex-skills/discord-setup
```

Expected: every command exits `0`.

- [ ] **Step 7: Commit implementation**

Run:

```bash
git add .agents/plugins/marketplace.json dev-skills/.codex-plugin/plugin.json dev-skills/codex-skills docs/superpowers/plans/2026-06-17-dev-skills-codex-installable.md
git commit -m "feat: add Codex dev-skills support"
```

Expected: commit succeeds.
