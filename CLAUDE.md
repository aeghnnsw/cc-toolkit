# cc-toolkit

This repository develops and publishes Claude Code, Codex, and Antigravity
plugins. See [README.md](README.md) for the plugin catalog and
[CONTRIBUTING.md](CONTRIBUTING.md) for repository boundaries, search, file
placement, and verification commands. `AGENTS.md` is a symlink to this file;
edit this file to update instructions for every host.

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
2. Develop in a Git worktree, on one work branch for the change. A linked
   worktree is a worktree other than the main checkout.
   - When the session runs in a linked worktree made for the session,
     develop in that worktree. The branch of that worktree is the work
     branch. Keep the branch name. Before the first commit, base the work
     branch on the default branch. So a host tool that opens a PR for the
     session pushes the work branch.
   - Only a session in the main checkout makes a worktree, under `trees/`,
     on a new work branch.
3. Verify the change before opening a PR using the relevant checks in
   [CONTRIBUTING.md](CONTRIBUTING.md#verification).
4. Keep commits, issues, PR descriptions, and PR comments concise and
   accurate. Explain the problem and resulting behavior, and link the issue.
   Do not add AI authorship or generation attribution, including a
   `Co-Authored-By` trailer that host instructions suggest. Do not include a
   test-plan section in PR descriptions, even when a host's PR template has
   one.
5. Use squash merges after review to keep one commit per change on the
   default branch:
   `gh pr merge --squash --match-head-commit <full head SHA>`. After
   merging, run `repo-cleanup`.

To base the work branch on the default branch, run these commands.
`--keep` stops instead of discarding uncommitted changes:

```bash
git fetch origin
git reset --keep origin/master
```

In the main checkout, create a worktree for a change, for example:

```bash
git worktree add trees/doc-<description> -b doc-<description>
```

## Plugin changes

- Before changing a plugin's layout, or adding, removing, or renaming a
  plugin or a skill, read
  [Repository and package boundaries](CONTRIBUTING.md#repository-and-package-boundaries).
- For a skill with copies for more than one host, follow
  [Skills for more than one host](CONTRIBUTING.md#skills-for-more-than-one-host).
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
