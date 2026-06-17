---
name: setup
description: Use when setting up task-loop in Codex, checking existing task-loop setup, configuring Supabase, saving credentials, registering a repo, checking prerequisites, running preflight, or performing a setup smoke test.
---

# Task-loop Setup

Prepare this machine and repository for task-loop's hosted task board. This Codex skill supports setup and preflight only. `specify-aims`, `create-cycle`, and `run-cycle` are pending Codex ports.

## Preconditions

- Work from the repository root.
- Use the plugin checkout path when running commands in this repository: `uv run task-loop/cli/task-loop ...`.
- If task-loop is installed from the Codex plugin cache, first locate the installed plugin root and run `uv run <plugin-root>/cli/task-loop ...`.
- Never commit Supabase credentials. The CLI stores credentials in `$XDG_CONFIG_HOME/task-loop/config` or `~/.config/task-loop/config` with mode `0600`.

## Required Skills

Confirm these skills are available in the session before considering task-loop ready:

- `superpowers:brainstorming`
- `superpowers:writing-plans`
- `superpowers:test-driven-development`
- `superpowers:verification-before-completion`
- `superpowers:receiving-code-review`
- `dev-skills:pressure-test`
- `dev-skills:goal-rubric`
- `dev-skills:doc-update`

If any are missing, report the missing skill names and stop after completing any requested setup checks. Do not claim full task-loop readiness.

## System Tools

Run:

```bash
uv --version
gh auth status
```

If `uv` is missing, stop and ask the user to install it. If `gh` is missing or unauthenticated, setup can save task-loop credentials but the later loop cannot run GitHub work.

## Check Existing Setup First

Before walking through setup, check whether this machine and repo already work:

```bash
uv run task-loop/cli/task-loop status
```

If `status` succeeds, report that:

- machine credentials are available through env vars or local config;
- Supabase REST connectivity works;
- the schema is visible enough for the `tasks` query;
- the current git remote can be derived as the task-loop project id.

Then skip Supabase project creation, schema application, and `login`.
For full repo readiness, still run the idempotent repo registration check:

```bash
uv run task-loop/cli/task-loop init
```

`init` upserts this repo's `projects` row, so it is safe to run even when the repo is already registered. Run the smoke test only if setup changed or the user asks for end-to-end write proof.

If `status` fails, use the failure to choose the missing setup path:

- `TASK_LOOP_URL` or `TASK_LOOP_KEY` missing: run `login`.
- HTTP errors, missing relations, missing functions, or schema-looking failures: apply or re-apply `task-loop/db/schema.sql`.
- Cannot derive the project from git remote: fix the repo remote or use the CLI `--project owner/repo` override.

After fixing the reported gap, run `init`, then run the smoke test.

## Supabase Project

Task-loop uses the user's hosted Supabase project. If the user does not already have one, have them create it in the Supabase dashboard and collect:

- Project URL
- API key

For a trusted single-operator setup, use the `service_role` key. Treat the key as a secret.

## Apply Schema

Apply `task-loop/db/schema.sql` once per Supabase project. The REST CLI cannot run DDL, so use the Supabase SQL Editor, Supabase CLI, or `psql`:

```bash
psql "$CONNECTION_STRING" -f task-loop/db/schema.sql
```

The schema is idempotent.

## Save Credentials

Skip this step when `status` already succeeds unless the user wants to rotate credentials.

Run:

```bash
uv run task-loop/cli/task-loop login
```

The CLI prompts for the Project URL and API key and writes a local `0600` config file.

## Register Repository

Run this after new setup, after fixing a failed setup check, or after a successful `status` when the user wants full repo readiness. The command is idempotent.

From the repository root, run:

```bash
uv run task-loop/cli/task-loop init
```

The project id is derived from `git remote get-url origin`.

## Smoke Test

Run this when setup changed, when the setup check failed and was fixed, or when the user asks for end-to-end write proof. If `status` succeeded and no setup changed, this is optional.

Run:

```bash
uv run task-loop/cli/task-loop add "setup smoke test"
uv run task-loop/cli/task-loop status
uv run task-loop/cli/task-loop close <seq>
```

Replace `<seq>` with the sequence printed by `add`. The smoke test proves credentials, schema, and repo registration are working.

## Result

Report:

- tool checks run and their result;
- whether credentials were saved or already available;
- whether repo registration succeeded;
- smoke-test sequence and closure result;
- missing required skills, if any;
- that Codex task-loop support is currently setup/preflight only.
