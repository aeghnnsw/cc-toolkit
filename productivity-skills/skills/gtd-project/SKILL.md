---
name: gtd-project
version: 3.0.0
description: This skill should be used when the user asks to "review projects", "manage projects", "check project status", "add action to project", "complete project", or wants to review and manage GTD projects with a guided workflow including status tracking and action management.
---

<!--
Projects list: "Projects" in macOS Reminders
Project naming: {CamelCaseSummary}-{YYYYMMDD} (e.g., VacationResearch-20260112)
Action reference: #{FullProjectName} in notes field
Project notes: "Goal: [end goal description]"
Human context lists: @quick, @1pomo, @2pomo, @deep
Agent context list: @agent (no duration, async)
CLI: swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift

Key principle: Projects can have multiple parallel actions. Track all actionable tasks that can be worked on independently. Actions are either human-centric (pomodoro-timed) or agent-centric (async, no duration).
-->

Review and manage GTD projects with infer-and-confirm workflow. The agent analyzes project state, proposes actions, and the user confirms or overrides — minimizing back-and-forth.

## CLI Tool

Run Swift source directly (no build step required):

```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift <command>
```

## Step 1: Gather Data

1. Query overdue reminders (uses Apple's datetime-aware overdue detection):
   ```bash
   swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders overdue
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
   swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders create-list "@agent"
   ```

3. Query all open projects:
   ```bash
   swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders incomplete "Projects"
   ```

4. Query all context lists for actions:
   ```bash
   for context in "@quick" "@1pomo" "@2pomo" "@deep" "@agent"; do
     swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders incomplete "$context"
   done
   ```

5. For each project, find ALL linked actions by matching `#{ProjectName}` in the action's notes field:
   - Parse the JSON output from context list queries
   - Match the notes field against pattern `#{ProjectName}`
   - Collect ALL matching actions (not just one)

6. Extract project end goal from project's notes field (format: "Goal: [description]")

7. Determine project status:
   - **Healthy** (✓): Has 1+ pending actions, none overdue
   - **Stalled** (⚠️): Has 0 pending actions linked to this project
   - **Overdue** (⚠️): Any action OR project appears in the overdue query results

   Statuses evaluated in order of severity: Overdue > Stalled > Healthy.

## Step 2: Display Projects Overview

Present all projects sorted by urgency (overdue first, then stalled, then healthy):

```
# Projects Overview

1. ⚠️ ClientProject-20260110 [Medium] — OVERDUE
   - Goal: Invoice paid and project closed
   - Actions (1):
     • "Send invoice" (@quick) - OVERDUE (due 2026-01-10)
   → Suggested: Reschedule overdue action

2. ⚠️ ReviewQ1Roadmap-20260115 [High] — STALLED
   - Goal: Roadmap approved by stakeholders
   - No pending actions
   → Suggested: Add next action

3. ✓ VacationResearch-20260112 [High]
   - Goal: Flights and hotel booked for Hawaii trip
   - Actions (3):
     • "Research flights to Hawaii" (@1pomo)
     • "Email hotel for rates" (@quick)
     • "Analyze flight price trends" (@agent) — due 2026-01-20

Which project to work on? [1/2/3/Done]
```

Use **AskUserQuestion**: "Which project to work on?"
- Options: Numbered list of projects + "Done reviewing"
- Overdue and stalled projects are listed first with suggested actions shown inline

If no open projects, inform user: "No open projects. Use /gtd-process to create projects from inbox items."

## Step 3: Auto-Infer Action

Based on the selected project's state, **infer the most logical action automatically** — do not ask "what would you like to do?":

| Project State | Auto-Inferred Action | Rationale |
|---------------|---------------------|-----------|
| Overdue actions | Reschedule the specific overdue action(s) (Step 4c) | Overdue items need immediate attention |
| Stalled (0 actions) | Add next action (Step 4a) | Stalled projects need a next action to move forward |
| Healthy with actions | Present brief options | Multiple valid paths — ask user |

**For overdue projects**: Identify the specific overdue action(s) and announce:
> "Project has overdue action 'Send invoice' (due 2026-01-10). Rescheduling — or would you rather mark the project complete / skip?"

If multiple actions are overdue, process each one sequentially. If the project also has non-overdue actions, only target the overdue ones.

**For stalled projects**: Announce:
> "Project is stalled with no actions. Let's add the next action — or mark project complete / skip?"

**For healthy projects**: Use **AskUserQuestion**: "What would you like to do?"
- Options: "Add action", "Mark action complete", "Edit action", "Mark project complete", "Skip"

In all cases, the user can override the suggestion by saying "complete project" or "skip".

## Step 4a: Add Action

1. Use **AskUserQuestion**: "What's the next action for [ProjectName]?"
   - User provides action title

2. **Infer all properties from the title text** (same pattern as gtd-process):
   - **Task type**: Infer human vs agent from text. Agent-centric indicators: "generate", "draft", "analyze", "research", "summarize", "review code", "run tests", "scan", "convert", "process". Default to human-centric when ambiguous.
   - **Time estimate** (human only): Infer from complexity. "Email..." → @quick, "Research..." → @1pomo, "Write report..." → @2pomo, "Redesign..." → @deep. Skip for agent-centric tasks.
   - **Priority**: Inherit from project priority by default
   - **Due date**: No due date unless the title implies urgency ("today", "by Friday", "urgent"). For agent-centric tasks, default to one week from today if no date implied.

3. Present a single proposal for confirmation:

   **Human-centric example:**
   ```
   Action: "Email hotel for rates"
   → Type: Human
   → List: @quick (~15 min)
   → Priority: High (inherited from project)
   → Due: No due date

   Confirm? [Yes / Modify / Skip]
   ```

   **Agent-centric example:**
   ```
   Action: "Analyze flight price trends"
   → Type: Agent
   → List: @agent
   → Priority: High (inherited from project)
   → Due: 2026-01-20

   Confirm? [Yes / Modify / Skip]
   ```

   Use **AskUserQuestion**: "Confirm this action?"
   - Options: "Yes", "Modify", "Skip"
   - If "Modify": ask which property to change (includes "Task type"), then re-confirm
   - If "Yes": create the action
   - If "Skip": return to Step 2

4. Create the action:
   ```bash
   swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders create \
     --title "Action title" \
     --list "@quick" \
     --notes "#{ProjectName-20260112}" \
     --priority 1
   ```
   Add `--due "2026-01-20 17:00"` only if a due date was inferred or confirmed.

5. Report: "Added action '[title]' to [ProjectName]"

6. Return to Step 2.

## Step 4b: Complete Action

1. If project has multiple actions, use **AskUserQuestion**: "Which action to complete?"
   - Options: List of actions for this project
   - If only one action, skip this question and complete it directly

2. Mark the selected action complete:
   ```bash
   swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders complete \
     --title "Action title" \
     --list "@1pomo"
   ```

3. Report: "Completed: '[action title]'"

4. Check remaining actions:
   - **If other actions remain**: Report "Project [ProjectName] has N remaining actions." Return to Step 2.
   - **If no actions remain**: Auto-suggest adding the next action:
     > "No remaining actions — project will become stalled. Let's add the next action."
     Proceed to Step 4a. The user can select "Skip" in Step 4a's confirm prompt to decline and return to Step 2 (project becomes stalled).

## Step 4c: Reschedule / Edit Action

1. If project has multiple actions, use **AskUserQuestion**: "Which action to edit?"
   - If only one action (or arrived here via auto-infer for overdue), skip this question

2. **For overdue reschedule** (arrived from auto-infer):
   - Show current due date
   - Infer a reasonable new date (tomorrow if 1 day overdue, next week if more)
   - Present proposal:
     ```
     "Send invoice" is overdue (due 2026-01-10)
     → Reschedule to: tomorrow 17:00
     Confirm? [Yes / Pick different date]
     ```
   - Use **AskUserQuestion** with options: "Yes", "Today", "Tomorrow", "This week", "Custom date"

3. **For general edit** (user selected "Edit action"):
   - Show current properties
   - Use **AskUserQuestion**: "What to edit?" with multiSelect
     - Options: "Title", "Task type", "Time estimate", "Priority", "Due date", "Done editing"
   - For each selected property, gather the new value:
     - Title: ask for new title text
     - Task type: options "Human", "Agent". Switching to agent moves task to @agent and removes time estimate. Switching to human requires selecting a time estimate.
     - Time estimate (human only): options "Quick", "1 Pomodoro", "2 Pomodoros", "Deep" (maps to @quick, @1pomo, @2pomo, @deep)
     - Priority: options "High", "Medium", "Low", "None" (maps to 1, 5, 9, 0)
     - Due date: options "No due date", "Today", "Tomorrow", "This week", "Custom date"

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

2. Complete any remaining linked actions:
   ```bash
   swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders complete \
     --title "Action title" \
     --list "@1pomo"
   ```

3. Report: "Project '[ProjectName]' marked complete"

4. Return to Step 2.

## Step 6: Exit

When user selects "Done reviewing" in Step 2:

```
# Review Complete

Projects reviewed: 3
Actions completed: 2
Actions added: 1
Projects completed: 1
```

## Guidelines

- Prioritize overdue items — they always appear first in the overview
- Auto-infer actions for overdue/stalled projects to reduce questions
- Infer action properties from title text — only ask user to confirm
- Multiple actions per project: track all actionable tasks independently
- After completing an action, auto-suggest next action if project becomes stalled
- Create missing reminder lists automatically before creating reminders
- Handle CLI errors gracefully and report to user
- Match project names case-insensitively
- Use `yyyy-MM-dd HH:mm` for due dates, default time 17:00

## Reference: Context Lists

| List | Type | Time Estimate |
|------|------|---------------|
| @quick | Human | Quick tasks (< 25 min) |
| @1pomo | Human | 1 Pomodoro (25 min) |
| @2pomo | Human | 2 Pomodoros (50 min) |
| @deep | Human | Deep focus (3+ pomodoros) |
| @agent | Agent | N/A (async, monitor progress) |

## Reference: Priority Values

| Display | Value |
|---------|-------|
| High | 1 |
| Medium | 5 |
| Low | 9 |
| None | 0 |
