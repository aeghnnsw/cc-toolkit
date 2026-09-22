---
name: claude-prompt-config
version: 1.0.0
description: This skill should be used when the user asks to "sync my CLAUDE.md", "install my global prompt", "apply my Claude config", "update the global CLAUDE.md on this machine", "push my CLAUDE.md to <host>", or wants to replace the global Claude Code instruction file with the maintained default, on this machine or on an SSH host.
---

# Claude Prompt Config

Replace the global Claude Code instruction file with the maintained default in
this skill. The file is `~/.claude/CLAUDE.md`. Claude Code loads its contents
into the system prompt in every session on that machine.

The maintained default is [assets/global-claude-md.md](assets/global-claude-md.md).
It is the only source. This skill writes to machines. It never copies a
machine's file back into this repository. To change the default, edit
`assets/global-claude-md.md` and open a pull request.

## Procedure

1. Determine the targets. Use the local machine when the user names none.
   Accept SSH host names when the user gives them.
2. Create `~/.claude/` on the target when it does not exist.
3. Back up the existing file. Copy `~/.claude/CLAUDE.md` to
   `~/.claude/CLAUDE.md.bak-YYYYMMDD-HHMMSS`. Skip this step when no file
   exists.
4. Copy `assets/global-claude-md.md` to `~/.claude/CLAUDE.md` on the target.
5. Verify the copy. Compare the checksum of the target file against the source.
6. Report each target, its result, and its backup filename.

## Remote targets

Resolve host names from the user's `~/.ssh/config`. Run the backup and the copy
over `ssh`. If a host is unreachable, report it and continue with the other
targets. Do not change a target you could not read.

## Rollback

Each run leaves a timestamped backup. To undo a run, copy that backup over
`~/.claude/CLAUDE.md` on the target.

## Notes

- The new file takes effect in the next Claude Code session on that machine. A
  running session keeps the file it loaded.
- Codex reads `~/.codex/AGENTS.md`, which is a separate file with different
  content. This skill does not touch it.
