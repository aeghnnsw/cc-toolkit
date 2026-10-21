# Navigation Retros

A navigation retro reads earlier agent sessions of this repository. It finds
where agents spent many calls to find information, or relied on out-of-date
documents. Each retro records its result as a comment on the navigation
tracking issue, so the next retro starts where the last one ended.

1. Find the tracking issue (#294 in October 2026):

   ```bash
   gh issue list --repo aeghnnsw/cc-toolkit --state all --search 'navigation in:title' --limit 5
   ```

2. Read its newest retro comment and the open `documentation` issues. Report
   a known candidate again only with new evidence.
3. Select the sessions that started after that comment. Select them by the
   `cwd` field of the session JSONL files under `~/.claude/projects/`: the
   main checkout, `trees/*`, and `.claude/worktrees/*`.
4. Copy each transcript to a `mktemp -d` directory, and process the copies.
   Leave the files under `~/.claude/projects/` unchanged.
5. Post a new comment on the tracking issue: the sessions read, the
   findings, the fixes made, and the candidates that remain.
