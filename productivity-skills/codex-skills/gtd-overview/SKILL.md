---
name: gtd-overview
description: Use when listing the whole GTD system read-only — every open project with its actions plus standalone actions not linked to any project.
---

Show every open GTD project and action in a compact, read-only report. Use rendered Markdown, with a summary first and one action table per project. Keep all records visible; this is an inventory, not a task recommendation.

## Gather

Resolve `<plugin-root>` to the absolute installed plugin directory, two levels above this skill folder. It contains `scripts/` and `codex-skills/`.

```bash
swift <plugin-root>/scripts/productivity-cli.swift reminders incomplete
swift <plugin-root>/scripts/productivity-cli.swift reminders overdue
```

Keep projects from `Projects` and actions from `@quick`, `@1pomo`, `@2pomo`, `@deep`, and `@agent`. Match overdue results by reminder `id`. Ignore other lists. Missing lists need no setup.

If the incomplete query fails, report that the overview is unavailable. If only the overdue query fails, show the inventory with an explicit “Overdue status unavailable” notice. Show overdue counts as “unavailable”, omit overdue ranking, and use only the action-presence labels in that case. Do not report a failed query as an empty or healthy system.

## Group

- Match the full `#{ProjectName}` reference in action notes to an open project title, case-insensitively. Keep the exact stored names and IDs for later operations.
- Put actions with no reference under **Standalone actions**.
- Put references with no matching open project under **Unmatched project links**. Display the reference; it can indicate a renamed, completed, or deleted project. If more than one project matches, show the action here as ambiguous instead of guessing.
- Extract each goal from `Goal:` in the project notes.
- Retain the existing status rules: overdue project or action → **Overdue**; no linked actions → **No next action**; otherwise → **Active**. “Active” means actions exist, not that progress was verified.

Count unique reminder IDs. Count overdue actions separately from overdue projects. Include unmatched actions in the action total.

## Display

1. Start with totals: projects, actions, overdue actions, and projects with no next action. Include the overdue-project count when nonzero. Show unmatched-link count when present.
2. Show projects with overdue records first, then projects with no actions, then the rest. Each project gets a heading with its full stored name, a short status line, its goal, and a table of all linked actions. If names repeat, append a short unique ID suffix to distinguish those headings.
3. Use **Action | List | Due | Priority** columns. Show `—` for unset dates and priority. Use `High`, `Medium`, or `Low` for priorities 1, 5, or 9. Show a due time only when stored. Undated work is normal; give it no warning.
4. Within each project, sort overdue actions first, then dated actions by due date, then undated actions. Break ties by priority, then title. Mark overdue dates with **Overdue** text. Use the same order within standalone lists.
5. Show standalone actions in one table, grouped by list. Add unmatched links last with their original references. Omit empty sections.
6. Escape pipes and line breaks in table cells. Preserve full action titles. Keep lengthy notes out of the report; display project goals as prose above the table. Use compact bullets instead of tables if the user requests a narrow display.

Example layout (illustrative records, as of 7 Sep 2026):

# GTD overview

**3 projects · 4 actions**

Needs attention: 1 overdue action · 1 overdue project · 1 project without a next action.

### ClientInvoice-20260901

**Overdue** · High priority · Project due: 10 Sep 2026

Goal: Invoice paid and project closed.

| Action | List | Due | Priority |
| --- | --- | --- | --- |
| Send the approved invoice to the client | @quick | **Overdue · 4 Sep 2026** | High |

### InsuranceRenewal-20260903

**No next action** · Medium priority

Goal: Insurance renewed before the current policy expires.

No open actions linked to this project.

### VacationResearch-20260905

**Active** · Medium priority

Goal: Compare flight options for the trip.

| Action | List | Due | Priority |
| --- | --- | --- | --- |
| Compare three flights for the chosen dates | @1pomo | — | Medium |
| Summarize the cancellation terms for those flights | @agent | — | Medium |

### Standalone actions

| Action | List | Due | Priority |
| --- | --- | --- | --- |
| Call the dentist to request an appointment | @quick | — | — |

## Finish

If no GTD records exist, say “No open GTD projects or actions.” This does not mean the capture inbox is empty; this report covers Reminders only.

End with one short next step when useful: use `gtd-next` to choose work, or `gtd-project` to inspect a project that needs attention. Keep the report read-only. Do not create lists, change reminders, ask for a selection, or imply that displayed actions were started.
