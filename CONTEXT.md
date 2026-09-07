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
