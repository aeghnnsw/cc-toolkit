---
name: gtd-process
version: 3.1.0
description: This skill should be used when the user asks to "process inbox", "process items", "triage inbox", "clarify inbox", "organize inbox", "categorize tasks", or wants to process GTD inbox items into projects or actions following the GTD clarify/organize workflow.
---

Process GTD inbox items into projects or actions. The agent infers categorization, project assignment, priority, time estimate, and due date for each item — then presents a single confirmation for the user to approve or modify.

## CLI Tool

```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift <command>
```

## Step 1: Determine Processing Mode

Default: **process all items** sequentially until the inbox is empty, every item has been presented this session, or the user selects "Stop" on the per-item confirmation.

Only switch to single-item mode if the user explicitly asks for it (e.g. "just one item", "single item", "process the first one" — non-exhaustive). In that case, process the first item and exit via Step 6.

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
   swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders create-list "@agent"
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
4. **Task type**: Is this human-centric or agent-centric?
   - **Agent-centric indicators**: "generate", "draft", "analyze", "research", "summarize", "review code", "run tests", "scan", "convert", "process" — tasks that produce an artifact the user monitors and checks later
   - **Human-centric indicators**: phone calls, meetings, physical tasks, decisions requiring real-time judgment
   - Default to human-centric when ambiguous
5. **Time estimate** (human-centric only): Infer from complexity — @quick (< 25 min), @1pomo (25 min), @2pomo (50 min), @deep (90+ min). Skip for agent-centric tasks.
6. **Priority**: Infer from urgency cues in the text (default: Medium)
7. **Due date**: Infer from any time references in the text (default: one week from today)

**For new projects**, also infer:
- Project name: `{CamelCaseSummary}-{YYYYMMDD}`
- End goal: What "done" looks like based on the item text

Present the proposal to the user with a single **AskUserQuestion**: "Confirm or modify this processing:"

**Human-centric example:**
```
Item: "Call dentist to schedule appointment"

Proposed:
  Type: Single Action
  Task type: Human
  Action: "Call dentist to schedule appointment"
  List: @quick (~15 min)
  Priority: Medium
  Due: 2026-05-04

Confirm or modify?
```

**Agent-centric example:**
```
Item: "Analyze Q1 sales data and generate summary report"

Proposed:
  Type: Single Action
  Task type: Agent
  Action: "Analyze Q1 sales data and generate summary report"
  List: @agent
  Priority: Medium
  Due: 2026-05-04

Confirm or modify?
```

**New project example:**
```
Item: "Research vacation flights by end of month"

Proposed:
  Type: New Project
  Project name: VacationResearch-20260324
  Goal: Flights researched and booked
  Priority: Medium
  Due: 2026-03-31
  First action: "Search flight comparison sites" (@1pomo, Human)

Confirm or modify?
```

Options: "Confirm", "Modify", "Skip", "Stop"

- **Confirm**: Execute the proposed processing (create project/action via CLI), then continue
- **Modify**: User provides corrections, then execute with modifications, then continue
- **Skip**: Leave item in inbox, advance to the next unpresented item
- **Stop**: Leave current item in inbox and exit the processing loop entirely — unlike Skip, no further items are presented

For Skip and Stop, do not perform Step 4 or Step 5 — proceed directly to Step 6.

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
2. Create first action in the appropriate context list (use the inferred list from Step 3):
   ```bash
   swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders create \
     --title "Action title" \
     --list "<inferred list>" \
     --notes "#{ProjectName-YYYYMMDD}" \
     --priority 5
   ```
   Use `@agent` if the first action is agent-centric, otherwise use the inferred time-based list (@quick, @1pomo, @2pomo, @deep).

**For project actions (use the inferred list from Step 3):**
```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders create \
  --title "Action title" \
  --list "<inferred list>" \
  --notes "#{ProjectName-YYYYMMDD}" \
  --priority 5 \
  --due "YYYY-MM-DD 17:00"
```

**For single actions (human-centric — use the inferred time-based list):**
```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders create \
  --title "Action title" \
  --list "<inferred list>" \
  --priority 5 \
  --due "YYYY-MM-DD 17:00"
```

**For single actions (agent-centric):**
```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders create \
  --title "Action title" \
  --list "@agent" \
  --priority 5 \
  --due "YYYY-MM-DD 17:00"
```

Omit `--due` only if user explicitly requests no due date. Omit `--priority` if None (0).

## Step 5: Remove from Inbox

Use Edit tool to remove the processed item from inbox.md.

## Step 6: Continue or Exit

Track which inbox items have been presented in this session (by their original text). Exit (show summary of processed items) when any of these are true:
- User selected "Stop" in Step 3
- Inbox is empty
- Every item currently in the inbox has already been presented this session (each was either processed or skipped) — this prevents an infinite loop when the user skips every item
- Single-item mode was requested in Step 1 and the first item is done

Otherwise, return to **Step 2** to refresh the inbox contents and the existing-projects context (Step 4 may have created a new project), then propose the next unpresented item in Step 3. Do **not** ask the user whether to continue.

## Reference

**Context lists (human):** @quick (< 25 min), @1pomo (25 min), @2pomo (50 min), @deep (90+ min)

**Context list (agent):** @agent (no duration — async, monitor progress)

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
