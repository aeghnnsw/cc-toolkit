# Task-loop Codex Specify-aims Pressure-test Conclusion

## Settled Position

Add Codex `task-loop:specify-aims` as the next task-loop Codex slice after setup.
The skill lives under `task-loop/codex-skills/specify-aims/`, uses the same proposal
output contract as the Claude skill, and replaces `dev-skills:discuss-with-codex`
with `dev-skills:pressure-test`.

## Key Decisions

- Keep `create-cycle` and `run-cycle` pending.
- Copy the proposal template into the Codex skill so the skill is self-contained.
- Update `task-loop/.codex-plugin/plugin.json` so marketplace metadata no longer describes the plugin as setup-only.
- Update Codex setup wording so supported Codex scope is setup, preflight, and `specify-aims`.
- Add an explicit `incorporated_through` frontmatter gate before re-aim edits.

## Objections And Dispositions

Round 1:
- **Objection:** Updating only setup wording leaves `.codex-plugin/plugin.json` advertising setup/preflight-only support.
- **Disposition:** Conceded. Added plugin metadata updates to the design, plan, implementation, and validation.

Round 2:
- **Objection:** The re-aim safety gate was too vague and could rewrite human-gated Specific Aims after execution starts.
- **Disposition:** Conceded. Added an explicit `incorporated_through` frontmatter gate to the skill, design, and plan.

Round 3:
- **Objection:** No substantive objection.
- **Disposition:** Converged.

## Unresolved Tensions

None for this slice. Codex `create-cycle`, `run-cycle`, and the worker execution model remain separate work.

## Ending Condition

Converged.
