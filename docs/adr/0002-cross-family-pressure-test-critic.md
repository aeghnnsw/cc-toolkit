# Use a cross-family critic for pressure tests

> **Superseded in part (2026-10-21, issue #327).** A pressure test no longer
> uses the fallback model only after a flag, and a flag on the fallback model
> no longer always ends it. The user or a calling skill can choose the
> critic model. Read [Critic model choice](#critic-model-choice).

Each host ships a `pressure-test` skill whose critic comes from the other
host's model family, called through that host's CLI in non-interactive mode.
In Claude Code, the skill calls `codex exec`. In Codex, it calls `claude -p`.
A critic from another model family shares fewer blind spots with the main
agent than a subagent of the same model. This decision replaces the Codex
subagent critic from the
[pressure-test design](../superpowers/specs/2026-06-17-pressure-test-design.md),
which listed nested non-interactive Claude sessions as out of scope. The
Claude Code skill was named `discuss-with-codex` before both hosts used one
name.

Each critic call names its model. The table records the allowed models
chosen on 2026-10-14. `allowed-models.json` at the repository root holds the
current list.

| Critic | Primary model | Fallback model |
| --- | --- | --- |
| GPT, through `codex exec` | `gpt-6-astra` | `gpt-6.1-sol` |
| Claude, through `claude -p` | `claude-opus-5-5` | `claude-sonnet-5-5` |

A Codex flag is a policy error such as `cyber_policy` or `bio_policy`, or a
model reroute. A Claude flag is any safeguard action: a response that ends
with `stop_reason: "refusal"`, a result with `safety_stops` above zero, or
a refusal event from Claude Code. After a flag, the skill switches to the
fallback model for the rest of the pressure test. A flag on the fallback
model ends the pressure test with a partial conclusion. (These two rules
are superseded; read [Critic model choice](#critic-model-choice).) The
skills turn off Claude Code's automatic refusal fallback, because Claude
Code chooses that fallback model itself. In Codex, each call accepts a reply
only from the current critic model. In Claude Code, the skill finds a model
change through the Codex reroute notice.

Consequences:

- Each skill needs the other host's CLI, installed and signed in. Neither
  skill falls back to inline self-critique or to a same-host subagent.
- In Codex, the `claude` command needs network access and write access to
  `~/.claude`, so a restricted sandbox must allow it.
- `codex exec resume` does not keep the sandbox or working directory of the
  first call. Each resume passes `-c sandbox_mode="read-only"` and runs from
  the repository root.
- Each model family has one primary model and one fallback model in
  `allowed-models.json`. A model pin names the primary model of its family.
  A Claude Code agent can set `inherit` instead. A pressure test uses the
  fallback model only after a flag. (Superseded; read
  [Critic model choice](#critic-model-choice).)
- A change to the allowed models starts in `allowed-models.json`. The same
  change updates both skills, the cc-customize `model-config` skill, and the
  model pins in agent and Codex agent files.
  The pressure-test tests in `dev-skills/tests/` read their test data from
  the file.
- `tests/test_model_pins.py` fails until these conditions are true:
  - Every model pin names the primary model of its family. A Claude Code
    agent can set `inherit` instead.
  - Each skill sets the primary and fallback models of its critic family
    and names no other model.
  - The `model-config` skill names the Claude primary and fallback models.

The CLI behavior above was verified on 2026-10-14 with codex-cli 0.162.1 and
Claude Code 2.1.299. No live call was rerouted. The reroute check matches
text in the codex-cli 0.162.1 binary: `model rerouted:` and the "as a
fallback" policy message. Codex lists the model IDs available to the account
in `$CODEX_HOME/models_cache.json`.

## Critic model choice

Since 2026-10-21, the user or a calling skill can choose the critic model when
a pressure test starts. The choice is one of the two allowed models of the
critic family: `gpt-6-astra` or `gpt-6.1-sol` in Claude Code, and
`claude-opus-5-5` or `claude-sonnet-5-5` in Codex. With no choice, the
pressure test starts on the primary model. A request for any other model
starts no critic call: the skill names the two allowed models and asks which
one to use. When the calling skill forbids questions, the agent chooses one
of them. A later change of model starts a new pressure test.

A flag on the starting model switches the pressure test to the other allowed
model of the family, once. A flag after that switch ends the pressure test
with a partial conclusion. So no unlisted model can answer, which was the
goal of the old rule: each skill writes only the primary or the fallback
model of its family as the critic model, and `tests/test_model_pins.py`
checks the skill text.

See [issue #284](https://github.com/aeghnnsw/cc-toolkit/issues/284) for the
critic decision, [issue #289](https://github.com/aeghnnsw/cc-toolkit/issues/289)
for the allowed-model list and its test, and
[issue #327](https://github.com/aeghnnsw/cc-toolkit/issues/327) for the
critic model choice.
