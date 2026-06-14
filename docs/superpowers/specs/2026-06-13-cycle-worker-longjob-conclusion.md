# cycle-worker long-running-job rule — Codex deliberation conclusion

**Date:** 2026-06-13 · **Method:** `dev-skills:discuss-with-codex` (adversarial), 5 rounds.
**Outcome:** Converged — Codex replied **NO FURTHER OBJECTIONS**. Scoped to
`task-loop/agents/cycle-worker.md` only; no protocol/`control_log.py` change.

## Problem

Cycle-workers could get stuck foreground-blocking on long-running jobs (test suites, builds, etc.).
A foreground `Bash` call is hard-capped at 10 minutes, so a long job is *killed*, and a synchronous
block stalls the worker's turn. The user asked to add a rule to the worker agent config: jobs
estimated > ~5 min should be backgrounded and watched.

## Settled rule (as added to `cycle-worker.md`)

For a **shell command** estimated to approach the 10-min foreground cap or with unbounded variance
(> ~5 min):

```bash
J=job-<label>-<attempt_id>-r<N>     # one RUN-unique stem the worker picks; bump <N> per rerun
rm -f "$J.status"                   # clear before launch
( cmd > "$J.log" 2>&1; rc=$?; printf '%s\n' "$rc" > "$J.status"; exit "$rc" )
```
- Run the command **itself** with `Bash run_in_background`; the background completion is the single
  terminal signal.
- **Verify BOTH, in order:** (a) `<J>.status` **exists** and equals `0` (authoritative exit code,
  written by the wrapper not the job's stdout — unspoofable, and a *missing* status = failure); and
  (b) `Read <J>.log` and scan for failure evidence, **inspecting each match in context** (a `0` exit
  can hide a swallowed child failure; `failed=0` / `0 errors` / test *names* are benign). Proceed only
  if status is `0` **and** every match is benign. Never infer success from silence.
- **Streamed progress** (CI steps, epochs) → `Monitor`, filter covering success **and** failure.
- **Completion signaled outside the launched process** (detached server, remote CI) → and only then →
  a `run_in_background` `until`-loop. Never use `until grep` for an ordinary command (fires early on
  an incidental `Error`, or hangs if the marker never prints).
- **Non-shell long calls** (a `Workflow` run, `discuss-with-codex`) are **not** shell jobs — rely on
  the tool's own bounded/background completion; if unbounded with no such mechanism, break it into
  smaller bounded calls or escalate to the orchestrator.

## Objections raised and how each resolved

1. **(R1) Don't weaken "verify terminal state" to "the process exited"** — a wrapper can exit `0`
   while the log says FAILED/OOM. Applied: normalized exit status + a *mandatory* log read & failure
   scan. Also: lead with plain `run_in_background` (not the `until`-loop), demote the `until`-loop to
   externally-signaled completion, keep ~5 min ("approach the cap / unbounded variance").
2. **(R2) Substrate overclaim** — the trigger listed `Workflow`/Codex but the mechanism was a Bash
   wrapper. Applied: scoped the wrapper to shell jobs; added a dedicated non-shell bullet.
3. **(R2) In-log `__CYCLE_EXIT` marker is spoofable/stale** — logs are untrusted output. Applied:
   separate status file.
4. **(R2) "No failure signatures" too absolute** (`failed=0`, `0 errors`, test names match).
   Applied: context-aware inspection of each match, not a blind regex gate.
5. **(R3) The snippet hid filenames + used two different UUIDs** (unpairable; worker can't `Read`
   them). Applied: one worker-chosen job stem with derived `.log`/`.status`.
6. **(R3) Over-asserted the `Workflow` background contract.** Applied: lead with "use the tool's own
   bounded/background completion," Workflow/codex as parenthetical in-harness examples.
7. **(R4) Stem was attempt-unique but not run-unique** — a rerun of the same label in one attempt
   could read a prior run's stale `0` (esp. if killed before writing). Applied: **run-unique** stem
   (`-r<N>`) + **clear status before launch**; a missing status is treated as failure.

## How it ended

Converged after 5 rounds — Codex's objections narrowed from substance (verify-vs-exited) to a final
stale-reuse edge case, then `NO FURTHER OBJECTIONS`. No unresolved tensions.
