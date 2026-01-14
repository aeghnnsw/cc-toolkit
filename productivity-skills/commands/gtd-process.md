---
description: Process GTD inbox items into projects or actions
argument-hint: [all]
allowed-tools: Read, Write, Edit, Bash, AskUserQuestion
model: opus
---

<!--
Inbox file: ~/.claude/productivity-skills/inbox.md
Projects list: "Projects" in macOS Reminders
Context lists: @quick, @1pomo, @2pomo, @deep
CLI tool: ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli
-->

Process GTD inbox items based on user instructions: $ARGUMENTS

## Step 1: Interpret Instructions

Parse `$ARGUMENTS` to understand intent:

| Argument | Behavior |
|----------|----------|
| (empty) | Show inbox, ask which item to process, process one item |
| `all` | Process all items sequentially until inbox empty or user says "Done" |

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

**If `$ARGUMENTS` is empty:**
- Use **AskUserQuestion**: "Which item to process?"
- Options: numbered items plus "Done processing"

**If `$ARGUMENTS` is `all`:**
- Start with first item automatically
- After each item, continue to next unless user chooses "Done"

## Step 4: Categorize Item

Use **AskUserQuestion**: "Is this a Project or Single Action?"

| Option | Description |
|--------|-------------|
| Project | Multi-step outcome requiring multiple actions |
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
4. Use **AskUserQuestion** for priority:
   - Options: "High", "Medium", "Low", "None"
   - Values: High=1, Medium=5, Low=9, None=0
5. Use **AskUserQuestion** for due date (optional):
   - "When should this project be completed?"
   - Options: "No deadline", "This week", "Next week", "Custom date"
   - If custom: ask for specific date
6. Create project in Projects list with end goal in notes:
   ```bash
   productivity-cli reminders create \
     --title "ProjectName-20260112" \
     --list "Projects" \
     --priority 5 \
     --notes "Goal: [end goal description]" \
     --due "2026-01-20 17:00"
   ```
   (omit `--due` if user selected "No deadline")
7. Use **AskUserQuestion**: "Add first action now?"
   - If yes: get action title, time estimate, due date (optional)
   - Create action in appropriate context list with project reference:
     ```bash
     productivity-cli reminders create \
       --title "Action title" \
       --list "@1pomo" \
       --notes "#{ProjectName-20260112}" \
       --priority 5
     ```

## Step 5b: Process as Single Action

1. Use **AskUserQuestion** for time estimate:
   - Options: "Quick (< 25 min)", "1 Pomodoro (25 min)", "2 Pomodoros (50 min)", "Deep (3+ pomodoros)"
2. Use **AskUserQuestion** for priority:
   - Options: "High", "Medium", "Low", "None"
3. Optionally ask for due date
4. Create reminder in appropriate context list:
   ```bash
   productivity-cli reminders create \
     --title "Action title" \
     --list "@1pomo" \
     --priority 5 \
     --due "2026-01-15 14:00"
   ```

## Step 5c: Skip

Leave item in inbox, proceed to Step 7.

## Step 6: Remove from Inbox

Use Edit tool to remove the processed item from inbox.md.

## Step 7: Continue Processing

**If `$ARGUMENTS` is empty:**
- Use **AskUserQuestion**: "Process another item?"
- If yes: return to Step 2
- If no: show summary and exit

**If `$ARGUMENTS` is `all`:**
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
- Use `#{ProjectName}` in notes field to link actions to projects
- Project notes contain the end goal: "Goal: [description]"
- Date format for due dates: `yyyy-MM-dd HH:mm`
- Handle CLI errors gracefully and report to user
