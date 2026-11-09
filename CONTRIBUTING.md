# Contributing to cc-toolkit

cc-toolkit uses one repository for development and plugin distribution.
Contributor documentation lives at the root and under `docs/`; installable
components live inside each plugin directory. Follow
[CLAUDE.md](CLAUDE.md) for the issue, worktree, and PR workflow.

## Coding standards

No repository-wide linter, formatter, or type checker is configured. Follow
the surrounding code style. Do not reformat unrelated code.

Wrap ordinary prose in `CLAUDE.md` and `CONTRIBUTING.md` at 78 characters.
Exempt headings, tables, links, and code examples, including inline commands.
Other Markdown files follow their surrounding style.

Prefer the Python standard library for helpers. Preserve existing
standard-library-only entry points. The table below names the current
third-party Python dependencies. Keep runtime dependency declarations with
the plugin. Test dependencies are separate from runtime dependencies.

### Python requirements

These are declared minimum versions, not a tested compatibility matrix.
Where no minimum is declared, check the affected script and its caller
before using newer Python features. The root tooling's Python requirement
does not set the minimum for installed plugins.

| Component | Declared minimum | Python dependencies and exceptions |
| --- | --- | --- |
| [Root package validator](scripts/validate_packages.py), [retrospective helper](scripts/retro_sessions.py), and root tests | 3.11 | Standard library, including `tomllib`. |
| [Core Hooks](core-hooks/scripts/safety_guard.py) | 3.8 | Standard library, except [`chime` for sound notifications](core-hooks/scripts/system_notification.py). |
| [Productivity Skills: GTD SQL renderer](productivity-skills/scripts/gtd_sql.py) | 3.11 | Standard library. The connected Supabase tool executes the prepared SQL. |
| [Dev Skills: lean-tests](dev-skills/skills/lean-tests/SKILL.md) | 3.9 | CLI helpers use the standard library. Target test runs need `pytest`; coverage runs also need `pytest-cov` and `coverage`. |
| Other Dev Skills helpers and templates | No common minimum declared | Standard library. The [scientific project template](dev-skills/skills/sci-project-layout/templates/paths.py) uses Python 3.9 APIs. |
| [Creator Skills: slide linter](creator-skills/skills/sci-slides/SKILL.md) | 3.9 | Standard library. |
| [Doc Skills: PDF converter](doc-skills/skills/docling-pdf/scripts/convert_pdf.py) | 3.10 | `docling`, `docling-ibm-models`, `numpy<2`, `pillow`, `pypdfium2`, and `tabulate`. |
| [PyMOL Skills: MCP bridge](pymol-skills/pymol_mcp_server.py) | 3.10 | `mcp[cli]>=1.0.0,<2`. |
| [Retained task-loop code](task-loop/cli/task-loop) (retired plugin) | 3.11 | The CLI needs `httpx>=0.27`; hooks and sync helpers use the standard library. |

