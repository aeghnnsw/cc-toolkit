# pr-feedback Step 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite Step 2 of the `pr-feedback` skill to prescribe a deterministic background wait mechanism, make empty-external behavior explicit, and reinforce autonomy.

**Architecture:** Single Markdown skill file edit plus two semver version bumps. No code, no tests — skill behavior is verified qualitatively by re-reading the rewritten Step 2.

**Tech Stack:** Markdown (skill doc), JSON (plugin manifest), Git.

**Spec:** `docs/superpowers/specs/2026-05-14-pr-feedback-step2-design.md`

---

### Task 1: Apply Step 2 redesign and bump versions

**Files:**
- Modify: `dev-skills/skills/pr-feedback/SKILL.md` (frontmatter line 3; Step 2 body lines 33–43)
- Modify: `dev-skills/.claude-plugin/plugin.json` (version field line 4)

- [x] **Step 1: Replace the Step 2 body in SKILL.md**

Open `dev-skills/skills/pr-feedback/SKILL.md`. Replace the existing Step 2 block (the section header `## Step 2: Gather External Reviews` and the lines up to but not including `## Step 3: Consolidate Issues`) with this exact text:

```markdown
## Step 2: Gather External Reviews

External reviewers (e.g., GitHub Actions bots, Claude Code Review) are typically triggered when the PR is pushed and run in parallel with the self-review. They often take longer to complete than the self-review.

**Wait via a background-scheduled delay, then read comments:**

1. After self-review completes, schedule a 2-minute background wait. Use the Bash tool with `run_in_background: true` and the command `sleep 120`. End your turn after firing — the harness will notify when the wait completes. Do not poll, do not run a foreground `sleep`, do not chain other tool calls in the same turn to check on the wait.

2. After the notification, read all reviewer comments on the PR — review summaries, inline review comments, and general PR comments. Extract actionable feedback items.

3. **If no external reviews exist after the wait, proceed to Step 3 with self-review issues only.** Do not extend the wait. Do not ask the user. The Step 6 loop will catch any late-arriving comments in a subsequent cycle — that's by design.

**Never ask the user for input during this step.** Not to wait longer, not to confirm, not to add reviewers. The full step is autonomous.

```

Preserve the blank line between this section and `## Step 3: Consolidate Issues`.

- [x] **Step 2: Bump the skill frontmatter version**

In the same file `dev-skills/skills/pr-feedback/SKILL.md`, change frontmatter line 3:

```yaml
version: 3.1.0
```

to:

```yaml
version: 3.2.0
```

- [x] **Step 3: Bump the plugin manifest version**

Edit `dev-skills/.claude-plugin/plugin.json`. Change:

```json
"version": "3.4.0"
```

to:

```json
"version": "3.5.0"
```

- [x] **Step 4: Verify the diff**

Run:

```bash
git diff dev-skills/skills/pr-feedback/SKILL.md dev-skills/.claude-plugin/plugin.json
```

Expected output:
- `SKILL.md`: version bump on line 3, Step 2 block replaced with the new prose. No other changes.
- `plugin.json`: single version field change from `3.4.0` to `3.5.0`.
- Confirm: no whitespace-only edits to surrounding sections; Step 1, Step 3, and other steps untouched.

If anything outside the intended scope changed, fix before committing.

- [x] **Step 5: Sanity-check against the failure modes**

Re-read the rewritten Step 2 and answer each question; all three must be "yes":
- Does it prescribe a specific mechanism (Bash + `run_in_background: true` + `sleep 120`)? — defeats "hangs / skips".
- Does it explicitly say to proceed to Step 3 if external is empty after the wait? — defeats "asks user / waits forever".
- Does it forbid asking the user for input? — defeats "asks user mid-step".

If any answer is no, return to Step 1 of this task and revise.

- [x] **Step 6: Commit**

```bash
git add dev-skills/skills/pr-feedback/SKILL.md dev-skills/.claude-plugin/plugin.json
git commit -m "Redesign pr-feedback Step 2 wait mechanism"
```

---

### Task 2: Push branch and open PR

**Files:** None (git/gh operations only)

- [x] **Step 1: Push the branch**

```bash
git push -u origin bugfix-pr-feedback-step2
```

The project's branch-naming hook requires one of the approved prefixes (`feat-`, `bugfix-`, `doc-`, `refactor-`, `chore-`, `test-`); this branch already satisfies that with `bugfix-`.

- [x] **Step 2: Open the PR**

```bash
gh pr create --title "Redesign pr-feedback Step 2 wait mechanism" --body "$(cat <<'EOF'
## Summary

- Prescribe an exact background-scheduled wait mechanism (`run_in_background: true` + `sleep 120`) instead of the vague "wait 2 minutes" instruction.
- Make the empty-external-reviews case explicit: proceed to Step 3 with self-review issues only; the Step 6 loop catches late-arriving comments.
- Reinforce the autonomy clause with specific anti-patterns to prevent agents from prompting the user mid-step.

Closes the "agent gets stuck on Step 2" failure modes observed in practice: never waits, waits forever, or asks the user mid-step.

Spec: `docs/superpowers/specs/2026-05-14-pr-feedback-step2-design.md`
EOF
)"
```

- [x] **Step 3: Confirm PR URL**

The `gh pr create` command prints the PR URL on success. Note it for the next phase (pr-feedback cycle).

---

## Post-Plan Workflow

After both tasks complete, the user will typically run `/pr-feedback` to exercise the self-review → external-review → fix-and-push cycle on this very PR. That cycle will be the first real test of the redesigned Step 2.

Cleanup after merge: `gh pr merge --squash --delete-branch` followed by `git fetch --prune` from the main repo (not the worktree). The worktree itself can be removed via ExitWorktree.
