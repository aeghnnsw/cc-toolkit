# Codex Run-cycle Pressure-test Conclusion

## Settled Position

Ship a conservative first Codex `run-cycle` slice as a manual single-pass controller. The main Codex thread is the controller; it reads task-loop state, GitHub, and `docs/task-loop/`, then reconciles, materializes, and dispatches only when worker launch can be observed in the active session. Full unattended scheduling remains out of scope.

## Key Decisions

- The controller is the only actor that uses the task-loop CLI, mutates task DB state, edits `proposal.md`, or merges PRs.
- Before `task-loop claim --json`, the controller must dry-run spawn `task_loop_cycle_worker` and observe the expected missing-input refusal.
- Before claiming, the controller must also know it can observe real worker acceptance or completion in the active Codex surface. If not, it may reconcile/materialize/report, but must not claim.
- After claim, the controller must build a complete dispatch packet. Missing issues are resolved by creating or adopting a GitHub issue and running `task-loop set-issue`.
- Reset is allowed only with positive evidence that no live worker owns the task. Ambiguous post-launch state stays `working` and is reported as `dispatch outcome unknown`.
- PR correlation uses both the persistent issue link and the task-specific study-log path for the current attempt.

## Strongest Objections And Dispositions

- Claiming before worker spawn is proven can orphan `working` rows. Conceded: dispatch is conditional, and pre-claim worker probing is required.
- “Worker spawn is available” was underspecified. Conceded: the gate is an observable dry-run spawn probe.
- A claimed task may lack an issue, so the real worker packet may be incomplete. Conceded: packet validation and `set-issue` happen before real launch, with reset if no packet was launched.
- A worker can spawn but immediately refuse the task. Conceded: real dispatch must produce observable acceptance/completion or an explicit refusal.
- Resetting after ambiguous launch can duplicate live work. Conceded: ambiguous post-launch state is never reset; it is surfaced for the next pass.

## Unresolved Tensions

- Codex custom-agent support may vary by active session. The skill therefore documents a capability gate rather than assuming a platform API.
- This first slice can block while observing a worker if the surface lacks an intermediate acceptance signal. That is acceptable for manual use and avoids unsafe unattended claims.

## Ending Condition

Converged at round 6. The critic reported no substantive objection after the design separated no-claim, positive-evidence reset, and unknown-after-launch handling.
