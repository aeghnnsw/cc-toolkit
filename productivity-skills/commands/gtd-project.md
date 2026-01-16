---
description: Review and manage GTD projects with guided workflow
argument-hint: []
allowed-tools: Read, Bash, AskUserQuestion
model: opus
---

<!--
Projects list: "Projects" in macOS Reminders
Project naming: {CamelCaseSummary}-{YYYYMMDD} (e.g., VacationResearch-20260112)
Action reference: #{FullProjectName} in notes field
Project notes: "Goal: [end goal description]"
Context lists: @quick, @1pomo, @2pomo, @deep
CLI: swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift

Key principle: One actionable task per project - only track the NEXT action, not all future actions.
-->

Review and manage GTD projects with auto-review and guided workflow.

## CLI Tool

Run Swift source directly (no build step required):

```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift <command>
```

## Step 1: Gather Data

1. Get current date for overdue calculation:
   ```bash
   date "+%Y-%m-%d"
   ```

2. Ensure required lists exist:
   ```bash
   swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders lists
   ```
   If any required lists are missing, create them:
   ```bash
   swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders create-list "Projects"
   swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders create-list "@quick"
   swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders create-list "@1pomo"
   swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders create-list "@2pomo"
   swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders create-list "@deep"
   ```

3. Query all open projects:
   ```bash
   swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders incomplete "Projects"
   ```

4. Query all context lists for actions:
   ```bash
   for context in "@quick" "@1pomo" "@2pomo" "@deep"; do
     swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders incomplete "$context"
   done
   ```

5. For each project, find its action by matching `#{ProjectName}` in the action's notes field:
   - Parse the JSON output from context list queries
   - Match the notes field against pattern `#{ProjectName}`
   - Example: Project "VacationResearch-20260112" matches action with notes containing "#VacationResearch-20260112"

6. Extract project end goal from project's notes field (format: "Goal: [description]")

7. Determine project status:
   - **Healthy** (✓): Has a pending action that is not overdue
   - **Stalled** (⚠️): No pending action linked to this project
   - **Overdue** (⚠️): Action's due date OR project's due date is in the past

## Step 2: Display Projects Overview

Present all projects with status indicators and end goals:

```
# Projects Overview

1. ✓ VacationResearch-20260112 [High]
   - Goal: Flights and hotel booked for Hawaii trip
   - Action: "Research flights to Hawaii" (@1pomo)

2. ⚠️ ReviewQ1Roadmap-20260115 [High]
   - Goal: Roadmap approved by stakeholders
   - No pending action (stalled)

3. ⚠️ ClientProject-20260110 [Medium]
   - Goal: Invoice paid and project closed
   - Action: "Send invoice" (@quick) - OVERDUE (due 2026-01-10)

Which project to work on? [1/2/3/Done]
```

Use **AskUserQuestion**: "Which project to work on?"
- Options: Numbered list of projects + "Done reviewing"

If no open projects, inform user: "No open projects. Use /gtd-process to create projects from inbox items."

## Step 3: Project Options

Based on the selected project's state, present appropriate options.

Use **AskUserQuestion**: "What would you like to do?"

Options presented based on project state:

| Option | When Available | Action |
|--------|----------------|--------|
| Add action | Stalled projects only | Go to Step 4a |
| Mark action complete | Projects with actions | Go to Step 4b |
| Reschedule action | Overdue actions only | Go to Step 4c (due date only) |
| Edit action | Projects with actions | Go to Step 4c (all properties) |
| Mark project complete | All projects | Go to Step 5 |
| Skip | All projects | Return to Step 2 |

**Note:** For overdue actions, highlight the "Reschedule" option to user.

## Step 4a: Add Action

1. Use **AskUserQuestion**: "What's the next action for this project?"
   - User provides action title

2. Use **AskUserQuestion** to gather all action properties together (3 questions in one call):
   - Question 1 - "Time estimate?": Options "Quick (< 25 min)", "1 Pomodoro (25 min)", "2 Pomodoros (50 min)", "Deep (3+ pomodoros)"
   - Question 2 - "Priority?": Options "High", "Medium", "Low", "None"
   - Question 3 - "Due date?": Options "No due date", "Today", "Tomorrow", "This week", "Custom date"
   - If custom date selected: follow up to ask for specific date

3. Create the action:
   ```bash
   swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders create \
     --title "Action title" \
     --list "@1pomo" \
     --notes "#{ProjectName-20260112}" \
     --priority 5 \
     --due "2026-01-20 17:00"
   ```
   (omit `--due` if user selected "No due date")

