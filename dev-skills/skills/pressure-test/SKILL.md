---
name: pressure-test
description: This skill should be used when the user asks to "pressure-test this", "pressure test the plan", "discuss with codex", "debate this with codex", "get codex's take", "deliberate with codex", or wants an independent adversarial review of a design, plan, rubric, PR, or decision before concluding, or when another skill needs its decisions reviewed by an independent critic. Claude holds a genuine position while the Codex CLI acts as an always-adversarial read-only critic; the loop runs to convergence or a round cap, then a conclusion is saved and presented.
---

# Pressure Test

## Overview

Run a pressure test on a goal: a question, a decision, or a design. You (Claude)
hold the position. The critic is GPT, run read-only through the Codex CLI in
non-interactive mode. The result is a written conclusion, not code changes.

Each round has two roles:
- **The critic attacks.** It finds the weakest point, pushes back, and proposes
  a better alternative.
- **You seek the truth.** Hold your best position and update it honestly.
  Concede an objection when it holds against the evidence; otherwise rebut it
  with evidence. Do not concede only to end a round.

The conclusion is your position after it survives the critic, plus each
objection that stays unresolved, with your chosen resolution and reasoning.

Drive the loop one round at a time with the bash blocks below. Read the critic's
reply, then write the next packet with your own reasoning. Every critic call
runs through the runner script `codex_critic.py`. It sets the read-only flags,
pins the model, enforces the timeout, and prints one status line.

## When to use / not use

- **Use** for: design decisions, architecture debates, "should we X or Y",
  pros/cons questions, plans, rubrics, PRs, and failure diagnoses.
- **Use from another skill** at a decision point. The calling skill then
  continues its own work with the conclusion.
- **Do not use** for a routine edit that has no judgment call. This skill
  changes no project files except its session record and conclusion.

## Defaults

- `ROUND_CAP=6` (one round = one position and one critic reply)
- Timeouts: the runner stops a critic call after 570 seconds and the preflight
  smoke call after 60 seconds, and reports exit code 124. Run each runner call
  with the Bash tool `timeout` set to `600000`; the default of 120000 ms stops
  a long call early.
