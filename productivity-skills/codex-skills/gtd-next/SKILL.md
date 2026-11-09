---
name: gtd-next
description: "Use when deciding what to work on next or requesting an agenda, with calendar-aware selection of cloud GTD human actions."
---

Recommend one concrete human action from the cloud GTD inventory. Give a
short reason and at most two feasible alternatives. Give a full agenda only
when the user asks for one. This workflow is read-only. It does not change
GTD records, create Calendar blocks, or dispatch agent work.

Before every invocation, read the [cloud operating contract](../../references/gtd-cloud.md)
and [shared planning policy](../../references/gtd-planning.md). Use the cloud
contract for the GTD binding, complete reads, UUID links, and dates. Use
the planning policy for readiness, effort, priority, and the human time
budget. Missing cloud data or access makes selection unavailable; it does
not authorize a native GTD fallback.

## Gather

Read the complete open cloud action inventory with the projects and links
needed to interpret it. Include undated, standalone, blocked, and legacy
actions. Use stored titles, notes, effort, priorities, deadlines, and current
support or output evidence. Follow the shared policy for legacy actions.

Read the local time and today's native Calendar events. `<plugin-root>` is the installed plugin directory two levels above this skill folder. Resolve it to an absolute path and substitute it below.

```bash
date "+%Y-%m-%d %H:%M %Z"
swift "<plugin-root>/scripts/productivity-cli.swift" calendars today
```

- An event that started earlier can still occupy the current time. Treat
  timed events as occupied unless known context says they are free. The
  native CLI does not expose event availability.
- If an event is in progress, state that the user is currently busy. Place
  the recommendation after it ends. Include overlapping events when finding
  the next free interval.
- Bound the interval by the next event and any known workday end. Allow
  known preparation or travel time. Otherwise leave a five-minute buffer
  before the next event.
- Use known all-day commitments as constraints. An all-day label alone
  does not establish occupied hours.
- If no event or known end bounds the interval, suggest a bounded focus
  session. Use 25 minutes when no other context is available. State this
  as an assumption, not confirmed availability. Do not invent work hours.
- If Calendar access fails, availability is unknown. State the failure.
  A bounded session assumption can support a conditional recommendation,
  but the failed read does not establish free time.
- If the known workday has ended or no usable interval remains, say so.
  Do not place work beyond that limit unless the user requested it.

## Select

1. Filter for known location, tools, energy, available time, and ready
   inputs. Include breaks and transitions when judging fit. Use known
   context without a routine selection question.
2. Weigh real deadlines, consequences, and priority among feasible actions.
   An overdue date does not make blocked work ready or exclude useful
   undated work.
3. Choose one observable human next action. If the stored title is a broad
   outcome, infer a bounded first step only when notes and current context
   support it. Label the step and its effort as a suggestion. Keep the
   stored record unchanged.
4. Use the shared effort rules. Unknown effort is not zero. A capture's
   placeholder duration label does not prove that it fits. If a known human
   step supports a bounded estimate, state that estimate and its assumption.
5. Skip steps that are unclear, blocked, or cannot fit. Briefly explain a
   relevant skipped candidate, such as an urgent item. Give at most two
   alternatives, each subject to the same constraints.

If no human action fits, state why. If every candidate lacks a clear next
step, identify the missing detail. Do not invent an action to fill the
response. Starting, supporting, and reviewing agent work use the same
readiness and time rules as other human actions.

## Report

Lead with the action and human effort estimate. Add one short reason for
its fit or urgency. Show its project and deadline when useful. Use the cloud
date rules for an Overdue flag. State any availability assumption. Render
Markdown normally, without a code fence.

### Full agenda on request

Arrange feasible human actions in sequential blocks within the bounded
interval. Label blocks as Human focus, Start agent task, Support agent task,
or Review agent result. Include five-minute breaks between 25-minute work
sessions and retain transition time before events. A longer action can span
sessions. Count each action's human work once under the shared time budget.

Use the shared policy for a conditional future review slot and independent
work if the output is late. State deferred work and unknown runtime. Show
estimates and assumptions clearly. An agenda remains a recommendation;
it does not schedule events or start tasks.
