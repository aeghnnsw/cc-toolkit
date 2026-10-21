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
4. Select the sessions that have records after that comment and ran in
   the main checkout, `trees/*`, or `.claude/worktrees/*`. A session that
   started before the comment can have later records; read only the
   records after the comment. Record timestamps have milliseconds, so
   compare each `timestamp` with the comment time written with
   milliseconds, such as `2026-10-21T20:22:41.000Z`. As a string,
   `20:22:41Z` sorts after `20:22:41.847Z`, so a comparison with it drops
   the records of that second. Claude Code sessions are JSONL files under
   `~/.claude/projects/` with a `cwd` field, and their sub-agents are under
   `<session>/subagents/`. Codex sessions are JSONL files under
   `~/.codex/sessions/` with the `cwd` in their `session_meta` line; keep
   only those whose `cwd` is in this repository. To list the files that
   changed after the comment, make the `mktemp -d` directory of step 5 now,
   put a marker file with the comment's UTC time in it, and keep error
   output visible:

   ```bash
   TZ=UTC0 touch -t <YYYYMMDDhhmm.ss> <tmp-dir>/marker
   find ~/.claude/projects ~/.codex/sessions -name '*.jsonl' -newer <tmp-dir>/marker
   ```
5. Process only copies of the selected transcripts, in one `mktemp -d`
   directory.
6. Post a new comment on the tracking issue: the sessions read, the
   findings, the fixes made, and the candidates that remain.
