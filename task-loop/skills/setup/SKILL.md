---
name: setup
description: This skill should be used when the user asks to "set up task-loop", "configure the Supabase backend", "connect the task-loop database", "save Supabase credentials", "onboard a repo to task-loop", "check existing task-loop setup", "check task-loop prerequisites", "verify task-loop dependencies", "enable agent teams", "preflight", or otherwise prepare a machine/repo to run the task-loop harness. It checks existing machine/repo setup first, then walks through missing Supabase, credential, repo-registration, Agent Teams, and required-skill setup only as needed.
---

# Task-loop setup

Onboards a user/machine/repo to the task-loop harness. The harness stores all task
state in **the user's own hosted Supabase project** (one project shared across all
their repos); the plugin ships only code (`db/schema.sql` + `cli/task-loop`). Nothing
secret lives in the plugin or in git.

Setup happens at three granularities, each done once:

| Layer | Once per… | Action |
|---|---|---|
| Supabase project + schema | **account** | create a project, apply `db/schema.sql` |
| credentials (`URL` + `KEY`) + Agent Teams | **machine** | `task-loop login` (0600); enable `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` (Step 7) |
| repo registration | **repo** | `task-loop init` |

(The required plugin *skills* — Step 0 — are session/project state, re-checked every run by `run-cycle`'s preconditions, not just here.)

`${CLAUDE_PLUGIN_ROOT}` is the installed plugin path; in this repo the files are
`task-loop/cli/task-loop` and `task-loop/db/schema.sql`.

## Step 0 — Prerequisites

- **`uv`** (runs the CLI; the CLI is a single `uv run` script with inline deps). Verify `uv --version`.
- **`gh`**, authenticated (`gh auth status`) — the orchestrator uses it for PRs/merges. Not needed for the CLI itself, but required to run the loop later.
- **Required plugin skills** — the harness invokes 8 skills from two plugins; install both (via `/plugin`):
  - **`superpowers`** — `brainstorming`, `writing-plans`, `test-driven-development`,
    `verification-before-completion`, `receiving-code-review`.
  - **`dev-skills`** — `discuss-with-codex`, `goal-rubric`, `doc-update`.

  A skill is loadable iff it appears in the session's available-skills list (match the
  `plugin:skill` name, owner-verified — a same-named personal skill is not the dependency).
  `specify-aims` / `create-cycle` need these; `run-cycle` re-checks them every session before
  dispatching (Step 7 enables what `run-cycle` also needs).

## Step 1 — Check existing setup first

Before walking through setup, check whether this machine and repo already work:

```
uv run ${CLAUDE_PLUGIN_ROOT}/cli/task-loop status
```

If `status` succeeds, report that:
- machine credentials are available (env vars or the local config file);
- Supabase REST connectivity works;
- the schema is visible enough for the `tasks` query;
- the current git remote can be derived as the task-loop project id.

Then skip Supabase project creation, schema application, and `task-loop login`.
For full repo readiness, still run the idempotent repo registration check:

```
uv run ${CLAUDE_PLUGIN_ROOT}/cli/task-loop init
```

`init` upserts this repo's `projects` row, so it is safe to run even when the repo
is already registered. Run the smoke test in Step 6 only if setup changed or the
user asks for end-to-end write proof.

If `status` fails, use the failure to choose the missing setup path:
- `TASK_LOOP_URL` or `TASK_LOOP_KEY` missing → run Step 4 (`login`).
- HTTP errors, missing relations, missing functions, or schema-looking failures → run Step 3.
- Cannot derive the project from git remote → fix the repo remote or use the CLI `--project owner/repo` override.

After fixing the reported gap, run Step 5 (`init`) and then Step 6 (smoke test).

## Step 2 — Supabase project (once per account)

If the user has no project yet:
1. Create a project at https://supabase.com (the free tier is fine). This is the
   user's own account/infra — they must do the browser steps.
