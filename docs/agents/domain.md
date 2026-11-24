# Domain documentation

Use one domain context for cc-toolkit. Agreed terms live in
[GLOSSARY.md](../../GLOSSARY.md). Accepted architecture decisions live in
[../adr/](../adr/).

Before changing terminology or architecture, read the glossary if present
and the relevant decision records. Use the glossary's terms consistently.
If proposed work contradicts a decision, surface the conflict and resolve
it explicitly before changing the documented policy. When a glossary entry
contradicts an accepted spec decision, change the entry in the same pull
request so that it follows the decision. To replace a rule in an
ADR, follow the superseded-note rule in
[CONTRIBUTING.md](../../CONTRIBUTING.md#what-belongs-in-git).

Keep implementation details in design documents and ADRs, and definitions
in the glossary. Add an ADR for a consequential trade-off whose rationale
future contributors would otherwise have to rediscover.

Current decisions:

- [Isolate host adapter discovery](../adr/0001-isolate-host-adapter-discovery.md)
- [Use a cross-family critic for pressure tests](../adr/0002-cross-family-pressure-test-critic.md)
- [Use the connected Supabase route for GTD](../adr/0003-use-connected-supabase-for-gtd.md)
- [Ship the GTD schema and a setup skill](../adr/0004-ship-the-gtd-schema.md)
- [Trigger agent captures from global instruction files](../adr/0005-trigger-agent-captures-from-global-instructions.md)
- [Use a native Antigravity plugin layout](../adr/0006-antigravity-plugin-layout.md)
- [Gate the project lead with a session-checked plugin hook](../adr/0007-gate-the-project-lead-with-a-session-checked-hook.md)
- [Keep the lead state in the step script](../adr/0008-keep-project-lead-state-in-a-cli.md)
- [Bind the lead state to its T3 thread, and find it in any worktree](../adr/0009-bind-the-lead-state-to-its-t3-thread.md)
- [Use entry files and a version script for parallel pull requests](../adr/0010-use-entry-files-and-a-version-script.md)
- [Give the merge-lock holder suite priority with a marker](../adr/0011-give-the-merge-lock-holder-suite-priority-with-a-marker.md)

## Host compatibility

Target the current releases of Claude Code, Codex, and Antigravity. For
Antigravity, this includes the desktop app, the IDE, and the `agy` CLI,
which share one plugin loader. Avoid adding compatibility code or fallbacks
for older host releases. Require a host update when an installed release
lacks a capability needed by the plugin.
