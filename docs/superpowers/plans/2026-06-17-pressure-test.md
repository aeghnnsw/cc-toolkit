# Pressure Test Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Codex `pressure-test` skill that runs independent adversarial pressure tests using a skeptical subagent.

**Architecture:** Add one instruction-only Codex skill under `dev-skills/codex-skills/pressure-test/`. Keep Claude `discuss-with-codex` unchanged. Update the Codex `dev-skills` plugin metadata to advertise pressure testing without changing the skill root.

**Tech Stack:** Markdown `SKILL.md` with YAML frontmatter, Codex plugin JSON, `jq`, `uv run --with pyyaml` validation.

## Global Constraints

- Work on branch `feat-143-pressure-test` for issue #143.
- Skill name must be `pressure-test`.
- Skill description must be concise, accurate, trigger-focused, and start with `Use when`.
- Skill description must not summarize the multi-round workflow.
- Default loop is multi-round with `ROUND_CAP = 6`.
- Stop early on convergence.
- Main Codex agent owns the position and conclusion.
- Critic must be an independent spawned subagent.
- Each critic round must include a critic context packet.
- Do not run nested non-interactive Claude or Codex CLI sessions.
- Do not silently fall back to inline self-critique when subagent spawning is unavailable.
- Do not modify Claude-facing `dev-skills/skills/discuss-with-codex/SKILL.md`.
- Do not update Claude-facing task-loop paths in this issue.
- Keep issue, commit, and PR text free of attribution boilerplate.
- Do not include a test plan section in the PR body.

---

## File Structure

- Create `dev-skills/codex-skills/pressure-test/SKILL.md`: Codex-facing pressure-test skill.
- Modify `dev-skills/.codex-plugin/plugin.json`: add pressure-test discovery metadata in keywords and default prompts.

### Task 1: Red Checks For Missing Pressure-test Support

**Files:**
- Inspect: `dev-skills/codex-skills/pressure-test/SKILL.md`
- Inspect: `dev-skills/.codex-plugin/plugin.json`

**Interfaces:**
- Consumes: current worktree state.
- Produces: failing checks that prove the requested skill is absent before implementation.

- [ ] **Step 1: Verify the skill is absent**

Run:

```bash
test ! -e dev-skills/codex-skills/pressure-test/SKILL.md
```

Expected: exits `0`.

- [ ] **Step 2: Verify the current Codex skill set does not include pressure-test**

Run:

```bash
! find dev-skills/codex-skills -mindepth 2 -maxdepth 2 -name SKILL.md | grep -q 'pressure-test/SKILL.md'
```

Expected: exits `0`.

### Task 2: Add Pressure-test Skill

**Files:**
- Create: `dev-skills/codex-skills/pressure-test/SKILL.md`

**Interfaces:**
- Consumes: design spec `docs/superpowers/specs/2026-06-17-pressure-test-design.md`.
- Produces: a Codex skill named `pressure-test` with concise frontmatter and the approved subagent critic loop.

- [ ] **Step 1: Create `dev-skills/codex-skills/pressure-test/SKILL.md`**

Use this content:

```markdown
---
name: pressure-test
description: Use when a design, plan, rubric, PR, failure diagnosis, or task orchestration decision needs independent adversarial review before conclusion.
---

# Pressure Test

Run an independent adversarial review before settling a decision. The main Codex agent owns the position and conclusion; a spawned skeptical subagent supplies pressure.

## Core Principle

Pressure testing only matters when the critic has enough context and independence to find real weaknesses. Do not replace the critic with inline self-critique.

## When To Use

Use for design decisions, architecture choices, task-loop aims, rubrics, plans, PRs, failure diagnoses, re-attack plans, and aim-fidelity checks.

Do not use for routine edits where the user asked for direct implementation and no judgment call needs adversarial review.

## Defaults

- `ROUND_CAP = 6`
- Stop early on convergence.
- Always save and present a conclusion.
- The critic is read-only. If the active Codex surface supports per-agent sandbox control, spawn the critic with read-only access. Otherwise, instruct the critic not to write files or run mutating commands, and do not approve critic write actions.

## Loop

1. State the current position: claim, reasoning, and decision boundary.
2. Build a critic context packet.
3. Spawn a skeptical subagent with the packet and critic instructions.
4. Read the critic's objections.
5. Handle every substantive objection: concede and revise, or rebut with evidence.
6. Stop if converged; otherwise repeat until round 6.
7. Write and present the conclusion.

## Critic Context Packet

Before every critic round, provide the subagent this packet:

```text
GOAL
The question, design, plan, rubric, PR, or failure diagnosis under review.

