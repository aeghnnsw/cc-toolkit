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

**Required resource**:
A plugin file that installed use needs and host discovery does not find,
such as a file that a skill links to or runs. It is required for each host
that ships the skill or component that uses it.

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

## Model language

**Allowed model**:
A model ID that the repository permits a model pin or a critic call to name.
_Avoid_: Approved model, supported model

**Model pin**:
A model value that a shipped agent sets for its own work.
_Avoid_: Hard-coded model

**Primary model**:
The allowed model of a model family that a model pin or the first critic call
of a pressure test names.
_Avoid_: Default model, main model

## Pressure-test language

**Pressure test**:
An adversarial review in which a critic attacks the main agent's position
until the position holds or a round cap ends the review. It ends with a saved
conclusion.
_Avoid_: Discussion with Codex, critic review

**Critic**:
The read-only model that attacks the position in a pressure test. It comes
from the model family of the other host.
_Avoid_: Reviewer, skeptic

**Flag**:
A safeguard action by a model provider on one critic call, such as a policy
error or a refusal.
_Avoid_: Safety stop, block

**Fallback model**:
The single model that a pressure test can use after a flag on its primary
model.
_Avoid_: Backup model, secondary model

**Pressure-test packet**:
The context that the main agent gives the critic in each round of a pressure
test: the goal, the current position, the decision boundary, evidence,
assumptions, earlier objections and their handling, and, for a choice, the
options considered. In a packet with several questions, each question has an
ID. After the first round, a packet states only the changes since the last
round. The critic receives the packet followed by the critic instructions.
_Avoid_: Critic context packet

**Converged**:
The state of a pressure test, or of one question in it, when the critic's
latest assessment of the current answer raises no substantive objection, or
raises only refinements outside the decision boundary. The main agent's own
disposition does not make a question converged.
_Avoid_: Settled, approved

## Git policy language

**Branch creation**:
A git command whose own arguments name a new or reset local branch. A command
that copies the name of an existing remote-tracking branch is not a branch
creation.
