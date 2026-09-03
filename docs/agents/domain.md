# Domain documentation

Use one domain context for cc-toolkit. Accepted architecture decisions live
in [../adr/](../adr/). Create a root `CONTEXT.md` only when agreed terms need
a glossary; its absence does not block development.

Before changing terminology or architecture, read the glossary if present
and the relevant decision records. Use the glossary's terms consistently.
If proposed work contradicts a decision, surface the conflict and resolve
it explicitly before changing the documented policy.

Keep implementation details in design documents and ADRs, and definitions
in the glossary. Add an ADR for a consequential trade-off whose rationale
future contributors would otherwise have to rediscover.

Current decision:

- [Isolate host adapter discovery](../adr/0001-isolate-host-adapter-discovery.md)
