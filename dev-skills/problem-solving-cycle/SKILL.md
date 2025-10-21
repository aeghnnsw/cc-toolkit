---
name: problem-solving-cycle
description: Guides through standardized development workflow from brainstorming to PR merge and cleanup. This skill should be used when starting new features, bug fixes, refactoring, documentation updates, or any development work that requires issue tracking and PR workflow. Use when the user wants to follow a systematic approach to problem-solving with proper version control and code review practices.
---

# Problem Solving Cycle

## Overview

This skill provides a comprehensive workflow for systematic problem-solving in software development. It guides through the complete development lifecycle from initial brainstorming to final PR merge and cleanup, ensuring proper issue tracking, branch management, testing, and code review at each step.

The workflow emphasizes:
- Issue-driven development (every change starts with an issue)
- Worktree-based isolation for parallel work
- Standardized branch naming conventions
- Simple, concise communication (no unnecessary boilerplate)
- Proper testing before PR creation
- Clean merge practices with issue references

## Workflow Phases

### 1. Brainstorming Phase

**Purpose:** Understand the problem and formulate a solution before starting implementation.

**Process:**
- Engage in discussion with the user about the problem and potential solutions
- Ask clarifying questions to understand requirements and constraints
- Help formulate a clear, concise problem statement
- Identify the scope of changes needed
- Determine the appropriate category (feature, bugfix, documentation, refactor, chore, test)

**Output:** Clear understanding of what needs to be done and why.

### 2. Issue Creation

**Purpose:** Document the problem and solution approach in a trackable format.

**Process:**
- Use GitHub CLI (`gh issue create`) to create a new issue
- Write a simple, concise issue description
- Focus on the problem and proposed solution
- Avoid unnecessary boilerplate or flowery language
- Include relevant technical details or context

**Format:**
```bash
gh issue create --title "Brief, descriptive title" --body "Problem description and solution approach"
```

**Note the issue number** for use in branch naming and PR linking.

### 3. Worktree & Branch Setup

**Purpose:** Create an isolated environment for development work.

**Branch Naming Convention:**
Enforce one of these prefixes based on the type of work:
- `feat-<issue-number>-<short-description>` - New features
- `bugfix-<issue-number>-<short-description>` - Bug fixes
- `doc-<issue-number>-<short-description>` - Documentation updates
- `refactor-<issue-number>-<short-description>` - Code refactoring
- `chore-<issue-number>-<short-description>` - Maintenance tasks
- `test-<issue-number>-<short-description>` - Test additions/updates

**Process:**
```bash
# Create worktree with appropriate branch name
git worktree add path/to/worktree <branch-name>

# Navigate to worktree
cd path/to/worktree
```

**Example:**
```bash
git worktree add ../trees/feat-42-user-auth feat-42-user-auth
```

### 4. Development & Testing

**Purpose:** Implement the solution and verify it works correctly.

**Process:**
- Implement the changes in the worktree
- Write or update tests as appropriate
- Run existing tests to ensure no regressions
- Test the implementation in isolation when possible
- Fix any issues discovered during testing

**Testing Guidelines:**
- Run tests before proceeding to PR creation
- For new features, add appropriate test coverage
- For bug fixes, add regression tests when applicable
- Ensure all tests pass before moving forward

**Important:** Do not proceed to PR creation if tests are failing or the implementation is incomplete.

### 5. Push & PR Creation

**Purpose:** Share the changes for review and integration.

**Push Process:**
```bash
# Push branch to remote with upstream tracking
git push -u origin <branch-name>
```

**PR Creation Process:**
```bash
gh pr create --title "Brief, descriptive title" --body "PR description"
```

**PR Description Format:**
- Keep it simple and concise
- Summarize the changes and their purpose
- Reference the issue number (e.g., "Closes #42" or "Fixes #42")
- **Do not include:**
  - Test plans (user will test manually)
  - "Created by Claude Code" or similar attribution
  - Unnecessary boilerplate sections

**Example:**
```bash
gh pr create --title "Add user authentication system" --body "Implements JWT-based authentication with refresh tokens. Closes #42"
```

### 6. Review Process

**Purpose:** Incorporate feedback and improve the implementation.

**Process:**
- Respond to reviewer comments and questions
- Make requested changes in the worktree
- Commit and push updates to the same branch
- Re-run tests after making changes
- Continue iterating until reviewers approve

**Communication:**
- Keep responses simple and focused
- Address all reviewer concerns
- Ask for clarification when feedback is unclear

### 7. Merge & Close

**Purpose:** Integrate the changes into the main codebase.

**Merge Process:**
- Use regular merge (not squash merge) to preserve commit history
- Ensure the PR description references the issue
- Merge via GitHub CLI or web interface:

```bash
gh pr merge <pr-number> --merge
```

**Result:** The PR is merged and the associated issue is automatically closed (if properly referenced).

### 8. Cleanup

**Purpose:** Remove temporary worktrees and branches when no longer needed.

**When to Clean Up:**
- After PR is successfully merged
- When the worktree is no longer needed for reference
- Before starting new work to keep workspace organized

**Process:**
```bash
# Return to main repository
cd /path/to/main/repo

# Remove worktree
git worktree remove path/to/worktree

# Optional: Delete local branch
git branch -d <branch-name>
```

**Note:** The remote branch is typically deleted automatically by GitHub after PR merge.

## Flexibility and Adaptation

While this workflow provides a structured approach, adapt steps based on context:

- **Small changes:** May not require extensive brainstorming
- **Urgent fixes:** May proceed more quickly through phases
- **Complex features:** May need more detailed issue descriptions and longer development cycles
- **Multiple related changes:** May use multiple worktrees simultaneously

The key is to maintain the core principles of issue tracking, isolation, testing, and review while adjusting the rigor to match the scope and complexity of the work.

## Key Principles

1. **Issue-Driven:** Every change starts with a documented issue
2. **Isolated Development:** Use worktrees to keep work separated
3. **Consistent Naming:** Follow branch naming conventions strictly
4. **Test Before PR:** Always run tests before creating PRs
5. **Simple Communication:** Keep issues and PRs concise and clear
6. **Clean History:** Use regular merges to preserve commit context
7. **Proper Cleanup:** Remove worktrees and branches when done
