# cc-toolkit

This repository develops and publishes Claude Code and Codex plugins. See
[README.md](README.md) for the plugin catalog and
[CONTRIBUTING.md](CONTRIBUTING.md) for repository boundaries, search, file
placement, and verification commands. `AGENTS.md` is a symlink to this file;
edit this file to update instructions for both hosts.

## Agent skills

These documents configure agents working on cc-toolkit. They are shared
project conventions; contributors can follow them with or without Matt
Pocock's skills installed.

### Issue tracker

Before reading, creating, or updating issues and pull requests, read
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

### Navigation retrospectives

Before a navigation retrospective of earlier agent sessions, read
[docs/agents/retro.md](docs/agents/retro.md).

## Development workflow

1. Start each change with a GitHub issue. Reuse an existing issue when it
   covers the work.
2. Develop in a Git worktree under `trees/` in the checkout where the
   session runs. A Claude Code desktop session runs in
   `.claude/worktrees/<name>/` and refuses edits outside that worktree.
   Branch names include an issue number: `feat-<issue>-<description>`,
   `bugfix-<issue>-<description>`, `doc-<issue>-<description>`,
   `refactor-<issue>-<description>`, `chore-<issue>-<description>`, or
   `test-<issue>-<description>`. Run shell commands from the worktree
   root, and pass paths or `git -C` instead of `cd` into a subdirectory.
   The commands in CONTRIBUTING.md use paths relative to that root.
3. Verify the change before opening a PR using the relevant checks in
   [CONTRIBUTING.md](CONTRIBUTING.md#verification). Run the affected test
   suites for executable changes; validate content, links, and configuration
   for documentation and metadata changes. When a check needs temporary
   files or a temporary Git repository, put them in one `mktemp -d`
   directory, stage files there by name, and remove the directory by its
   path. The core-hooks policy scripts block bulk staging and an `rm` with
   a wildcard target.
4. Stage changed files by name. Keep commits, issues, PR descriptions, and
   PR comments concise and accurate. Explain the problem and resulting
   behavior, and link the issue. Do not add AI authorship or generation
   attribution, including a `Co-Authored-By` trailer that host instructions
   suggest. Do not include a test-plan section in PR descriptions. Write
   each commit message to a file and run `git commit -F <file>`. The
   installed core-hooks policy scripts check the text of each shell command
   and can block a command that quotes message text.
5. Use squash merges after review (`gh pr merge --squash`) to keep one commit
   per change on the default branch. `master` requires a pull request; it
   requires no approval and no status check. Before merging a plugin
   release, compare the plugin version with `origin/master` as described in
   [release validation](CONTRIBUTING.md#package-and-release-validation).
   After merging, use `repo-cleanup` to verify merged branches (including
   squash merges), remove eligible worktrees and branches, prune the upstream
   remote, and reconcile the default branch. Preserve dirty or unverified
   work.

Create a worktree with an issue-specific name, for example:

```bash
git worktree add trees/doc-<issue>-<description> -b doc-<issue>-<description>
```

## Shell

- The shell is zsh on macOS. Quote a word that starts with `=`, such as
  `echo '====='`.
- zsh does not split an unquoted variable into words. Put a multi-word
  command in a function or in a script that `bash` runs.
- zsh stops a command when an unquoted glob matches no file. Quote the
  glob, such as `--include='*.md'`, or list tracked files with
  `git ls-files '<pattern>'`.
- Use BSD tool options. GNU `timeout` is absent.

## Plugin changes

- Keep each plugin self-contained. Put shipped skills, agents, hooks,
  scripts, and their runtime resources inside that plugin's directory.
- Update the relevant marketplace registry when adding, removing, or
  renaming a plugin, or changing its source path:
  `.claude-plugin/marketplace.json` for Claude Code and
  `.agents/plugins/marketplace.json` for Codex.
- When adding, removing, or renaming a plugin or a skill, update its
  entries in [README.md](README.md).
- Read the plugin's host-specific manifest before changing component paths.
  Claude Code discovers conventional `skills/` and `agents/` directories;
  some plugins use explicitly configured paths. Codex plugin manifests live
  in `.codex-plugin/plugin.json` and declare their component paths. Some
  resources outside these paths belong to one host, such as task-loop's Codex
  agents. See [host ownership](docs/design/package-validation.md#host-ownership).
- Update the affected host's plugin version when shipping changes to that
  plugin: the `version` field in `<plugin>/.claude-plugin/plugin.json` or
  `<plugin>/.codex-plugin/plugin.json`. The `metadata.version` field in the
  Claude Code marketplace registry is not a plugin version. Root contributor
  documentation does not require a plugin version bump. Hosts can have
  different release versions.
- When editing a skill, verify its frontmatter and invocation guidance. Run
  the [root tests](CONTRIBUTING.md#package-and-release-validation) to check
  its links and referenced resources. For a skill with Claude and Codex
  copies, follow
  [Skills for both hosts](CONTRIBUTING.md#skills-for-both-hosts).
- Record substantive behavior or policy changes in the root
  [CHANGELOG.md](CHANGELOG.md). Before you open the file, read the
  [entry format](CONTRIBUTING.md#changelog-entries), which shows how to
  find the insertion point.
- Before adding agent-generated files, apply the storage policy in
  [CONTRIBUTING.md](CONTRIBUTING.md#what-belongs-in-git). Keep durable project
  decisions and shared configuration discoverable from these instructions.

## Automation

[.github/workflows/claude.yml](.github/workflows/claude.yml) handles explicit
`@claude` mentions on GitHub issues, comments, and PR reviews. Read the
workflow when changing its triggers or permissions.
