---
name: gtd-process
version: 1.0.0
description: This skill should be used when the user asks to "process inbox", "process items", "organize inbox", "categorize tasks", or wants to process GTD inbox items into projects or actions following the GTD clarify/organize workflow.
---

Process GTD inbox items into projects or actions.

## Step 1: Determine Processing Mode

Determine the processing mode from the user's message:

| User Intent | Behavior |
|-------------|----------|
| Process specific item or no qualifier | Show inbox, ask which item to process, process one item |
| "process all", "process everything" | Process all items sequentially until inbox empty or user says "Done" |

## Step 2: Read Inbox

1. Use Read tool to read `~/.claude/productivity-skills/inbox.md`
2. If file or directory doesn't exist:
   - Create directory: `mkdir -p ~/.claude/productivity-skills`
   - Create file with format:
     ```markdown
     # Inbox

     ```
3. If empty, inform user: "Inbox is empty. Nothing to process."
4. Display numbered list of items

## Step 3: Select Item

**If processing a single item:**
- Use **AskUserQuestion**: "Which item to process?"
- Options: numbered items plus "Done processing"

**If processing all items:**
- Start with first item automatically
- After each item, continue to next unless user chooses "Done"

## Step 4: Categorize Item

Use **AskUserQuestion**: "What is this item?"

| Option | Description |
|--------|-------------|
| New Project | Multi-step outcome requiring multiple actions |
| Project Action | A next action that belongs to an existing project |
| Single Action | One clear next action |
| Skip | Leave in inbox for later |

## Step 5a: Process as Project

1. Generate project name: `{CamelCaseSummary}-{YYYYMMDD}`
   - Examples: "Research vacation" → `VacationResearch-20260112`

2. Use **AskUserQuestion** to confirm/edit name

3. Use **AskUserQuestion** for end goal: "What does 'done' look like for this project?"
   - This is critical for GTD - every project needs a clear outcome
   - User provides a concrete, achievable end state
   - Examples: "Flights and hotel booked for Hawaii trip", "Documentation updated and reviewed"
   - Record this end goal in the project's notes field

4. Use **AskUserQuestion** to gather priority and due date together (2 questions in one call):
   - Question 1 - "Priority?": Options "High", "Medium", "Low", "None"
   - Question 2 - "Due date?": Options "No deadline", "This week", "Next week", "Custom date"
   - If custom date selected: follow up to ask for specific date

5. Create project in Projects list with end goal in notes:
   ```bash
   swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders create \
     --title "ProjectName-20260112" \
     --list "Projects" \
     --priority 5 \
     --notes "Goal: [end goal description]" \
     --due "2026-01-20 17:00"
   ```
   (omit `--due` if user selected "No deadline")
6. Use **AskUserQuestion**: "Add first action now?"
   - If yes: get action title, time estimate, due date (optional)
   - Create action in appropriate context list with project reference:
     ```bash
     swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders create \
       --title "Action title" \
       --list "@1pomo" \
       --notes "#{ProjectName-20260112}" \
       --priority 5
     ```

## Step 5b: Process as Project Action

1. Fetch existing projects:
   ```bash
   swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders incomplete "Projects"
   ```

2. If no projects exist, use **AskUserQuestion**: "No projects found. What would you like to do?"
   - Options: "Create a new project" (go to Step 5a), "Create a single action" (go to Step 5c)

3. Display project list and use **AskUserQuestion**: "Which project does this belong to?"
   - Options: project titles from the response

4. Use **AskUserQuestion**: "What's the action title?"
   - Use the inbox item text as the default suggestion

5. Use **AskUserQuestion** to gather action properties (3 questions in one call):
   - Question 1 - "Time estimate?": Options "Quick (< 25 min)", "1 Pomodoro (25 min)", "2 Pomodoros (50 min)", "Deep (3+ pomodoros)"
   - Question 2 - "Priority?": Options "Inherit from project", "High", "Medium", "Low", "None"
   - Question 3 - "Due date?": Options "No due date", "Today", "Tomorrow", "This week", "Custom date"
   - If custom date selected: follow up to ask for specific date

6. Determine context list from time estimate:
   - Quick → @quick, 1 Pomodoro → @1pomo, 2 Pomodoros → @2pomo, Deep → @deep

7. Create action in context list with project link:
   ```bash
   swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders create \
     --title "Action title" \
     --list "@1pomo" \
     --notes "#{ProjectName-20260112}" \
     --priority 5 \
     --due "2026-01-15 14:00"
   ```
   (omit `--due` if user selected "No due date", use project's priority if "Inherit from project" selected)

## Step 5c: Process as Single Action

1. Use **AskUserQuestion** to gather all action properties together (3 questions in one call):
   - Question 1 - "Time estimate?": Options "Quick (< 25 min)", "1 Pomodoro (25 min)", "2 Pomodoros (50 min)", "Deep (3+ pomodoros)"
   - Question 2 - "Priority?": Options "High", "Medium", "Low", "None"
   - Question 3 - "Due date?": Options "No due date", "Today", "Tomorrow", "This week", "Custom date"
   - If custom date selected: follow up to ask for specific date

2. Create reminder in appropriate context list:
   ```bash
   swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders create \
     --title "Action title" \
     --list "@1pomo" \
     --priority 5 \
     --due "2026-01-15 14:00"
   ```

## Step 5d: Skip

Leave item in inbox, proceed to Step 7.

## Step 6: Remove from Inbox

Use Edit tool to remove the processed item from inbox.md.

## Step 7: Continue Processing

**If processing a single item:**
- Use **AskUserQuestion**: "Process another item?"
- If yes: return to Step 2
- If no: show summary and exit

**If processing all items:**
- If more items remain: automatically continue to next item
- Use **AskUserQuestion**: "Continue with next item '[item]'?"
- Options: "Yes, process it", "Skip this one", "Done processing"
- If done or inbox empty: show summary and exit

## Context Lists Reference

| List | Time Estimate |
|------|---------------|
| @quick | Quick tasks (< 25 min, do during breaks) |
| @1pomo | 1 Pomodoro (25 min) |
| @2pomo | 2 Pomodoros (50 min) |
| @deep | Deep focus (3+ pomodoros) |

## Priority Values

| Display | Value |
|---------|-------|
| High | 1 |
| Medium | 5 |
| Low | 9 |
| None | 0 |

## Guidelines

- **Every project must have a clear end goal** - this defines what "done" looks like
- Create missing reminder lists automatically before creating reminders
- Project actions inherit priority from the project
- Use `#{ProjectName-YYYYMMDD}` in notes field to link actions to projects
- Project notes contain the end goal: "Goal: [description]"
- Date format for due dates: `yyyy-MM-dd HH:mm`
- Handle CLI errors gracefully and report to user

## Note: Batched vs Sequential Questions

**Batched (independent answers):**
- Time estimate + Priority + Due date → ask in single AskUserQuestion call with 3 questions

**Sequential (dependent answers):**
- "What is this item?" → must ask first, determines which path to follow
- "Which project?" → must ask before action title (Project Action path)
- "Action title?" → must ask before gathering action properties (Project Action path)
- "Confirm project name" → must confirm before asking for end goal (New Project path)
- "Add first action?" → must ask after project is created (New Project path)
