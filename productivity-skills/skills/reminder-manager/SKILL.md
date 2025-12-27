---
name: reminder-manager
description: Manage macOS Reminders app via AppleScript. Use this skill when the user wants to create reminders, add tasks, add todos, set due dates, check pending tasks, list reminder lists, view overdue reminders, mark tasks as complete, or delete reminders. Supports setting due dates, priorities, and notes. Requires macOS and Reminders.app automation permissions.
---

# Reminder Manager

Manage macOS Reminders using AppleScript.

## Important: Always Ask for Reminder List

Before any operation, list reminder lists and ask the user which one to use:

```bash
osascript -e 'tell application "Reminders" to get name of lists'
```

## Common Patterns

### Permissions

First run prompts for Reminders access. Grant in **System Settings > Privacy & Security > Automation**.

### Date Handling

```applescript
-- Normalize date to midnight (start of day)
set dayStart to current date
set hours of dayStart to 0
set minutes of dayStart to 0
set seconds of dayStart to 0

-- End of day (for range queries)
set dayEnd to dayStart + (1 * days)

-- Date formats accepted:
-- date "January 15, 2025 5:00 PM"
-- current date
-- current date + (1 * days)
```

### Priority Values

| Value | Meaning |
|-------|---------|
| 0 | No priority |
| 1 | High (!!!) |
| 5 | Medium (!!) |
| 9 | Low (!) |

## Operations

### List All Reminder Lists

```bash
osascript -e 'tell application "Reminders" to get name of lists'
```

### List Reminders

**Incomplete reminders in a list:**
```bash
osascript <<'EOF'
tell application "Reminders"
    tell list "LIST_NAME"
        set incompleteReminders to (reminders whose completed is false)
        set reminderInfo to {}
        repeat with r in incompleteReminders
            set end of reminderInfo to {title:(name of r), dueDate:(due date of r), priority:(priority of r)}
        end repeat
        return reminderInfo
    end tell
end tell
EOF
```

**All reminders (including completed):**
```bash
osascript <<'EOF'
tell application "Reminders"
    tell list "LIST_NAME"
        set allReminders to every reminder
        set reminderInfo to {}
        repeat with r in allReminders
            set end of reminderInfo to {title:(name of r), completed:(completed of r), dueDate:(due date of r)}
        end repeat
        return reminderInfo
    end tell
end tell
EOF
```

**Reminders due today:**
```bash
osascript <<'EOF'
tell application "Reminders"
    -- Normalize to midnight (see Common Patterns)
    set today to current date
    set hours of today to 0
    set minutes of today to 0
    set seconds of today to 0
    set tomorrow to today + (1 * days)

    set dueToday to {}
    repeat with lst in lists
        set lstReminders to (reminders of lst whose due date >= today and due date < tomorrow and completed is false)
        repeat with r in lstReminders
            set end of dueToday to {list:(name of lst), title:(name of r), dueDate:(due date of r)}
        end repeat
    end repeat
    return dueToday
end tell
EOF
```

**Overdue reminders:**
```bash
osascript <<'EOF'
tell application "Reminders"
    set now to current date
    set overdueReminders to {}
    repeat with lst in lists
        set lstReminders to (reminders of lst whose due date < now and completed is false)
        repeat with r in lstReminders
            set end of overdueReminders to {list:(name of lst), title:(name of r), dueDate:(due date of r)}
        end repeat
    end repeat
    return overdueReminders
end tell
EOF
```

### Create a Reminder

**Basic reminder:**
```bash
osascript <<'EOF'
tell application "Reminders"
    tell list "LIST_NAME"
        make new reminder with properties {name:"Buy groceries"}
    end tell
end tell
EOF
```

**With due date:**
```bash
osascript <<'EOF'
tell application "Reminders"
    tell list "LIST_NAME"
        set dueDate to date "January 15, 2025 5:00 PM"
        make new reminder with properties {name:"Submit report", due date:dueDate}
    end tell
end tell
EOF
```

