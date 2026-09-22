# cc-toolkit

This repository develops and publishes Claude Code and Codex plugins. See
[README.md](README.md) for the plugin catalog and
[CONTRIBUTING.md](CONTRIBUTING.md) for repository boundaries, file placement,
and verification commands. `AGENTS.md` is a symlink to this file; edit this
file to update instructions for both hosts.

## Agent skills

These documents configure agents working on cc-toolkit. They are shared
project conventions; contributors can follow them with or without Matt
Pocock's skills installed.

### Issue tracker

Before creating or updating issues and pull requests, read
[docs/agents/issue-tracker.md](docs/agents/issue-tracker.md). GitHub Issues
tracks work; durable design documents can live in the repository.

### Triage labels

Before triaging issues, read
[docs/agents/triage-labels.md](docs/agents/triage-labels.md) for the label
mapping and how to handle labels that are absent from GitHub.

### Domain docs

Before changing terminology or architecture, read
[docs/agents/domain.md](docs/agents/domain.md), then the relevant decision
records. The repository uses a single-context layout.

## Development workflow

1. Start each change with a GitHub issue. Reuse an existing issue when it
   covers the work.
2. Develop in a Git worktree under `trees/`. Branch names include an issue
   number: `feat-<issue>-<description>`, `bugfix-<issue>-<description>`,
   `doc-<issue>-<description>`, `refactor-<issue>-<description>`,
   `chore-<issue>-<description>`, or `test-<issue>-<description>`.
3. Verify the change before opening a PR using the relevant checks in
   [CONTRIBUTING.md](CONTRIBUTING.md#verification). Run the affected test
   suites for executable changes; validate content, links, and configuration
   for documentation and metadata changes.
4. Keep commits, issues, PR descriptions, and PR comments concise and
   accurate. Explain the problem and resulting behavior, and link the issue.
   Do not add AI authorship or generation attribution. Do not include a
   test-plan section in PR descriptions.
5. Use squash merges after review (`gh pr merge --squash`) to keep one commit
   per change on the default branch. After merging, use `repo-cleanup` to
   verify merged branches (including squash merges), remove eligible
   worktrees and branches, prune the upstream remote, and reconcile the
   default branch. Preserve dirty or unverified work.

Create a worktree with an issue-specific name, for example:

```bash
git worktree add trees/doc-<issue>-<description> -b doc-<issue>-<description>
```

## Plugin changes

- Keep each plugin self-contained. Put shipped skills, agents, hooks,
  scripts, and their runtime resources inside that plugin's directory.
- Update the relevant marketplace registry when adding, removing, or
  renaming a plugin, or changing its source path:
  `.claude-plugin/marketplace.json` for Claude Code and
  `.agents/plugins/marketplace.json` for Codex.
- Read the plugin's host-specific manifest before changing component paths.
  Claude Code discovers conventional `skills/` and `agents/` directories;
  some plugins use explicitly configured paths. Codex plugin manifests live
  in `.codex-plugin/plugin.json` and declare their component paths.
- Update the affected host's plugin version when shipping changes to that
  plugin. Root contributor documentation does not require a plugin version
  bump. Hosts can have different release versions.
- When editing a skill, verify its frontmatter, invocation guidance, and
  referenced resources. Record substantive behavior or policy changes in
  the root [CHANGELOG.md](CHANGELOG.md).
- Before adding agent-generated files, apply the storage policy in
  [CONTRIBUTING.md](CONTRIBUTING.md#what-belongs-in-git). Keep durable project
  decisions and shared configuration discoverable from these instructions.

## Automation

[.github/workflows/claude.yml](.github/workflows/claude.yml) handles explicit
`@claude` mentions on GitHub issues, comments, and PR reviews. Read the
workflow when changing its triggers or permissions.
