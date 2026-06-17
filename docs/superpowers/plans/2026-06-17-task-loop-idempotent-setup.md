# Task-loop Idempotent Setup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update both task-loop setup skills so they check existing machine/repo setup before running setup steps.

**Architecture:** Keep the CLI unchanged and encode the idempotent setup policy in both skill documents. `status` is the early connectivity check, `init` remains the idempotent repo-registration check, and smoke testing becomes conditional.

**Tech Stack:** Markdown skills, YAML frontmatter validation, `task-loop` CLI via `uv`, GitHub CLI.

## Global Constraints

- Modify `task-loop/skills/setup/SKILL.md` and `task-loop/codex-skills/setup/SKILL.md` only for setup behavior.
- Do not change `task-loop/cli/task-loop`.
- Claude setup keeps Agent Teams and `${CLAUDE_PLUGIN_ROOT}` paths.
- Codex setup must not introduce `Agent Teams`, `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`, `${CLAUDE_PLUGIN_ROOT}`, `discuss-with-codex`, or `TodoWrite`.
- `status` proves machine credentials, Supabase connectivity, schema visibility, and git remote project derivation.
- `init` is idempotent and ensures the repo project row exists.
- Smoke test is required when setup changed or when the user asks for write proof; otherwise it is optional.

---

### Task 1: Update setup skills

**Files:**
- Modify: `task-loop/skills/setup/SKILL.md`
- Modify: `task-loop/codex-skills/setup/SKILL.md`

**Interfaces:**
- Consumes: existing task-loop CLI commands `status`, `login`, `init`, `add`, and `close`.
- Produces: setup instructions that skip unnecessary work when setup is already valid.

- [ ] **Step 1: Run red content checks**

Run:

```bash
! rg -q "Check existing setup first" task-loop/skills/setup/SKILL.md
! rg -q "Check Existing Setup First" task-loop/codex-skills/setup/SKILL.md
```

Expected: both commands exit 0 because the sections are absent before implementation.

- [ ] **Step 2: Update Claude setup skill**

In `task-loop/skills/setup/SKILL.md`:

- Add a new section after Step 0 named `Step 1 - Check existing setup first`.
- Move the existing Supabase project/schema/login/init/verify sections down by one step number.
- State that `uv run ${CLAUDE_PLUGIN_ROOT}/cli/task-loop status` is the first setup check.
- State that successful `status` means credentials, Supabase REST connectivity, schema visibility, and project-id derivation are working.
- State that successful `status` means to skip Supabase project creation, schema application, and `login`.
- State that `uv run ${CLAUDE_PLUGIN_ROOT}/cli/task-loop init` is safe to run because it is idempotent and ensures the repo row exists.
- State that the smoke test is only needed if setup changed or the user asks for write proof.
- Keep the Agent Teams section intact.

- [ ] **Step 3: Update Codex setup skill**

In `task-loop/codex-skills/setup/SKILL.md`:

- Add a new section after System Tools named `Check Existing Setup First`.
- State that `uv run task-loop/cli/task-loop status` is the first setup check in this repo checkout.
- State that successful `status` means credentials, Supabase REST connectivity, schema visibility, and project-id derivation are working.
- State that successful `status` means to skip Supabase project creation, schema application, and `login`.
- State that `uv run task-loop/cli/task-loop init` is safe to run because it is idempotent and ensures the repo row exists.
- State that the smoke test is only needed if setup changed or the user asks for write proof.
- Keep the setup/preflight-only note.

- [ ] **Step 4: Run green content checks**

Run:

```bash
rg -q "Check existing setup first" task-loop/skills/setup/SKILL.md
rg -q "Check Existing Setup First" task-loop/codex-skills/setup/SKILL.md
rg -q "skip Supabase project creation, schema application, and" task-loop/skills/setup/SKILL.md
rg -q "skip Supabase project creation, schema application, and" task-loop/codex-skills/setup/SKILL.md
rg -q "idempotent" task-loop/skills/setup/SKILL.md
rg -q "idempotent" task-loop/codex-skills/setup/SKILL.md
```

Expected: all commands exit 0.

- [ ] **Step 5: Validate skills and CLI status**

Run:

```bash
uv run --with pyyaml python /Users/steven/.codex/skills/.system/skill-creator/scripts/quick_validate.py task-loop/codex-skills/setup
uv run task-loop/cli/task-loop status
```

Expected:

```text
Skill is valid!
aeghnnsw/cc-toolkit: no tasks
```

- [ ] **Step 6: Check Codex forbidden terms and formatting**

Run:

```bash
uv run --with pyyaml python - <<'PY'
from pathlib import Path
text = Path("task-loop/codex-skills/setup/SKILL.md").read_text()
for term in ("Agent Teams", "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", "${CLAUDE_PLUGIN_ROOT}", "discuss-with-codex", "TodoWrite"):
    assert term not in text, term
PY
git diff --check
```

Expected: both commands exit 0.

- [ ] **Step 7: Commit**

```bash
git add task-loop/skills/setup/SKILL.md task-loop/codex-skills/setup/SKILL.md
git commit -m "feat: make task-loop setup skills check existing config"
```

### Task 2: Final validation and PR

**Files:**
- Verify: changed files

**Interfaces:**
- Consumes: Task 1.
- Produces: pushed branch and PR closing #148.

- [ ] **Step 1: Run final verification**

Run:

```bash
uv run --with pyyaml python /Users/steven/.codex/skills/.system/skill-creator/scripts/quick_validate.py task-loop/codex-skills/setup
uv run task-loop/cli/task-loop status
git diff --check
git status --short --branch
```

Expected: skill validation succeeds, CLI status returns this repo, no whitespace errors, and the branch is clean before push.

- [ ] **Step 2: Push and create PR**

Run:

```bash
git push -u origin feat-148-idempotent-task-loop-setup
gh pr create --title "Make task-loop setup skills check existing config" --body "Updates both task-loop setup skills to check existing machine and repo setup before walking through setup steps.\n\nSuccessful status now skips project creation, schema application, and login; init remains the idempotent repo readiness check.\n\nCloses #148" --base master --head feat-148-idempotent-task-loop-setup
```
