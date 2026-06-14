# task-loop Phase 0 — Agent-Teams primitive spike (checklist + findings)

**Purpose.** Prove the experimental Claude Code primitives that `run-cycle` (the orchestrator)
will rest on, **before** building it. This is throwaway verification, not TDD. Run each check
in a **teams-enabled, interactive session** and record the result inline. If a primitive can't
be made to work, STOP and adapt the design (the "If it fails" note says where) before building
`run-cycle`.

**How to use.** Work top to bottom. Check the box when a check passes; write the observed
behavior on its `RESULT:` line. The **Decision gate** at the end says whether `run-cycle` is
buildable as designed.

**Session prerequisites:** a terminal session (not headless), a GitHub repo you can write
issues/PRs in, and `gh` authenticated.

---

## A. Preconditions

### A1. Enablement + version
- [ ] `claude --version` is **≥ v2.1.32**.
- [ ] `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` is set (shell env or `~/.claude/settings.json`
  `env`). Restart the session after setting it.

```bash
claude --version
echo "${CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS:-unset}"
```
RESULT: ___ (version: ___ ; flag: ___ ; restart needed: ___)

### A2. Plugin installed and `cycle-worker` discoverable
- [ ] The `task-loop` plugin is installed/enabled locally (it is registered in
  `.claude-plugin/marketplace.json`). Add this repo as a local marketplace and install it
  (`/plugin` → add local marketplace → install `task-loop`, or `claude plugin marketplace add .`
  then `claude plugin install task-loop`).
- [ ] In the session, confirm `cycle-worker` appears as an available **agent type**.

RESULT: ___ (cycle-worker resolves as agentType: ___)

> If it fails: the agent isn't being discovered — check the plugin install and `agents/` path
> before anything else; `run-cycle` cannot spawn workers without this.

---

## B. Loop + stop-signal primitives

### B1. `/loop` self-paced entry
- [ ] A skill / prompt can enter or require built-in `/loop` in self-paced mode (no fixed
  interval).
- [ ] From inside `/loop`, calling `ScheduleWakeup` (e.g. 60 s) causes the harness to
  **re-invoke** the loop turn.

Prompt to try: *"Start a self-paced /loop. On this turn, call ScheduleWakeup for 60s with a
note, then stop. Confirm you are re-invoked after the wake."*

RESULT: ___ (/loop entry: ___ ; ScheduleWakeup re-invoke from lead: ___)

> If it fails: the orchestrator's continuous-service driver is unavailable — revisit the
> loop-mechanism conclusion (the whole termination model assumes `/loop`+`ScheduleWakeup`).

### B2. Stop-signal writer + drain
- [ ] Identify a mechanism that writes `.claude/task-loop/stop-request.json` **atomically**
  (temp file + `mv`) on a schedule. Try, in order, whichever is available:
  1. `CronCreate` (a scheduled agent that writes the file),
  2. the `schedule` skill (a cloud routine), or
  3. a background shell job: `Bash(run_in_background)` running `sleep <N> && printf '{}' > t && mv t .claude/task-loop/stop-request.json`.
- [ ] Confirm the orchestrator pattern **reads** the flag at the top of a turn and treats it as
  "drain" (no new dispatch). (Test the read/drain behavior with a manually-created flag.)

RESULT: ___ (chosen writer: ___ ; atomic write works: ___ ; read-at-top-of-turn drains: ___)

> If none of 1–3 works as a scheduled writer, document the fallback (operator manually creates
> the flag) — `run-cycle` still drains on it; only the *scheduling* is manual.

---

## C. Agent Teams primitives

### C1. Create a team + spawn ONE worker by `agentType`, pass metadata
- [ ] Create a team and spawn exactly **one** teammate using `agentType: cycle-worker`, passing
  task metadata in the spawn prompt.
- [ ] The teammate receives the metadata (it can read `task_id`, `issue`, `spawned_plan_revision`
  from its prompt).

Prompt to try: *"Create an agent team. Spawn one teammate using the cycle-worker agent type with
the prompt: `task_id=T1 issue=<n> spawned_plan_revision=1 — write SPIKE_OK <task_id>
<spawned_plan_revision> to spike-<task_id>.txt and report done`. Wait for its idle notification."*

```bash
cat spike-T1.txt   # expect: SPIKE_OK T1 1
```
RESULT: ___ (spawn by agentType: ___ ; metadata received: ___)

### C2. Idle / completion notification to the lead
- [ ] When the teammate finishes and goes idle, the **lead is notified automatically** (no
  polling). Note how the notification surfaces.

RESULT: ___ (auto idle notification to lead: ___)

> If it fails: the orchestrator's "dispatch-and-wait" model breaks — it would have to poll.
> Re-examine the loop-mechanism conclusion's reliance on idle notifications.

### C3. `SendMessage` lead ↔ teammate
- [ ] The lead can `SendMessage` a teammate by name, and the teammate can message back. (Used for
  coordination; the merge gate itself is orchestrator-executed, not a handshake.)

RESULT: ___ (lead→teammate: ___ ; teammate→lead: ___)

### C4. `TaskCreate` with dependency edges + auto-unblock
- [ ] Create two tasks where B `depends_on` A; confirm B is **not** claimable until A is marked
  complete, then **auto-unblocks**.

