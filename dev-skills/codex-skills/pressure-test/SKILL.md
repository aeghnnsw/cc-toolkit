---
name: pressure-test
description: Use when a design, plan, rubric, PR, failure diagnosis, or task orchestration decision needs independent adversarial review before conclusion.
---

# Pressure Test

Run an independent adversarial review before settling a decision. The main Codex agent owns the position and conclusion; a spawned skeptical subagent supplies pressure.

## Core Principle

Pressure testing only matters when the critic has enough context and independence to find real weaknesses. Do not replace the critic with inline self-critique.

## When To Use

Use for design decisions, architecture choices, task-loop aims, rubrics, plans, PRs, failure diagnoses, re-attack plans, and aim-fidelity checks.

Do not use for routine edits where the user asked for direct implementation and no judgment call needs adversarial review.

## Defaults

- `ROUND_CAP = 6`
- Stop early on convergence.
- Always save and present a conclusion.
- The critic is read-only. If the active Codex surface supports per-agent sandbox control, spawn the critic with read-only access. Otherwise, instruct the critic not to write files or run mutating commands, and do not approve critic write actions.

## Loop

1. State the current position: claim, reasoning, and decision boundary.
2. Build a critic context packet.
3. Spawn a skeptical subagent with the packet and critic instructions.
4. Read the critic's objections.
5. Handle every substantive objection: concede and revise, or rebut with evidence.
6. Stop if converged; otherwise repeat until round 6.
7. Write and present the conclusion.

## Critic Context Packet

Before every critic round, provide the subagent this packet:

```text
GOAL
The question, design, plan, rubric, PR, or failure diagnosis under review.

CURRENT POSITION
The current answer and reasoning.

DECISION BOUNDARY
What is in scope, what is out of scope, and what kind of objection would change the decision.

EVIDENCE
Relevant files, diffs, command outputs, proposal sections, rubric text, PR body, task-loop state, or other concrete artifacts.

ASSUMPTIONS
Known constraints and assumptions to attack.

PRIOR ROUNDS
Objections already raised and how they were handled.

CRITIC INSTRUCTIONS
Attack the weakest point first. Ground objections in evidence. Propose better alternatives when they exist. Say no substantive objection only when warranted.
```

If the packet lacks enough evidence for reliable judgment, gather the missing evidence before spawning the critic or report the gap.

## Critic Prompt

Use this stance for each critic subagent:

```text
You are an independent adversarial critic. Do not approve, praise, or soften the review.

Find the single weakest point in the current position. Surface hidden assumptions, edge cases, failure modes, and missing evidence. Ground objections in the provided evidence and inspect the repo read-only when needed. If a better alternative exists, propose it concretely.

Avoid repeating prior objections unless the handling was insufficient. If no substantive objection remains, reply with: NO SUBSTANTIVE OBJECTION. Then give one sentence explaining why the position holds.
```

## Convergence

Stop before round 6 only when:

- the critic reports no substantive objection, or
- the original decision is stable and remaining objections are out-of-scope refinements that do not change the decision.

Do not stop because the current position feels persuasive. Judge convergence against the critic's actual objections and the decision boundary.

## Progress Format

After each round, record:

```text
Round N
Critic: strongest objections, faithfully summarized.
Disposition: conceded and revised, or rebutted with evidence.
Current position: updated position.
```

## Conclusion

Write the conclusion to:

```text
docs/superpowers/specs/YYYY-MM-DD-topic-slug-conclusion.md
```

Include:

- settled position
- key decisions
- strongest objections and dispositions
- unresolved tensions, if any
- ending condition: converged, round cap, critic unavailable, or cut short

Present the same conclusion in chat.

## Failure Behavior

If subagent spawning is unavailable, stop and report that an independent critic could not run. Do not silently run inline self-critique.

If a critic round fails mid-loop, retry that round once. If it still fails, write a partial conclusion with the last stable position, unresolved objections, and the failure point.
