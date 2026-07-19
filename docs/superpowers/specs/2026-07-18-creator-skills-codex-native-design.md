# Creator Skills and Step Workflow Codex-native Migration Design

## Goal

Make `creator-skills` installable as a native Codex plugin for issue #175 and
expose Codex-adjusted versions of both existing scientific-content skills:

- `sci-slides`
- `sci-figure-format`

Also expose the existing `step-workflow` file-naming convention through the
already-native `dev-skills` plugin.

Both plugins' Claude skill trees remain unchanged.

## Context

`creator-skills` currently has a Claude manifest at
`creator-skills/.claude-plugin/plugin.json` and two skills under
`creator-skills/skills/`. Codex-native plugins in this repository use a separate
`.codex-plugin/plugin.json`, a dedicated `codex-skills/` tree when platform
instructions may diverge, and a repo marketplace entry in
`.agents/plugins/marketplace.json`.

`dev-skills` and `task-loop` establish the repository pattern. This migration
uses that pattern instead of pointing both runtimes at the same skill files.
`dev-skills` already has a Codex manifest and marketplace entry, but its Codex
skill tree does not yet contain `step-workflow`.

## Scope

In scope:

- Add `creator-skills/.codex-plugin/plugin.json`.
- Add Codex-native `sci-slides` and `sci-figure-format` skills under
  `creator-skills/codex-skills/`.
- Add `creator-skills` to `.agents/plugins/marketplace.json`.
- Add a Codex-adjusted `step-workflow` under `dev-skills/codex-skills/`.
- Validate skill frontmatter, plugin metadata, paths, and marketplace metadata.
- Forward-test all three Codex skills on representative tasks.

Out of scope:

- Changing either Claude manifest or either plugin's `skills/` content.
- Rewriting or re-sourcing the scientific guidance.
- Adding slide-generation scripts, presentation templates, icons, MCP servers,
  hooks, apps, or other plugin components.
- Migrating any other skill or plugin.

## Alternatives Considered

### Separate Codex skill tree

Add `codex-skills/` and point the Codex manifest at it. This duplicates the two
skill documents, but it isolates platform-specific frontmatter and future Codex
workflow changes. This is the selected approach because it matches existing
native plugins in the repository.

### Shared skill tree

Point both Claude and Codex manifests at `skills/`. This minimizes duplication
but couples the runtimes and leaves the current Claude-oriented frontmatter in
the Codex package.

### Platform-neutral rewrite

Rewrite the existing skills as one shared, neutral implementation. This could
reduce long-term duplication but expands the migration into a Claude behavior
change and risks unnecessary regressions.

## Package Structure

```text
creator-skills/
|-- .claude-plugin/
|   `-- plugin.json
|-- .codex-plugin/
|   `-- plugin.json
|-- skills/
|   |-- sci-figure-format/
|   |   `-- SKILL.md
|   `-- sci-slides/
|       `-- SKILL.md
`-- codex-skills/
    |-- sci-figure-format/
    |   `-- SKILL.md
    `-- sci-slides/
        `-- SKILL.md

dev-skills/
|-- .codex-plugin/
|   `-- plugin.json
`-- codex-skills/
    |-- ...
    `-- step-workflow/
        `-- SKILL.md
