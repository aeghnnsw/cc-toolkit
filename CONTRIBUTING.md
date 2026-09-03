# Contributing to cc-toolkit

cc-toolkit uses one repository for development and plugin distribution.
Contributor documentation lives at the root and under `docs/`; installable
components live inside each plugin directory. Follow
[CLAUDE.md](CLAUDE.md) for the issue, worktree, and PR workflow.

## Repository and package boundaries

The Claude Code and Codex marketplace registries select plugin directories
such as `dev-skills/` and `core-hooks/`. Each directory contains that
plugin's manifests, components, and supporting resources. Keep resources
needed by an installed plugin inside its directory.

Root documents describe how to maintain this repository. They remain
public in the source checkout, but are outside the plugin directories
selected by the registries. Installing a plugin does not require adopting
cc-toolkit's contributor workflow or installing the tools used to develop it.

Keep development and publishing in this repository. Use branches and
worktrees for changes and the host-specific manifests for plugin releases.
A root documentation change does not require changing plugin versions.

## What belongs in Git

Classify a file by its purpose and expected lifetime, regardless of whether
a person or an agent wrote it.

| Material | Location and treatment |
| --- | --- |
| Installable skills, agents, hooks, scripts, and required resources | Commit inside the owning plugin directory. |
| Shared contributor instructions and agent configuration | Commit `CLAUDE.md`, its `AGENTS.md` symlink, and `docs/agents/`. |
| Accepted architecture decisions | Commit concise records under `docs/adr/`. |
| Agreed domain terminology | Commit a root `CONTEXT.md` when a glossary is needed. |
| Durable designs and review conclusions | Commit under a relevant `docs/` directory and link them from the issue or relevant documentation. |
| Disposable notes, trial output, and intermediate reports | Use `.scratch/`, which is ignored. Promote useful conclusions into shared documentation. |
| Logs, caches, local worktrees, and generated binaries | Keep out of Git using the shared `.gitignore`. |
| Personal tool settings and local-only notes | Keep outside the repository or exclude specific paths locally. |

Before committing generated documentation, check its claims against the
current project, remove unused template assumptions, and add a pointer from
the relevant instructions. An installed development skill's configuration
belongs in Git when it expresses conventions shared by this repository.

Do not blanket-ignore `docs/`, `docs/agents/`, or `docs/adr/`. Git ignores
control tracking; they do not define which files belong in a plugin package.

## Local exclusions

Use `.gitignore` for paths every contributor should exclude. For personal
files in this checkout, edit the Git common directory's `info/exclude` file;
it is local and is shared by linked worktrees. Locate it with:

```bash
git rev-parse --path-format=absolute --git-path info/exclude
```

Use exact file paths or a dedicated personal directory. Prefer putting
machine-specific agent preferences in the host's user configuration so
shared repository instructions remain portable. Ignore rules do not hide
changes to files already tracked by Git.

See [Git's ignore documentation](https://git-scm.com/docs/gitignore) for the
scope of local and shared exclusions.

## Verification

There is no repository-wide build or lint command. Verification depends on
what changed:

- **Documentation:** check accuracy, relative links, referenced paths, and
  whitespace with `git diff --check`.
- **Skills and metadata:** check skill frontmatter and resource paths;
  parse affected manifests and marketplace registries as JSON. Confirm
  registered source directories exist.
- **Executable code:** run the tests for the affected plugin. Core Hooks
  tests require Python and `uv` on `PATH`; task-loop CLI tests require
  Python 3.11+ and `httpx>=0.27` as declared by the CLI. The command below
  supplies that dependency through `uv`.
- **GitHub Actions:** validate edited workflow YAML and check its triggers
  and permissions against the intended behavior.

Run the existing Python suites from the repository root:

```bash
python3 -m unittest discover -s core-hooks/tests -p 'test_*.py'
uv run --no-project --python '>=3.11' --with 'httpx>=0.27' python -m unittest discover -s task-loop/tests -p 'test_*.py'
```

Keep validation proportional to the change. Documentation-only changes
normally need the documentation and configuration checks above.
