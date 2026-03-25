---
name: statusline-setup
version: 1.1.0
description: This skill should be used when the user asks to "set up statusline", "configure statusline", "install statusline", "set up status bar", or wants to configure the Claude Code statusline with model info, git status, context/rate-limit bars, and token cost tracking.
---

Install and configure a custom Claude Code statusline that shows model info, git status, context usage, rate limits, and token costs.

## What It Does

The statusline displays 3 lines:

1. **Model + Project + Git** — `[Opus 4.6] │ my-project git:(main*)`
2. **Usage bars** — Context, 5-hour rate limit, and 7-day rate limit with color-coded progress bars and reset countdowns
3. **Token breakdown + cost** — Input, cache-write, cache-read, output tokens with session cost from Claude Code

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

Read `~/.claude/settings.json`, then set the `statusLine` field:

```json
{
  "statusLine": {
    "type": "command",
    "command": "bash ~/.claude/statusline-command.sh"
  }
}
```

Use the Edit tool to update `~/.claude/settings.json`. If a `statusLine` field already exists, replace it. If not, add it.

### Step 3: Verify

Inform the user that the statusline is configured. Changes take effect on the next Claude Code session (restart required).

## Uninstall

To remove the statusline, delete the `statusLine` field from `~/.claude/settings.json` and remove `~/.claude/statusline-command.sh`.