**With relative due date:**
```bash
osascript <<'EOF'
tell application "Reminders"
    tell list "LIST_NAME"
        set dueDate to (current date) + (1 * days)
        make new reminder with properties {name:"Follow up on email", due date:dueDate}
    end tell
end tell
EOF
```

**With priority:**
```bash
osascript <<'EOF'
tell application "Reminders"
    tell list "LIST_NAME"
        -- Priority: 0=none, 1=high, 5=medium, 9=low (see Common Patterns)
        make new reminder with properties {name:"Urgent task", priority:1}
    end tell
end tell
EOF
```

**With notes:**
```bash
osascript <<'EOF'
tell application "Reminders"
    tell list "LIST_NAME"
        make new reminder with properties {name:"Call John", body:"Discuss project timeline and budget"}
    end tell
end tell
EOF
```

**Full reminder with all properties:**
```bash
osascript <<'EOF'
tell application "Reminders"
    tell list "LIST_NAME"
        set dueDate to date "January 15, 2025 9:00 AM"
        make new reminder with properties {name:"Team meeting prep", due date:dueDate, priority:1, body:"Prepare slides and agenda"}
    end tell
end tell
EOF
```

### Mark Reminder as Complete

**By name:**
```bash
osascript <<'EOF'
tell application "Reminders"
    tell list "LIST_NAME"
        try
            set targetReminder to first reminder whose name is "Buy groceries"
            set completed of targetReminder to true
        on error
            return "Reminder not found."
        end try
    end tell
end tell
EOF
```

**Complete all in a list:**
```bash
osascript <<'EOF'
tell application "Reminders"
    tell list "LIST_NAME"
        set incompleteReminders to (reminders whose completed is false)
        repeat with r in incompleteReminders
            set completed of r to true
        end repeat
    end tell
end tell
EOF
```

### Mark Reminder as Incomplete

```bash
osascript <<'EOF'
tell application "Reminders"
    tell list "LIST_NAME"
        try
            set targetReminder to first reminder whose name is "Buy groceries"
            set completed of targetReminder to false
        on error
            return "Reminder not found."
        end try
    end tell
end tell
EOF
```

### Delete a Reminder

**By name:**
```bash
osascript <<'EOF'
tell application "Reminders"
    tell list "LIST_NAME"
        try
            delete (first reminder whose name is "Buy groceries")
        on error
            return "Reminder not found."
        end try
    end tell
end tell
EOF
```

**Delete all completed:**
```bash
osascript -e 'tell application "Reminders" to delete (reminders whose completed is true)'
```

**Delete completed in a specific list:**
```bash
osascript <<'EOF'
tell application "Reminders"
    tell list "LIST_NAME"
        delete (reminders whose completed is true)
    end tell
end tell
EOF
```

### Create a New Reminder List

```bash
osascript -e 'tell application "Reminders" to make new list with properties {name:"New List Name"}'
```

### Get Reminder Count

**Incomplete in a list:**
```bash
osascript <<'EOF'
tell application "Reminders"
    tell list "LIST_NAME"
        count of (reminders whose completed is false)
    end tell
end tell
EOF
```

**All reminders:**
```bash
osascript -e 'tell application "Reminders" to count of reminders'
```

## Reminder Properties

| Property | Type | Description |
|----------|------|-------------|
| name | text | Reminder title |
| body | text | Notes/description |
| due date | date | When reminder is due |
| remind me date | date | When to show alert |
| priority | integer | 0=none, 1=high, 5=medium, 9=low |
| completed | boolean | Whether reminder is done |
| completion date | date | When marked complete |
| flagged | boolean | Whether flagged |

## Limitations

- **Tags:** Not supported via AppleScript
- **Location-based reminders:** Cannot be created
- **Subtasks:** Not accessible
- **Attachments:** Cannot be added

## Notes

- Always list reminder lists first and confirm with user
- Invalid list names cause errors
- Searching by name errors if no match; use try blocks for robustness
