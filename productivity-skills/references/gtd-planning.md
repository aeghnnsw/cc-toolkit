# GTD planning

Use this policy whenever processing, reviewing, displaying, or selecting
GTD work. Raw capture preserves the user's wording; planning follows later.
The [cloud operating contract](gtd-cloud.md) defines storage operations,
identity, deadline representation, and recovery.

## Concrete human actions

A next action is a human step with ready inputs and an observable stopping
point. Write a concrete verb and object. Direct work, starting agent work,
answering an agent question, and reviewing a result use the same rule.
Examples:

- Send the source data and comparison brief to the agent.
- Answer the agent's question about the date range.
- Check the available comparison against the three acceptance criteria.

Preserve the user's intended outcome. A preferred work date is not a
deadline. A suggestion does not authorize a new commitment, a stored change,
or agent dispatch.

## Readiness and project status

Determine readiness from the meaning of current notes, user statements,
and available task or output evidence. An open record, priority, or duration
label alone does not prove readiness. State unknown readiness explicitly.
Keep blocked work visible and outside the ready-action pool.

Use this one rule in both project review and overview:

| Status | Meaning |
| --- | --- |
| Active | At least one concrete human action has ready inputs and no known blocker. |
| Waiting | No human action is ready, and current evidence supports an unresolved external result or response. |
| No next action | Neither ready human work nor a supported wait is established. State any blocker, uncertain readiness, or deliberate deferral. |

Show pending results beside Active too. Exclude Waiting projects from the
count of projects with no next action. Read failure makes the affected
status unavailable; it does not establish a healthy or empty system.

Overdue is an independent deadline flag. Show it beside any status when
the project or a linked action is overdue. Apply the cloud date rules.
Keep the existing deadline unless the user authorizes a change.

Interpret waits semantically. `Waiting for:` is readable example prose,
not a required field or parser format. A supported free-form pending result
can establish a wait. A resolved past wait, quoted template, or the word
“waiting” alone cannot. If evidence conflicts, state what is uncertain
instead of promoting the project to Active.

## Human effort

Estimate the current human step, separately from unattended agent runtime.
Use current stored human effort and explicit effort notes before duration
labels. An explicit unknown-effort note remains unknown. If the stored
evidence conflicts, state the uncertainty until it is resolved. Missing
effort is not zero.

Use these duration labels for new human actions when the estimate supports
one:

| Label | Human effort |
| --- | --- |
| `@quick` | Less than 25 minutes |
| `@1pomo` | About 25 minutes |
| `@2pomo` | About 50 minutes |
| `@deep` | About 90 minutes or more |

A label describes duration, not readiness. A capture's placeholder `@quick`
label does not establish a 15-minute action. Estimate a known concrete step
when its scope supports that estimate, and label assumptions. Keep effort
unknown when it does not. A legacy `@agent` label supplies no human duration.
Never create new actions in that legacy label.

When an authorized edit changes effort or its label, update the effort
notes with it so an old estimate cannot remain. Preserve unrelated notes.

## Priority

Use High (1), Medium (5), Low (9), and None (0) as optional priority hints.
None means unset, not highest priority. Preserve an explicit zero. New
clarified work defaults to Medium unless the user supplies another priority
or urgency context supports a different proposal. A project action inherits
the project's stored priority, including zero, unless the user overrides
it. Use Medium only when that project priority is unavailable.

Choose feasible actions by context, available time, and energy. Then weigh
importance, real deadlines, and consequences against current commitments
and goals. A stored priority label alone does not select the next action.

## Startup, support, wait, and review

Infer startup only for work that has not started and whose inputs are ready.
Infer support only for a concrete human question or need. Infer review only
when the output is available. Use current evidence; do not restart running
work or create a premature review action.

An outcome that needs startup and later review is a project. Reuse an
existing project when it covers that outcome. Preserve the full deliverable
in its goal and keep known asynchronous runtime and source references in
notes. Runtime does not consume human action time.

When completing startup while later output or review remains, save the
expected pending result in the linked project notes and complete the
startup action in one atomic batch. For example: `Waiting for: price
comparison; source: <task ID or link when known>`. Merge with the current
goal and notes. Failure leaves both changes unapplied. Resolve an uncertain
response through the cloud receipt procedure before retrying.

When output becomes available, propose its concrete review action. Create
and link the approved action and remove only its resolved waiting note in
one atomic batch. Preserve unrelated waits and notes. Failure retains the
wait. Reconcile an uncertain response through the same cloud procedure.

Startup completion completes that human action only. It does not complete
the deliverable or project. A waiting project stays open. Propose another
human step only when its inputs are ready. Project completion or deletion
does not authorize changes to linked actions.

## Legacy actions

Keep existing `@agent` actions visible. For read-only selection, infer the
current human step from notes and known state, label the suggestion, and
leave the stored action unchanged. Unknown human effort remains unknown
unless a concrete step supports a new, stated estimate.

During an authorized edit or processing batch, propose conversion to the
current concrete human action and supported duration label. Update the
same UUID. Preserve the full original deliverable, runtime context,
original source references, UUID links, priority, deadline semantics, and
unrelated notes. Keep waiting or blocked records as they are when no human
step is ready. Retiring a label does not authorize bulk conversion,
completion, or deletion.

## Agenda time budget

All human actions share one time budget and cannot overlap. Include breaks
and transitions when judging fit. Count each action's human work once.
Unattended agent runtime can overlap human work. Dependent actions need
ready inputs.

For a requested full agenda, a future review slot can be conditional on
output being ready. Label it as conditional. Provide independent work that
fits that slot if the output is late. Show deferred review time as remaining
work. Do not promise completion when runtime is unknown.

Sources: [GTD action selection](https://gettingthingsdone.com/2010/06/you-are-in-control-when-you-can-see-it-all/)
and [GTD priority decisions](https://gettingthingsdone.com/2008/08/determining-priority-gtd-style/).
