---
name: claude-prompt-config
version: 1.1.0
description: This skill should be used when the user asks to "sync my CLAUDE.md", "install my global prompt", "apply my Claude config", "update the global CLAUDE.md", "push my CLAUDE.md to <host>", or wants to replace the global Claude Code instruction file with the maintained default, on this machine or on a remote host.
disable-model-invocation: true
---

# Claude Prompt Config

Replace the global Claude Code instruction file with the maintained default in
this skill. The file is `${CLAUDE_CONFIG_DIR:-$HOME/.claude}/CLAUDE.md`: Claude
Code reads its configuration from `CLAUDE_CONFIG_DIR` when the variable is set.
Claude Code loads the file into the system prompt in every session on that
machine. The skill is user-invoked, because it replaces the whole file.

The maintained default is
`${CLAUDE_PLUGIN_ROOT}/skills/claude-prompt-config/assets/global-claude-md.md`.
It is the only source. This skill writes in one direction, from this plugin to
a target machine. It never copies the file on a target back into this
repository. To change the default, edit
[assets/global-claude-md.md](assets/global-claude-md.md) and open a pull
request.

The script [scripts/install_prompt.sh](scripts/install_prompt.sh) builds the
new file. The new file is the maintained default, plus the
`# GTD agent captures` section of the old file when it has one. The
`gtd-setup` skill adds that section in its step 9; without it, agent captures
turn off.

## Procedure

Apply these steps to the local machine. When the user names remote hosts, apply
the same steps to each host as [Remote hosts](#remote-hosts) describes.

1. Show what the new file drops. This command writes nothing:

   ```bash
   bash "${CLAUDE_PLUGIN_ROOT}/skills/claude-prompt-config/scripts/install_prompt.sh"
   ```

   It prints `target: <path>`, then one of these lines:
   - `new file`: no file exists.
   - `unchanged`: the file already has the new content. Report it and stop
     for this target.
   - `keep: # GTD agent captures`: the new file keeps that section.
   - `drop: <line>`: one for each line with text that the new file does not
     have.
2. When the output has a `drop:` line, show each one to the user. Ask whether
   to replace the file. Stop for this target when the user says no. When a
   dropped line holds the agent-capture rule outside a `# GTD agent captures`
   section, tell the user to run `gtd-setup` step 9 again after the
   replacement.
3. Replace the file:

   ```bash
   bash "${CLAUDE_PLUGIN_ROOT}/skills/claude-prompt-config/scripts/install_prompt.sh" --apply
   ```

   The script creates the folder when it does not exist. It copies the old
   file to `CLAUDE.md.bak-YYYYMMDD-HHMMSS` in the same folder, writes the new
   file, and compares it with the new content. It prints `backup: <path>` and
   `wrote: <path>`. It writes through a symlink and keeps the symlink.
4. Report each target, its result, and its backup filename. If one target
   fails, report it and continue with the others.

### Remote hosts

1. Make a temporary folder on the host, and copy the script and the
   maintained default to it:

   ```bash
   scp "${CLAUDE_PLUGIN_ROOT}/skills/claude-prompt-config/scripts/install_prompt.sh" \
     "${CLAUDE_PLUGIN_ROOT}/skills/claude-prompt-config/assets/global-claude-md.md" \
     <host>:<temporary folder>/
   ```

2. Run steps 1-3 on the host with
   `ssh <host> bash <temporary folder>/install_prompt.sh --asset <temporary folder>/global-claude-md.md`,
   and add `--apply` for step 3.
3. Remove the temporary folder.

The script reads `CLAUDE_CONFIG_DIR` from the shell that `ssh` starts. A
non-interactive `ssh` shell can skip the login profile that sets it. When the
user runs Claude Code on the host with another configuration folder, put
`CLAUDE_CONFIG_DIR=<folder>` before `bash` in the `ssh` command.

## Uninstall

Copy the newest `${CLAUDE_CONFIG_DIR:-$HOME/.claude}/CLAUDE.md.bak-*` file over
`${CLAUDE_CONFIG_DIR:-$HOME/.claude}/CLAUDE.md` on the target. To take out the
instruction file, delete `${CLAUDE_CONFIG_DIR:-$HOME/.claude}/CLAUDE.md`.

## Notes

- The new file takes effect in the next Claude Code session on the target. A
  running session keeps the file it loaded.
- Codex reads `~/.codex/AGENTS.md`. That is a separate file with different
  content. This skill does not touch it.
