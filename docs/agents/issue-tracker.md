# Issue tracker: GitHub

Track work in GitHub Issues for `aeghnnsw/cc-toolkit`. Use `gh` from the
repository checkout so it resolves the configured remote. Link durable
designs and decision records in `docs/` from their issue.

## Skill integration

- When a skill says to publish to the issue tracker, create a GitHub issue.
- When a skill says to fetch a ticket, use `gh issue view <number> --comments`.
- Pull requests propose changes; they are not a separate request intake queue.
  Resolve an ambiguous number with `gh pr view <number>`, falling back to
  `gh issue view <number>`.
- For triage, use the mapping in [triage-labels.md](triage-labels.md).

For multiline issues, PR descriptions, and comments, write the text to a
temporary file and pass `--body-file`. Follow the branch and communication
conventions in [CLAUDE.md](../../CLAUDE.md#development-workflow).
