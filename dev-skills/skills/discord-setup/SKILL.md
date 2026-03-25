---
name: discord-setup
version: 1.0.0
description: This skill should be used when the user asks to "set up discord", "configure discord bot", "install discord plugin dependencies", or wants to set up the prerequisites for the Claude Code Discord channel plugin including bun installation and shell alias configuration.
---

Set up prerequisites for the Claude Code Discord channel plugin.

## Step 1: Check and install bun

Check if bun is installed:

```bash
command -v bun
```

If bun is not found, install it:

```bash
curl -fsSL https://bun.sh/install | bash
```

After installation, detect the user's shell and add bun to the appropriate rc file:

```bash
echo $SHELL
```

- If zsh: add `export BUN_INSTALL="$HOME/.bun"` and `export PATH="$BUN_INSTALL/bin:$PATH"` to `~/.zshrc`
- If bash: add the same lines to `~/.bashrc`

Skip this step if bun is already on PATH.

## Step 2: Configure the dangercc-discord alias

Check if the alias already exists in the user's shell rc file (`~/.zshrc` or `~/.bashrc` based on Step 1).

If not present, add this alias:

```bash
alias dangercc-discord='DISCORD_STATE_DIR="$(pwd)/.claude/channels/discord" claude --dangerously-skip-permissions --channels plugin:discord@claude-plugins-official'
```

This alias launches Claude Code with:
- `--dangerously-skip-permissions` for unattended operation
- `--channels plugin:discord@claude-plugins-official` to connect the Discord bot
- `DISCORD_STATE_DIR` set to the current project directory so each project gets isolated Discord state

## Step 3: Verify

Confirm both are configured:

```bash
command -v bun && echo "bun: OK" || echo "bun: NOT FOUND"
```

Check the appropriate rc file (from Step 1) for the alias:

```bash
grep -q "dangercc-discord" ~/.zshrc 2>/dev/null || grep -q "dangercc-discord" ~/.bashrc 2>/dev/null && echo "alias: OK" || echo "alias: NOT FOUND"
```

Inform the user to restart their shell or run `source` on their rc file for changes to take effect.
