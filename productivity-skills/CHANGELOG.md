# Changelog

## [4.2.0] - 2026-03-24

### Changed
- Increase gtd-next recommended tasks from 5 to 10 (no time constraint mode)
- Bump gtd-next skill to v2.1.0

## [4.1.0] - 2026-03-24

### Changed
- Rewrite gtd-process to infer categorization, project, priority, time, and due date automatically
- Reduce user interaction to single confirm/modify per item (was 3-6 questions)
- Agent analyzes inbox item text and existing projects to propose processing
- Bump gtd-process skill to v2.0.0

## [4.0.0] - 2026-03-24

### Changed
- Rewrite gtd-next to be fully autonomous — agent decides what to work on, no user interaction
- Remove all AskUserQuestion calls from gtd-next
- With time constraint (next event): auto-select optimal tasks and generate time-blocked agenda
- Without time constraint: present top 5 ranked tasks with time estimates
- Bump gtd-next skill to v2.0.0

## [3.1.0] - 2026-03-22

### Changed
- Remove command-specific frontmatter (argument-hint, allowed-tools, model) from all GTD skills
- Rewrite gtd-inbox and gtd-process to use user-intent detection instead of $ARGUMENTS
- Full compliance with skill-development standard

## [3.0.1] - 2026-03-22

### Changed
- Standardize calendar-manager and reminder-manager frontmatter
- Add missing `version` field to both skills
- Rewrite descriptions to third-person trigger format for consistency with GTD skills

## [3.0.0] - 2026-03-19

### Changed
- Migrate all GTD commands from `commands/` to `skills/<name>/SKILL.md` format
- Add `name` and `version` fields to all skill frontmatter
- Rewrite descriptions to third-person trigger format for better discoverability
- Remove legacy `commands/` directory

## [2.2.0] - 2026-01-19

### Changed
- `/gtd-project` now supports multiple parallel actions per project
- `/gtd-next` clarified to show all actions even if multiple belong to same project
- Updated project status logic: Healthy (1+ actions), Stalled (0 actions), Overdue (any action overdue)
- "Add action" now available for all projects, not just stalled ones
- After completing action, only prompts for next if no remaining actions

## [2.1.0] - 2026-01-15

### Added
- `/gtd-next` command for calendar-aware task selection (GTD Engage step)
- Batched AskUserQuestion calls for independent questions

### Changed
- Refactored `/gtd-process` to batch time/priority/due questions
- Refactored `/gtd-project` to batch action property questions
- Added documentation for batched vs sequential question patterns

## [2.0.0] - 2026-01-14

### Added
- `/gtd-inbox` command for GTD inbox management (capture, list, remove)
- `/gtd-process` command for processing inbox into projects/actions
- `/gtd-project` command with guided workflow and auto-review
- Time-aware capture (relative dates converted to explicit dates)
- Pomodoro-based context lists (@quick, @1pomo, @2pomo, @deep)
- Project end goal tracking

### Changed
- Run Swift source directly instead of compiled binary (no build step)
- Updated CLI usage in all skills to use `swift productivity-cli.swift`

## [1.2.0] - 2025-12-28

### Added
- Personal assistant agent for proactive task management
- Pomodoro mode support

## [1.1.0] - 2025-12-27

### Added
- Calendar manager skill
- Reminder manager skill

## [1.0.0] - 2025-12-26

### Added
- Initial release
- productivity-cli.swift for EventKit access
