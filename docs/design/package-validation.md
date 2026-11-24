# Package and release validation

> **Superseded in part (2026-11-23, issue
> [#298](https://github.com/aeghnnsw/cc-toolkit/issues/298)).** New changelog
> bullets go in entry files, and a new bullet in `CHANGELOG.md` fails. Read
> [CHANGELOG checks](#changelog-checks) and
> [ADR 0010](../adr/0010-use-entry-files-and-a-version-script.md).

Tracked in [issue #206](https://github.com/aeghnnsw/cc-toolkit/issues/206),
with delivery in [#207](https://github.com/aeghnnsw/cc-toolkit/issues/207),
[#208](https://github.com/aeghnnsw/cc-toolkit/issues/208), and
[#209](https://github.com/aeghnnsw/cc-toolkit/issues/209). Antigravity
support is tracked in [#426](https://github.com/aeghnnsw/cc-toolkit/issues/426).
Terms are defined in [GLOSSARY.md](../../GLOSSARY.md).

## Purpose and constraints

Package validation checks the declared local contract of every registered
plugin. Release validation checks plugin version increases for affected
hosts and skill version increases for changed skills.
Both checks run read-only on contributor machines, and in the
[CI workflow](../../.github/workflows/ci.yml) on each pull request.
Contributors choose versions and make corrections. Deterministic
errors fail the command.

Validation uses Python 3.11 or newer and the standard library. It inspects
repository files and Git changes. It installs no dependencies and runs no
plugin code. The speed target is less than 10 seconds of validator execution.

Plugin packages remain self-contained. Host manifests, versions, and
independent discovery roots follow
[ADR 0001](../adr/0001-isolate-host-adapter-discovery.md). The Antigravity
layout follows [ADR 0006](../adr/0006-antigravity-plugin-layout.md).

## Module and interface

[The validator](../../scripts/validate_packages.py) contains the Claude Code
and Codex registry adapters and the Claude Code, Codex, and Antigravity
manifest adapters in one repository-owned module.
The local interface is one command from the repository root:

```bash
uv run --no-project --python '>=3.11' python scripts/validate_packages.py --base origin/master
```

`--base` names the target ref or SHA. The module resolves its merge base
with `HEAD`. Local checks inspect the resulting working tree, including
staged edits, unstaged edits, and new files that Git does not ignore.

An unavailable target ref or merge base causes an actionable error. The
validator does not fetch history or skip release validation. Contributors
fetch enough target history before retrying. The command reports the first
failure and returns a nonzero status. Package errors identify the relevant
path or registration. Release errors identify the plugin, host, changed
path, ownership reason, and base version that must be exceeded. A skill
version error also identifies the skill and its `SKILL.md` path. Successful
and failed runs report elapsed execution time.

## Antigravity registration

This repository has no Antigravity marketplace registry. An entry in an
Antigravity marketplace registry needs an `https` source URL and a `sha256`
for each plugin, and Antigravity documents no way to add a third-party
marketplace registry. A plugin directory that the Claude Code or Codex
registry lists is an Antigravity registration when it holds
`.antigravity-plugin/plugin.json`. The registration uses the registered
name of the plugin. When the two registries give the directory different
names, the validator fails, because Antigravity needs one name.

The validator checks the Antigravity manifest:

- The manifest `name` equals the registered name.
- The `version` uses numeric `major.minor.patch` components. Antigravity
  accepts any string, but release validation compares versions.
- The manifest uses only the keys of the Antigravity manifest schema:
  `name`, `displayName`, `description`, `version`, `disabled`, `logo`,
  `suggestedPrompts`, `skills`, `author`, `homepage`, `repository`,
  `license`, `keywords`, and `extensions`. Antigravity ignores other keys.

The Antigravity discovery paths are the declared `skills` paths, `skills/`
only when the manifest declares no `skills` path, a root `hooks.json`, a
root `mcp_config.json`, `agents/`, and `rules/`. The manifest schema has no
path field for agents, hooks, or MCP servers, so those paths are fixed.

Antigravity always scans `skills/` and also loads the declared `skills`
paths. A same-named skill in a declared path replaces the skill in
`skills/`; this is shadowing. A skill that is only in `skills/` still loads.
So each skill folder in `skills/` of an Antigravity registration needs a
same-named skill in a declared `skills` path. Otherwise, the validator fails
with a message that names the skill and the expected folder. A declared
`skills` path that is `skills/` also fails, because then the Claude copies
load in Antigravity.

## Host ownership

Ownership follows declared host roots and discovery conventions, with
explicit exceptions in [package-validation.json](../../package-validation.json).
The rules include these shared and host-specific resources:

| Resource | Affected host |
| --- | --- |
| `core-hooks/hooks/hooks.json` | Claude Code |
| `core-hooks/hooks/hooks.codex.json` | Codex |
| `core-hooks/hooks.json` | Antigravity |
| `dev-skills/hooks/hooks.json` | Claude Code |
| `dev-skills/hooks/hooks.codex.json` | Codex |
| `dev-skills/hooks.json` | Antigravity |
| Core Hooks and Productivity Skills shared scripts | Every registered host |

For Antigravity, the inferred host paths are the `.antigravity-plugin/`
folder and the Antigravity discovery paths. When the manifest declares a
`skills` path, `skills/` does not affect Antigravity, because shadowing
replaces each skill in it. A path that two hosts discover, such as
`agents/`, affects both.

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
| `plugins.<name>.ownership` | List of objects with `path` and a nonempty `hosts` list. Each host is `claude`, `codex`, or `antigravity`. |
| `plugins.<name>.resources` | The same object shape, for required local resources and their owning hosts. |

Classification uses required-resource rules first, then ownership rules,
then exemptions, then inferred host paths. The longest matching path wins
within each explicit rule list. Unknown paths affect all registered hosts.
Required resources therefore take precedence over contributor exemptions.
An ownership entry classifies changes; a resource entry also requires that
path to exist for its registered hosts.

## Package checks

The command validates all current registrations in both marketplace
registries, and the Antigravity registrations in their plugin directories.
It parses registry and manifest JSON and checks names, duplicate
registrations, source directories, and numeric three-part versions.
A Claude Code manifest `agents` field can declare a list of `.md` files.
Each declared path must exist. Claude Code also loads `agents/`, so
`agents/` stays a Claude Code discovery path.

It checks declared paths and explicitly listed resources. Symlink resolution
must keep paths inside the plugin package. Required paths must be tracked or
new files that Git does not ignore. Ignored local files cannot satisfy the
package contract. Optional roots remain optional;
a hooks-only plugin does not need skills.

Discovered skills require header delimiters and one nonempty, single-line
`name` and `description`. Duplicate `name`, `description`, and `version`
fields and invalid names fail. Names contain lowercase letters and digits,
with single hyphens between segments. A skill-level `version` is optional;
when present, it uses numeric `major.minor.patch` components. These checks
define a narrow repository contract. They do not provide full YAML
validation or apply to agent headers with lists and multiline examples.

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

A skill can also carry a `version` in its `SKILL.md` frontmatter. Claude Code
copies usually do; Codex and Antigravity copies do not. A skill changes when
an affected path of its existing registration is in the skill directory, so
the same ownership rules and exemptions apply. Each changed skill needs a
frontmatter version greater than its base version. A new skill and a skill
with no base version need no increase. A changed skill that has a base
version and no current version fails, because a deleted `version` line would
otherwise skip this check. Skills
match by plugin identity, host, and skill directory name across the base and
proposed layouts. A source move changes every path in the skill, so a
versioned skill needs an increase. This check finds a skill version that a
rebase removed: when both branches made the same version change, the rebase
drops it from the branch without a conflict.

A new plugin or host registration needs valid current packaging and a valid
initial version. It has no previous registered version to exceed. A removed
host registration needs no version increase for that host. Remaining
registrations are checked normally.

A new Antigravity manifest in a registered plugin directory is a new host
registration, so it needs no version increase. After that, a change that
affects Antigravity needs a greater Antigravity manifest version.

Source moves match by plugin identity and host, so they preserve release
history. Only changes since the selected merge base affect release checks.
Historical omissions do not create retroactive version requirements.

## CHANGELOG checks

Release validation also checks the root `CHANGELOG.md` and the entry files
in `changelog.d/`
([ADR 0010](../adr/0010-use-entry-files-and-a-version-script.md)). A bullet
is new when its exact text is in neither `CHANGELOG.md` nor an entry file at
the merge base. A moved bullet, such as one that the release step moves
from an entry file into `CHANGELOG.md`, is not new, and an edited bullet is
new. Existing bullets are not checked.

Each new or changed entry file must be named `changelog.d/<N>.md` or
`changelog.d/<N>-<words>.md`, with lowercase words. Each of its lines must
be blank, one of the headings `### Added`, `### Removed`, and
`### Changed`, or a one-line bullet under one of them, and the file needs a
bullet. Each new bullet must have at most 600 characters and match the
[entry form](../../CONTRIBUTING.md#changelog-entries): `Repository:` or a
registered plugin name with hosts and versions, then the change, then one
` See [#N](https://github.com/aeghnnsw/cc-toolkit/issues/N).` link whose two
numbers agree. The change text holds no other ` See [#`; it can name other
issues inline as bare `(#N)`. A plugin bullet
names the hosts in the order Claude Code, Codex, Antigravity, writes one
version for adjacent hosts that ship the same version, gives each host its
current manifest version, and names exactly the hosts whose version
increased. A new host registration counts as an increase. Each plugin with
an increased version needs a new bullet in an entry file. The branch adds
at most one new bullet for each plugin and one new `Repository:` bullet,
counted across all new or changed entry files and all three headings. A
bullet at the merge base is not counted. The error names the plugin or
`Repository`, gives the `path:line` of the first two bullets, and shows the
form for a pull request that closes several issues.

A new line in `CHANGELOG.md` below its first `## ` heading must be blank or
a heading; a new bullet there fails, because only the release step adds
bullets to it. When the base has `CHANGELOG.md` and the proposed tree does
not, validation fails; when neither has it, the changelog checks are
skipped.

A branch that deletes an entry file of the merge base runs the release
step. It must change no file other than `CHANGELOG.md` and the entry files
of the merge base, and `CHANGELOG.md` must hold each bullet of each deleted
entry file.

## Adoption and verification

The repository adopts validation for all current packages without an
ignored-error baseline. Deterministic package defects require correction.
Substantial unrelated adoption repairs require a scope review.

[Command-interface fixtures](../../tests/test_validate_packages.py) use
temporary Git repositories. They check observable exit status, diagnostics,
and unchanged repository content. Coverage includes single-host, dual-host,
and hooks-only packages; Antigravity registration and shadowing; invalid
metadata; missing and escaped resources; skill headers; shared and
host-specific changes; exemptions; unknown files; plugin and skill version
rules; resource changes and source moves; registration lifecycle; missing
history; staged, unstaged, and new files; new bullets of entry files and
`CHANGELOG.md`; the count of new bullets for each plugin and `Repository:`;
and branches that run the release step. The
[release script tests](../../tests/test_release_scripts.py) run the release
step, the version script, and a rebase of two branches with entry files.

The [skill link test](../../tests/test_skill_links.py) imports the
validator module. It reuses registry loading, skill discovery, rule
validation, and path matching to check links in discovered skills. Keep
these functions compatible, or change the test with them.

Run the fixture suite during validator development. Measure the command
against the actual repository before adoption. See
[contributor verification](../../CONTRIBUTING.md#verification) for commands
and the separate plugin runtime suites.
