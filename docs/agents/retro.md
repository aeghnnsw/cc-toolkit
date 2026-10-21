# Navigation Retrospectives

A navigation retrospective reads earlier agent sessions of this repository.
It finds where agents spent many calls to find information, or relied on
out-of-date documents. Each retrospective records its result as a comment on
the tracking issue, so the next one starts where the last one ended.

1. Find the tracking issue: the open issue that this search lists (#294 in
   October 2026). If none is open, create a `documentation` issue with
   "navigation" in its title.

   ```bash
   gh issue list --repo aeghnnsw/cc-toolkit --state all --search 'navigation in:title' --limit 5
   ```

2. Read the newest retrospective comment on the tracking issue.
3. Read the open `documentation` issues. Report a known candidate again only
   with new evidence.
4. Select the sessions that started after that comment and ran in the main
   checkout, `trees/*`, or `.claude/worktrees/*`. Claude Code sessions are
   JSONL files under `~/.claude/projects/` with a `cwd` field. Codex
   sessions are JSONL files under `~/.codex/sessions/` with the `cwd` in
   their `session_meta` line.
5. Process only copies of the selected transcripts, in one `mktemp -d`
   directory.
6. Post a new comment on the tracking issue: the sessions read, the
   findings, the fixes made, and the candidates that remain.
