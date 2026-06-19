# Task-loop Loop C Drain Monitor Design

## Decision

Issue #169 changes Claude `run-cycle` stop handling from a one-shot bounded drain to a post-`stop_at`
drain monitor.

Initial `/run-cycle` still creates only:

- **Loop A**: fixed-interval active pass.
- **Loop B**: one-shot `stop_at` transition.

When Loop B fires, it validates its generation from schedule names, creates recurring **Loop C**, and
runs or wakes one drain tick. Loop B never dispatches, materializes re-attacks, or force-stops live
work.

Loop C runs the drain subset only: steering, liveness, PR merge/classification, and proposal
reconciliation. It skips materialization and dispatch. It cancels the generation only when no
positively live in-session worker or monitored detached job remains and no PR-present `working` task
still needs merge/classification.

## Boundaries

`stop_at` means "no new starts," not "abandon work already launched." Loop C waits only for observable
live work or PR-present work. Opaque `working`-no-PR rows without positive live ownership follow the
existing reset rule and never block the drain forever.

Codex support remains manual. A Codex post-`stop_at` pass can follow the same drain-only subset, but
Codex does not schedule unattended Loop A/B/C jobs yet.

## Versioning

Both task-loop plugin manifests move from `0.16.0` to `0.17.0` so Claude and Codex refresh cached
skill docs.
