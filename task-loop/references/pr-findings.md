# PR findings — the worker → orchestrator contract

The cycle-worker's durable record is a **git-tracked study log**,
`docs/task-loop/logs/<NNN>_<task>.md` (`<NNN>` = the task `seq`, zero-padded — e.g.
`007_stage2.md`), **committed as part of its PR**. The orchestrator reads the PR to decide the task's
fate. This is a markdown convention, not a machine format (the orchestrator *reads* the PR).

The **cycle-worker** writes it; the **orchestrator** (`run-cycle`) reads it.

## The study-log record (`docs/task-loop/logs/<NNN>_<task>.md`)

```
## Study log — task <seq>: <title>

**Outcome:** success          <!-- exactly one of: success | failed | blocked -->

### Rubric
- [x] <binary acceptance item> — <command run + result proving it>

### Evidence
<key commands actually run + their real output — enough to trust the rubric>

### Findings
<follow-up work discovered, surprises, risks, decisions taken;
 for `blocked`: state the blocker concretely so it can be filed as a dependency task>
```

- **`<NNN>` = the task `seq`** (zero-padded) — the only index; no separate counter.
- **Exactly one `**Outcome:**` line** — the worker's honest verdict.
- **Rubric is binary** — an item is checked only when a command was run and its output confirms it
  (`superpowers:verification-before-completion`).

## The PR

The PR carries the study-log record in its diff. Keep the PR **body** short:

```
Refs #<issue>

**Outcome:** success
Study log: docs/task-loop/logs/<NNN>_<task>.md
```

- **`Refs #<issue>`, never `Closes #<issue>`** — the worker links the issue but never auto-closes it;
  the orchestrator owns every issue transition.

## The three outcomes

The worker declares one; the orchestrator acts (full handling in `run-cycle` §8). Every outcome funnels
the task `working → closed` — nothing is dropped.

| Outcome | Worker means | Orchestrator bookkeeping |
|---|---|---|
| `success` | rubric green; task done | merge PR, `close` task, file **Findings** follow-ups as new tasks, close issue |
| `failed` | can't complete as specified, no dependency to name | `close` task (PR stays as the record) |
| `blocked` | something must land first | `close` task, create a new task `--dep <blocker>` carrying the remaining work, **re-link the issue** to it (stays open) |

Whether a `failed`/`blocked` PR is merged, closed, or left open is the orchestrator's judgment
(§8–§9); the worker never merges.

## Finding the PR

- **Fast path** — the worker's handoff message reports the PR number + URL + head SHA + outcome.
- **Durable path** (cold start) — `Refs #<issue>` links it; `gh pr list --search "<issue>"`. Branch
  naming isn't prescribed, so the issue is the reliable link.
