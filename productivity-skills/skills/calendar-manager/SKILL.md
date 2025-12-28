---
name: calendar-manager
description: Manage macOS Calendar app events via EventKit CLI. Use this skill when the user wants to create calendar events, add meetings, schedule appointments, check calendar availability, list upcoming events, search for events by date or title, update event details, or delete calendar entries. Supports setting event details like title, start/end times, location, and notes. Requires macOS and Calendar.app access permissions.
---

# Calendar Manager

Manage macOS Calendar events using the productivity-cli tool (EventKit-based).

## CLI Location

The CLI tool is located at: `scripts/productivity-cli` (relative to plugin root)

## Building the CLI

If the binary doesn't exist, build it from source:

```bash
cd scripts
swiftc -O -o productivity-cli productivity-cli.swift -framework EventKit
```

Requires: macOS 13+ with Xcode command line tools installed.

## Important: Always Ask for Calendar Name

Before any create/delete operation, list calendars and ask the user which one to use:

```bash
productivity-cli calendars list
```

## Operations

### List All Calendars

```bash
productivity-cli calendars list
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
productivity-cli calendars today
```

### Get This Week's Events

```bash
productivity-cli calendars week
```

### Get Events on a Specific Date

```bash
productivity-cli calendars date 2025-01-15
productivity-cli calendars date 2025-01-15 --calendar Work
```

### Get Events in a Date Range

```bash
productivity-cli calendars range 2025-01-01 2025-01-31
productivity-cli calendars range 2025-01-01 2025-01-31 --calendar Work
```

### Search Events by Title

```bash
productivity-cli calendars search "meeting"
```

Searches events in the next 365 days matching the term.

### Create an Event

**Basic event (1 hour duration):**
```bash
productivity-cli calendars create \
  --title "Team Meeting" \
  --calendar "Work" \
  --start "2025-01-15 14:00"
```

**Event with end time:**
```bash
productivity-cli calendars create \
  --title "Team Meeting" \
  --calendar "Work" \
  --start "2025-01-15 14:00" \
  --end "2025-01-15 15:30"
```

**Event with location and notes:**
```bash
productivity-cli calendars create \
  --title "Team Meeting" \
  --calendar "Work" \
  --start "2025-01-15 14:00" \
  --end "2025-01-15 15:00" \
  --location "Conference Room A" \
  --notes "Weekly sync meeting"
```

**All-day event:**
```bash
productivity-cli calendars create \
  --title "Company Holiday" \
  --calendar "Work" \
  --start "2025-01-20" \
  --allday
```

### Delete an Event

```bash
productivity-cli calendars delete \
  --title "Team Meeting" \
  --date "2025-01-15"
```

With specific calendar:
```bash
productivity-cli calendars delete \
  --title "Team Meeting" \
  --date "2025-01-15" \
  --calendar "Work"
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

## Limitations

- Events from subscribed calendars (holidays, etc.) cannot be deleted
- Recurring event editing affects only the single instance
- No support for attendees or invitations

## Notes

- Always list calendars first and confirm with user before create/delete
- Calendar names are case-insensitive
- The CLI uses EventKit for fast, native access to Calendar data
