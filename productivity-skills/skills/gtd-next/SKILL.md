---
name: gtd-next
version: 1.0.0
description: This skill should be used when the user asks "what should I work on next?", "plan my next block", "generate an agenda", "what's next?", or wants calendar-aware task selection and time-blocked agenda generation for the GTD Engage step.
---

<!--
CLI: swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift
Context lists: @quick, @1pomo, @2pomo, @deep
Projects list: "Projects" in macOS Reminders
Action reference: #{ProjectName} in notes field

Note: Projects can have multiple parallel actions. When displaying suggestions,
show all matching actions even if multiple belong to the same project.

Time to context mapping:
- < 25 min → @quick only
- 25-50 min → @quick, @1pomo
- 50-90 min → @quick, @1pomo, @2pomo
- 90+ min → all contexts including @deep

Task durations: @quick=15min, @1pomo=25min, @2pomo=50min, @deep=90min
Buffer: ~10 min per hour (available_minutes / 6, min 5, max 20)
Pomodoro: 25 min work + 5 min break
-->

Help user select tasks and generate a time-blocked agenda for their available time slot (GTD "Engage" step).

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

3. Parse the JSON response and find the next event (after current time)
   - Skip all-day events
   - Find the earliest event with a start time after now

4. If no remaining events today:
   - Use **AskUserQuestion**: "No more calendar events today. Any other time constraints?"
   - Options: "I'm free for the rest of the day", "I have about 1 hour", "I have about 2 hours", "I have 30 minutes or less"
   - Map response to available time and skip to Step 3

## Step 2: Confirm with User

Present the next event and ask for confirmation:

Use **AskUserQuestion**:
```
Your next event: "[Event Title]" at [Time]

Any other commitments before then?
```
- Options: "No, that's correct", "I have something else sooner"

If user has an unlisted commitment:
- Use **AskUserQuestion**: "When is your commitment?"
- Options: "In about 30 minutes", "In about 1 hour", "In about 2 hours", "Let me add it to calendar"
- If "Let me add it to calendar": inform user to add the event and re-run /gtd-next

## Step 3: Calculate Available Time

Calculate minutes until next commitment:
```
Available time = Next event start time - Current time
```

Map to suitable contexts:

| Available Time | Suitable Contexts |
|----------------|-------------------|
| < 15 min | None - suggest taking a break |
| 15-25 min | @quick only |
| 25-50 min | @quick, @1pomo |
| 50-90 min | @quick, @1pomo, @2pomo |
| 90+ min | @quick, @1pomo, @2pomo, @deep |

If available time < 15 minutes:
- Display: "Only [X] minutes until [Event]. Consider taking a break or reviewing notes for your upcoming event."
- Exit the workflow

## Step 4: Query Matching Actions

1. Ensure required lists exist:
   ```bash
   swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders lists
   ```

2. Query actions from suitable context lists:
   ```bash
   swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders incomplete "@quick"
   swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders incomplete "@1pomo"
   # etc. based on available time
   ```

3. Also query overdue reminders:
   ```bash
   swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders overdue
   ```