CURRENT POSITION
The current answer and reasoning.

DECISION BOUNDARY
What is in scope, what is out of scope, and what kind of objection would change the decision.

EVIDENCE
Relevant files, diffs, command outputs, proposal sections, rubric text, PR body, task-loop state, or other concrete artifacts.

ASSUMPTIONS
Known constraints and assumptions to attack.

PRIOR ROUNDS
Objections already raised and how they were handled.

CRITIC INSTRUCTIONS
Attack the weakest point first. Ground objections in evidence. Propose better alternatives when they exist. Say no substantive objection only when warranted.
```

If the packet lacks enough evidence for reliable judgment, gather the missing evidence before spawning the critic or report the gap.

## Critic Prompt

Use this stance for each critic subagent:

```text
You are an independent adversarial critic. Do not approve, praise, or soften the review.

Find the single weakest point in the current position. Surface hidden assumptions, edge cases, failure modes, and missing evidence. Ground objections in the provided evidence and inspect the repo read-only when needed. If a better alternative exists, propose it concretely.

Avoid repeating prior objections unless the handling was insufficient. If no substantive objection remains, reply with: NO SUBSTANTIVE OBJECTION. Then give one sentence explaining why the position holds.
```

## Convergence

Stop before round 6 only when:

- the critic reports no substantive objection, or
- the original decision is stable and remaining objections are out-of-scope refinements that do not change the decision.

Do not stop because the current position feels persuasive. Judge convergence against the critic's actual objections and the decision boundary.

## Progress Format

After each round, record:

```text
Round N
Critic: strongest objections, faithfully summarized.
Disposition: conceded and revised, or rebutted with evidence.
Current position: updated position.
```

## Conclusion

Write the conclusion to:

```text
docs/superpowers/specs/YYYY-MM-DD-topic-slug-conclusion.md
```

Include:

- settled position
- key decisions
- strongest objections and dispositions
- unresolved tensions, if any
- ending condition: converged, round cap, critic unavailable, or cut short

Present the same conclusion in chat.

## Failure Behavior

If subagent spawning is unavailable, stop and report that an independent critic could not run. Do not silently run inline self-critique.

If a critic round fails mid-loop, retry that round once. If it still fails, write a partial conclusion with the last stable position, unresolved objections, and the failure point.
```

- [ ] **Step 2: Verify the description is concise and trigger-focused**

Run:

```bash
uv run --with pyyaml python - <<'PY'
from pathlib import Path
import yaml

text = Path("dev-skills/codex-skills/pressure-test/SKILL.md").read_text()
end = text.find("\n---", 4)
meta = yaml.safe_load(text[4:end])
description = meta["description"]

assert description.startswith("Use when "), description
assert len(description) <= 180, len(description)
for forbidden in ("spawn", "subagent", "round", "loop", "context packet", "conclusion file"):
    assert forbidden not in description.lower(), forbidden
print(description)
print(len(description))
PY
```

Expected: prints the description and a length no greater than `180`.

### Task 3: Update Codex Plugin Metadata

**Files:**
- Modify: `dev-skills/.codex-plugin/plugin.json`

**Interfaces:**
- Consumes: existing Codex dev-skills manifest.
- Produces: plugin metadata that mentions pressure testing while keeping `"skills": "./codex-skills/"`.

- [ ] **Step 1: Add pressure-test metadata**

Update `keywords` to include:

