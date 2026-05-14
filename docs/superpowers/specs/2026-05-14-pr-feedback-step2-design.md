# pr-feedback Step 2 — Wait Mechanism Redesign

## Goal

Rewrite Step 2 of `dev-skills/skills/pr-feedback/SKILL.md` so the "wait for external reviewers" phase is deterministic, bounded, and autonomous. Eliminate the three failure modes observed in practice: agents skipping the wait, hanging on the wait, or asking the user mid-step.

## Problem

The current Step 2 instruction is "wait 2 minutes" with no prescribed mechanism. Three distinct misinterpretations have been observed:

1. **Never waits at all** — agent moves to Step 3 immediately with self-review issues only.
2. **Waits forever / hangs** — agent tries a foreground `sleep 120`, which the harness blocks as a long leading sleep, and the agent gets stuck.
3. **Asks user mid-Step 2** — agent breaks the autonomy clause and prompts for confirmation.

Root cause: the skill specifies an outcome ("wait 2 minutes") but no concrete mechanism. Different agent interpretations diverge.

## Design Decisions

### Wait mechanism: background scheduled wait

Use the Bash tool with `run_in_background: true` running `sleep 120`. This is the harness's native pattern for one-shot waits: the agent fires the command, returns control, and is auto-notified when the timer elapses. Foreground long sleeps are blocked by the harness, so they're explicitly forbidden in the new text.

Considered alternatives:
- **Foreground `sleep 120`** — rejected: harness blocks long leading sleeps.
- **Until-loop with short sleeps** — rejected: verbose, harder to teach in skill prose, no functional advantage over background sleep.
- **`ScheduleWakeup`** — not available outside `/loop` dynamic mode.
- **`CronCreate`** — designed for recurring tasks; runs independently of the conversation.

### Empty-external behavior: proceed, trust cycle 2

If the wait completes and no external comments are present, the agent proceeds to Step 3 with self-review issues only. It does not extend the wait, does not ask the user. Step 6's loop catches any late-arriving comments in cycle 2 — this is the existing safety net, now made explicit.

This is the load-bearing decision: once the skill says "proceed if external is empty," the 2-min wait stops being safety-critical. It's a courtesy delay to reduce cycles, not a correctness guarantee. The simplest wait mechanism becomes sufficient.

### Autonomy reinforcement

The existing "never ask the user" clause is preserved and reinforced. The new text spells out each tempting branch (don't ask to wait longer, don't ask to confirm, don't ask to add reviewers) to prevent agents rationalizing around it.

## Proposed Step 2 Text

```markdown
## Step 2: Gather External Reviews

External reviewers (e.g., GitHub Actions bots, Claude Code Review) are
typically triggered when the PR is pushed and run in parallel with the
self-review. They often take longer to complete than the self-review.

**Wait via a background-scheduled delay, then read comments:**

1. After self-review completes, fire a 2-minute background wait. Use the
   Bash tool with `run_in_background: true` and the command `sleep 120`.
   The harness will notify when it completes — do not poll, do not run a
   foreground `sleep`, do not invoke any other tool while waiting.

2. After the notification, read all reviewer comments on the PR — review
   summaries, inline review comments, and general PR comments. Extract
   actionable feedback items.

3. **If no external reviews exist after the wait, proceed to Step 3 with
   self-review issues only.** Do not extend the wait. Do not ask the user.
   The Step 6 loop will catch any late-arriving comments in a subsequent
   cycle — that's by design.

**Never ask the user for input during this step.** Not to wait longer,
not to confirm, not to add reviewers. The full step is autonomous.
```

## Out of Scope

- Enumerating exact `gh` commands for each comment surface (Step 2 already lists the categories conceptually; "wrong surface" failure was not observed).
- Check-based conditional wait (`gh pr checks` polling).
- Restructuring Steps 1, 3–7.

## Version Bumps

- `dev-skills/skills/pr-feedback/SKILL.md` frontmatter: `version: 3.1.0` → `3.2.0`
- `dev-skills/.claude-plugin/plugin.json` version: `3.4.0` → `3.5.0`

Minor (not patch) because the empty-external behavior is a newly explicit specification, not a bug fix to existing prose.

## Validation

This is a documentation/spec change, not code. Validation is qualitative:
- Re-read the rewritten Step 2 and confirm each of the three failure modes is addressed.
- Confirm no contradictions with Steps 1, 3, 6.
- Future cycle of pr-feedback on a real PR will exercise the new instructions.
