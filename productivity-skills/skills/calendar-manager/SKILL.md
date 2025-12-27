---
name: calendar-manager
description: Manage macOS Calendar app events via AppleScript. Use this skill when the user wants to create calendar events, add meetings, schedule appointments, check calendar availability, list upcoming events, search for events by date or title, update event details, or delete calendar entries. Supports setting event details like title, start/end times, location, notes, and alarms. Requires macOS and Calendar.app automation permissions.
---

# Calendar Manager

Manage macOS Calendar events using AppleScript.

## Important: Always Ask for Calendar Name

Before any operation, list calendars and ask the user which one to use:

```bash
osascript -e 'tell application "Calendar" to get name of calendars'
```

## Common Patterns

### Permissions

First run prompts for Calendar access. Grant in **System Settings > Privacy & Security > Automation**.

### Date Handling

```applescript
-- Normalize date to midnight (start of day)
set dayStart to current date  -- or: date "January 15, 2025"
set hours of dayStart to 0
set minutes of dayStart to 0
set seconds of dayStart to 0

-- End of day (for range queries)
set dayEnd to dayStart + (1 * days)

-- Date formats accepted:
-- date "January 15, 2025 2:00 PM"
-- date "1/15/2025 14:00"
-- current date
-- current date + (1 * days)
-- current date + (2 * hours)
```

## Operations

### List All Calendars

```bash
osascript -e 'tell application "Calendar" to get name of calendars'
```

### Create an Event

**Basic event:**
```bash
osascript <<'EOF'
tell application "Calendar"
    tell calendar "CALENDAR_NAME"
        set startDate to current date
        set hours of startDate to 14
        set minutes of startDate to 0
        set seconds of startDate to 0
        set endDate to startDate + (1 * hours)

        make new event at end with properties {summary:"Meeting Title", start date:startDate, end date:endDate}
    end tell
end tell
EOF
```

**Event with location and notes:**
```bash
osascript <<'EOF'
tell application "Calendar"
    tell calendar "CALENDAR_NAME"
        set startDate to date "January 15, 2025 2:00 PM"
        set endDate to date "January 15, 2025 3:00 PM"

        make new event at end with properties {summary:"Team Meeting", start date:startDate, end date:endDate, location:"Conference Room A", description:"Weekly sync meeting"}
    end tell
end tell
EOF
```

**All-day event:**
```bash
osascript <<'EOF'
tell application "Calendar"
    tell calendar "CALENDAR_NAME"
        -- Normalize to midnight (see Common Patterns)
        set eventDate to date "January 20, 2025"
        set hours of eventDate to 0
        set minutes of eventDate to 0
        set seconds of eventDate to 0
        set endEventDate to eventDate + (1 * days)

        make new event at end with properties {summary:"Company Holiday", start date:eventDate, end date:endEventDate, allday event:true}
    end tell
end tell
EOF
```

**Event with alarm:**
```bash
osascript <<'EOF'
tell application "Calendar"
    tell calendar "CALENDAR_NAME"
        set startDate to date "January 15, 2025 2:00 PM"
        set endDate to date "January 15, 2025 3:00 PM"

        set newEvent to make new event at end with properties {summary:"Important Meeting", start date:startDate, end date:endDate}

        tell newEvent
            make new display alarm at end with properties {trigger interval:-15}
        end tell
    end tell
end tell
EOF
```

### Search Events

**Events on a specific date:**
```bash
osascript <<'EOF'
tell application "Calendar"
    -- Normalize to midnight (see Common Patterns)
    set dayStart to date "January 15, 2025"
    set hours of dayStart to 0
    set minutes of dayStart to 0
    set seconds of dayStart to 0
    set dayEnd to dayStart + (1 * days)

    set matchingEvents to {}
    repeat with cal in calendars
        set calEvents to (every event of cal whose start date >= dayStart and start date < dayEnd)
        repeat with evt in calEvents
            set end of matchingEvents to {calName:(name of cal), eventName:(summary of evt), startTime:(start date of evt)}
        end repeat
    end repeat
    return matchingEvents
end tell
EOF
```

**Events in a date range:**
```bash
osascript <<'EOF'
tell application "Calendar"
    set rangeStart to date "January 1, 2025"
    set rangeEnd to date "January 31, 2025"

    set matchingEvents to {}
    repeat with cal in calendars
        set calEvents to (every event of cal whose start date >= rangeStart and start date <= rangeEnd)
        repeat with evt in calEvents
            set end of matchingEvents to {calName:(name of cal), eventName:(summary of evt), startTime:(start date of evt)}
        end repeat
    end repeat
    return matchingEvents
end tell
EOF
```

**Today's events:**
```bash
osascript <<'EOF'
tell application "Calendar"
    -- Normalize to midnight (see Common Patterns)
    set today to current date
    set hours of today to 0
    set minutes of today to 0
    set seconds of today to 0
    set tomorrow to today + (1 * days)

    set todayEvents to {}
    repeat with cal in calendars
        set calEvents to (every event of cal whose start date >= today and start date < tomorrow)
        repeat with evt in calEvents
            set end of todayEvents to {calendar:(name of cal), title:(summary of evt), time:(start date of evt)}
        end repeat
    end repeat
    return todayEvents
end tell
EOF
```

**Search by title:**
```bash
osascript <<'EOF'
tell application "Calendar"
    set searchTerm to "meeting"
    set matchingEvents to {}

    repeat with cal in calendars
        set calEvents to (every event of cal whose summary contains searchTerm)
        repeat with evt in calEvents
            set end of matchingEvents to {calendar:(name of cal), title:(summary of evt), time:(start date of evt)}
        end repeat
    end repeat
    return matchingEvents
end tell
EOF
```

### Delete an Event

**Delete by title on a specific date:**
```bash
osascript <<'EOF'
tell application "Calendar"
    tell calendar "CALENDAR_NAME"
        -- Normalize to midnight (see Common Patterns)
        set dayStart to date "January 15, 2025"
        set hours of dayStart to 0
        set minutes of dayStart to 0
        set dayEnd to dayStart + (1 * days)

        set eventsToDelete to (every event whose summary is "Meeting Title" and start date >= dayStart and start date < dayEnd)
        repeat with evt in eventsToDelete
            delete evt
        end repeat
    end tell
end tell
EOF
```

**Note:** Events from shared/subscribed calendars may not be deletable.

### Get Event Details

```bash
osascript <<'EOF'
tell application "Calendar"
    tell calendar "CALENDAR_NAME"
        -- Normalize to midnight (see Common Patterns)
        set dayStart to date "January 15, 2025"
        set hours of dayStart to 0
        set minutes of dayStart to 0
        set dayEnd to dayStart + (1 * days)

        try
            set evt to first event whose start date >= dayStart and start date < dayEnd
            return {title:(summary of evt), startDate:(start date of evt), endDate:(end date of evt), location:(location of evt), notes:(description of evt)}
        on error
            return "No matching event found."
        end try
    end tell
end tell
EOF
```

## Event Properties

| Property | Type | Description |
|----------|------|-------------|
| summary | text | Event title |
| start date | date | When event starts |
| end date | date | When event ends |
| location | text | Event location |
| description | text | Event notes |
| allday event | boolean | All-day event flag |
| url | text | Associated URL |

## Notes

- Always list calendars first and confirm with user
- Invalid calendar names cause errors
- Use explicit date format when in doubt: `date "Month Day, Year Hour:Minute AM/PM"`