4. Report: "Added action '[title]' to [ProjectName]"

5. Return to Step 2.

## Step 4b: Complete Action

1. Mark the action complete:
   ```bash
   swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders complete \
     --title "Action title" \
     --list "@1pomo"
   ```

2. Report: "Completed: '[action title]'"

3. **Immediately ask for next action** - Use **AskUserQuestion**: "What's the next action for this project?"
   - Options: "Enter next action", "Mark project complete", "Skip for now"

4. If "Enter next action": Go to Step 4a (Add Action)
5. If "Mark project complete": Go to Step 5 (Complete Project)
6. If "Skip for now": Return to Step 2

## Step 4c: Edit Action

1. Show current action properties:
   ```
   Current action: "Send invoice"
   List: @quick
   Priority: Medium
   Due: 2026-01-10 17:00
   ```

2. Use **AskUserQuestion**: "What would you like to edit?"
   - Options: "Title", "Time estimate", "Priority", "Due date", "Done editing"
   - multiSelect: true (allow multiple selections)

3. For each selected property, gather new value using **Action Property Questions** (see reference section below)

4. To update, delete old action and create new one with updated properties:
   ```bash
   swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders delete \
     --title "Old title" \
     --list "@old-list"

   swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders create \
     --title "New title" \
     --list "@new-list" \
     --notes "#{ProjectName}" \
     --priority 5 \
     --due "2026-01-15 17:00"
   ```

5. Report: "Updated action '[title]'"

6. Return to Step 2.

## Step 5: Complete Project

1. Mark the project complete:
   ```bash
   swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders complete \
     --title "ProjectName-20260112" \
     --list "Projects"
   ```

2. Check for any remaining actions linked to this project and complete them:
   ```bash
   swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders complete \
     --title "Action title" \
     --list "@1pomo"
   ```

3. Report: "Project '[ProjectName]' marked complete"

4. Return to Step 2.

## Step 6: Exit

When user selects "Done reviewing" in Step 2:

1. Show summary:
   ```
   # Review Complete

   Projects reviewed: 3
   Actions completed: 2
   Actions added: 1
   Projects completed: 1
   ```

2. Exit the workflow.

---

## Reference: Batched Action Property Questions

When gathering action properties, use a single **AskUserQuestion** call with multiple questions:

```
AskUserQuestion with 3 questions:
  Question 1 (header: "Time"): "Time estimate?"
    Options: "Quick (< 25 min)", "1 Pomodoro (25 min)", "2 Pomodoros (50 min)", "Deep (3+ pomodoros)"
    Maps to lists: @quick, @1pomo, @2pomo, @deep

  Question 2 (header: "Priority"): "Priority?"
    Options: "High", "Medium", "Low", "None"
    Values: High=1, Medium=5, Low=9, None=0

  Question 3 (header: "Due"): "Due date?"
    Options: "No due date", "Today", "Tomorrow", "This week", "Custom date"
    If custom selected: follow up to ask for specific date
```

This reduces back-and-forth interactions from 3 separate questions to 1 batched question.

---

## Reference: Context Lists

| List | Time Estimate |
|------|---------------|
| @quick | Quick tasks (< 25 min) |
| @1pomo | 1 Pomodoro (25 min) |
| @2pomo | 2 Pomodoros (50 min) |
| @deep | Deep focus (3+ pomodoros) |

## Reference: Priority Values

| Display | Value |
|---------|-------|
| High | 1 |
| Medium | 5 |
| Low | 9 |
| None | 0 |

## Reference: Date Format

Use `yyyy-MM-dd HH:mm` for due dates. Default time is 17:00 if only date provided.

---

## Guidelines

- **One action per project**: Only track the NEXT action, not all future actions
- Every project should have exactly one pending action (unless stalled or complete)
- After completing an action, immediately prompt for the next action
- Create missing reminder lists automatically before creating reminders
- Handle CLI errors gracefully and report to user
- Match project names case-insensitively

## Note: Batched vs Sequential Questions

**Batched (independent answers):**
- Time estimate + Priority + Due date → ask in single AskUserQuestion call with 3 questions (Step 4a)

**Sequential (dependent answers):**
- "Which project?" → must select before showing options
- "What to do?" → options depend on project state (stalled vs healthy)
- "Action title" → must get title before asking for properties
- "What to edit?" → must know which properties before gathering new values
