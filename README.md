# cc-toolkit

Unified Claude Code and Codex plugin marketplace for development workflows and scientific content creation, with Antigravity support where a plugin has been ported.

## Overview

**cc-toolkit** is a modular plugin marketplace following the Claude Code plugin system, with Codex and Antigravity plugin support where a plugin has been ported. Each plugin is self-contained and can include skills, agents, hooks, commands, scripts, and Codex and Antigravity manifests.

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
├── .github/workflows/                # @claude automation and PR checks
├── .gitignore                        # Exclusions shared by all contributors
├── README.md                         # Overview and plugin catalog
├── CLAUDE.md                         # Shared contributor instructions
├── AGENTS.md                         # Symlink to CLAUDE.md
├── CONTRIBUTING.md                   # Repository boundaries and verification
├── GLOSSARY.md                       # Glossary of agreed domain terms
├── CHANGELOG.md                      # Plugin and repository changes
├── changelog.d/                      # Entry files of merged changes that wait for the release step
├── package-validation.json           # Package and release validation rules
├── scripts/validate_packages.py      # Package and release validator
├── scripts/next_versions.py          # Version script: next free versions above master
├── scripts/release_changelog.py      # Release step: entry files into CHANGELOG.md
├── tests/                            # Root tests: validator, release scripts, skill links, model pins, placeholders, agent fields
├── docs/
│   ├── adr/                          # Accepted architecture decisions
│   ├── agents/                       # Issue tracker, triage, domain, and retrospective conventions
│   └── design/                       # Durable designs, such as package validation
├── cc-customize/                     # Claude Code model, statusline, and prompt config skills
├── core-hooks/                       # Safety and workflow hooks plugin
├── creator-skills/                   # Scientific content creation plugin
├── dev-skills/                       # Development workflow plugin
├── productivity-skills/              # Personal productivity plugin
└── pymol-skills/                     # PyMOL molecular visualization plugin
```

Each plugin directory holds `.claude-plugin/plugin.json`, a
`.codex-plugin/plugin.json` when the plugin supports Codex, and its
components, resources, and any tests (see
[Repository and package boundaries](CONTRIBUTING.md#repository-and-package-boundaries)).
[Skills for more than one host](CONTRIBUTING.md#skills-for-more-than-one-host)
names each host's skill directory, and [Available Plugins](#available-plugins)
describes each plugin and lists its skills.

A plugin that ships to Antigravity also holds these files:

- `.antigravity-plugin/plugin.json`, the Antigravity manifest. It registers
  the plugin for Antigravity; no Antigravity marketplace registry exists.
- `antigravity-skills/`, the Antigravity copies of its skills.
- A root `hooks.json` for its hooks and a root `mcp_config.json` for its MCP
  servers, when the plugin has them.
- `claude-agents/` for its Claude Code agents, when it has them. Antigravity
  loads `agents/`, so such a plugin has no `agents/` folder.

## Available Plugins

### Development Skills (`dev-skills`)
Development workflows, repository hygiene, documentation, and review.

**Skills:**
- **repo-cleanup**: Remove merged worktrees and branches, prune the upstream remote, reconcile completed issues, delete the planning folders of completed issues, and update the Default Branch
- **step-workflow**: Step-based file naming and folder organization using numbered prefixes (01_, 02_, 03_) for clear workflow order
- **goal-rubric**: Draft a binary pass/fail rubric and a ready-to-paste `/goal` completion condition for Claude Code, Codex, or Antigravity
- **doc-update**: Update existing documentation to current project truth and audit it against a documentation quality rubric
- **grill-with-research**: Research the project before each round of Matt’s grilling interview, drop the questions that research can settle, and ask the rest in dependency order with evidence and a recommendation; research can run scripts in an untracked planning folder; requires the Matt skills plugin
- **matt-automode**: Run Matt’s planning-to-merge workflow without human checkpoints; grill with grill-with-research and answer its questions itself, reuse completed grilling, and end each run with a retro that only proposes issues; requires the Matt skills plugin
- **pressure-test**: Run an independent adversarial review of a design, plan, PR, rubric, or decision and save a conclusion. The read-only critic comes from another model family: GPT through the Codex CLI in Claude Code and Antigravity, and Claude through the Claude Code CLI in Codex. In Antigravity, the skill stops when the agent runs a GPT-family model. The user or a calling skill can choose the critic model from the two allowed models of its family. Another skill can call it with several questions; the conclusion shows the critic's assessment of each question
- **sci-project-layout**: Set up or adopt the layout of a scientific Python research project, and find where a file goes in it: one store for data and results that every worktree finds, one folder for each experiment and each run, and read-only cited runs for the results you keep
- **lean-tests**: Check a pytest suite without changing a file: run time, the slowest tests and fixtures, flaky or order-dependent tests, tests that check nothing, coverage-subset candidates, and diff coverage of recent changes, with one recommended next mode; on request, make the suite faster without deleting a test, with ordered fixes, test tiers with time budgets, the tier commands in each agent instruction file that exists, and a before/after table; or prune redundant tests under one path, deleting a test only when a full kill matrix of bundled mutants and a written rationale show that retained tests detect the same faults, in checked batches of one commit each; or review the tests of a change: a weakening gate that fails a change to product code that also removes, skips, loosens, or rewrites an existing test, a label for each new test from a run against the base code, a mutation check that each new test detects a fault that no existing test detects, the changed lines that no test executes, and pinned requirement sources for the acceptance of an intended test change
- **project-eval**: Evaluate a feature, a design document, a running web app, or a whole project with skeptical evaluator agents; a separate verifier checks every finding before it enters one report
- **t3-project-lead**: Lead a project in T3 Code when the user invokes it: plan worker tasks with success criteria that a check can pass or fail, start each task in a T3 worker with its own worktree, judge the workers' reports, and report what waits on the user; a new lead finds open work through a read-only discovery task that reports only links; workers do every other task, even a small fix or a check, and a dev-skills hook blocks the lead's other shell commands, file reads, and file edits, and in Claude Code and Codex its reads of issue and PR text, its question tool, and its answers to a worker's question; requires T3 Code

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
- **t3-project-lead**

project-eval has no Codex copy by decision ([#313](https://github.com/aeghnnsw/cc-toolkit/issues/313)).

**Antigravity skills:**
- **doc-update**
- **goal-rubric**
- **grill-with-research**
- **lean-tests**
- **matt-automode**
- **pressure-test**
- **project-eval**
- **repo-cleanup**
- **sci-project-layout**
- **step-workflow**
- **t3-project-lead**

**t3-project-lead threads:** The lead state belongs to one T3 thread, the lead thread. Delete the lead thread only after `finish`: when T3's `worktreeOnDelete` setting is on, T3 removes a thread's worktree, and the lead state in it, when the thread is deleted. A provider or model change keeps the thread, so the lead needs no step. Run `takeover` once in a fork of the lead thread, or in a new thread bound to the lead's worktree; not after a provider change. When `start` finds no lead state in its own worktree, it lists the lead states of the other worktrees; continue that lead in its own worktree. When the lead thread is flagged:

1. Start a new thread bound to the lead's worktree, with `t3_thread_launch` and `workspaceStrategy` `existing_worktree`, on another model.
2. In the new thread, run `start`, then `takeover`.
3. Do not fork the flagged thread: a fork copies the flagged context.
4. Do not delete the flagged thread before the takeover.

### Creator Skills (`creator-skills`)
Scientific content creation for figures and presentations.

**Skills:**
- **sci-figure-format**: Publication-quality scientific figure formatting for major journals (Nature, Science, ACS, RSC)
- **sci-slides**: Academic presentation slide creation for STEM fields

**Codex skills:**
- **sci-figure-format**
- **sci-slides**

**Antigravity skills:**
- **sci-figure-format**
- **sci-slides**

### Core Hooks (`core-hooks`)
Safety guards and workflow enforcement hooks for Claude Code, Codex, and Antigravity.
In Claude Code, `safety_guard.py`, `pre_git_hook.py`, and `zsh_traps.py` check the shell command of the `Bash` and `Monitor` tools. The `echo` quoting of `zsh_traps.py` applies only to a `Bash` command: for a `Monitor` command, the hook blocks the unquoted separator. A `Monitor` call without a command, such as its `ws` (WebSocket) form, is allowed.

**Hooks:**
- **safety_guard.py**: Blocks an `rm` of a wildcard target, `/`, `.`, a path with `..`, a `~` or `$HOME` path, the temporary directory root or `/tmp` itself, or a system path such as `/usr`, `/etc`, or `/var`. A named path inside `$TMPDIR` is allowed. Also blocks a command that prints every environment variable: `env` or `printenv` with no command, `export`, `declare`, or `typeset` with only options, and a bare `set`. `env | cut -d= -f1` and `env | awk -F= '{print $1}'` list the names only, and `--version` or `--help` prints no variable. The guard skips a quoted heredoc body only when the whole command is a `cat` file write, a `git commit` message, or a `gh` PR or issue body in one of the allowed forms (see [#445](https://github.com/aeghnnsw/cc-toolkit/issues/445)); it scans every other heredoc body. An error that the guard catches, such as unreadable input, blocks the tool call, and the message names the error and how to turn off the plugin. When the guard allows a call and then cannot write its log, the call runs, and one warning line on stderr names the error and the log file (see [#535](https://github.com/aeghnnsw/cc-toolkit/issues/535))
- **pre_git_hook.py**: Checks Git policy, including branch prefixes and bulk staging (`git add .`, `git add -- .`, `git add :/`, and `-A` or `--all` with no path). Blocks AI attribution in a commit message, in PR and issue text, in the squash message of `gh pr merge`, and in a file that `--body-file`, `-F`, or `--file` names. Blocks a test-plan heading in a PR description, and a `gh pr merge` without `--match-head-commit <full head SHA>`. Blocks `git grep -E` with an escape such as `\b`, `\s`, or `\d`, which macOS reads as a plain character; the message says to use `-P`
- **zsh_traps.py**: When the shell is zsh, quotes separators with two or more leading equals signs in simple `echo` commands, with optional `-n`. An `echo` command can stand alone or be part of a list that `;`, `&&`, `||`, or newlines join, as in `cat a; echo =====; cat b`. Labels can use ASCII letters, digits, and underscores, as in `echo =====CODEX`. Current Claude Code and Codex apply the corrected input through their normal permission checks. Other commands keep the existing checks, and so does a command with a heredoc, or with a quote, backslash, backtick, `$`, or `#` before the end of the last `echo` command to quote: the hook blocks each unquoted `=name` word that zsh expands, also when `name` is a command, and warns about unsplit variables, unmatched globs, and a letter after `$NAME:`, which zsh can read as a modifier. It reads the parts of a word that can expand to nothing, as in `""==a`, brace expansion, array elements, the parts after a `:` of an assignment value, `[[ ]]` operands, and the default word of `${name:-word}`. It also blocks a command whose substitutions nest deeper than it reads when the unread text holds an `=`, and a command that it fails to read. The block of an `=name` word that names no command ends with the corrected command, which has a backslash before the `=` of each such word, when the command has no heredoc and at most 1500 characters. It also warns when the output of `pytest`, `python -m unittest`, or `validate_packages.py` goes through a pipe to `tail` or `head` without `set -o pipefail`, because the pipeline can then exit 0 when the tests fail. In Claude Code, it blocks a zsh parameter flag such as `${(f)...}`, which the Claude Code safety check rejects with a message about `rm`. It also warns about GNU options that the BSD tools of macOS reject (`head -n 0`; `cat -A`, `-E`, `-T`, or a long option), and about `timeout` when no `timeout` command is on `PATH`; Antigravity skips these three checks. Each message names the fix
- **post_tool_use.py**: Logs tool executions to `logs/post_tool_use.jsonl` in the project directory
- **system_notification.py**: Plays sound notifications on task completion
- **stale_install_check.py**: Claude Code and Codex, at session start. For each stale install, an installed copy that is older than the same plugin in the marketplace clone of the same home, the session gets the update commands. The check reads the Claude Code plugin folders in `CLAUDE_CODE_PLUGIN_CACHE_DIR`, `CLAUDE_CONFIG_DIR`, and `~/.claude`, and the Codex homes `CODEX_HOME`, `~/.codex`, and `~/.codex-t3/*`. Codex homes that share their installed copies and marketplace clone through links get one command set. The check is on by default, because an opt-in variable does not reach the sessions that T3 Code starts, and no known route reaches the Codex app server; one run takes 0.03 to 0.06 s. Set `CORE_HOOKS_STALE_CHECK=0`, for example in the `env` setting of Claude Code or in the shell that starts Codex, to turn the check off. Set `CORE_HOOKS_STALE_CHECK=1` to also compare the installed copies with the default branch when the session starts in a cc-toolkit checkout. That comparison stays opt-in, because it warns after each merge. Codex runs the check only after you trust the core-hooks hooks; see [Updates and removal](#updates-and-removal). Antigravity does not run the check, because an Antigravity hook cannot warn without blocking

In Antigravity, a root `hooks.json` runs the same scripts, and a block
shows its reason. An Antigravity hook cannot warn without blocking the
command. So each zsh trap blocks the command, and the `echo` quoting
becomes a block that names the corrected command. The hooks drop the Git
policy reminders and the branch-prefix message. The unmatched-glob check
does not run, because a command can create the files before its glob. The
pipefail warning and the `head`, `cat`, and `timeout` warnings do not run,
because they must not block a command. A
safety or Git policy hook that cannot read its input blocks the command.
Antigravity has no SessionEnd or SubagentStop event; the sound plays when
the agent stops.

### Productivity Skills (`productivity-skills`)
GTD workflows through a connected Supabase account, plus native macOS Calendar. GTD uses a GTD binding (a private project reference and owner UUID) and `uv` on `PATH`, which supplies Python 3.11+. Run `gtd-setup` to create a GTD database or to bind an existing one on a new computer. `gtd-setup` can also turn on agent captures: agents then add inbox items when a task waits on you. In Antigravity, connect the Supabase MCP server with `agy mcp add supabase https://mcp.supabase.com/mcp`, then sign in when Antigravity asks. See the [cloud workflow](productivity-skills/references/gtd-cloud.md).

**Skills:**
- **calendar-manager**: Manage macOS Calendar events via EventKit CLI
- **gtd-inbox**: Capture thoughts and tasks into the cloud GTD inbox, including agent captures
- **gtd-process**: Process cloud inbox items into linked projects or actions
- **gtd-project**: Review and manage cloud GTD projects and their actions
- **gtd-next**: Select cloud GTD actions with available native Calendar context
- **gtd-overview**: Read-only cloud project and action inventory with shared status rules
- **gtd-setup**: Create a cloud GTD database or bind an existing one, verify it, and optionally turn on agent captures (user-invoked)

**Codex skills:**
- **calendar-manager**
- **gtd-inbox**
- **gtd-process**
- **gtd-project**
- **gtd-next**
- **gtd-overview**
- **gtd-setup**

**Antigravity skills:**
- **calendar-manager**
- **gtd-inbox**
- **gtd-process**
- **gtd-project**
- **gtd-next**
- **gtd-overview**
- **gtd-setup**

### PyMOL Skills (`pymol-skills`)
PyMOL molecular visualization control via MCP server for Claude Code, Codex,
and Antigravity. The three hosts share the local Python bridge and socket
plugin. See the [installation guide](pymol-skills/README.md).

**Skills:**
- **pymol-mcp**: Control PyMOL through natural language for protein visualization and structural analysis
- **pymol-setup**: Set up the PyMOL socket plugin, or diagnose missing PyMOL MCP tools and connection failures

**Codex skills:**
- **pymol-mcp**
- **pymol-setup**

**Antigravity skills:**
- **pymol-mcp**
- **pymol-setup**

### Claude Code Customization (`cc-customize`)

**Skills:**
- **model-config**: Configure model, effort level, and auto-compact window
- **statusline-setup**: Configure the Claude Code statusline
- **claude-prompt-config**: Back up and replace the global Claude Code instruction file (`${CLAUDE_CONFIG_DIR:-$HOME/.claude}/CLAUDE.md`) on this machine or a remote host; show the lines that the new file drops and keep the GTD agent-capture section (user-invoked)

## Plugin System Benefits

1. **Modular**: Each plugin is self-contained and portable
2. **Scalable**: Easy to add new skills, agents, hooks, or commands to any plugin
3. **Standard**: Follows Claude Code and Codex plugin packaging conventions where supported
4. **Maintainable**: Clear separation of concerns between plugins
5. **Shareable**: Individual plugins can be distributed independently

## Usage

Run these commands in a terminal with Git and the matching host CLI installed.
The commands download from GitHub; a local checkout is not required. The
Claude Code and Codex examples install `creator-skills`. Replace that name with
another plugin from [Available Plugins](#available-plugins) when needed.

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

### Antigravity

This repository has no Antigravity marketplace registry. Install one plugin
directory from its GitHub URL with the Antigravity CLI, `agy`. Replace
`<plugin>` with the directory name of the plugin:

```bash
agy plugin install https://github.com/aeghnnsw/cc-toolkit/tree/master/<plugin>
```

Install only a plugin whose directory holds `.antigravity-plugin/plugin.json`.
For a plugin without that manifest, `agy plugin install` converts the Claude
Code plugin, and the result can lose parts of it. See the
[Antigravity plugin guide](https://antigravity.google/docs/plugins) for other
commands.

#### Antigravity in T3 Code

T3 Code runs Antigravity with a private profile for each Antigravity
provider instance, not with `~/.gemini`. Each profile is a folder in
`~/.t3/userdata/providers/antigravity/`. T3 Code sets `GEMINI_HOME` to the
profile and does not link `~/.gemini/config/plugins/` into it, so its
Antigravity does not load the plugins in that folder. `agy plugin install`
ignores `GEMINI_HOME` and installs into `~/.gemini/config/plugins/`
(measured with `agy` 1.5.13).

To load an installed plugin in T3 Code, link its folder into the profile.
Replace `<profile>` with the profile folder name and `<plugin>` with the
plugin directory name:

```bash
profile=~/.t3/userdata/providers/antigravity/<profile>
mkdir -p "$profile/config/plugins"
ln -s ~/.gemini/config/plugins/<plugin> "$profile/config/plugins/<plugin>"
```

Then start a new T3 Code Antigravity session. One check on 2026-11-21, with
T3 Code's Antigravity binary 1.5.14, measured this path: the session listed
the skills of four linked plugins, and the linked Core Hooks blocked
`git add -A`. No other version was checked.

### Updates and removal

The examples use `creator-skills`. Replace that name with the plugin you
want to manage.

To update the installed Claude Code copy:

1. Run `claude plugin marketplace update cc-toolkit`.
2. Run `claude plugin update creator-skills@cc-toolkit --scope user`. For a
   project or local installation, use that installation's scope instead.
3. Start a new Claude Code session.

To update the installed Codex copy (measured with codex-cli 0.172.0):

1. Run `codex plugin marketplace upgrade cc-toolkit`. When the marketplace
   has new commits, the command updates the marketplace clone. It then
   installs the version in the marketplace clone of each installed
   cc-toolkit plugin, also of a disabled plugin, and removes the old
   version folders. So it updates all installed cc-toolkit plugins, not
   only the plugin that you want to update. It does not install a plugin
   that is not installed.
2. If step 1 printed "Marketplace `cc-toolkit` is already up to date.", the
   command changed no installed copy, and a stale install stays. Then run
   `codex plugin add creator-skills@cc-toolkit`. It installs the version in
   the marketplace clone and removes the old version folder.
3. Restart each running Codex session, because the version folder that it
   loaded at start no longer exists. Start new sessions as usual.

These commands update the Codex home in `CODEX_HOME`, by default `~/.codex`.
To update another home, set `CODEX_HOME` for each command, for example
`CODEX_HOME=~/.codex-t3/codex-2 codex plugin add creator-skills@cc-toolkit`.
A home that links its `plugins` and `.tmp` folders to another home shares
the installed copies and the marketplace clone of that home, so one update
covers both homes.

Codex runs a plugin hook only after you trust it, and the trust ends when a
file of the plugin changes (measured with Codex 0.172.0). So after you
install or update `core-hooks`, also through a marketplace upgrade for
another plugin, trust its hooks again: start the Codex TUI
and choose "Review hooks" or "Trust all and continue" at the "Hooks need
review" prompt, or use `/hooks`. `codex exec` and the Codex app server,
which T3 Code uses, show no prompt. Until you trust the hooks, they skip a
new hook, such as the SessionStart stale-install check, without a message,
and they report each changed hook as failed with "plugin contents changed;
hook approval required".

To update the installed Antigravity copy:

1. Run `agy plugin install https://github.com/aeghnnsw/cc-toolkit/tree/master/creator-skills`
   again. `agy` has no plugin update command. With `agy` 1.5.14, the install
   replaces the installed folder, and a link to it in a T3 Code profile
   still finds the new copy.
2. Start a new Antigravity session.

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

To uninstall the Antigravity copy, run
`agy plugin uninstall creator-skills`. With `agy` 1.5.14, the uninstall does
not remove a link in a T3 Code profile, so delete
`~/.t3/userdata/providers/antigravity/<profile>/config/plugins/creator-skills`
too.

Start a new host session after changing its plugins. See the
[Claude Code management guide](https://code.claude.com/docs/en/plugins/install#manage-plugins-from-your-shell)
and [Codex plugin configuration](https://developers.openai.com/plugins/build/plugins#enable-or-disable-a-plugin-for-a-repo)
for scope and configuration details.
