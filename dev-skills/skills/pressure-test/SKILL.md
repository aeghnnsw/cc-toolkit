---
name: pressure-test
description: This skill should be used when the user asks to "pressure-test this", "pressure test the plan", "discuss with codex", "debate this with codex", "get codex's take", "deliberate with codex", or wants an independent adversarial review of a design, plan, rubric, PR, or decision before concluding. Claude holds a genuine position while the Codex CLI acts as an always-adversarial read-only critic; the loop runs to convergence or a round cap, then a conclusion is saved and presented.
---

# Pressure Test

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
- `CALL_TIMEOUT=570` seconds per codex call; `SMOKE_TIMEOUT=60` for preflight.
  Run each codex call with the Bash tool `timeout` set to `600000`; the default
  of 120000 ms stops a deliberation call early.
- Critic model: `gpt-6-astra`. Use `gpt-6.1-sol` only after Codex flags a call
  (see [Flagged calls](#flagged-calls)). Use no other model. Pin the model on
  every call so the skill does not depend on the ambient `~/.codex/config.toml`.
- Reasoning effort: `xhigh` on the deliberation calls (kickoff/resume) and `low`
  on the preflight smoke (a trivial connectivity check)
- Codex sandbox: `read-only` on every call. The kickoff passes `-s read-only`.
  `codex exec resume` rejects `-s` and does not keep the kickoff sandbox; it
  reads `sandbox_mode` from the user config. Each resume therefore passes
  `-c sandbox_mode="read-only"`.
- Working directory: run every codex call from `$REPO`. `codex exec resume`
  rejects `-C` and uses the shell's current directory.
- `SESSION_PATH = docs/pressure-test/sessions/YYYY-MM-DD-topic-slug-session.md`
- `CONCLUSION_PATH = docs/pressure-test/YYYY-MM-DD-topic-slug-conclusion.md`
- Explicit user directions override the corresponding output path.
- Conclusion: always saved AND presented

## Setup (run once at start)

Each Bash tool call starts a new shell, so variables and functions do not carry
over. Setup writes them to `env.sh` in a new work directory and prints its path.
Start every later block with `source "<workdir>/env.sh"`, where `<workdir>` is
that printed path.

```bash
DIR="$(mktemp -d)"                      # transcript + working files
REPO="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
{
  printf 'DIR="%s"\nREPO="%s"\n' "$DIR" "$REPO"
  cat <<'ENV'
PRIMARY_MODEL="gpt-6-astra"
FALLBACK_MODEL="gpt-6.1-sol"            # only after a flagged call
CALL_TIMEOUT=570

# Portable per-call timeout. macOS has no `timeout`; perl ships at /usr/bin/perl.
# Redirect stdin on every call: codex reads stdin until EOF.
codex_to() {                            # usage: codex_to <seconds> <cmd...>
  local s="$1"; shift
  if command -v timeout  >/dev/null 2>&1; then timeout  "$s" "$@"
  elif command -v gtimeout >/dev/null 2>&1; then gtimeout "$s" "$@"
  else perl -e 'my $t=shift; my $p=fork; if(!$p){exec @ARGV;exit 127} eval{local $SIG{ALRM}=sub{die};alarm $t;waitpid($p,0);alarm 0}; if($@){kill "TERM",$p;exit 124} exit($?>>8)' "$s" "$@"
  fi
}

# Succeeds when Codex reports a safety flag or a model reroute. Only error
# events and stderr are searched, so the critic's own words cannot match.
codex_flagged() {                       # usage: codex_flagged <events.jsonl> <err.log>
  { grep -E '"type" *: *"(error|turn\.failed)"' "$1"; cat "$2"; } 2>/dev/null |
    grep -qiE 'flagged for|policy violation|cyber_policy|bio_policy|misalignment_policy|rerouted|as a fallback'
}
ENV
} > "$DIR/env.sh"
echo "gpt-6-astra" > "$DIR/model"       # the current critic model

cat > "$DIR/critic.txt" <<'CRITIC'

You are acting as an ADVERSARIAL CRITIC in a structured discussion. Your job is NOT to agree.
- Find the single weakest point in the position above and attack it concretely.
- Push back hard; surface hidden assumptions, edge cases, and failure modes.
- If a better alternative exists, propose it specifically.
- Ground objections in this repo when relevant (you have read-only access).
- Keep it tight: a few concrete objections, strongest first.
- If, and only if, you genuinely have no substantive objection left, reply with the single line: NO FURTHER OBJECTIONS, then one sentence on why the position holds.
CRITIC
echo "workdir: $DIR"; echo "repo: $REPO"
```

## Step 0 — Preflight (mandatory)

A real smoke call catches broken Codex environments that `command -v` cannot
(failed/missing Codex hooks, auth problems, sandbox refusals).

```bash
source "<workdir>/env.sh"
command -v codex >/dev/null || { echo "codex CLI not found — install it first"; exit 1; }
cd "$REPO" && codex_to 60 codex exec --json --skip-git-repo-check \
  -m "$PRIMARY_MODEL" -c model_reasoning_effort="low" \
  -s read-only -C "$REPO" -o "$DIR/smoke.txt" \
  "Reply with exactly: ok" < /dev/null > "$DIR/smoke.jsonl" 2> "$DIR/smoke.err"
echo "exit=$?"
codex_flagged "$DIR/smoke.jsonl" "$DIR/smoke.err" && echo "SMOKE FLAGGED"
grep -qiw "ok" "$DIR/smoke.txt" 2>/dev/null && echo "SMOKE OK" || { echo "SMOKE FAILED"; tail -5 "$DIR/smoke.err"; }
```

If the smoke call times out, exits non-zero, or `smoke.txt` lacks the reply,
**STOP**. Report a one-line diagnosis from `$DIR/smoke.err` (e.g. "Codex hooks
are failing — check the `~/.codex` plugin cache", "Codex not authenticated", or
"`gpt-6-astra` is not available to this account"). Do not fall back to a
Claude-only discussion — this skill is pointless without Codex.

## Step 1 — Kickoff

1. Form your **honest initial position** on the goal (claim + reasoning). Show it
   to the user.
2. Write the kickoff prompt to `$DIR/prompt.md`: the goal, your position, and the
   critic block. The quoted heredoc keeps your text literal, so backticks, `$`,
   and quotes in it are safe. Do not build the prompt in a double-quoted shell
   variable: a backtick in your text would run as a command.
3. Send it. **Only this first call carries `-s`/`-C`** — later
   `codex exec resume` calls reject them and use the overrides in Step 2.

```bash
source "<workdir>/env.sh"
cat > "$DIR/prompt.md" <<'__PROMPT_END__'
GOAL:
<the goal>

CLAUDE'S CURRENT POSITION:
<your position + reasoning>
__PROMPT_END__
cat "$DIR/critic.txt" >> "$DIR/prompt.md"

MODEL="$(cat "$DIR/model")"
rm -f "$DIR/msg.txt"                    # never read a stale reply
cd "$REPO" && codex_to "$CALL_TIMEOUT" codex exec --json --skip-git-repo-check \
  -m "$MODEL" -c model_reasoning_effort="xhigh" \
  -s read-only -C "$REPO" -o "$DIR/msg.txt" \
  - < "$DIR/prompt.md" > "$DIR/events.jsonl" 2> "$DIR/err.log"
rc=$?
echo "exit=$rc model=$MODEL"
codex_flagged "$DIR/events.jsonl" "$DIR/err.log" && echo "FLAGGED"

sed -nE '/"type"[[:space:]]*:[[:space:]]*"thread\.started"/s/.*"thread_id"[[:space:]]*:[[:space:]]*"([^"]+)".*/\1/p' \
  "$DIR/events.jsonl" | head -n1 > "$DIR/thread_id"
echo "thread_id=$(cat "$DIR/thread_id")"
cat "$DIR/msg.txt"
```

Branch on the result, in this order:

- **`FLAGGED`** — follow [Flagged calls](#flagged-calls).
- **`rc` is non-zero (124 = timed out)** — the call failed transiently.
  Follow the **Error** stop condition (retry the kickoff once; if it still
  fails, conclude with what exists and state the discussion was cut short).
- **`rc` is zero but `thread_id` is empty** — the call succeeded yet did
  not emit a `thread.started` event, which means the event shape changed.
  **STOP** and report the last lines of `$DIR/err.log` and
  `$DIR/events.jsonl`; do not fall back to the `--last` form.

## Step 2 — Discussion loop (repeat until a stop condition)

Each round:
1. Read Codex's objections from `$DIR/msg.txt`.
2. For **each** objection, decide: **concede & revise** or **rebut with reasoning**.
   Update your position accordingly.
3. Print the round block (see Progress format) and append the round to
   `SESSION_PATH` (see Session record).
4. Check stop conditions (below). If stopping, go to Step 3.
5. Otherwise send your revised position back:

```bash
source "<workdir>/env.sh"
cat > "$DIR/prompt.md" <<'__PROMPT_END__'
I have revised my position in response to your objections.

HOW I HANDLED YOUR LAST OBJECTIONS:
<per-objection: conceded & revised, or rebutted with reasoning>

CLAUDE'S REVISED POSITION:
<updated position>
__PROMPT_END__
cat "$DIR/critic.txt" >> "$DIR/prompt.md"

MODEL="$(cat "$DIR/model")"; THREAD_ID="$(cat "$DIR/thread_id")"
rm -f "$DIR/msg.txt"
# Resume rejects -s/-C and does not keep the kickoff sandbox: pass the sandbox
# with -c and run from $REPO. Always use the THREAD_ID captured in Step 1.
cd "$REPO" && codex_to "$CALL_TIMEOUT" codex exec resume "$THREAD_ID" --json \
  --skip-git-repo-check -m "$MODEL" -c model_reasoning_effort="xhigh" \
  -c sandbox_mode="read-only" -o "$DIR/msg.txt" \
  - < "$DIR/prompt.md" > "$DIR/events.jsonl" 2> "$DIR/err.log"
echo "exit=$? model=$MODEL"
codex_flagged "$DIR/events.jsonl" "$DIR/err.log" && echo "FLAGGED"
cat "$DIR/msg.txt"
```

## Flagged calls

Codex flags a request with a policy error, for example "This request has been
flagged for possible cybersecurity risk." (`cyber_policy`), a biological-risk
flag (`bio_policy`), or a misalignment policy block. Codex can also reroute a
flagged account to another model. `codex_flagged` detects these cases.

- **Flagged on `gpt-6-astra`** — run `echo "gpt-6.1-sol" > "$DIR/model"` and
  re-run the same block once; `prompt.md` is unchanged. For the kickoff, the
  retry starts a new thread. For a resume, it continues the same thread on
  `gpt-6.1-sol`. Codex then warns that the session "was recorded with model
  `gpt-6-astra`"; ignore that warning. Keep `gpt-6.1-sol` for the rest of the
  discussion and tell the user about the switch in the round block.
- **Flagged on `gpt-6.1-sol`** — stop. Do not try another model and do not
  continue without a critic. Write the conclusion with what exists; the ending
  condition is "critic flagged".
- A flagged call is not an **Error**: it does not use the Error retry.

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
  out) without a flag → retry the same call once → if it still fails, conclude
  with what exists and state the discussion was cut short.
- **Critic flagged** — both models flagged the request (see Flagged calls).

## Progress format (print one block per round, as it happens)

```
─── Round N ───
Codex ▸ <faithful 2-4 bullet objections — no softening>
Claude ▸ <concede/rebut per objection, condensed>
```

Show objections faithfully. End with: `Converged after N rounds.`,
`Round cap reached — K tension(s) unresolved.`, or the reason the discussion
was cut short.

## Session record

After each round, append the round to `SESSION_PATH` so a later turn can resume
the discussion after the work directory is gone:

```text
Round N (model: <critic model>)
Codex: strongest objections, faithfully summarized.
Disposition: conceded and revised, or rebutted with reasoning.
Current position: updated position.
```

## Step 3 — Conclusion (always)

Write the conclusion to `CONCLUSION_PATH` AND present it in chat.

Conclusion contents:
- The settled position.
- Key decisions made.
- The strongest objections Codex raised and how each resolved.
- Any unresolved tensions, with your chosen resolution and why.
- How it ended: converged after N rounds, round cap, cut short, or critic
  flagged. Name the critic model or models that took part.

Then tell the user the path and show the conclusion.
