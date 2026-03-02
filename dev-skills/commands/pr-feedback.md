---
description: Gather and address PR feedback from all reviewers
argument-hint: []
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, AskUserQuestion, Skill, Task
model: opus
---

<!--
This command orchestrates a full PR feedback cycle that loops until clean:
1. Self-review (loads relevant skills automatically)
2. Read external reviewer comments (after self-review finishes, giving reviewers time)
3. Consolidate all issues into a single list
4. Investigate and fix valid issues, skip invalid ones
5. Commit and push
6. Loop back to Step 1 until no new issues found
7. When clean, ask user about merge

Uses: gh CLI for PR operations
-->

Gather and address all feedback on the current PR through a structured review-fix-push cycle.

## Step 0: Pre-flight Check

Verify the current branch has an associated PR:
```bash
gh pr view --json number -q '.number'
```
If this fails, inform the user they need to be on a branch with an open PR and exit.

## Step 1: Self-Review

Load any relevant review skills available, then review the current PR for bugs, logic errors, and code quality issues. List **all** potential issues found regardless of severity or confidence — do not filter or skip any.

Save the full list for consolidation in Step 3.

## Step 2: Gather External Reviews

Read all other reviewer comments on the PR — including review comments, inline comments, and general PR comments. Extract actionable feedback items.

## Step 3: Consolidate Issues

Merge **all** issues from Step 1 (self-review) and Step 2 (external reviews) into a single deduplicated list. Include every issue regardless of its original score or severity — all issues are treated equally from this point forward.

Present the consolidated list to the user:

```
## Consolidated PR Issues

| # | Issue | Source | Severity |
|---|-------|--------|----------|
| 1 | Description of issue | self-review / reviewer-name | high/medium/low |
| 2 | ... | ... | ... |
```

If no issues were found from any source, inform the user the PR looks clean and skip to Step 7.

## Step 4: Investigate and Fix

For each issue in the consolidated list, investigate one by one:

1. **Investigate**: Read the relevant code, understand the context, and determine if the issue is valid.

2. **If valid**: Fix the issue, even if minor. Make the minimal change needed.

3. **If invalid**: Skip it with a brief explanation of why (e.g., "false positive — the null check already exists on line 42").

After processing each issue, report the outcome:

```
## Issue Resolution

| # | Issue | Verdict | Action |
|---|-------|---------|--------|
| 1 | Description | Valid | Fixed in path/to/file.ts |
| 2 | Description | Invalid | Already handled by ... |
```

## Step 5: Commit and Push

If any fixes were made in Step 4:

1. Stage the changed files (specific files, not `git add .`)
2. Create a commit with a message summarizing the fixes (e.g., "Address PR review feedback")
3. Push to the remote branch:
   ```bash
   git push
   ```

If no fixes were needed, skip this step.

## Step 6: Loop

After fixes are committed and pushed, go back to Step 1 to run a full review cycle again. The self-review will catch any issues introduced by the fixes, and external reviewer comments will be re-read for any new feedback.

Repeat until no new issues are found in Step 3, then proceed to Step 7.

## Step 7: Merge Decision

When no new issues are found, summarize the overall PR state:
- Total issues found (across all cycles)
- Issues fixed
- Issues skipped (with reasons)

Use **AskUserQuestion**: "PR feedback cycle complete. No new issues found. What would you like to do?"
- Options: "Merge the PR", "I'll handle it manually"

**If "Merge the PR":**
```bash
gh pr merge $(gh pr view --json number -q '.number') --squash
```
After successful merge, inform the user to clean up their worktree and local branch if applicable.

**If "I'll handle it manually":** Exit.
