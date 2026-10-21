# Domain documentation

Use one domain context for cc-toolkit. Agreed terms live in
[CONTEXT.md](../../CONTEXT.md). Accepted architecture decisions live in
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
