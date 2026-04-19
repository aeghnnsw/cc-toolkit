---
name: model-config
version: 1.0.0
description: This skill should be used when the user asks to "change model", "set default model", "switch model", "use 1M context", "enable 1M context window", "change effort level", "set thinking depth", "configure effort", "adjust auto compact", "change compact percentage", "set auto compact threshold", "configure auto compaction", "configure model settings", or wants to modify the model, effortLevel, or CLAUDE_AUTOCOMPACT_PCT_OVERRIDE settings in Claude Code.
---

Configure the default model, thinking effort level, and auto-compact threshold in `~/.claude/settings.json`.

## Background

Three settings in `~/.claude/settings.json` control core Claude Code behavior:

- **model** (top-level key) — the default model ID used for all sessions
- **effortLevel** (top-level key) — thinking depth for models that support extended thinking
- **CLAUDE_AUTOCOMPACT_PCT_OVERRIDE** (inside the `env` block, as a string) — the percentage of context capacity at which Claude Code automatically compacts conversation history

Supported models and their valid effort levels:

| Model | Valid effort levels | Default effort | 1M context |
|---|---|---|---|
| claude-opus-4-7 | low, medium, high, xhigh, max | xhigh | yes |
| claude-opus-4-6 | low, medium, high, max | high | yes |
| claude-sonnet-4-6 | low, medium, high, max | high | yes |
| claude-haiku-4-5-20251001 | not supported | — | no |

### 1M Context Window

Opus 4.7, Opus 4.6, and Sonnet 4.6 support a 1 million token context window. To enable it, append `[1m]` to either a model alias or a full model name:

- Aliases: `opus[1m]`, `sonnet[1m]`
- Full names: `claude-opus-4-7[1m]`, `claude-opus-4-6[1m]`, `claude-sonnet-4-6[1m]`

Claude Code strips the `[1m]` suffix before sending the model ID to the API — it only controls the local context window behavior. On Max, Team, and Enterprise plans, Opus is automatically upgraded to 1M context even without the suffix, but using it makes the setting explicit.

For auto-compact: the default behavior (no setting) triggers compaction at ~95% context capacity. The valid range is 1–83; values above 83 are silently capped internally.

## Step 1: Fetch Current Model Information

Use **WebFetch** to read `https://code.claude.com/docs/en/model-config` and extract the current list of supported models, their effort levels, and 1M context support. Parse the page content to identify:

- Available model IDs
- Which models support extended thinking and their valid effort levels
- Which models support the `[1m]` suffix for 1M context window

If WebFetch fails or the page format is unrecognizable, fall back to the hardcoded table in the Background section above. Inform the user: "Could not fetch latest model info; using built-in defaults."

## Step 2: Read Current Settings

Read `~/.claude/settings.json` to check the current configuration.

## Step 3: Display Current Values

Extract and display all three current values:

- **Model**: the value of the top-level `model` key, or "not set (Claude Code default)" if absent
- **Effort level**: the value of the top-level `effortLevel` key, or "not set (model default)" if absent
- **Auto-compact threshold**: the value of `env.CLAUDE_AUTOCOMPACT_PCT_OVERRIDE`, or "not set (default: ~95%)" if absent

## Step 4: Ask Which Settings to Change

Use **AskUserQuestion** to ask:

"Which setting(s) would you like to change? (model / effort / compact — or name multiple)"

Parse the response and collect a list of the selected settings. Proceed through the applicable steps below in order, skipping any not selected.

## Step 5: Update Model (if selected)

### Step 5a: Select Base Model

Use **AskUserQuestion** to present the following choices:

```
1. claude-opus-4-7
2. claude-opus-4-6
3. claude-sonnet-4-6
4. claude-haiku-4-5-20251001
```

Include in the question text: "Or type a custom model ID directly."

Parse the user's response:

- If 1–4, use the corresponding model ID.
- If the user enters a model name matching one of options 1–4, use the corresponding model ID.
- If the user enters a different model ID string, use that value exactly as a custom model ID.
- If the input is empty or unrecognized, inform the user and ask again.

### Step 5b: Enable 1M Context Window

If the selected base model supports 1M context (check the model table in Background, or the data fetched in Step 1), use **AskUserQuestion** to ask:

"Enable 1M context window? (yes / no)"