- Critic model: `gpt-6-astra`. The fallback model is `gpt-6.1-sol`; use it only
  after a flag (see [Flags](#flags)). Use no other model. The runner pins the
  model on every call, so the skill does not depend on the ambient
  `~/.codex/config.toml`.
- Reasoning effort: `xhigh` on critic rounds and `low` on the preflight smoke
  call.
- Codex sandbox: `read-only` on every call. The kickoff passes `-s read-only`.
  `codex exec resume` rejects `-s` and does not keep the kickoff sandbox; it
  reads `sandbox_mode` from the user config. The runner therefore passes
  `-c sandbox_mode="read-only"` on each resume.
- Working directory: the runner runs every codex call from `$REPO`.
  `codex exec resume` rejects `-C` and uses the current directory.
- One goal per critic thread. A new goal starts a new pressure test with its
  own setup. Send no critic call after convergence or the round cap.
- `SESSION_PATH = docs/pressure-test/sessions/YYYY-MM-DD-topic-slug-session.md`
- `CONCLUSION_PATH = docs/pressure-test/YYYY-MM-DD-topic-slug-conclusion.md`
- An explicit direction from the user or from a calling skill overrides the
  corresponding output path.
- Always save and present a conclusion.

## Setup (run once per pressure test)

Each Bash tool call starts a new shell, so variables do not carry over. Setup
writes them to `env.sh` in a new work directory and prints its path. Start
every later block with `source "<workdir>/env.sh"`, where `<workdir>` is that
printed path.

```bash
DIR="$(mktemp -d)"                      # transcript + working files
REPO="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
RUNNER="${CLAUDE_PLUGIN_ROOT}/skills/pressure-test/scripts/codex_critic.py"
{
  printf 'DIR="%s"\nREPO="%s"\nRUNNER="%s"\n' "$DIR" "$REPO" "$RUNNER"
  cat <<'ENV'
PRIMARY_MODEL="gpt-6-astra"
FALLBACK_MODEL="gpt-6.1-sol"            # only after a flag
ENV
} > "$DIR/env.sh"
source "$DIR/env.sh"
printf '%s\n' "$REPO" > "$DIR/repo"
printf '%s\n' "$PRIMARY_MODEL" > "$DIR/model"   # the current critic model

cat > "$DIR/critic.txt" <<'CRITIC'

You are an independent adversarial critic. Do not approve, praise, or soften the review.

When the packet lists question IDs, first give a one-line assessment of the current answer for every ID: objection, no substantive objection, or not assessed with the reason. Then develop the strongest objection.

Find the single weakest point in the current position. Surface hidden assumptions, edge cases, failure modes, and missing evidence. Ground objections in the provided evidence and inspect the repo read-only when needed. If a better alternative exists, propose it concretely. If the options omit a better option or frame the choice falsely, say so and propose the missing option.

Avoid repeating prior objections unless the handling was insufficient. If no substantive objection remains, reply with: NO SUBSTANTIVE OBJECTION. Then give one sentence explaining why the position holds.
CRITIC
test -f "$RUNNER" || echo "runner not found: $RUNNER"
echo "workdir: $DIR"; echo "repo: $REPO"
```

The runner sends `prompt.md` followed by `critic.txt` to the critic, so every
prompt ends with the critic instructions.

## Step 0 — Preflight (mandatory)

A real smoke call catches broken Codex environments that `command -v` cannot
(failed/missing Codex hooks, auth problems, sandbox refusals).

```bash
source "<workdir>/env.sh"
python3 "$RUNNER" smoke "$DIR"
```

- **`status=ok`** — continue to Step 1.
- **`status=flagged`** — follow [Flags](#flags), then re-run the preflight.
- **Any other status** — stop. Report a one-line diagnosis from the status line
  and `$DIR/err.log`, for example "Codex is not signed in", "Codex hooks are
  failing — check the `~/.codex` plugin cache", or "`gpt-6-astra` is not
  available to this account". Write a short conclusion with the diagnosis; the
  ending condition is "critic unavailable". Every pressure test needs an
  independent critic, so do not continue with self-critique only.

## Step 1 — Kickoff

1. Form your **honest initial position** on the goal (claim + reasoning). Print
   it.
2. Write the [pressure-test packet](#pressure-test-packet) to `$DIR/prompt.md`
   with the quoted heredoc below. The quotes keep your text literal, so
   backticks, `$`, and quotes in it are safe. Write every packet this way: in a
   double-quoted shell variable, a backtick in your text would run as a
   command.
3. Send it and act on the [status line](#status-line).

```bash
source "<workdir>/env.sh"
cat > "$DIR/prompt.md" <<'__PROMPT_END__'
<pressure-test packet>
__PROMPT_END__
python3 "$RUNNER" kickoff "$DIR"
cat "$DIR/msg.txt"
```

## Pressure-test packet

The kickoff packet has these fields:

```text
GOAL:
<the question, decision, design, plan, rubric, PR, or failure diagnosis>

CURRENT POSITION:
<your claim and reasoning; for several questions, one entry per ID (Q1, Q2, ...) with its current answer>

OPTIONS:
<for a choice: each option with its evidence, and the option you recommend; per ID for several questions>

DECISION BOUNDARY:
<what is in scope, what is out of scope, and what objection would change the decision>

EVIDENCE:
<relevant files, diffs, and command output; name files the critic can read>

ASSUMPTIONS:
<known constraints and assumptions to attack>

PRIOR ROUNDS:
<objections already raised and how they were handled, or "none">
```

- Omit OPTIONS when the goal is not a choice.
- Give each question an ID when the packet holds several questions.
- The critic can read files and run read-only commands in the repository. Put
  long command output in a file under `$DIR` and name it in EVIDENCE.
- If the packet lacks enough evidence for reliable judgment, gather the missing
  evidence before calling the critic, or state the gap in ASSUMPTIONS.

The critic keeps earlier rounds in its thread. A later packet states the
changes since the last round:

```text
HOW I HANDLED YOUR LAST OBJECTIONS:
<per objection: conceded and revised, or rebutted with evidence>

CURRENT POSITION:
<the revised position; restate each changed answer in full and list the IDs that changed>

NEW EVIDENCE:
<new files or command output, or "none">
```

## Step 2 — Review loop (repeat until a stop condition)

Each round:
1. Read the critic's reply from `$DIR/msg.txt`.
2. For **each** objection, decide: **concede & revise** when it holds against the
   evidence, or **rebut with evidence**. Update your position accordingly.
3. With question IDs, update the [coverage table](#session-record).
4. Print the round block (see Progress format) and append the round to
   `SESSION_PATH` (see Session record).
5. Check stop conditions (below). If stopping, go to Step 3.
6. Otherwise send the next packet:

```bash
source "<workdir>/env.sh"
cat > "$DIR/prompt.md" <<'__PROMPT_END__'
<pressure-test packet for this round>
__PROMPT_END__
python3 "$RUNNER" resume "$DIR"
cat "$DIR/msg.txt"
```

## Status line

The runner prints `exit=<code> model=<model> status=<status>` and writes the
reply to `$DIR/msg.txt`, the Codex events to `$DIR/events.jsonl`, and stderr
to `$DIR/err.log`. On the kickoff, it saves the thread ID to
`$DIR/thread_id`; each resume uses that ID. Act on the status:

- **`ok`** — read the reply in `$DIR/msg.txt`.
- **`flagged`** — follow [Flags](#flags).
- **`error:no thread id`** (kickoff only) — the call succeeded but did not emit
  a `thread.started` event, which means the event shape changed. **STOP** and
  report the last lines of `$DIR/err.log` and `$DIR/events.jsonl`. The runner
  never falls back to the `--last` form.
- **Any other `error:` status**, for example `error:timeout` (exit code 124) or
  `error:exit 1` — the call failed. Follow the **Error** stop condition.

Record every status line that is not `ok`, and each retry, in the session
record.

## Flags

Codex flags a request with a policy error, for example "This request has been
flagged for possible cybersecurity risk." (`cyber_policy`), a biological-risk
flag (`bio_policy`), or a misalignment policy error (`misalignment_policy`).
Codex can also reroute a flagged account to another model. The runner searches
only error events and stderr for these notices, so the critic's own words
cannot match, and reports `status=flagged`.

- **Flag on the critic model** — switch to the fallback model and re-run the
  same block once; `prompt.md` is unchanged:

  ```bash
  source "<workdir>/env.sh"; echo "$FALLBACK_MODEL" > "$DIR/model"
  ```

  For the kickoff, the retry starts a new thread. For a resume, it continues
  the same thread on the fallback model. Codex then warns that the session "was
  recorded with model `gpt-6-astra`"; ignore that warning. Keep the fallback
  model for the rest of the pressure test, and name the switch in the round
  block and the session record.
- **Flag on the fallback model** — stop. Use no other model, and do not
  continue without a critic. Write the conclusion with what exists; the ending
  condition is "critic flagged".
- A flag is not an **Error**: it does not use the Error retry.

## Stop conditions

- **Converged** — any of:
  - The critic replies `NO SUBSTANTIVE OBJECTION`; or
  - **Goal convergence** — the original goal question now has a stable answer and
    the critic's new objections have drifted to out-of-scope refinements (deeper
    implementation details, adjacent APIs, edge cases that don't change the
    answer to the goal). An always-adversarial critic keeps finding *some*
    new edge case, so do not wait for it to run dry on a tangent.
  Judge against the critic's actual words, not your preference — only call goal
  convergence when the goal is genuinely answered (often the critic itself
  signals it, e.g. "the core question is solid"), not merely because you want to
  stop. Record the accepted out-of-scope refinements in the conclusion.
  With question IDs, the packet converges only when the critic's latest reply
  clears every ID: each ID has no substantive objection, or only out-of-scope
  refinements. An ID that the latest reply does not assess is not assessed.
  Your own disposition never makes the packet or an ID converged: a critic
  that repeats a rebutted objection still objects.
- **Round cap** — 6 rounds reached. Carry any live disagreements into the
  conclusion as explicitly unresolved.
- **Error** — a runner call reports an `error:` status without a flag → retry
  the same block once → if it still fails, write the conclusion with what
  exists and end with "cut short".
- **Critic flagged** — the fallback model was also flagged (see [Flags](#flags)).
- **Critic unavailable** — the preflight failed.

## Progress format (print one block per round, as it happens)

```
─── Round N ───
Critic ▸ <faithful 2-4 bullet objections — no softening>
Claude ▸ <concede/rebut per objection, condensed>
```

Show objections faithfully. End with the ending condition, for example
`Converged after N rounds.` or `Round cap reached — K tension(s) unresolved.`

## Session record

After each round, update `SESSION_PATH` with the complete session so a later
turn can resume from it after the work directory is gone:

```text
Round N (critic model: <model>)
Calls: <each status line that is not ok, and each retry; or "ok">
Critic: strongest objections, faithfully summarized.
Disposition: conceded and revised, or rebutted with evidence.
Current position: updated position.
```

With question IDs, keep a coverage table:

```text
| ID | Latest critic assessment | Round | Revised after last assessment |
```

An ID is **reviewed** when the critic has assessed some version of its answer.
It is **converged** when the critic's latest assessment covers its current
answer and raises no substantive objection, or only out-of-scope refinements. Mark "revised after last
assessment" when you change an answer after the critic's latest reply.

## Step 3 — Conclusion (always)

Write the conclusion to `CONCLUSION_PATH` and present it in chat.

Include:

- final position
- key decisions
- strongest objections and dispositions
- the coverage table, when the packet had question IDs
- unresolved tensions, if any, with your chosen resolution and why
- failed and retried critic calls, with their status lines
- ending condition: converged, round cap, critic unavailable, critic flagged,
  or cut short
- the critic model or models that took part

Then tell the user the path and show the conclusion. A calling skill reads the
conclusion and continues its own work; do not wait for the user.
