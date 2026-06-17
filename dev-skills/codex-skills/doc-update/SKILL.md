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