4. Parse and combine results, noting:
   - Which context list each action belongs to
   - Project reference from notes field (#{ProjectName})
   - Priority value
   - Due date
   - Whether overdue

## Step 5: Select Tasks for Agenda

Sort actions by:
1. Overdue items first
2. High priority (priority=1)
3. Due date approaching (soonest first)
4. Medium priority (priority=5)
5. Remaining items

Display format:

```
# Available Time: [X hours/minutes] until [Event] ([Time])

Available actions:

1. ⚠️ [Action Title] #[ProjectName] [Priority] @[context] (~15 min) - OVERDUE
2. [Action Title] #[ProjectName] [Priority] @[context] (~25 min) - due [date]
3. [Action Title] [Priority] @[context] (~25 min)

Select the tasks you want to work on.
```

Format notes:
- ⚠️ prefix for overdue items
- Show project name if linked (from notes field)
- Show priority: [High], [Medium], [Low], or omit for None
- Show context list: @quick, @1pomo, @2pomo, @deep
- Show estimated duration based on context (see Reference: Task Durations)
- Show due date if set, with "OVERDUE" if past

If no actions match available contexts:
- Display: "No actions found matching your available time. Consider adding actions to @quick or @1pomo lists."
- Exit the workflow

Use **AskUserQuestion** with **multiSelect: true**: "Which tasks do you want to work on?"
- Options: Numbered list of matching actions + "None of these"
- If "None of these" selected: exit workflow

**Validate selection:**
1. Calculate total time needed:
   - Sum of task durations based on context
   - Add pomodoro breaks (5 min after each 25 min of work)
   - Add buffer time (see Reference: Buffer Calculation)

2. If total time exceeds available time:
   - Display: "Selected tasks need [X] minutes but you only have [Y] minutes available."
   - Suggest which tasks could fit (e.g., "You could fit tasks 1 and 3 within your available time.")
   - Re-ask with multiSelect showing the same full list
   - Continue validation until selections fit or user selects "None of these"
   - If "None of these" on re-prompt: exit workflow

3. Once validated, proceed to Step 6.

## Step 6: Generate Agenda

Based on the user's selections and available time, create a time-blocked agenda.

**Agenda Generation Rules:**

1. **Calculate buffer time** before next event:
   - Buffer = available_minutes / 6 (roughly 10 min per hour)
   - Round to nearest 5 minutes
   - Minimum 5 minutes, maximum 20 minutes

2. **Calculate usable work time:**
   - Usable time = Available time - Buffer time

3. **Arrange tasks into pomodoro blocks:**
   - Each pomodoro = 25 min work + 5 min break
   - If multiple short tasks fit within 25 min, group them without breaks
   - After each 25 min of work, schedule a 5 min break
   - No break needed before the final buffer

4. **Generate the agenda:**

```
## Your Agenda (until [Event] at [Time])

[Start Time] - [End Time]  [Task A] (@quick)
[Start Time] - [End Time]  [Task B] (@1pomo)
[Start Time] - [End Time]  Break
[Start Time] - [End Time]  [Task C] (@2pomo)
[Start Time] - [End Time]  Buffer before [Event]
```

**Example with multiple tasks:**

```
## Your Agenda (until Team Meeting at 11:00)

09:00 - 09:15  Reply to client email (@quick)
09:15 - 09:25  Review PR comments (@quick)
09:25 - 09:30  Break
09:30 - 09:55  Write documentation (@1pomo)
09:55 - 10:00  Break
10:00 - 10:50  Deep work on feature (@2pomo)
10:50 - 11:00  Buffer before Team Meeting
```

5. **Present the agenda:**
   - Display the formatted agenda
   - Optionally show linked project goals for context
   - Exit the workflow

---

## Reference: Context Lists

| List | Time Estimate | Suitable When |
|------|---------------|---------------|
| @quick | < 25 min | Any short window |
| @1pomo | 25 min | 25+ min available |
| @2pomo | 50 min | 50+ min available |
| @deep | 90+ min | Long uninterrupted time |

## Reference: Task Durations

| Context | Duration (minutes) |
|---------|-------------------|
| @quick | 15 |
| @1pomo | 25 |
| @2pomo | 50 |
| @deep | 90 |

## Reference: Priority Display

| Value | Display |
|-------|---------|
| 1 | [High] |
| 5 | [Medium] |
| 9 | [Low] |
| 0 | (omit) |

## Reference: Time Calculations

To calculate available minutes:
1. Parse event start time from calendar JSON (format: "2026-01-15 14:00:00")
2. Parse current time (format: "2026-01-15 13:30")
3. Calculate difference in minutes
4. When generating agenda, subtract buffer time (see Reference: Buffer Calculation)

## Reference: Buffer Calculation

Buffer time provides transition time before the next event:

```
buffer_minutes = available_minutes / 6
buffer_minutes = round_to_nearest_5(buffer_minutes)
buffer_minutes = max(5, min(20, buffer_minutes))
```

Examples:
- 30 min available → 5 min buffer
- 60 min available → 10 min buffer
- 90 min available → 15 min buffer
- 120 min available → 20 min buffer

## Reference: Pomodoro Breaks

Breaks are scheduled after every 25 minutes of cumulative work:

- Multiple @quick tasks within 25 min: no break between them, break after reaching 25 min
- @1pomo (25 min): break after completing the task
- @2pomo (50 min): treat as single focused block, break after completing (not mid-task)
- @deep (90 min): treat as single focused block, break after completing (not mid-task)
- No break needed immediately before the final buffer

Note: For simplicity, longer tasks (@2pomo, @deep) are not interrupted with breaks. The pomodoro timing applies to cumulative work when combining multiple smaller tasks.

---

## Guidelines

- Always show context (@quick, @1pomo, etc.) with each action
- Prioritize overdue items - they should always appear first
- Link actions to projects when #{ProjectName} is found in notes
- Show all matching actions even if multiple belong to the same project
- Provide time-appropriate suggestions (don't suggest @deep tasks for 30-minute windows)
- Show estimated duration with each task to help user plan
- Validate total time of selected tasks before generating agenda
- Display a clear, time-blocked agenda as the final output
- Handle CLI errors gracefully and report to user

## Note: Question Patterns

**Sequential questions** (dependent answers):
- Step 2: "Other commitments?" → only ask "When?" if user says yes

**MultiSelect questions:**
- Step 5: "Which tasks?" → allows selecting multiple tasks for the agenda
