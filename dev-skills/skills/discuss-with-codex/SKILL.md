---
name: discuss-with-codex
description: This skill should be used when the user asks to "discuss with codex", "debate this with codex", "get codex's take", "deliberate with codex", or wants Claude and the Codex CLI to reach a reasoned conclusion on a question or design through autonomous turn-by-turn adversarial discussion. Claude holds a genuine position while Codex acts as an always-adversarial read-only critic; the loop runs to convergence or a round cap, then a conclusion is saved and presented.
---

# Discuss with Codex

## Overview

Given a goal — a question, decision, or design — run an autonomous, turn-by-turn
deliberation between **you (Claude)** and the **Codex CLI**, converging on a
written conclusion. You harness the turns. Codex is an adversarial critic running
read-only. The deliverable is a reasoned conclusion, not code changes.

**Core asymmetry (the whole point):**
- **Codex always attacks** — every turn it finds the weakest point, pushes back,
  and proposes a better alternative.
- **You are truth-seeking** — hold your genuine best position and update it
  honestly, conceding or rebutting each objection.

The conclusion is your position *after* it survives adversarial pressure, plus
any objections that could not be dissolved (flagged as unresolved with your
chosen resolution and reasoning).

You drive the loop by running the bash commands below turn by turn — reading
Codex's reply, then composing the next prompt with your own reasoning. It is NOT
a single shell script: composing each rebuttal is your job.

## When to use / not use

- **Use** for: design decisions, architecture debates, "should we X or Y", pros/cons
  questions, pressure-testing a plan.
- **Do not use** when the user wants files changed or code written — this skill
  only deliberates. Suggest a normal workflow instead.

## Defaults

- `ROUND_CAP=6` (one round = one Claude↔Codex exchange)
- `CALL_TIMEOUT=600` seconds per codex call; `SMOKE_TIMEOUT=60` for preflight
- Model: `gpt-5.6-sol` with `model_reasoning_effort=xhigh`, pinned per call so the
  skill does not depend on the ambient `~/.codex/config.toml` default
- Codex sandbox: `read-only`, repo as working dir
- Conclusion: always saved AND presented

## Setup (run once at start)

```bash
DIR="$(mktemp -d)"                      # transcript + working files
REPO="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
echo "workdir: $DIR"; echo "repo: $REPO"

# Portable per-call timeout. macOS has no `timeout`; perl ships at /usr/bin/perl.
# Also forces child stdin to /dev/null — codex blocks on stdin otherwise.
codex_to() {                            # usage: codex_to <seconds> <cmd...>
  local s="$1"; shift
  if command -v timeout  >/dev/null 2>&1; then timeout  "$s" "$@" </dev/null
  elif command -v gtimeout >/dev/null 2>&1; then gtimeout "$s" "$@" </dev/null
  else perl -e 'my $t=shift; my $p=fork; if(!$p){open(STDIN,"<","/dev/null");exec @ARGV;exit 127} eval{local $SIG{ALRM}=sub{die};alarm $t;waitpid($p,0);alarm 0}; if($@){kill "TERM",$p;exit 124} exit($?>>8)' "$s" "$@"
  fi
}
```

## Step 0 — Preflight (mandatory)

A real smoke call catches broken Codex environments that `command -v` cannot
(failed/missing Codex hooks, auth problems, sandbox refusals).

```bash
command -v codex >/dev/null || { echo "codex CLI not found — install it first"; exit 1; }
codex_to 60 codex exec --json -m gpt-5.6-sol -c model_reasoning_effort="xhigh" \
  -s read-only -C "$REPO" -o "$DIR/smoke.txt" \
  "Reply with exactly: ok" > "$DIR/smoke.jsonl" 2> "$DIR/smoke.err"
echo "exit=$?"
grep -qi "ok" "$DIR/smoke.txt" 2>/dev/null && echo "SMOKE OK" || { echo "SMOKE FAILED"; tail -5 "$DIR/smoke.err"; }
```

