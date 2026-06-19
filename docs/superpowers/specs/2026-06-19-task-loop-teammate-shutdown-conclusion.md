# Task-Loop Teammate Shutdown Conclusion

## Settled Position

Claude `run-cycle` must not use `TaskStop` to clean up cycle-worker teammates. `TaskStop` is for
background shell tasks, while Agent Teams teammates are shut down by asking the recorded teammate
id/name to shut down.

After task closure, the orchestrator sends a graceful shutdown request only when this session has the
worker's teammate id/name for the closed seq. The worker stays idle until that request and approves it.
If no in-session handle exists, shutdown is not attempted and the orchestrator surfaces that fact as a
cleanup finding. If shutdown is rejected, does not respond by the next drain tick, or still appears
alive after approval, the orchestrator records and surfaces the cleanup failure. The closed seq is no
longer active work and must not block Loop C self-close solely because cleanup failed.

## Key Decisions

- Replace `TaskStop` reaping guidance with a graceful teammate shutdown request.
- Record teammate id/name against each seq for in-session liveness and shutdown targeting.
- Make worker handoff explicit: workers do not self-terminate, but approve shutdown requests for their
  closed seq.
- Treat closed-task shutdown failures as cleanup findings, not reasons to reopen/reset tasks or keep
  Loop C alive forever.
- Surface `shutdown not attempted for task <seq>: no in-session teammate handle` when another
  orchestrator closes a task without owning the teammate handle.
- Run a final cleanup audit before goal-met cancellation or Loop C self-close so shutdown uncertainty
  from the last tick is surfaced.
- Bump task-loop plugin manifests and affected Claude skill versions so cached installs refresh.

## Pressure-Test Round 1

Critic: A shutdown request is cooperative and rejectable. If the docs only say to request shutdown,
Loop C can still deadlock because a closed task's worker may reject, hang, or remain addressable after
approval.

Disposition: Conceded and revised. The final contract separates active task liveness from closed-task
cleanup. Shutdown failure is surfaced, but it does not block Loop C once the seq is already closed.

## Pressure-Test Round 2

Critic: The existing reset rule treated a fresh single-orchestrator session as proof that pre-PR
workers from prior Agent Teams sessions were dead. The evidence does not establish that strongly enough,
and a blind reset could clobber a still-live teammate.

Disposition: Conceded and revised. Fresh session alone is no longer positive no-live-owner evidence.
Opaque `working`-no-PR rows are reset only after in-session observed death, human reset, or explicit
operator assertion that the prior Agent Teams session is terminated and no other orchestrator owns the
task. Otherwise they are surfaced.

## Pressure-Test Round 3

Critic: If the final PR closes on the same tick that satisfies goal completion or Loop C self-close,
there may be no next drain tick to detect a rejected, missing, or incomplete shutdown response.

Disposition: Conceded and revised. Before goal-met cancellation or Loop C self-close, the orchestrator
runs a final closed-teammate cleanup audit. Shutdown is verified only after approval and a
post-approval addressability check confirms the teammate is no longer reachable. Otherwise it surfaces
`shutdown unverified for task <seq> teammate <id/name>` as a cleanup finding and then stops.

## Pressure-Test Round 4

Critic: Any orchestrator can integrate a PR, but teammate handles are in-session only. If orchestrator B
closes a task whose worker was spawned by orchestrator A, B cannot send shutdown and the prior audit did
not surface that missing handle.

Disposition: Conceded and revised. Closed-task cleanup now branches on handle availability. With a
handle, the orchestrator requests shutdown and audits it. Without one, it surfaces
`shutdown not attempted for task <seq>: no in-session teammate handle`. Only the owning live
orchestrator can later request shutdown if it observes the closed seq.

## Pressure-Test Round 5

Critic: The final cleanup audit treated approval as enough, but the contract also says cleanup fails if
the teammate remains addressable after approval. A same-tick final shutdown approval could be followed
by immediate generation cancellation without checking whether the teammate actually exited.

Disposition: Conceded and revised. Shutdown verification now requires approval plus a post-approval
addressability check confirming the teammate is no longer reachable. If that check has not happened or
the teammate remains reachable, the audit surfaces `shutdown unverified for task <seq> teammate
<id/name>` before stopping.

## Pressure-Test Round 6

Critic: The docs still claimed every orchestrator reading the same durable state takes the same action,
but cleanup now depends on nondurable in-session teammate handles.

Disposition: Conceded and revised. The invariant now says durable task/PR/proposal decisions are
re-derived and convergent, while liveness and teammate cleanup may differ by in-session handle
ownership.

## Unresolved Tensions

Claude Agent Teams currently has no documented hard-kill equivalent for a teammate. The best available
contract is graceful shutdown plus bounded cleanup reporting. Without a durable worker ownership marker,
fresh-session pre-PR recovery may need an operator reset/assertion, and non-owning orchestrators can
only report missing teammate handles.

## Ending Condition

Reached round cap after six critic rounds; all substantive objections were handled in the final text.
