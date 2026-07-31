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

Normalize line continuations and strip comments from the quote-aware source
text, then tokenize with Python's standard-library `shlex` support. Quoted and
escaped punctuation remains literal. Shell control operators split commands,
while redirections and their operands remain part of the simple command long
enough to locate its executable and removal targets accurately.

Inspect only invocations whose resolved program is `rm`. Besides direct path
forms, resolve common wrappers and launchers including `sudo`, `env`, `command`,
`exec`, `time`, `xargs`, `find -exec`, `timeout`, `nice`, `ionice`, `stdbuf`,
`chroot`, `watch`, and `parallel`. Wrapper option parsing consumes long, short,
clustered, inline, and separate option values according to each supported
launcher. Executable basenames are compared case-insensitively because default
macOS filesystems resolve names such as `RM` to the same program as `rm`.

Recursively inspect shell `-c`/fish `-C` command strings, `eval`, shell-mode
`watch` and `parallel` templates, command substitutions, and process
substitutions. `env -S` is handled as an argv splitter rather than as shell
text: its split arguments are combined with the remaining outer operands and
then analyzed as one invocation. For `find -exec rm ... {}`, protected starting
paths are treated as the substituted removal targets.

For each real `rm` invocation:

- apply wildcard checks only to that invocation's arguments;
- apply dangerous-path checks only to its removal targets;
- continue blocking `/`, `.`, `..`, home references, and protected system
  directories, including absolute paths with redundant leading slashes;
- allow an explicit target strictly beneath the active per-user temporary
  directory, while continuing to block removal of the temporary root itself;
- return a specific reason for a rejection so the hook can explain which rule
  matched.

Malformed shell text that appears to invoke `rm` remains blocked
conservatively because its targets cannot be classified safely.

## Temp-directory exception

The exception is derived from the process environment (`TMPDIR`) and Python's
resolved temporary directory. Both the configured root and candidate target
are normalized before containment is checked. `/`, ancestors of protected
system roots, and broad protected roots are never trusted. A temp root inside
`/var` is trusted only when it has exactly the macOS per-user
`/var/folders/<id>/<id>/T` shape; over-deep or unrelated values cannot bypass
protection.

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

Regression tests cover that the hook allows:

- explicit cleanup of a file beneath a configured macOS-style `TMPDIR`;
- explicit `rm` followed by a separate command containing a glob;
- issue, commit, grep, or echo text that merely quotes `rm` and `/var`;
- real shell comments and literal quoted/process-substitution text;
- protected paths used only as redirection destinations;
- non-`rm` utilities whose arguments contain standalone `rm` and `/var`
  tokens;
- ordinary explicit files under `/tmp`.

Safety tests cover that it still blocks:

- `/`, protected system directories, `.`, `..`, home references, and the temp
  root itself;
- broad or unrelated protected paths supplied through `TMPDIR`;
- wildcards belonging to an actual `rm`;
- dangerous `rm` after compound-command separators, inside shell groups and
  function bodies, and through common wrappers;
- dangerous `rm` across line continuations and shell redirections;
- dangerous `rm` inside recognized shell, launcher, `eval`, and `env -S`
  command forms;
- dangerous `rm` inside command and process substitutions;
- protected `find` roots substituted into `find -exec rm ... {}`;
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
- Inferring data sent to `xargs` through pipes, files, or standard input.
- Changing the hook's fail-open behavior for invalid hook JSON or unrelated
  runtime exceptions.
