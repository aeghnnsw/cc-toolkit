# Contributing to cc-toolkit

cc-toolkit uses one repository for development and plugin distribution.
Contributor documentation lives at the root and under `docs/`; installable
components live inside each plugin directory. Follow
[CLAUDE.md](CLAUDE.md) for the issue, worktree, and PR workflow.

## Coding standards

No repository-wide linter, formatter, or type checker is configured. Follow
the surrounding code style. Do not reformat unrelated code.

Wrap ordinary prose in `CLAUDE.md` and `CONTRIBUTING.md` at 78 characters.
Exempt headings, tables, links, and code examples, including inline commands.
Root `CLAUDE.md` has a budget of 450 words, counted as `wc -w` counts them,
and a fixed set of sections. [tests/test_steering_budget.py](tests/test_steering_budget.py)
checks both. Move detail to `CONTRIBUTING.md` or `docs/agents/`, and leave a
pointer in `CLAUDE.md`.
Other Markdown files follow their surrounding style.
[tests/test_prose_width.py](tests/test_prose_width.py) checks this rule and
prints `file:line:width` for each line to rewrap.

Prefer the Python standard library for helpers. Preserve existing
standard-library-only entry points. The table below names the current
third-party Python dependencies. Keep runtime dependency declarations with
the plugin. Test dependencies are separate from runtime dependencies.

### Python requirements

These are declared minimum versions, not a tested compatibility matrix.
The root tooling's Python requirement does not set the minimum for
installed plugins. A plugin script declares its minimum in a
`requires-python = ">=X.Y"` line of PEP 723 inline script metadata.
[tests/test_script_python_floor.py](tests/test_script_python_floor.py) parses
each shipped Python file at that minimum, or at 3.9, the version of
`/usr/bin/python3` on macOS, when the file has no such line. It fails on an
`X | Y` annotation that Python 3.9 evaluates. It also fails when plugin
text runs a script above 3.9 with a bare `python` or `python3`; run it as
`uv run --no-project --python '>=X.Y' python <script>`. The test does not
find newer runtime APIs, such as `tomllib`.

| Component | Declared minimum | Python dependencies and exceptions |
| --- | --- | --- |
| [Root package validator](scripts/validate_packages.py), the [release step](scripts/release_changelog.py), the [version script](scripts/next_versions.py), and root tests | 3.11 | Standard library, including `tomllib`. |
| [Core Hooks](core-hooks/scripts/safety_guard.py) | 3.8 | Standard library, except [`chime` for sound notifications](core-hooks/scripts/system_notification.py). |
| [Productivity Skills: GTD SQL renderer](productivity-skills/scripts/gtd_sql.py) | 3.11 | Standard library. The connected Supabase tool executes the prepared SQL. |
| [Dev Skills: lean-tests](dev-skills/skills/lean-tests/SKILL.md) | 3.9 | CLI helpers use the standard library. Target test runs need `pytest`; coverage runs also need `pytest-cov` and `coverage`. |
| [Dev Skills: retrospective session script](dev-skills/scripts/retro_sessions.py) | 3.9 | Standard library. |
| Other Dev Skills helpers and templates | 3.9 | Standard library. The [scientific project template](dev-skills/skills/sci-project-layout/templates/paths.py) uses Python 3.9 APIs. |
| [Creator Skills: slide linter](creator-skills/skills/sci-slides/SKILL.md) | 3.9 | Standard library. |
| [PyMOL Skills: MCP bridge](pymol-skills/pymol_mcp_server.py) | 3.10 | `mcp[cli]>=1.0.0,<2`. |

