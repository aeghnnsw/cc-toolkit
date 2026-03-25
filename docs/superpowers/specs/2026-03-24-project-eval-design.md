# Project Eval — Design Spec

A skill for dev-skills that dispatches long-running critic agents to evaluate a project from multiple directions. Inspired by [Anthropic's harness design for long-running apps](https://www.anthropic.com/engineering/harness-design-long-running-apps), specifically the finding that separating creation from evaluation — and tuning evaluators for skepticism — produces far better quality assessment than self-review.

## Problem

Agent-generated code benefits from independent critical review, but:
- Agents exhibit self-praise bias when evaluating their own work
- Single-pass reviews miss issues that require looking from different angles
- Review scope is typically limited to code — missing UX, product, and design concerns
- There's no mechanism for continuous, multi-angle evaluation during development

## Solution

An on-demand evaluation skill with two modes:
- **Focus mode**: Converge on a specific feature until no new issues are found
- **Explore mode**: Diverge across the entire project for a time-limited period (default 30 min)

Both modes dispatch long-running critic agents that autonomously loop through evaluation iterations, writing findings to per-critic files that the main agent merges at consolidation.

## File Layout

```
dev-skills/
  skills/
    project-eval/
      SKILL.md                      # Orchestration skill
      references/
        angles.md                   # Angle pool with calibration examples
        finding-format.md           # Finding structure & report templates
        focus-mode.md               # Focus mode detailed workflow
        explore-mode.md             # Explore mode detailed workflow
  agents/
    eval-critic.md                  # Generic skeptical critic agent
```

**Reference file loading**: The SKILL.md instructs the main agent to `Read` specific reference files at the points in the workflow where they are needed (e.g., read `angles.md` before selecting directions, read `finding-format.md` before dispatching critics). Reference files are NOT auto-loaded by the plugin system — they must be explicitly read.

**Note**: The `dev-skills/agents/` directory does not currently exist and must be created.

## Mode Detection

The skill detects mode from the user's natural language:

| User intent | Mode | Behavior |
|-------------|------|----------|
| "evaluate auth module", "review the payment flow" | Focus | Target specific feature/files, converge until clean |
| "evaluate the project", "run a deep eval", "explore" | Explore | Broad project scan, time-limited, maximize diversity |

Focus mode extracts the target scope (feature, module, or file path). Explore mode extracts optional time limit (default 30 min).

## Angle Pool

The angle pool is a **starting menu, not a constraint**. It provides direction and calibration, but critic agents explore freely within their assigned direction and may discover issues outside the predefined list.

The pool serves two purposes:
1. **Dispatch coordination**: Main agent uses cluster names to assign directions and avoid overlap between critics
2. **Calibration anchor**: Critics read examples to calibrate severity judgment

### Clusters

**Code**
- `logic` — Logic errors, wrong conditionals, off-by-one
- `error-handling` — Missing catches, swallowed errors, unhelpful messages
- `state` — State inconsistencies, stale references, missing syncs
- `completeness` — Stubs, TODOs in production paths, half-implemented features
- `concurrency` — Race conditions, partial writes, deadlocks

**Architecture**
- `coupling` — Modules knowing too much about each other
- `boundaries` — Unclear module separation, circular dependencies
- `consistency` — Same problem solved differently across codebase
- `scalability` — Patterns that break under load or growth

**Security**
- `injection` — SQL, command, XSS, template injection
- `auth` — Authentication/authorization gaps
- `secrets` — Credentials in code, logs, or committed config
- `data-privacy` — PII leaks, missing anonymization, retention violations

**Frontend & Design**
- `visual-coherence` — Inconsistent spacing, typography, color usage across views
- `responsiveness` — Breakpoint gaps, overflow issues, touch target sizes
- `accessibility` — Missing ARIA labels, contrast ratios, keyboard navigation
- `component-design` — Duplicated UI patterns, inconsistent component APIs

**User Experience**
- `flow` — Confusing navigation, dead ends, unnecessary steps
- `feedback` — Missing loading states, error messages, success confirmations
- `discoverability` — Hidden features, unclear CTAs, unintuitive interactions
- `edge-ux` — Empty states, first-time experience, degraded states

**Product**
- `feature-gaps` — Missing functionality users would reasonably expect
- `requirement-drift` — Implementation diverging from stated requirements
- `coherence` — Features that contradict each other
- `value` — Features adding complexity with unclear user value

**Data & API**
- `api-contract` — Route conflicts, parameter mismatches, response shape violations
- `schema` — Migration gaps, orphaned references, type mismatches
- `validation` — Missing input validation at system boundaries
- `performance` — N+1 queries, unnecessary fetches, missing caching

**Documentation & Convention**
- `project-rules` — CLAUDE.md compliance, project-specific conventions
- `documentation` — Missing or misleading docs at critical decision points
- `test-quality` — Tests that don't actually verify behavior

31 angles across 8 clusters. Each angle includes a calibration example (one real issue + one false positive) in `references/angles.md`.

## Critic Agent Design

A single generic agent (`eval-critic.md`) tuned for skepticism. The blog's key finding: "tuning a standalone evaluator to be skeptical turns out to be far more tractable than making a generator critical of its own work."

### System prompt principles

1. **Identity**: Skeptical evaluator. Job is to find real issues, not to praise.
2. **Anti-self-praise**: Explicit instruction to resist downgrading findings or talking yourself into approving marginal work.
3. **Direction-driven**: Evaluates through assigned direction lens, but explores freely within it.
4. **Evidence requirement**: Every finding must cite specific file + line + code snippet.
5. **False positive awareness**: Calibration examples anchor judgment.

### Agent frontmatter

```yaml
---
name: eval-critic
description: Skeptical project evaluator dispatched by project-eval skill. Long-running agent that iterates through evaluation angles within an assigned direction.
tools: Read, Glob, Grep, Write, Bash, WebFetch
model: sonnet
color: red
---
```

Tools: `Read`, `Glob`, `Grep` for codebase exploration. `Write` for findings output. `Bash` for running project commands (tests, build checks). `WebFetch` for checking external references. Model: `sonnet` balances depth of reasoning with cost for long-running evaluation loops.

### Dispatch parameters

The main agent passes to each critic at dispatch time:
- Assigned direction (cluster name from the pool)
- Target scope (feature path for Focus, or "entire project" for Explore)
- Previous findings (to avoid re-reporting known issues)
- Finding format template
- **Deadline timestamp** (Explore mode only): critic must self-terminate after this time
- **Output file path**: each critic writes to its own file (`docs/eval/findings-<timestamp>-<critic-id>.md`)

### Return values

Each critic returns:
- List of findings in structured format
- Directions explored and depth reached
- Suggested directions for next iteration (things noticed outside assignment)

## Agent Lifecycle

### Critical rule for SKILL.md

The skill must explicitly instruct the main agent:
- Critic agents are **long-running team agents** — never kill them unless the user explicitly asks to stop
- The main agent dispatches critics and lets them run autonomously
- The main agent does NOT wait for critics to finish before responding to the user

### Terminology

- **Iteration**: One evaluate-write-rotate loop within a single critic agent
- **Cycle**: An orchestrator-level concept — one round of dispatching critics and collecting results. In the current design, critics run multiple iterations autonomously within a single dispatch cycle.

### Focus mode critic lifecycle

1. Evaluate from assigned direction
2. Write findings to own output file
3. Loop job: "Did I find new issues this iteration?"
   - Yes: rotate to new angle within direction, evaluate again
   - No: self-terminate, report convergence to main agent

### Explore mode critic lifecycle

1. Evaluate from assigned direction
2. Write findings to own output file
3. Loop job: "Continue exploring, try a different angle"
   - Always continues — picks increasingly diverse/deep angles
   - Never self-terminates based on findings
4. **Time-based self-termination**: Each critic receives a deadline timestamp at dispatch. At the start of each iteration, the critic checks the current time against the deadline. If past the deadline, it finishes the current iteration, writes final findings, and terminates. This avoids the need for cross-agent signaling.

### Main agent role after dispatch

- Responds to user — does not block
- When critics complete (Focus converge or Explore deadline reached): reads all per-critic findings files, merges into the consolidated findings report, and presents to user
- The main agent writes the Cycle Log, Summary table, and Coverage Map during consolidation. Critics only write their individual findings.

## Focus Mode Workflow

```
User: "evaluate the auth middleware"

1. Main agent identifies target files/scope
   - Searches codebase for relevant files
   - Establishes evaluation boundary

2. Select relevant directions from angle pool
   - e.g., security, code, architecture
   - Decide how many critics to dispatch (1-N based on scope)

3. Dispatch critic agent(s) as long-running background agents
   - Each gets a direction, target scope, calibration reference
   - Each runs its own evaluation loop autonomously

4. Critics iterate internally
   - Evaluate → write findings → rotate angle → repeat
   - Self-terminate when no new findings in a full iteration

5. Main agent consolidates on completion
   - Reads findings file
   - Presents final report to user
```

## Explore Mode Workflow

```
User: "run a deep eval" (or "evaluate the project for 45 minutes")

1. Parse time limit (default 30 min)
   - Calculate deadline timestamp (now + time limit)
   - Pass deadline to each critic at dispatch

2. Survey the project
   - Read structure, recent changes, README, CLAUDE.md
   - Build initial map of areas to explore

3. Dispatch critics as long-running background agents
   - Pick diverse starting directions
   - Assign different project areas to maximize coverage

4. Critics iterate internally
   - Evaluate → write findings → try different angle → repeat
   - Prioritize unexplored directions and areas
   - Go deeper where issues were found
   - Incorporate own suggestions for next angles
   - Check deadline timestamp before each iteration

5. Deadline reached
   - Critics finish current iteration, write final findings, terminate

6. Main agent consolidates
   - Reads all per-critic findings files
   - Merges into consolidated report with cycle log and coverage map
   - Presents final report to user
```

## Finding Format

Each finding:

```markdown
### [F1] Session token stored in localStorage (Critical)
- **Direction**: Security
- **Location**: `auth/session.ts:42-48`
- **Iteration**: 1
- **Status**: Open
- **Description**: Session tokens are written to localStorage, which is
  accessible to any JS running on the page. An XSS vulnerability anywhere
  in the app would expose all user sessions.
- **Evidence**: `localStorage.setItem('session', token)` at line 42
```

Fields: severity (critical/major/minor), direction, location (file + line range), iteration number (within the critic's own loop), status (open), description, evidence (code snippet).

## Findings File Structure

**Per-critic files** (written by each critic during evaluation):
`docs/eval/findings-<timestamp>-<critic-id>.md` — each critic writes only to its own file, avoiding concurrent write conflicts.

**Consolidated report** (written by main agent at consolidation):
`docs/eval/findings-<YYYY-MM-DD-HHMMSS>.md` — main agent reads all per-critic files, deduplicates, assigns global finding IDs (F1, F2, ...), and produces the final report. Critics use local IDs in their own files (e.g., C1-F1, C1-F2); the main agent renumbers them globally during consolidation. Per-critic files are deleted only after the consolidated report is fully written to disk.

Consolidated report format:

```markdown
# Project Evaluation — Focus: auth-middleware
Started: 2026-03-24 14:30
Mode: Focus
Status: Complete (4 cycles)

## Summary
| Severity | Count |
|----------|-------|
| Critical | 1     |
| Major    | 3     |
| Minor    | 2     |

## Findings
(individual findings here)

## Iteration Log

### Critic A (security) — 3 iterations
- Iteration 1: 2 findings (F1, F2)
- Iteration 2: 1 finding (F3)
- Iteration 3: 0 findings → converged

### Critic B (code, architecture) — 2 iterations
- Iteration 1: 2 findings (F4, F5)
- Iteration 2: 1 finding (F6) → converged
```

Explore mode adds a coverage map:

```markdown
## Coverage Map
| Area | Directions Explored |
|------|-------------------|
| auth/ | security, code, architecture |
| frontend/components/ | visual-coherence, accessibility |
| api/routes/ | api-contract, validation |
| **Not explored** | billing/, migrations/, tests/ |
```

## Fan-Out Strategy

The main agent decides how many critics to dispatch based on context:
- **User specifies count**: use that count (e.g., "use 3 critics")
- **User says nothing about count** (most common): use defaults:
  - Focus mode: 1-3 critics based on how many direction clusters are relevant to the target scope (e.g., auth module → security + code + architecture = 3)
  - Explore mode: 3-5 critics to cover the major cluster families and maximize early coverage
- Main agent coordinates direction assignment to avoid overlap between critics
- Each critic gets a distinct direction cluster

**Ambiguous mode detection**: If the user's intent is unclear (e.g., "run a quick eval"), the main agent should ask the user for clarification rather than silently choosing a mode.

**Resource constraints**: If the platform limits concurrent sub-agents, the skill should adapt by reducing fan-out and dispatching remaining directions in subsequent rounds.

## Version

This skill will be added to `dev-skills` as version 3.2.0 (minor feature addition).
