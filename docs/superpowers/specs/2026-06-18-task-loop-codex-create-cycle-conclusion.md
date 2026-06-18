# Task-loop Codex Create-cycle Pressure-test Conclusion

## Settled Position

Implement Codex `create-cycle` as a scaffolding-only task-loop skill. It should generate durable
project files for a later Codex runner, not claim current `run-cycle` or worker execution support.

The emitted `docs/task-loop/task-loop.md` must be self-contained: it must use Codex-compatible skills,
state that Codex `run-cycle` and worker execution are pending, and inline the study-log/PR handoff
contract instead of referencing plugin-local files.

## Key Decisions

- Add `task-loop/codex-skills/create-cycle/SKILL.md`.
- Add Codex-native assets for `task-loop.md` and `directions.md`.
- Validate all Codex-facing skill files and assets for forbidden Claude-only terms.
- Validate a representative rendered `task-loop.md` fixture, not only the skill wrapper.
- Inline required study-log and PR markers:
  `**Outcome:**`, `### Rubric`, `### Evidence`, `### Findings`, `Refs #<issue>`, and
  `Study log: docs/task-loop/logs/<NNN>_<task>.md`.
- Update Codex metadata to advertise setup, `specify-aims`, and `create-cycle`, while keeping
  `run-cycle` pending and out of default prompts.

## Objections and Dispositions

Round 1:
The critic objected that wrapper validation would not prove the generated worker contract was usable.
Disposition: conceded. The spec now requires Codex-native assets plus validation of bundled assets and
a representative rendered fixture.

Round 2:
The critic objected that referencing `task-loop/references/pr-findings.md` would create dead links in
target projects. Disposition: conceded. The generated skeleton now must inline the study-log/PR
contract.

Round 3:
The critic objected that the contract validation used a single alternation and would pass if only one
required string appeared. Disposition: conceded. The validation now checks every required marker with
fixed-string checks.

Round 4:
The critic objected that manifest validation could pass if `run-cycle` was advertised as supported.
Disposition: conceded. Manifest and setup checks now distinguish supported create-cycle behavior from
pending run-cycle behavior.

Round 5:
The critic objected that default-prompt validation was too narrow and blacklist-only. Disposition:
conceded. The validation now requires a positive create-cycle/scaffold prompt and rejects runner or
execution language in prompt, description, and short-description surfaces.

Round 6:
The critic objected that `longDescription` remained a discoverability escape hatch. Disposition:
conceded. The validation now requires long description to mention create-cycle support and run-cycle
pending status while rejecting runner/execution language.

## Unresolved Tensions

No unresolved design objections remain inside this slice, but the pressure-test ended at the round
cap rather than with a no-objection response. The next slice still needs an actual Codex run-cycle and
worker model before task-loop is fully runnable from Codex.

## Ending Condition

Round cap reached after six critic rounds. The final objection was bounded and incorporated before
implementation.
