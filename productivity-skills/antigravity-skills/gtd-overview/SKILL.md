---
name: gtd-overview
description: "Use when listing the whole GTD system read-only: every open project with its actions, standalone actions, and unresolved project links."
---

Show every open cloud GTD project and action in a compact, read-only
inventory. Keep blocked and legacy work visible. This workflow does not
change records or dispatch work.

Before every invocation, read the [cloud operating contract](../../references/gtd-cloud.md)
and [shared planning policy](../../references/gtd-planning.md). Use the cloud
contract for the GTD binding, complete reads, UUID grouping, unique
counts, and dates. Use the planning policy for every project's status.
Missing cloud data or access makes the inventory unavailable; it does not
authorize a native fallback.

## Gather

Read the complete open project and action inventory and its links through
the cloud contract. Resolve referenced project identities as that contract
requires. Include actions linked to closed or deleted projects and actions
with unresolved original references. Exclude inbox captures from this
report and its totals.

Use the shared policy to assess readiness, waits, and blockers from the
available evidence. Keep the status and Overdue flag separate. Show pending
results beside any status, including Active. Do not derive readiness from
an open action, duration label, or priority alone.

An incomplete read cannot establish complete totals or an empty system.
Report the affected inventory or status as unavailable. A partial report
must identify its missing coverage and omit unsupported totals.

## Display

1. Start with unique counts of open projects and actions, overdue actions,
   overdue projects, and projects with no next action. Include the count of
   actions with unresolved or closed-project links when present. Follow
   cloud counting rules when one action links to several projects.
2. Show overdue projects first, then projects with no next action, then the
   rest. Give each project its full stored name, status, deadline flag,
   goal, and a table of all linked open actions. For repeated names, append
   a short unique ID suffix. State blockers and uncertain readiness.
3. Use **Action | Duration label | Human effort | Due | Priority** columns.
   Preserve full titles. Show “Unknown” for unknown effort, “—” for no
   deadline, and the shared priority labels. Show a due time only when
   stored. Undated work needs no warning.
4. Within each project, show overdue actions first, then dated actions by
   deadline, then undated actions. Break ties by High, Medium, Low, None,
   then title. This is display order, not a recommendation to start work.
   Mark overdue dates with **Overdue** text.
5. Show standalone actions in one table, grouped by duration label. Show
   unmatched links and links to closed or deleted projects in a separate
   section with their known identity or original reference. Use the same
   action order. Omit empty sections.
6. Escape pipes and line breaks in table cells. Keep lengthy notes outside
   tables. Show goals, waits, and blockers as short prose. Use compact
   bullets when the user requests a narrow display.

## Report

Say “No open GTD projects or actions” only after a complete successful read
establishes that result. This does not mean the capture inbox is empty.

When useful, end with one short next step: use `gtd-next` to choose work or
`gtd-project` to inspect a project. Do not ask for a selection or imply that
the displayed actions have started.
