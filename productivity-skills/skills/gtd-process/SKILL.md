---
name: gtd-process
version: 2.0.0
description: This skill should be used when the user asks to "process inbox", "process items", "organize inbox", "categorize tasks", or wants to process GTD inbox items into projects or actions following the GTD clarify/organize workflow.
---

Process GTD inbox items into projects or actions. The agent infers categorization, project assignment, priority, time estimate, and due date for each item — then presents a single confirmation for the user to approve or modify.

## CLI Tool

```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift <command>
```

## Step 1: Determine Processing Mode

Determine the processing mode from the user's message:

| User Intent | Behavior |
|-------------|----------|
| No qualifier or single item | Process the first inbox item, then exit |
| "process all", "process everything" | Process all items sequentially until inbox is empty |

## Step 2: Read Inbox and Gather Context

1. Read `~/.claude/productivity-skills/inbox.md`
2. If file or directory does not exist, create directory and file:
   ```bash
   mkdir -p ~/.claude/productivity-skills
   ```
   Then write an empty inbox file with header `# Inbox` and a blank line.
3. If empty, inform user: "Inbox is empty. Nothing to process." and exit.
4. Display numbered list of items.
5. Ensure required lists exist, creating any that are missing:
   ```bash
   swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders lists
   swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders create-list "Projects"
   swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders create-list "@quick"
   swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders create-list "@1pomo"
   swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders create-list "@2pomo"
   swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders create-list "@deep"
   ```
6. Fetch existing projects for context:
   ```bash
   swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders incomplete "Projects"
   ```

## Step 3: Analyze and Propose

For each inbox item, analyze the text and infer:

1. **Category**: Is this a new project (multi-step outcome), a project action (belongs to an existing project), or a single action (standalone task)?
   - If existing projects were fetched, check if the item relates to any of them
2. **Project assignment**: If it's a project action, which project does it belong to?
3. **Action title**: Clean up the inbox text into a clear action title
4. **Time estimate**: Infer from complexity — @quick (< 25 min), @1pomo (25 min), @2pomo (50 min), @deep (90+ min)
5. **Priority**: Infer from urgency cues in the text (default: Medium)
6. **Due date**: Infer from any time references in the text (default: no due date)

**For new projects**, also infer:
- Project name: `{CamelCaseSummary}-{YYYYMMDD}`
- End goal: What "done" looks like based on the item text

Present the proposal to the user with a single **AskUserQuestion**: "Confirm or modify this processing:"

```
Item: "Research vacation flights by end of month"

Proposed:
  Type: New Project
  Project name: VacationResearch-20260324
  Goal: Flights researched and booked
  Priority: Medium
  Due: 2026-03-31
  First action: "Search flight comparison sites" (@1pomo)

Confirm or modify?
```

Options: "Confirm", "Modify", "Skip"

- **Confirm**: Execute the proposed processing (create project/action via CLI)
- **Modify**: User provides corrections, then execute with modifications
- **Skip**: Leave item in inbox, move to next

## Step 4: Execute Processing

Based on the confirmed or modified proposal:

**For new projects:**
1. Create project in Projects list:
   ```bash
   swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders create \
     --title "ProjectName-YYYYMMDD" \
     --list "Projects" \
     --priority 5 \
     --notes "Goal: [end goal]" \
     --due "YYYY-MM-DD 17:00"
   ```
2. Create first action in the appropriate context list:
   ```bash
   swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders create \
     --title "Action title" \
     --list "@1pomo" \
     --notes "#{ProjectName-YYYYMMDD}" \
     --priority 5
   ```

**For project actions:**
```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders create \
  --title "Action title" \
  --list "@1pomo" \
  --notes "#{ProjectName-YYYYMMDD}" \
  --priority 5 \
  --due "YYYY-MM-DD 17:00"
```

**For single actions:**
```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders create \
  --title "Action title" \
  --list "@1pomo" \
  --priority 5 \
  --due "YYYY-MM-DD 17:00"
```

Omit `--due` if no due date. Omit `--priority` if None (0).

## Step 5: Remove from Inbox

Use Edit tool to remove the processed item from inbox.md.

## Step 6: Continue or Exit

**Single item mode:** Show summary and exit.

**Process all mode:** Automatically continue to the next item (return to Step 3). Repeat until inbox is empty, then show summary and exit.

## Reference

**Context lists:** @quick (< 25 min), @1pomo (25 min), @2pomo (50 min), @deep (90+ min)

**Priority values:** 1=High, 5=Medium, 9=Low, 0=None

**Date format:** `yyyy-MM-dd HH:mm` (default time 17:00)

**Project naming:** `{CamelCaseSummary}-{YYYYMMDD}`

**Project linking:** `#{ProjectName-YYYYMMDD}` in action notes field

## Guidelines

- Every project must have a clear end goal
- Create missing reminder lists automatically before creating reminders
- Project actions inherit priority from the project unless overridden
- Infer as much as possible from the inbox item text — minimize user interaction
- Present one confirmation per item, not multiple sequential questions
