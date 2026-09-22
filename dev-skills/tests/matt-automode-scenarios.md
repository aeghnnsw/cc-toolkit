# Matt Automode scenario review

These cases cover [issue #241](https://github.com/aeghnnsw/cc-toolkit/issues/241).
Apply each case to the [Claude Code skill](../skills/matt-automode/SKILL.md)
and the [Codex skill](../codex-skills/matt-automode/SKILL.md).

For each case, identify the next permitted action, blocked work, and evidence
needed to pass the gate. Use a fresh review context with the skill and scenario
inputs. Keep expected results separate from the initial review prompt.

## Scenarios

1. **Pending research.** A schema investigation is still running. A decisions
   file recommends a schema. An independent logging question can be resolved.
2. **Conflicting decisions.** An old ADR selects interface A. A newer merged PR
   implements B. It is unclear whether the PR's issue authorizes replacing A.
3. **Early coding delegation.** A coding sub-agent started before spec and ticket
   publication. Those artifacts are now published. The orchestrator wants to
   report strict compliance.
4. **New evidence.** All planning gates passed and coding is active. New consumer
   evidence invalidates the chosen schema.
5. **Investigated recommendation.** Repository investigation and challenge support
   the recommended answer to the current question. A dependent design question
   remains for the next round.

## Expected results

| Case | Next permitted action | Blocked work | Evidence needed |
| --- | --- | --- | --- |
| Pending research | Resolve the independent logging question and wait for the schema finding. | Settling the schema, passing gate 1, and assigning coding work. | Returned findings, evaluated alternatives, resolved design-critical questions, and a recorded completion check. |
| Conflicting decisions | Read the relevant issue, comments, PR rationale, and current interfaces and tests. Resolve whether B supersedes A. | Treating recency or current code alone as design authority; closing the affected question. | Cited rationale for the current decision, evaluated compatibility and consumers, and an explicit resolution of the conflict. |
| Early coding delegation | Report the ordering failure and pause dependent work. Validate the missing gates in sequence before resuming. | Claiming the earlier execution was compliant because artifacts now exist; continuing on unverified artifacts. | Content checks for the published spec and tickets, resolved questions, satisfied blockers, and an accurate sequence record. |
| New evidence | Pause dependent coding, including active sub-agents. Reopen the affected gate and downstream gates. | Continuing dependent work using the invalid decision. | Updated decisions, spec and tickets as needed, and new completion checks before resumption. |
| Investigated recommendation | Accept the recommended answer, record the decision, and continue the next grilling round. | Skipping remaining questions or asking for routine human approval. | Repository evidence and challenge supporting the recommendation; resolved dependent questions before gate 1 can pass. |

## Validation limits

Reading the instructions checks coverage. A simulated next-action review checks
how an agent interprets these cases. Neither demonstrates a full workflow in
Claude Code or Codex. Package validation checks metadata and release contracts;
it does not enforce agent behavior. Record actual review outcomes separately
from these expected results.

## Review record: 2026-09-22

At commit `5489760`, an independent agent read both skills and the first four
scenario inputs. It received no expected results. Its proposed next actions
matched all four cases
for both variants. It found no substantive host mismatch. This was a simulated
review of instructions, not execution of either host workflow.

After the recommendation-acceptance clarification, a fresh independent agent
reviewed both skills against all five inputs without the expected results.
Its next actions matched all five cases for both variants. It accepted the
supported recommendation and continued grilling on the dependent question.
Gate 1 remained blocked for design-critical questions. This was also a simulated
interpretation review, not live host execution.