The PyMOL socket plugin runs in PyMOL's own interpreter. It declares no
minimum, so the test parses it at 3.9. The bridge requirement does not
apply to that separate process.
Productivity Skills also uses Swift for native Calendar.
CC Customize uses Bash and `jq`, with Git for status information.
Dev Skills `repo-cleanup` runs `lsof` and `ps` to find live sessions.
See [Verification](#verification) for test commands and test prerequisites.

## Repository and package boundaries

The Claude Code and Codex marketplace registries select plugin directories
such as `dev-skills/` and `core-hooks/`. Each directory contains that
plugin's manifests, components, and supporting resources. Keep resources
needed by an installed plugin inside its directory. Antigravity has no
registry in this repository. A plugin directory that a registry selects is
registered for Antigravity when it holds `.antigravity-plugin/plugin.json`.

- Edit the plugin directory in this repository, not an installed copy under
  `~/.claude/plugins/cache/` or `~/.codex/plugins/cache/`.
- When you add, remove, or rename a plugin, or change its source path,
  update the marketplace registries: `.claude-plugin/marketplace.json` for
  Claude Code and `.agents/plugins/marketplace.json` for Codex. To register
  a plugin for Antigravity, add its Antigravity manifest.
- When you add, remove, or rename a plugin or a skill, update its entries in
  [README.md](README.md).
- When you rename or remove a skill or an agent, update each
  `<plugin>:<name>` reference to it.
  [tests/test_skill_references.py](tests/test_skill_references.py) fails on
  a reference that names no skill or agent of a plugin in this marketplace.
- To retire a plugin, tag the last commit that has it, then delete its
  folder from master. `tests/test_registered_skills.py` fails on a tracked
  `SKILL.md` outside a registered plugin directory.
- Before you change component paths, read the plugin's host-specific
  manifests and [host ownership](docs/design/package-validation.md#host-ownership).

### Skills for more than one host

A skill has one copy for each host that ships it: `skills/<name>/` for
Claude Code, `codex-skills/<name>/` for Codex, and
`antigravity-skills/<name>/` for Antigravity. Change every copy in the same
pull request. Keep differences host-specific, such as tool names,
invocation, and plugin-root paths.

For an example, see `creator-skills/skills/sci-slides/`,
`creator-skills/codex-skills/sci-slides/`, and
`creator-skills/antigravity-skills/sci-slides/`.

The root test [tests/test_host_copies.py](tests/test_host_copies.py)
compares each copy with the Claude copy: its file list, and the
`description` line, body, and text of each shared file. It also checks the
frontmatter, invocation policy, and tool-name rules below. A difference
fails unless an allowlist at the end of the test lists it. List only
host-specific lines in `HOST_LINES`, and files that only one copy has in
`HOST_FILES`. A drifted copy names its repair issue in `UNMATCHED`,
`INVOCATION_EXCEPTIONS`, or a `#` comment in `HOST_LINES`. An entry that no
longer matches a difference also fails; delete it.

A new skill also needs an entry in each [README.md](README.md) list of its
plugin: **Skills:** with a one-line description, and **Codex skills:** and
**Antigravity skills:** with its name for each host that ships it. When the
Codex manifest's `interface.longDescription` describes the purposes of the
plugin's skills, add the purpose of the new skill. When a change alters the
purpose of a skill, update that purpose in `longDescription` and in the
README **Skills:** line.
[tests/test_readme_catalog.py](tests/test_readme_catalog.py) checks the
README lists against the skill folders of each host. Its `LONG_DESCRIPTION`
table gives the phrase of `longDescription` that names the purpose of each
Codex skill; add an entry for a new Codex skill.

- **Frontmatter.** Claude copies carry `name`, `description`, and usually
  `version`. Codex copies carry only `name` and `description`. Antigravity
  copies carry `name` and `description`, and
  `disable-model-invocation: true` when the skill is user-invoked. They
  carry no `version`. Run the skill-creator validator on Codex copies only.
  Its command is in [Verification](#verification).
- **Invocation policy.** To make a skill user-invoked, set
  `disable-model-invocation: true` in the Claude and Antigravity
  frontmatter, and `allow_implicit_invocation: false` under `policy:` in
  the Codex copy's `agents/openai.yaml`. A Codex copy without that file is
  not user-invoked. In Antigravity, the user runs a skill as `/<name>`.
  All copies of a skill set the same policy. The root test also pins the
  policy of each skill in its `PINNED_POLICY`, such as repo-cleanup, which
  workflows run.
- **Shell blocks.** A skill's shell blocks run in the user's shell, which
  can be bash or zsh. Write each block to run in both shells, with the BSD
  tools of macOS and the GNU tools of Linux. Make a temporary folder with
  `mktemp -d "${TMPDIR:-/tmp}/<name>.XXXXXX"`, and a temporary file with
  the same template without `-d`. Write a placeholder without a space, such
  as `<work-dir>`.
  [tests/test_skill_shell_blocks.py](tests/test_skill_shell_blocks.py)
  parses each shell block of a shipped Markdown file with `bash -n` and
  `zsh -n -f`, and runs the Core Hooks zsh trap check on it.
  [tests/test_mktemp_form.py](tests/test_mktemp_form.py) checks each
  `mktemp` call. For a test that runs a skill's blocks, see
  `dev-skills/tests/test_pressure_test_models.py`.
- **Paths.** A link relative to `SKILL.md` reads the same in every copy. A
  plugin-root path differs: `${CLAUDE_PLUGIN_ROOT}/...` in the Claude copy,
  and `<plugin-root>/...` in the Codex and Antigravity copies. A command
  that runs a file inside the skill directory can write `<skill-dir>/...`,
  which reads the same in every copy.
- **Registration.** List each file that a skill links to or runs under the
  plugin's `resources` in `package-validation.json`, once per host that
  ships it. A link to a `SKILL.md` that the same host discovers needs no
  entry. The validator requires only listed resources; it does not find
  them from links in prose. The skill link test,
  [tests/test_skill_links.py](tests/test_skill_links.py), enforces this
  rule for every copy, including Antigravity copies. It also checks that
  each link target exists in the plugin and each anchor matches a heading.

#### Antigravity copies

Start an Antigravity copy from the Codex copy when one exists. The Codex
copy has no argument placeholders and already uses `<plugin-root>` paths.
Otherwise, start from the Claude copy. Then write each host concept as this
table shows:

| Concept | Antigravity copy |
| --- | --- |
| Plugin root | `<plugin-root>`: two directories above the folder of the `SKILL.md` file |
| Skill folder | `<skill-dir>` |
| Ask the user | `ask_question` for a choice; plain text otherwise |
| Task list or plan | A Markdown task artifact; Antigravity has no task-list tool |
| Subagent | `invoke_subagent` with `TypeName: "self"`, a `Role`, and a `Prompt` |
| Fan-out workflow | `run_workflow` |
| Load another skill | Read its `SKILL.md`. The user runs a skill as `/<name>` |
| Shell | A plain verb, such as "run the command"; it runs in the user's shell |
| Web search | A plain verb, such as "search the web" |
| Arguments | No argument placeholders; write "the user's request" |
| Instruction files | `GEMINI.md` and `AGENTS.md`. Global copies load from `~/.gemini/` and `~/.gemini/config/`; write to `~/.gemini/GEMINI.md`, which the Antigravity docs list for every surface |

The Antigravity agent reported its tool names itself (`agy` 1.5.13).
Antigravity's builtin skills confirm only `ask_question`,
`invoke_subagent`, and `run_workflow`. A copy names only these tools. For
another action, write a plain verb. T3 Code tools, such as `delegate_task`,
keep the same names in every copy, because T3 gives each host the same tool
instructions. The root test fails on a Claude Code or Codex tool name in an
Antigravity copy, and on a Claude Code tool name in a Codex copy.

The Antigravity manifest declares `"skills": "./antigravity-skills/"` when
the plugin has skills.

#### Shadowing

Antigravity always scans the `skills/` folder of a plugin. It also loads
the folders that the `skills` field of the Antigravity manifest declares.
When `skills/` and a declared folder both hold a skill with the same name,
the skill in the declared folder wins. A skill that is only in `skills/`
still loads, so a Claude copy without an Antigravity copy runs in
Antigravity. Thus every `skills/<name>` of a plugin that is registered for
Antigravity needs a same-named Antigravity copy. Otherwise, the package
validator fails. Its message names the skill and the expected folder.

#### Claude agents in an Antigravity plugin

Antigravity loads agent files from `agents/`. Its loader skips a Claude
agent file, because the Claude `tools` value is a string, not a list, and
the Claude `model` value is not an Antigravity model tier. Claude Code also
loads `agents/`, and adds the declared agent paths to it. Thus a plugin
that ships to Antigravity keeps its Claude agents in `claude-agents/` and
has no `agents/` folder. In `.claude-plugin/plugin.json`, declare the
agents as a list of `.md` files, for example
`"agents": ["./claude-agents/<name>.md"]`. Claude Code rejects a folder
string in this field. The agent name in Claude Code stays
`<plugin>:<name>`.

### Argument placeholders

Claude Code replaces `$N`, `$ARGUMENTS`, and the argument names that the
`arguments` frontmatter declares in a skill or command body, including code
blocks. Codex and Antigravity do not replace them.
`tests/test_skill_placeholders.py`, one of the
[root tests](#package-and-release-validation), fails on each unescaped
placeholder in a Claude copy and prints the fix.

An Antigravity copy has no argument placeholder. It has no `$ARGUMENTS`
form, no backslash-escaped `\$N`, and no `arguments` frontmatter.
Antigravity keeps the backslash of `\$N` in the text that the agent reads.
Write "the user's request" instead. The placeholder test checks Antigravity
copies for these forms.

## Repository search

From the repository root, search with `git grep`. It skips untracked files
and the other worktrees under `trees/` and `.claude/worktrees/`; pass
`--untracked` to include new files.

The entries in `CHANGELOG.md` and `changelog.d/` can describe replaced
behavior. To search current text only, exclude them:

```bash
git grep -n <term> -- ':!CHANGELOG.md' ':!changelog.d'
```

## Changelog entries

The root [CHANGELOG.md](CHANGELOG.md) is the only maintained changelog. A
feature pull request does not edit `CHANGELOG.md`. The pull request adds
its bullets in a new entry file, `changelog.d/<N>.md`, where `<N>` is the
number of the linked issue. When the pull request closes several issues,
it adds one entry file, and `<N>` is the lowest issue number. When another
change already uses that name, add lowercase words, as in
`changelog.d/<N>-<words>.md`. Two pull requests thus add different files,
and a rebase does not conflict in a changelog file. The
[release step](#release-step) moves the bullets into `CHANGELOG.md`.

An entry file holds one or more of the headings `### Added`, `### Removed`,
and `### Changed`, each with its bullets:

```markdown
### Changed

- <plugin> (<Host> <version>): <change>. See [#N](https://github.com/aeghnnsw/cc-toolkit/issues/N).
- Repository: <change>. See [#N](https://github.com/aeghnnsw/cc-toolkit/issues/N).
```

For a pull request that closes several issues, each bullet names the other
issues inline as bare numbers without a link, as in `(#555, #556)`. The
bullet ends with one `See` link to the lowest issue number:

```markdown
- Repository: <change> (#555, #556). See [#554](https://github.com/aeghnnsw/cc-toolkit/issues/554).
```

Name each host whose manifest version the change increases, in the order
Claude Code, Codex, Antigravity. When the versions differ, give each host
its version: `Claude Code <version>, Codex <version>, Antigravity <version>`.
When the named hosts ship the same version, write the version once, as in
`Claude Code and Codex <version>`. For one host, write the host and its
version, as in `<plugin> (Antigravity <version>)`. Start a change outside the
plugin directories with `Repository:` and give no version. The plugin entry
also covers the README catalog entry and the `package-validation.json`
lines that ship with the plugin change. When a pull request changes a
plugin and other files outside it, write one plugin entry and one
`Repository:` entry. A change only to contributor-only files of a
plugin, such as its `tests/`, needs no version and is also a `Repository:`
entry. Link the issue that the pull request closes; for a spec with
tickets, link the ticket. When the pull request closes several issues,
link the lowest issue number, as the form above shows.

The package validator checks each new bullet: a bullet whose text is not in
`CHANGELOG.md` or in an entry file at the merge base. An edited bullet is
new; a moved bullet is not. A new bullet is one line that uses the form
above, has at most 600 characters, and is under one of the three headings
of an entry file. Put more detail in the pull request. A plugin bullet uses
the registered plugin name and names each host whose manifest version
increased, at its current manifest version. Each plugin whose manifest
version increases needs a new bullet. A branch adds at most one new bullet
for each plugin and one new `Repository:` bullet. The validator counts the
new bullets of all new or changed entry files under all three headings. A
new bullet in `CHANGELOG.md` fails.
Older entries are under `## 2026-11-22`.

### Release step

The release step moves the bullets of each entry file into
`## [Unreleased]` of `CHANGELOG.md`, under the same headings, and deletes
the files. The entry file that the newest commit added under its current
name comes first, and each file keeps the order of its bullets:

```bash
uv run --no-project --python '>=3.11' python scripts/release_changelog.py
```

The maintainer runs the release step, or asks an agent to run it, on a
branch from `master`, in a pull request that changes nothing else. A
feature pull request never runs it. Run it between batches of parallel
pull requests, for example, so that no open pull request must rebase over
it. The release step needs no version increase. The package validator fails a
branch that deletes an entry file of the merge base and changes another
file, or that drops a bullet of a deleted entry file from `CHANGELOG.md`.

## Versions and rebases

Set the plugin and skill versions with the version script when the pull
request is ready, and again after each rebase. First run
`git fetch origin master`:

```bash
uv run --no-project --python '>=3.11' python scripts/next_versions.py --base origin/master
```

For each plugin that the branch changes, the script sets the `version` of
each affected host's manifest, and of each changed skill that has one, to
the next free version: the next version above `origin/master`. A host that
a new plugin bullet of the branch names also gets an increase, for example
after a change only to the plugin's tests. It raises the minor number; pass
`--part patch` for a fix, or `--part major`. A version that is already
above `origin/master` stays, so a second run changes nothing. The script
also writes the new versions into the plugin bullets of the branch's entry
files, and into each `<skill> <version>` in their text. It adds no bullet.
Then run the package validator.

When a rebase conflicts in a `version`, keep either side, then run the
script. Git merges equal versions from both sides without a conflict, and
so leaves the branch at the version of `origin/master`. Thus run the
script after each rebase, also after a rebase without a conflict.

When the resolution of a rebase changes no file other than versions and
changelog entries, run only the package validator locally, and let CI run
the suites on the new head. Run a suite locally again only when the
resolution changes another file.

## What belongs in Git

Classify a file by its purpose and expected lifetime, regardless of whether
a person or an agent wrote it.

| Material | Location and treatment |
| --- | --- |
| Installable skills, agents, hooks, scripts, and required resources | Commit inside the owning plugin directory. |
| Shared contributor instructions and agent configuration | Commit `CLAUDE.md`, its `AGENTS.md` symlink, and `docs/agents/`. |
| Accepted architecture decisions | Commit concise records under `docs/adr/`. |
| Agreed domain terminology | Commit a root `GLOSSARY.md` when a glossary is needed. |
| Durable designs and review conclusions | Commit under a relevant `docs/` directory and link them from the issue or relevant documentation. |
| Disposable notes, trial output, and intermediate reports | Use `.scratch/`, which is ignored. Name a planning folder `.scratch/<issue>-<slug>/`, and keep it in the main checkout, because worktree cleanup removes the ignored files of a worktree. Promote useful conclusions into shared documentation. |
| Logs, caches, local worktrees, and generated binaries | Keep out of Git using the shared `.gitignore`. |
| Personal tool settings and local-only notes | Keep outside the repository, or list exact paths in the file that `git rev-parse --path-format=absolute --git-path info/exclude` prints; linked worktrees share it. Prefer putting machine-specific agent preferences in the host's user configuration so shared repository instructions remain portable. |
| Private GTD account bindings and migration records | Keep outside this repository. |

When a change supersedes part of a design, plan, conclusion, or ADR under
`docs/`, add a superseded note at its top. Name the date and the issue, and
link the replacement. In an ADR, also mark each replaced sentence and record
the new rule with its reason in a new section; see ADR 0002 for an example.
A change that only adds facts needs no note.

## Work branches

A linked worktree is a worktree other than the main checkout. When a
session runs in a linked worktree made for it, the branch of that worktree
is the work branch. Keep its name. Before the first commit, base the work
branch on the default branch, so that a host tool that opens a pull request
for the session pushes the work branch. `--keep` stops instead of
discarding uncommitted changes:

```bash
git fetch origin
git reset --keep origin/master
```

Only a session in the main checkout makes a worktree, under `trees/`, on a
new work branch, for example:

```bash
git worktree add trees/doc-<description> -b doc-<description>
```

## Verification

Run these checks locally before opening a pull request. On each pull
request, [.github/workflows/ci.yml](.github/workflows/ci.yml) runs the
package validator, the root tests, and the plugin test suites in one job on
Linux and one on macOS. It does not run the Codex skill validator or `agy`.
There is no repository-wide build command. Run every row that matches your
change from the repository root:

| Change | Check |
| --- | --- |
| Any change | `git diff --check` |
| Documentation | Check accuracy, relative links, and referenced paths. |
| Markdown prose | `python3 dev-skills/scripts/avoid_terms.py --base origin/master`. For a file that no diff holds, such as a draft of an issue under `.scratch/`, name it: `python3 dev-skills/scripts/avoid_terms.py <file>...`. Where a listed line names a glossary concept, use the glossary term. |
| A skill | Check its frontmatter and invocation guidance. |
| A plugin file, an entry file, a marketplace registry, `package-validation.json`, or the validator | `uv run --no-project --python '>=3.11' python scripts/validate_packages.py --base origin/master` |
| A skill, an agent, a plugin Python file, a root Python helper or test, `README.md`, `CLAUDE.md`, `CONTRIBUTING.md`, a Codex manifest, `allowed-models.json`, or `package-validation.json` | `uv run --no-project --python '>=3.11' python -m unittest discover -s tests -p 'test_*.py'` |
| A Codex copy of a skill | `uv run --no-project --with pyyaml python "${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py" <plugin>/codex-skills/<name>` |
| A plugin with an Antigravity manifest, when `agy` is installed | `agy plugin validate <plugin>` |
| `allowed-models.json`, a `pressure-test` `SKILL.md`, or code or a test in `dev-skills` | `uv run --no-project --python '>=3.11' --with pytest --with pytest-cov python -m unittest discover -s dev-skills/tests -p 'test_*.py'` |
| Code or a test in `cc-customize`, `core-hooks`, `creator-skills`, or `pymol-skills` | `python3 -m unittest discover -s <plugin>/tests -p 'test_*.py'` |
| Code or a test in `productivity-skills` | `uv run --no-project --python '>=3.11' python -m unittest discover -s productivity-skills/tests -p 'test_*.py'` |
| A GitHub Actions workflow | Validate the YAML. Check its triggers and permissions against the intended behavior. |

`agy plugin validate` warns about a skill-name collision for each Claude
copy that an Antigravity copy shadows (see [Shadowing](#shadowing)). These
warnings are expected. Do not pass `--strict`, because it fails on them.

Core Hooks tests require Python and `uv` on `PATH`. The `cc-customize`
tests run its scripts with `bash`, and the statusline-setup shell blocks in
`bash` and `zsh`. Without `jq`, the `set_autocompact.sh` and statusline
checks skip. Without `zsh`, the zsh cases skip. Before you run a plugin
suite, read [Plugin runtime tests](#plugin-runtime-tests).

### Package and release validation

Run the package validator for the changes that the
[Verification](#verification) table lists, and again after a rebase; see
[Versions and rebases](#versions-and-rebases). Run `git fetch origin master`
first. The command is read-only:

```bash
uv run --no-project --python '>=3.11' python scripts/validate_packages.py --base origin/master
```

Shipped changes need a greater plugin `version` in each affected host's
manifest, and a greater skill `version` when the skill has one. Set them
with the [version script](#versions-and-rebases). A changed skill that
loses its `version` line fails. The validator also checks the new bullets
of entry files; see [Changelog entries](#changelog-entries). The
[package validation design](docs/design/package-validation.md) describes
each check, the rules in [package-validation.json](package-validation.json),
and the error messages.

The validator checks an Antigravity registration as follows:

- The Antigravity manifest `name` equals the registered name of the plugin,
  and its `version` has numeric `major.minor.patch` parts. The manifest
  uses only the keys of the Antigravity manifest schema. When the Claude Code
  and Codex registries give the plugin directory different names, the
  validator fails.
- Each `skills/<name>` has a same-named skill in a declared `skills` path
  (see [Shadowing](#shadowing)). A declared `skills` path is not `skills/`.
- Antigravity owns the `.antigravity-plugin/` folder and its discovery
  paths: the declared `skills` paths, a root `hooks.json`, a root
  `mcp_config.json`, `agents/`, and `rules/`. `skills/` affects Antigravity
  only when the manifest declares no `skills` path.
- A `hosts` list in `package-validation.json` can name `antigravity`.
- A new Antigravity registration needs no version increase. After that, a
  change that affects Antigravity needs a greater Antigravity manifest
  `version`. An Antigravity-owned file and a shared file both affect it.
- A Claude manifest `agents` field can list `.md` files (see
  [Claude agents in an Antigravity plugin](#claude-agents-in-an-antigravity-plugin)).
  Claude Code owns them, and it also owns `agents/`, because it loads that
  folder too.

The root tests are under `tests/`; [Verification](#verification) gives when
and how to run them. A test reads a release version from its manifest or
`SKILL.md`; it does not hold one as a literal.
[tests/test_no_version_pins.py](tests/test_no_version_pins.py) fails on each
version string in a `tests/*.py` or `<plugin>/tests/*.py` file that its
`FIXTURE_VERSIONS` list does not give for that file. List there only
versions that a test writes to a fixture or quotes from another tool.

### Plugin runtime tests

The table in [Verification](#verification) gives the command for each suite.

The `productivity-skills` suite needs `uv` and PostgreSQL tools (`initdb`,
`pg_ctl`, and `psql`). `uv` supplies Python 3.11+.

The `dev-skills` suite takes about 5 minutes on an idle machine, and
longer when other test runs share the machine. Of this time,
`dev-skills/tests/test_codex_critic.py` takes about 1.5 minutes, and
`dev-skills/tests/test_lean_tests.py` about 1 minute.

To run a full suite, put `python3 dev-skills/scripts/run_suite.py --` before
its command. A suite is one command in one folder. The script takes one
lock for each suite, and all worktrees of the repository share each lock.
So two runs of the same suite run one at a time, and different suites run
in parallel. A repository's merge-lock tool can make the runs of the other
worktrees wait with a priority marker; cc-toolkit writes none. See
[ADR 0011](docs/adr/0011-give-the-merge-lock-holder-suite-priority-with-a-marker.md).
The script reports a pass recorded for the same clean tree instead of a new
run, and it prints the failing tests and the exit status last. When a
failing run prints `Operation not permitted`, the summary says that a
sandbox probably blocks the suite. Run the command again outside the
sandbox. The Claude Code sandbox blocks `ps`, which the `dev-skills` suite
needs.

The lean-tests checks in `dev-skills/tests/test_lean_tests.py` that run
pytest need pytest and pytest-cov, which the `dev-skills` command
supplies. Under a `python3` without them, these checks skip; their skip
reason, which `-v` shows, gives the command. The checks that also need
pytest-xdist skip unless you add `--with pytest-xdist`.

The PyMOL startup suite requires `uv` and access to download missing script
dependencies. It checks MCP initialization and tool discovery without changing
the PyMOL scene. A running PyMOL instance is not required.

To replay one Core Hooks policy check, write a hook payload to
`.scratch/payload.json`. A hook payload is the JSON that the host sends to
a hook before a tool runs, for example:

```json
{"tool_name": "Bash", "tool_input": {"command": "git status"}}
```

Then run a policy script on the payload. `pre_git_hook.py` checks git
policy, and `safety_guard.py` checks `rm` commands and commands that print
every environment variable.
Exit status 2 means the policy script blocks the command:

```bash
python3 core-hooks/scripts/pre_git_hook.py < .scratch/payload.json
```
