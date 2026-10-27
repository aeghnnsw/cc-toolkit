# Navigation Retrospectives

Read agent sessions to find slow information searches and stale guidance.
Keep a short `Navigation retrospective` record in each PR's body or a comment.
Never create or post to a catch-all tracking issue.

1. Read [issue-tracker.md](issue-tracker.md). Find completed retrospective
   records on merged PRs. Use the greatest `Reviewed through` timestamp as
   the previous cutoff. Do not use the PR or comment publication time.
   If no record exists, read relevant available earlier implementation
   sessions. Use the current session if none exist. State the history limit.
2. Read existing documentation issues before recording findings. Reuse a
   matching issue. Add a known finding only when you have new evidence.
3. Select sessions by repository and worktree metadata. Include the main
   checkout, `trees/`, and `.claude/worktrees/`. Claude Code stores JSONL
   transcripts under `~/.claude/projects/`, with `cwd` fields and subagents
   under `<session>/subagents/`. Codex stores JSONL transcripts under
   `~/.codex/sessions/`, with `cwd` in `session_meta`. Keep this metadata
   even when it precedes the previous cutoff. Do not select by session
   start time alone: an older session can contain newer records.
4. Record the current UTC time as this run's cutoff, then copy selected
   transcripts into one `mktemp -d` directory. Preserve the originals.
   Read only the copies. This fixed cutoff excludes records added during copying.
   Select records after the previous cutoff and through the current cutoff.
   Compare parsed timestamps, or normalize both values to UTC with
   milliseconds, such as `2026-10-27T14:32:18.847Z`. Do not compare timestamp
   strings with different precision. Report unavailable or unreadable history.
5. Apply small fixes in the same PR. A small fix needs no new design decision
   or substantial increase in scope. Run the relevant checks and review it.
   For each larger finding, create or reuse one separate follow-up issue.
   Block the PR only when the finding affects the current change's correctness.
6. Add the completed record to the PR. Include:

   - `Reviewed through: <UTC timestamp with milliseconds>`: the scanned
     snapshot cutoff, never the record's publication time.
   - Sessions reviewed and the previous cutoff or initial history scope.
   - Unavailable history and other limits.
   - Findings, fixes made, and separate follow-up issue links, or `none`.
7. Remove the temporary directory by its exact path after the review.
