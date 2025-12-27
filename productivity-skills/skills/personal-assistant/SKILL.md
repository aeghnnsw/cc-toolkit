---
name: personal-assistant
description: Proactive task management for daily planning and next-task suggestions based on calendar, reminders, and personal preferences. Use this skill when the user wants proactive task suggestions, daily planning, next-task recommendations, pomodoro-based task scheduling, or preference-based task prioritization. Integrates with calendar-manager and reminder-manager skills to suggest context-aware tasks based on work windows, priorities, and upcoming events. Learns from user feedback and stores preferences in ~/.claude/personal-assistant.md. Requires macOS with Calendar.app and Reminders.app automation permissions.
---

# Personal Assistant

Proactive task management that learns your preferences and suggests what to do next.

## When to Use

- User asks "what's next?", "what should I do?", or "next task"
- User requests "plan my day", "daily plan", "schedule today", or "organize my day"
- User wants pomodoro-based task suggestions
- User provides preference feedback ("I prefer mornings for coding")

## Modes

### Next Task Mode (Pomodoro)

Suggests ONE specific task for next 25 minutes based on:
- Current time and deep work windows
- Calendar availability and upcoming events
- Reminder priorities and due dates
- Learned preferences

### Daily Plan Mode

Creates full-day schedule with:
- Calendar events blocked
- Tasks from reminders prioritized and scheduled
- Pomodoro breaks included
- Deep work windows respected

## Setup

Create preferences file at `~/.claude/personal-assistant.md` with:

```markdown
# Personal Assistant Preferences

## Calendar Defaults
**Default Calendar:** Work

## Reminder Lists
**Work List:** Tasks
**Personal List:** Personal

## Work Schedule
**Work Days:** Monday, Tuesday, Wednesday, Thursday, Friday
**Work Hours:** 9:00 AM - 5:30 PM
**Deep Work Windows:** 9:00 AM - 11:00 AM, 2:00 PM - 4:00 PM

## Pomodoro Settings
**Focus Duration:** 25 minutes
**Short Break:** 5 minutes
**Long Break:** 15 minutes
**Pomodoros Before Long Break:** 4

## Learning & Feedback History
<!-- Auto-updated by the agent when you provide feedback -->
```

## Integration

Uses AppleScript patterns from:
- **calendar-manager** skill - Fetch calendar events
- **reminder-manager** skill - Fetch reminders/tasks

## Notes

- Requires macOS with Calendar.app and Reminders.app
- First use will prompt for automation permissions
- Feedback is stored in preferences file for personalization
