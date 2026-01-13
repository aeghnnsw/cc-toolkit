---
name: gtd-process
description: Process GTD inbox items into actionable reminders. Use when user wants to process inbox, review inbox, clarify tasks, organize inbox items, work through captured items, or apply GTD workflow. Reads from ~/.claude/productivity-skills/inbox.md and creates reminders in context-based lists.
---

# GTD Process

Process inbox items into Projects or Single Actions using GTD methodology.

## Inbox Location

**Path:** `~/.claude/productivity-skills/inbox.md`

## Reminder Lists

| List | Purpose |
|------|---------|
| Projects | Multi-step outcomes |
| @5min | Quick tasks |
| @15min | Short tasks |
| @30min | Medium tasks |
| @1hr | Longer tasks |
| @Deep | Extended focus work |

## CLI Tool

Uses `productivity-cli` at `${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli`. See reminder-manager skill for build instructions.

## Processing Workflow

### Step 1: Read Inbox

1. Read `~/.claude/productivity-skills/inbox.md`
2. If empty or missing, inform user and exit
3. Display numbered list of items

### Step 2: Select Item

Ask user: "Which item to process?" with numbered options plus "Done processing"

### Step 3: Categorize

Ask user: "Is this a Project or Single Action?"
- **Project**: Multi-step outcome
- **Single Action**: One clear next action
- **Skip**: Leave in inbox

### Step 4a: Process as Project

1. Generate project name: `{CamelCaseSummary}-{YYYYMMDD}`
2. Ask user to confirm/edit name
3. Ask user for priority (High=1, Medium=5, Low=9, None=0)
4. Create in Projects list:
   ```bash
   productivity-cli reminders create \
     --title "ProjectName-20260112" \
     --list "Projects" \
     --priority 5
   ```
5. Ask user: "Add first action now?"
   - If yes: get action title, time estimate, due date (optional)
   - Create action with `#ProjectName` in notes, inherit priority

### Step 4b: Process as Single Action

1. Ask user for time estimate: 5min/15min/30min/1hr/Deep
2. Ask user for priority (High=1, Medium=5, Low=9, None=0)
3. Ask user for due date (optional)
4. Create in appropriate context list:
   ```bash
   productivity-cli reminders create \
     --title "Action title" \
     --list "@15min" \
     --priority 5 \
     --due "2026-01-15 14:00"
   ```

### Step 4c: Skip

Leave item in inbox, continue to Step 6.

### Step 5: Remove from Inbox

Use Edit tool to remove processed item from inbox.md.

### Step 6: Continue?

Ask user: "Process another item?"
- If yes: return to Step 1
- If no: show summary and exit

## Naming Conventions

### Projects

Format: `{CamelCaseSummary}-{YYYYMMDD}`

Examples:
- "Research vacation" → `VacationResearch-20260112`
- "Update documentation" → `UpdateDocs-20260112`

### Project References

Actions for a project include `#{ProjectName}` in notes field.

## Priority Values

| Value | Meaning |
|-------|---------|
| 1 | High |
| 5 | Medium |
| 9 | Low |
| 0 | None |

## Response Format

CLI commands return JSON:

```json
{
  "success": true,
  "message": "Reminder 'VacationResearch-20260112' created successfully"
}
```

Error responses:
```json
{
  "error": "Reminder list 'Projects' not found"
}
```

## CLI Commands Reference

### List reminder lists
```bash
productivity-cli reminders lists
```

### Create list (if missing)
```bash
productivity-cli reminders create-list "Projects"
productivity-cli reminders create-list "@5min"
```

### Create reminder
```bash
productivity-cli reminders create \
  --title "Task" \
  --list "ListName" \
  --priority 5 \
  --notes "Optional notes" \
  --due "2026-01-15 14:00"
```

## Limitations

- Inbox file must exist and be valid markdown
- Required reminder lists are created on demand if missing
- No support for recurring reminders
- Date format must be `yyyy-MM-dd HH:mm`

## Notes

- Check if required lists exist before creating reminders; create if missing
- Priority for project actions is inherited from the project
