---
name: statusline-setup
version: 1.1.0
description: This skill should be used when the user asks to "set up statusline", "configure statusline", "install statusline", "set up status bar", or wants to configure the Claude Code statusline with model info, git status, context/rate-limit bars, and token cost tracking.
---

Install and configure a custom Claude Code statusline that shows model info, git status, context usage, rate limits, and token costs.

## What It Does

The statusline displays 3 lines:

1. **Model[·Effort] + Project + Git** — `[Opus 4.7 · high] │ my-project git:(main*)` (effort level shown when the model supports it)
2. **Usage bars** — Context, 5-hour rate limit, and 7-day rate limit with color-coded progress bars and reset countdowns
3. **Token breakdown + cost** — Fresh input, cache-write, cache-read, output tokens (non-overlapping components of the current context window) with session cost from Claude Code

## Prerequisites

- `jq` must be installed (`brew install jq` on macOS)

## Setup Steps

### Step 1: Copy the statusline script

Copy the bundled script to the Claude Code config directory:

```bash
cp "${CLAUDE_PLUGIN_ROOT}/skills/statusline-setup/scripts/statusline-command.sh" ~/.claude/statusline-command.sh
chmod +x ~/.claude/statusline-command.sh
```

### Step 2: Configure settings.json

Read `~/.claude/settings.json`, then set the `statusLine` field to the following value:

```json
{
  "type": "command",
  "command": "bash ~/.claude/statusline-command.sh"
}
```

- If `~/.claude/settings.json` does not exist, create it: `{ "statusLine": <value above> }`.
- If the file exists and a `statusLine` field already exists, replace its value. If not, add it.
- Preserve all other top-level keys in the file.

### Step 3: Verify

Inform the user that the statusline is configured. Changes take effect on the next Claude Code session (restart required).

## Updating

To install changes from a new plugin version, re-run Step 1 above.

## Uninstall

To remove the statusline, delete the `statusLine` field from `~/.claude/settings.json` and remove `~/.claude/statusline-command.sh`.
