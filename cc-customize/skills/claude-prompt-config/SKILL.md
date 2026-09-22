---
name: claude-prompt-config
version: 1.0.0
description: This skill should be used when the user asks to "sync my CLAUDE.md", "install my global prompt", "apply my Claude config", "update the global CLAUDE.md", "push my CLAUDE.md to <host>", or wants to replace the global Claude Code instruction file with the maintained default, on this machine or on a remote host.
---

# Claude Prompt Config

Replace the global Claude Code instruction file with the maintained default in
this skill. The file is `~/.claude/CLAUDE.md`. Claude Code loads its contents
into the system prompt in every session on that machine.

The maintained default is
`${CLAUDE_PLUGIN_ROOT}/skills/claude-prompt-config/assets/global-claude-md.md`.
It is the only source. This skill writes in one direction, from this plugin to
a target machine. It never copies the file on a target back into this
repository. To change the default, edit
[assets/global-claude-md.md](assets/global-claude-md.md) and open a pull
request.

## Procedure

Apply these steps to the local machine. When the user names remote hosts, apply
the same steps to each host over `ssh`.

1. Create `~/.claude/` when it does not exist.
2. Back up the existing file. Copy `~/.claude/CLAUDE.md` to
   `~/.claude/CLAUDE.md.bak-YYYYMMDD-HHMMSS`. Skip this step when no file
   exists.
3. Copy the maintained default to `~/.claude/CLAUDE.md`.
4. Compare the checksum of the target file against the maintained default.
5. Report each target, its result, and its backup filename. If one target
   fails, report it and continue with the others.

## Uninstall

Copy the newest `~/.claude/CLAUDE.md.bak-*` file over `~/.claude/CLAUDE.md` on
the target. To take out the instruction file, delete `~/.claude/CLAUDE.md`.

## Notes

- The new file takes effect in the next Claude Code session on the target. A
  running session keeps the file it loaded.
- Codex reads `~/.codex/AGENTS.md`. That is a separate file with different
  content. This skill does not touch it.
