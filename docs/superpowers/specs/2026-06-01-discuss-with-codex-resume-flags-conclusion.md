# Conclusion: discuss-with-codex resume-flag asymmetry (issue #113)

Date: 2026-06-01
Branch: `doc-113-codex-resume-flags`
Initial discussion: 6 rounds with Codex CLI as adversarial read-only critic.
Outcome: converged at Round 6 with `NO FURTHER OBJECTIONS`.

## Settled position

The fix delivers a small, internally-consistent change across three docs
(SKILL.md, plan.md, design.md) that closes the bug reported in issue #113
and four additional weaknesses surfaced during adversarial review:

1. The `codex exec / codex exec resume` flag asymmetry (sandbox + cwd are
   bound at kickoff; resume rejects `-s`/`-C`) is now documented at both
   anchor points — Step 1 lead-in prose and an inline `# NOTE:` directly
   above the Step 2 resume call.
2. The empty-`THREAD_ID` case is no longer a silent fall-through to
   `codex exec resume --last`. The skill now branches on the kickoff exit
   status:
   - Non-zero exit (124 = timed out) follows the existing **Error** stop
     condition (retry once, then conclude cut-short).
   - Zero exit but no parseable `thread.started` event is a hard stop with
     diagnostics from `err.log` and `events.jsonl`.
3. The `THREAD_ID` parser is now a single `sed -nE '/type-match/s/.../p'`
   pipeline that tolerates JSON whitespace on both the type-match and the
   thread_id extraction, and uses strict match semantics (the `p` flag
   only emits when the substitution matched, so non-matching input
   produces empty output rather than the raw line).
4. The kickoff exit status is captured into a `status` variable so the
   failure-class split is load-bearing.
5. The plan doc's Step 4 verification block locks in 11 invariants — six
   original (helper, stdin redirect, kickoff/resume/smoke call shapes,
   tolerant thread_id capture) and five new (`--last` absent, Step 2
   NOTE present, Step 1 asymmetry prose present, tolerant parser, status
   capture).

## Strongest objections raised and how they resolved

| Round | Codex objection | Resolution |
|-------|-----------------|------------|
| 1     | The fix only touched SKILL.md; the design spec and plan doc still preserved the old `--last` fallback prose, so the bug could come back via regeneration or audit. | Updated both docs to match the SKILL.md hard-stop. |
| 2     | "Scope defer" on the THREAD_ID parser is too convenient — the hard-stop change makes parse robustness part of this PR's behavior surface, not adjacent to it. | Conceded. Tightened the regex (`sed -nE … p`, whitespace tolerance, strict match semantics). Also updated plan's verification to lock the new invariants. |
| 3     | End-to-end tolerance not actually achieved — only the sed stage was hardened; the upstream `grep -m1` filter still required compact JSON. Empirically verified against `{"type" : "thread.started", "thread_id" : "abc-123"}`. | Replaced grep+sed with a single `sed -nE '/pattern1/s/pattern2/.../p'` pipeline. Updated verification to assert the new shape. |
| 4     | The new "empty THREAD_ID → hard stop" rule conflicted with the existing **Error** stop condition (which says non-zero exit / timeout → retry once). | Conceded. Captured `status=$?` and split the failure handling into two typed classes. |
| 5     | "Internally consistent" claim was still false because the design doc still conflated the two failure classes. | Updated the design doc paragraph to mirror the split explicitly. |

## Unresolved tensions

None. All five substantive objections were conceded and addressed in-PR.

## Out-of-scope refinements accepted

None deferred. (One adjacent improvement was initially proposed for a
follow-up issue — strengthening the JSON parser — but Codex's Round 2
argument that the parse boundary had moved into PR scope was correct, so
the parser was hardened in this PR rather than deferred.)

## How the discussion ended

Round 6: Codex replied with the single line `NO FURTHER OBJECTIONS` plus
one sentence on why the position holds. Converged within the 6-round cap.
