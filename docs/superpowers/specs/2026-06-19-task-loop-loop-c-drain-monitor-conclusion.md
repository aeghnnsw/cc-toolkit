# Task-loop Loop C Drain Monitor Pressure-Test Conclusion

The initial Loop C design failed pressure testing until these points were tightened:

- Loop A must not cancel the generation at `stop_at` before Loop B installs Loop C.
- The "finish long work" guarantee must be scoped to observable in-session workers, monitored detached
  jobs, and PR-present tasks; hidden opaque no-PR rows cannot be treated as live.
- Drain-only classification must leave failed/blocked/stuck attempts recoverable without starting new
  attempts after `stop_at`.
- Stale generation checks must use schedule names because there is no DB cell, stored handle, or local
  runtime file.
- Codex docs must describe manual drain-only passes only, not unattended scheduling.

The implemented wording addresses those objections by making Loop B the stop transition, making Loop C
the post-`stop_at` cancellation authority, deferring drain-time re-attacks to the next active run, and
updating the README plus authoritative design spec alongside the skill files.
