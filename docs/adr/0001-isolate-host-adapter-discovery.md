# Isolate host adapter discovery

Core Hooks ships host-specific manifests and hook configurations alongside
shared scripts so each host can load its own installed copy independently.
Claude Code and Codex use their native plugin-root locators; neither adapter
searches another host's installation. The Codex adapter has no fallback to
an executable on `PATH`. This keeps discovery independent of which other
agent tools happen to be installed.

The Codex hook configuration maps observable safety-hook failures to a
blocking result, and logging or notification failures to a warning with a
successful exit. This policy covers failures seen by the hook's shell
wrapper; it cannot cover the host failing to launch that shell or
terminating the entire hook. Claude Code retains its own hook configuration.
A native Grok Build adapter is deferred; shared-script tests cover its
payload format without guaranteeing host-level hook invocation.

See the [host-isolation design](../superpowers/specs/2026-08-18-core-hooks-codex-host-isolation-design.md)
and the [Codex adapter tests](../../core-hooks/tests/test_codex_host_adapter.py)
for the implementation boundaries and validation.
