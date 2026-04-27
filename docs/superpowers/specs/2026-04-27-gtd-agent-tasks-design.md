# GTD Agent-Assisted Tasks Design

## Problem

The current GTD system categorizes all tasks by pomodoro duration (`@quick`, `@1pomo`, `@2pomo`, `@deep`). AI agents are now deeply involved in workflows, and many tasks are delegated to agents — dispatched asynchronously and monitored for results. These agent-centric tasks don't fit the pomodoro model: their duration is unpredictable, and multiple can run concurrently.

## Decision

Binary task classification: every task is either **human-centric** (sequential, pomodoro-timed) or **agent-centric** (parallel, async, due-date only). A new `@agent` list in macOS Reminders holds all agent-centric tasks.

Scheduling model: `gtd-next` assigns 1 human task that fits the time slot + up to 3 agent tasks ranked by priority/due date. Agent tasks require monitoring but not continuous engagement.

## Data Model

### New `@agent` context list

| List | Type | Duration |
|------|------|----------|
| @quick | Human | ~15 min |
| @1pomo | Human | ~25 min |
| @2pomo | Human | ~50 min |
| @deep | Human | ~90 min |
| @agent | Agent | N/A |

### Agent task properties

- Title
- Priority (1=High, 5=Medium, 9=Low, 0=None)
- Due date (required, defaults to one week from today)
- Notes: `#{ProjectName}` for project linking
- No duration / no time estimate

### Agent-centric inference heuristics

Classify as agent-centric when action text suggests delegatable work:
- Keywords: "generate", "draft", "analyze", "research", "summarize", "review code", "run tests", "scan", "convert", "process"
- Pattern: tasks that produce an artifact the user checks later
- Default to human-centric when ambiguous

All skills use infer-and-confirm: the agent guesses human vs agent from text, user confirms or overrides.

## Skill Changes

### gtd-next

**Current:** Fill time slot with human tasks ranked by priority.

**New:** Two parallel selections.

Human track (unchanged):
- Rank from `@quick`, `@1pomo`, `@2pomo`, `@deep`
- Fit into available time slot using pomodoro blocks

Agent track (new):
- Query `@agent` list
- Rank by: overdue first, high priority, soonest due date
- Select top 3 (or fewer if less available)
- No time-fitting

**Agenda output — with time constraint:**

```
## Your Agenda (until [Event] at [Time])

### Focus Task
[Start] - [End]  [Task A] (@1pomo) #[Project]
[Start] - [End]  Break
[Start] - [End]  Buffer before [Event]

### Agent Tasks (dispatch and monitor)
1. [Task B] #[Project] [High] — due 2026-05-01
2. [Task C] — due 2026-05-03
3. [Task D] #[Project] [Medium] — due 2026-05-10
```

**Agenda output — without time constraint:**

```
## Recommended Next Tasks

### Human Tasks
1. [Action] #[Project] [High] @quick (~15 min) - OVERDUE
2. [Action] @1pomo (~25 min) - due 2026-05-01
...

### Agent Tasks (dispatch up to 3, monitor progress)
1. [Action] #[Project] [High] — due 2026-05-01
2. [Action] [Medium] — due 2026-05-05
3. [Action] — due 2026-05-10
```

Rules:
- Agent tasks shown below human task section
- Max 3 agent tasks per agenda
- Agent tasks show priority and due date, no duration
- Overdue agent tasks get warning prefix same as human tasks

### gtd-process

**Step 2:** Add `@agent` to required list creation checks.

**Step 3 (Analyze and Propose):** New inference before time estimation:
1. Infer task type (human or agent) from text
2. If human: infer time estimate, assign context list (existing logic)
3. If agent: skip time estimate, assign `@agent`

**Confirmation prompt — human-centric (unchanged):**
```
Item: "Call dentist to schedule appointment"
Proposed:
  Type: Human
  Action: "Call dentist to schedule appointment"
  List: @quick (~15 min)
  Priority: Medium
  Due: 2026-05-04
```

**Confirmation prompt — agent-centric:**
```
Item: "Analyze Q1 sales data and generate summary report"
Proposed:
  Type: Agent
  Action: "Analyze Q1 sales data and generate summary report"
  List: @agent
  Priority: Medium
  Due: 2026-05-04
```

**Step 4 (Execute):** Same CLI commands, targeting `@agent` list for agent tasks.

### gtd-project

**Step 1 (Gather Data):** Add `@agent` to context list queries and list creation checks.

**Step 2 (Display):** Show `(@agent)` tag with due date instead of time estimate:
```
- Actions (3):
  • "Review pipeline output" (@1pomo)
  • "Run ETL on Q1 dataset" (@agent) — due 2026-05-01
  • "Generate dashboard charts" (@agent) — due 2026-05-03
```

**Step 4a (Add Action):** Infer human vs agent from title text. Include task type in confirmation. "Modify" options include "Task type".

**Step 4c (Edit Action):** "What to edit?" options add "Task type". Switching type moves the task between `@agent` and a time-based list.

**Reference table:** Updated to include `@agent` row.

### gtd-inbox

No changes. Inbox is for raw capture — classification happens during processing.

## Files to Modify

1. `productivity-skills/skills/gtd-next/SKILL.md` — add `@agent` queries, two-track selection, updated agenda format
2. `productivity-skills/skills/gtd-process/SKILL.md` — add agent inference, `@agent` list creation, updated confirmation prompts
3. `productivity-skills/skills/gtd-project/SKILL.md` — add `@agent` queries, updated display, task type in add/edit flows
