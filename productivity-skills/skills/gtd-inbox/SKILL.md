---
name: gtd-inbox
version: 1.0.0
description: This skill should be used when the user asks to "add to inbox", "capture a thought", "show inbox", "list inbox items", "clear inbox", "remove from inbox", or wants to manage their GTD inbox for capturing thoughts and tasks.
---

Manage the user's GTD inbox based on their request.

## Step 1: Read Inbox File

1. Read `~/.claude/productivity-skills/inbox.md`
2. If file or directory does not exist:
   - Create directory: `mkdir -p ~/.claude/productivity-skills`
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

If unclear, use **AskUserQuestion** to clarify.

## Step 3: Execute Action

**Adding Items:**
1. Check if a semantically similar item already exists
2. If similar found, use **AskUserQuestion**: "Similar item exists: '[item]'. Add anyway?" with options "Yes, add it" / "No, skip"
3. **Get current date** if item contains time references:
   ```bash
   date "+%Y-%m-%d %A"
   ```
   This returns the date and day of week (e.g., "2026-01-13 Monday") for accurate time calculation.
4. **Convert relative time references to explicit dates** before adding:
   - "today" → "(YYYY-MM-DD)"
   - "tomorrow" → "(YYYY-MM-DD)"
   - "this Monday" → "(Mon YYYY-MM-DD)"
   - "next week" → "(week of YYYY-MM-DD)"
   - "end of week" → "(by Fri YYYY-MM-DD)"
   - "end of month" → "(by YYYY-MM-DD)"
   - If no time reference, store item as-is

   Examples:
   - "call John this Monday" → "call John (Mon 2026-01-20)"
   - "finish report by end of week" → "finish report (by Fri 2026-01-17)"
   - "buy groceries tomorrow" → "buy groceries (2026-01-14)"
   - "review docs" → "review docs" (no change)
5. If confirmed or no duplicate, append the converted item to list
6. Report: "Added '[converted item]' to inbox (N items pending)"

**Listing Items:**
1. Display numbered list
2. If empty: "Inbox is empty"
3. Format: "# Inbox (N items)" followed by numbered items

**Removing Items:**
1. Find item matching description semantically
2. If multiple matches or unclear, use **AskUserQuestion** to confirm which
3. Use Edit tool to remove the line
4. Report: "Removed '[item]'. (N items remaining)"

**Counting:**
Report: "N items pending"

**Clearing:**
1. Use **AskUserQuestion**: "Clear all N items from inbox?"
2. If confirmed, write empty inbox format
3. Report: "Inbox cleared"

## Step 4: Save Changes

- Use **Write** tool for: creating new file, clearing all items
- Use **Edit** tool for: adding items, removing items

## Guidelines

Follow GTD inbox principles:
- Capture everything without judgment
- Keep items atomic (single thought/task each)
- The inbox is for capture, not organization

Handle errors gracefully:
- If file malformed, parse what's readable and warn user
- If item not found, use AskUserQuestion to clarify
- Always confirm destructive actions (clear all)
