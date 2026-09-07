---
name: gtd-inbox
description: Use when capturing thoughts or tasks into the GTD inbox, or when listing, counting, removing, or clearing inbox items.
---

Manage the user's GTD inbox based on their request.

## Step 1: Read Inbox File

1. Read `~/.gtd/inbox.md` (shared with the Claude Code version of this skill — keep this exact path)
2. If file or directory does not exist:
   - Create directory: `mkdir -p ~/.gtd`
   - Create file with format:
     ```markdown
     # Inbox

     ```

## Step 2: Interpret Instructions

Determine the user's intent from their message:

| Intent | Example phrases |
|--------|-----------------|
| Add item | "add buy milk", "remember to call John", "capture: review docs" |
| List items | "list", "show", "what's in my inbox", "" (empty = list) |
| Remove item | "remove buy milk", "delete the call item", "done with groceries" |
| Count | "count", "how many items" |
| Clear all | "clear", "empty inbox" |

If unclear, ask the user to clarify.

## Step 3: Execute Action

**Adding Items:**
1. Append the item without a confirmation step. Preserve the user's wording and scope. Do not clarify or organize the task during capture.
2. If useful, append a resolved date to an unambiguous relative date. Read the current local date first:
   ```bash
   date "+%Y-%m-%d %A %Z"
   ```
   Keep the original phrase. For example, on 2026-09-07, store "buy groceries tomorrow (2026-09-08)". Preserve ranges as ranges. Leave ambiguous phrases unchanged. Do not turn a preferred work date into a deadline or add a time.
3. Report the saved item and pending count. If a similar item exists, mention it after capture. Do not block capture or merge items because they seem similar.

**Listing Items:**
1. Display numbered list
2. If empty: "Inbox is empty"
3. Format: "# Inbox (N items)" followed by numbered items

**Removing Items:**
1. Find item matching description semantically
2. If multiple matches or unclear, ask the user to confirm which
3. Edit the file to remove the line
4. Report: "Removed '[item]'. (N items remaining)"

**Counting:**
Report: "N items pending"

**Clearing:**
1. If the user has not already explicitly authorized clearing all items, ask: "Clear all N items from inbox?"
2. If confirmed, write empty inbox format
3. Report: "Inbox cleared"

## Step 4: Save Changes

- Rewrite the whole file when creating it or clearing all items
- Edit only the affected lines when adding or removing items

## Guidelines

Follow GTD inbox principles:
- Capture everything without judgment
- Keep items atomic (single thought/task each)
- The inbox is for capture, not organization

Handle errors gracefully:
- If file malformed, parse what's readable and warn user
- If item not found, ask the user to clarify
- Honor explicit authorization. Do not ask again for the same operation.
