# Design - Codex pressure-test skill

## Goal

Add a Codex-native adversarial review primitive for issue #143. The skill should
replace the Codex-facing need for `discuss-with-codex` with a clearer runtime
neutral concept: `pressure-test`.

The value is not "Codex talks to Codex." The value is an independent skeptical
critic that pressures a design, plan, rubric, PR, failure diagnosis, or
task-loop decision until the main agent has a defensible conclusion.

## Context

The existing Claude skill, `dev-skills:discuss-with-codex`, runs a turn-by-turn
discussion where Claude owns the position and Codex acts as an always
adversarial read-only critic. That implementation depends on nested `codex exec`
sessions and Claude/Codex asymmetry.

For Codex, that framing is awkward and unnecessary. Codex already supports
subagents. A Codex skill can ask the main Codex agent to spawn a read-only
skeptical subagent and use that subagent as the independent critic. This keeps
the useful behavior while removing the runtime-specific name and CLI-session
machinery.

## Name

Use `pressure-test` for the Codex-facing skill name.

Rejected names:

- `discuss-with-codex` - implementation-specific and confusing when Codex is
  the main agent.
- `critic-review` - too close to PR review; this skill also reviews aims,
  rubrics, plans, and failure diagnoses.
- `adversarial-review` - accurate but heavier than the task-loop primitive.

`pressure-test` describes the job and works across runtimes.

## Scope

In scope:

- Add a Codex skill named `pressure-test`.
- Default to a multi-round adversarial loop.
- Stop early on convergence.
- Cap the loop at 6 rounds.
- Use a spawned Codex subagent as the independent critic.
- Require the main agent to build a compact critic context packet before each
  critic round.
- Save and present a conclusion.
- Update Codex-facing task-loop references to use `pressure-test` instead of
  `discuss-with-codex`.

Out of scope:

- Running nested non-interactive Claude sessions.
- Running nested non-interactive Codex CLI sessions.
- Porting the Claude `discuss-with-codex` skill verbatim.
- Providing inline self-critique as a silent substitute for an independent
  critic.
- Updating Claude-facing task-loop paths.

## Architecture

The main Codex agent is the deliberation owner:

1. It states the current position.
2. It packages enough context for reliable external judgment.
3. It spawns a read-only skeptical subagent.
4. It reads the critic's objections.
5. It concedes and revises, or rebuts with evidence.
6. It repeats until convergence or the round cap.
7. It writes the conclusion and presents it to the user.

The critic subagent is not the decision maker. It has one job: find the weakest
remaining point and make the best objection.

## Critic Context Packet

Before every critic round, the main agent must build a compact context packet.
The subagent must not be dispatched with only "review this." A reliable critic
needs enough specific context to judge the actual decision.

Each packet includes:

- **Goal** - the question, design, plan, rubric, PR, or failure diagnosis under
  review.
- **Current position** - the main agent's current answer and reasoning.
- **Decision boundary** - what is in scope, what is out of scope, and what kind
  of objection would change the decision.
- **Evidence** - relevant files, diffs, command outputs, proposal sections,
  rubric text, PR body, task-loop state, or other concrete artifacts.
- **Assumptions** - known constraints and assumptions the critic should attack.
- **Prior rounds** - objections already raised and how they were handled, so
  the critic does not repeat stale points.
- **Critic instructions** - attack the weakest point, ground objections in
  evidence, propose alternatives, and report no substantive objection only when
  warranted.

The packet should be concise but not under-specified. If the main agent cannot
build a trustworthy packet because required evidence is missing, it should gather
the missing evidence before spawning the critic or report the gap.

## Loop Semantics

Defaults:

- `ROUND_CAP = 6`
- one round = main position plus one independent critic response plus main
  disposition
- save and present a conclusion every time

Stop early when either condition holds:

- The critic reports no substantive objection.
- The original goal question now has a stable answer and remaining objections
  are out-of-scope refinements that do not change the decision.

Do not stop merely because the main agent prefers its current answer. Judge
convergence against the critic's actual objections and the decision boundary.

At the round cap, carry live disagreements into the conclusion as unresolved
tensions, with the main agent's chosen resolution and reasoning.

## Critic Stance

The critic must be skeptical by default:

- Do not praise or approve.
- Attack the single weakest point first.
- Surface hidden assumptions, edge cases, and failure modes.
- Ground objections in repo evidence when relevant.
- Propose a better alternative when one exists.
- Avoid repeating objections already handled unless the handling was
  insufficient.

## Outputs

The skill writes a conclusion file under:

```text
docs/superpowers/specs/YYYY-MM-DD-topic-slug-conclusion.md
```

The conclusion includes:

- settled position
- key decisions
- strongest objections and their dispositions
- unresolved tensions, if any
- how the loop ended: converged, round cap, or critic unavailable

The main agent also presents the conclusion in chat.

## Failure Behavior

If Codex cannot spawn a subagent, do not silently fall back to inline
self-critique. Report that the independent critic could not run.

For task-loop, critic unavailability is a blocked prerequisite unless the caller
explicitly accepts a weaker fallback for that specific decision. This preserves
the property that pressure-testing is independent enough to matter.

If a critic round fails mid-loop, retry the round once. If it still fails, write
a partial conclusion that states where the loop stopped and what evidence is
missing.

## Task-loop Integration

Codex-facing task-loop docs and skills should call `dev-skills:pressure-test`
for:

- aims and stage decomposition
- rubric finalization
- spec and plan review
- open-question routing during autonomous design
- PR review
- failure diagnosis and re-attack design
- aim-fidelity checks
- roadmap/finding significance checks

Codex-facing task-loop paths should not invoke `dev-skills:discuss-with-codex`.
Claude-facing paths can keep the existing skill until a separate runtime-neutral
cleanup is planned.

## Validation

Implementation validation should include:

- The Codex `dev-skills` manifest exposes `pressure-test`.
- `dev-skills/codex-skills/pressure-test/SKILL.md` passes skill frontmatter
  validation.
- Existing Codex skills `goal-rubric` and `doc-update` remain discoverable.
- Codex-facing task-loop references use `pressure-test`, not
  `discuss-with-codex`.
- A dry-run prompt confirms the skill instructs Codex to spawn a critic subagent
  with a context packet and a 6-round cap.

## Open Risk

Codex subagent behavior is surface-dependent. The design relies on Codex CLI or
Codex app sessions where subagents are available. If a surface cannot spawn
subagents, the skill should fail clearly rather than degrade invisibly.
