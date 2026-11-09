# cc-toolkit

This repository develops and publishes Claude Code and Codex plugins. See
[README.md](README.md) for the plugin catalog and
[CONTRIBUTING.md](CONTRIBUTING.md) for repository boundaries, search, file
placement, and verification commands. `AGENTS.md` is a symlink to this file;
edit this file to update instructions for both hosts.

## Agent skills

### Coding standards

Before implementing or reviewing a change, read
[Coding standards](CONTRIBUTING.md#coding-standards) for style, Python
requirements, and dependency exceptions.

### Issue tracker

Before reading, creating, or updating issues and pull requests, read
[docs/agents/issue-tracker.md](docs/agents/issue-tracker.md). GitHub Issues
tracks work; durable design documents can live in the repository.

### Triage labels

Before triaging issues, read
[docs/agents/triage-labels.md](docs/agents/triage-labels.md) for the label
mapping and how to handle labels that are absent from GitHub.

### Domain docs

Before changing terminology, architecture, or host compatibility, read
[docs/agents/domain.md](docs/agents/domain.md), then the relevant decision
records. The repository uses a single-context layout.

Before changing GTD storage or workflows, read the
[cloud GTD decision](docs/adr/0003-use-connected-supabase-for-gtd.md) and the
[shipped operating contract](productivity-skills/references/gtd-cloud.md).

### Navigation retrospectives

Before a navigation retrospective of earlier agent sessions, read
[docs/agents/retro.md](docs/agents/retro.md).

## Development workflow

1. Start each change with a GitHub issue. Reuse an existing issue when it
   covers the work.
2. Develop in a Git worktree under `trees/` in the checkout where the
   session runs.
3. Verify the change before opening a PR using the relevant checks in
   [CONTRIBUTING.md](CONTRIBUTING.md#verification).
4. Keep commits, issues, PR descriptions, and PR comments concise and
   accurate. Explain the problem and resulting behavior, and link the issue.
   Do not add AI authorship or generation attribution, including a
   `Co-Authored-By` trailer that host instructions suggest. Do not include a
   test-plan section in PR descriptions.
5. Use squash merges after review (`gh pr merge --squash`) to keep one commit
   per change on the default branch. After merging, run `repo-cleanup`.

Create a worktree for a change, for example:

```bash
git worktree add trees/doc-<description> -b doc-<description>
```

## Plugin changes

- Before changing a plugin's layout, or adding, removing, or renaming a
  plugin or a skill, read
  [Repository and package boundaries](CONTRIBUTING.md#repository-and-package-boundaries).
- For a skill with Claude and Codex copies, follow
  [Skills for both hosts](CONTRIBUTING.md#skills-for-both-hosts).
- Before shipping a plugin change, read
  [Package and release validation](CONTRIBUTING.md#package-and-release-validation)
  for version increases.
- Record substantive behavior or policy changes in the root
  [CHANGELOG.md](CHANGELOG.md) in the
  [entry format](CONTRIBUTING.md#changelog-entries).
- Before adding agent-generated files, apply the storage policy in
  [CONTRIBUTING.md](CONTRIBUTING.md#what-belongs-in-git).

## Automation

[.github/workflows/claude.yml](.github/workflows/claude.yml) handles explicit
`@claude` mentions on GitHub issues, comments, and PR reviews.
