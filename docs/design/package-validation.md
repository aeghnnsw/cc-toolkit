# Package and release validation

Tracked in [issue #206](https://github.com/aeghnnsw/cc-toolkit/issues/206),
with delivery in [#207](https://github.com/aeghnnsw/cc-toolkit/issues/207),
[#208](https://github.com/aeghnnsw/cc-toolkit/issues/208), and
[#209](https://github.com/aeghnnsw/cc-toolkit/issues/209).
Terms are defined in [CONTEXT.md](../../CONTEXT.md).

## Purpose and constraints

Package validation checks the declared local contract of every registered
plugin. Release validation checks version increases for affected hosts.
Both checks run read-only, locally and on pull requests. Contributors choose
versions and make corrections. Deterministic errors fail the command.

Validation uses Python 3.11 or newer and the standard library. It inspects
repository files and Git changes. It installs no dependencies and runs no
plugin code. The speed target is less than 10 seconds of validator execution.
Queue, checkout, and runner startup time are separate.

Plugin packages remain self-contained. Host manifests, versions, and
independent discovery roots follow
[ADR 0001](../adr/0001-isolate-host-adapter-discovery.md).

## Module and interface

[The validator](../../scripts/validate_packages.py) contains the Claude Code
and Codex registry and manifest adapters in one repository-owned module.
The local interface is one command from the repository root:

```bash
python3 scripts/validate_packages.py --base origin/master
```

`--base` names the target ref or SHA. The module resolves its merge base
with `HEAD`. Local checks inspect the resulting working tree, including
staged edits, unstaged edits, and new files that Git does not ignore.
CI checks the exact pull-request head against the target SHA.

An unavailable target ref or merge base causes an actionable error. The
validator does not fetch history or skip release validation. Contributors
fetch enough target history before retrying. The command reports the first
failure and returns a nonzero status. Package errors identify the relevant
path or registration. Release errors identify the plugin, host, changed
path, ownership reason, and base version that must be exceeded. Successful
and failed runs report elapsed execution time.

## Host ownership

Ownership follows declared host roots and discovery conventions, with
explicit exceptions in [package-validation.json](../../package-validation.json).
The rules include these shared and host-specific resources:

| Resource | Affected host |
| --- | --- |
| `task-loop/codex-agents/` | Codex |
| `task-loop/hooks/` | Codex |
| `task-loop/scripts/sync_codex_agents.py` | Codex |
| `core-hooks/hooks/hooks.json` | Claude Code |
| `core-hooks/hooks/hooks.codex.json` | Codex |
| Core Hooks and Productivity Skills shared scripts | Both |
| Task-loop CLI, database schema, and shared references | Both |

An ownership rule affects only registered hosts. An unclassified file inside
a plugin affects all its registered hosts. Release diagnostics include
that reason. Contributors add a precise rule when a file belongs to one
host or is contributor-only.

Tests and contributor-only files use explicit exemptions. Markdown is not
exempt by extension: skill references and templates are shipped content.
Plugin-root `README.md` and `CHANGELOG.md` are exempt unless an explicit
resource or ownership rule includes them.

### Rule schema and precedence

The JSON configuration stays outside installed plugins. All rule paths are
relative to the owning plugin directory. Absolute paths and `..` components
are invalid. A path matches itself; a trailing `/` also matches descendants.
Patterns are literal paths, not globs.

| Field | Value |
| --- | --- |
| `version` | Schema version `1`. |
| `defaults.exempt` | List of contributor-only paths for all plugins. Current defaults are `tests/`, `README.md`, and `CHANGELOG.md`. |
| `plugins` | Object keyed by registered plugin name, independent of its source directory. |
| `plugins.<name>.exempt` | Additional contributor-only path list. |
| `plugins.<name>.ownership` | List of objects with `path` and a nonempty `hosts` list. Hosts are `claude`, `codex`, or both. |
| `plugins.<name>.resources` | The same object shape, for required local resources and their owning hosts. |

Classification uses required-resource rules first, then ownership rules,
then exemptions, then inferred host paths. The longest matching path wins
within each explicit rule list. Unknown paths affect all registered hosts.
Required resources therefore take precedence over contributor exemptions.
An ownership entry classifies changes; a resource entry also requires that
path to exist for its registered hosts.

## Package checks

The command validates all current registrations in both marketplace
registries. It parses registry and manifest JSON and checks names, duplicate
registrations, source directories, and numeric three-part versions.

It checks declared paths and explicitly listed resources. Symlink resolution
must keep paths inside the plugin package. Required paths must be tracked or
new files that Git does not ignore. Ignored local files cannot satisfy the
package contract. Optional roots remain optional;
a hooks-only plugin does not need skills.

Discovered skills require header delimiters and one nonempty, single-line
`name` and `description`. Duplicate required fields and invalid names fail.
Names contain lowercase letters and digits, with single hyphens between
segments. A skill-level version is not required. These checks define a
narrow repository contract. They do not provide full YAML validation or
apply to agent headers with lists and multiline examples.

Explicitly listed agent resources must exist. Listed TOML resources are
parsed with the standard library. Declared JSON hook and MCP files and
listed JSON resources are parsed as JSON.
The command does not check external links, run host loaders, interpret
arbitrary paths in prose or shell examples, or infer dependencies from
source code. It proves only the declared local contract.

## Release checks

Changed paths are classified with both the base and proposed layouts and
rules. Additions, deletions, and renames count. A file removed from shipped
content still affects its former host when that registration remains.

Each affected existing registration needs a manifest version greater than
its base version. Versions use numeric `major.minor.patch` components.
An unchanged or lower version fails. A valid version-only increase is
allowed. One increase covers all changed content across the pull request.

A new plugin or host registration needs valid current packaging and a valid
initial version. It has no previous registered version to exceed. A removed
host registration needs no version increase for that host. Remaining
registrations are checked normally.

Source moves match by plugin identity and host, so they preserve release
history. Only changes since the selected merge base affect release checks.
Historical omissions do not create retroactive version requirements.

## Pull-request job

[The workflow](../../.github/workflows/package-validation.yml) runs one job
on relevant pull-request changes. It excludes root contributor documents
and `docs/` through `paths-ignore`. Other paths remain eligible, including
new plugin source directories, registries, rules, tests, and the validator.

Checkout selects the explicit head SHA with full history. A separate fetch
makes the explicit target SHA available. The same local command resolves
their merge base. The job has `contents: read`, a five-minute timeout, and
cancels superseded runs for the same pull request. It uses the runner's
Python and installs nothing. It runs no plugin runtime suites or live host
checks. Command output reports validator execution time.

## Adoption and verification

The repository adopts validation for all current packages without an
ignored-error baseline. Deterministic package defects require correction.
Substantial unrelated adoption repairs require a scope review.

[Command-interface fixtures](../../tests/test_validate_packages.py) use
temporary Git repositories. They check observable exit status, diagnostics,
and unchanged repository content. Coverage includes single-host, dual-host,
and hooks-only packages; invalid metadata; missing and escaped resources;
skill headers; shared and host-specific changes; exemptions; unknown files;
version rules; resource changes and source moves; registration lifecycle;
missing history; and staged, unstaged, and new files.

Run the fixture suite during validator development. Measure the command
against the actual repository before adoption. See
[contributor verification](../../CONTRIBUTING.md#verification) for commands
and the separate plugin runtime suites.
