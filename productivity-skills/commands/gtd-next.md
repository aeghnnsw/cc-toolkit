---
description: Calendar-aware task selection for GTD Engage step
argument-hint: []
allowed-tools: Read, Bash, AskUserQuestion
model: opus
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
-->

Help user pick the best task based on available time until their next fixed event (GTD "Engage" step).

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

## Step 5: Prioritize and Display Suggestions

Sort actions by:
1. Overdue items first
2. High priority (priority=1)
3. Due date approaching (soonest first)
4. Medium priority (priority=5)
5. Remaining items

Display format:

```
# Available Time: [X hours/minutes] until [Event] ([Time])

Suggested actions:

1. ⚠️ [Action Title] #[ProjectName] [Priority] @[context] - OVERDUE
2. [Action Title] #[ProjectName] [Priority] @[context] - due [date]
3. [Action Title] [Priority] @[context]

Recommended: Start with #1 (overdue), then #2
```

Format notes:
- ⚠️ prefix for overdue items
- Show project name if linked (from notes field)
- Show priority: [High], [Medium], [Low], or omit for None
- Show context list: @quick, @1pomo, @2pomo, @deep
- Show due date if set, with "OVERDUE" if past

If no actions match available contexts:
- Display: "No actions found matching your available time. Consider adding actions to @quick or @1pomo lists."
- Exit the workflow

Use **AskUserQuestion**: "Which task to start?"
- Options: Numbered list (up to 4 items) + "Show more" + "Skip for now"
- If "Show more": display next batch of suggestions
- If "Skip for now": exit workflow

## Step 6: Start Selected Task

1. Display task details:
   ```
   Starting: "[Action Title]"
   Context: @[context]
   ```

2. If task is linked to a project (has #{ProjectName} in notes):
   - Query the project to get its goal:
     ```bash
     swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders incomplete "Projects"
     ```
   - Parse to find matching project and extract goal from notes
   - Display: "Project: [ProjectName]\nGoal: [Goal description]"

3. Display: "Let me know when you're done with this task."

## Step 7: Task Completion

Use **AskUserQuestion**: "How did it go?"
- Options: "Completed", "Partially done, need more time", "Couldn't start, will do later"

**If "Completed":**
1. Mark the action complete:
   ```bash
   swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders complete \
     --title "[Action title]" \
     --list "@[context]"
   ```
2. Report: "Marked complete: '[Action title]'"
3. Go to Step 8

**If "Partially done":**
1. Keep action incomplete
2. Report: "Keeping '[Action title]' on your list for later."
3. Go to Step 8

**If "Couldn't start":**
1. Keep action incomplete
2. Go to Step 8

## Step 8: Recalculate and Continue

1. Get current time:
   ```bash
   date "+%Y-%m-%d %H:%M"
   ```

2. Recalculate remaining time until the original next event

3. If remaining time < 15 minutes:
   - Display: "Only [X] minutes left before [Event]. Take a break and prepare for your meeting."
   - Exit workflow

4. Otherwise, display updated time and next suggestion:
   ```
   Remaining time: [X hours/minutes] until [Event] ([Time])

   Next suggestion:
   1. [Action Title] [Priority] @[context]
   ```

Use **AskUserQuestion**: "Continue?"
- Options: "Yes, start this task", "Pick a different task", "Done for now"
- If "Yes": Go to Step 6
- If "Pick a different task": Go to Step 4 (re-query and display options)
- If "Done for now": Exit workflow

---

## Reference: Context Lists

| List | Time Estimate | Suitable When |
|------|---------------|---------------|
| @quick | < 25 min | Any short window |
| @1pomo | 25 min | 25+ min available |
| @2pomo | 50 min | 50+ min available |
| @deep | 90+ min | Long uninterrupted time |

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
4. Subtract 5-10 minutes buffer for transition

---

## Guidelines

- Always show context (@quick, @1pomo, etc.) with each action
- Prioritize overdue items - they should always appear first
- Link actions to projects when #{ProjectName} is found in notes
- Show all matching actions even if multiple belong to the same project
- Provide time-appropriate suggestions (don't suggest @deep tasks for 30-minute windows)
- After each completed task, immediately recalculate and suggest next
- Respect the user's time by exiting gracefully when time is short
- Handle CLI errors gracefully and report to user

## Note: Sequential Questions

Questions in this command are asked sequentially (not batched) because each answer affects subsequent behavior:
- Step 2: "Other commitments?" → only ask "When?" if user says yes
- Step 7: "How did it go?" → determines whether to mark complete
- Step 8: "Continue?" → depends on remaining time after completion

Use batched questions only when answers are independent (e.g., time estimate + priority + due date in /gtd-process).
