---
name: model-config
version: 1.0.0
description: This skill should be used when the user asks to "change model", "set default model", "switch model", "change effort level", "set thinking depth", "configure effort", "adjust auto compact", "change compact percentage", "set auto compact threshold", "configure auto compaction", "configure model settings", or wants to modify the model, effortLevel, or CLAUDE_AUTOCOMPACT_PCT_OVERRIDE settings in Claude Code.
---

Configure the default model, thinking effort level, and auto-compact threshold in `~/.claude/settings.json`.

## Background

Three settings in `~/.claude/settings.json` control core Claude Code behavior:

- **model** (top-level key) — the default model ID used for all sessions
- **effortLevel** (top-level key) — thinking depth for models that support extended thinking
- **CLAUDE_AUTOCOMPACT_PCT_OVERRIDE** (inside the `env` block, as a string) — the percentage of context capacity at which Claude Code automatically compacts conversation history

Supported models and their valid effort levels:

| Model | Valid effort levels | Default effort |
|---|---|---|
| claude-opus-4-7 | low, medium, high, xhigh, max | xhigh |
| claude-opus-4-6 | low, medium, high, max | high |
| claude-sonnet-4-6 | low, medium, high, max | high |
| claude-haiku-4-5-20251001 | not supported | — |

For auto-compact: the default behavior (no setting) triggers compaction at ~95% context capacity. The valid range is 1–83; values above 83 are silently capped internally.

## Step 1: Read Current Settings

Read `~/.claude/settings.json` to check the current configuration.

## Step 2: Display Current Values

Extract and display all three current values:

- **Model**: the value of the top-level `model` key, or "not set (Claude Code default)" if absent
- **Effort level**: the value of the top-level `effortLevel` key, or "not set (model default)" if absent
- **Auto-compact threshold**: the value of `env.CLAUDE_AUTOCOMPACT_PCT_OVERRIDE`, or "not set (default: ~95%)" if absent

## Step 3: Ask Which Settings to Change

Use **AskUserQuestion** to ask:

"Which setting(s) would you like to change? (model / effort / compact — or name multiple)"

Parse the response and collect a list of the selected settings. Proceed through the applicable steps below in order, skipping any not selected.

## Step 4: Update Model (if selected)

Use **AskUserQuestion** to present the following numbered choices:

```
1. claude-opus-4-7
2. claude-opus-4-6
3. claude-sonnet-4-6
4. claude-haiku-4-5-20251001
5. Enter a custom model ID
```

Parse the user's response:

- If 1–4, use the corresponding model ID.
- If 5, use **AskUserQuestion** to ask for the custom model ID (e.g., `claude-sonnet-4-6`) and use that value exactly.
- If the input is empty or unrecognized, inform the user and ask again.
- If the selected model equals the current setting, note "Already set to that model. No change needed." and skip the write for this field.

Record the chosen model ID as the **target model** for Step 5.

## Step 5: Update Effort Level (if selected)

Determine which model to validate against:

- If the user changed the model in Step 4, use the newly selected model as the reference.
- Otherwise, use the current `model` value from settings.json. If no `model` key exists, treat as unknown.

If the reference model is `claude-haiku-4-5-20251001`, inform the user: "Haiku 4.5 does not support effortLevel. Skipping effort configuration." If an `effortLevel` key currently exists in settings.json, ask the user if they want to remove it. Proceed to Step 6.

Use **AskUserQuestion** to present the valid effort levels for the reference model:

- For `claude-opus-4-7`: `low`, `medium`, `high`, `xhigh`, `max` (default: xhigh)
- For `claude-opus-4-6` or `claude-sonnet-4-6`: `low`, `medium`, `high`, `max` (default: high)
- For unknown or custom model: `low`, `medium`, `high`, `xhigh`, `max` — note that validity depends on the model

Parse the response:

- If the value is not in the valid list for the reference model, inform the user of the valid options and ask again.
- If the value equals the current setting, note "Already set to that level. No change needed." and skip the write for this field.
- Normalize the value to lowercase before writing.

**Known bug with `max`:** If the user selects `max`, warn them:

> "Note: `max` effort has a known bug where it does not persist correctly in settings.json. Preferred workaround: add `"CLAUDE_CODE_EFFORT_LEVEL": "max"` to the `env` block in settings.json. Alternatively, add `export CLAUDE_CODE_EFFORT_LEVEL=max` to your shell profile. Would you like to set it via the env block, or skip?"

If the user chooses the env block workaround, write `CLAUDE_CODE_EFFORT_LEVEL` with value `"max"` to the `env` block in Step 7 instead of writing the `effortLevel` key. If the user chooses to skip, do not write the `effortLevel` key.

## Step 6: Update Auto-Compact Threshold (if selected)

Use **AskUserQuestion** to ask:

"Enter desired auto-compact percentage (1–83). Recommended: 60–75 for most work. Values above 83 are capped internally."

Parse the user's response as an integer:

- If not a valid integer, inform the user and ask again.
- If the value is less than 1, inform the user the minimum is 1 and ask again.
- If the value is greater than 83, inform the user: "The maximum effective value is 83 (Claude Code caps anything higher internally). Setting to 83." Use 83.
- If the value equals the current setting, note "Already set to N%. No change needed." and skip the write for this field.

## Step 7: Write All Changes

Read `~/.claude/settings.json` again (to get the latest state), then apply all collected changes in a single surgical update:

- If `~/.claude/settings.json` does not exist, use the **Write** tool to create it with only the keys being set.
- If the file exists, use the **Edit** tool for surgical updates.
- For the `model` key: add or replace the top-level `model` key. Preserve all other top-level keys.
- For the `effortLevel` key: add or replace the top-level `effortLevel` key. Preserve all other top-level keys.
- For `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE`: if no `env` block exists, add one. Add or replace only the `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` key within `env`. Preserve all other keys in both the `env` block and the rest of the file.

All values are JSON strings: `model`, `effortLevel`, and env var values must be quoted.

Example partial result after setting all three:

```json
{
  "model": "claude-opus-4-7",
  "effortLevel": "xhigh",
  "env": {
    "EXISTING_KEY": "preserved",
    "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "50"
  }
}
```

Only write keys that the user selected and that differ from the current value.

## Step 8: Confirm

For each setting that was changed, report the new value. Then inform the user: "Restart Claude Code for changes to take effect."

If nothing was changed, confirm: "No changes were made."

## Uninstall

To revert to defaults, remove the relevant keys from `~/.claude/settings.json`:

- Remove the top-level `model` key to restore Claude Code's default model selection.
- Remove the top-level `effortLevel` key to restore the model's default thinking depth.
- Remove the `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` key from the `env` block to restore the ~95% default compaction threshold. If the `env` block becomes empty after removal, remove the `env` block as well.

Preserve all other keys in the file.
