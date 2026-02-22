---
description: Gather and address PR feedback from all reviewers
argument-hint: []
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, AskUserQuestion, Skill, Task
model: opus
---

<!--
This command orchestrates a full PR feedback cycle:
1. Self-review using code-review skill
2. Gather external reviewer comments (GitHub Actions, human reviewers)
3. Consolidate all issues into a single list
4. Investigate and fix valid issues, skip invalid ones
5. Commit and push
6. Re-review and decide on merge readiness

Uses: gh CLI for PR operations, code-review skill for structured review
-->

Gather and address all feedback on the current PR through a structured review-fix-push cycle.

## Step 0: Pre-flight Check

Verify the current branch has an associated PR:
```bash
gh pr view --json number -q '.number'
```
If this fails, inform the user they need to be on a branch with an open PR and exit.

## Step 1: Self-Review

Invoke the `code-review:code-review` skill to review the current PR. This produces a structured review with confidence-based filtering.

> **Note:** The `code-review` skill is an external dependency (not part of this repository). If the skill is not available, fall back to manually reviewing the PR diff with `gh pr diff` and identifying potential issues.

After the review completes, save the list of issues found for consolidation in Step 3.

## Step 2: Gather External Reviews

Use **AskUserQuestion**: "Have all external reviewers (GitHub Actions, teammates) posted their comments on the PR?"
- Options: "Yes, all reviews are in", "Not yet, I'll wait", "Skip external reviews"

**If "Not yet":** Inform the user to re-run `/pr-feedback` when reviews are ready, then exit.

**If "Yes" or "Skip":**

When not skipping, read all PR review comments:

1. Get the PR number and repo:
   ```bash
   PR_NUMBER=$(gh pr view --json number -q '.number')
   REPO=$(gh repo view --json nameWithOwner -q '.nameWithOwner')
   ```

2. Read PR review comments:
   ```bash
   gh api --paginate repos/$REPO/pulls/$PR_NUMBER/reviews --jq '.[] | {user: .user.login, state: .state, body: .body}'
   ```

3. Read inline review comments:
   ```bash
   gh api --paginate repos/$REPO/pulls/$PR_NUMBER/comments --jq '.[] | {user: .user.login, path: .path, line: .line, body: .body}'
   ```

4. Read general PR comments:
   ```bash
   gh api --paginate repos/$REPO/issues/$PR_NUMBER/comments --jq '.[] | {user: .user.login, body: .body}'
   ```

Collect all comments and extract actionable feedback items.

## Step 3: Consolidate Issues

Merge issues from Step 1 (self-review) and Step 2 (external reviews) into a single deduplicated list.

Present the consolidated list to the user:

```
## Consolidated PR Issues

| # | Issue | Source | Severity |
|---|-------|--------|----------|
| 1 | Description of issue | self-review / reviewer-name | high/medium/low |
| 2 | ... | ... | ... |
```

If no issues were found from any source, inform the user the PR looks clean and skip to Step 6.

## Step 4: Investigate and Fix

For each issue in the consolidated list:

1. **Investigate**: Read the relevant code, understand the context, and determine if the issue is valid.

2. **If valid**: Fix the issue. Make the minimal change needed.

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

## Step 6: Re-Review and Merge Decision

1. If fixes were made, briefly review the changes to confirm they are correct and don't introduce new issues.

2. Summarize the overall PR state:
   - Total issues found
   - Issues fixed
   - Issues skipped (with reasons)
   - Any remaining concerns

3. Use **AskUserQuestion**: "PR feedback cycle complete. What would you like to do?"
   - Options: "Merge the PR", "Run another feedback cycle", "I'll handle it manually"

   **If "Merge the PR":**
   ```bash
   gh pr merge $(gh pr view --json number -q '.number') --squash
   ```
   After successful merge, inform the user to clean up their worktree and local branch if applicable.

   **If "Run another feedback cycle":** Return to Step 1.

   **If "I'll handle it manually":** Exit.