Prompt to try: *"Create task A and task B with B depending on A. Show that B is blocked, then mark
A complete and confirm B becomes available."*

RESULT: ___ (dependency blocks: ___ ; auto-unblock on completion: ___)

> This is the orchestrator's core control surface (your item 3). If dependency auto-unblock
> doesn't work, the orchestrator must enforce ordering manually — a design change.

### C5. No nested teams (confirm the constraint)
- [ ] Confirm a teammate **cannot** spawn its own team/teammates (expected per the docs), so the
  worker's intra-task parallelism must use `Workflow`/inline subagents.

RESULT: ___ (nested team blocked as expected: ___)

### C6. Ephemerality on resume (HARD READY gate)
- [ ] Confirm in-process teammates do **not** survive `/resume` / session end. This underpins the
  recovery model. **Hard gate:** if teammates *can* survive detached, two attempts could coexist
  far more easily, so the durable `attempt_id` fence + per-attempt branches are not optional —
  do **not** run unattended until ephemerality is confirmed.

RESULT: ___ (teammates ephemeral on resume: ___)

### C7. Worktree isolation actually honored (HARD READY gate)
- [ ] Spawn **two** teammates with `agentType: cycle-worker` (which declares `isolation: worktree`),
  each reporting `git rev-parse --show-toplevel`. Require the two toplevels to be **distinct from
  each other AND both different from the lead's** `git rev-parse --show-toplevel`.
- [ ] **Hard gate:** if isolation is silently ignored (a teammate's toplevel == the lead root),
  workers share the lead cwd and race the index/filesystem — the merge gate cannot detect cross-task
  contamination. "Agent Teams enabled" is **not** READY without this probe passing. (The worker's
  runtime self-check is the second line of defense, but the probe must pass first.)

Prompt to try: *"Create an agent team. Spawn two cycle-worker teammates; each runs
`git rev-parse --show-toplevel` and reports it. Then print the lead's own toplevel."*

RESULT: ___ (two distinct worktrees, both ≠ lead root: ___)

---

## D. Control-protocol round-trip against real GitHub

> Validates `gh_store` + `control_log` against real `gh` output (the reviewers flagged that `gh`
> returns comment `id` as a node-ID string and `createdAt` for the watermark — confirm the real
> shapes match the code).

### D1. `read_comments` returns the real shape
- [ ] On a real issue with ≥1 comment, `gh_store.read_comments(<issue>)` returns
  `(id, created_at, body)` triples, oldest-first, with `id` a node-ID string and `created_at`
  canonical UTC.

```bash
python -c "import sys; sys.path.insert(0,'task-loop/scripts'); import gh_store; \
print(gh_store.read_comments(<issue>))"
```
RESULT: ___ (id is node-id string: ___ ; created_at is `...Z`: ___ ; oldest-first: ___)

### D2. End-to-end: worker posts inbox → orchestrator parses → emits control → replay
- [ ] Post a fenced `task-loop-event` MERGE_REQUEST inbox comment on a task issue (as the worker
  would, via `gh issue comment --body-file`).
- [ ] Read it back, `control_log.parse_events` it, run the orchestrator steps (filter_new_inbox →
  assign_seq a MERGE_GRANTED with `source_comment_ts` from the comment's `createdAt` → post it on
  a control issue), then `control_log.replay` the control issue and confirm the task shows
  `merged` and the uuid is in `seen_source_uuids`.

RESULT: ___ (parse: ___ ; replay rebuilds state from real gh: ___)

> If `createdAt` is ever NOT second-granularity canonical UTC on this GitHub instance, the
> `_is_canonical_utc` validator will reject it — record the actual format so the validator can be
> reconciled.

---

## E. Worker skill-dependency detection

### E1. Detect required skills
- [ ] Determine a reliable way to detect whether `superpowers:brainstorming` and
  `dev-skills:discuss-with-codex` are available before relying on them (e.g. check installed
  plugin dirs under `~/.claude/plugins`, or attempt-and-catch). Record the chosen method (this is
  what the skills' fail-fast preflight will use).

RESULT: ___ (detection method: ___)

---

## Decision gate

`run-cycle` is **buildable as designed** when A1–A2, B1–B2, C1–C4, and D1–D2 all pass. **C6
(ephemerality) and C7 (worktree isolation honored) are now HARD gates for unattended runs** — the
single-flight safety (durable `attempt_id` + per-attempt branches) and the no-cross-task-contamination
guarantee depend on them (C5/E1 remain confirmations/inputs).

- [ ] **All required checks pass** → proceed to build `run-cycle` (the orchestrator state machine
  on top of `control_log`/`gh_store`, using the confirmed primitives).
- [ ] **A primitive failed** → record which, and adapt the design before building:
  - B1 fails → revisit the loop driver (loop-mechanism conclusion).
  - C2 fails → the dispatch-and-wait model needs polling.
  - C4 fails → the orchestrator must enforce task ordering itself.
  - B2 (all writers) fails → manual stop-flag only; document it.

**Findings summary (fill in after running):**
- Primitives confirmed working: ___
- Primitives needing a workaround: ___
- Design changes required before `run-cycle`: ___
