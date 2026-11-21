# Use a native Antigravity plugin layout

Antigravity is Google's agent host. Its desktop app, its IDE, and its `agy`
CLI share one plugin loader. Without a native manifest, `agy plugin install`
converts a Claude Code plugin, and the result loses parts of it. Converted
Core Hooks apply no policy, because the shared scripts do not read the
Antigravity hook payload. Converted PyMOL Skills has no MCP server. Claude
copies of skills also name Claude Code tools and argument placeholders that
Antigravity does not have. So Antigravity is a third registered host, and
each plugin that ships to it has a native Antigravity layout.

## Native manifest

Each plugin that ships to Antigravity has `.antigravity-plugin/plugin.json`.
Antigravity also reads a `plugin.json` at the plugin root and
`.gemini-plugin/plugin.json`; `.antigravity-plugin/` takes precedence. The
folder keeps the plugin root host-neutral and matches the `.claude-plugin/`
and `.codex-plugin/` folders, so the package validator finds every host
manifest by one pattern. The manifest uses only the keys of the Antigravity
schema, because Antigravity ignores other keys. Its `skills` field declares
the folder of the Antigravity copies. The schema has no path field for
hooks or MCP servers, so hooks go in a root `hooks.json` and MCP servers in
a root `mcp_config.json`.

Rejected alternatives:

- **A root `plugin.json`.** It puts one host's manifest at the shared plugin
  root, and the validator pattern for host manifest folders does not find
  it.
- **Gemini CLI extensions.** The request named Antigravity, and
  `agy plugin import gemini` imports Gemini CLI extensions. A separate
  adapter can add Gemini CLI later.
- **Agent Plugins 1.0.0.** This vendor-neutral specification uses a root
  `plugin.json`, a fixed `skills/` folder, and `mcp.json`. Google does not
  name Antigravity as a host that supports it, and the Antigravity loader
  keeps its support behind a flag that is off.

## A third skill copy

Each skill that ships to Antigravity has an Antigravity copy in its own
folder, as Codex has the Codex copy. The copy starts from the Codex copy
when one exists, otherwise from the Claude copy. It names Antigravity tools
and has no argument placeholder. [CONTRIBUTING](../../CONTRIBUTING.md)
gives the translation rules.

Rejected alternatives:

- **Point the Antigravity `skills` field at the Codex copies.** Codex copies
  name Codex tools, the Codex home folder, and the Claude critic. One copy
  for two hosts breaks the rule to keep differences host-specific.
- **A generator that writes the Antigravity copies.** The repository has no
  generator. It adds a build step and checks for drift. A generator can
  replace the hand-written copies later without a change to the installed
  layout.

## Shadowing and the validator check

Antigravity always scans `skills/` and also loads the declared `skills`
paths. A same-named skill in a declared path replaces the skill in
`skills/`. A skill that is only in `skills/` still loads. So each Claude
copy of a plugin that ships to Antigravity needs a same-named Antigravity
copy. Otherwise, the Claude copy runs in Antigravity. The package validator
fails when an Antigravity copy is missing. `agy plugin validate` warns once
for each shadowed Claude copy, so the repository does not run it with
`--strict`.

## Claude agents move to their own folder

Antigravity loads agent files from `agents/`. Its loader skips a Claude
agent file: the Claude `tools` value is a string, not a YAML list, and a
Claude model is not an Antigravity model tier. `agy plugin validate` then
fails. One agent file cannot serve both hosts. Claude Code adds declared
agent paths to `agents/`, and it rejects a folder string in the manifest
`agents` field. So a plugin that ships to Antigravity keeps its Claude
agents in `claude-agents/`, lists each agent file in its Claude Code
manifest, and has no `agents/` folder. Agent names in Claude Code do not
change. An Antigravity copy that needs an agent starts one with
`invoke_subagent` and gives it instructions from a reference file in the
skill.

Rejected alternative: keep `agents/` and accept the loader errors in
Antigravity.

## Hook failure policy

Antigravity reads hooks from a root `hooks.json` and runs each command from
the plugin root. In a PreToolUse hook, exit status 2 with a reason on
stderr denies the tool call. Exit status 1 and a JSON `deny` decision on
stdout also deny it. Plain text or Claude Code JSON on stdout denies it
with a parse error. Empty stdout with exit status 0 allows it. So a hook's
stdout is empty or Antigravity JSON only.

The Core Hooks policy for Antigravity:

- Safety and git policy hooks fail closed: a failure denies the tool call.
- Logging and notification hooks catch their own failure, write a warning
  to stderr, and exit 0, as the Codex adapter does
  ([ADR 0001](0001-isolate-host-adapter-discovery.md)).
- No hook returns an `allow` decision, because `allow` skips the permission
  checks of Antigravity.
- A PreToolUse hook cannot show a warning without denying the tool call.
  Antigravity has no Notification, SessionEnd, or SubagentStop event.

## Registration without a catalog

An Antigravity catalog entry needs an `https` source URL and a `sha256` for
each plugin, and Antigravity documents no way to register a third-party
catalog. So the repository has no Antigravity catalog. A plugin directory
that the Claude Code or Codex registry lists, and that holds an Antigravity
manifest, is registered for Antigravity under the registered name. Users
install one plugin directory from its GitHub URL with `agy plugin install`.
A new Antigravity registration needs no version increase. After that, a
change that affects Antigravity needs a greater Antigravity manifest
version.

## Pressure-test critic in Antigravity

The Antigravity copy of `pressure-test` uses only the GPT critic through
`codex exec`. It starts from the Claude copy and its critic runner. GPT
comes from a model family other than Gemini and Claude, so the critic is
cross-family for a Gemini or Claude main agent. The runner starts each
critic call in a detached process and polls it. So it works within the time
limit of any shell tool: Antigravity moves a long command to the
background. The Claude critic path needs one foreground command of more
than 1800 seconds. When the main agent runs a GPT model, the skill stops
and reports that no cross-family critic is available.
[ADR 0002](0002-cross-family-pressure-test-critic.md) allows no
same-family critic.

## Consequences

- A skill that ships to all three hosts has three copies, and a change
  updates all of them in one pull request.
- The Antigravity agent reported its tool names itself. Antigravity's
  builtin skills confirm `ask_question`, `invoke_subagent`, and
  `run_workflow`. A copy can use a plain verb for another tool. A change to
  an Antigravity tool name needs a change to every Antigravity copy that
  names it.
- `agy` 1.0.0 read only a root `plugin.json`; `agy` 1.5.13 reads
  `.antigravity-plugin/`. A user with an older release updates it, as the
  host-compatibility rule in the domain documentation requires.
- Gemini CLI stays out of scope.

The behavior above was measured on 2026-11-20 with the Antigravity app
2.33.0 and `agy` 1.5.13.

See [#425](https://github.com/aeghnnsw/cc-toolkit/issues/425) for the
Antigravity specification and
[#426](https://github.com/aeghnnsw/cc-toolkit/issues/426) for the
repository host support.
