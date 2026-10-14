# Use a cross-family critic for pressure tests

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

| Critic | Model | After a flag |
| --- | --- | --- |
| GPT, through `codex exec` | `gpt-6-astra` | `gpt-6.1-sol` |
| Claude, through `claude -p` | `claude-opus-5-5` | `claude-sonnet-5-5` |

A Codex flag is a policy error such as `cyber_policy` or `bio_policy`, or a
model reroute. A Claude flag is any safeguard action: a response that ends
with `stop_reason: "refusal"`, a result with `safety_stops` above zero, or
a refusal event from Claude Code. After a flag, the skill switches to the
fallback model for the rest of the pressure test. A flag on the fallback
model ends the pressure test with a partial conclusion. The skills turn off
Claude Code's automatic refusal fallback, because Claude Code chooses that
fallback model itself. In Codex, each call accepts a reply only from the current critic
model. In Claude Code, the skill finds a model change through the Codex
reroute notice.

Consequences:

- Each skill needs the other host's CLI, installed and signed in. Neither
  skill falls back to inline self-critique or to a same-host subagent.
- In Codex, the `claude` command needs network access and write access to
  `~/.claude`, so a restricted sandbox must allow it.
- `codex exec resume` does not keep the sandbox or working directory of the
  first call. Each resume passes `-c sandbox_mode="read-only"` and runs from
  the repository root.
- Each model family has one primary model and one fallback model in
  `allowed-models.json`. A model pin names the primary model of its family,
  or `inherit`. A pressure test uses the fallback model only after a flag.
- A change to the allowed models starts in `allowed-models.json`. The same
  change updates both skills, the cc-customize `model-config` skill, and the
  model pins in agent and Codex agent files. The test data in
  `dev-skills/tests/test_critic_status.py` reads the file.
- `tests/test_model_pins.py` fails until these conditions are true:
  - Every model pin names the primary model of its family, or `inherit`.
  - Each skill sets the primary and fallback models of its critic family
    and names no other model.
  - The `model-config` skill names the Claude primary and fallback models.

The CLI behavior above was verified on 2026-10-14 with codex-cli 0.162.1 and
Claude Code 2.1.299. No live call was rerouted. The reroute check matches
text in the codex-cli 0.162.1 binary: `model rerouted:` and the "as a
fallback" policy message. Codex lists the model IDs available to the account
in `$CODEX_HOME/models_cache.json`.

See [issue #284](https://github.com/aeghnnsw/cc-toolkit/issues/284).
