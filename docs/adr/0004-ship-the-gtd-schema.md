# Ship the GTD schema and a setup skill

The five GTD skills used a Supabase database that the plugin could not
create. The only schema was a test fixture, and
[ADR 0003](0003-use-connected-supabase-for-gtd.md) left new database setup
as separate work. The plugin now ships one schema file and the user-invoked
`gtd-setup` skill. The skill applies the schema through the connected route
and writes the GTD binding. Only a person starts it, so a capture request
never creates a project. The contract tests create their database from the
shipped file, so the tested schema and the shipped schema cannot differ.

The owner is a plain UUID. Setup generates it for a new database and creates
no Supabase Auth user. The renderer and the transaction scope each operation
to the owner in the GTD binding and never read an Auth identity, so an Auth
user would add an account in a second system with no effect on access.

The schema has three tables: `gtd_items`, `gtd_links`, and `gtd_requests`.
They hold only the columns, keys, and checks that the shipped renderer and
transaction use. The snapshot table, the source columns, and the source
trigger are optional migration records. They belong to a database that was
migrated from the native workflow, and routine use preserves them there.

Row-level security is enabled on each table with no policy, and no public
role gets a grant. The connected route runs as a database role that bypasses
row-level security, and the plugin ships no browser access. Each other role,
including the roles of the public Data API, therefore reads and writes
nothing.

Rejected alternative: ship the four-table shape of the first database, with
its browser Auth parts: policies for the `authenticated` role, which need
an Auth user as the owner, and functions for browser calls. A new user would
create an Auth user and get policies and functions that no shipped skill
uses or tests. The
snapshot table and the source columns would stay empty in each database that
was not migrated.

Consequences:

- Setup never repairs a partial schema and builds no schema upgrade
  procedure. The schema file is safe to apply more than one time.
- A connector role that cannot bypass row-level security cannot use the
  tables. Setup checks the role and reports this state.
- Browser access needs a new decision, with policies and an owner identity
  that the browser session can prove.

See [#403](https://github.com/aeghnnsw/cc-toolkit/issues/403) and the shipped
[schema](../../productivity-skills/references/gtd-schema.sql).
