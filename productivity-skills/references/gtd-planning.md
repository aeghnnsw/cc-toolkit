# GTD planning

## Priority

Reminders supports High (1), Medium (5), Low (9), and None (0). These are
optional hints, not fixed GTD ranks. None means unset, not highest priority.
The GTD capture convention uses Medium by default. Project actions inherit
project priority unless the user overrides it. Preserve these conventions
and existing values unless the user requests a change.

Choose feasible actions by context, available time, and energy. Then weigh
importance, real deadlines, and consequences against the user's current
commitments and goals. Reassess priority when circumstances change. A stored
label alone does not decide the next action.

Sources: [GTD action selection](https://gettingthingsdone.com/2010/06/you-are-in-control-when-you-can-see-it-all/)
and [GTD priority decisions](https://gettingthingsdone.com/2008/08/determining-priority-gtd-style/).

## One model for human actions

Every next action describes something the user can do. This includes direct
work, starting an agent task, answering an agent question, and reviewing an
agent result. Store all new actions in `@quick`, `@1pomo`, `@2pomo`, or `@deep`
according to the human time needed for that action. `@agent` is a legacy list,
not a destination for new work.

Write a concrete verb, object, and stopping point. Examples:

- Send the agent the source data and comparison brief.
- Answer the agent's question about the date range.
- Check the agent's comparison against the three acceptance criteria.

Estimate each action's own human duration. Keep unattended runtime in notes
only when useful for dependencies. It does not consume human action time.
Use known estimates first. Infer bounded estimates when possible and label
assumptions. Missing time is not zero time. If the step is unclear, identify
the missing information.

All human actions share one time budget and cannot overlap. Add breaks and
transitions when checking calendar fit. Count each action once. Unattended
agent work can overlap human work, but dependent actions need ready inputs.
Recommend startup only when the task has not started and required inputs are
available. Recommend support when there is a concrete question or need.
Recommend review when the output is available. Use evidence for these states.

For a full agenda, a future review slot can be conditional on output being
ready. Label it as conditional. Provide independent work that fits the slot
if output is late. State deferred review time as remaining work. Do not
promise completion when runtime is unknown.

Completing a startup reminder completes that human action. It does not
complete the agent deliverable or project. An outcome that requires startup and later review is a project; reuse an
existing project when it covers the outcome. Before completing startup, retain
the expected result in its project notes. For example: `Waiting for: flight
comparison; source: <task ID or link when known>`. Preserve the goal and all
unrelated notes. This is prose, not a new CLI field. If that write fails, retain
the startup reminder and report the partial result.

When the result is ready, propose a review action. Clear only the resolved
waiting note after that action is confirmed created. Retain it on failure.
A project waiting for output stays open; show its wait instead of forcing an
unready next action. Propose the next human action when its inputs are ready. Keep blocked follow-ups out of the ready-action pool.
A planning recommendation does not dispatch work or change reminders.

## Existing agent reminders

Continue reading `@agent` when present. For selection, infer the current
human next step from its notes and known state. Label that suggestion and
leave the stored reminder unchanged in read-only workflows.

When processing or editing with the user's authorization, propose converting
the legacy reminder to the current concrete human action and its time-based
list. Update the same reminder ID. Preserve its original deliverable in notes,
project reference, deadlines, priority, and unrelated content. Use known
state to choose startup, support, or review; avoid starting running work again.
If the task is waiting with no actionable human step, retain it and explain
what it awaits. Convert it when an actionable step is known. Do not bulk move
or complete legacy reminders merely because the list is retired.
