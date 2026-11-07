# Use the connected Supabase route for GTD

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
Shared project-status policy interprets human readiness and waiting evidence;
it does not turn free-form notes into a required database state format.

See [#117](https://github.com/aeghnnsw/cc-toolkit/issues/117), implementation
[#382](https://github.com/aeghnnsw/cc-toolkit/issues/382), and the shipped
[cloud workflow](../../productivity-skills/references/gtd-cloud.md).
