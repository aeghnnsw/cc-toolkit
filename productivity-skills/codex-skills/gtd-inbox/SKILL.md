---
name: gtd-inbox
description: "Use when capturing thoughts or tasks into the GTD inbox, or when listing, counting, removing, clearing, or restoring inbox items."
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
An empty invocation lists pending captures. Ask only when the intended
operation or record is unclear. Keep the question concise.

For a capture, validate the route and write without first organizing the
inbox. For list or count, read the complete pending inbox. For removal or
clear, read the pending records and retain the selected UUIDs. For explicit
restoration, retrieve the requested deleted records through the cloud
contract.

## Select

- **Capture:** Keep each supplied occurrence, including identical text, as
  a distinct record. Do not merge similar thoughts or broaden their scope.
  Do not clarify or plan the task during capture.
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

## Report

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
