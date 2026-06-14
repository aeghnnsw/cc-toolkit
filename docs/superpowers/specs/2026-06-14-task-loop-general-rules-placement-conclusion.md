# Conclusion — Where do task-loop's general worker rules live?

> **SUPERSEDED (2026-06-14, same day — issue #129).** This conclusion recommended keeping general
> rules in the rendered playbook (and rejected system-prompt-only). The user subsequently made the
> opposite call by explicit decision: **all general/project-agnostic worker instructions —
> including the worktree setup — live in the `cycle-worker` agent contract only; the rendered
> `task-loop.md` holds only this project's parameters.** Rationale (the user's): general rules then
> update centrally with the plugin (no re-running `create-cycle` per project) and there is a single
> copy, so nothing can drift. This was a deliberate user override of the Codex/Claude recommendation
> below; the analysis is retained for the record, but the placement decision here no longer reflects
> the implementation.

**Goal:** Should task-loop's general (project-agnostic) worker rules live ONLY in the
`cycle-worker` agent system prompt, instead of being duplicated into the rendered
`task-loop.md` playbook (the `create-cycle` skeleton)? Triggered by wanting to add a new
general rule: "fully utilize available compute (cores/GPUs/SLURM), parallelize, never crawl
single-threaded."

**How it ended:** Converged after 3 rounds with Codex (adversarial critic).

## Settled position

**NO — do not move general rules into the system prompt only.** The committed, rendered
`docs/task-loop/task-loop.md` must remain the **self-contained, auditable contract**: it
explicitly declares itself "the instruction set a worker follows," and the system prompt
already defers to it ("follow `task-loop.md` step by step"). Hollowing it out would gut
auditability, manual recovery, and reproducibility, and would turn plugin-version bumps into
**silent, undiffable behavior changes** in every already-scaffolded project — especially
dangerous for compute policy (cost/quota/cluster-etiquette).

### The new compute rule answers its own placement
Its *safe* form is **project-parameterized**, so it physically cannot be a system-prompt-only
rule. It belongs in the **rendered playbook** as an operating principle carrying a new
`{{COMPUTE_POLICY}}` placeholder — exactly like `{{CONTRACTS}}` / `{{TEST_CONVENTIONS}}`, which
already live playbook-only and are **not** duplicated in `cycle-worker.md`. Two reasons it must
be parameterized rather than a blanket "use everything":

1. **Etiquette/quota:** cluster/SLURM submission needs an account/partition and has
   shared-resource implications — it must be gated behind explicit project policy, never a
   silent default.
2. **Oversubscription (correctness):** the loop runs **up to 5 concurrent workers on one host**
   (`skeleton:78`, `cycle-worker.md:89`). If each worker grabs all CPUs/GPUs they thrash. The
   safe default is a **bounded per-worker share**, not "grab everything."

The general *backgrounding* kernel ("never foreground-block / never let a long job block")
already exists in BOTH files — unchanged. The compute principle is **additive** and references it.

## Key decisions

1. Reject "system-prompt-only." Playbook stays the authoritative, self-contained contract.
2. Add the compute rule as a **parameterized playbook operating principle** (`{{COMPUTE_POLICY}}`),
   NOT in the system prompt.
3. **Ship the placeholder machinery with the rule** (Codex's rollout-gap catch): update
   `create-cycle/SKILL.md` to discover/interview/render `{{COMPUTE_POLICY}}` so no generated
   playbook is ever left with a raw placeholder or ad-hoc policy.
4. **Concrete safe default** for `{{COMPUTE_POLICY}}`: parallelize aggressively but cap each
   worker to a bounded share of the 5-seat loop (default `max(1, floor(nproc/5))`-style),
   background long jobs, never single-thread a parallelizable task; **local CPU only** — no
   GPU/SLURM/multi-node submission unless the policy explicitly names the account/partition/device.
   (Future enhancement: orchestrator passes an explicit `worker_parallelism_budget` since it,
   not the worker, knows live seat occupancy.)
5. Optionally add a `directions-template.md` heading for temporary compute overrides (steering
   file is highest priority).
6. **Defer the drift fix** (the dual-source duplication of the *non-parameterized* worker
   contract) to its own follow-up issue: a canonical `task-loop/shared/worker-guardrails.md`
   asset, generated/synced into both surfaces, a unittest verifying both embedded blocks match
   canonical, **plus a CI workflow that actually runs it** (without CI the test is advisory).
   Kept separate because the largest shared chunk is the worktree block and a botched sync could
   corrupt the live agent contract — coupling it to a behavior addition is risky.

## Strongest objections Codex raised, and how each resolved

- **"Always-loaded isn't enough — the playbook must be a complete contract."** Conceded;
  drove the rejection of system-prompt-only.
- **"Central updates = silent cross-project behavior change, dangerous for compute."** Conceded;
  drove "behavior change must be a reviewable diff in the committed playbook" → parameterized
  playbook placement.
- **"Delimiter+unittest isn't drift-proof (no CI), byte-equality is two sinks + an alarm, and
  the worktree guardrail is too big to slim."** Conceded all three; replaced my inconsistent
  "slim + byte-equality" mechanism with Codex's canonical-asset design — and moved it to a
  follow-up so this PR stays a clean behavior addition.
- **"`{{COMPUTE_POLICY}}` rollout gap + bounded share needs a real allocator."** Accepted;
  added decisions 3 and 4.

## Unresolved tension (a genuine user decision)

The user's stated intent ("use ALL GPUs and CPUs, go fast, don't waste") conflicts with the
safe conservative default (bounded per-worker share to avoid 5-worker oversubscription). Chosen
resolution: the **default** policy is conservative-safe, but `{{COMPUTE_POLICY}}` is
**user-tunable per project**, and the `create-cycle` interview should surface this fork so the
project owner picks aggressive-vs-bounded explicitly (knowing their host size, typical seat
occupancy, and whether jobs are CPU- or GPU-bound). To be confirmed with the user before
writing the default text.
