# Goal Rubric Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `goal-rubric` skill — a single-file Claude Code skill that turns a one-line goal into a binary pass/fail rubric and a ready-to-paste `/goal` completion condition.

**Architecture:** One `SKILL.md` under `dev-skills/skills/goal-rubric/`, auto-discovered by the `dev-skills` plugin (no manifest edits needed). The file teaches a hybrid workflow: draft a binary rubric from the goal + read-only repo inspection, ask only about gaps, then save a rubric file and render the `/goal` condition. The skill's value-add is enforcing that every criterion is binary, transcript-observable, and small-model-judgeable — the properties that let a `/goal` grader actually close the loop.

**Tech Stack:** Markdown only. No code, no dependencies, no build/lint/test steps. This is a configuration/documentation repository; "tests" are structural verifications (frontmatter parses, required sections present, no placeholders).

**Reference:** Design spec at `docs/superpowers/specs/2026-05-30-goal-rubric-design.md`.

**Note on commits:** Run all commands from the repository worktree root, on the `feat-goal-rubric` branch. Keep commit messages concise and free of AI-tool attribution.

---

## File Structure

- Create: `dev-skills/skills/goal-rubric/SKILL.md` — the entire skill (frontmatter + rules + workflow + output format + self-check).

No other files change. Skills are auto-discovered, so neither `dev-skills/.claude-plugin/plugin.json` nor the root `.claude-plugin/marketplace.json` needs editing (`dev-skills` is already a registered plugin).

---

### Task 1: Scaffold the skill — frontmatter and intro

**Files:**
- Create: `dev-skills/skills/goal-rubric/SKILL.md`

- [ ] **Step 1: Create the skill file with frontmatter and intro**

Create `dev-skills/skills/goal-rubric/SKILL.md` with exactly this content (this is the whole file for now; later tasks append sections):

````markdown
---
name: goal-rubric
version: 1.0.0
description: Draft a binary (pass/fail) rubric and a ready-to-paste completion condition for a Claude Code or Codex /goal command. Use when the user wants to write or design a rubric, success criteria, acceptance criteria, or a "done"/completion condition for /goal, or when a /goal loop will not close because its criteria are not measurable.
---

# Goal Rubric

Turn a one-line goal into a **binary rubric** a `/goal` grader can check against, then render it into a ready-to-paste `/goal` condition.

A `/goal` loop runs an agent turn-by-turn; after each turn a separate small/fast grader model decides whether to stop. The loop only closes when the completion condition is genuinely checkable. This skill produces a rubric that is checkable.
````

- [ ] **Step 2: Verify the frontmatter is well-formed**

Run:
```bash
grep -nE "^(name|version|description):" dev-skills/skills/goal-rubric/SKILL.md
```
Expected: three lines — `2:name: goal-rubric`, `3:version: 1.0.0`, and `4:description: ...`. The file must open with `---` on line 1 and close the frontmatter block with a second `---` before `# Goal Rubric`.

- [ ] **Step 3: Verify no manifest changes are required**

Run:
```bash
test -f dev-skills/.claude-plugin/plugin.json && echo "dev-skills plugin exists — skill is auto-discovered, no edit needed"
```
Expected: prints the confirmation line. Do NOT edit `plugin.json` or `marketplace.json`.

- [ ] **Step 4: Commit**

```bash
git add dev-skills/skills/goal-rubric/SKILL.md
git commit -m "Add goal-rubric skill scaffold and frontmatter"
```

---

### Task 2: Add the grader-constraints and rubric-rules sections

**Files:**
- Modify: `dev-skills/skills/goal-rubric/SKILL.md` (append after the intro)

- [ ] **Step 1: Append the "How the grader works" and "What a good rubric contains" sections**

Append exactly this content to the end of `dev-skills/skills/goal-rubric/SKILL.md`:

````markdown

## How the grader works (why these rules exist)

The grader is not the agent doing the work. It is constrained:

- **Transcript-only.** It reads only what the agent surfaced in the conversation. It does NOT run commands or read files itself. → every criterion must be provable from the agent's own output.
- **Small/fast model** (Haiku-class by default), returning yes/no plus a short reason. → every criterion must be atomic and unambiguous.

Write criteria the agent can *demonstrate in its output* and a small model can *judge at a glance*.

## What a good rubric contains

The rubric is a set of independent **pass/fail** criteria joined by AND — the goal is done only when every criterion passes. Each criterion has:

- **End state** — one measurable, observable signal (a test result, a build/exit code, a file count, an empty queue).
- **Check** — how that end state is proven *in the agent's output* (e.g. "`pytest test/auth` printed `0 failed`").
- **Constraint** — what must not change on the way there (e.g. "no file outside `src/auth/` is modified"), when relevant.

Plus one overall **stop clause** — a turn or time cap (e.g. "or stop after 20 turns").

Apply these rules. Rules 1–3 and 6 are per-criterion; rules 4–5 are about the rubric as a whole:

1. Names a measurable end state.
2. States the check that proves it.
3. Captures any guardrail or constraint that must hold (when one applies).
4. The rubric has a stop clause.
5. Criteria are independent — no two overlap or double-count.
6. Every criterion is binary; "done" = all pass.