The PyMOL socket plugin runs in PyMOL's own interpreter. It has no declared
minimum; the bridge requirement does not apply to that separate process.
Productivity Skills also uses Swift for native Calendar and Reminders.
CC Customize uses Bash and `jq`, with Git for status information.
See [Verification](#verification) for test commands and test prerequisites.

## Repository and package boundaries

The Claude Code and Codex marketplace registries select plugin directories
such as `dev-skills/` and `core-hooks/`. Each directory contains that
plugin's manifests, components, and supporting resources. Keep resources
needed by an installed plugin inside its directory.

- Edit the plugin directory in this repository, not an installed copy under
  `~/.claude/plugins/cache/` or `~/.codex/plugins/cache/`.
- When you add, remove, or rename a plugin, or change its source path,
  update the marketplace registries: `.claude-plugin/marketplace.json` for
  Claude Code and `.agents/plugins/marketplace.json` for Codex.
- When you add, remove, or rename a plugin or a skill, update its entries in
  [README.md](README.md).
- Before you change component paths, read the plugin's host-specific
  manifests and [host ownership](docs/design/package-validation.md#host-ownership).

### Skills for both hosts

A skill that ships to Claude Code and Codex has one copy per host:
`skills/<name>/` and `codex-skills/<name>/`. Change both copies in the same
pull request. Keep differences host-specific, such as tool names,
invocation, and plugin-root paths.

For an example pair, see `creator-skills/skills/sci-slides/` and
`creator-skills/codex-skills/sci-slides/`. The test
`creator-skills/tests/test_sci_slides.py` compares the two copies. A new
skill also needs an entry in both [README.md](README.md) lists of its
plugin: **Skills:** with a one-line description, and **Codex skills:** with
its name. When the Codex manifest's `interface.longDescription` describes
the purposes of the plugin's skills, add the purpose of the new skill. When
a change alters the purpose of a skill, update that purpose in
`longDescription` and in the README **Skills:** line.

- **Frontmatter.** Claude copies carry `name`, `description`, and usually
  `version`. Codex copies carry only `name` and `description`. Run the
  skill-creator validator on Codex copies only. Its command is in
  [Verification](#verification).
- **Invocation policy.** To make a skill user-invoked, set
  `disable-model-invocation: true` in the Claude frontmatter, and
  `allow_implicit_invocation: false` under `policy:` in the Codex copy's
  `agents/openai.yaml`. A Codex copy without that file is not user-invoked.
- **Shell blocks.** A skill's shell blocks run in the user's shell, which
  can be bash or zsh. Write each block to run in both shells. For a test
  that runs a skill's blocks in bash and zsh, see
  `dev-skills/tests/test_pressure_test_models.py`.
- **Paths.** A link relative to `SKILL.md` reads the same in both copies. A
  plugin-root path differs: `${CLAUDE_PLUGIN_ROOT}/...` in the Claude copy
  and `<plugin-root>/...` in the Codex copy. A command that runs a file
  inside the skill directory can write `<skill-dir>/...`, which reads the
  same in both copies.
- **Registration.** List each file that a skill links to or runs under the
  plugin's `resources` in `package-validation.json`, once per host that
  ships it. A link to a `SKILL.md` that the same host discovers needs no
  entry. The validator requires only listed resources; it does not find
  them from links in prose. The skill link test,
  [tests/test_skill_links.py](tests/test_skill_links.py), enforces this
  rule. It also checks that each link target exists in the plugin and each
  anchor matches a heading.

### Argument placeholders

Claude Code replaces `$N`, `$ARGUMENTS`, and the argument names that the
`arguments` frontmatter declares in a skill or command body, including code
blocks. Codex does not replace them. `tests/test_skill_placeholders.py`, one
of the [root tests](#package-and-release-validation), fails on each
unescaped placeholder and prints the fix.

## Repository search

From the repository root, search with `git grep`. It skips untracked files
and the other worktrees under `trees/` and `.claude/worktrees/`; pass
`--untracked` to include new files.

The entries in `CHANGELOG.md` can describe replaced behavior. The
`task-loop/` folder is
[not in the marketplaces](task-loop/README.md#status), but its copies of
shared skills match many terms. To search current text only, exclude both:

```bash
git grep -n <term> -- ':!CHANGELOG.md' ':!task-loop'
```

## Changelog entries

The root [CHANGELOG.md](CHANGELOG.md) is the only maintained changelog.
Add each entry under `## [Unreleased]`, in `### Added`, `### Removed`,
or `### Changed`. Put the newest entry first.

Use this form:

```text
- <plugin> (<Host> <version>): <change>. See [#N](https://github.com/aeghnnsw/cc-toolkit/issues/N).
```

When both hosts ship the same version, write
`Claude Code and Codex <version>`. When the versions differ, write
`Claude Code <version>, Codex <version>`. Start a change outside the
plugin directories with `Repository:` and give no version. The plugin entry
also covers the README catalog entry and the `package-validation.json`
lines that ship with the plugin change. When a pull request changes a
plugin and other files outside it, write one plugin entry and one
`Repository:` entry. A change only to contributor-only files of a
plugin, such as its `tests/`, needs no version and is also a `Repository:`
entry. Link the issue that the pull request closes; for a spec with
tickets, link the ticket.

When a rebase makes `CHANGELOG.md` conflict, keep both entries, and put
the entry of the rebased branch first.

## What belongs in Git

Classify a file by its purpose and expected lifetime, regardless of whether
a person or an agent wrote it.

| Material | Location and treatment |
| --- | --- |
| Installable skills, agents, hooks, scripts, and required resources | Commit inside the owning plugin directory. |
| Shared contributor instructions and agent configuration | Commit `CLAUDE.md`, its `AGENTS.md` symlink, and `docs/agents/`. |
| Accepted architecture decisions | Commit concise records under `docs/adr/`. |
| Agreed domain terminology | Commit a root `GLOSSARY.md` when a glossary is needed. |
| Durable designs and review conclusions | Commit under a relevant `docs/` directory and link them from the issue or relevant documentation. |
| Disposable notes, trial output, and intermediate reports | Use `.scratch/`, which is ignored. Name a planning folder `.scratch/<issue>-<slug>/`, and keep it in the main checkout, because worktree cleanup removes the ignored files of a worktree. Promote useful conclusions into shared documentation. |
| Logs, caches, local worktrees, and generated binaries | Keep out of Git using the shared `.gitignore`. |
| Personal tool settings and local-only notes | Keep outside the repository, or list exact paths in the file that `git rev-parse --path-format=absolute --git-path info/exclude` prints; linked worktrees share it. Prefer putting machine-specific agent preferences in the host's user configuration so shared repository instructions remain portable. |
| Private GTD account bindings and migration records | Keep outside this repository. |

When a change supersedes part of a design, plan, conclusion, or ADR under
`docs/`, add a superseded note at its top. Name the date and the issue, and
link the replacement. In an ADR, also mark each replaced sentence and record
the new rule with its reason in a new section; see ADR 0002 for an example.
A change that only adds facts needs no note.

## Verification

Run these checks locally before opening a pull request. This repository
does not use CI. There is no repository-wide build command. Run every row
that matches your change from the repository root:

| Change | Check |
| --- | --- |
| Any change | `git diff --check` |
| Documentation | Check accuracy, relative links, and referenced paths. |
| A skill | Check its frontmatter and invocation guidance. |
| A plugin file, a marketplace registry, `package-validation.json`, or the validator | `uv run --no-project --python '>=3.11' python scripts/validate_packages.py --base origin/master` |
| A skill, an agent, a root Python helper or test, `allowed-models.json`, or `package-validation.json` | `uv run --no-project --python '>=3.11' python -m unittest discover -s tests -p 'test_*.py'` |
| A Codex copy of a skill | `uv run --no-project --with pyyaml python "${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py" <plugin>/codex-skills/<name>` |
| `allowed-models.json` or a `pressure-test` `SKILL.md` | `python3 -m unittest discover -s dev-skills/tests -p 'test_*.py'` |
| Code or a test in `core-hooks`, `creator-skills`, `dev-skills`, or `pymol-skills` | `python3 -m unittest discover -s <plugin>/tests -p 'test_*.py'` |
| Code or a test in `productivity-skills` | `uv run --no-project --python '>=3.11' python -m unittest discover -s productivity-skills/tests -p 'test_*.py'` |
| Code or a test in `task-loop` | `uv run --no-project --python '>=3.11' --with 'httpx>=0.27' python -m unittest discover -s task-loop/tests -p 'test_*.py'` |
| A GitHub Actions workflow | Validate the YAML. Check its triggers and permissions against the intended behavior. |

Core Hooks tests require Python and `uv` on `PATH`. `cc-customize` and
`doc-skills` have no test suite. Before you run a plugin suite, read
[Plugin runtime tests](#plugin-runtime-tests).

### Package and release validation

Run the package validator for the changes that the
[Verification](#verification) table lists, and again after a rebase. Run
`git fetch origin master` first. The command is read-only:

```bash
uv run --no-project --python '>=3.11' python scripts/validate_packages.py --base origin/master
```

Shipped changes need a greater plugin `version` in each affected host's
manifest, and a greater skill `version` when the skill has one. The
[package validation design](docs/design/package-validation.md) describes
each check, the rules in [package-validation.json](package-validation.json),
and the error messages.

The root tests are under `tests/`; [Verification](#verification) gives when
and how to run them.

### Plugin runtime tests

The table in [Verification](#verification) gives the command for each suite.

The `productivity-skills` suite needs `uv`, which supplies Python 3.11+,
`swiftc`, and PostgreSQL tools (`initdb`, `pg_ctl`, and `psql`).

The `dev-skills` suite takes about 2 minutes, most of it in
`dev-skills/tests/test_codex_critic.py`.

The lean-tests checks in `dev-skills/tests/test_lean_tests.py` that run
pytest need pytest and pytest-cov. Under a `python3` without them, these
checks skip; their skip reason, which `-v` shows, gives the command.

The PyMOL startup suite requires `uv` and access to download missing script
dependencies. It checks MCP initialization and tool discovery without changing
the PyMOL scene. A running PyMOL instance is not required.

To replay one Core Hooks policy check, write a hook payload to
`.scratch/payload.json`. A hook payload is the JSON that the host sends to
a hook before a tool runs, for example:

```json
{"tool_name": "Bash", "tool_input": {"command": "git status"}}
```

Then run a policy script on the payload. `pre_git_hook.py` checks git
policy, and `safety_guard.py` checks `rm`, `env`, and `printenv` commands.
Exit status 2 means the policy script blocks the command:

```bash
python3 core-hooks/scripts/pre_git_hook.py < .scratch/payload.json
```
