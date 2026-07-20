# Changelog

## [Unreleased]

### Changed

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
