---
name: gtd-inbox
description: "Use when capturing thoughts or tasks into the GTD inbox, when the user's instructions ask you to add waiting items to the GTD inbox (agent captures), or when listing, counting, removing, clearing, or restoring inbox items."
---

Manage raw GTD captures in the configured Supabase store. Save captures
immediately. Keep their wording and scope.

Before any operation, read the [cloud operating contract](../../references/gtd-cloud.md)
and [shared planning policy](../../references/gtd-planning.md). Use the cloud
contract for the GTD binding, connector calls, UUIDs, revisions, atomic
writes, receipts, and recovery. Missing access makes the operation
unavailable. It does not authorize a local or Reminders fallback.

## Gather

Use the request to choose capture, list, count, remove, clear, or restore.
An empty invocation lists pending captures. When the user's instructions
ask you to add waiting items to the GTD inbox, follow
[Agent capture](#agent-capture). Ask only when the intended
operation or record is unclear. Keep the question concise.

For a capture, validate the route and write without first organizing the
inbox. For list or count, read the complete pending inbox. For removal or
clear, read the pending records and retain the selected UUIDs. For explicit
restoration, retrieve the requested deleted records through the cloud
contract.

## Select

- **Capture:** Keep each supplied occurrence, including identical text, as
  a distinct record. Do not merge similar thoughts or broaden their scope.
  Do not clarify or plan the task during capture. An agent capture is
  the exception: it adds a proposal in its notes, and it skips an item
  that GTD already holds.
- **Remove:** Resolve the requested item to its UUID. If several records
  match, show their full titles and short unique ID suffixes. Ask which
  occurrence the user means.
- **Clear:** Select the UUIDs in the complete pending inbox just read. An
  explicit request to clear it authorizes that set. Ask for confirmation
  only when the request did not already authorize clearing.
- **Restore:** Use the explicitly selected deleted UUIDs. A new capture
  with similar wording is not a restoration request.

Keep the captured title exact. If useful, store an unambiguous relative-date
annotation separately in notes. Follow the cloud date rules and retain the
original phrase. Leave ambiguous dates unchanged. A preferred work date is
not a deadline.

## Apply

Capture immediately without a confirmation step. Use a distinct item UUID
for each occurrence. Keep its request and item UUIDs for recovery through
the cloud contract.

Remove or clear with authorized soft-delete batches under the cloud
contract. Select only the record UUIDs gathered above. Captures added after that selection must
survive. Restore only the selected records in an explicit restore batch.
List and count requests perform no writes.

Use the cloud receipt and readback procedure before reporting success.
Resolve uncertain outcomes through that procedure before another write.

## Agent capture

An agent capture is an inbox item that an agent adds when a task that it
was given stops and waits on the user. Add agent captures only when the
user's instructions ask for them, for example the rule that `gtd-setup`
adds to the global `CLAUDE.md` or `AGENTS.md`. The user processes each
agent capture with `gtd-process`.

Add one agent capture for each of these items:

- A decision that only the user can make.
- A finding that needs the user's attention.
- A finished result that the user must review, with or without a linked
  GTD project.

Add no agent capture for these items:

- Any item in a conversation where the user answers turn by turn, such as
  a question, a confirmation, or a result of the current turn. The user
  sees it in the conversation.
- A decision that you made and that is easy to reverse. Put it in the notes
  of the review item.
- An item that GTD already holds: a pending inbox item or an open action
  with the same `Source` link and the same decision, finding, or result.

A subagent, or a child task that another agent started, adds no agent
capture. It reports the items to its parent, and the parent adds them.

Write a one-line title that names the decision or the review and its
source reference, for example `Decide the access rule for agent captures
(#406)`. Write the notes in this form, and leave out the `Options` line
when there is no decision:

```text
Source: <thread, issue, or pull request link>
Context: <what is blocked, finished, or found>
Options: <the choices>
Recommendation: <one choice and its reason>

Proposed next action: <a concrete human action>
Proposed project: <an existing project, a new project outcome, or none>
Proposed priority: <High (1), Medium (5), Low (9), or None (0)>
Proposed deadline: <a date and its evidence, or none>
Proposed effort: <the human effort and its duration label, or unknown>
```

Use the shared planning policy for the proposed values. Propose a deadline
only from evidence of a real deadline. Set only `kind` to `inbox`, `title`,
and `notes`. The other fields keep their defaults, because a proposal is
not a commitment.

Before you save, read the complete pending inbox and the open actions.
Save the agent captures of one turn together, without a confirmation step.
Split them into batches only at the cloud contract's batch limit. Make no
other GTD change: for an agent capture, an agent never changes, completes,
deletes, or restores a record, and it never starts `gtd-setup`.

## Report

For agent captures, end the final message of the turn with a
`## Needs you` list. Give one line for each item: its title and the short
unique ID suffix of the saved record. For an item that was not saved, give
its title and the error, such as a missing GTD binding or connector sign-in.

For capture, show the saved wording. Then show the pending count when a
complete read succeeds. Mention any similar existing item after capture;
similarity does not change the saved records.

For list, show **Inbox (N items)** and a numbered list with full titles.
Distinguish identical titles with short unique ID suffixes. For count,
report the number of pending captures. Say “Inbox is empty” only after a
complete successful read.

For remove, clear, or restore, report the affected count and remaining
pending count when available. State any failed or uncertain result. A
failed count does not undo a confirmed capture or establish an empty inbox.
