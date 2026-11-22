---
name: pressure-test
description: This skill should be used when the user asks to "pressure-test this", "pressure test the plan", "discuss with claude", "debate this with claude", "get claude's take", "deliberate with claude", or wants an independent adversarial review of a design, plan, rubric, PR, failure diagnosis, or decision before concluding, or when another skill needs its decisions reviewed by an independent critic. Codex holds a genuine position while the Claude Code CLI runs an always-adversarial read-only Claude critic; the loop runs to convergence or a round cap, then a conclusion is saved and presented.
---

# Pressure Test

## Overview

Run a pressure test on a goal: a question, a decision, or a design. You (Codex)
hold the position. The critic is Claude, run read-only through Claude Code in
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
runs through the shell function `critic`. It sets the read-only flags,
pins the model, enforces the time limits, and prints the status line.

## When to use / not use

- **Use** for: design decisions, architecture choices, rubrics, plans, PRs,
  and failure diagnoses.
- **Use from another skill** at a decision point. The calling skill then
  continues its own work with the conclusion.
- **Do not use** for a routine edit that has no judgment call. This skill
  changes no project files except its session record and conclusion.

## Defaults

- `ROUND_CAP=6` (one round = one position and one critic reply)
- Time limits: `limit_call.py` stops a critic call when it has run for
  `CALL_TIMEOUT`, 1,800 seconds, and exits 124. The preflight smoke call has
  `SMOKE_TIMEOUT`, 120 seconds.
- Waiting: a critic command returns only when the call ends. Give each critic
  command a shell timeout above `CALL_TIMEOUT`, for example 1860000 ms, or
  poll the command until it exits.
