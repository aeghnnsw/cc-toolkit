# cc-toolkit

Unified Claude Code and Codex plugin marketplace for development workflows, scientific content creation, and document processing.

## Overview

**cc-toolkit** is a modular plugin marketplace following the Claude Code plugin system, with Codex plugin support where a plugin has been ported. Each plugin is self-contained and can include skills, agents, hooks, commands, scripts, and Codex-specific manifests.

## Development

This repository contains both plugin source and shared contributor documentation.
The marketplace registries select individual plugin directories for distribution.
See [CONTRIBUTING.md](CONTRIBUTING.md) for what belongs in Git and
verification, and [CLAUDE.md](CLAUDE.md) for the development workflow.
`AGENTS.md` links to the same instructions. The documents under `docs/agents/`
configure work on this repository; using its plugins does not require installing
Matt Pocock's development skills.

## Repository Structure

```
cc-toolkit/
├── .claude-plugin/marketplace.json   # Claude Code plugin registry
├── .agents/plugins/marketplace.json  # Codex plugin registry
├── .github/workflows/                # @claude automation and PR package validation
├── .gitignore                        # Exclusions shared by all contributors
├── README.md                         # Overview and plugin catalog
├── CLAUDE.md                         # Shared contributor instructions
├── AGENTS.md                         # Symlink to CLAUDE.md
├── CONTRIBUTING.md                   # Repository boundaries and verification
├── GLOSSARY.md                       # Glossary of agreed domain terms
├── CHANGELOG.md                      # Plugin and repository changes
├── package-validation.json           # Package and release validation rules
├── scripts/validate_packages.py      # Package and release validator
├── tests/                            # Root tests: validator, skill links, model pins, placeholders, agent fields
├── docs/
│   ├── adr/                          # Accepted architecture decisions
│   ├── agents/                       # Issue tracker, triage, domain, and retrospective conventions
│   ├── design/                       # Durable designs, such as package validation
│   └── superpowers/                  # Dated specs, plans, and conclusions; some superseded
├── cc-customize/                     # Claude Code model, statusline, and prompt config skills
├── core-hooks/                       # Safety and workflow hooks plugin
├── creator-skills/                   # Scientific content creation plugin
├── dev-skills/                       # Development workflow plugin
├── doc-skills/                       # Document processing plugin
├── productivity-skills/              # Personal productivity plugin
├── pymol-skills/                     # PyMOL molecular visualization plugin
└── task-loop/                        # Not in the marketplaces; see its README
```

