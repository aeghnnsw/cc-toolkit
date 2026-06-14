---
name: preflight
description: This skill should be used when the user asks to "preflight", "run the task-loop preflight", "check task-loop prerequisites", "check if task-loop can run", "verify task-loop dependencies", or "enable agent teams for task-loop". It checks two scopes — whether the skills the task-loop depends on are loadable in this session (re-run safely any time), and whether the experimental Agent Teams feature is enabled on this machine (a one-time settings.json write). Run it when setting up a machine and at the start of a task-loop session.
version: 0.1.0
---

# Preflight

## Overview

Verify a session/machine is ready to run the task-loop workflow. Two checks, **two scopes**:

- **Check 1 — required skills (this *session*):** are the skills the task-loop invokes loadable
  right now? This is session/project state — re-run preflight whenever you start a task-loop
  session; it is cheap and idempotent.
- **Check 2 — Agent Teams config (this *machine*):** is the experimental feature enabled in
  `settings.json`? If not, set it — a one-time, machine-wide write (then a restart).

`specify-aims` / `create-cycle` need only Check 1; `run-cycle` needs both.

## When to use / not use

- **Use** when setting up a machine for the task-loop, and at the start of a task-loop session
  to re-verify the skills are loadable.
- It is a verify + a single, guarded config write — it does **not** install plugins (that needs
  the user) and does **not** run any task.

## Check 1 — Required skills are loadable (this session)

The task-loop invokes the skills below. A skill is loadable **iff it appears in this session's
available-skills list** (that list reflects an installed *and enabled* plugin). **Do not invoke
a skill to test it** — invoking `brainstorming` / `discuss-with-codex` (etc.) would actually
*start* it. Check each name against the available skills instead.

Required (9 skills across 2 plugins):

- **`superpowers`** — `brainstorming`, `writing-plans`, `test-driven-development`,
  `verification-before-completion`, `finishing-a-development-branch`. (Each `cycle-worker`
  self-provisions its own git worktree at invocation — in-process Teams do not honor an
  `isolation: worktree` declaration, and it does **not** use `using-git-worktrees`.)
- **`dev-skills`** — `discuss-with-codex`, `goal-rubric`, `doc-update`, `step-workflow`.

**Matching (owner-verified preferred):** the task-loop depends on these *specific plugins'*
skills, not just any skill with the same name. Match the fully-qualified `plugin:skill`
(case-insensitive) — the available-skills list normally shows entries that way
(`superpowers:brainstorming`, `dev-skills:discuss-with-codex`). Classify each required skill:

- **installed** — a skill from the expected plugin is available;
- **present, owner-unverified** — only a same-named skill is available and the list does not
  expose the owning plugin (a personal/other-plugin `brainstorming` is **not** the dependency);
- **missing** — no skill of that name is available.

## Check 2 — Agent Teams config (this machine)

`run-cycle` needs **experimental Agent Teams** (off by default) and Claude Code **≥ v2.1.32**.

**Source of truth = `settings.json`.** A shell env var of the same name is informational only —
the agent cannot reliably read the running session's resolved process env, so decide the write
from the settings file.

**Target = global `~/.claude/settings.json`** (machine-wide, matching "set it once per machine"
and the rest of this repo's settings-writing skills). Use a project `.claude/settings.json` only
as a deliberate exception, and warn the user it is often version-controlled and shared.

**Guarded write (mirror `cc-customize/skills/model-config`):**
1. **Read** `~/.claude/settings.json`. **Refuse and stop** (report exactly what to fix, edit
   nothing) if it does **not** parse as a JSON object, or if `env` exists but is not an object
   (a scalar/array) — a "surgical" edit on malformed config would corrupt it.
2. If the file is **absent** → `Write`:
   ```json
   { "env": { "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1" } }
   ```
3. If it **exists and is a valid object** → use the **`Edit`** tool to add/replace **only** the
   `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` key inside the existing `env` object (create `env` only
   if absent). **Preserve every other key.** The value is the **quoted string `"1"`**, not `1`.
4. If you just wrote it, a **session restart** is required for it to take effect.

**Version:** report `claude --version` (must be ≥ v2.1.32 — cannot be auto-fixed; tell the user
to update if older).

## Report (two scopes, text labels — no emoji)

- **Machine config:** `ENABLED` · `JUST-CONFIGURED (restart required)` · `BLOCKED (settings.json
  needs a manual fix: …)` · `VERSION TOO OLD (have X, need ≥ v2.1.32)`.
- **Session readiness:** `ALL LOADABLE` · `OWNER-UNVERIFIED (list which)` · `MISSING (list +
  which plugin to install)`.
- **Overall:** `READY` only when every required skill is **installed** (owner-verified) **and**
  Agent Teams is **ENABLED**. A *just-configured* (pending restart) machine, an
  *owner-unverified* skill, an old version, or any missing skill → `NOT READY`, with the specific
  blocker and next step (install plugin via `/plugin`; restart; update the CLI).

Re-run preflight after installing plugins or restarting.

## Notes

- Detection is session-based ("can Claude load it *now*?"), not a filesystem scan — an
  installed-but-disabled plugin correctly reads as unavailable, and a "Ready" from one session
  does not carry to a different project/session, so re-run it per task-loop session.
- The config write is the only durable, machine-wide effect; running preflight again is a no-op
  once the key is set.