In addition, each criterion must be **transcript-observable** (provable from the agent's surfaced output) and **small-model-judgeable** (atomic, unambiguous).
````

- [ ] **Step 2: Verify both section headings are present**

Run:
```bash
grep -nE "^## (How the grader works|What a good rubric contains)" dev-skills/skills/goal-rubric/SKILL.md
```
Expected: two matching heading lines.

- [ ] **Step 3: Verify the six rules are all present**

Run:
```bash
grep -cE "^[1-6]\. " dev-skills/skills/goal-rubric/SKILL.md
```
Expected: `6`.

- [ ] **Step 4: Commit**

```bash
git add dev-skills/skills/goal-rubric/SKILL.md
git commit -m "Add grader constraints and rubric rules to goal-rubric skill"
```

---

### Task 3: Add the workflow and output sections

**Files:**
- Modify: `dev-skills/skills/goal-rubric/SKILL.md` (append after the rules)

- [ ] **Step 1: Append the "Workflow" and "Output" sections**

Append exactly this content to the end of `dev-skills/skills/goal-rubric/SKILL.md`:

````markdown

## Workflow

1. **Take the goal.** Get the one-line goal from the user.
2. **Inspect the repo (read-only).** Look at test config, build/lint commands, and file layout to infer the measurable end states and the exact commands/artifacts that prove them. Do not modify anything.
3. **Draft the binary rubric.** Write the independent criteria (end state + check, plus a constraint where one applies) and the stop clause, applying every rule above.
4. **Ask only about gaps.** Ask the user targeted questions ONLY for what inspection could not settle — e.g. "which command proves the feature works?", "any files that must not change?", "what turn or time cap?". Never re-ask what the repo already answered. Keep it to the minimum.
5. **Finalize.** Save the rubric file and render the `/goal` condition.

## Output

Save the rubric to `./goal-rubric-<slug>.md` in the working directory (let the user override the path). Use this structure:

```
# Goal rubric: <goal one-liner>

## Criteria (all must pass)
1. <name> — End state: <observable signal>. Check: <how it is proven in the transcript>. Constraint (if any): <what must not change>.
2. ...

## Stop clause
<turn or time cap>

## /goal condition (<tool>)
<the rendered condition — one string for Claude, or the four-part framing for Codex — in a fenced block>
```

Then render the condition for the target tool (ask which if unclear; default **Claude**):

- **Claude `/goal`** — a single condition string (keep it within the `/goal` length limit — around 4,000 chars) phrased so the proof appears in the transcript, e.g. `all tests in test/auth pass (pytest prints 0 failed) and git status is clean, without modifying any file outside src/auth/, or stop after 20 turns`.
- **Codex `/goal`** — frame it as: what to achieve / what not to change / how to validate / when to stop.
````

- [ ] **Step 2: Verify both section headings are present**

Run:
```bash
grep -nE "^## (Workflow|Output)" dev-skills/skills/goal-rubric/SKILL.md
```
Expected: two matching heading lines.

- [ ] **Step 3: Verify the workflow has five steps**

Run:
```bash
grep -cE "^[1-5]\. \*\*" dev-skills/skills/goal-rubric/SKILL.md
```
Expected: `5` (the five bold-led workflow steps).

- [ ] **Step 4: Commit**

```bash
git add dev-skills/skills/goal-rubric/SKILL.md
git commit -m "Add workflow and output sections to goal-rubric skill"
```

---

### Task 4: Add the self-check section and run final verification

**Files:**
- Modify: `dev-skills/skills/goal-rubric/SKILL.md` (append the closing section)

- [ ] **Step 1: Append the "Before you finish — self-check" section**

Append exactly this content to the end of `dev-skills/skills/goal-rubric/SKILL.md`:

````markdown

## Before you finish — self-check

- [ ] Every criterion names a measurable end state and the check that proves it.
- [ ] Every criterion is pass/fail (no scores, no "mostly").
- [ ] Every criterion's proof would actually appear in the agent's output.
- [ ] No criterion needs the grader to run a command or open a file.
- [ ] Criteria do not overlap.
- [ ] There is a stop clause.
````

- [ ] **Step 2: Verify there are no leftover authoring placeholders**

Run:
```bash
grep -nE "TODO|TBD|FIXME" dev-skills/skills/goal-rubric/SKILL.md || echo "no placeholders"
```
Expected: `no placeholders`. (The `<...>` tokens inside the Output template are intentional fill-in slots, not placeholders — leave them.)

- [ ] **Step 3: Verify the full section structure**

Run:
```bash
grep -nE "^#{1,2} " dev-skills/skills/goal-rubric/SKILL.md
```
Expected, in order: `# Goal Rubric`, `## How the grader works (why these rules exist)`, `## What a good rubric contains`, `## Workflow`, `## Output`, `## Before you finish — self-check`.

- [ ] **Step 4: Spec-coverage check**

Read `docs/superpowers/specs/2026-05-30-goal-rubric-design.md` and confirm each is reflected in SKILL.md:
- Rules 1–6 (binary) → "What a good rubric contains".
- Transcript-observable / small-model-judgeable overlay → "How the grader works" + the overlay line.
- Hybrid workflow (take goal → inspect → draft → gap questions → finalize) → "Workflow".
- Output = rubric file + rendered `/goal` condition, default save path, Claude/Codex rendering, default Claude → "Output".
- Scope is draft-only, no diagnose/scoring/examples → confirm none of those crept in.

If any item is missing, add it before committing.

- [ ] **Step 5: (Optional) Run the skill reviewer**

If desired, dispatch the `plugin-dev:skill-reviewer` agent on `dev-skills/skills/goal-rubric/SKILL.md` to sanity-check description quality and triggering. Apply only changes that keep the design intent (binary, draft-only, single-file, no examples).

- [ ] **Step 6: Commit**

```bash
git add dev-skills/skills/goal-rubric/SKILL.md
git commit -m "Add self-check section to goal-rubric skill"
```

---

## Done

`dev-skills/skills/goal-rubric/SKILL.md` is complete and committed on branch `feat-goal-rubric`. The skill is auto-discovered by the `dev-skills` plugin. Next step outside this plan: push the branch and open a PR (simple, concise description; references the design spec; no test plan, no attribution — per the user's instructions).
