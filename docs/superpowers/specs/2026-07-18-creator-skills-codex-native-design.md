# Creator Skills Codex-native Migration Design

## Goal

Make `creator-skills` installable as a native Codex plugin for issue #175 and
expose Codex-adjusted versions of both existing scientific-content skills:

- `sci-slides`
- `sci-figure-format`

The Claude plugin and its existing skill tree remain unchanged.

## Context

`creator-skills` currently has a Claude manifest at
`creator-skills/.claude-plugin/plugin.json` and two skills under
`creator-skills/skills/`. Codex-native plugins in this repository use a separate
`.codex-plugin/plugin.json`, a dedicated `codex-skills/` tree when platform
instructions may diverge, and a repo marketplace entry in
`.agents/plugins/marketplace.json`.

`dev-skills` and `task-loop` establish the repository pattern. This migration
uses that pattern instead of pointing both runtimes at the same skill files.

## Scope

In scope:

- Add `creator-skills/.codex-plugin/plugin.json`.
- Add Codex-native `sci-slides` and `sci-figure-format` skills under
  `creator-skills/codex-skills/`.
- Add `creator-skills` to `.agents/plugins/marketplace.json`.
- Validate skill frontmatter, plugin metadata, paths, and marketplace metadata.
- Forward-test each Codex skill on a representative scientific-content task.

Out of scope:

- Changing the Claude manifest or `creator-skills/skills/` content.
- Rewriting or re-sourcing the scientific guidance.
- Adding slide-generation scripts, presentation templates, icons, MCP servers,
  hooks, apps, or other plugin components.
- Migrating other plugins.

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

## Marketplace Entry

Append `creator-skills` to the existing ordered plugin list in
`.agents/plugins/marketplace.json` with:

- local source path `./creator-skills`, matching this repository's established
  marketplace layout;
- installation policy `AVAILABLE`;
- authentication policy `ON_INSTALL`;
- category `Productivity`.

The existing marketplace name and plugin order remain unchanged.

## Validation

Use a red-green validation cycle:

1. Confirm packaging checks fail before the Codex manifest, skill tree, and
   marketplace entry exist.
2. Add the minimum native package files.
3. Run the skill creator validator for both Codex skill directories.
4. Run the plugin creator validator against `creator-skills`.
5. Validate all changed JSON with `jq` and verify every manifest path exists.
6. Confirm the native marketplace contains exactly one `creator-skills` entry.
7. Forward-test `sci-slides` with a slide-design scenario and
   `sci-figure-format` with a publication-figure scenario.

Forward tests are read-only and verify that each skill retrieves and applies
its specific guidance. They do not create durable presentation artifacts.

## Acceptance Criteria

- `creator-skills/.codex-plugin/plugin.json` passes plugin validation and points
  to `./codex-skills/`.
- Both Codex skills pass skill validation and contain no unsupported
  frontmatter fields.
- `.agents/plugins/marketplace.json` contains one valid `creator-skills` entry.
- Existing Claude files remain byte-for-byte unchanged.
- Representative forward tests show that each Codex skill applies its
  domain-specific guidance.
