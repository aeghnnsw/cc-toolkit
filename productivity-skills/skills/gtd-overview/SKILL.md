---
name: gtd-overview
version: 1.0.0
description: This skill should be used when the user asks to "list all projects and actions", "show gtd overview", "show all my projects", "list everything", "what's in my gtd system", "show standalone actions", or wants a complete read-only listing of all GTD projects with their actions plus all individual actions not linked to any project.
---

<!--
Projects list: "Projects" in macOS Reminders
Project naming: {CamelCaseSummary}-{YYYYMMDD} (e.g., VacationResearch-20260112)
Action reference: #{FullProjectName} in notes field
Project notes: "Goal: [end goal description]"
Human context lists: @quick, @1pomo, @2pomo, @deep
Agent context list: @agent (no duration, async)
CLI: swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift

Key principle: Read-only overview. Display projects with nested actions, then standalone actions, then a summary. No modifications, no questions — direct user to /gtd-project or /gtd-process for changes.
-->

Display a complete read-only overview of the GTD system: every open project with its linked actions nested underneath, followed by all standalone actions not linked to any project. No interaction required — gather, group, and display.

## CLI Tool

Run Swift source directly (no build step required):

```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift <command>
```

## Step 1: Gather Data

1. Query all open projects:
   ```bash
   swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders incomplete "Projects"
   ```

2. Query all context lists for actions:
   ```bash
   for context in "@quick" "@1pomo" "@2pomo" "@deep" "@agent"; do
     swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders incomplete "$context"
   done
   ```

3. Query overdue reminders (uses Apple's datetime-aware overdue detection):
   ```bash
   swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders overdue
   ```

If a context list does not exist, treat it as empty — do not create lists in this read-only skill.

## Step 2: Group Actions

Parse the JSON output and classify every action from the context lists:

1. **Project actions**: Notes field contains `#{ProjectName}` matching an open project (case-insensitive). Group under that project.
2. **Orphaned actions**: Notes field contains a `#{...}` reference that matches no open project (project completed or deleted). Group into an "Orphaned" section.
3. **Standalone actions**: Notes field contains no `#{...}` reference. Group into the "Standalone Actions" section.

For each project, determine status (evaluated in order of severity):
- **Overdue** (⚠️): Any linked action OR the project itself appears in the overdue query results
- **Stalled** (⚠️): Has 0 pending linked actions
- **Healthy** (✓): Has 1+ pending linked actions, none overdue

Extract each project's end goal from its notes field (format: "Goal: [description]").

## Step 3: Display Overview

Present projects sorted by urgency (overdue first, then stalled, then healthy), followed by standalone actions grouped by context list:

```
# GTD Overview

## Projects (3)

1. ⚠️ ClientProject-20260110 [Medium] — OVERDUE
   Goal: Invoice paid and project closed
   • "Send invoice" (@quick) — OVERDUE (due 2026-01-10)

2. ⚠️ ReviewQ1Roadmap-20260115 [High] — STALLED
   Goal: Roadmap approved by stakeholders
   (no pending actions)

3. ✓ VacationResearch-20260112 [High]
   Goal: Flights and hotel booked for Hawaii trip
   • "Research flights to Hawaii" (@1pomo)
   • "Email hotel for rates" (@quick)
   • "Analyze flight price trends" (@agent) — due 2026-01-20

## Standalone Actions (3)

@quick
   • "Call dentist to schedule appointment" — due 2026-01-18
@2pomo
   • "Write blog post draft" [High]
@agent
   • "Summarize meeting notes" — OVERDUE (due 2026-01-12)

## Summary

Projects: 3 (1 overdue, 1 stalled, 1 healthy)
Project actions: 4 | Standalone actions: 3 | Overdue: 2
```

Formatting rules:
- Show priority in brackets only when set (High/Medium/Low; omit None)
- Show due date only when set; mark overdue items with `— OVERDUE (due YYYY-MM-DD)`
- Omit empty context-list groups in the standalone section
- If there are orphaned actions, add an `## Orphaned Actions` section after standalone actions, listing each with its dangling `#{ProjectName}` reference

Empty states:
- No projects and no actions: "GTD system is empty. Use /gtd-inbox to capture items and /gtd-process to organize them."
- No projects but actions exist: skip the Projects section, note "No open projects."
- Projects exist but no standalone actions: note "No standalone actions."

## Step 4: Suggest Next Steps

After the overview, append one line pointing to follow-up skills based on what was found:
- Overdue or stalled projects → "Run /gtd-project to reschedule overdue actions or add next actions."
- Orphaned actions → "Orphaned actions reference completed projects — run /gtd-project to clean up."
- Otherwise → "Run /gtd-next to pick what to work on."

Do not perform any modifications in this skill.

## Guidelines

- Read-only: never create, complete, edit, or delete reminders or lists
- No user interaction: gather, group, display — done
- Match project names case-insensitively when linking actions
- Sort actions within a project by overdue first, then by due date, then by priority
- Handle CLI errors gracefully: report which query failed and continue with available data

## Reference: Context Lists

| List | Type | Time Estimate |
|------|------|---------------|
| @quick | Human | Quick tasks (< 25 min) |
| @1pomo | Human | 1 Pomodoro (25 min) |
| @2pomo | Human | 2 Pomodoros (50 min) |
| @deep | Human | Deep focus (3+ pomodoros) |
| @agent | Agent | N/A (async, monitor progress) |

## Reference: Priority Values

| Display | Value |
|---------|-------|
| High | 1 |
| Medium | 5 |
| Low | 9 |
| None | 0 |
