# Codex Task-loop Setup Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `task-loop` Codex-installable with a setup/preflight skill only.

**Architecture:** Add a Codex plugin manifest and a separate `codex-skills/` tree so Codex-facing instructions do not inherit Claude-only setup behavior. Add a repo-local Codex marketplace entry now so the setup skill can be loaded and tested, while metadata clearly limits this slice to setup/preflight.

**Tech Stack:** Codex plugin manifest JSON, repo-local Codex marketplace JSON, Codex `SKILL.md` frontmatter, existing `task-loop/cli/task-loop` via `uv`, GitHub CLI via `gh`.

## Global Constraints

- Preserve existing Claude task-loop files unchanged.
- Marketplace entry is intentional in this slice so users can load and test setup.
- Metadata and setup skill must not imply `specify-aims`, `create-cycle`, or `run-cycle` support.
- Codex-facing files must not mention `Agent Teams`, `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`, `${CLAUDE_PLUGIN_ROOT}`, `discuss-with-codex`, or `TodoWrite`.
- Required Codex skills are `superpowers:{brainstorming, writing-plans, test-driven-development, verification-before-completion, receiving-code-review}` and `dev-skills:{pressure-test, goal-rubric, doc-update}`.
- Keep issue and PR text concise and attribution-free.

---

### Task 1: Add Codex manifest and marketplace entry

**Files:**
- Create: `task-loop/.codex-plugin/plugin.json`
- Modify: `.agents/plugins/marketplace.json`

**Interfaces:**
- Consumes: existing `task-loop/.claude-plugin/plugin.json` identity and version.
- Produces: a Codex plugin manifest pointing to `./codex-skills/`, and a marketplace entry at `./task-loop`.

- [ ] **Step 1: Run red manifest and marketplace checks**

Run:

```bash
test ! -e task-loop/.codex-plugin/plugin.json
! jq -e '.plugins[] | select(.name == "task-loop")' .agents/plugins/marketplace.json >/dev/null
```

Expected: exit 0 because the Codex manifest and marketplace entry are absent before implementation.

- [ ] **Step 2: Create `task-loop/.codex-plugin/plugin.json`**

Create this exact manifest:

```json
{
  "name": "task-loop",
  "version": "0.15.0",
  "description": "Task-loop setup and preflight support for Codex.",
  "author": {
    "name": "Steven",
    "email": "aeghnnsw@users.noreply.github.com"
  },
  "repository": "https://github.com/aeghnnsw/cc-toolkit",
  "license": "MIT",
  "keywords": [
    "task-loop",
    "setup",
    "preflight",
    "supabase",
    "workflow"
  ],
  "skills": "./codex-skills/",
  "interface": {
    "displayName": "Task Loop",
    "shortDescription": "Setup and preflight for task-loop in Codex.",
    "longDescription": "Use Task Loop to configure the hosted Supabase task board, save local credentials, register a repository, and verify setup. Codex support is rolling out in phases; this slice supports setup and preflight only.",
    "developerName": "Steven",
    "category": "Developer Tools",
    "capabilities": [
      "Read",
      "Write"
    ],
    "defaultPrompt": [
      "Set up task-loop for this repo.",
      "Check task-loop prerequisites."
    ]
  }
}
```

- [ ] **Step 3: Add marketplace entry**

Append this entry to `.agents/plugins/marketplace.json` after `dev-skills`:

```json
{
  "name": "task-loop",
  "source": {
    "source": "local",
    "path": "./task-loop"
  },
  "policy": {
    "installation": "AVAILABLE",
    "authentication": "ON_INSTALL"
  },
  "category": "Developer Tools"
}
```

- [ ] **Step 4: Run green manifest and marketplace checks**

Run:

```bash
jq . task-loop/.codex-plugin/plugin.json >/dev/null
jq . .agents/plugins/marketplace.json >/dev/null
jq -e '.skills == "./codex-skills/" and (.interface.longDescription | contains("setup and preflight only"))' task-loop/.codex-plugin/plugin.json
jq -e '.plugins[] | select(.name == "task-loop" and .source.path == "./task-loop" and .policy.installation == "AVAILABLE" and .policy.authentication == "ON_INSTALL")' .agents/plugins/marketplace.json >/dev/null
```

Expected: all commands exit 0.

- [ ] **Step 5: Commit**

```bash
git add task-loop/.codex-plugin/plugin.json .agents/plugins/marketplace.json
git commit -m "feat: add Codex task-loop plugin metadata"
```

### Task 2: Add Codex setup skill

**Files:**
- Create: `task-loop/codex-skills/setup/SKILL.md`

**Interfaces:**
- Consumes: `task-loop/cli/task-loop`, `task-loop/db/schema.sql`, `uv`, `gh`, and the Codex skills listed in Global Constraints.
- Produces: a single Codex-discoverable skill named `setup`.

- [ ] **Step 1: Run red setup skill discovery check**

Run:

```bash
test ! -e task-loop/codex-skills/setup/SKILL.md
! find task-loop/codex-skills -mindepth 2 -maxdepth 2 -name SKILL.md 2>/dev/null | grep -q .
```

Expected: exit 0 because no Codex task-loop skill exists before implementation.

- [ ] **Step 2: Create `task-loop/codex-skills/setup/SKILL.md`**

Create the skill with this frontmatter:

```markdown
---
name: setup
description: Use when setting up task-loop in Codex, configuring the Supabase backend, saving task-loop credentials, registering a repo, checking prerequisites, running preflight, or performing a setup smoke test.
---
```

The body must include these sections:

```markdown
# Task-loop Setup

Prepare this machine and repository for task-loop's hosted task board. This Codex skill supports setup and preflight only. `specify-aims`, `create-cycle`, and `run-cycle` are pending Codex ports.

## Preconditions

- Work from the repository root.
- Use the plugin checkout path when running commands in this repository: `uv run task-loop/cli/task-loop ...`.
- If task-loop is installed from the Codex plugin cache, first locate the installed plugin root and run `uv run <plugin-root>/cli/task-loop ...`.
- Never commit Supabase credentials. The CLI stores credentials in `$XDG_CONFIG_HOME/task-loop/config` or `~/.config/task-loop/config` with mode `0600`.

## Required Skills

Confirm these skills are available in the session before considering task-loop ready:

- `superpowers:brainstorming`
- `superpowers:writing-plans`
- `superpowers:test-driven-development`
- `superpowers:verification-before-completion`
- `superpowers:receiving-code-review`
- `dev-skills:pressure-test`
- `dev-skills:goal-rubric`
- `dev-skills:doc-update`

If any are missing, report the missing skill names and stop after completing any requested setup checks. Do not claim full task-loop readiness.

## System Tools

Run:

```bash
uv --version
gh auth status
```

If `uv` is missing, stop and ask the user to install it. If `gh` is missing or unauthenticated, setup can save task-loop credentials but the later loop cannot run GitHub work.

## Supabase Project

Task-loop uses the user's hosted Supabase project. If the user does not already have one, have them create it in the Supabase dashboard and collect:

- Project URL
- API key

For a trusted single-operator setup, use the `service_role` key. Treat the key as a secret.

## Apply Schema

Apply `task-loop/db/schema.sql` once per Supabase project. The REST CLI cannot run DDL, so use the Supabase SQL Editor, Supabase CLI, or `psql`:

```bash
psql "$CONNECTION_STRING" -f task-loop/db/schema.sql
```

The schema is idempotent.

## Save Credentials

Run:

```bash
uv run task-loop/cli/task-loop login
```

The CLI prompts for the Project URL and API key and writes a local `0600` config file.

## Register Repository

From the repository root, run:

```bash
uv run task-loop/cli/task-loop init
```

The project id is derived from `git remote get-url origin`.

## Smoke Test

Run:

```bash
uv run task-loop/cli/task-loop add "setup smoke test"
uv run task-loop/cli/task-loop status
uv run task-loop/cli/task-loop close <seq>
```

Replace `<seq>` with the sequence printed by `add`. The smoke test proves credentials, schema, and repo registration are working.

## Result

Report:

- tool checks run and their result;
- whether credentials were saved or already available;
- whether repo registration succeeded;
- smoke-test sequence and closure result;
- missing required skills, if any;
- that Codex task-loop support is currently setup/preflight only.
```

- [ ] **Step 3: Run green setup skill validation**

Run:

```bash
uv run --with pyyaml python /Users/steven/.codex/skills/.system/skill-creator/scripts/quick_validate.py task-loop/codex-skills/setup
find task-loop/codex-skills -mindepth 2 -maxdepth 2 -name SKILL.md | sort
```

Expected:

```text
Skill is valid!
task-loop/codex-skills/setup/SKILL.md
```

- [ ] **Step 4: Check description concision and Claude-only terms**

Run:

```bash
uv run --with pyyaml python - <<'PY'
from pathlib import Path
import yaml
text = Path("task-loop/codex-skills/setup/SKILL.md").read_text()
front = text.split("---", 2)[1]
desc = yaml.safe_load(front)["description"]
print(desc)
print(len(desc))
assert len(desc) <= 220
for term in ("Agent Teams", "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", "${CLAUDE_PLUGIN_ROOT}", "discuss-with-codex", "TodoWrite"):
    assert term not in text, term
PY
```

Expected: prints the description and length, then exits 0.

- [ ] **Step 5: Commit**

```bash
git add task-loop/codex-skills/setup/SKILL.md
git commit -m "feat: add Codex task-loop setup skill"
```

### Task 3: Final validation and PR

**Files:**
- Verify: all changed files

**Interfaces:**
- Consumes: Tasks 1 and 2.
- Produces: pushed branch and PR closing #146.

- [ ] **Step 1: Validate JSON and skill discovery**

Run:

```bash
jq . task-loop/.codex-plugin/plugin.json >/dev/null
jq . .agents/plugins/marketplace.json >/dev/null
uv run --with pyyaml python /Users/steven/.codex/skills/.system/skill-creator/scripts/quick_validate.py task-loop/codex-skills/setup
find task-loop/codex-skills -mindepth 2 -maxdepth 2 -name SKILL.md | sort
```

Expected:

```text
Skill is valid!
task-loop/codex-skills/setup/SKILL.md
```

- [ ] **Step 2: Validate unchanged Claude files and setup CLI**

Run:

```bash
git diff -- task-loop/.claude-plugin/plugin.json task-loop/skills/setup/SKILL.md task-loop/README.md task-loop/agents/cycle-worker.md
uv run task-loop/cli/task-loop status
```

Expected: no diff for Claude-facing files. If `uv run task-loop/cli/task-loop status` fails because local credentials are unavailable, report the failure and continue; do not treat missing local credentials as a code failure.

- [ ] **Step 3: Check formatting**

Run:

```bash
git diff --check
git status --short --branch
```

Expected: no whitespace errors. Status should show only intended tracked changes before final commit, and clean after commits.

- [ ] **Step 4: Push and create PR**

Run:

```bash
git push -u origin feat-146-codex-task-loop-setup
gh pr create --title "Add Codex task-loop setup support" --body "Makes task-loop Codex-installable for setup and preflight testing.\n\nAdds the Codex plugin manifest, marketplace entry, and setup skill while leaving full task-loop execution for later slices.\n\nCloses #146" --base master --head feat-146-codex-task-loop-setup
```
