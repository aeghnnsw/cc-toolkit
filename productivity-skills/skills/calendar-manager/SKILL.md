---
name: calendar-manager
version: 1.0.0
description: This skill should be used when the user asks to "create calendar event", "add meeting", "schedule appointment", "check calendar", "list upcoming events", "search events", "update event", "delete event", or wants to manage macOS Calendar app events via EventKit CLI. Supports setting event details like title, start/end times, location, and notes. Requires macOS and Calendar.app access permissions.
---

# Calendar Manager

Manage macOS Calendar events using the productivity-cli tool (EventKit-based).

## CLI Usage

Run the Swift source directly (no build step required):

```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift <command>
```

Requires: macOS 13+ with Xcode command line tools installed.

## Important: Always Ask for Calendar Name

Before any create/delete operation, list calendars and ask the user which one to use:

```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift calendars list
```

## Operations

### List All Calendars

```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift calendars list
```

Returns JSON:
```json
{
  "success": true,
  "count": 3,
  "data": [
    {"name": "Work", "type": "calDAV", "color": "..."},
    {"name": "Personal", "type": "calDAV", "color": "..."}
  ]
}
```

### Get Today's Events

```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift calendars today
```

### Get This Week's Events

```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift calendars week
```

### Get Events on a Specific Date

```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift calendars date 2025-01-15
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift calendars date 2025-01-15 --calendar Work
```

### Get Events in a Date Range

```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift calendars range 2025-01-01 2025-01-31
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift calendars range 2025-01-01 2025-01-31 --calendar Work
```

### Search Events by Title

```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift calendars search "meeting"
```

Searches events in the next 365 days matching the term.

### Create an Event

**Basic event (1 hour duration):**
```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift calendars create \
  --title "Team Meeting" \
  --calendar "Work" \
  --start "2025-01-15 14:00"
```

**Event with end time:**
```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift calendars create \
  --title "Team Meeting" \
  --calendar "Work" \
  --start "2025-01-15 14:00" \
  --end "2025-01-15 15:30"
```

**Event with location and notes:**
```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift calendars create \
  --title "Team Meeting" \
  --calendar "Work" \
  --start "2025-01-15 14:00" \
  --end "2025-01-15 15:00" \
  --location "Conference Room A" \
  --notes "Weekly sync meeting"
```

**All-day event:**
```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift calendars create \
  --title "Company Holiday" \
  --calendar "Work" \
  --start "2025-01-20" \
  --allday
```

### Create a Recurring Event

**Daily standup:**
```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift calendars create \
  --title "Daily Standup" \
  --calendar "Work" \
  --start "2026-01-20 09:00" \
  --end "2026-01-20 09:30" \
  --repeat daily
```

**Weekly team meeting on Mondays:**
```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift calendars create \
  --title "Team Meeting" \
  --calendar "Work" \
  --start "2026-01-20 14:00" \
  --repeat weekly \
  --repeat-days mon \
  --repeat-until "2026-06-30"
```

**Monthly review (12 occurrences):**
```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift calendars create \
  --title "Monthly Review" \
  --calendar "Work" \
  --start "2026-02-01 10:00" \
  --repeat monthly \
  --repeat-count 12
```

**Bi-weekly meeting:**
```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift calendars create \
  --title "Bi-weekly Sync" \
  --calendar "Work" \
  --start "2026-01-20 15:00" \
  --repeat weekly \
  --repeat-interval 2
```

### Delete an Event

```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift calendars delete \
  --title "Team Meeting" \
  --date "2025-01-15"
```

With specific calendar:
```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift calendars delete \
  --title "Team Meeting" \
  --date "2025-01-15" \
  --calendar "Work"
```

**Delete recurring event and all future occurrences:**
```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift calendars delete \
  --title "Daily Standup" \
  --date "2026-01-25" \
  --all-future
```

## Response Format

All commands return JSON. Success responses:

```json
{
  "success": true,
  "count": 2,
  "data": [...]
}
```

Action results:
```json
{
  "success": true,
  "message": "Event 'Team Meeting' created successfully"
}
```

Error responses:
```json
{
  "error": "Calendar 'Unknown' not found"
}
```

## Date Formats

| Format | Example | Usage |
|--------|---------|-------|
| Date only | `2025-01-15` | For date queries, all-day events |
| Date and time | `2025-01-15 14:00` | For timed events |

## Event Properties

| Argument | Required | Description |
|----------|----------|-------------|
| `--title` | Yes | Event title |
| `--calendar` | Yes (create) | Calendar name |
| `--start` | Yes (create) | Start date/time |
| `--end` | No | End date/time (default: 1 hour after start) |
| `--location` | No | Event location |
| `--notes` | No | Event notes/description |
| `--allday` | No | Make it an all-day event |
| `--repeat` | No | Recurrence frequency: daily, weekly, monthly, yearly |
| `--repeat-interval` | No | Every N periods (default: 1) |
| `--repeat-until` | No | End date for recurrence (yyyy-MM-dd) |
| `--repeat-count` | No | Number of occurrences |
| `--repeat-days` | No | Days for weekly recurrence (e.g., mon,wed,fri) |
| `--all-future` | No | Delete all future occurrences (delete only) |

## Event Output with Recurrence

When reading events, recurring events include additional fields:

```json
{
  "title": "Daily Standup",
  "calendar": "Work",
  "startDate": "2026-01-20 09:00:00",
  "endDate": "2026-01-20 09:30:00",
  "isAllDay": false,
  "isRecurring": true,
  "recurrence": {
    "frequency": "daily",
    "interval": 1,
    "endDate": "2026-12-31",
    "occurrenceCount": null,
    "daysOfWeek": null
  }
}
```

## Limitations

- Events from subscribed calendars (holidays, etc.) cannot be deleted
- No support for attendees or invitations

## Notes

- Always list calendars first and confirm with user before create/delete
- Calendar names are case-insensitive
- The CLI uses EventKit for fast, native access to Calendar data