If the smoke call times out, exits non-zero, or `smoke.txt` lacks the reply,
**STOP**. Report a one-line diagnosis from `$DIR/smoke.err` (e.g. "Codex hooks
are failing — check the `~/.codex` plugin cache" or "Codex not authenticated").
Do not fall back to a Claude-only discussion — this skill is pointless without Codex.

## Step 1 — Kickoff

1. Form your **honest initial position** on the goal (claim + reasoning). Show it
   to the user.
2. Build the kickoff prompt: the goal, your position, and the critic block.
3. Send it. **Only this first call carries `-s`/`-C`** — they configure the
   session. Later `codex exec resume` calls inherit sandbox and cwd from the
   session and will error if you pass `-s`/`-C` again.

```bash
PROMPT="GOAL:
<the goal>

CLAUDE'S CURRENT POSITION:
<your position + reasoning>

$(cat <<'CRITIC'
You are acting as an ADVERSARIAL CRITIC in a structured discussion. Your job is NOT to agree.
- Find the single weakest point in the position above and attack it concretely.
- Push back hard; surface hidden assumptions, edge cases, and failure modes.
- If a better alternative exists, propose it specifically.
- Ground objections in this repo when relevant (you have read-only access).
- Keep it tight: a few concrete objections, strongest first.
- If, and only if, you genuinely have no substantive objection left, reply with the single line: NO FURTHER OBJECTIONS, then one sentence on why the position holds.
CRITIC
)"

codex_to 600 codex exec --json -m gpt-5.6-sol -c model_reasoning_effort="xhigh" \
  -s read-only -C "$REPO" \
  -o "$DIR/msg.txt" "$PROMPT" \
  > "$DIR/events.jsonl" 2> "$DIR/err.log"
status=$?
echo "exit=$status"

THREAD_ID=$(sed -nE '/"type"[[:space:]]*:[[:space:]]*"thread\.started"/s/.*"thread_id"[[:space:]]*:[[:space:]]*"([^"]+)".*/\1/p' "$DIR/events.jsonl" | head -n1)
echo "thread_id=$THREAD_ID"
cat "$DIR/msg.txt"
```

Branch on the two failure classes:

- **`status` is non-zero (124 = timed out)** — the call failed transiently.
  Follow the **Error** stop condition (retry the kickoff once; if it still
  fails, conclude with what exists and state the discussion was cut short).
- **`status` is zero but `THREAD_ID` is empty** — the call succeeded yet did
  not emit a `thread.started` event, which means the event shape changed.
  **STOP** and report the last lines of `$DIR/err.log` and
  `$DIR/events.jsonl`; do not fall back to the `--last` form.

## Step 2 — Discussion loop (repeat until a stop condition)

Each round:
1. Read Codex's objections from `$DIR/msg.txt`.
2. For **each** objection, decide: **concede & revise** or **rebut with reasoning**.
   Update your position accordingly.
3. Print the round block (see Progress format).
4. Check stop conditions (below). If stopping, go to Step 3.
5. Otherwise send your revised position back:

```bash
PROMPT="I have revised my position in response to your objections.

HOW I HANDLED YOUR LAST OBJECTIONS:
<per-objection: conceded & revised, or rebutted with reasoning>

CLAUDE'S REVISED POSITION:
<updated position>

$(cat <<'CRITIC'
You are acting as an ADVERSARIAL CRITIC in a structured discussion. Your job is NOT to agree.
- Find the single weakest point in the position above and attack it concretely.
- Push back hard; surface hidden assumptions, edge cases, and failure modes.
- If a better alternative exists, propose it specifically.
- Ground objections in this repo when relevant (you have read-only access).
- Keep it tight: a few concrete objections, strongest first.
- If, and only if, you genuinely have no substantive objection left, reply with the single line: NO FURTHER OBJECTIONS, then one sentence on why the position holds.
CRITIC
)"

# NOTE: do NOT pass -s/-C to `codex exec resume`. Sandbox and cwd are bound to
# the session at kickoff and `resume` rejects those flags. (-m/-c ARE accepted,
# so the model pin below is fine.) Always use the explicit THREAD_ID form
# captured in Step 1.
codex_to 600 codex exec resume "$THREAD_ID" --json \
  -m gpt-5.6-sol -c model_reasoning_effort="xhigh" \
  -o "$DIR/msg.txt" "$PROMPT" \
  > "$DIR/events.jsonl" 2> "$DIR/err.log"
echo "exit=$?"
cat "$DIR/msg.txt"
```

## Stop conditions

- **Converged** — any of:
  - Codex replies `NO FURTHER OBJECTIONS`, or only restates points you have
    already addressed (no new substantive objection); or
  - **Goal convergence** — the original goal question now has a stable answer and
    Codex's new objections have drifted to out-of-scope refinements (deeper
    implementation details, adjacent APIs, edge cases that don't change the
    answer to the goal). An always-adversarial critic will keep finding *some*
    new edge case forever, so do not wait for it to run dry on a tangent.
  Judge against Codex's actual words, not your preference — only call goal
  convergence when the goal is genuinely settled (often Codex itself signals it,
  e.g. "the core question is solid"), not merely because you want to stop. Record
  the accepted out-of-scope refinements in the conclusion.
- **Round cap** — 6 rounds reached. Carry any live disagreements into the
  conclusion as explicitly unresolved.
- **Error** — a codex call exits non-zero or times out (exit code 124 = timed
  out) → retry the same call once → if it still fails, conclude with what exists
  and state the discussion was cut short.

## Progress format (print one block per round, as it happens)

```
─── Round N ───
Codex ▸ <faithful 2-4 bullet objections — no softening>
Claude ▸ <concede/rebut per objection, condensed>
```

Show objections faithfully. Raw exchanges persist in `$DIR/msg.txt`. End with:
`Converged after N rounds.` or `Round cap reached — K tension(s) unresolved.`

## Step 3 — Conclusion (always)

Write the conclusion to a dated file AND present it in chat.

```bash
OUT="docs/superpowers/specs/$(date +%F)-<topic-slug>-conclusion.md"
```

Conclusion contents:
- The settled position.
- Key decisions made.
- The strongest objections Codex raised and how each resolved.
- Any unresolved tensions, with your chosen resolution and why.
- How it ended (converged after N rounds / round cap / cut short).

Then tell the user the path and show the conclusion.
