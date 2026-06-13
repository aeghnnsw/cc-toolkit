---
name: preflight
description: This skill should be used when the user asks to "preflight", "run the task-loop preflight", "check task-loop prerequisites", "check if task-loop can run", "verify task-loop dependencies", or "enable agent teams for task-loop". It verifies that every skill the task-loop workflow depends on can be loaded in this session and reports needed/installed/missing, then ensures the experimental Agent Teams config is enabled (adjusting settings.json if needed). Run it before specify-aims / create-cycle / run-cycle.
version: 0.1.0
---

# Preflight

## Overview

Verify a session is ready to run the task-loop workflow, and make it ready where possible.
Two checks:
1. **Required skills are loadable** — every skill the task-loop invokes must be available in
   this session; report `needed` / `installed` / `missing`.
2. **Agent Teams config** — the orchestrator needs the experimental feature enabled; **set it**
   in `settings.json` if it is not already.

`specify-aims` / `create-cycle` / `run-cycle` delegate their fail-fast checks here.

## When to use / not use

- **Use** before starting a task-loop run, or whenever a task-loop skill reports a missing
  prerequisite.
- It is a read/verify + a single targeted config write — it does **not** install plugins
  (that needs the user) and does **not** run any task.

## Check 1 — Required skills are loadable

The task-loop invokes the skills below. A skill is loadable **iff it appears in this session's
available-skills list** — that list is exactly "what Claude can load," and it reflects an
installed *and enabled* plugin. **Do not invoke a skill to test it** — invoking
`brainstorming` / `discuss-with-codex` (etc.) would actually *start* it. Instead, check each
name against the available skills.

Required (10 skills across 2 plugins):

- **`superpowers`** — `brainstorming`, `writing-plans`, `test-driven-development`,
  `verification-before-completion`, `using-git-worktrees`, `finishing-a-development-branch`.
- **`dev-skills`** — `discuss-with-codex`, `goal-rubric`, `doc-update`, `step-workflow`.

For each required `plugin:skill`, mark it **installed** (present in available skills) or
**missing** (absent). Report grouped, e.g.:

```
Required (10): superpowers ×6, dev-skills ×4
Installed (9): superpowers:brainstorming, superpowers:writing-plans, …, dev-skills:goal-rubric
Missing  (1): superpowers:test-driven-development
```

For any **missing** skill, give install guidance: install the owning plugin from its
marketplace (`superpowers`, and `dev-skills` from the `cc-toolkit` marketplace) via `/plugin`,
then re-run preflight. List the distinct missing **plugins** so the user installs each once.

## Check 2 — Agent Teams config (set it, don't just check)

`run-cycle` (the orchestrator) needs the **experimental Agent Teams** feature — off by default —
and Claude Code **≥ v2.1.32**. (`specify-aims` and `create-cycle` do **not** need it.)

1. **Check** whether `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` resolves to `1` (already in the
   environment, or in a `settings.json` `env` block).
2. **If it is not set, set it.** Edit `.claude/settings.json` (project scope; use
   `~/.claude/settings.json` for global) to add `"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"`
   inside the top-level `env` object — **merging carefully**: read the file (treat a missing
   file as `{}`), preserve every existing key, create the `env` object only if absent, and write
   valid JSON back. Then tell the user a **session restart is required** for it to take effect.
   The intended result:
   ```json
   { "env": { "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1" } }
   ```
3. **Version:** check `claude --version` ≥ v2.1.32 and report it (this cannot be auto-fixed —
   if older, tell the user to update Claude Code).

## Report

End with a clear verdict:

- ✅ **Ready** — all 10 skills loadable; Agent Teams enabled (note "restart required" if it was
  just set); version OK.
- ❌ **Not ready** — list the missing skills + which plugins to install; note any config change
  made and the restart; note an out-of-date version.

Re-run preflight after installing plugins or restarting.

## Notes

- This is the shared fail-fast for the suite: `specify-aims` / `create-cycle` need only Check 1;
  `run-cycle` needs Check 1 **and** Check 2.
- Detection is intentionally session-based ("can Claude load it?"), not a filesystem scan — an
  installed-but-disabled plugin correctly reads as unavailable.
