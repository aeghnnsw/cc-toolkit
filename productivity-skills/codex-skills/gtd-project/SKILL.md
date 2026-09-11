---
name: gtd-project
description: Use when reviewing GTD project status, adding actions or agent tasks to projects, completing or rescheduling actions, or completing projects tracked in macOS Reminders.
---

Review and manage GTD projects with infer-and-confirm workflow. The agent analyzes project state, proposes actions, and the user confirms or overrides — minimizing back-and-forth.

Before proposing, editing, completing, or reviewing actions that involve agent work, read the [shared GTD planning policy](../../references/gtd-planning.md).

## CLI Tool

Run the Swift source directly (no build step required). `<plugin-root>` is the installed plugin directory — the directory that contains `scripts/` and `codex-skills/` (two levels above this skill's folder; in a repository checkout it is `productivity-skills/`). Resolve it to an absolute path and substitute it in every command:

```bash
swift <plugin-root>/scripts/productivity-cli.swift <command>
```

## Step 1: Gather Data

1. Query overdue reminders (uses Apple's datetime-aware overdue detection):
   ```bash
   swift <plugin-root>/scripts/productivity-cli.swift reminders overdue
   ```

2. Ensure required lists exist:
   ```bash
   swift <plugin-root>/scripts/productivity-cli.swift reminders lists
   ```
   If any required lists are missing, create them:
   ```bash
   swift <plugin-root>/scripts/productivity-cli.swift reminders create-list "Projects"
   swift <plugin-root>/scripts/productivity-cli.swift reminders create-list "@quick"
   swift <plugin-root>/scripts/productivity-cli.swift reminders create-list "@1pomo"
   swift <plugin-root>/scripts/productivity-cli.swift reminders create-list "@2pomo"
   swift <plugin-root>/scripts/productivity-cli.swift reminders create-list "@deep"
   ```

3. Query all open projects:
   ```bash
   swift <plugin-root>/scripts/productivity-cli.swift reminders incomplete "Projects"
   ```

4. Query human context lists and read legacy `@agent` reminders if that list exists. Never create new `@agent` reminders or lists:
   ```bash
   for context in "@quick" "@1pomo" "@2pomo" "@deep"; do
     swift <plugin-root>/scripts/productivity-cli.swift reminders incomplete "$context"
   done
   ```

   If `@agent` exists, query its incomplete reminders with the same command.

5. For each project, find ALL linked actions by matching `#{ProjectName}` in the action's notes field:
   - Parse the JSON output from context list queries
   - Match the notes field against pattern `#{ProjectName}`
   - Collect ALL matching actions (not just one)

6. Read the project goal and waiting records from its notes. Use the shared planning policy to interpret waiting records. Check available evidence for output or a request for human support.

7. Determine project status:
   - **Healthy** (✓): Has at least one ready human action.
   - **Waiting**: Has no ready human action, and notes or other evidence show that output is pending.
   - **Stalled** (⚠️): Has no ready action and no supported waiting state.
   - **Overdue** (⚠️): Any action or project appears in the overdue query. Show this deadline flag alongside its status, including Waiting. Preserve the deadline.

   Show any waiting record even when other actions are ready. For legacy `@agent` reminders, use the shared policy and the existing confirmation flow to propose conversion. Update the same ID and preserve the original deliverable, project reference, and other notes.

## Step 2: Display Projects Overview

Present overdue projects first, then stalled projects, then healthy and waiting projects. Show what each waiting project needs and any known source ID or link.

```
# Projects Overview

1. ⚠️ ClientProject-20260110 [Medium] — OVERDUE
   - Goal: Invoice paid and project closed
   - Actions (1):
     • "Send invoice" (@quick) - OVERDUE (due 2026-01-10)
   → Suggested: Reschedule overdue action

2. ⚠️ ReviewQ1Roadmap-20260115 [High] — STALLED
   - Goal: Roadmap approved by stakeholders
   - No pending actions
   → Suggested: Add next action

3. ✓ VacationResearch-20260112 [High]
   - Goal: Flights and hotel booked for Hawaii trip
   - Actions (3):
     • "Research flights to Hawaii" (@1pomo)
     • "Email hotel for rates" (@quick)
     • "Send the agent the flight price analysis request" (@quick) — due 2026-01-20

Which project to work on? [1/2/3/Done]
```

Ask the user: "Which project to work on?"
- Options: Numbered list of projects + "Done reviewing"
- Overdue and stalled projects are listed first with suggested actions shown inline

If no open projects, inform user: "No open projects. Use the gtd-process skill to create projects from inbox items."

## Step 3: Auto-Infer Action

Based on the selected project's state, **infer the most logical action automatically** — do not ask "what would you like to do?":

| Project State | Auto-Inferred Action | Rationale |
|---------------|---------------------|-----------|
| Waiting, including overdue | Report the waiting state and keep the project open | No human action is ready |
| Output ready or support requested | Propose a concrete review or support action (Step 4a) | Human work is now actionable |
| Overdue actions | Reschedule the specific overdue action(s) (Step 4c) | Overdue items need immediate attention |
| Stalled (no ready action or waiting state) | Add next action (Step 4a) | Stalled projects need a next action to move forward |
| Healthy with actions | Present brief options | Multiple valid paths — ask user |

**For waiting projects**: Report the pending deliverable and retain its deadline. Return to Step 2. Do not force an add-action loop or infer project completion. When output is ready or support is requested, propose that human action through Step 4a.

**For overdue projects with ready actions**: Identify the specific overdue action(s) and announce:
> "Project has overdue action 'Send invoice' (due 2026-01-10). Rescheduling — or would you rather mark the project complete / skip?"

If multiple actions are overdue, process each one sequentially. If the project also has non-overdue actions, only target the overdue ones.

**For stalled projects**: Announce:
> "Project is stalled with no actions. Let's add the next action — or mark project complete / skip?"

**For healthy projects**: Ask the user: "What would you like to do?"
- Options: "Add action", "Mark action complete", "Edit action", "Mark project complete", "Skip"

In all cases, the user can override the suggestion by saying "complete project" or "skip".

## Step 4a: Add Action

1. Ask the user: "What's the next action for [ProjectName]?"
   - User provides action title

2. **Infer all properties from the title text** (same pattern as gtd-process):
   - **Human time estimate**: Estimate the current action’s human effort. Use @quick, @1pomo, @2pomo, or @deep. Agent-related actions are concrete steps to start the agent, support its work, or review its output. Keep the original deliverable and asynchronous runtime, when known, in notes. Label uncertain durations as estimates; never treat unknown effort as zero.
   - **Priority**: Treat labels as optional Reminders hints. Inherit project priority by default, including explicit None (0). Use Medium only when the project priority is unavailable.
   - **Action title**: Use a concrete next step with an object and a clear stopping point. Preserve the project goal. Ask one focused question if the next step cannot be inferred.
   - **Due date**: No due date unless the user specifies a deadline. “Urgent” can affect priority but does not supply a date. A planned work session is not a deadline.

3. Present a single proposal for confirmation:

   **Human action example:**
   ```
   Action: "Email hotel for rates"
   → List: @quick (~15 min)
   → Priority: High (inherited from project)
   → Due: No due date

   Confirm? [Yes / Modify / Skip]
   ```

   **Agent startup example:**
   ```
   Action: "Send the agent the flight price analysis request"
   → List: @quick (estimated 5 min)
   → Notes: Agent deliverable: flight price trend analysis. Async runtime: Unknown.
   → Priority: High (inherited from project)
   → Due: No due date

   Confirm? [Yes / Modify / Skip]
   ```

   Ask the user: "Confirm this action?"
   - Options: "Yes", "Modify", "Skip"
   - If "Modify": ask which property to change, then re-confirm
   - If "Yes": create the action
   - If "Skip": return to Step 2

4. Create the action:
   ```bash
   swift <plugin-root>/scripts/productivity-cli.swift reminders create \
     --title "Action title" \
     --list "@quick" \
     --notes "#{ProjectName-20260112}" \
     --priority 1
   ```
   Save the current action’s human effort estimate in `--notes`. Include the intended agent deliverable and asynchronous runtime, when known, in `--notes`. Preserve the project reference and other relevant notes. For an approved legacy conversion, update the existing reminder by ID using Step 4c. Do not create a replacement.

   When creating a review action for ready output, first confirm that the action exists. Then remove only the resolved waiting record from the project notes. Preserve the goal and unrelated notes. If creation fails or is uncertain, retain the waiting record. If the notes update fails, report the partial result and reuse the confirmed action ID on retry.

   Add `--due "2026-01-20"` only for a specified deadline. Include a time only when the user supplies one.

5. Report: "Added action '[title]' to [ProjectName]"

6. Return to Step 2.

## Step 4b: Complete Action

1. If project has multiple actions, ask the user: "Which action to complete?"
   - Options: List of actions for this project
   - If only one action, skip this question and complete it directly

2. Before completing startup when later output or review remains, save a waiting record in the linked project notes: `Waiting for: <deliverable>; source: <task ID/link when known>`. Treat this as prose, not a parser format. Re-read and merge the notes to preserve the goal and unrelated content. Confirm the notes update before completing startup. If that update fails or is uncertain, leave startup open and report the error.

   Completing startup does not complete the deliverable or project. Mark the selected human action complete:
   ```bash
   swift <plugin-root>/scripts/productivity-cli.swift reminders complete \
     --id "<action-id>"
   ```

3. Report: "Completed: '[action title]'"

4. Check remaining actions. After agent startup, propose support or review only when it is actionable. Waiting for output is not a ready action. Keep the project open while its deliverable remains incomplete:
   - **If other actions remain**: Report "Project [ProjectName] has N remaining actions." Return to Step 2.
   - **If no actions remain and a human step is actionable**: Auto-suggest adding the next action:
     > "No remaining actions — project will become stalled. Let's add the next action."
     Proceed to Step 4a. The user can select "Skip" in Step 4a's confirm prompt to decline and return to Step 2 (project becomes stalled).

If the project is waiting for agent output, report the wait and return to Step 2. Do not create a premature review action.

## Step 4c: Reschedule / Edit Action

1. If project has multiple actions, ask the user: "Which action to edit?"
   - If only one action (or arrived here via auto-infer for overdue), skip this question

2. **For overdue reschedule** (arrived from auto-infer):
   - Show the current deadline. Keep it unless the user changes it.
   - Ask the user for a new deadline or whether to remove the date if it was only a planning target. Use a date already supplied in the request without asking again.

3. **For general edit** (user selected "Edit action"):
   - Show current properties
   - Ask the user: "What to edit?" (multiple selections allowed)
     - Options: "Title", "Time estimate", "Priority", "Due date", "Done editing"
   - For each selected property, gather the new value:
     - Title: ask for new title text
     - Time estimate: Options "Quick", "1 Pomodoro", "2 Pomodoros", "Deep" map to @quick, @1pomo, @2pomo, @deep. Estimate only the current action’s human effort. Update the effort estimate in notes with the list change so an old estimate cannot remain. Label uncertain values as estimates; never replace unknown effort with zero.
     - Priority: options "High", "Medium", "Low", "None" (maps to 1, 5, 9, 0)
     - Due date: options "No due date", "Today", "Tomorrow", "This week", "Custom date"

4. Update the selected reminder in place using its `id` from the query. Pass only changed fields:
   ```bash
   swift <plugin-root>/scripts/productivity-cli.swift reminders update \
     --id "<action-id>" \
     --title "New title" \
     --list "@new-list"
   ```
   Use `--due "2026-01-15"` to set a deadline or `--clear-due` to remove it. Use `--priority` only when changing priority. Omit `--notes` when notes are unchanged. When editing agent planning notes, merge the changes with the current notes and preserve the project reference and all unrelated content. Pass the full merged value with `--notes`. Unspecified fields, including recurrence, stay unchanged.

   If the update fails, report the error and retain the original reminder. If its ID is stale, refetch and identify the intended action before retrying. Do not fall back to a title-only mutation.

5. Report: "Updated action '[title]'"

6. Return to Step 2.

## Step 5: Complete Project

1. Mark the project complete:
   ```bash
   swift <plugin-root>/scripts/productivity-cli.swift reminders complete \
     --id "<project-id>"
   ```

2. Complete any remaining linked actions:
   ```bash
   swift <plugin-root>/scripts/productivity-cli.swift reminders complete \
     --id "<action-id>"
   ```

3. Report: "Project '[ProjectName]' marked complete"

4. Return to Step 2.

## Step 6: Exit

When user selects "Done reviewing" in Step 2:

```
# Review Complete

Projects reviewed: 3
Actions completed: 2
Actions added: 1
Projects completed: 1
```

## Guidelines

- Prioritize overdue items — they always appear first in the overview
- Auto-infer actions for overdue/stalled projects to reduce questions
- Infer action properties from title text — only ask user to confirm
- Multiple actions per project: track all actionable tasks independently
- After completing an action, auto-suggest next action if project becomes stalled
- Create missing reminder lists automatically before creating reminders
- Handle CLI errors gracefully and report to user
- Match project names case-insensitively
- Use `yyyy-MM-dd` for date-only deadlines and `yyyy-MM-dd HH:mm` when the user specifies a time.
- Carry reminder IDs from queries into every complete or update command. Report success only after a successful CLI response. Refresh data before displaying the next overview.
- Use prior explicit instructions to identify the project, action, and requested changes before asking a question.

## Reference: Context Lists

| List | Type | Time Estimate |
|------|------|---------------|
| @quick | Human | Quick tasks (< 25 min) |
| @1pomo | Human | 1 Pomodoro (25 min) |
| @2pomo | Human | 2 Pomodoros (50 min) |
| @deep | Human | Deep focus (3+ pomodoros) |
| @agent | Legacy only | Convert to the current human action through confirmation |

## Reference: Priority Values

| Display | Value |
|---------|-------|
| High | 1 |
| Medium | 5 |
| Low | 9 |
| None | 0 |