```json
"pressure-test",
"critic",
"review"
```

Update `interface.longDescription` to:

```json
"Use Dev Skills for selected development workflows, including measurable goal rubrics, current-truth documentation updates, and independent adversarial pressure tests."
```

Update `interface.defaultPrompt` to include:

```json
"Pressure-test this plan before implementation."
```

- [ ] **Step 2: Verify the manifest still declares the Codex skill root**

Run:

```bash
jq -e '.skills == "./codex-skills/" and (.keywords | index("pressure-test")) and (.interface.defaultPrompt | index("Pressure-test this plan before implementation."))' dev-skills/.codex-plugin/plugin.json
```

Expected: exits `0`.

### Task 4: Validate Discovery And Existing Skills

**Files:**
- Inspect: `dev-skills/codex-skills/pressure-test/SKILL.md`
- Inspect: `dev-skills/codex-skills/goal-rubric/SKILL.md`
- Inspect: `dev-skills/codex-skills/doc-update/SKILL.md`
- Inspect: `dev-skills/.codex-plugin/plugin.json`

**Interfaces:**
- Consumes: tasks 2 and 3.
- Produces: validation evidence that Codex discovers exactly the intended dev-skills.

- [ ] **Step 1: Validate JSON**

Run:

```bash
jq . dev-skills/.codex-plugin/plugin.json >/dev/null
```

Expected: exits `0`.

- [ ] **Step 2: Validate skill frontmatter**

Run:

```bash
uv run --with pyyaml python /Users/steven/.codex/skills/.system/skill-creator/scripts/quick_validate.py dev-skills/codex-skills/pressure-test
uv run --with pyyaml python /Users/steven/.codex/skills/.system/skill-creator/scripts/quick_validate.py dev-skills/codex-skills/goal-rubric
uv run --with pyyaml python /Users/steven/.codex/skills/.system/skill-creator/scripts/quick_validate.py dev-skills/codex-skills/doc-update
```

Expected: each command prints `Skill is valid!`.

- [ ] **Step 3: Validate Codex skill discovery scope**

Run:

```bash
find dev-skills/codex-skills -mindepth 2 -maxdepth 2 -name SKILL.md | sort
```

Expected output:

```text
dev-skills/codex-skills/doc-update/SKILL.md
dev-skills/codex-skills/goal-rubric/SKILL.md
dev-skills/codex-skills/pressure-test/SKILL.md
```

- [ ] **Step 4: Validate declared root resolves to those skills**

Run:

```bash
uv run --with pyyaml python - <<'PY'
from pathlib import Path
import json

manifest = json.loads(Path("dev-skills/.codex-plugin/plugin.json").read_text())
assert manifest["skills"] == "./codex-skills/"
root = Path("dev-skills") / manifest["skills"].removeprefix("./").rstrip("/")
names = sorted(path.parent.name for path in root.glob("*/SKILL.md"))
assert names == ["doc-update", "goal-rubric", "pressure-test"], names
print(names)
PY
```

Expected: prints `['doc-update', 'goal-rubric', 'pressure-test']`.

- [ ] **Step 5: Verify Claude skill remains unchanged**

Run:

```bash
git diff -- dev-skills/skills/discuss-with-codex/SKILL.md
```

Expected: no output.

### Task 5: Commit Implementation

**Files:**
- Add: `dev-skills/codex-skills/pressure-test/SKILL.md`
- Modify: `dev-skills/.codex-plugin/plugin.json`
- Add: `docs/superpowers/plans/2026-06-17-pressure-test.md`

**Interfaces:**
- Consumes: completed validation.
- Produces: committed implementation ready for PR.

- [ ] **Step 1: Run final whitespace check**

Run:

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 2: Commit**

Run:

```bash
git add dev-skills/.codex-plugin/plugin.json dev-skills/codex-skills/pressure-test/SKILL.md docs/superpowers/plans/2026-06-17-pressure-test.md
git commit -m "feat: add Codex pressure-test skill"
```

Expected: commit succeeds.
