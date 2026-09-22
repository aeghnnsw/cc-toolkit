---
name: model-config
version: 2.0.0
description: This skill should be used when the user asks to "change model", "set default model", "switch model", "use 1M context", "enable 1M context window", "change effort level", "set thinking depth", "configure effort", "set auto-compact window", "adjust auto compact", "compact earlier", "change compact threshold", "disable auto compact", "configure autocompact", or wants to modify the model, effort level, or auto-compact settings in Claude Code.
---

Configure the default model, effort level, and auto-compact window in
`~/.claude/settings.json`.

## Background

Claude Code reads these top-level keys from `~/.claude/settings.json`:

| Key | Type | Purpose |
|---|---|---|
| `model` | string | Default model for new sessions |
| `effortLevel` | string | Default effort for models with no saved level |
| `modelSettings` | object | Effort level saved per model (v2.1.251 and later) |
| `ultracode` | boolean | Start sessions at `xhigh` effort with dynamic workflows |
| `autoCompactEnabled` | boolean | Turn automatic compaction off or on |
| `autoCompactWindow` | number | Token count at which automatic compaction runs |

Related environment variables go in the `env` block. Each one overrides the
matching setting.

### Auto-compact uses a token window

The auto-compact window is a token count, not a percentage. Four places set
it. This list shows the precedence, highest first:

1. `CLAUDE_CODE_AUTO_COMPACT_WINDOW` in the environment, set either in the
   shell or in the `env` block. It accepts a plain integer only. A value such
   as `500k` reads as `500` and clamps to the 100,000 minimum.
2. `claude --autocompact <auto|tokens>` at launch. It applies to one launch and
   does not change the saved setting.
3. `autoCompactWindow` in settings. The `/autocompact` command writes this key
   to user settings.
4. The window tuned for the model.

The `/autocompact` command and the `--autocompact` flag accept a window from
100K to 1M tokens in three forms:

- A plain token count, such as `200000`
- A `k` or `M` suffix, such as `500k` or `1M`
- A bare number from 100 to 1000, meaning thousands, so `200` sets 200,000

Claude Code caps the window at the model context window. `/autocompact auto`
returns to the tuned window.

Keep an explicitly set window at 200,000 tokens or more. In the v2.1.275
binary, the check that starts proactive compaction returns false when the
window source is not `auto` and the window is below 200,000 tokens, even though
the documented minimum is 100,000. A session under that floor still compacts
reactively, but it loses the smoother proactive pass. This floor is not
documented; verify it against the installed version before you rely on it.

### Default auto-compact thresholds

Without an auto-compact window, Claude Code compacts when the conversation
reaches the model context limit. These sessions compact earlier:

- Models with a native 1M window, such as Fable 5.1, Fable 5, Sonnet 5, and
  Opus 4.7 and later on the Anthropic API, compact at about 967K tokens
- Sonnet 4.6 and Opus 4.6 without extended context compact at the 200K
  boundary, and so do Opus 4.8 and Opus 5 when they run with a 200K window
- With `CLAUDE_CODE_DISABLE_1M_CONTEXT=1`, models with a native 1M window
  compact at the 200K boundary
- Cloud sessions compact as the conversation approaches the model limit
- Sessions on a model ID Claude Code does not recognize compact at the window
  Claude Code assumes for that ID

### The percentage override is limited

`CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` sets a percentage (1-100) of the auto-compact
window at which compaction triggers. It has two limits:

- It cannot raise the threshold. Values above the default percentage are
  ignored.
- It applies only in sessions that compact **before** the model context limit.

A session that compacts at the model context limit ignores the variable
completely. This is why a configured percentage can appear to have no effect.

