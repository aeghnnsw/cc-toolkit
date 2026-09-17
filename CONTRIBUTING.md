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
  run the package and release validator described below.
- **Executable code:** run the tests for the affected plugin. Core Hooks
  tests require Python and `uv` on `PATH`; task-loop CLI tests require
  Python 3.11+ and `httpx>=0.27` as declared by the CLI. The command below
  supplies that dependency through `uv`.
- **GitHub Actions:** validate edited workflow YAML and check its triggers
  and permissions against the intended behavior.

### Package and release validation

Run this read-only command from the repository root with Python 3.11 or
newer. It uses only the standard library and installs no dependencies:

```bash
python3 scripts/validate_packages.py --base origin/master
```

`--base` accepts the target branch ref or a commit SHA. The validator finds
its merge base with `HEAD`. Local validation includes staged edits,
unstaged edits, and new files that Git does not ignore. It checks the
resulting working tree. It does not select versions or change files.

The target ref and enough history to find the merge base must exist
locally. Run `git fetch origin master` to update the usual target. For a
shallow checkout, fetch the missing history before retrying. An unavailable
ref or merge base fails validation with a correction message. The validator
does not fetch history or skip release checks.

Package validation checks all registered plugins, their JSON metadata,
declared local paths, and explicitly required resources. It resolves
symlinks to check package containment. Required paths must be tracked or
new files that Git does not ignore. Ignored local files cannot satisfy the
package contract. Optional discovery roots remain
optional. Discovered skills need `---` header delimiters and one nonempty,
single-line `name` and `description`. Names use lowercase letters, digits,
and single separating hyphens. This is a narrow skill header contract, not
full YAML validation. Agent headers do not use this contract. Declared JSON
hook and MCP files and listed TOML and JSON resources are parsed.
The validator does not check external links,
interpret paths in prose or shell examples, infer code dependencies, or
run plugins and host loaders.

Release validation compares both package layouts across the merge base.
Changed shipped content requires a greater numeric `major.minor.patch`
version for each affected existing host registration. One increase covers
the whole pull request. New registrations need a valid initial version.
Removed registrations need no increase for the removed host. A source move
preserves release history by plugin identity and host.

[package-validation.json](package-validation.json) holds the ownership
exceptions, required resources, and contributor-only exemptions. Update
these rules when a package needs an explicit local contract. Plugin-root
tests, `README.md`, and `CHANGELOG.md` are exempt by default. Required
resources override exemptions. Markdown files are not exempt by extension.
Unclassified plugin files affect all registered hosts. Failure diagnostics
identify the relevant path or package and host. Version failures include
the ownership reason and the version that must be exceeded. Fix the first
reported error and rerun the command. The result includes elapsed execution
time. See the [design](docs/design/package-validation.md) for the rule schema
and ownership precedence. Terms are defined in [CONTEXT.md](CONTEXT.md).

The [pull-request workflow](.github/workflows/package-validation.yml) runs
the same command against the exact pull-request head and target SHA. It
fetches the comparison history and runs one job with read-only repository
permission. Changes limited to root contributor documents or `docs/` skip
the job. Other paths remain eligible, including new plugin source
directories. The job uses the runner's Python and runs no plugin runtime
suites. The speed target is less than 10 seconds of validator execution;
queue, checkout, and runner startup time are separate.

Run the validator's command-interface fixtures when changing its behavior:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

### Plugin runtime tests

Run the existing Python suites from the repository root:

```bash
python3 -m unittest discover -s core-hooks/tests -p 'test_*.py'
python3 -m unittest discover -s pymol-skills/tests -p 'test_*.py'
uv run --no-project --python '>=3.11' --with 'httpx>=0.27' python -m unittest discover -s task-loop/tests -p 'test_*.py'
```

The PyMOL startup suite requires `uv` and access to download missing script
dependencies. It checks MCP initialization and tool discovery without changing
the PyMOL scene. A running PyMOL instance is not required.

Keep validation proportional to the change. Documentation-only changes
normally need the documentation and configuration checks above.
