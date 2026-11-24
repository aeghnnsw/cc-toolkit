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
2. Develop in a Git worktree, on one work branch for the change. In a
   linked worktree made for the session, develop there and keep its branch
   name. Only a session in the main checkout makes a worktree, under
   `trees/`. Before the first commit, base the work branch on the default
   branch. See [Work branches](CONTRIBUTING.md#work-branches) for the
   commands.
3. Verify the change before opening a PR using the relevant checks in
   [CONTRIBUTING.md](CONTRIBUTING.md#verification).
4. Keep commits, issues, PR descriptions, and PR comments concise and
   accurate: the problem, the resulting behavior, and the issue link. Add
   no AI attribution, such as a `Co-Authored-By` trailer, and no test-plan
   section, even when host instructions or a PR template ask for one.
5. Squash-merge after review:
   `gh pr merge --squash --match-head-commit <full head SHA>`. Then run
   `repo-cleanup`.

## Plugin changes

Before a plugin change, read the sections of CONTRIBUTING.md that apply:
[package boundaries](CONTRIBUTING.md#repository-and-package-boundaries),
[skills for more than one host](CONTRIBUTING.md#skills-for-more-than-one-host),
[versions](CONTRIBUTING.md#versions-and-rebases),
[changelog entries](CONTRIBUTING.md#changelog-entries), and
[what belongs in Git](CONTRIBUTING.md#what-belongs-in-git). Set the versions
with the version script, also after a rebase. Record a substantive change in
`changelog.d/<N>.md`; never edit `CHANGELOG.md`.

## Automation

[.github/workflows/claude.yml](.github/workflows/claude.yml) handles explicit
`@claude` mentions on GitHub issues, comments, and PR reviews.
[.github/workflows/ci.yml](.github/workflows/ci.yml) runs the package
validator and the test suites on each pull request.