```

## Codex Plugin Manifest

The native manifest will:

- use the plugin identity `creator-skills`;
- keep version `1.0.1`, matching the current Claude plugin;
- point `skills` to `./codex-skills/`;
- include author, repository, license, discovery keywords, and interface
  metadata following the `dev-skills` and `task-loop` manifests;
- use the `Productivity` category and `Read`/`Write` capabilities;
- offer starter prompts for scientific slide design and figure formatting.

The manifest will not declare components that do not exist.

## Codex Skills

Each Codex skill will preserve the current domain guidance and workflow while
using Codex-valid skill metadata:

- YAML frontmatter contains only `name` and `description`.
- Each description begins with `Use when` and names concrete triggering tasks.
- The unsupported `version` frontmatter field is omitted.
- Claude-specific wording is not introduced.

The migration will not alter numerical claims, design standards, palettes,
format recommendations, or other scientific content. Content modernization is
a separate concern.

## Codex Step Workflow

The Codex version of `step-workflow` will preserve the numbered file and
sub-step naming conventions while adjusting runtime-specific instructions:

- YAML frontmatter contains only `name` and a `Use when` description.
- `TodoWrite` references are replaced with Codex's `update_plan` workflow.
- The skill applies when the user requests sequential, step-based organization;
  it does not override an existing repository layout or naming convention.
- `dev-skills/.codex-plugin/plugin.json` is updated so its discovery metadata
  mentions the newly available workflow.
- The Codex plugin version advances from `1.0.0` to `1.0.1` so existing native
  installations receive a new version-keyed cache entry containing the skill.

## Marketplace Entry

Append `creator-skills` to the existing ordered plugin list in
`.agents/plugins/marketplace.json` with:

- local source path `./creator-skills`, matching this repository's established
  marketplace layout;
- installation policy `AVAILABLE`;
- authentication policy `ON_INSTALL`;
- category `Productivity`.

The existing marketplace name and plugin order remain unchanged.
The existing `dev-skills` marketplace entry already covers `step-workflow` and
does not need a second entry.

## Validation

Use a red-green validation cycle:

1. Confirm packaging checks fail before the Codex manifest, skill tree, and
   marketplace entry exist.
2. Add the minimum native package files.
3. Run the skill creator validator for all three Codex skill directories.
4. Validate all changed JSON with `jq` and run an executable manifest contract
   check that proves the declared skill root is relative, remains inside the
   plugin, contains exactly the two expected creator skill directories, and has
   folder names matching each skill's frontmatter `name`. Separately confirm
   that the existing `dev-skills` root contains `step-workflow` with matching
   folder and frontmatter names.
5. Confirm the native marketplace contains exactly one `creator-skills` entry.
6. Use an isolated temporary Codex home to add the worktree as a local
   marketplace, discover `creator-skills` through `codex plugin list`, and
   install it with `codex plugin add`.
7. Start `codex app-server --stdio` with that same isolated Codex home and call
   `skills/list` for the worktree with `forceReload: true`. Assert that the
   registry contains the enabled namespaced skills
   `creator-skills:sci-slides` and `creator-skills:sci-figure-format`, that
   their paths originate under the isolated installed plugin cache and its
   `codex-skills/` tree, that neither path resolves to the Claude `skills/`
   tree, and that the response contains no skill-loading errors. In the same
   isolated home, install `dev-skills` and assert that the registry contains
   enabled `dev-skills:step-workflow` from its installed `1.0.1` native
   `codex-skills/` tree.
8. Forward-test `sci-slides` with a slide-design scenario,
   `sci-figure-format` with a publication-figure scenario, and `step-workflow`
   with a request for sequential feature-file naming.

Forward tests are read-only and verify that each skill retrieves and applies
its specific guidance. They do not create durable presentation artifacts and
do not substitute for the native-loader discovery smoke test.

The bundled plugin-creator validator is not part of this migration's contract:
its current implementation hard-codes `skills/` and rejects the repository's
working `./codex-skills/` manifest pattern. The explicit contract check and
isolated Codex loader test validate the package that this repository actually
ships.

## Acceptance Criteria

- `creator-skills/.codex-plugin/plugin.json` passes the explicit manifest
  contract checks and points to `./codex-skills/`.
- Both creator Codex skills pass skill validation and contain no unsupported
  frontmatter fields.
- The Codex `step-workflow` passes skill validation, preserves the file-naming
  convention, uses Codex planning terminology, and is discoverable through the
  version-bumped `dev-skills` package.
- `.agents/plugins/marketplace.json` contains one valid `creator-skills` entry.
- An isolated Codex loader discovers and installs `creator-skills` from the
  repository marketplace, and `skills/list` registers both namespaced native
  skills from the installed `codex-skills/` tree without loader errors. The
  same check registers `dev-skills:step-workflow` from the installed native
  `dev-skills` `1.0.1` tree.
- Existing Claude files for both plugins remain byte-for-byte unchanged.
- Representative forward tests show that all three Codex skills apply their
  domain-specific guidance.
