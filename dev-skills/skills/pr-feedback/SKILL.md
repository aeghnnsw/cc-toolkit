---
name: pr-feedback
version: 3.0.0
description: This skill should be used when the user asks to "gather PR feedback", "review and fix PR issues", "run pr-feedback", "address reviewer comments", or wants to run a structured review-fix-push cycle on the current pull request. Orchestrates self-review, external review collection, issue investigation, and iterative fixing until clean.
---

Gather and address all feedback on the current PR through a structured review-fix-push cycle.

## Auto-Merge Behavior

If the user explicitly requests auto-merge (e.g., "allow merge", "merge when clean", "auto-merge"), merge the PR directly when the cycle completes clean. Otherwise, always ask the user for approval before merging.

## Step 0: Pre-flight Check

Verify the current branch has an associated PR:

```bash
gh pr view --json number -q '.number'
```

If this fails, inform the user they need to be on a branch with an open PR and exit.

## Step 1: Self-Review

Invoke a code review or PR review skill via the **Skill tool** for the self-review. Do not just run `gh pr diff` and scan it manually — the skill-based review provides structured, thorough analysis that a manual diff scan cannot match.

If no review skill is available, fall back to a thorough manual review — but always attempt the Skill tool first.

**Collect ALL issues the review skill finds, regardless of their scores.** The review skill may internally score and filter issues — ignore its filtering. Even if the skill reports "no issues met the threshold" or "not posting a comment", extract every issue it identified at any score level. Do not let the skill's score-based filtering determine what reaches Step 3. Scores are informational only — the decision of whether an issue is valid happens in Step 4 through investigation, not through score thresholds.

Save the full list for consolidation in Step 3.

## Step 2: Gather External Reviews

Read all other reviewer comments on the PR — including review comments, inline comments, and general PR comments. Extract actionable feedback items.

## Step 3: Consolidate Issues

Merge all issues from Step 1 (self-review) and Step 2 (external reviews) into a single deduplicated list. Include every issue regardless of its original score or severity — all issues are treated equally from this point forward.

Present the consolidated list:

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
3. **If invalid**: Skip it with a brief explanation (e.g., "false positive — the null check already exists on line 42").

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
2. Create a commit summarizing the fixes (e.g., "Address PR review feedback")
3. Push to the remote branch

If no fixes were needed, skip to Step 7.

## Step 6: Loop

After fixes are committed and pushed, return to **Step 1** and run the exact same full review cycle again. Do not take shortcuts — every cycle must invoke the same review skills and apply the same level of scrutiny as cycle 1. Fixing issues can introduce new bugs, so a superficial check is not acceptable.

Specifically:
- Re-invoke review skills via the Skill tool — do not just scan the diff or skim changes
- Treat cycle N the same as cycle 1 — same tools, same depth, same rigor
- External reviewer comments will also be re-read for any new feedback

Repeat until no new issues are found in Step 3, then proceed to Step 7.

## Step 7: Merge Decision

When no new issues are found, summarize the overall PR state:
- Total issues found (across all cycles)
- Issues fixed
- Issues skipped (with reasons)

**If the user requested auto-merge:**

Merge the PR directly:

```bash
gh pr merge --squash
```

After successful merge, inform the user to clean up their worktree and local branch if applicable.

**Otherwise (default):**

Ask the user: "PR feedback cycle complete. No new issues found. What would you like to do?"
- Options: "Merge the PR", "I'll handle it manually"

If merge requested, run `gh pr merge --squash`. After successful merge, inform the user to clean up their worktree and local branch if applicable.
