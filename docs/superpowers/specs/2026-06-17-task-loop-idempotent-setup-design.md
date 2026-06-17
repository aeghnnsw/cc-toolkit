# Design - task-loop idempotent setup skills

Issue: #148

## Goal

Update both task-loop setup skills so they first check whether the machine and
current repo are already configured for the hosted Supabase task board. If setup
is already valid, they should report that status and skip unnecessary setup
steps.

## Current Behavior

Both setup skills describe a mostly linear flow:

1. check tools and required skills;
2. create or reuse a Supabase project;
3. apply schema;
4. run `task-loop login`;
5. run `task-loop init`;
6. run an `add/status/close` smoke test.

That flow works for a new machine, but it does not clearly handle an already
configured machine and repo.

## CLI Semantics

`task-loop status` proves:

- task-loop credentials are available through env vars or local config;
- the Supabase REST endpoint is reachable;
- the schema is sufficiently present for the `tasks` query;
- the current git remote can be converted into an `owner/repo` project id.

It does not prove the project row exists, because it only queries `tasks`.

`task-loop init` is idempotent and upserts the current repo's project row. Use it
as the repo-registration check when full readiness is needed.

The smoke test (`add`, `status`, `close`) proves write access, schema functions,
and repo registration.

## Design

Add an early "Check existing setup first" section to both setup skills.

The check-first flow is:

1. Run the system tool checks (`uv --version`, and `gh auth status` for later
   loop readiness).
2. Run `uv run .../cli/task-loop status`.
3. If `status` succeeds:
   - report that machine credentials, Supabase connectivity, schema visibility,
     and git-remote project derivation are working;
   - skip Supabase project creation, schema application, and `login`;
   - run `uv run .../cli/task-loop init` when the user wants full readiness,
     because it is idempotent and ensures the repo row exists;
   - run the smoke test only if setup changed or the user asks for an
     end-to-end write proof.
4. If `status` fails:
   - if it reports `TASK_LOOP_URL` or `TASK_LOOP_KEY` missing, run `login`;
   - if it reports an HTTP/schema/table/function error, apply or re-apply
     `db/schema.sql`;
   - if it cannot derive the project from git remote, fix the remote or use the
     CLI `--project owner/repo` override;
   - after the fix, run `init`;
   - run the smoke test.

## File Changes

Update:

- `task-loop/skills/setup/SKILL.md`
- `task-loop/codex-skills/setup/SKILL.md`

Do not change the CLI in this issue. A future `doctor` command can provide a
more exact machine/schema/repo diagnostic if needed.

## Runtime-Specific Notes

The Claude setup skill keeps its Agent Teams section and
`${CLAUDE_PLUGIN_ROOT}` command paths.

The Codex setup skill stays setup/preflight only and keeps Codex command paths.
It must not introduce Claude-only terms.

## Acceptance Criteria

- Both setup skills include the check-first flow before setup steps.
- Both setup skills say successful `status` skips project creation, schema
  application, and `login`.
- Both setup skills explain that `init` is idempotent and is the repo readiness
  check.
- Both setup skills reserve the smoke test for changed setup or explicit proof.
- Existing CLI behavior is unchanged.
- Codex setup skill still validates and stays concise.
