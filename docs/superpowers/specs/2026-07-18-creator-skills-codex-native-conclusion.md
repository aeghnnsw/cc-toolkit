# Creator Skills and Step Workflow Pressure-Test Conclusion

## Settled Position

Proceed with a Codex-native `creator-skills` package containing `sci-slides`
and `sci-figure-format`, and add a Codex-native `step-workflow` to the existing
`dev-skills` package. Keep the Claude skill trees unchanged, use the established
`codex-skills/` layout, register `creator-skills` in the Codex marketplace, and
bump the Codex `dev-skills` manifest from `1.0.0` to `1.0.1`.

Native support is accepted only when an isolated Codex installation registers
all three namespaced skills through `skills/list` from the installed
`codex-skills/` trees.

## Decisions

- Use separate Codex skill trees rather than sharing the Claude files.
- Preserve the existing scientific guidance while normalizing frontmatter.
- Replace `TodoWrite` with `update_plan` in the Codex step workflow.
- Do not let `step-workflow` override established repository structure or
  naming conventions.
- Exclude the generic plugin validator because it incorrectly hard-codes the
  default `skills/` root; validate the declared roots directly instead.
- Verify registry loading, namespacing, installed paths, and loader errors with
  the app server rather than treating installation or file presence as proof.
- Version-bump `dev-skills` so existing installations receive a new cache entry.

## Objections and Dispositions

### Round 1: Validator contract mismatch

The generic plugin validator rejects `./codex-skills/`, even though that is the
working repository pattern. Agreed. The design now uses explicit executable
checks for relative, contained skill roots, expected directories, and matching
frontmatter names.

### Round 2: Installation does not prove native discovery

Installing a plugin and observing its files does not prove Codex loaded its
skills. Agreed. The design now calls `skills/list` in the same isolated Codex
home and asserts exact namespaced registry entries, installed native paths, and
the absence of loader errors or Claude-tree paths.

### Round 3: Existing `dev-skills` users could remain on a stale cache

Adding `step-workflow` without changing `dev-skills` version would prove only a
clean install and could leave existing `1.0.0` caches unchanged. Agreed. The
Codex manifest advances to `1.0.1`, and validation asserts that installed
version.

### Round 4: Convergence

The critic returned `NO SUBSTANTIVE OBJECTION`, finding the revised design
decision-complete across versioned delivery, native discovery, platform
adaptation, marketplace packaging, validation, and Claude-tree non-regression.

## Ending Condition

Pressure testing ended by convergence after three substantive objections were
resolved and the next review found no remaining substantive objection.
