# PR #182 Pressure-Test Conclusion

## Settled position

PR #182 is technically ready for final verification and CI. The reviewed tree
fixes issue #181's three false positives without the safety regressions found
in the initial PR head.

## Key decisions

- Parse executable `rm` invocations instead of scanning arbitrary command
  text.
- Preserve quote, comment, line-continuation, redirection, and substitution
  semantics needed to distinguish executable commands from literal arguments.
- Interpret only explicitly supported wrappers and launchers, including their
  value-taking and clustered options.
- Treat `env -S` as argv splitting and direct `find -exec rm ... {}` as
  substitution of the find roots.
- Trust protected-tree temp roots only for the exact macOS per-user
  `/var/folders/<id>/<id>/T` shape, and never trust `/` or an ancestor of a
  protected root.

## Strongest objections and dispositions

### Round 1

- Common launchers (`xargs`, `find -exec`, `timeout`, and valid `sudo`
  options) bypassed invocation detection. Conceded and fixed with
  launcher-aware parsing and safe non-`rm` counterexamples.
- Redirections were treated as command boundaries. Conceded and fixed by
  keeping redirections within the simple command and removing their operands
  before invocation classification.
- Quoted `#` tokens were mistaken for comments. Conceded and fixed by stripping
  comments quote-aware from source text.
- Broad `TMPDIR` values such as `/` disabled protected-path checks. Conceded and
  fixed by rejecting protected-root ancestors and requiring the exact macOS
  temp-root shape.

### Round 2

- Process substitutions, line continuations, quoted punctuation, and shell
  option variants created additional bypasses. Conceded and covered with
  source-aware normalization and recursive command inspection.
- Wrapper option values and clusters could hide the launched executable.
  Conceded and fixed in the shared option parser, with launcher-specific option
  semantics where required.
- `watch -x` and the initial `env -S` implementation could create false
  positives by reconstructing argv as shell text. Conceded and fixed by
  respecting exec mode and analyzing split argv directly.
- `find -exec rm ... {}` did not classify protected find roots, while prefixed
  placeholders could be over-classified. Conceded and fixed for direct
  placeholders beginning with `{}`, with a safe prefixed-placeholder
  counterexample.

### Round 3

- Repeated leading slashes bypassed protected-path classification. Conceded and
  fixed by collapsing repeated slashes in absolute removal targets, with
  regressions for `/var` and `/etc`.
- Executable matching was case-sensitive even though default macOS filesystems
  resolve names such as `RM` and `SUDO` case-insensitively. Conceded and fixed
  by normalizing executable basenames, with direct and wrapped regressions.

### Round 4

- An unexpected parser exception could reach `main()`'s pre-existing
  fail-open handler. Conceded and fixed at the public analysis boundary:
  commands that cannot be analyzed are rejected with a specific safety-analysis
  failure reason.
- A raw-text fallback for that boundary missed supported escaped executable
  spellings such as line-continuation `rm`. Conceded and replaced with genuine
  fail-closed behavior, with literal, escaped, and unrelated-command
  regressions under a synthetic parser failure.
- Native `find -delete`, broader glob syntax, and deletion through other
  interpreters were identified as existing capabilities outside issue #181's
  invocation-aware `rm` scope. They remain explicit follow-up concerns rather
  than regressions introduced by this PR.
- The missing Unreleased changelog entry was added.

## Unresolved tensions

The hook is an accident-prevention guard, not a full shell interpreter.
Arbitrary programs that indirectly launch `rm`, and values delivered to
`xargs` through pipes, files, or standard input, remain out of scope. Supported
launcher semantics are explicit so quoted prose is not reclassified as an
executable command.

## Ending condition

Converged after round 4. The final GitHub review's remaining in-scope
hardening concern and the critic's objection to its first disposition were
addressed with focused regressions.
