# GTD daily use

Superseded in part on 2026-11-07 by
[#382](https://github.com/aeghnnsw/cc-toolkit/issues/382): GTD storage,
project links and mutation identity now follow the
[cloud GTD contract](../../productivity-skills/references/gtd-cloud.md).
The native lists, name references and reminder-ID decisions below describe
the preserved source workflow. Calendar and general Reminders remain native.

The user selects work through `gtd-next`. The complete spec and single
implementation ticket are [#215](https://github.com/aeghnnsw/cc-toolkit/issues/215).
See the [GTD glossary](../../GLOSSARY.md#gtd-language) for the agreed terms.

## Decisions

- Keep the current lists and project references. Add no new workflow states.
- Leave new projects and actions undated unless the user supplies a deadline.
  Existing deadlines remain unchanged until an explicit edit.
- Capture quickly. Clarify concrete next actions during batch processing.
  Leave unclear items in the inbox and preserve partial creation results.
- Recommend one action and up to two alternatives. Use known calendar and
  working constraints. Suggest a bounded session when availability is unknown.
- Show overview totals and project action tables. Keep all records visible and
  distinguish unavailable status from an empty result.
- Use reminder IDs for mutations. Update records in place and preserve fields
  that were not requested. Keep date-only deadlines separate from timed ones.

These choices are reversible skill and CLI policies. They do not require an ADR.
Agent execution tracking, weekly review, new lists, and project-completion
policy changes remain out of scope.

## Verification

For current GTD verification, follow the
[repository checks](../../CONTRIBUTING.md#verification). The native-only
checks below remain relevant to general Reminders changes.

Use compiled CLI commands for argument rejection and JSON response checks.
Use unsaved EventKit objects to verify edit preservation and local date behavior
without personal data access. Run the affected runtime suite with:

```bash
uv run --no-project --python '>=3.11' python -m unittest discover -s productivity-skills/tests -p 'test_*.py'
```

Use independent synthetic skill scenarios for overlapping calendar events,
blocked or vague work, duplicate project names, and unavailable overdue status.
Complete skill, package, and whitespace validation before merging.
