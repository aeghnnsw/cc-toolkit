---
name: gtd-next
version: 3.0.0
description: This skill should be used when the user asks "what should I work on next?", "plan my next block", "generate an agenda", "what's next?", "dispatch agent tasks", or wants calendar-aware task selection, time-blocked agenda generation, and parallel agent task dispatch for the GTD Engage step.
---

<!--
CLI: swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift
Human context lists: @quick, @1pomo, @2pomo, @deep
Agent context list: @agent (no duration, async)
Projects list: "Projects" in macOS Reminders
Action reference: #{ProjectName} in notes field

Task durations: @quick=15min, @1pomo=25min, @2pomo=50min, @deep=90min
Agent tasks: no duration, ranked by priority/due date
Scheduling: 1 human task (fits time slot) + up to 3 agent tasks (parallel)
Buffer: ~10 min per hour (available_minutes / 6, min 5, max 20)
Pomodoro: 25 min work + 5 min break
-->

Automatically select the next actionable tasks and generate a time-blocked agenda based on calendar context and task priority. The agent decides — no user interaction required.

## CLI Tool

Run Swift source directly (no build step required):

```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift <command>
```

## Step 1: Check Calendar

1. Get current date and time:
   ```bash
   date "+%Y-%m-%d %H:%M"
   ```

2. Query today's remaining events:
   ```bash
   swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift calendars today
   ```

3. Parse the JSON response and find the next event (after current time). Skip all-day events.

4. If a next event exists, calculate available minutes until it starts. This becomes the time constraint. If no events remain today, there is no time constraint — proceed without one.

## Step 2: Query All Actionable Tasks

1. Query actions from all context lists:
   ```bash
   swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders incomplete "@quick"
   swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders incomplete "@1pomo"
   swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders incomplete "@2pomo"
   swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders incomplete "@deep"
   swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders incomplete "@agent"
   ```

2. Query overdue reminders:
   ```bash
   swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders overdue
   ```

3. Parse and combine results, separating into two pools:

   **Human tasks** (from @quick, @1pomo, @2pomo, @deep):
   - Context list and duration
   - Project reference from notes field (#{ProjectName})
   - Priority value, due date, whether overdue

   **Agent tasks** (from @agent):
   - Project reference from notes field (#{ProjectName})
   - Priority value, due date, whether overdue
   - No duration

If no actionable tasks found in either pool, report "No actionable tasks found. Add tasks to @quick, @1pomo, @2pomo, @deep, or @agent lists." and exit.

## Step 3: Rank and Select Tasks

**Ranking order (same for both pools):**
1. Overdue items first
2. High priority (priority=1)
3. Due date approaching (soonest first)
4. Medium priority (priority=5)
5. Remaining items

### Human task selection

**If there is a time constraint** (next event found in Step 1):

Select human tasks from the top of the ranked list that fit within the available time. Use task durations based on context (@quick=15min, @1pomo=25min, @2pomo=50min, @deep=90min). Account for buffer time and pomodoro breaks when calculating fit. Skip tasks that exceed remaining time and try the next one.

**If there is no time constraint:**

Select the top 10 human tasks from the ranked list.

### Agent task selection

Select up to 3 agent tasks from the top of the ranked `@agent` list. No time-fitting — agent tasks run asynchronously in the background. If fewer than 3 agent tasks are available, show all of them.

## Step 4: Generate Agenda

**If there is a time constraint:**

1. Calculate buffer time before next event:
   - Buffer = available_minutes / 6 (roughly 10 min per hour)
   - Round to nearest 5 minutes
   - Minimum 5 minutes, maximum 20 minutes

2. Usable work time = Available time - Buffer time

3. Arrange selected human tasks into pomodoro blocks:
   - Each pomodoro = 25 min work + 5 min break
   - Multiple short tasks within 25 min: group without breaks
   - After each 25 min of work, schedule a 5 min break
   - No break needed before the final buffer
   - Longer tasks (@2pomo, @deep): treat as single focused blocks, break after completing

4. Present a time-blocked agenda with agent tasks listed separately:

```
## Your Agenda (until [Event] at [Time])

### Focus Tasks
[Start Time] - [End Time]  [Task A] (@quick) #[ProjectName]
[Start Time] - [End Time]  [Task B] (@1pomo)
[Start Time] - [End Time]  Break
[Start Time] - [End Time]  [Task C] (@2pomo) #[ProjectName]
[Start Time] - [End Time]  Buffer before [Event]

### Agent Tasks (dispatch and monitor)
1. [Task D] #[ProjectName] [High] — due [date]
2. [Task E] — due [date]
3. [Task F] #[ProjectName] [Medium] — due [date]
```

**If there is no time constraint:**

Present human tasks as a ranked list, agent tasks separately:

```
## Recommended Next Tasks

### Human Tasks
1. ⚠️ [Action Title] #[ProjectName] [High] @quick (~15 min) - OVERDUE
2. [Action Title] #[ProjectName] [High] @1pomo (~25 min) - due [date]
3. [Action Title] [Medium] @2pomo (~50 min)
...

Total estimated time: ~X hours Y min

### Agent Tasks (dispatch up to 3, monitor progress)
1. [Action Title] #[ProjectName] [High] — due [date]
2. [Action Title] [Medium] — due [date]
3. [Action Title] — due [date]
```

**Display formatting:**
- ⚠️ prefix for overdue items (both human and agent)
- Show project name if linked (from notes field)
- Map priority values: 1=[High], 5=[Medium], 9=[Low], 0=omit
- Human tasks: show context list (@quick, @1pomo, @2pomo, @deep) and estimated duration
- Agent tasks: show priority and due date only, no duration
- Show due date if set, with "OVERDUE" if past

## Guidelines

- Prioritize overdue items — they always appear first (both human and agent)
- Link actions to projects when #{ProjectName} is found in notes
- Show all matching actions even if multiple belong to the same project
- Handle CLI errors gracefully and report to user
- The agent decides what to work on — present the result, do not ask for selection
- Human tasks are sequential — only 1 active focus task at a time
- Agent tasks are parallel — up to 3 dispatched concurrently, no time-fitting needed
- If only human tasks exist, show agenda without agent section (and vice versa)
