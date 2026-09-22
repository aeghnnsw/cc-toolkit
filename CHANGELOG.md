# Changelog

## [Unreleased]

### Added

- cc-customize (Claude Code 1.3.0): add `claude-prompt-config` to back up and replace the global `~/.claude/CLAUDE.md` on the local machine or on an SSH host. Ship the maintained file as a skill asset and write in one direction only.
- pymol-skills (Codex 1.0.0): add the Codex manifest, marketplace registration, MCP launch configuration, and setup and visualization skills. Reuse the shared PyMOL bridge and socket plugin. See [#232](https://github.com/aeghnnsw/cc-toolkit/issues/232).

- Repository: add read-only package and affected-host release validation with a shared local command, explicit resource rules, command-interface fixtures, and one fast pull-request job. See [#206](https://github.com/aeghnnsw/cc-toolkit/issues/206).
- dev-skills (Codex 1.3.0): add `matt-automode` to run Matt’s planning, ticket implementation, PR merge, and cleanup workflows without human checkpoints.
- dev-skills (Claude Code 3.13.0): add `matt-automode` for Claude Code. Resolve user-invoked skills from the plugin registry and replace interactive checkpoints with agent decisions. Define "User-invoked skill" in the glossary. See [#223](https://github.com/aeghnnsw/cc-toolkit/issues/223).

### Removed

- dev-skills (Claude Code 3.11.0, Codex 1.4.0): retire the borrowed `handoff` skill; use Matt’s original skill instead.
- productivity-skills: remove the redundant Claude `personal-assistant` subagent; use `gtd-next` for task selection and agenda planning.
- GitHub Actions: remove the automatic Claude review from every pull request; keep on-demand `@claude` triggers.

### Changed

- dev-skills (Claude Code 3.13.1, Codex 1.5.1): require evidence-based investigation and grilling gates in `matt-automode`. Accept recommended answers after repository investigation and full grilling rounds. Block coding delegation until the spec and tickets are published and blockers are satisfied. Reopen affected gates when evidence changes, and report phase order accurately. See [#241](https://github.com/aeghnnsw/cc-toolkit/issues/241).

- cc-customize (Claude Code 2.0.0): configure auto-compact with the token-based
  `autoCompactWindow` setting and its `/autocompact`, `--autocompact`, and
  `CLAUDE_CODE_AUTO_COMPACT_WINDOW` overrides. State the precedence order and the
  per-model defaults, and mark `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` unreliable because
  it cannot raise the threshold and applies only in sessions that compact before the
  model context limit. Refresh the model, effort, and 1M context tables for Fable 5.1,
  Opus 5, and Sonnet 5, add `modelSettings` and `ultracode`, and replace the `max`
  effort bug wording with the documented behavior. See
  [#234](https://github.com/aeghnnsw/cc-toolkit/issues/234).

- core-hooks (Claude Code and Codex 1.0.13): stop two false positives. Match AI attribution forms in git operations instead of the bare product names `Claude Code` and `Codex CLI`, and keep heredoc bodies out of the shell tokenizer. Allow an unparseable command that cannot invoke `rm`, and keep blocking obfuscated removals and expanded removals inside a heredoc body. See [#236](https://github.com/aeghnnsw/cc-toolkit/issues/236).

- pymol-skills (Claude Code 2.0.2, Codex 1.0.0): constrain the shared bridge to MCP 1.x, which provides its FastMCP API. Verify startup from a relocated package.

- productivity-skills (Claude Code and Codex 6.3.0): store agent startup, support, and review as ordinary human actions in time-based lists. Use one human time budget, preserve waiting outcomes and legacy agent reminders, and explain GTD priority selection. See [#228](https://github.com/aeghnnsw/cc-toolkit/issues/228).

- dev-skills (Claude Code 3.12.0, Codex 1.5.0): move completed ticket and parent-spec reconciliation into `repo-cleanup`. Keep PR closing references in `matt-automode` and delegate post-merge closure to cleanup. See [#221](https://github.com/aeghnnsw/cc-toolkit/issues/221).
- dev-skills (Codex 1.4.2): require `matt-automode` to link resolving PRs, verify ticket closure after merge, and close fully satisfied parent specs. Keep partial work open and report unresolved issues. See [#219](https://github.com/aeghnnsw/cc-toolkit/issues/219).
- dev-skills (Codex 1.4.1): require `matt-automode` to use `step-workflow` before planning and throughout the task, while preserving repository layout and naming conventions. See [#217](https://github.com/aeghnnsw/cc-toolkit/issues/217).
- productivity-skills (Claude Code and Codex 6.2.0): keep GTD work undated unless a deadline is given, clarify concrete actions in batch proposals, recommend one action with alternatives, and display compact overview tables. Use reminder IDs and in-place edits to preserve existing data. See [#215](https://github.com/aeghnnsw/cc-toolkit/issues/215).

- productivity-skills: store the shared Claude Code and Codex GTD inbox at `~/.gtd/inbox.md`.
- Repository: track shared agent guidance and the host-adapter decision, document contributor and plugin package boundaries, and reserve `.scratch/` for disposable development output.
- dev-skills: store pressure-test sessions and conclusions under `docs/pressure-test` by default.
- dev-skills: add explicit repository cleanup for Claude Code and Codex.
- core-hooks: enforce pre-git and dangerous-removal policies under Grok Build by
  normalizing hook payloads and using cross-runtime blocking exits.
- core-hooks: scope safety checks to real `rm` invocations, allow valid macOS
  per-user temp descendants, and fail closed on parser errors.
- productivity-skills: add native Codex support for all seven Calendar, Reminders, and GTD skills.
- creator-skills/dev-skills: add native Codex support for `sci-slides`, `sci-figure-format`, and `step-workflow`.
- task-loop: replace Claude cycle-worker `TaskStop` reaping guidance with graceful teammate shutdown requests.
- task-loop: require positive no-live-owner evidence before resetting fresh-session opaque workers.
- task-loop: document Loop C post-`stop_at` drain monitoring and bump plugin manifests to `0.17.0`.
- task-loop: bump plugin manifests to `0.16.0` so Claude and Codex refresh cached run-cycle support.
- task-loop: add conservative manual Codex `run-cycle` support with observable worker dispatch gates.
- task-loop: document optional `set-seq` setup step before smoke testing existing task histories.
- task-loop: run CLI setup examples with `uv run --script` and add guarded `set-seq` support.
- task-loop: add structured CLI state output and CAS-only task issue repair for orchestrators.
- README: document Codex marketplace support, current dev-skills coverage, and the task-loop plugin's current Claude/Codex support status.
