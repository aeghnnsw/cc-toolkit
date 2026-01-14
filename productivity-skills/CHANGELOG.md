# Changelog

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
