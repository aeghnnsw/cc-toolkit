---
name: doc-update
description: This skill should be used when the user asks to "update the docs", "update documentation", "refresh the README", "the docs are out of date", "update X to reflect Y", "audit this doc", "clean up the documentation", or wants existing documentation brought to current truth and checked for quality. It edits existing docs in place (not issue- or PR-tracked development work), moves change history to a separate CHANGELOG, and audits the result against a documentation quality rubric.
---

# Doc Update

## Overview

Update existing documentation so it reflects only the current, correct state of the project, then audit the result against a quality rubric before finishing. Change history is never narrated inside the docs themselves — it is recorded in the project's changelog, by default a central `CHANGELOG.md`. This keeps documentation clean for both humans and AI agents.

This skill both **updates** (applies new/changed information and cleans the prose) and **audits** (scores the result against a rubric as a quality gate). The audit runs after the edit so it catches regressions the update itself may introduce.

## Core principle: living documents

- **Main docs contain only current truth.** State how things are now, in the present tense.
- **No backward narrative.** Remove "previously…", "used to…", "we changed…", "as of v1 this was…". Such history belongs in the CHANGELOG, not in instructions or concept explanations.
- **Forward-looking pointers are allowed** because they describe the current state: a one-line deprecation or migration note (`` `oldFn` is deprecated; use `newFn` ``) is current truth an agent needs.
- **Rationale:** an AI agent retrieving a fragment of a doc may surface the "before" without the "after," then act on the wrong value. Current-truth-only prose removes that failure mode. The rule is not "no temporal information" — it is "no backward narrative; only the current state and where to go next."

## When to use

Use this skill to refresh, correct, or clean up documentation that already exists. Do **not** use it to author brand-new documentation from scratch.

## Workflow

### 1. Locate target docs

- Use the path(s) the user specifies.
- If none are specified, scan standard locations: `README.md`, files under `docs/`, top-level `*.md`, and `SKILL.md` / `AGENTS.md` / `CLAUDE.md` / `GEMINI.md` (only if the request mentions skills, agents, or Claude Code or Antigravity configuration). List what was found and confirm scope before editing.
- If nothing is found and nothing was specified, ask the user where the docs are.

### 2. Read and classify

