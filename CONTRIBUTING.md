# Contributing to cc-toolkit

cc-toolkit uses one repository for development and plugin distribution.
Contributor documentation lives at the root and under `docs/`; installable
components live inside each plugin directory. Follow
[CLAUDE.md](CLAUDE.md) for the issue, worktree, and PR workflow.

## Repository and package boundaries

The Claude Code and Codex marketplace registries select plugin directories
such as `dev-skills/` and `core-hooks/`. Each directory contains that
plugin's manifests, components, and supporting resources. Keep resources
needed by an installed plugin inside its directory.

Root documents describe how to maintain this repository. They remain
public in the source checkout, but are outside the plugin directories
selected by the registries. Installing a plugin does not require adopting
cc-toolkit's contributor workflow or installing the tools used to develop it.

Keep development and publishing in this repository. Use branches and
worktrees for changes and the host-specific manifests for plugin releases.
A root documentation change does not require changing plugin versions.

Installed copies under `~/.claude/plugins/cache/` and
`~/.codex/plugins/cache/` are release snapshots. They can lag this checkout,
and each update replaces them. Read and edit the plugin directory in this
repository.

The Core Hooks policy scripts that check your shell commands are the
installed copy. A denial names its path, such as
`core-hooks/1.0.13/scripts/pre_git_hook.py`. Until you update that copy, it
keeps blocking a command that this checkout allows. To update the Claude
Code copy, run `claude plugin marketplace update cc-toolkit`, then
`claude plugin update core-hooks@cc-toolkit`, and restart the session.

### Skills for both hosts

A skill that ships to Claude Code and Codex has one copy per host:
`skills/<name>/` (`claude-skills/<name>/` in task-loop) and
`codex-skills/<name>/`. Change both copies in the same pull request. Keep
differences host-specific, such as tool names, invocation, and plugin-root
paths.

For an example pair, see `creator-skills/skills/sci-slides/` and
`creator-skills/codex-skills/sci-slides/`. The test
`creator-skills/tests/test_sci_slides.py` compares the two copies. A new
skill also needs an entry in both [README.md](README.md) lists of its
plugin: **Skills:** with a one-line description, and **Codex skills:** with
its name. When the Codex manifest's `interface.longDescription` describes
the purposes of the plugin's skills, add the purpose of the new skill. When
a change alters the purpose of a skill, update that purpose in
`longDescription` and in the README **Skills:** line.

- **Frontmatter.** Claude copies carry `name`, `description`, and usually
  `version`. Codex copies carry only `name` and `description`. The Codex
  skill-creator validator rejects Claude-only keys. Run the skill-creator
  validator on Codex copies only. Codex installs the skill-creator
  validator at
  `$CODEX_HOME/skills/.system/skill-creator/scripts/quick_validate.py`.
  `CODEX_HOME` defaults to `~/.codex`. The skill-creator validator takes
  one skill directory as its argument. To supply its PyYAML dependency,
  run the skill-creator validator through `uv` from the repository root:

  ```bash
  uv run --no-project --with pyyaml python "${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py" <plugin>/codex-skills/<name>
  ```

  A valid copy prints `Skill is valid!`. The repository validator checks
  the headers of both copies.
