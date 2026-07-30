# Design — scope `safety_guard` checks to real `rm` invocations

**Issue:** [#181](https://github.com/aeghnnsw/cc-toolkit/issues/181)
**Branch:** `bugfix-181-safety-guard-macos-temp`

## Problem

`core-hooks/scripts/safety_guard.py` searches the normalized text of an entire
shell command. Once it sees `rm ` anywhere, every wildcard and protected path
anywhere else in the command can trigger the guard.

That produces three false-positive classes:

1. A normal macOS temporary file under the per-user `$TMPDIR` is rejected
   because that directory lives under `/var/folders`.
2. A wildcard in a later command, such as `ls prefix*`, is treated as if it
   belonged to an earlier explicit `rm`.
3. Quoted prose containing both `rm ` and a protected path is treated as a
   destructive command even when the invoked program is non-destructive.

The hook must remove those false positives without weakening protection for
actual destructive `rm` invocations.

## Decision

Tokenize shell input with Python's standard-library `shlex` support and split it
at shell control operators. Inspect only segments whose invoked program is
`rm`, including direct path forms and common command wrappers such as `sudo`,
`env`, and `command`. Recognized shell interpreters using `-c` are inspected
recursively so invocation scoping does not create a bypass for commands such
as `bash -c "rm /var/..."`. Executing command substitutions inside unquoted or
double-quoted text are also inspected, while literal single-quoted text is not.

For each real `rm` invocation:

- apply wildcard checks only to that invocation's arguments;
- apply dangerous-path checks only to its removal targets;
- continue blocking `/`, `.`, `..`, home references, and protected system
  directories;
- allow an explicit target strictly beneath the active per-user temporary
  directory, while continuing to block removal of the temporary root itself;
- return a specific reason for a rejection so the hook can explain which rule
  matched.

Malformed shell text that appears to invoke `rm` remains blocked
conservatively because its targets cannot be classified safely.

## Temp-directory exception

The exception is derived from the process environment (`TMPDIR`) and Python's
resolved temporary directory. Both the configured root and candidate target
are normalized before containment is checked. A temp root inside a protected
system tree is trusted only when it has the macOS per-user
`/var/folders/<id>/<id>/T` shape; broad or unrelated values such as `/var`,
`/var/folders`, or `/var/log/.../T` cannot bypass protection.

Only descendants are exempt. The temp root itself, targets containing a parent
component, wildcard targets, and paths resolving outside the configured root
remain blocked. The exception therefore permits ordinary `mktemp` cleanup
without making the broader `/var/folders` tree removable.

## Compatibility

The hook retains `is_dangerous_rm_command(command)` as its boolean public
helper. A reason-returning helper supplies diagnostics to `main()`.

No runtime dependency is added; the plugin continues to run with
`uv run --no-project`.

## Testing

Regression tests will verify that the hook allows:

- explicit cleanup of a file beneath a configured macOS-style `TMPDIR`;
- explicit `rm` followed by a separate command containing a glob;
- issue, commit, grep, or echo text that merely quotes `rm` and `/var`;
- ordinary explicit files under `/tmp`.

Safety tests will verify that it still blocks:

- `/`, protected system directories, `.`, `..`, home references, and the temp
  root itself;
- broad or unrelated protected paths supplied through `TMPDIR`;
- wildcards belonging to an actual `rm`;
- dangerous `rm` after compound-command separators, inside shell groups and
  function bodies, and through common wrappers;
- dangerous `rm` inside a recognized shell interpreter's command string;
- dangerous `rm` inside command substitutions, including double-quoted ones;
- literal `rm` text inside single quotes remaining allowed;
- malformed shell text that appears to invoke `rm`.

Tests will exercise both Claude `Bash` and Codex `exec_command` payloads where
the transport matters.

## Files affected

- `core-hooks/scripts/safety_guard.py`
- `core-hooks/tests/test_safety_guard.py`
- `core-hooks/.claude-plugin/plugin.json` for a patch-version bump

## Out of scope

- Full POSIX/Bash grammar support.
- Detecting deletion performed indirectly by arbitrary programs or scripts.
- Changing the hook's fail-open behavior for invalid hook JSON or unrelated
  runtime exceptions.
