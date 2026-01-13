---
description: Manage GTD projects via natural language instructions
argument-hint: [instructions]
allowed-tools: Read, Bash, AskUserQuestion
model: haiku
---

<!--
Projects list: "Projects" in macOS Reminders
Project naming: {CamelCaseSummary}-{YYYYMMDD} (e.g., VacationResearch-20260112)
Action reference: #{FullProjectName} in notes field (e.g., #VacationResearch-20260112)
Context lists: @5min, @15min, @30min, @1hr, @Deep
-->

Manage GTD projects based on user instructions: $ARGUMENTS

## CLI Tool

Uses `productivity-cli` at `${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli`. See reminder-manager skill for build instructions.

## Step 1: Interpret Instructions

Parse `$ARGUMENTS` to understand intent:

| Intent | Example phrases |
|--------|-----------------|
| List projects | "list", "show all", "open projects", "" (empty = list) |
| Show actions | "show actions for X", "what's in X", "actions for X" |
| Add action | "add action: X", "next action: X", "add to X: task" |
| Complete project | "complete X", "mark X done", "finish X" |
| Find stalled | "stalled", "stuck", "no progress", "which projects are stalled" |
| Project status | "status of X", "how is X going", "progress on X" |

If unclear, use **AskUserQuestion** to clarify.

## Step 2: Execute Action

### List Projects

1. Query Projects list:
   ```bash
   productivity-cli reminders incomplete "Projects"
   ```
2. Display projects with format:
   ```
   # Open Projects (N)
   1. ProjectName-20260112 [Priority]
   2. AnotherProject-20260110 [Priority]
   ```
3. If empty: "No open projects"

### Show Actions for Project

1. Identify project name from user input (match partial names)
2. If ambiguous, use **AskUserQuestion** to select from matching projects
3. Query all context lists for actions with `#{FullProjectName}` in notes:
   ```bash
   productivity-cli reminders incomplete "@5min"
   productivity-cli reminders incomplete "@15min"
   productivity-cli reminders incomplete "@30min"
   productivity-cli reminders incomplete "@1hr"
   productivity-cli reminders incomplete "@Deep"
   ```
4. Filter results where notes contain `#{FullProjectName}`
5. Display:
   ```
   # Actions for ProjectName-20260112 (N)
   1. [15min] Task title [Priority]
   2. [1hr] Another task [Priority]
   ```
6. If no actions: "No pending actions for this project"

### Add Action to Project

1. Identify project name from user input
2. If ambiguous, use **AskUserQuestion** to select project
3. Extract action title from input
4. Use **AskUserQuestion** for time estimate:
   - Question: "Time estimate for this action?"
   - Options: "5 minutes", "15 minutes", "30 minutes", "1 hour", "Deep work"
5. Optionally ask for priority and due date
6. Create action in appropriate context list:
   ```bash
   productivity-cli reminders create \
     --title "Action title" \
     --list "@15min" \
     --notes "#{ProjectName-20260112}" \
     --priority 5
   ```
7. Report: "Added action '[title]' to ProjectName"

### Complete Project

1. Identify project name from user input
2. If ambiguous, use **AskUserQuestion** to select project
3. Check for remaining actions (query all context lists)
4. If actions remain, use **AskUserQuestion**:
   - "Project has N pending actions. Complete anyway?"
   - Options: "Yes, complete project", "No, show actions first"
5. Mark project complete:
   ```bash
   productivity-cli reminders complete \
     --title "ProjectName-20260112" \
     --list "Projects"
   ```
6. Report: "Project 'ProjectName' marked complete"

### Find Stalled Projects

1. Get all open projects from Projects list
2. For each project, check for actions with `#{FullProjectName}` in notes
3. A project is stalled if it has zero pending actions
4. Display:
   ```
   # Stalled Projects (N)
   1. ProjectName-20260112 - No pending actions
   2. AnotherProject-20260110 - No pending actions
   ```
5. If none stalled: "All projects have pending actions"

### Project Status

1. Identify project name
2. Get project details from Projects list
3. Count pending actions across all context lists
4. Display:
   ```
   # ProjectName-20260112
   Priority: Medium
   Pending actions: 3
   - [15min] Task 1
   - [30min] Task 2
   - [Deep] Task 3
   ```

## Step 3: Handle Errors

- **Project not found**: "No project matching 'X'. Show all projects?"
- **List not found**: Create missing lists automatically
- **CLI error**: Report error message to user

## Priority Values

| Value | Display |
|-------|---------|
| 1 | High |
| 5 | Medium |
| 9 | Low |
| 0 | None |

## Guidelines

- Match project names case-insensitively and support partial matches
- When multiple projects match, always ask user to select
- Show context (time estimate) when displaying actions
- Warn before completing projects with pending actions