2. From the project dashboard, collect:
   - **Project URL** — Settings → API → *Project URL* (`https://<ref>.supabase.co`).
   - **API key** — Settings → API. Use the **service_role** key for a trusted
     single-operator setup, or the **anon** key plus RLS policies for stricter scoping.
     Treat it as a secret.

If they already have a shared task-loop project, reuse its URL + key — do **not** make a new one.

## Step 3 — Apply the schema (once per project)

PostgREST (the REST API the CLI uses) cannot run DDL, so the schema is applied once,
out-of-band:
- Open the project's **SQL Editor**, paste the full contents of `db/schema.sql`, and run it. It is idempotent (`create … if not exists`), so re-running is safe.
- (Alternative) with the Supabase CLI or `psql` and the project's connection string:
  `psql "$CONNECTION_STRING" -f db/schema.sql`.

This creates `projects` + `tasks`, the `claimable` view, and the `task_add` / `task_claim` functions.

## Step 4 — Save credentials (once per machine)

```
uv run ${CLAUDE_PLUGIN_ROOT}/cli/task-loop login
```
It prompts for the Project URL and the API key (hidden) and writes them to
`$XDG_CONFIG_HOME/task-loop/config` (default `~/.config/task-loop/config`) at mode 0600.
The CLI reads credentials env-first (`TASK_LOOP_URL` / `TASK_LOOP_KEY`), then this file.

Skip this step when Step 1 `status` already succeeds unless the user wants to rotate credentials.

## Step 5 — Register the repo (once per repo)

From inside the repo (the project id is auto-derived from `git remote get-url origin`):
```
uv run ${CLAUDE_PLUGIN_ROOT}/cli/task-loop init
```
Upserts this repo's `projects` row. Repeat in each repo that uses task-loop. This command is
idempotent; run it after successful Step 1 when the user wants full repo readiness.

## Step 6 — Verify

```
uv run ${CLAUDE_PLUGIN_ROOT}/cli/task-loop add "setup smoke test"   # prints e.g. 001
uv run ${CLAUDE_PLUGIN_ROOT}/cli/task-loop status                   # lists the task
uv run ${CLAUDE_PLUGIN_ROOT}/cli/task-loop close 001                # closes it
```
A clean `add → status → close` confirms the URL, key, schema, and repo registration are all good.
Run this smoke test when setup changed, when Step 1 failed and was fixed, or when the user asks for
end-to-end write proof. If Step 1 succeeded and no setup changed, the smoke test is optional.

## Step 7 — Enable Agent Teams (once per machine; needed by `run-cycle`)

`run-cycle` spawns `cycle-worker` **teammates**, which require **experimental Agent Teams** (off by
default) and Claude Code **≥ v2.1.32**. `specify-aims` / `create-cycle` do **not** need it.

**Source of truth = `~/.claude/settings.json`** (machine-wide). Guarded write:
1. **Read** it. If it does **not** parse as a JSON object, or `env` exists but is not an object,
   **stop** and report what to fix — never edit malformed config.
2. **Absent** → `Write` `{ "env": { "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1" } }`.
3. **Valid object** → `Edit` to add/replace **only** the `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` key
   inside `env` (create `env` only if absent); value is the **string `"1"`**, not `1`; preserve every
   other key.
4. A just-written setting needs a **session restart** to take effect.

Report `claude --version` (must be ≥ v2.1.32 — tell the user to update if older).

## Notes

- **The Supabase MCP is not required.** Setup and the running harness use only the REST `URL` + `KEY`. If the Supabase MCP happens to be connected it can optionally run the schema for you (it can execute DDL, which the REST API cannot), but it is never a dependency — when in doubt, apply the schema via the SQL editor (Step 3).
- **Per-account / per-machine / per-repo** are independent: a new machine repeats Steps 4 + 7 (and confirms Step 0 skills); a new repo only repeats Step 5.
- The key is a machine-local 0600 secret — never commit it, never put it in `settings.json`.
- Setup is standalone; it is not part of the `specify-aims → create-cycle → run-cycle` workflow.
