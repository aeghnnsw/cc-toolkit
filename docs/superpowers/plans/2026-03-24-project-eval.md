# Project Eval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a dev-skills skill that dispatches long-running skeptical critic agents to evaluate projects from multiple directions, with Focus (converge) and Explore (time-limited diverge) modes.

**Architecture:** A SKILL.md orchestrates mode detection, agent dispatch, and report consolidation. Reference files provide the angle pool and templates. A single generic eval-critic agent definition handles all evaluation — parameterized at dispatch with direction, scope, and mode-specific behavior.

**Tech Stack:** Claude Code plugin system (SKILL.md, agents/*.md), markdown reference files, no external dependencies.

**Spec:** `docs/superpowers/specs/2026-03-24-project-eval-design.md`

---

### Task 1: Create the eval-critic agent definition

The agent is the foundation — the skill dispatches it, so it must exist first.

**Files:**
- Create: `dev-skills/agents/eval-critic.md`

- [ ] **Step 1: Create the agents directory**

```bash
mkdir -p dev-skills/agents
```

- [ ] **Step 2: Write the eval-critic agent definition**

Create `dev-skills/agents/eval-critic.md` with:
- YAML frontmatter: name, description, tools (Read, Glob, Grep, Write, Bash, WebFetch), model (sonnet), color (red)
- System prompt establishing skeptical identity
- Anti-self-praise calibration (explicit instruction to never downgrade findings)
- Evidence requirement (every finding must cite file + line + snippet)
- Iteration loop behavior:
  - Read assigned direction and target scope from dispatch prompt
  - Read the angle pool reference file for calibration within assigned direction
  - Evaluate the target from assigned direction
  - Write findings to assigned output file using the finding format
  - **Focus mode**: Check if new issues found this iteration. Yes → rotate angle, repeat. No → report convergence and terminate.
  - **Explore mode**: Check current time against deadline timestamp. Past deadline → finish current iteration, write final findings, terminate. Otherwise → pick a new angle, go deeper or broader, repeat.
- Finding output format: each finding as a markdown section with local ID (e.g., C1-F1), severity, direction, location, iteration, status, description, evidence
- Suggested next directions: at end of each iteration, note anything spotted outside assigned direction
- Instruction to read `${CLAUDE_PLUGIN_ROOT}/skills/project-eval/references/angles.md` at start for calibration
- Instruction to read `${CLAUDE_PLUGIN_ROOT}/skills/project-eval/references/finding-format.md` for output format

The agent prompt should be ~400-600 words. Focus on behavior, not repeating the angle pool content (that's in the reference file).

- [ ] **Step 3: Verify file structure**

```bash
ls -la dev-skills/agents/eval-critic.md
head -10 dev-skills/agents/eval-critic.md
```

Expected: File exists, frontmatter starts with `---`

- [ ] **Step 4: Commit**

```bash
git add dev-skills/agents/eval-critic.md
git commit -m "Add eval-critic agent definition"
```

---

### Task 2: Create the finding format reference

This is referenced by both the agent and the skill, so create it early.

**Files:**
- Create: `dev-skills/skills/project-eval/references/finding-format.md`

- [ ] **Step 1: Create the directory structure**

```bash
mkdir -p dev-skills/skills/project-eval/references
```

- [ ] **Step 2: Write finding-format.md**

Include:
- **Per-critic finding format**: How each critic writes individual findings (local ID like C1-F1, severity, direction, location, iteration, status, description, evidence)
- **Per-critic file naming**: `docs/eval/findings-<timestamp>-<critic-id>.md`
- **Consolidated report format**: Header (project name, start time, mode, status), summary table (severity counts), findings section (globally renumbered F1, F2, ...), iteration log (per-critic iteration breakdown), coverage map (Explore mode only)
- **Example per-critic finding** (complete markdown example)
- **Example consolidated report** (complete markdown example showing header, summary, 2-3 findings, iteration log)

Copy the exact formats from the spec at `docs/superpowers/specs/2026-03-24-project-eval-design.md` sections "Finding Format" and "Findings File Structure".

- [ ] **Step 3: Commit**

```bash
git add dev-skills/skills/project-eval/references/finding-format.md
git commit -m "Add finding format reference for project-eval"
```

---

### Task 3: Create the angle pool reference

The calibration content that anchors critic judgment.

**Files:**
- Create: `dev-skills/skills/project-eval/references/angles.md`

- [ ] **Step 1: Write angles.md**

Structure:
- Introduction: "This is a starting menu, not a constraint. Use these directions and calibration examples as inspiration. You may explore freely within your assigned direction and discover issues outside the predefined list."
- For each of the 8 clusters (Code, Architecture, Security, Frontend & Design, User Experience, Product, Data & API, Documentation & Convention):
  - Cluster name and description (1-2 sentences)
  - List of angles within the cluster (from spec lines 62-108)
  - **One calibration example per cluster** showing:
    - A REAL ISSUE: file, code, why it's real, severity
    - A FALSE POSITIVE: file, code, why it's false positive
  - The calibration examples should be realistic and varied across domains (not all backend code — include frontend, UX, product examples)

Keep total length under 1500 words. The angles are brief — most of the content is the 8 calibration examples.

- [ ] **Step 2: Commit**

```bash
git add dev-skills/skills/project-eval/references/angles.md
git commit -m "Add angle pool reference with calibration examples"
```

---

### Task 4: Create the focus mode reference

Detailed workflow for Focus mode, referenced by SKILL.md.

**Files:**
- Create: `dev-skills/skills/project-eval/references/focus-mode.md`

- [ ] **Step 1: Write focus-mode.md**

Include the complete Focus mode workflow:
1. Main agent identifies target files/scope (search codebase, establish boundary)
2. Select relevant directions from angle pool (read `angles.md`, pick 1-3 clusters based on target)
3. Dispatch critic agent(s) as long-running background agents:
   - Use the Agent tool with `run_in_background: true`
   - Each critic gets: direction, target scope, calibration reference path, output file path, previous findings (empty for first dispatch)
   - Critic agent name: `eval-critic` (or `eval-critic-1`, `eval-critic-2` for multiple)
   - Tell each critic: "You are in Focus mode. Loop until you find no new issues in a full iteration, then terminate."
4. Main agent informs user that critics are running
5. When all critics complete (notification from background agents):
   - Read all per-critic findings files from `docs/eval/`
   - Merge into consolidated report: deduplicate, assign global IDs, write iteration log
   - Write consolidated report to `docs/eval/findings-<YYYY-MM-DD-HHMMSS>.md`
   - Delete per-critic files after consolidated report is fully written
   - Present final report to user

Include the exact Agent tool dispatch pattern:
```
Agent(
  subagent_type: "eval-critic",
  prompt: "...",
  run_in_background: true,
  name: "eval-critic-1"
)
```

- [ ] **Step 2: Commit**

```bash
git add dev-skills/skills/project-eval/references/focus-mode.md
git commit -m "Add focus mode workflow reference for project-eval"
```

---

### Task 5: Create the explore mode reference

Detailed workflow for Explore mode, referenced by SKILL.md.

**Files:**
- Create: `dev-skills/skills/project-eval/references/explore-mode.md`

- [ ] **Step 1: Write explore-mode.md**

Include the complete Explore mode workflow:
1. Parse time limit from user's message (default 30 min if not specified)
2. Calculate deadline timestamp: `date +%s` + (time_limit_minutes * 60)
3. Survey the project: read structure, recent changes, README, CLAUDE.md, build initial map of areas
4. Dispatch 3-5 critics as long-running background agents:
   - Same Agent tool pattern as Focus mode
   - Each critic gets: direction, "entire project" as scope, output file path, **deadline timestamp**
   - Assign diverse starting directions to maximize coverage
   - Tell each critic: "You are in Explore mode. Check `date +%s` against your deadline before each iteration. Past deadline → finish current iteration and terminate. Otherwise → pick a new angle, go deeper or broader, repeat."
5. Main agent informs user that critics are running with time limit
6. When all critics complete (deadline-based self-termination):
   - Same consolidation as Focus mode
   - Additionally write Coverage Map section showing which areas and directions were explored
   - Flag unexplored areas for potential future runs
   - Present final report to user

Include note about resource constraints: if platform limits concurrent agents, reduce fan-out and dispatch remaining directions after first batch completes.

- [ ] **Step 2: Commit**

```bash
git add dev-skills/skills/project-eval/references/explore-mode.md
git commit -m "Add explore mode workflow reference for project-eval"
```

---

### Task 6: Create the SKILL.md orchestration skill

The main skill file — lean orchestrator that references the detail files.

**Files:**
- Create: `dev-skills/skills/project-eval/SKILL.md`

- [ ] **Step 1: Write SKILL.md**

YAML frontmatter:
```yaml
---
name: project-eval
version: 1.0.0
description: This skill should be used when the user asks to "evaluate the project", "run a deep eval", "review this feature", "evaluate the auth module", "find issues", or wants multi-angle project evaluation with long-running critic agents. Dispatches skeptical evaluator agents that iterate through evaluation angles to find issues across code, architecture, security, UX, product, and design dimensions.
---
```

Body (keep under 2000 words — reference files carry the detail):

1. **Overview**: Brief description of what the skill does. Two modes: Focus and Explore.

2. **Critical lifecycle rules**:
   - Critic agents are long-running team agents — NEVER kill them unless the user explicitly asks
   - Do NOT wait for critics to finish before responding to the user
   - Critics run autonomously and self-terminate based on mode (convergence or deadline)

3. **Mode detection table**: Map user intent to Focus vs Explore. If ambiguous, ask user.

4. **Workflow — Focus mode**:
   - "Read `${CLAUDE_PLUGIN_ROOT}/skills/project-eval/references/focus-mode.md` for the complete workflow."
   - Brief summary: identify scope → read angles.md → dispatch critics → consolidate on completion

5. **Workflow — Explore mode**:
   - "Read `${CLAUDE_PLUGIN_ROOT}/skills/project-eval/references/explore-mode.md` for the complete workflow."
   - Brief summary: parse time limit → survey project → dispatch critics with deadline → consolidate on completion

6. **Fan-out strategy**:
   - User specifies count → use it
   - Default: Focus 1-3 based on relevant clusters, Explore 3-5 for broad coverage
   - Coordinate direction assignment to avoid overlap
   - Adapt to platform limits on concurrent agents

7. **Consolidation**:
   - "Read `${CLAUDE_PLUGIN_ROOT}/skills/project-eval/references/finding-format.md` for report format."
   - Read all per-critic files, deduplicate, assign global IDs, write consolidated report, delete per-critic files after write completes

8. **Angle pool reference**:
   - "Read `${CLAUDE_PLUGIN_ROOT}/skills/project-eval/references/angles.md` before selecting directions."
   - Brief list of the 8 cluster names for quick reference

- [ ] **Step 2: Verify SKILL.md is under 2000 words**

```bash
wc -w dev-skills/skills/project-eval/SKILL.md
```

Expected: Under 2000 words

- [ ] **Step 3: Commit**

```bash
git add dev-skills/skills/project-eval/SKILL.md
git commit -m "Add project-eval orchestration skill"
```

---

### Task 7: Bump version and finalize

**Files:**
- Modify: `dev-skills/.claude-plugin/plugin.json`

- [ ] **Step 1: Bump dev-skills version to 3.2.0**

In `dev-skills/.claude-plugin/plugin.json`, change `"version": "3.1.0"` to `"version": "3.2.0"`.

- [ ] **Step 2: Verify plugin structure**

```bash
cat dev-skills/.claude-plugin/plugin.json | python3 -m json.tool
ls dev-skills/skills/project-eval/
ls dev-skills/skills/project-eval/references/
ls dev-skills/agents/
```

Expected:
- Valid JSON
- SKILL.md in project-eval/
- angles.md, finding-format.md, focus-mode.md, explore-mode.md in references/
- eval-critic.md in agents/

- [ ] **Step 3: Commit**

```bash
git add dev-skills/.claude-plugin/plugin.json
git commit -m "Bump dev-skills to 3.2.0 for project-eval skill"
```
