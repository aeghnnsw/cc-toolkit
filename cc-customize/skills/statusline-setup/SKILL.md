---
name: statusline-setup
version: 2.0.0
description: This skill should be used when the user asks to "set up statusline", "configure statusline", "install statusline", "set up status bar", or wants to configure the Claude Code statusline with model info, git status, context/rate-limit bars, prompt-cache state, and session token and cost totals.
---

Install and configure a custom Claude Code statusline that shows model info, git status, context usage, rate limits, prompt-cache state, and session token and cost totals.

## What It Does

The statusline displays 3 lines. Each item shows only when Claude Code sends its field.

1. **Session** — `[Opus 5.5 · high · fast] │ my-session │ my-project git:(main* ↑1) │ wt:feat-1 │ PR #12 approved │ INSERT`
   - Model, effort level, `fast` mode, and `no-think` when thinking is off.
   - Session name, project directory, and git branch. `*` marks uncommitted changes to tracked files. `↑`/`↓` count commits ahead of and behind the upstream. A detached HEAD shows as `@<short-sha>`.
   - Worktree name, PR number and review state, and vim mode.
2. **Usage bars** — `Context ███░░░░░░░ 31% (113.8K/367.0K) │ 5h: … (4h 33m) │ 7d: … (2d 10h) │ spend: …`
   - Context usage is measured against the auto-compact trigger, the point where Claude Code compacts. The trigger is the window minus about 33,000 tokens (a 20,000-token summary reserve plus a 13,000-token margin). The window is `CLAUDE_CODE_AUTO_COMPACT_WINDOW`, else `autoCompactWindow` from the user `settings.json`, else the model context window. It is capped at the model context window. `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` can only lower the trigger. When auto-compact is off, the bar uses the window.
   - The script does not read project settings files or the `--autocompact` launch flag. When the window is set there, the bar uses the wrong limit.
   - 5-hour and 7-day rate limits with reset countdowns, and the spend limit.
   - Bars are green below 50%, yellow from 50%, and red from 90%.
3. **Session totals** — `tasks 3/5 │ cache 1h: warm 59m hit 91% │ tokens 648.0K │ cost $0.67`
   - Completed and total tasks in the session task list.
   - Prompt-cache state (warm with time to expiry, or cold), hit ratio, and misses.
   - Total tokens (input, cache write, cache read, and output) of the session and its subagents. `…` shows until the first count is ready.
   - Session cost estimate from Claude Code.

### Performance

Claude Code cancels a statusline run that is still busy when the next update arrives. The script keeps each run fast:

- One `jq` call parses the input.
- Git status is cached for 5 seconds per session.
- A detached background process adds the new transcript lines to the token total. It reads only the bytes added since its last run.

Per-session state is kept in `${TMPDIR:-/tmp}/cc-statusline-<uid>/<session-id>/`. The script sets the directory to mode 700. If another user owns the directory, the script keeps no state: the token total shows `…` and git status is not cached. The last input JSON is saved there as `last-input.json` for debugging.

The script reads `settings.json` and the session task list from `${CLAUDE_CONFIG_DIR:-~/.claude}`. If `settings.json` is not valid JSON, the script ignores it.

## Prerequisites

- `bash` and `jq` (`brew install jq` on macOS).
- `git` for the git status. Linux and macOS are supported. The script uses `flock` and `setsid` when they are available, and falls back to a `mkdir` lock on macOS.

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
