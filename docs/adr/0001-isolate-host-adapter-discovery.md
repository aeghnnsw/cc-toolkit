# Isolate host adapter discovery

> **Superseded in part (2026-11-22, issue #487).** An error that the
> safety script catches blocks the tool call in Claude Code and Codex too,
> not only in Antigravity. Read [Safety script errors](#safety-script-errors).

Core Hooks ships host-specific manifests and hook configurations alongside
shared scripts so each host can load its own installed copy independently.
Claude Code and Codex use their native plugin-root locators; neither adapter
searches another host's installation. The [Antigravity adapter](#antigravity-adapter)
follows the same rule. The Codex adapter has no fallback to
an executable on `PATH`. This keeps discovery independent of which other
agent tools happen to be installed.

The Codex hook configuration maps observable safety-hook failures to a
blocking result, and logging or notification failures to a warning with a
successful exit. This policy covers failures seen by the hook's shell
wrapper; it cannot cover the host failing to launch that shell or
terminating the entire hook. Claude Code retains its own hook configuration.
A native Grok Build adapter is deferred; shared-script tests cover its
payload format without guaranteeing host-level hook invocation.

The Codex safety and git policy commands pass `--host codex`. In this mode,
those scripts exit 3 for a block, and their wrappers change that status to 2
without the failure line, because `uv` also exits 2 when it cannot start a
script. Every other nonzero status of these two commands blocks with the
failure line. The wrappers keep the status in `rc`, because zsh reserves
`status` as a read-only variable
([#442](https://github.com/aeghnnsw/cc-toolkit/issues/442)).

See the [host-isolation design](https://github.com/aeghnnsw/cc-toolkit/blob/4be3c4bf74dd07eb08bde12da95f0c26f24980b6/docs/superpowers/specs/2026-08-18-core-hooks-codex-host-isolation-design.md)
and the [Codex adapter tests](../../core-hooks/tests/test_codex_host_adapter.py)
for the implementation boundaries and validation.

## Antigravity adapter

Added on 2026-11-21 for
[#430](https://github.com/aeghnnsw/cc-toolkit/issues/430).

Antigravity reads the Core Hooks configuration from a root `hooks.json`.
Antigravity runs each hook command from the plugin root, so the commands
name the shared scripts by paths relative to it, and the adapter searches no
other host's installation. Each command passes `--host antigravity`. In this
mode, the scripts read the Antigravity payload and write nothing to stdout.
A block reaches Antigravity as exit status 2 with the reason on stderr. No
script returns an `allow` decision, because `allow` skips the permission
checks of Antigravity. Logs go under the Git top level of the payload `cwd`,
never under the plugin root or an inherited `CLAUDE_PROJECT_DIR`.

The wrappers apply the Codex failure policy: a safety or git policy hook
failure blocks, and a zsh trap, logging, or notification hook failure writes
a warning to stderr and exits 0. `uv` also exits 2 when it cannot start a
script. So the safety, git policy, and zsh trap scripts exit 3 for a block,
and their wrappers change that status to 2 without the failure line. An
Antigravity safety script error exits 1, so its wrapper blocks; in Claude
Code and Codex, a safety script error still allows the command. (Superseded
in part; read [Safety script errors](#safety-script-errors).) The wrappers
keep the status in `rc`, because zsh reserves `status` as a read-only
variable.

Antigravity has no Notification, SessionEnd, or SubagentStop event, and a
PreToolUse hook cannot warn without blocking. So the adapter drops the git
policy reminders and the branch-prefix message, and each zsh trap blocks.
The adapter skips the unmatched-glob check. That check reads the files
before the command runs, so it can block a command that creates them
first. The adapter also skips the pipefail warning, which must not block a
command. No measured Antigravity contract changes the command, so the zsh
rewrite becomes a block that names the corrected command. See
[ADR 0006](0006-antigravity-plugin-layout.md#hook-failure-policy) and the
[Antigravity adapter tests](../../core-hooks/tests/test_antigravity_host_adapter.py).

## Safety script errors

Added on 2026-11-22 for
[#487](https://github.com/aeghnnsw/cc-toolkit/issues/487).

An error that the safety script catches blocks the tool call in Claude
Code, Codex, and Antigravity. Examples are unreadable input and a failed log
write. Where a safety check cannot decide, it blocks, and an error is such a
case. The script writes the error and the host's way to turn off Core Hooks
to stderr, so that a bug in the guard does not leave the user with no way to
run a command. It exits 2 in Claude Code, which blocks on 2. In Codex and
Antigravity mode, it exits 1, and the wrapper blocks with the failure line.

The script catches the errors after it starts. A failure before that, such
as an import error or a missing `uv`, gets no message from the script. The
Codex and Antigravity wrappers block it. The Claude Code configuration has
no wrapper, so Claude Code lets the tool call run unless the status is 2.
The git policy script is unchanged: an error exits 1, so Codex and
Antigravity block, and Claude Code lets the tool call run.