- Critic model: `claude-opus-5-5`, the primary model. The user or a calling
  skill can choose the fallback model, `claude-sonnet-5-5`, instead (see
  [Critic model](#critic-model)). After a flag, the pressure test switches to
  the other allowed model once (see [Flags](#flags)). Use no other model. The
  `critic` function passes `--model` on every call, and `critic_status.py`
  accepts a reply only from the current critic model.
- Reasoning effort: `xhigh` on critic rounds and `low` on the preflight smoke
  call.
- Read-only critic: `--tools "Read,Grep,Glob"` gives the critic no shell,
  edit, or write tool. `--permission-mode dontAsk` denies anything that is not
  pre-approved. `--strict-mcp-config` loads no MCP servers, and
  `--disable-slash-commands` loads no skills. `--add-dir "$DIR"` lets the
  critic read evidence files in the work directory.
- Refusal fallback: setup exports `CLAUDE_CODE_DISABLE_REFUSAL_FALLBACK=1`.
  Claude Code otherwise picks its own model after a refusal; this skill
  switches models itself.
- Working directory: `critic` runs every claude call from `$REPO`, because
  Claude Code stores sessions per project directory.
- Codex sandbox: the `claude` CLI needs network access and write access to
  `~/.claude`. If the Codex sandbox blocks either, run each `claude` command
  with escalated permissions. If escalation is unavailable or denied, stop and
  report that the critic could not run. Write a short conclusion; the ending
  condition is "critic unavailable".
- One goal per critic session. A new goal starts a new pressure test with its
  own setup. Send no critic call after convergence or the round cap.
- `SESSION_PATH = docs/pressure-test/sessions/YYYY-MM-DD-topic-slug-session.md`
- `REPLIES_PATH = docs/pressure-test/sessions/YYYY-MM-DD-topic-slug-replies.md`
- `CONCLUSION_PATH = docs/pressure-test/YYYY-MM-DD-topic-slug-conclusion.md`
- An explicit direction from the user or from a calling skill overrides the
  corresponding output path.
- Always save and present a conclusion.

## Setup (run once per pressure test)

Each command runs in a new shell, so variables do not carry over. Setup
writes them to `env.sh` in a new work directory and prints its path. Start
every later block with `source "<workdir>/env.sh"`, where `<workdir>` is that
printed path. `<skill-dir>` is the folder that holds this `SKILL.md`; write
its absolute path in the block.

```bash
DIR="$(mktemp -d "${TMPDIR:-/tmp}/pressure-test.XXXXXX")"   # transcript + working files
REPO="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
SKILL_DIR="<skill-dir>"
{
  printf 'DIR="%s"\nREPO="%s"\nSKILL_DIR="%s"\n' "$DIR" "$REPO" "$SKILL_DIR"
  cat <<'ENV'
PRIMARY_MODEL="claude-opus-5-5"
FALLBACK_MODEL="claude-sonnet-5-5"      # when chosen, or after a flag
CALL_TIMEOUT=1800
SMOKE_TIMEOUT=120
export CLAUDE_CODE_DISABLE_REFUSAL_FALLBACK=1

# One read-only critic call. The prompt comes from stdin. limit_call.py stops
# the call at the time limit and exits 124 only after the CLI has ended. Prints
# the exit code, the model, and the call time in seconds, then one status from
# critic_status.py, and writes the reply to $DIR/msg.txt. Appends both lines and
# the reply to $DIR/replies.md, which keeps every reply. Only the current
# critic model may answer; any other model is wrong_model.
critic() {                              # usage: critic <seconds> <effort> [session flags] < prompt
  local s="$1" effort="$2" start="$SECONDS" rc line verdict; shift 2
  (cd "$REPO" && python3 "$SKILL_DIR/scripts/limit_call.py" "$s" \
    claude -p --model "$(cat "$DIR/model")" --effort "$effort" "$@" \
    --output-format stream-json --verbose --tools "Read,Grep,Glob" \
    --permission-mode dontAsk --strict-mcp-config --disable-slash-commands \
    --add-dir "$DIR") > "$DIR/events.jsonl" 2> "$DIR/err.log"
  rc=$?
  line="exit=$rc model=$(cat "$DIR/model") seconds=$((SECONDS - start))"
  verdict="$(python3 "$SKILL_DIR/scripts/critic_status.py" "$DIR/events.jsonl" "$DIR/msg.txt" \
    "$(cat "$DIR/model")")"
  printf '%s\n%s\n' "$line" "$verdict"
  printf '## critic call\n\n%s\n%s\n\n%s\n\n' "$line" "$verdict" "$(cat "$DIR/msg.txt")" >> "$DIR/replies.md"
}

new_session() { python3 -c 'import uuid; print(uuid.uuid4())' > "$DIR/session_id"; }
ENV
} > "$DIR/env.sh"
source "$DIR/env.sh"
printf '%s\n' "$PRIMARY_MODEL" > "$DIR/model"   # the current critic model

cat > "$DIR/critic.txt" <<'CRITIC'

You are an independent adversarial critic. Do not approve, praise, or soften the review.

When the packet lists question IDs, first give a one-line assessment of the current answer for every ID: objection, no substantive objection, or not assessed with the reason. Then develop the strongest objection.

Find the single weakest point in the current position. Surface hidden assumptions, edge cases, failure modes, and missing evidence. Ground objections in the provided evidence and inspect the repo read-only when needed. If a better alternative exists, propose it concretely. If the options omit a better option or frame the choice falsely, say so and propose the missing option.

Your only tools are Read, Grep, and Glob, so you cannot run a command or reach the network. When the packet names a file with line ranges, read those ranges first, with the offset and limit of Read, and read the whole file only when the ranges do not settle the point.

Avoid repeating prior objections unless the handling was insufficient. If no substantive objection remains, reply with: NO SUBSTANTIVE OBJECTION. Then give one sentence explaining why the position holds.
CRITIC

cat > "$DIR/narrow.txt" <<'NARROW'

Your previous turn on this packet ran out of time and was stopped before you replied. If the packet lists question IDs, first give the one-line assessment for every ID. Then give only your single strongest objection. Reuse what you already read; make at most five more targeted reads. Put the whole reply in your final message.
NARROW
test -f "$SKILL_DIR/scripts/limit_call.py" || echo "critic scripts not found: $SKILL_DIR/scripts"
echo "workdir: $DIR"; echo "repo: $REPO"
```

The call blocks send `prompt.md` followed by `critic.txt` to the critic, so every
prompt ends with the critic instructions. A [narrow retry](#narrow-retry) also
sends `narrow.txt` last.

## Critic model

The critic starts on the primary model, `claude-opus-5-5`. The user or a
calling skill can choose the fallback model, `claude-sonnet-5-5`, by its ID or
a short name, for example "pressure-test this with sonnet". Then run this
block once, after setup and before the preflight:

```bash
source "<workdir>/env.sh"; echo "$FALLBACK_MODEL" > "$DIR/model"
```

The model of the first critic call is the starting model.

- A request that names the primary model, for example "opus", needs no
  block.
- A request for any other model starts no critic call. Tell the user that the
  critic can use only `claude-opus-5-5` or `claude-sonnet-5-5`, and ask which
  one to use.
  When the calling skill forbids questions, choose one of the two models
  yourself and record the choice in the session record.
- The choice applies only at setup. To change the model later, start a new
  pressure test. Inside one pressure test, only a [flag](#flags) changes the
  model.

## Step 0 — Preflight (mandatory)

A real smoke call catches problems that `command -v` cannot: a missing
sign-in, a model that the account cannot use, or a sandbox that blocks the
network.

```bash
source "<workdir>/env.sh"
command -v claude  >/dev/null || { echo "claude CLI not found"; exit 1; }
command -v python3 >/dev/null || { echo "python3 not found"; exit 1; }
printf 'Reply with exactly: ok\n' | critic "$SMOKE_TIMEOUT" low --no-session-persistence
grep -qiw "ok" "$DIR/msg.txt" && echo "REPLY OK" || { echo "REPLY MISSING"; tail -5 "$DIR/err.log"; }
```

- **`ok` and `REPLY OK`** — continue to Step 1.
- **`flagged`** — follow [Flags](#flags), then re-run the preflight.
- **Any other result** — stop. Report a one-line diagnosis from the status line
  and `$DIR/err.log`, for example "Claude Code is not signed in", "the Codex
  sandbox blocked network access", or "the critic model is not
  available to this account". Write a short conclusion with the diagnosis; the
  ending condition is "critic unavailable". Every pressure test needs an
  independent critic, so do not continue with self-critique only, and do not
  use a Codex subagent as the critic.

## Step 1 — Kickoff

1. Form your **honest initial position** on the goal (claim + reasoning). Print
   it.
2. Write the [pressure-test packet](#pressure-test-packet) to `$DIR/prompt.md`
   with the quoted heredoc below. The quotes keep your text literal, so
   backticks, `$`, and quotes in it are safe. Write every packet this way: in a
   double-quoted shell variable, a backtick in your text would run as a
   command.
3. Send it and act on the [status line](#status-line).

## Calling the critic

Kickoff (round 1):

```bash
source "<workdir>/env.sh"
cat > "$DIR/prompt.md" <<'__PROMPT_END__'
<pressure-test packet>
__PROMPT_END__
new_session
cat "$DIR/prompt.md" "$DIR/critic.txt" | critic "$CALL_TIMEOUT" xhigh --session-id "$(cat "$DIR/session_id")"
cat "$DIR/msg.txt"
```

Later rounds:

```bash
source "<workdir>/env.sh"
cat > "$DIR/prompt.md" <<'__PROMPT_END__'
<pressure-test packet for this round>
__PROMPT_END__
cat "$DIR/prompt.md" "$DIR/critic.txt" | critic "$CALL_TIMEOUT" xhigh --resume "$(cat "$DIR/session_id")"
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
- The critic can read files in the repository and in `$DIR`. It cannot run
  a command, such as `gh` or `curl`, and it has no network. Save issue
  text, PR text, and long command output to a file under `$DIR`, and name the
  file in EVIDENCE. For a long file, name the line ranges to read.
- If the packet lacks enough evidence for reliable judgment, gather the missing
  evidence before calling the critic, or state the gap in ASSUMPTIONS.

The critic keeps earlier rounds in its session. A later packet states the
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
6. Otherwise send the next packet (see [Calling the critic](#calling-the-critic)).

## Status line

`critic` prints the status line in two lines. The first line is
`exit=<code> model=<model> seconds=<n>`, where `seconds` is the time of the
call; the second line is the status from `critic_status.py`. It writes the
reply to `$DIR/msg.txt`, the Claude Code events to `$DIR/events.jsonl`, and
stderr to `$DIR/err.log`. When a call ends, `critic` appends its status line
and reply to `$DIR/replies.md`, because the next call overwrites `msg.txt`.
The kickoff saves a new session ID to `$DIR/session_id`; each resume uses
that ID. Act on the status:

- **`ok`** — read the reply in `$DIR/msg.txt`.
- **`flagged`** — follow [Flags](#flags).
- **`wrong_model:<ids>`** — a model other than the current critic model
  answered. **STOP** and report the model IDs, and do not use the reply.
  Make no retry. Write the conclusion with what exists; the
  ending condition is "cut short".
- **Exit code 124**, with any `error:` status — the call reached a
  time limit. Make one [narrow retry](#narrow-retry).
- **Any other `error:` status**, for example `error:no result event`, or
  another non-zero exit code — the call failed. Follow the **Error** stop
  condition.

Record every call's final status line in the session record.

## Narrow retry

A narrow retry asks the critic for less after a call reached a time limit.
`limit_call.py` exits 124 only after it has stopped the call, so the
retry cannot overlap it. Run the retry once; `prompt.md` is unchanged.

A timed-out kickoff retries in a new session, because the timed-out call may
not have created a session that Claude Code can resume:

```bash
source "<workdir>/env.sh"
new_session
cat "$DIR/prompt.md" "$DIR/critic.txt" "$DIR/narrow.txt" | critic "$CALL_TIMEOUT" xhigh --session-id "$(cat "$DIR/session_id")"
cat "$DIR/msg.txt"
```

A timed-out later round retries in the same session, so the critic keeps what
it already read:

```bash
source "<workdir>/env.sh"
cat "$DIR/prompt.md" "$DIR/critic.txt" "$DIR/narrow.txt" | critic "$CALL_TIMEOUT" xhigh --resume "$(cat "$DIR/session_id")"
cat "$DIR/msg.txt"
```

The retry sends `prompt.md`, `critic.txt`, and then `narrow.txt`, with the
same limit and effort. Each form follows the status rules of the call it makes.
A flag during the retry follows [Flags](#flags). A retry that fails ends the
pressure test (see **Error** in [Stop conditions](#stop-conditions)).

## Flags

Any safeguard action flags the call, even when the critic finished its answer.
`critic_status.py` reports `flagged` when a response ends with
`stop_reason: "refusal"`, when the result reports `safety_stops` above zero,
or when Claude Code reports a `model_refusal_fallback` or
`model_refusal_no_fallback` event.

- **Flag on the starting model** — switch to the other allowed model and re-run
  the same block once; `prompt.md` is unchanged. The other allowed model of
  `claude-opus-5-5` is `claude-sonnet-5-5`, and the reverse:

  ```bash
  source "<workdir>/env.sh"; CURRENT="$(cat "$DIR/model")"
  if [ "$CURRENT" = "$PRIMARY_MODEL" ]; then echo "$FALLBACK_MODEL"; else echo "$PRIMARY_MODEL"; fi > "$DIR/model"
  ```

  For the kickoff, the re-run calls `new_session` again, because Claude Code
  refuses to reuse a session ID. For a resume, it continues the same session
  on the other allowed model. Keep the
  other allowed model for the rest of the pressure test, and name the switch in
  the round block and the session record.
- **Flag after the switch** — stop. Use no other model, and do not continue
  without a critic. Write the conclusion with what exists; the ending
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
  Your own disposition never makes the packet converged: a critic that
  repeats a rebutted objection still objects.
  With question IDs, the packet converges only when the critic's latest reply
  clears every ID: each ID has no substantive objection, or only out-of-scope
  refinements. An ID that the latest reply does not assess counts as not
  assessed and does not converge.
- **Round cap** — 6 rounds reached. Carry any live disagreements into the
  conclusion as explicitly unresolved.
- **Error** — a critic call reports an `error:` status, a `wrong_model:`
  status, or a non-zero exit code, without a flag. After `wrong_model:<ids>`,
  make no retry; the ending condition is "cut short". After exit code 124,
  make one [narrow retry](#narrow-retry); after any other
  error, retry the same block once. If the retry also fails, write the
  conclusion with what exists; the ending condition is "cut short".
- **Critic flagged** — the other allowed model was also flagged (see
  [Flags](#flags)).
- **Critic unavailable** — the preflight failed.

## Progress format (print one block per round, as it happens)

```
─── Round N ───
Critic ▸ <faithful 2-4 bullet objections — no softening>
Codex ▸ <concede/rebut per objection, condensed>
```

Show objections faithfully. End with the ending condition, for example
`Converged after N rounds.` or `Round cap reached — K tension(s) unresolved.`

## Session record

After each round, update `SESSION_PATH` with the complete session so a later
turn can resume from it after the work directory is gone:

```text
Round N (critic model: <model>)
Calls: <every call's final status line, in order, including ok calls and retries>
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
answer and raises no substantive objection, or only out-of-scope
refinements. Mark "revised after last assessment" when you change an answer
after the critic's latest reply.

## Step 3 — Conclusion (always)

Write the conclusion to `CONCLUSION_PATH` and present it in chat. When
`$DIR/replies.md` exists, copy it to `REPLIES_PATH` first. It keeps the
critic's exact replies, so a reader can check the conclusion against them.

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
- a link to `REPLIES_PATH`, when you copied the replies

Then tell the user the path and show the conclusion. When another skill called
this skill, that skill reads the conclusion and continues its own work; do not
wait for the user.