- **Shell blocks.** A skill's shell blocks run in the user's shell, which
  can be bash or zsh. Write each block to run in both shells. Store an exit
  code in a name such as `rc`, because `status` is read-only in zsh. Pass a
  file list through `xargs` or a loop, because zsh does not split an
  unquoted variable into words. Compare strings with one `=` in `[ ]`,
  because zsh expands a word that starts with `=`, such as `==`. Read a file
  into a variable before a redirection to the same file, because
  `if ...; fi > file` empties the file before the condition runs. Each tool
  call can start a new shell, so keep state that later blocks need in a
  file. In a Claude copy, put code that needs positional parameters in a
  script under the skill directory. See
  [Argument placeholders](#argument-placeholders). For a test that runs a
  skill's blocks in bash and zsh, see
  `dev-skills/tests/test_pressure_test_models.py`.
- **Paths.** A link relative to `SKILL.md` reads the same in both copies. A
  plugin-root path differs: `${CLAUDE_PLUGIN_ROOT}/...` in the Claude copy
  and `<plugin-root>/...` in the Codex copy. A command that runs a file
  inside the skill directory can write `<skill-dir>/...`, which reads the
  same in both copies. `${CLAUDE_PLUGIN_ROOT}` names the plugin that the
  session loaded, usually the installed copy, not your worktree. For a live
  check of a changed skill, replace it with the worktree's plugin directory,
  for example `$PWD/dev-skills` from the worktree root.
- **Registration.** List each file that a skill links to or runs under the
  plugin's `resources` in `package-validation.json`, once per host that
  ships it. A link to a `SKILL.md` that the same host discovers needs no
  entry. The validator requires only listed resources; it does not find
  them from links in prose. The skill link test,
  [tests/test_skill_links.py](tests/test_skill_links.py), checks this rule.
  It follows relative Markdown links and `${CLAUDE_PLUGIN_ROOT}/`,
  `<plugin-root>/`, and `<skill-dir>/` paths from each discovered skill and
  through the Markdown files that the skill reaches. Each target must be a
  file inside the plugin. A link anchor must match a heading. The target
  must be listed for the host.

### Argument placeholders

When Claude Code loads a skill or command, it replaces argument placeholders
in the body with the invocation arguments. It replaces them everywhere,
including code spans and fenced blocks:

- `$N`, where `N` is a number such as `0` or `10`: one argument, counted
  from 0. `$ARGUMENTS[N]` is the long form.
- `$ARGUMENTS`: the full argument string. With no arguments, it becomes
  empty.
- `$name`: a name that the `arguments` frontmatter declares. With no
  matching argument, it becomes empty.

When no placeholder takes the arguments, Claude Code appends
`ARGUMENTS: <value>` to the skill text. Codex does not replace
placeholders. Claude Code does not replace them in the supporting files
that a skill reads. In a test, Claude Code did not replace them in an
agent file; its documentation does not cover agent files.

Write a `$` before a number, `ARGUMENTS`, or a declared name in a Claude
Code skill or command as follows:

- In prose or an example, write one backslash before the `$`. For example,
  `\$0.67` loads as `$0.67`. Two or three backslashes do not escape a
  placeholder.
- Put shell code that needs positional parameters in a script in the
  plugin, for example under the skill directory. Do not escape the shell
  code: an agent can read the file directly instead of through the Skill
  tool, and then the shell gets the backslash.
- Do not use `${N}`, a braced positional parameter such as `${1}`. Claude
  Code does not document this form, and a backslash before it stays in the
  loaded text. Put the code in a script.
- For an intended placeholder, add the exact line to `ALLOWED` in
  [tests/test_skill_placeholders.py](tests/test_skill_placeholders.py),
  with its line count and a reason.

The argument-placeholder test, `tests/test_skill_placeholders.py`, is one of
the [root tests](#package-and-release-validation). It checks every Claude
Code skill and command file. It fails on an unescaped placeholder and on
`${N}`, unless an `ALLOWED` entry covers the line. It also fails on a
declared name that it cannot check, such as `my-arg`; use letters, digits,
and underscores.

## Repository search

From the repository root, search with `git grep`. It reads only the tracked
files of the current worktree, so it skips the other worktrees under
`trees/` and `.claude/worktrees/`. A recursive `grep` from the main checkout
can read those worktrees and match many copies of the same file. To also
search new files that are not yet added, pass `--untracked`.

Dated records under `docs/superpowers` and the entries in `CHANGELOG.md` can
describe replaced behavior. The task-loop plugin is
[not usable now](task-loop/README.md#status), but its copies of shared
skills match many terms. To search current text only, exclude all three:

```bash
git grep -n <term> -- ':!docs/superpowers' ':!CHANGELOG.md' ':!task-loop'
```

Keep task-loop in the search when the change renames a skill or changes a
model pin.

## Changelog entries

The root [CHANGELOG.md](CHANGELOG.md) is the only maintained changelog.
Add each entry under `## [Unreleased]`, in `### Added`, `### Removed`,
or `### Changed`. Put the newest entry first. Each entry is one long line.
To find the insertion point, get the line number of the target `###`
heading with `grep -n '^##' CHANGELOG.md`, and read only a few lines below
it. Use this form:

```text
- <plugin> (<Host> <version>): <change>. See [#N](https://github.com/aeghnnsw/cc-toolkit/issues/N).
```

When both hosts ship the same version, write
`Claude Code and Codex <version>`. When the versions differ, write
`Claude Code <version>, Codex <version>`. Start a change outside the
plugin directories with `Repository:` and give no version. The plugin entry
also covers the README catalog entry and the `package-validation.json`
lines that ship with the plugin change. When a pull request changes a
plugin and other files outside it, write one plugin entry and one
`Repository:` entry. A change only to contributor-only files of a
plugin, such as its `tests/`, needs no version and is also a `Repository:`
entry. Link the issue that the pull request closes; for a spec with
tickets, link the ticket.

## What belongs in Git

Classify a file by its purpose and expected lifetime, regardless of whether
a person or an agent wrote it.

| Material | Location and treatment |
| --- | --- |
| Installable skills, agents, hooks, scripts, and required resources | Commit inside the owning plugin directory. |
| Shared contributor instructions and agent configuration | Commit `CLAUDE.md`, its `AGENTS.md` symlink, and `docs/agents/`. |
| Accepted architecture decisions | Commit concise records under `docs/adr/`. |
| Agreed domain terminology | Commit a root `CONTEXT.md` when a glossary is needed. |
| Durable designs and review conclusions | Commit under a relevant `docs/` directory and link them from the issue or relevant documentation. |
| Disposable notes, trial output, and intermediate reports | Use `.scratch/`, which is ignored. Name a planning directory `.scratch/<issue>-<description>/`, and keep it in the main checkout, because worktree cleanup removes the ignored files of a worktree. A desktop session edits only its own worktree: copy its planning directory to the main checkout before the worktree is removed. Promote useful conclusions into shared documentation. |
| Logs, caches, local worktrees, and generated binaries | Keep out of Git using the shared `.gitignore`. |
| Personal tool settings and local-only notes | Keep outside the repository or exclude specific paths locally. |

Before committing generated documentation, check its claims against the
current project, remove unused template assumptions, and add a pointer from
the relevant instructions. An installed development skill's configuration
belongs in Git when it expresses conventions shared by this repository.

A design, plan, conclusion, or ADR under `docs/` records decisions as of
when it was written, and later work can supersede part of it. Before
relying on one, read any status or superseded note at its top, and confirm
current behavior in the code it describes.
When a change supersedes part of such a record, add a superseded note at
its top. Name the date and the issue, and link the replacement. In an ADR,
also mark each replaced sentence and record the new rule with its reason in
a new section; see ADR 0002 for an example. A change that only adds facts
needs no note.

Do not blanket-ignore `docs/`, `docs/agents/`, or `docs/adr/`. Git ignores
control tracking; they do not define which files belong in a plugin package.

## Local exclusions

Use `.gitignore` for paths every contributor should exclude. For personal
files in this checkout, edit the Git common directory's `info/exclude` file;
it is local and is shared by linked worktrees. Locate it with:

```bash
git rev-parse --path-format=absolute --git-path info/exclude
```

Use exact file paths or a dedicated personal directory. Prefer putting
machine-specific agent preferences in the host's user configuration so
shared repository instructions remain portable. Ignore rules do not hide
changes to files already tracked by Git.

See [Git's ignore documentation](https://git-scm.com/docs/gitignore) for the
scope of local and shared exclusions.

## Verification

There is no repository-wide build or lint command. Verification depends on
what changed:

- **Documentation:** check accuracy, relative links, referenced paths, and
  whitespace with `git diff --check`.
- **Skills and metadata:** check skill frontmatter; run the package and
  release validator and the root tests described below. The root tests
  include the skill link test.
- **Executable code:** run the tests for the affected plugin. Core Hooks
  tests require Python and `uv` on `PATH`; task-loop CLI tests require
  Python 3.11+ and `httpx>=0.27` as declared by the CLI. The command below
  supplies that dependency through `uv`.
- **GitHub Actions:** validate edited workflow YAML and check its triggers
  and permissions against the intended behavior.

### Package and release validation

Run this read-only command from the repository root. The validator needs
Python 3.11 or newer; `uv` obtains a suitable interpreter. The validator
uses only the standard library and installs no dependencies:

```bash
uv run --no-project --python '>=3.11' python scripts/validate_packages.py --base origin/master
```

Use this `uv` form: the `python3` of a contributor machine can be older
than 3.11. With such a `python3`, the validator stops with exit status 1 and
prints the `uv` command that repeats the same arguments.

`--base` accepts the target branch ref or a commit SHA. The validator finds
its merge base with `HEAD`. Local validation includes staged edits,
unstaged edits, and new files that Git does not ignore. It checks the
resulting working tree. It does not select versions or change files.

The target ref and enough history to find the merge base must exist
locally. Run `git fetch origin master` to update the usual target. For a
shallow checkout, fetch the missing history before retrying. An unavailable
ref or merge base fails validation with a correction message. The validator
does not fetch history or skip release checks.

Package validation checks all registered plugins, their JSON metadata,
declared local paths, and explicitly required resources. It resolves
symlinks to check package containment. Required paths must be tracked or
new files that Git does not ignore. Ignored local files cannot satisfy the
package contract. Optional discovery roots remain
optional. Discovered skills need `---` header delimiters and one nonempty,
single-line `name` and `description`. Names use lowercase letters, digits,
and single separating hyphens. This is a narrow skill header contract, not
full YAML validation. Agent headers do not use this contract. Declared JSON
hook and MCP files and listed TOML and JSON resources are parsed.
The validator does not check external links,
interpret paths in prose or shell examples, infer code dependencies, or
run plugins and host loaders.

The root agent-field test, `tests/test_agent_fields.py`, checks agent
headers. It fails when a plugin agent sets `hooks`, `mcpServers`,
`permissionMode`, or `initialPrompt`, which Claude Code ignores for plugin
agents.

Release validation compares both package layouts across the merge base.
Changed shipped content requires a greater numeric `major.minor.patch`
version for each affected existing host registration. One increase covers
the whole pull request. New registrations need a valid initial version.
Removed registrations need no increase for the removed host. A source move
preserves release history by plugin identity and host.

Release validation compares only with the merge base, so it does not see
a version that another pull request released after the merge base. Before
merging, run `git fetch origin master` and compare each version you raised
with the one on `origin/master`. If `origin/master` has that version or a
greater one, raise yours above it. Choose a version when the pull request
is ready, and write no target version in an issue or a ticket. After a
rebase, run the validator again: when both sides made the same version
change, the rebase removes that change from the branch. The validator
checks only plugin manifest versions. After a rebase, also compare each
skill frontmatter `version` that you raised with the one on
`origin/master`. When `origin/master` has that version or a greater one,
raise yours above it. Update each test that pins the version, such as
`HostParityTest` in `dev-skills/tests/test_lean_tests.py`.

[package-validation.json](package-validation.json) holds the ownership
exceptions, required resources, and contributor-only exemptions. Update
these rules when a package needs an explicit local contract. Edit the file
as text and keep one entry object per line, so rule diffs stay small.
Plugin-root tests, `README.md`, and `CHANGELOG.md` are exempt by default.
Required resources override exemptions. Markdown files are not exempt by
extension.
Unclassified plugin files affect all registered hosts. Failure diagnostics
identify the relevant path or package and host. Version failures include
the ownership reason and the version that must be exceeded. Fix the first
reported error and rerun the command. The result includes elapsed execution
time. See the [design](docs/design/package-validation.md) for the rule schema
and ownership precedence. Terms are defined in [CONTEXT.md](CONTEXT.md).

The [pull-request workflow](.github/workflows/package-validation.yml) runs
the same command against the exact pull-request head and target SHA. It
fetches the comparison history and runs one job with read-only repository
permission. Changes limited to root contributor documents or `docs/` skip
the job. Other paths remain eligible, including new plugin source
directories. The job uses the runner's Python and runs no plugin runtime
suites. The speed target is less than 10 seconds of validator execution;
queue, checkout, and runner startup time are separate.

Run the root tests when you change the validator, a skill, an agent,
`allowed-models.json`, or `package-validation.json`. The root tests contain
the validator's command-interface fixtures, the skill link test, the
model-pin test, the argument-placeholder test, and the agent-field test:

```bash
uv run --no-project --python '>=3.11' python -m unittest discover -s tests -p 'test_*.py'
```

With a `python3` older than 3.11, the root tests load no test. They print
this command and stop with exit status 1.

When you change `allowed-models.json` or a pressure-test `SKILL.md`, also
run the `dev-skills` tests. `dev-skills/tests/test_critic_status.py`,
`test_codex_critic.py`, and `test_pressure_test_models.py` read their critic
model IDs from `allowed-models.json`, and `test_pressure_test_models.py`
runs the model blocks of both `SKILL.md` copies:

```bash
python3 -m unittest discover -s dev-skills/tests -p 'test_*.py'
```

### Plugin runtime tests

Run the existing Python suites from the repository root:

```bash
python3 -m unittest discover -s creator-skills/tests -p 'test_*.py'
python3 -m unittest discover -s dev-skills/tests -p 'test_*.py'
python3 -m unittest discover -s core-hooks/tests -p 'test_*.py'
python3 -m unittest discover -s pymol-skills/tests -p 'test_*.py'
uv run --no-project --python '>=3.11' --with 'httpx>=0.27' python -m unittest discover -s task-loop/tests -p 'test_*.py'
```

The `dev-skills` suite takes about 2 minutes, most of it in
`dev-skills/tests/test_codex_critic.py`. When the 1-minute load average is
above the CPU count, the waits in that file grow with the load, and the
suite takes longer. Give its command a timeout of at least 300 seconds (in
Claude Code, a Bash tool `timeout` of 300000). On a loaded host, give it 600
seconds or run it as a background command. Test runs on one host slow each
other. When you run agents in parallel, let one agent at a time run a full
suite; the other agents run single test files until that suite ends. This
command runs one file:

```bash
python3 -m unittest discover -s dev-skills/tests -p 'test_limit_call.py'
```

The lean-tests checks in `dev-skills/tests/test_lean_tests.py` that run
pytest need pytest and pytest-cov. Under a `python3` without them, these
checks skip. Their skip reason, which `-v` shows, gives this command, which
supplies both:

```bash
uv run --no-project --python '>=3.11' --with pytest --with pytest-cov python -m unittest discover -s dev-skills/tests -p 'test_lean_tests*.py'
```

When you raise the core-hooks Codex version, also change the version that
`core-hooks/tests/test_codex_host_adapter.py` pins.

The PyMOL startup suite requires `uv` and access to download missing script
dependencies. It checks MCP initialization and tool discovery without changing
the PyMOL scene. A running PyMOL instance is not required.

To replay one Core Hooks policy check, write a hook payload to
`.scratch/payload.json`. A hook payload is the JSON that the host sends to
a hook before a tool runs, for example:

```json
{"tool_name": "Bash", "tool_input": {"command": "git status"}}
```

Write the payload, and any probe script whose text contains git commands or
attribution lines, with a file-writing tool, not a shell command. The
installed policy scripts check the text of each shell command, and some
checks read heredoc bodies and `python -c` code. Then run a policy script on
the payload. `pre_git_hook.py` checks git policy, and
`safety_guard.py` checks `rm` commands. Exit status 2 means the policy
script blocks the command:

```bash
python3 core-hooks/scripts/pre_git_hook.py < .scratch/payload.json
```

Keep validation proportional to the change. Documentation-only changes
normally need the documentation and configuration checks above.
