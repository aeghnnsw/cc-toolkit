---
name: gtd-process
version: 3.2.0
description: This skill should be used when the user asks to "process inbox", "process items", "triage inbox", "clarify inbox", "organize inbox", "categorize tasks", or wants to process GTD inbox items into projects or actions following the GTD clarify/organize workflow.
---

Process GTD inbox items into concrete actions and projects. Present one batch proposal for approval or corrections. Honor existing explicit authorization.

## CLI Tool

```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift <command>
```

## Step 1: Read the Requested Items

Read `~/.gtd/inbox.md`. If missing, create it with `# Inbox` and a blank line. If empty, report that and exit.

Process all current items by default. If the user requests one item or a subset, use only that scope. Track each original item occurrence, including identical lines. Do not revisit skipped items in the same session. Stop when the user asks to stop.

Read the available lists and existing projects:

```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders lists
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders incomplete "Projects"
```

If `Projects` is absent, there are no existing projects. Create missing lists only when needed for an approved proposal. Use only `Projects`, `@quick`, `@1pomo`, `@2pomo`, `@deep`, and `@agent`.

## Step 2: Clarify and Propose a Batch

For each item, propose a standalone action, an action linked to an existing project, a new project with its first action, or leaving it in the inbox.

- Write an action with a concrete verb, an object, and a clear stopping point. Use only facts available from the item and context.
- Preserve the user's goal. Researching flights does not authorize booking flights. Do not invent a larger project or additional commitments.
- For a new project, state the intended outcome and name it `{CamelCaseSummary}-{YYYYMMDD}`. Its first action must be something the user or agent can start now.
- Use `@agent` for work an agent can perform with the available inputs and access. Use human lists for calls, physical work, and decisions that need the user. Estimate human effort: `@quick` (<25 min), `@1pomo` (25 min), `@2pomo` (50 min), or `@deep` (90+ min).
- Use priority from explicit urgency cues, or Medium by default. Project actions inherit project priority unless overridden.
- Leave projects and actions undated by default, including agent tasks. Set a due date only for a real deadline supplied by the user. A preferred work date is not a deadline. Keep date-only deadlines as `YYYY-MM-DD`; add `HH:mm` only when the user supplied a time. Resolve relative deadlines from the current local date, or reuse a capture-time date annotation when available. Do not give a first action the project deadline unless that deadline also applies to the action.
- Ask one focused question when missing information changes the action, outcome, or deadline and context cannot resolve it. Leave that item in the inbox while processing clear items. Leave skipped and non-actionable items there too, and state why. Do not force them into tasks.

Show a compact numbered batch with the proposed action, project if any, list, priority, and deadline or "No deadline". Include the reason for each item left in the inbox.

Example, when the route and dates are already known:

```text
Item: Research vacation flights
Action: Compare flights for the agreed route and dates; save prices and travel times in a shortlist.
List: @agent
Priority: Medium
Due: No deadline
```

Use **AskUserQuestion** once to approve the batch or collect numbered corrections, skips, or a stop request.

Apply clear corrections without another approval round. Skip items the user excludes. If the user stops, leave all unprocessed items in the inbox and exit. Do not repeat approval for work already explicitly authorized. An instruction to process the inbox alone does not approve an inferred proposal.

## Step 3: Create the Approved Reminders

Create each missing destination list with:

```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders create-list "<list>"
```

For a new project, create its outcome reminder first:

```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders create \
  --title "ProjectName-YYYYMMDD" \
  --list "Projects" \
  --priority 5 \
  --notes "Goal: [approved outcome]"
```

Create the standalone action, linked project action, or first action:

```bash
swift ${CLAUDE_PLUGIN_ROOT}/scripts/productivity-cli.swift reminders create \
  --title "[approved concrete action]" \
  --list "[approved context list]" \
  --priority 5
```

For a linked action, add `--notes "#{ProjectName-YYYYMMDD}"`. Use `@agent` for approved agent tasks. Use the approved priority: 1=High, 5=Medium, 9=Low, 0=None. Add `--due "YYYY-MM-DD"` only for an approved deadline, or `--due "YYYY-MM-DD HH:mm"` when its time was supplied.

Check each command result. Record the reminder IDs from successful creates. If a create fails or its result is uncertain, retain the inbox item and report the partial result. Inspect the destination list before retrying an uncertain create. Reuse confirmed reminders and create only missing records. If processing must resume later, preserve the confirmed IDs with the retained inbox item so a later run can avoid duplicates.

## Step 4: Remove Completed Items and Report

Remove an inbox item only after every reminder required by its proposal is confirmed created. For a new project, both the project and first action must exist. Re-read the inbox before removal and edit only the processed occurrence. Preserve concurrent additions and identical items. If removal fails, report the successful reminder IDs and retain that information for recovery.

Report what was created and what remains, with reasons for skipped, unclear, non-actionable, or failed items. Finish after the requested batch. Do not ask whether to continue or loop through retained items.
