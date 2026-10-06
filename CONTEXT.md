# cc-toolkit

cc-toolkit publishes plugins through host-specific marketplace registries.

## Language

**Host**:
An agent tool that discovers and loads a cc-toolkit plugin. Registered hosts
are Claude Code and Codex.

**Plugin package**:
A self-contained plugin directory selected by a marketplace registry. It
contains host manifests, installable content, and required resources.

**Shipped content**:
Plugin content intended for installed use, including skills, agents, hooks,
scripts, and required resources. Tests and contributor-only files are not
shipped content for release validation.

**Affected host**:
A registered host whose shipped plugin content changes. Shared runtime
changes affect each host that uses that runtime.

**Package validation**:
Checks that a registered plugin has valid metadata and the local files
required for installed use.

**Release validation**:
Checks that shipped content changes include a plugin version increase for
each affected host.

**User-invoked skill**:
A skill that a host loads only when the user invokes it by name. The agent
cannot load it through the host's skill tool.

## GTD language

**GTD project**:
A desired outcome that requires more than one action.

**Next action**:
A concrete human step that can start with the available context and has an
observable stopping point. Starting agent work and reviewing its result are
next actions when their inputs are ready.

**GTD deadline**:
The date, and optional time, by which an outcome or action must be complete.
A preferred work date is not a deadline.

**Human action time**:
The time the user spends on a next action, including starting, supporting, or
reviewing agent work. Unattended agent runtime is separate.

**Waiting outcome**:
An incomplete outcome that depends on an external result and currently has no
ready human next action.

## Slide language

**Assertion title**:
A one-line slide title that states the slide's finding, with its main number
when the slide has one. A topic, question, or contrast title is not an
assertion title.

**Slide budget**:
The maximum number of content slides for a talk, set from its speaking time.

**Standing rules**:
A presenter's rules that apply to every deck in a project, such as template,
wording, and label conventions, as distinct from the general rules that apply
to any presenter.

**Meaning review**:
A review that checks each claim against what its number or figure measures, in
addition to checking the number against its source.

**Reused figure**:
A figure from a paper or another earlier source that a slide shows.
