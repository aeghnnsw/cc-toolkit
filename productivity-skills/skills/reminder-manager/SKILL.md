---
name: reminder-manager
description: Manage macOS Reminders app via EventKit CLI. Use this skill when the user wants to create reminders, add tasks, add todos, set due dates, check pending tasks, list reminder lists, view overdue reminders, mark tasks as complete, or delete reminders. Supports setting due dates, priorities, and notes. Requires macOS and Reminders.app access permissions.
---

# Reminder Manager

Manage macOS Reminders using the productivity-cli tool (EventKit-based).

## CLI Usage

Run the Swift source directly (no build step required):

```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift <command>
```

Requires: macOS 13+ with Xcode command line tools installed.

## Important: Always Ask for Reminder List

Before any create operation, list reminder lists and ask the user which one to use:

```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders lists
```

## Operations

### List All Reminder Lists

```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders lists
```

Returns JSON:
```json
{
  "success": true,
  "count": 3,
  "data": [
    {"name": "Tasks", "count": 5},
    {"name": "Work", "count": 2},
    {"name": "Personal", "count": 0}
  ]
}
```

The `count` field shows incomplete reminders in each list.

### Get Reminders Due Today

```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders today
```

### Get Incomplete Reminders

**All incomplete reminders:**
```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders incomplete
```

**From a specific list:**
```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders incomplete "Tasks"
```

### Get Overdue Reminders

```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders overdue
```

### Create a Reminder

**Basic reminder:**
```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders create \
  --title "Buy groceries" \
  --list "Tasks"
```

**With due date:**
```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders create \
  --title "Submit report" \
  --list "Work" \
  --due "2025-01-15 17:00"
```

**With priority:**
```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders create \
  --title "Urgent task" \
  --list "Work" \
  --priority 1
```

**With notes:**
```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders create \
  --title "Call John" \
  --list "Tasks" \
  --notes "Discuss project timeline and budget"
```

**Full reminder with all properties:**
```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders create \
  --title "Team meeting prep" \
  --list "Work" \
  --due "2025-01-15 09:00" \
  --priority 1 \
  --notes "Prepare slides and agenda"
```

### Mark Reminder as Complete

```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders complete --title "Buy groceries"
```

With specific list:
```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders complete --title "Buy groceries" --list "Tasks"
```

### Mark Reminder as Incomplete

```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders uncomplete --title "Buy groceries"
```

With specific list:
```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders uncomplete --title "Buy groceries" --list "Tasks"
```

### Delete a Reminder

```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders delete --title "Buy groceries"
```

With specific list:
```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders delete --title "Buy groceries" --list "Tasks"
```

### Create a New Reminder List

```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders create-list "Shopping"
```

## Response Format

All commands return JSON. Success responses:

```json
{
  "success": true,
  "count": 5,
  "data": [
    {
      "title": "Buy groceries",
      "list": "Tasks",
      "dueDate": "2025-01-15 17:00:00",
      "priority": 0,
      "isCompleted": false,
      "notes": null
    }
  ]
}
```

Action results:
```json
{
  "success": true,
  "message": "Reminder 'Buy groceries' created successfully"
}
```

Error responses:
```json
{
  "error": "Reminder list 'Unknown' not found"
}
```

## Priority Values

| Value | Meaning | Display |
|-------|---------|---------|
| 0 | No priority | (none) |
| 1 | High | !!! |
| 5 | Medium | !! |
| 9 | Low | ! |

## Date Format

Use `yyyy-MM-dd HH:mm` for due dates:
- `2025-01-15 17:00` - January 15, 2025 at 5:00 PM
- `2025-01-15 09:00` - January 15, 2025 at 9:00 AM

## Reminder Properties

| Argument | Required | Description |
|----------|----------|-------------|
| `--title` | Yes | Reminder title |
| `--list` | Yes (create) | Reminder list name |
| `--due` | No | Due date/time |
| `--priority` | No | Priority (0, 1, 5, or 9) |
| `--notes` | No | Notes/description |

## Limitations

- Tags are not supported
- Location-based reminders cannot be created
- Subtasks are not accessible
- Attachments cannot be added

## Notes

- Always list reminder lists first and confirm with user before create
- List names are case-insensitive
- The CLI uses EventKit for fast, native access to Reminders data
- Searching by title finds the first matching reminder
