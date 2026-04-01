---
name: compact-percentage
version: 1.0.0
description: This skill should be used when the user asks to "adjust auto compact", "change compact percentage", "set auto compact threshold", "configure auto compaction", "change context compaction", or wants to modify the CLAUDE_AUTOCOMPACT_PCT_OVERRIDE setting in Claude Code.
---

Adjust the auto-compact percentage threshold that controls when Claude Code automatically compresses conversation context.

## Background

Claude Code automatically compacts (summarizes) conversation history when context usage reaches a threshold. The `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` environment variable controls this threshold as a percentage of context capacity. Lower values trigger compaction earlier, preserving more room but summarizing sooner. Values above 83 are silently capped due to an internal response-token buffer.

- **Default behavior**: Compaction triggers at ~95% context capacity
- **Valid range**: 1–83 (values above 83 are capped internally)
- **Recommended**: 60–75 for most development work

## Step 1: Read Current Settings

Read `~/.claude/settings.json` to check the current configuration.

## Step 2: Display Current Value

Extract the current `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` value from the `env` block in settings.json.

- If the key exists, display: "Current auto-compact threshold: **N%**"
- If the key does not exist or `env` block is absent, display: "Auto-compact threshold is **not set** (default: ~95%)"

## Step 3: Ask for New Value

Use **AskUserQuestion** to ask:

"Enter desired auto-compact percentage (1–83). Lower values compact earlier, preserving more context headroom. Recommended: 60–75 for most work."

## Step 4: Validate Input

Parse the user's response as an integer.

- If not a valid integer, inform the user and ask again.
- If the value is less than 1, inform the user the minimum is 1 and ask again.
- If the value is greater than 83, inform the user: "The maximum effective value is 83 (Claude Code caps anything higher internally). Setting to 83." Use 83.
- If the value equals the current setting, inform the user: "Already set to N%. No changes made." and exit.

## Step 5: Update Settings

Read `~/.claude/settings.json` again (to get the latest state), then use the **Edit** tool to perform a surgical update:

- If `~/.claude/settings.json` does not exist, create it with `{ "env": { "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "N" } }`.
- If the file exists but has no `env` block, add an `env` key. Preserve all other top-level keys.
- If an `env` block exists, add or replace only the `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` key within it. Preserve all other keys in both the `env` block and the rest of the file.

The value must be a **string** (environment variables are strings). Example partial excerpt:

```json
"env": {
  "EXISTING_KEY": "preserved",
  "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "75"
}
```

## Step 6: Confirm

Inform the user: "Auto-compact threshold set to **N%**. Restart Claude Code for the change to take effect."