Users also report that the variable has no effect when it is set in the `env`
block of `settings.json`, and works only when it is exported in the shell
before launch. See
[anthropics/claude-code#63186](https://github.com/anthropics/claude-code/issues/63186),
closed as not planned. GUI-launched surfaces, such as the desktop app and the
IDE extensions, do not read shell profiles, so the export workaround does not
help there.

Treat the variable as unreliable. Use `autoCompactWindow` instead, which
applies to every session and every surface.

If the user has `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` set, offer to replace it with
an equivalent `autoCompactWindow` value. Compute the token count from the
model context window, then round to a clean number.

### Turn auto-compact off

- `"autoCompactEnabled": false` in settings, or `DISABLE_AUTO_COMPACT=1` in the
  `env` block, turns off automatic compaction. The manual `/compact` command
  keeps working. Whichever of the two turns it off, the other cannot turn it
  back on.
- `DISABLE_COMPACT=1` turns off all compaction, including `/compact`.

### Models and effort levels

| Model | Effort levels | 1M context |
|---|---|---|
| `claude-fable-5-1`, `claude-fable-5` | low, medium, high, xhigh, max | native |
| `claude-opus-5` | low, medium, high, xhigh, max | native on the Anthropic API |
| `claude-opus-4-8`, `claude-opus-4-7` | low, medium, high, xhigh, max | native on the Anthropic API |
| `claude-sonnet-5` | low, medium, high, xhigh, max | native, always on |
| `claude-opus-4-6`, `claude-sonnet-4-6` | low, medium, high, max | `[1m]` variant only |
| `claude-sonnet-4-5`, `claude-haiku-4-5` | not supported | no |

The default effort level is `high` on every model that supports effort, except
Opus 4.7, which defaults to `xhigh`. If the active model does not support the
level you set, Claude Code falls back to the highest supported level at or
below it.

`max` is not accepted in `effortLevel` or `modelSettings`. Set
`CLAUDE_CODE_EFFORT_LEVEL=max` in the `env` block to keep `max` across
sessions. Set any other way, `max` applies to the current session only.

`ultracode` is a Claude Code setting, not a model effort level. `"ultracode":
true` runs sessions at `xhigh` effort and lets Claude plan dynamic workflows.
It takes precedence over `effortLevel` and `modelSettings`.

### Where effort levels are saved

Since v2.1.251, `/effort low|medium|high|xhigh` saves the level under
`modelSettings` for the active model, not under the top-level `effortLevel`:

```json
{
  "modelSettings": {
    "claude-opus-5": { "effortLevel": "medium" }
  }
}
```

Within one settings file, a model entry in `modelSettings` takes precedence
over the top-level `effortLevel`. Use `effortLevel` as the default for models
that have no saved entry.

### 1M context window

Fable 5.1, Fable 5, Sonnet 5, and Opus 4.7 and later run with the 1M window on
every plan on the Anthropic API. Do not append `[1m]` to these models.

Opus 4.6 and Sonnet 4.6 reach 1M only through the `[1m]` suffix, for example
`claude-opus-4-6[1m]` or the `opus[1m]` alias. Access depends on the plan:
Opus 4.6 with 1M context is included on Max, Team, and Enterprise; Sonnet 4.6
with 1M context requires usage credits on every subscription plan.

`CLAUDE_CODE_DISABLE_1M_CONTEXT=1` turns off 1M support and holds models with a
native 1M window to a 200K window.

## Step 1: Fetch Current Model Information

Use **WebFetch** to read `https://code.claude.com/docs/en/model-config` and
extract the current model list, effort levels, 1M context support, and
auto-compact defaults. Use
`https://code.claude.com/docs/en/settings-reference` for setting types and
ranges, and `https://code.claude.com/docs/en/env-vars` for environment
variables.

If WebFetch fails, fall back to the tables in the Background section and inform
the user: "Could not fetch latest model info; using built-in defaults."

## Step 2: Read Current Settings

Read `~/.claude/settings.json`.

## Step 3: Display Current Values

Report each value, or mark it as not set:

- **Model**: the `model` key, or "not set (account default)"
- **Effort level**: the entry for the active model in `modelSettings`, then the
  `effortLevel` key, then "not set (model default)". Report
  `env.CLAUDE_CODE_EFFORT_LEVEL` and `ultracode` when either is present,
  because both override the settings.
- **Auto-compact**: `autoCompactEnabled`, `autoCompactWindow`, and any of
  `env.CLAUDE_CODE_AUTO_COMPACT_WINDOW`,
  `env.CLAUDE_AUTOCOMPACT_PCT_OVERRIDE`, `env.DISABLE_AUTO_COMPACT`, and
  `env.DISABLE_COMPACT`. Name which one wins.

If `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` is set, warn the user that it applies only
in sessions that compact before the model context limit.

## Step 4: Ask Which Settings to Change

Use **AskUserQuestion** to ask which settings to change: model, effort,
auto-compact, or several. Proceed through the applicable steps in order and
skip the rest.

## Step 5: Update Model (if selected)

### Step 5a: Select Base Model

Use **AskUserQuestion** to present the models from Step 1, or these when the
fetch failed:

```
1. claude-fable-5-1
2. claude-opus-5
3. claude-sonnet-5
4. claude-haiku-4-5
```

Include in the question text: "Or type a custom model ID or alias directly."

Accept a number, a matching model name, or any other string as a custom model
ID. Ask again if the input is empty or unrecognized.

### Step 5b: Enable 1M Context Window

Check the selected model against the 1M context table:

- Native 1M model: inform the user that the model already runs at 1M on the
  Anthropic API and do not append `[1m]`.
- Opus 4.6 or Sonnet 4.6: ask whether to enable 1M context. If yes, append
  `[1m]`. State the plan requirement for that model.
- No 1M support: skip this sub-step.

For a custom model ID, tell the user that `[1m]` works on any model that
supports the variant.

### Step 5c: Validate Selection

If the final model ID equals the current setting, report "Already set to that
model. No change needed." and skip the write for this field.

Record the chosen ID as the **target model**. Strip any `[1m]` suffix before
you validate effort levels in Step 6.

## Step 6: Update Effort Level (if selected)

Determine the reference model: the target model from Step 5, otherwise the
current `model` value. Strip any `[1m]` suffix.

If the reference model does not support effort, such as Haiku 4.5, inform the
user and skip this step. Offer to remove a stale `effortLevel` key or
`modelSettings` entry.

Use **AskUserQuestion** to present the valid levels for the reference model
from the table in Background. Validate the answer against that list and
normalize it to lowercase.

Then ask about scope:

- **This model only**: write `modelSettings.<model>.effortLevel`. This matches
  what `/effort` writes.
- **All models without a saved level**: write the top-level `effortLevel`.

**If the user selects `max`:** explain that `effortLevel` and `modelSettings`
do not accept `max`, and that `CLAUDE_CODE_EFFORT_LEVEL=max` in the `env` block
is the documented way to keep it across sessions. Ask whether to set the
environment variable or to skip. If the user sets it, remove any conflicting
`effortLevel` key or `modelSettings` entry for that model.

## Step 7: Update Auto-Compact (if selected)

### Step 7a: Choose the Change

Use **AskUserQuestion** to ask what to change:

1. Set the auto-compact window
2. Return to the window tuned for the model
3. Turn auto-compact off
4. Turn auto-compact on

### Step 7b: Set the Window

Ask for a token count. State the model context window and the current
threshold so the user can judge the value. Accept `200000`, `500k`, `1M`, or a
bare number from 100 to 1000 meaning thousands, and convert the answer to a
plain integer.

Validate the integer:

- Below `100000`: inform the user that the minimum is 100,000 and ask again.
- Between `100000` and `199999`: warn the user that proactive compaction
  appears to switch off below 200,000 tokens, and recommend `200000` or more.
  Confirm the value before you write it.
- Above `1000000`: inform the user that the maximum is 1,000,000 and ask again.
- Above the model context window: inform the user that Claude Code caps the
  window at the model context window, and confirm the value.
- Equal to the current setting: report "Already set. No change needed." and
  skip the write.

Write the integer to the top-level `autoCompactWindow` key. Tell the user that
`/autocompact <value>` does the same thing from inside a session.

If `env.CLAUDE_CODE_AUTO_COMPACT_WINDOW` is set, warn the user that it
overrides the setting, and offer to remove it.

If `env.CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` is set, offer to remove it, because
`autoCompactWindow` replaces it and applies to every session.

### Step 7c: Return to the Tuned Window

Remove the `autoCompactWindow` key, and
`env.CLAUDE_CODE_AUTO_COMPACT_WINDOW` when present. This matches
`/autocompact auto`.

### Step 7d: Turn Auto-Compact Off or On

Ask which scope the user wants:

- **Automatic compaction only**: set `"autoCompactEnabled": false`. The manual
  `/compact` command keeps working. Warn the user that a session which reaches
  the context limit stops with a context-limit error instead of compacting.
- **All compaction**: add `"DISABLE_COMPACT": "1"` to the `env` block. This
  also disables `/compact`.

To turn auto-compact back on, set `"autoCompactEnabled": true` and remove
`DISABLE_AUTO_COMPACT` and `DISABLE_COMPACT` from the `env` block. Tell the
user that `DISABLE_AUTO_COMPACT` overrides `autoCompactEnabled`, so leaving it
in place keeps auto-compact off.

## Step 8: Write All Changes

Read `~/.claude/settings.json` again, then apply every collected change in one
surgical update:

- If the file does not exist, use **Write** to create it with only the keys
  being set.
- If the file exists, use **Edit** for each key.
- Add or replace only the target keys. Preserve every other key in the file and
  in the `env` block.
- If no `env` block exists and an environment variable is needed, add one.

`model` and `effortLevel` are JSON strings. `autoCompactWindow` is a JSON
number. `autoCompactEnabled` and `ultracode` are JSON booleans. Every value in
the `env` block is a string.

Example result:

```json
{
  "model": "claude-fable-5-1",
  "effortLevel": "high",
  "modelSettings": {
    "claude-opus-5": { "effortLevel": "medium" }
  },
  "autoCompactWindow": 500000,
  "env": {
    "EXISTING_KEY": "preserved"
  }
}
```

Write only the keys the user selected that differ from the current value.

## Step 9: Confirm

Report the new value of each changed setting. Then inform the user: "Restart
Claude Code for changes to take effect."

`/autocompact` and `/effort` apply inside a running session. Mention them when
the user wants the change now.

If nothing changed, confirm: "No changes were made."

## Uninstall

Remove these keys from `~/.claude/settings.json` to return to defaults:

- `model`, to restore the account default model
- `effortLevel` and `modelSettings`, to restore the model default effort
- `ultracode`, to turn off ultracode
- `autoCompactWindow`, to restore the tuned auto-compact window
- `autoCompactEnabled`, to restore automatic compaction
- From the `env` block: `CLAUDE_CODE_AUTO_COMPACT_WINDOW`,
  `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE`, `DISABLE_AUTO_COMPACT`, `DISABLE_COMPACT`,
  `CLAUDE_CODE_EFFORT_LEVEL`, and `CLAUDE_CODE_DISABLE_1M_CONTEXT`

If the `env` block becomes empty, remove it. Preserve all other keys.