Read each target fully, then identify its Diátaxis type (the framework's four documentation types, shown below) and keep edits true to it. Mixing types in one doc is the most common quality defect — note any mixing for Step 4.

| Type | Purpose | Keep it… |
|------|---------|----------|
| **Tutorial** | Learning by doing | Concrete, guided, minimal theory |
| **How-to guide** | Accomplishing a specific goal | Task-focused steps, no digressions |
| **Reference** | Looking up facts | Precise, complete, free of interpretation |
| **Explanation** | Understanding *why* | Discursive, no step-by-step instructions |

### 3. Establish current truth

- Combine the user's new information with the actual sources of truth.
- For checkable claims (commands, file paths, APIs, config, version numbers), verify against the codebase or linked specs rather than trusting the existing prose.
- **Never invent facts.** If current truth cannot be verified, flag the uncertainty in the report instead of guessing or silently keeping old text.

### 4. Apply updates (tiered)

**Auto-apply (safe — no approval needed):**

- Correct inaccurate or outdated statements.
- Rewrite to current-truth-only; strip backward-looking history (route it to Step 5).
- De-duplicate repeated content; keep one canonical statement per fact.
- Improve clarity: active voice, present tense, define each term once, remove undefined jargon.
- Improve self-containment: replace "see above" / "as mentioned earlier" with explicit references so each section stands alone.
- Trim filler and marketing language.

**Propose first (structural — needs approval):**

- Splitting a type-mixed doc into separate files (e.g., reference vs. tutorial).
- Major reorganization, or renaming/moving files.

Present the rationale and a concrete plan; apply only after the user approves.

### 5. Record history in the CHANGELOG

Record each **substantive** change in the changelog. If the project documents its changelog place or format, for example in `CONTRIBUTING.md`, `GEMINI.md`, `AGENTS.md`, or `CLAUDE.md`, follow it. Otherwise add an entry, newest first, under `## [Unreleased]` in a single central `CHANGELOG.md` at the repository root — or inside `docs/` if that is where documentation lives (create it if missing) — in the format below.

- **Substantive** = a change in meaning, described behavior, instructions, or facts.
- **Not substantive** = wording, formatting, typo, or reordering — do not log these.
- **Keep past entries.** Never edit or remove them.
- Keep entries factual and short. The CHANGELOG is the home for the "before"; the doc keeps only the "after."

Format (Keep a Changelog style):

```markdown
## [Unreleased]
### Changed
- README: install steps now use pnpm instead of npm
### Removed
- docs/api.md: dropped the deprecated v1 auth section
```

### 6. Audit gate

Run the doc check on the target docs (Python 3.9 or newer, standard library only). Do not check the changelog; it holds history by design.

```bash
python3 <skill-dir>/scripts/doc_check.py <doc>...
```

Here `<skill-dir>` is this skill's directory. The check prints one finding per line as `<doc>:<line>: <rule>: <detail>`, and a summary line. `--help` lists its phrases. Act on each finding:

- `broken-link` or `broken-anchor`: a relative link, or its `#anchor`, does not resolve. Fix it. The check exits 1 while one remains.
- `path`: a relative path in inline code does not exist from the doc's folder or from the repository root. Fix it, unless the path is relative to another folder or names a file that the reader creates.
- `history`: a backward-narrative phrase. Move the history to the changelog (Step 5) and keep the current state, unless the phrase is part of a forward-looking pointer.
- `see-above`: a vague reference. Replace it with an explicit reference.

The phrase lists do not find every backward narrative or vague reference; read for the others. When the check exits 2 or cannot run, report the reason and check the links and paths by reading.

Score the updated doc against the rubric below. Auto-fix any safe residuals found, then run the check and score the doc again, once. **Do not report the task complete** until every dimension passes, or the remaining items are explicitly deferred — either by the user (typically the structural changes from Step 4), or because a dimension fails on a pre-existing content gap beyond this update's scope (e.g., missing edge-case docs that must be authored fresh). Flag such out-of-scope gaps in the report rather than blocking completion.

| # | Dimension | Pass check |
|---|-----------|-----------|
| 1 | Accuracy & currency | Every statement matches present reality; one canonical statement per fact; the check finds no broken link or anchor. |
| 2 | Type purity | Doc stays one Diátaxis type; no tutorial hand-holding in reference, no "why" essays in how-to. |
| 3 | Findability & structure | Descriptive title, clean `H2`/`H3` hierarchy, one concept per section. |
| 4 | Self-containment | Each section makes sense extracted alone; references are explicit; no `see-above` finding remains. |
| 5 | Clarity | Plain language, active voice, present tense, terms defined once. |
| 6 | Conciseness | No redundancy, filler, or marketing; minimal tokens for the meaning. |
| 7 | Completeness | Prerequisites, happy path, examples, and error/edge cases covered. |
| 8 | Consistency | Uniform terminology, naming, and formatting across the doc set. |
| 9 | No embedded history | No backward narrative in prose; history lives in the CHANGELOG; each remaining `history` finding is part of a forward-looking pointer. |

### 7. Report

Summarize, with evidence:

- Files changed: the `git diff --stat` output for the changed docs and the changelog, and a one-line description of each file. Name each file that Git does not track.
- CHANGELOG entry written (or "no substantive change — not logged").
- The output of the last doc check, and the reason that each remaining finding stays.
- Each claim verified in Step 3, with the file or command that confirmed it.
- Rubric scorecard (pass / flag per dimension). Each flag cites a file and line as `<file>:<line>`, and its reason.
- Any structural changes proposed and awaiting approval.

## Safety rules

- **Look before overwriting:** do not delete content whose correctness cannot be assessed; flag it for the user instead.
- Respect the doc's existing voice, structure, and formatting conventions unless they violate the rubric.
- Confirm before large deletions or file splits.
- Never edit or remove past CHANGELOG entries.
