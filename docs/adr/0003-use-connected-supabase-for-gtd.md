# Use the connected Supabase route for GTD

> **Superseded in part (2026-11-09, issue #403).** New database setup is no
> longer separate work: the plugin ships its schema and a setup skill. Read
> [New database setup](#new-database-setup) and
> [ADR 0004](0004-ship-the-gtd-schema.md).

The live GTD workflow moved to Supabase while the shared skills still used
native files and Reminders. Use the connected Supabase management tool for
all five GTD skills, with a private project/owner binding and one packaged SQL
renderer and transaction. This uses the working authentication route without
introducing a second token client or a new service.

The renderer prepares queries; it never connects or reads credentials. The
transaction scopes every operation to the configured owner and preserves
revisions, exact retries, source provenance and recoverable deletion. This
management route is distinct from browser user-session RPC access and does
not establish end-user row-level security. Personal bindings stay outside
published packages.

Native GTD data remains a preserved source after cutover. Missing cloud access
is an explicit error, not a reason to resume native writes. General Calendar
and explicitly requested Reminders operations remain native. New database
setup, imports, synchronization and credential changes are separate work.
(Superseded for new database setup; read
[New database setup](#new-database-setup).)
Shared project-status policy interprets human readiness and waiting evidence;
it does not turn free-form notes into a required database state format.

See [#117](https://github.com/aeghnnsw/cc-toolkit/issues/117), implementation
[#382](https://github.com/aeghnnsw/cc-toolkit/issues/382), and the shipped
[cloud workflow](../../productivity-skills/references/gtd-cloud.md).

## New database setup

Before 2026-11-09, the plugin shipped no schema, so a person who installed
it could not create a GTD database, and the owner of an existing database
wrote the GTD binding by hand on each new computer. Since then, the plugin
ships its schema and the user-invoked `gtd-setup` skill, which creates or
binds a GTD database through the connected route.
[ADR 0004](0004-ship-the-gtd-schema.md) records the decision. Imports,
synchronization and credential changes remain separate work. See
[#403](https://github.com/aeghnnsw/cc-toolkit/issues/403).
