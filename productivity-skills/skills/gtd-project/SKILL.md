---
name: gtd-project
version: 3.2.0
description: "Use when reviewing GTD project status, adding or editing actions, completing or rescheduling actions, or completing, deleting, or restoring projects and actions."
---

Review and manage cloud GTD projects and their human actions. Use the
user's direct instructions first. Propose changes only where their intent
leaves a decision open.

Before every invocation, read the [cloud operating contract](../../references/gtd-cloud.md)
and [shared planning policy](../../references/gtd-planning.md). Use the cloud
contract for the private route, complete reads, UUID grouping, dates,
revisions, atomic writes, receipts, and recovery. Apply the planning policy
to every project and action. Missing cloud data or access makes the affected
review or operation unavailable; it does not authorize a native fallback.

## Gather

For a general review, read all open projects and linked actions. For a
specific instruction, read the selected project, actions, and links needed
to carry it out. Include legacy actions and relevant waiting evidence.
Retrieve closed or deleted records only when the requested operation needs
them. Follow the cloud identity rules; names help selection but do not
replace UUIDs.

Use the shared policy to assess each project's status and ready human
work. Read goals, blockers, pending results, and current output or support
evidence. Report unavailable facts and uncertain readiness explicitly.

For a general review, show overdue projects first, then projects with no
next action, then the rest. Show full project names, goals, status, the
independent Overdue flag, and linked actions. Keep waits visible when other
actions are ready. Distinguish repeated names with short unique ID suffixes.

## Select or propose

If the request already identifies the records and changes, proceed within
that authorization. Otherwise ask for a project or action only when its
identity is unresolved. Use **AskUserQuestion** when needed. A general
review can offer numbered projects and “Done reviewing”.

Use the shared readiness policy to propose the current human step:

- For a supported wait, report what is pending and keep the project open.
- For available output or a concrete support request, propose the review
  or support action.
- For a project with no next action, propose a concrete step only when its
  inputs are ready. Otherwise state the blocker or missing detail.
- For overdue work, show the existing deadline and its consequence. Keep
  that deadline unless the user authorizes a change. Overdue status alone
  does not authorize rescheduling or completion.

For an added action or an inferred edit, show one compact proposal with its
title, project, duration label, human effort or “Unknown”, priority, and
deadline or “No deadline”. Inherit project priority under the shared policy.
Ask for approval, correction, or skip only when the existing instructions
do not already cover those changes. Apply clear corrections without a
redundant confirmation.

For completion, deletion, or restoration, identify the selected UUIDs and
use the direct instruction or approved selection. Completing or deleting a
project affects only that project. Include linked actions only when the
user also authorized those specific actions. Do not infer their completion
from the project's state.

## Apply

Use a fresh read and the cloud transaction procedure for the authorized
records. Update the same UUID for edits and legacy conversion. Change only
requested fields. Merge note edits with the current notes so goals,
original references, runtime context, and unrelated content survive.
Preserve deadline semantics and fields outside the requested change.

Apply startup completion and its pending-result record atomically under
the shared lifecycle policy. Apply review creation and removal of only its
resolved wait atomically. Keep waiting projects open. These transitions do
not authorize agent dispatch.

Use soft deletion and explicit restoration through the cloud contract.
Project operations do not cascade to linked actions. When an authorized
operation includes selected actions, name those records in the same batch.

Confirm the receipt and readback before reporting success. Follow the
cloud conflict and exact-replay procedures for stale revisions or uncertain
responses. Refresh affected records before showing their resulting state.

## Report

Report the specific changes, resulting project status, pending results,
and any failed or uncertain operation. Preserve visibility of open actions
linked to a completed or deleted project.

After action completion, propose another human step only when its inputs
are ready and the user is still reviewing. A wait does not require a new
action. Finish a direct request after its result. In a guided review, return
to the remaining projects until the user selects “Done reviewing” or stops.
End with concise counts of the changes made.
