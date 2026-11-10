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

## Host compatibility

Target the current releases of Claude Code and Codex. Avoid adding
compatibility code or fallbacks for older host releases. Require a host
update when an installed release lacks a capability needed by the plugin.