Each plugin directory holds `.claude-plugin/plugin.json`, a
`.codex-plugin/plugin.json` when the plugin supports Codex, and its
components, resources, and any tests (see
[Repository and package boundaries](CONTRIBUTING.md#repository-and-package-boundaries)).
[Skills for both hosts](CONTRIBUTING.md#skills-for-both-hosts) names each
host's skill directory, and [Available Plugins](#available-plugins) describes
each plugin and lists its skills.

## Available Plugins

### Development Skills (`dev-skills`)
Development workflows, repository hygiene, documentation, and review.

**Skills:**
- **repo-cleanup**: Remove merged worktrees and branches, prune the upstream remote, reconcile completed issues, delete the planning folders of completed issues, and update the Default Branch
- **step-workflow**: Step-based file naming and folder organization using numbered prefixes (01_, 02_, 03_) for clear workflow order
- **goal-rubric**: Draft a binary pass/fail rubric and a ready-to-paste `/goal` completion condition for Claude or Codex
- **doc-update**: Update existing documentation to current project truth and audit it against a documentation quality rubric
- **grill-with-research**: Research the project before each round of Matt’s grilling interview, drop the questions that research can settle, and ask the rest in dependency order with evidence and a recommendation; research can run scripts in an untracked planning folder; requires the Matt skills plugin
- **matt-automode**: Run Matt’s planning-to-merge workflow without human checkpoints; grill with grill-with-research and answer its questions itself, reuse completed grilling, and end each run with a retro that only proposes issues; requires the Matt skills plugin
- **pressure-test**: Run an independent adversarial review of a design, plan, PR, rubric, or decision and save a conclusion. The read-only critic comes from the other host: GPT through the Codex CLI in Claude Code, and Claude through the Claude Code CLI in Codex. The user or a calling skill can choose the critic model from the two allowed models of its family. Another skill can call it with several questions; the conclusion shows the critic's assessment of each question
- **pr-feedback**: Gather PR feedback and run a structured review-fix-push cycle
- **sci-project-layout**: Set up or adopt the layout of a scientific Python research project, and find where a file goes in it: one store for data and results that every worktree finds, one folder for each experiment and each run, and read-only cited runs for the results you keep
- **lean-tests**: Check a pytest suite without changing a file: run time, the slowest tests and fixtures, flaky or order-dependent tests, tests that check nothing, coverage-subset candidates, and diff coverage of recent changes, with one recommended next mode; on request, make the suite faster without deleting a test, with ordered fixes, test tiers with time budgets, the tier commands in each agent instruction file that exists, and a before/after table; or prune redundant tests under one path, deleting a test only when a full kill matrix of bundled mutants and a written rationale show that retained tests detect the same faults, in checked batches of one commit each; or review the tests of a change: a weakening gate that fails a change to product code that also removes, skips, loosens, or rewrites an existing test, a label for each new test from a run against the base code, a mutation check that each new test detects a fault that no existing test detects, the changed lines that no test executes, and pinned requirement sources for the acceptance of an intended test change
- **project-eval**: Evaluate a feature, a design document, a running web app, or a whole project with skeptical evaluator agents; a separate verifier checks every finding before it enters one report
- **discord-setup**: Configure Discord plugin prerequisites

**Codex skills:**
- **doc-update**
- **goal-rubric**
- **grill-with-research**
- **lean-tests**
- **matt-automode**
- **pressure-test**
- **repo-cleanup**
- **sci-project-layout**
- **step-workflow**

### Creator Skills (`creator-skills`)
Scientific content creation for figures and presentations.

**Skills:**
- **sci-figure-format**: Publication-quality scientific figure formatting for major journals (Nature, Science, ACS, RSC)
- **sci-slides**: Academic presentation slide creation for STEM fields

**Codex skills:**
- **sci-figure-format**
- **sci-slides**

### Document Skills (`doc-skills`)
Document processing and AI-accessible content extraction.

**Skills:**
- **docling-pdf**: PDF to markdown conversion using IBM's Docling library
- **paper-rename**: Intelligent PDF renaming based on extracted titles and metadata

**Agents (deprecated; retained for compatibility):**
- **paper-reader**: Analyzes research papers and answers questions about content
- **paper-consolidator**: Consolidates multiple paper analysis outputs into unified reports

### Core Hooks (`core-hooks`)
Safety guards and workflow enforcement hooks.

**Hooks:**
- **safety_guard.py**: Blocks an `rm` of a wildcard target, `/`, `.`, a path with `..`, a `~` or `$HOME` path, the temporary directory root, or a system path such as `/usr`, `/etc`, or `/var`. A named path inside `$TMPDIR` is allowed. Also blocks `env` or `printenv` with no command, which prints every environment variable; `env | cut -d= -f1` lists the names only
- **pre_git_hook.py**: Checks Git policy, including branch prefixes, bulk staging, and AI attribution. Blocks `git grep -E` with an escape such as `\b`, `\s`, or `\d`, which macOS reads as a plain character; the message says to use `-P`
- **zsh_traps.py**: When the shell is zsh, quotes separators with two or more leading equals signs in standalone `echo` commands, with optional `-n`. Labels can use ASCII letters, digits, and underscores, as in `echo =====CODEX`. Current Claude Code and Codex apply the corrected input through their normal permission checks. Complex commands keep the existing checks: the hook blocks unresolved `=name` expansions and warns about valid command expansions, unsplit variables, unmatched globs, and a letter after `$NAME:`, which zsh can read as a modifier. In Claude Code, it blocks a zsh parameter flag such as `${(f)...}`, which the Claude Code safety check rejects with a message about `rm`. Each message names the fix
- **post_tool_use.py**: Logs tool executions to `logs/post_tool_use.jsonl` in the project directory
- **system_notification.py**: Plays sound notifications on task completion

### Productivity Skills (`productivity-skills`)
GTD workflows through a connected Supabase account, plus native macOS Calendar and Reminders. GTD uses a private project/owner configuration and Python 3.11+. See the [cloud workflow and setup](productivity-skills/references/gtd-cloud.md).

**Skills:**
- **calendar-manager**: Manage macOS Calendar events via EventKit CLI
- **reminder-manager**: Manage macOS Reminders via EventKit CLI
- **gtd-inbox**: Capture thoughts and tasks into the cloud GTD inbox
- **gtd-process**: Process cloud inbox items into linked projects or actions
- **gtd-project**: Review and manage cloud GTD projects and their actions
- **gtd-next**: Select cloud GTD actions with available native Calendar context
- **gtd-overview**: Read-only cloud project and action inventory with shared status rules

**Codex skills:**
- **calendar-manager**
- **reminder-manager**
- **gtd-inbox**
- **gtd-process**
- **gtd-project**
- **gtd-next**
- **gtd-overview**

### PyMOL Skills (`pymol-skills`)
PyMOL molecular visualization control via MCP server for Claude Code and Codex.
Both hosts share the local Python bridge and socket plugin. See the
[installation guide](pymol-skills/README.md).

**Skills:**
- **pymol-mcp**: Control PyMOL through natural language for protein visualization and structural analysis
- **pymol-setup**: Installation instructions for the PyMOL socket plugin

**Codex skills:**
- **pymol-mcp**
- **pymol-setup**

### Claude Code Customization (`cc-customize`)

**Skills:**
- **model-config**: Configure model, effort level, and auto-compact window
- **statusline-setup**: Configure the Claude Code statusline
- **claude-prompt-config**: Back up and replace the global Claude Code instruction file (`~/.claude/CLAUDE.md`) on this machine or a remote host

## Plugin System Benefits

1. **Modular**: Each plugin is self-contained and portable
2. **Scalable**: Easy to add new skills, agents, hooks, or commands to any plugin
3. **Standard**: Follows Claude Code and Codex plugin packaging conventions where supported
4. **Maintainable**: Clear separation of concerns between plugins
5. **Shareable**: Individual plugins can be distributed independently

## Usage

Run these commands in a terminal with Git and the matching host CLI installed.
The commands download the marketplace from GitHub; a local checkout is not
required. Each example installs `creator-skills`. Replace that name with another
plugin from [Available Plugins](#available-plugins) when needed.

### Claude Code

Add the marketplace, then install the plugin for your user account:

```bash
claude plugin marketplace add aeghnnsw/cc-toolkit
claude plugin install creator-skills@cc-toolkit --scope user
claude plugin list
```

Start a new Claude Code session to load the plugin. See the
[Claude Code plugin guide](https://code.claude.com/docs/en/plugins/install)
for other installation scopes.

### Codex

Add the marketplace, then install the plugin:

```bash
codex plugin marketplace add aeghnnsw/cc-toolkit
codex plugin add creator-skills@cc-toolkit
codex plugin list --marketplace cc-toolkit
```

Start a new Codex session to load the plugin. The Codex marketplace includes
`core-hooks`, `dev-skills`, `creator-skills`, `productivity-skills`, and
`pymol-skills`. See the [Codex plugin commands](https://learn.chatgpt.com/docs/developer-commands#codex-plugin)
for command options.

### Updates and removal

The examples use `creator-skills`. Replace that name with the plugin you
want to manage.

To update the installed Claude Code copy:

1. Run `claude plugin marketplace update cc-toolkit`.
2. Run `claude plugin update creator-skills@cc-toolkit --scope user`. For a
   project or local installation, use that installation's scope instead.
3. Start a new Claude Code session.

To update the installed Codex copy:

1. Run `codex plugin marketplace upgrade cc-toolkit`.
2. Check that `~/.codex/plugins/cache/cc-toolkit/creator-skills/` contains
   the intended version.
3. If it does not, run `codex plugin add creator-skills@cc-toolkit`.
4. Start a new Codex session.

The Core Hooks policy scripts that check your shell commands are the
installed copy. A denial names its path, such as
`core-hooks/1.0.13/scripts/pre_git_hook.py`. Until you update that copy, it
keeps blocking a command that this checkout allows.

Disabling keeps a plugin installed. Uninstalling removes it. For the Claude
Code user installation above, choose one action:

```bash
# Disable; use enable to turn it on again.
claude plugin disable creator-skills@cc-toolkit --scope user

# Uninstall.
claude plugin uninstall creator-skills@cc-toolkit --scope user
```

For a project or local installation, use that installation's scope instead.

To disable the Codex plugin, set its entry in your active user configuration
(`~/.codex/config.toml` by default):

```toml
[plugins."creator-skills@cc-toolkit"]
enabled = false
```

Edit the existing entry if present; do not add a duplicate table. Set
`enabled = true` to enable it again. A trusted project's `.codex/config.toml`
can override this user setting. Codex has no `plugin disable` subcommand.

To uninstall it instead:

```bash
codex plugin remove creator-skills@cc-toolkit
```

Start a new host session after changing its plugins. See the
[Claude Code management guide](https://code.claude.com/docs/en/plugins/install#manage-plugins-from-your-shell)
and [Codex plugin configuration](https://developers.openai.com/plugins/build/plugins#enable-or-disable-a-plugin-for-a-repo)
for scope and configuration details.