- If yes, append `[1m]` to the model ID (e.g., `claude-opus-4-6` → `claude-opus-4-6[1m]`).
- If no, use the base model ID as-is.
- Inform the user: "On Max, Team, and Enterprise plans, Opus models auto-upgrade to 1M context even without the suffix."

If the selected model does not support 1M context (e.g., Haiku), skip this sub-step.

For custom model IDs (option 5), inform the user they can manually append `[1m]` to any supported model for 1M context.

### Step 5c: Validate Selection

- If the final model ID (with or without `[1m]`) equals the current setting, note "Already set to that model. No change needed." and skip the write for this field.

Record the chosen model ID as the **target model** for Step 6. When determining the base model for effort level validation in Step 6, strip the `[1m]` suffix (e.g., `claude-opus-4-6[1m]` → validate against `claude-opus-4-6`).

## Step 6: Update Effort Level (if selected)

Determine which model to validate against:

- If the user changed the model in Step 5, use the newly selected model as the reference. Strip the `[1m]` suffix before validation (e.g., `claude-opus-4-6[1m]` → validate against `claude-opus-4-6`).
- Otherwise, use the current `model` value from settings.json (also stripping any `[1m]` suffix). If no `model` key exists, treat as unknown.

If the reference model is `claude-haiku-4-5-20251001`, inform the user: "Haiku 4.5 does not support effortLevel. Skipping effort configuration." If an `effortLevel` key currently exists in settings.json, ask the user if they want to remove it. Proceed to Step 7.

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

If the user chooses the env block workaround, write `CLAUDE_CODE_EFFORT_LEVEL` with value `"max"` to the `env` block in Step 8 instead of writing the `effortLevel` key. If an `effortLevel` key currently exists, remove it to avoid conflicts. If the user chooses to skip, do not write the `effortLevel` key.

## Step 7: Update Auto-Compact Threshold (if selected)

Use **AskUserQuestion** to ask:

"Enter desired auto-compact percentage (1–83). Recommended: 60–75 for most work. Values above 83 are capped internally."

Parse the user's response as an integer:

- If not a valid integer, inform the user and ask again.
- If the value is less than 1, inform the user the minimum is 1 and ask again.
- If the value is greater than 83, inform the user: "The maximum effective value is 83 (Claude Code caps anything higher internally). Setting to 83." Use 83.
- If the value equals the current setting, note "Already set to N%. No change needed." and skip the write for this field.

## Step 8: Write All Changes

Read `~/.claude/settings.json` again (to get the latest state), then apply all collected changes in a single surgical update:

- If `~/.claude/settings.json` does not exist, use the **Write** tool to create it with only the keys being set.
- If the file exists, use the **Edit** tool for surgical updates.
- For the `model` key: add or replace the top-level `model` key. Preserve all other top-level keys.
- For the `effortLevel` key: add or replace the top-level `effortLevel` key. Preserve all other top-level keys. If the user chose the `max` env block workaround in Step 6, remove the `effortLevel` key instead.
- For `CLAUDE_CODE_EFFORT_LEVEL` (max workaround): if the user chose the env block workaround in Step 6, add `"CLAUDE_CODE_EFFORT_LEVEL": "max"` to the `env` block.
- For `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE`: if no `env` block exists, add one. Add or replace only the `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` key within `env`. Preserve all other keys in both the `env` block and the rest of the file.

All values are JSON strings: `model`, `effortLevel`, and env var values must be quoted.

Example partial result after setting all three:

```json
{
  "model": "claude-opus-4-7[1m]",
  "effortLevel": "xhigh",
  "env": {
    "EXISTING_KEY": "preserved",
    "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "50"
  }
}
```

Only write keys that the user selected and that differ from the current value.

## Step 9: Confirm

For each setting that was changed, report the new value. Then inform the user: "Restart Claude Code for changes to take effect."

If nothing was changed, confirm: "No changes were made."

## Uninstall

To revert to defaults, remove the relevant keys from `~/.claude/settings.json`:

- Remove the top-level `model` key to restore Claude Code's default model selection.
- Remove the top-level `effortLevel` key to restore the model's default thinking depth.
- Remove the `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` key from the `env` block to restore the ~95% default compaction threshold.
- Remove the `CLAUDE_CODE_EFFORT_LEVEL` key from the `env` block if present (set via the `max` effort workaround).
- If the `env` block becomes empty after removal, remove the `env` block as well.

Preserve all other keys in the file.
