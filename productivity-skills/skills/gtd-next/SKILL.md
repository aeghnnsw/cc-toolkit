---
name: gtd-next
version: 3.1.0
description: Use when deciding what to work on next or requesting an agenda, with calendar-aware action selection for the GTD Engage step.
---

Recommend one concrete human action for the GTD Engage step. Use the current calendar, task notes, and known working context. Give a short reason and at most two alternatives that also fit. Generate a full agenda only when the user asks for one.

This workflow reads Calendar and Reminders. It does not change reminders, create calendar blocks, or dispatch agent tasks.

## CLI Tool

Run the Swift source directly. No build step is required.

```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift <command>
```

## Check Available Time

Read the local time and today's events:

```bash
date "+%Y-%m-%d %H:%M"
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift calendars today
```

- Check event start and end times. An event that started earlier can still occupy the current time. Treat timed events as occupied unless known context says they are free. The CLI does not expose event availability.
- If an event is in progress, place any recommendation after it ends. Include overlapping events when finding the next free interval. State that the user is currently busy.
- Bound the interval by the next event and any known workday end. Allow time to prepare or travel when known. Otherwise leave a five-minute buffer before the next event.
- Use known all-day commitments as constraints. An all-day label alone does not establish occupied hours.
- If no event or known end bounds the interval, suggest a bounded focus session. Use 25 minutes when no other context is available. State this as a suggestion, not confirmed availability. Do not invent a work schedule.
- If the known workday has ended, or no usable interval remains, say so. Do not schedule work beyond that limit unless the user has requested it.

## Read Candidates

Read incomplete tasks from all context lists, including tasks without due dates:

```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders incomplete "@quick"
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders incomplete "@1pomo"
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders incomplete "@2pomo"
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders incomplete "@deep"
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders incomplete "@agent"
```

Use the title, notes, priority, due date, and project reference (`#{ProjectName}` in notes). Keep human tasks and `@agent` tasks separate. Context lists estimate human work time: `@quick` = 15 minutes, `@1pomo` = 25 minutes, `@2pomo` = 50 minutes, and `@deep` = 90 minutes.

Report CLI failures and use only the data that was retrieved. A failed calendar query does not establish a free interval. A missing list does not establish that all lists are empty.

## Select One Human Action

1. Filter for the known location, tools, energy, available time, and dependencies. Include breaks and transition time when judging fit. Use known context without a routine selection question.
2. Give real deadlines and consequences weight among feasible actions. Use priority to help choose: 1 = high, 5 = medium, 9 = low, and 0 = unset. An overdue date alone does not make a blocked task actionable or exclude useful undated work.
3. Choose one observable next action. If a stored title describes a broad outcome, use its notes and known context to infer a safe first step. Label it as a suggested first step and estimate that step's duration. Keep the stored reminder unchanged.
4. Skip candidates whose next step is unclear, blocked, or cannot fit. Briefly explain a relevant skipped candidate, such as an urgent item, and recommend another feasible action. Do not turn an unclear task into a multi-step plan.
5. Give at most two useful alternatives. Each must meet the same constraints as the main recommendation.

If no human action fits, state the reason. If all candidates lack a clear next step, identify the missing detail needed to select one. Do not fabricate an action to fill the response.

## Present the Recommendation

Lead with the action and estimated duration. Add one short reason that explains its fit or urgency. Show the project reference and due date when useful. Mark overdue dates accurately. Render Markdown normally; do not wrap the response in a code fence.

Example with a meeting at 10:30 and a known laptop context:

**Next: Draft the three budget questions for Friday's review.** About 15 minutes, until 10:20. Project: Budget review.

This is a suggested first step for “Prepare budget review.” You have the source notes on your laptop and time before the 10:30 meeting.

**Alternative:** Check the two invoice totals against the spreadsheet. About 15 minutes.

The supplier call is blocked until the contact number is available.

### Optional Agent List

When `@agent` contains tasks, show up to three relevant items separately under **Agent candidates**. Show priority and due date where present. These are stored candidates, not dispatched work. Do not assign execution state or claim they are running.

### Full Agenda on Request

For an explicit agenda request, arrange feasible human actions in sequential blocks within the bounded interval. Include five-minute breaks between 25-minute work sessions and retain transition time before events. A longer task can span sessions. Show estimated times and any suggested first steps clearly. If availability is unknown, state the bounded session assumption. Keep agent candidates separate.
