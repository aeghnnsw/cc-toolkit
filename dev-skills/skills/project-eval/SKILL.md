---
name: project-eval
version: 1.0.0
description: This skill should be used when the user asks to "evaluate the project", "run a deep eval", "review this feature", "evaluate the auth module", "find issues", or wants multi-angle project evaluation with long-running critic agents. Dispatches skeptical evaluator agents that iterate through evaluation angles to find issues across code, architecture, security, UX, product, and design dimensions.
---

Dispatch long-running skeptical critic agents to evaluate a project from multiple directions. Inspired by the principle that separating creation from evaluation — and tuning evaluators for skepticism — produces far better quality assessment than self-review.

## Critical Lifecycle Rules

- Critic agents are **long-running team agents** — NEVER kill them unless the user explicitly asks to stop
- Do NOT wait for critics to finish before responding to the user
- Dispatch critics as background agents and inform the user they are running
- Critics self-terminate based on mode: convergence (Focus) or deadline (Explore)

## Mode Detection

| User intent | Mode |
|-------------|------|
| "evaluate auth module", "review the payment flow", "check this feature" | **Focus** |
| "evaluate the project", "run a deep eval", "explore the codebase" | **Explore** |

If ambiguous, ask the user to clarify: "Would you like to focus on a specific feature, or explore the entire project?"

## Focus Mode

Target a specific feature or module. Critics iterate until no new issues are found, then self-terminate.

1. Read `${CLAUDE_PLUGIN_ROOT}/skills/project-eval/references/angles.md` — scan the 8 direction clusters
2. Read `${CLAUDE_PLUGIN_ROOT}/skills/project-eval/references/focus-mode.md` — follow the complete workflow
3. Identify target scope from user's message (search codebase for relevant files)
4. Select 1-3 direction clusters relevant to the target
5. Dispatch critic agents (one per direction, background, long-running)
6. Inform user and respond — do not block
7. Consolidate findings when all critics converge

## Explore Mode

Evaluate the entire project for a time-limited period (default 30 minutes). Critics explore diverse angles until the deadline.

1. Parse time limit from user's message (default: 30 min)
2. Read `${CLAUDE_PLUGIN_ROOT}/skills/project-eval/references/angles.md`
3. Read `${CLAUDE_PLUGIN_ROOT}/skills/project-eval/references/explore-mode.md` — follow the complete workflow
4. Survey the project structure, recent changes, and documentation
5. Dispatch 3-5 critic agents with diverse directions and the deadline timestamp
6. Inform user and respond — do not block
7. Consolidate findings when all critics reach the deadline

## Fan-Out Strategy

- **User specifies count** (e.g., "use 3 critics"): use that count
- **Default — Focus mode**: 1-3 critics based on relevant direction clusters
- **Default — Explore mode**: 3-5 critics to maximize early coverage
- Coordinate direction assignment so critics do not overlap
- If the platform limits concurrent agents, reduce fan-out and dispatch remaining directions after the first batch completes

## Consolidation

When all critics complete, read `${CLAUDE_PLUGIN_ROOT}/skills/project-eval/references/finding-format.md` for the report format, then:

1. Read all per-critic findings files matching `docs/eval/findings-<timestamp>-critic-*.md` (use this run's timestamp)
2. Deduplicate findings (same file + same issue = one finding)
3. Assign global IDs: F1, F2, ... ordered by severity (critical first)
4. Write consolidated report to `docs/eval/findings-<YYYYMMDD-HHMMSS>.md`
5. Delete per-critic files only after the consolidated report is fully written
6. Present the final report to the user

## Direction Clusters (Quick Reference)

Read `angles.md` for full details and calibration examples. The 8 clusters:

1. **Code** — logic, error handling, state, completeness, concurrency
2. **Architecture** — coupling, boundaries, consistency, scalability
3. **Security** — injection, auth, secrets, data privacy
4. **Frontend & Design** — visual coherence, responsiveness, accessibility, components
5. **User Experience** — flow, feedback, discoverability, edge states
6. **Product** — feature gaps, requirement drift, coherence, value
7. **Data & API** — contracts, schema, validation, performance
8. **Documentation & Convention** — project rules, documentation, test quality

These are a starting menu — critics explore freely within their assigned direction.
