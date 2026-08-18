# Design — harden Codex Core Hooks host isolation

**Issue:** [#191](https://github.com/aeghnnsw/cc-toolkit/issues/191)
**Branch:** `bugfix-191-codex-hook-isolation`

## Goal

Make the Codex Core Hooks adapter demonstrably independent of every other host
adapter, and make its observable failure behavior match the safety policy.
Codex must discover and execute its own installed plugin copy without probing a
Claude Code or Grok Build installation.

## Current behavior

`core-hooks/.codex-plugin/plugin.json` selects
`./hooks/hooks.codex.json`. That hook configuration already invokes scripts via
Codex's native `${PLUGIN_ROOT}` value. Codex supplies this value to plugin hook
commands and points it at the installed Codex plugin copy. Hook commands run
from the active session working directory, so bare relative script paths are
not plugin-relative.

The discovery path is therefore already host-independent. The missing pieces
are regression tests, robust quoting, and explicit failure-status translation.
Codex treats generic hook launch or runtime failures as failed hooks but does
not block a `PreToolUse` call. Blocking requires the documented exit status 2
with a nonempty stderr reason, or valid deny JSON. Conversely, exit status 2
from a noncritical `Stop` hook can be interpreted as a deliberate continuation
request rather than an incidental operational failure.

References:

- [Codex hooks](https://learn.chatgpt.com/docs/hooks)
- [Codex plugin packaging](https://developers.openai.com/plugins/build/plugins)

## Host boundary

This change affects only the Codex Host Adapter:

- `core-hooks/.codex-plugin/plugin.json`
- `core-hooks/hooks/hooks.codex.json`
- Codex-facing tests and documentation

Claude files and shared hook scripts remain unchanged. Grok Build remains a
planned host and is out of scope. One release archive may contain multiple host
adapters; independence means that Codex discovers only its own manifest and
hook configuration and does not inspect another host's files or installation.

Codex supports `${PLUGIN_ROOT}` natively in the current supported release. No
older Codex releases, foreign-root fallback, relative-path fallback, or
host-qualified executable on `PATH` will be supported.

## Hook commands

Every script path in `hooks.codex.json` will be quoted as
`"${PLUGIN_ROOT}/scripts/<script>.py"`. The adapter retains `uv run
--no-project`; `uv` is an explicit runtime prerequisite rather than another
host dependency.

### Safety hooks

The `safety_guard.py` and `pre_git_hook.py` commands are `PreToolUse` policy
boundaries. Their outer shell commands will inspect the script process status.
Success remains status 0. Every observable nonzero status emits a concise
blocking reason on stderr and exits with status 2, including:

- `uv` unavailable;
- the installed script path unavailable;
- interpreter or dependency startup failure;
- an unhandled script failure; and
- an intentional policy rejection already returned by the script.

The wrapper may add a generic failure reason after a script's more specific
rejection reason. Correct control behavior takes priority over deduplicating
stderr.

### Noncritical hooks

The `post_tool_use.py` logging hook and `system_notification.py` Stop hook are
noncritical. Their outer shell commands will preserve status 0 on success and
translate every nonzero status to 0 after emitting a concise warning on stderr.
This prevents an incidental `uv` status 2 from becoming a Codex control signal.

### Host limitation

The shell guard can translate only failures it observes. It cannot intercept
Codex failing to spawn the outer shell or Codex terminating the entire hook at
the host timeout. Those host-level cases remain fail-open in the current Codex
runtime and must be documented rather than represented as protected.

## Versioning

The Codex plugin manifest moves from `1.0.11` to `1.0.12`. The Claude manifest
and marketplace metadata remain untouched because host versions are
independent and this change does not modify shared scripts.

For local installed-plugin verification only, the plugin-creator cachebuster
helper temporarily converts the Codex version to
`1.0.12+codex.<timestamp>`. The cache-busted files are staged in an isolated
local marketplace for the smoke test. After staging, the source manifest
returns to the release version `1.0.12`; marketplace files are not edited by
hand.

## Test seams

Tests exercise two public boundaries agreed during design review.

### Discovery and configuration seam

- The Codex manifest selects exactly `./hooks/hooks.codex.json`.
- The selected file resolves beneath the Core Hooks plugin root and parses.
- Every configured Codex hook command contains a quoted
  `${PLUGIN_ROOT}/scripts/` path.
- No configured Codex hook command contains `CLAUDE_PLUGIN_ROOT`,
  `GROK_PLUGIN_ROOT`, a `.claude` cache path, or a `.grok` cache path.

### Executed hook-command seam

Tests execute the configured shell commands, not a separately reimplemented
status mapper.

- A safety hook runs successfully with the real plugin root while
  `CLAUDE_PLUGIN_ROOT` points at an invalid poison path.
- Missing `uv`, a missing script, and a generic nonzero script process each
  produce status 2 plus a nonempty reason for safety hooks.
- The equivalent operational failures produce status 0 plus a warning for
  logging and notification hooks.

Each red/green cycle adds one behavioral assertion and the minimum command
change needed to satisfy it.

## Installed verification

After the focused and full Core Hooks suites pass:

1. Validate the manifest and hook JSON through the test suite. The bundled
   plugin-creator validator currently rejects the officially supported `hooks`
   field, so it cannot validate this hook plugin without a false failure.
2. Apply a temporary Codex cachebuster with the plugin-creator helper.
3. Use the plugin-creator scaffold command to create an isolated local
   marketplace, stage the exact cache-busted plugin files there, and install
   them with `codex plugin add`. This avoids rewriting the active remote
   `cc-toolkit` marketplace.
4. Start the smoke command from a working directory unrelated to the plugin
   source or cache.
5. Verify the installed manifest selects the Codex hook file and a safe
   `PreToolUse` payload reaches the installed script through `PLUGIN_ROOT` even
   with a poisoned Claude compatibility root.
6. Restore and revalidate the source release version `1.0.12`.
7. Remove only the temporary plugin and marketplace registrations after the
   smoke test so a later Codex session cannot load duplicate hooks.

A new Codex thread remains the final manual boundary for loading a newly
installed plugin into the app.

## Delivery tickets

Implementation is split into ordered vertical tickets:

1. [#192 — Lock the Codex Core Hooks adapter to native plugin discovery](https://github.com/aeghnnsw/cc-toolkit/issues/192)
2. [#193 — Enforce explicit Codex failure policy in Core Hooks commands](https://github.com/aeghnnsw/cc-toolkit/issues/193), after #192
3. [#194 — Validate the standalone installed Codex Core Hooks package](https://github.com/aeghnnsw/cc-toolkit/issues/194), after #192 and #193

Issue #191 remains the parent design and completion tracker.

## Out of scope

- Changes to Claude hook configuration or release metadata.
- A native Grok Build adapter.
- Shared hook-policy or payload-parsing changes.
- Removing the `uv` prerequisite.
- Supporting Codex releases without native `PLUGIN_ROOT`.
- Guaranteeing fail-closed behavior when Codex cannot start or retain control
  of the outer hook process.
