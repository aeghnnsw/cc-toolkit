---
name: gtd-process
description: Use when processing, triaging, or clarifying GTD inbox items into projects and context-list actions following the GTD clarify and organize workflow.
---

Process GTD inbox items into concrete actions and projects. Present one batch proposal for approval or corrections. Honor existing explicit authorization.

## CLI Tool

Run the Swift source directly. `<plugin-root>` is the installed plugin directory that contains `scripts/` and `codex-skills/` (two levels above this skill folder). Resolve it to an absolute path and substitute it in every command.

```bash
swift <plugin-root>/scripts/productivity-cli.swift <command>
```

## Step 1: Read the Requested Items

Read `~/.gtd/inbox.md` (shared with the Claude Code skill; keep this exact path). If missing, create it with `# Inbox` and a blank line. If empty, report that and exit.

Process all current items by default. If the user requests one item or a subset, use only that scope. Track each original item occurrence, including identical lines. Do not revisit skipped items in the same session. Stop when the user asks to stop.

Read the available lists and existing projects:

```bash
swift <plugin-root>/scripts/productivity-cli.swift reminders lists
swift <plugin-root>/scripts/productivity-cli.swift reminders incomplete "Projects"
```

If `Projects` is absent, there are no existing projects. Create missing lists only when needed for an approved proposal. Create reminders only in `Projects`, `@quick`, `@1pomo`, `@2pomo`, and `@deep`. Read legacy `@agent` reminders only within the requested scope. Do not expand inbox processing into bulk conversion. Propose conversion through the batch approval flow. Update the same reminder ID to a concrete human action and duration list. Preserve its original deliverable, project reference, and other notes.

## Step 2: Clarify and Propose a Batch

Before proposing actions that involve agent work or converting legacy reminders, read the [shared GTD planning policy](../../references/gtd-planning.md).

For each item, propose a standalone action, an action linked to an existing project, a new project with its first action, or leaving it in the inbox.

- Write an action with a concrete verb, an object, and a clear stopping point. Use only facts available from the item and context.
- Preserve the user's goal. Researching flights does not authorize booking flights. Do not invent a larger project or additional commitments.
- If agent work requires startup and later support or review, link the current action to an existing project for that outcome, or propose a new project. Keep the full deliverable in the project goal.
- For a new project, state the intended outcome and name it `{CamelCaseSummary}-{YYYYMMDD}`. Its first action must be something the user can start now.
- Express agent work as the current concrete human action: start the agent, support its work, or review its output. Use `@quick` (<25 min), `@1pomo` (25 min), `@2pomo` (50 min), or `@deep` (90+ min). Estimate only that action’s human effort. Label uncertain values as estimates; never treat unknown effort as zero. Keep the intended agent deliverable and asynchronous runtime, when known, in notes. Waiting for output is not a ready action.
- Priority labels are optional Reminders hints. Use priority from explicit urgency cues, or Medium by default. Project actions inherit project priority unless overridden.
- Leave projects and actions undated by default, including agent tasks. Set a due date only for a real deadline supplied by the user. A preferred work date is not a deadline. Keep date-only deadlines as `YYYY-MM-DD`; add `HH:mm` only when the user supplied a time. Resolve relative deadlines from the current local date, or reuse a capture-time date annotation when available. Do not give a first action the project deadline unless that deadline also applies to the action.
- Ask one focused question when missing information changes the action, outcome, or deadline and context cannot resolve it. Leave that item in the inbox while processing clear items. Leave skipped and non-actionable items there too, and state why. Do not force them into tasks.

Show a compact numbered batch with the proposed action, project if any, list, priority, and deadline or "No deadline". Show each action’s human effort estimate. Include the reason for each item left in the inbox.

Example, when the route and dates are already known:

```text
Item: Research vacation flights
Action: Confirm route and dates, then send the agent the flight comparison request.
List: @quick
Human effort (estimate): 5 min.
Notes: Agent deliverable: shortlist of flight prices and travel times. Async runtime: Unknown.
Priority: Medium
Due: No deadline
```

Ask the user once to approve the batch or give numbered corrections, skips, or a stop request.

Apply clear corrections without another approval round. Skip items the user excludes. If the user stops, leave all unprocessed items in the inbox and exit. Do not repeat approval for work already explicitly authorized. An instruction to process the inbox alone does not approve an inferred proposal.

## Step 3: Create the Approved Reminders

Create each missing destination list with:

```bash
swift <plugin-root>/scripts/productivity-cli.swift reminders create-list "<list>"
```

For a new project, create its outcome reminder first:

```bash
swift <plugin-root>/scripts/productivity-cli.swift reminders create \
  --title "ProjectName-YYYYMMDD" \
  --list "Projects" \
  --priority 5 \
  --notes "Goal: [approved outcome]"
```

Create the standalone action, linked project action, or first action:

```bash
swift <plugin-root>/scripts/productivity-cli.swift reminders create \
  --title "[approved concrete action]" \
  --list "[approved context list]" \
  --priority 5
```

Use `--notes` for the approved notes, including the current action’s human effort estimate. Include `#{ProjectName-YYYYMMDD}` for a linked action. Preserve the intended agent deliverable, runtime context, and other relevant notes. For an approved legacy conversion, use `reminders update --id "<reminder-id>"` with the human action title, duration list, and full merged notes. Do not create a replacement reminder. Use the approved priority: 1=High, 5=Medium, 9=Low, 0=None. Add `--due "YYYY-MM-DD"` only for an approved deadline, or `--due "YYYY-MM-DD HH:mm"` when its time was supplied.

For later completion and review, follow the shared planning policy. Save a waiting record in the project notes before completing startup. Preserve the goal and unrelated notes. If that write fails, leave startup open. Propose support or review only when it is actionable.

Check each command result. Record reminder IDs from successful creates or conversions. Confirm each conversion update before removing its inbox item. If a create fails or its result is uncertain, retain the inbox item and report the partial result. Inspect the destination list before retrying an uncertain create. Reuse confirmed reminders and create only missing records. If processing must resume later, preserve the confirmed IDs with the retained inbox item so a later run can avoid duplicates.

## Step 4: Remove Completed Items and Report

Remove an inbox item only after every reminder required by its proposal is confirmed created or updated. For a new project, both the project and first action must exist. Re-read the inbox before removal and edit only the processed occurrence. Preserve concurrent additions and identical items. If removal fails, report the successful reminder IDs and retain that information for recovery.

Report what was created and what remains, with reasons for skipped, unclear, non-actionable, or failed items. Finish after the requested batch. Do not ask whether to continue or loop through retained items.
