---
name: pressure-test
description: This skill should be used when the user asks to "pressure-test this", "pressure test the plan", "discuss with codex", "debate this with codex", "get codex's take", "deliberate with codex", or wants an independent adversarial review of a design, plan, rubric, PR, or decision before concluding. Claude holds a genuine position while the Codex CLI acts as an always-adversarial read-only critic; the loop runs to convergence or a round cap, then a conclusion is saved and presented.
---

# Pressure Test

## Overview

Run a pressure test on a goal: a question, a decision, or a design. You (Claude)
hold the position. The critic is GPT, run read-only through the Codex CLI in
non-interactive mode. The result is a written conclusion, not code changes.

Each round has two roles:
- **The critic attacks.** It finds the weakest point, pushes back, and proposes
  a better alternative.
- **You seek the truth.** Hold your best position and update it honestly:
  concede or rebut each objection.

The conclusion is your position after it survives the critic, plus each
objection that stays unresolved, with your chosen resolution and reasoning.

Drive the loop one round at a time with the bash blocks below. Read the critic's
reply, then write the next prompt with your own reasoning.

## When to use / not use

- **Use** for: design decisions, architecture debates, "should we X or Y", pros/cons
  questions, pressure-testing a plan.
- **Do not use** when the user wants files changed or code written — this skill
  only deliberates. Suggest a normal workflow instead.

## Defaults

- `ROUND_CAP=6` (one round = one position and one critic reply)
- `CALL_TIMEOUT=570` seconds per critic call; `SMOKE_TIMEOUT=60` for preflight.
  Run each critic call with the Bash tool `timeout` set to `600000`; the default
  of 120000 ms stops a long call early.
- Critic model: `gpt-6-astra`. The fallback model is `gpt-6.1-sol`; use it only
  after a flag (see [Flags](#flags)). Use no other model. Pin the model on every
  call so the skill does not depend on the ambient `~/.codex/config.toml`.
- Reasoning effort: `xhigh` on critic rounds and `low` on the preflight smoke
  call.
- Codex sandbox: `read-only` on every call. The kickoff passes `-s read-only`.
  `codex exec resume` rejects `-s` and does not keep the kickoff sandbox; it
  reads `sandbox_mode` from the user config. Each resume therefore passes
  `-c sandbox_mode="read-only"`.
- Working directory: run every codex call from `$REPO`. `codex exec resume`
  rejects `-C` and uses the shell's current directory.
- `SESSION_PATH = docs/pressure-test/sessions/YYYY-MM-DD-topic-slug-session.md`
- `CONCLUSION_PATH = docs/pressure-test/YYYY-MM-DD-topic-slug-conclusion.md`
- Explicit user directions override the corresponding output path.
- Always save and present a conclusion.

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
FALLBACK_MODEL="gpt-6.1-sol"            # only after a flag
CALL_TIMEOUT=570
SMOKE_TIMEOUT=60

# Portable per-call timeout. macOS has no `timeout`; perl ships at /usr/bin/perl.
# Redirect stdin on every call: codex reads stdin until EOF.
codex_to() {                            # usage: codex_to <seconds> <cmd...>
  local s="$1"; shift
  if command -v timeout  >/dev/null 2>&1; then timeout  "$s" "$@"
  elif command -v gtimeout >/dev/null 2>&1; then gtimeout "$s" "$@"
  else perl -e 'my $t=shift; my $p=fork; if(!$p){exec @ARGV;exit 127} eval{local $SIG{ALRM}=sub{die};alarm $t;waitpid($p,0);alarm 0}; if($@){kill "TERM",$p;exit 124} exit($?>>8)' "$s" "$@"
  fi
}

# Succeeds when Codex reports a flag or a model reroute. Only error events and
# stderr are searched, so the critic's own words cannot match.
codex_flagged() {                       # usage: codex_flagged <events.jsonl> <err.log>
  { grep -E '"type" *: *"(error|turn\.failed)"' "$1"; cat "$2"; } 2>/dev/null |
    grep -qiE 'flagged for|policy violation|cyber_policy|bio_policy|misalignment_policy|rerouted|as a fallback'
}
ENV
} > "$DIR/env.sh"
source "$DIR/env.sh"
echo "$PRIMARY_MODEL" > "$DIR/model"    # the current critic model

cat > "$DIR/critic.txt" <<'CRITIC'

You are an independent adversarial critic. Do not approve, praise, or soften the review.

Find the single weakest point in the current position. Surface hidden assumptions, edge cases, failure modes, and missing evidence. Ground objections in the provided evidence and inspect the repo read-only when needed. If a better alternative exists, propose it concretely.

Avoid repeating prior objections unless the handling was insufficient. If no substantive objection remains, reply with: NO SUBSTANTIVE OBJECTION. Then give one sentence explaining why the position holds.
CRITIC
echo "workdir: $DIR"; echo "repo: $REPO"
```

## Step 0 — Preflight (mandatory)

A real smoke call catches broken Codex environments that `command -v` cannot
(failed/missing Codex hooks, auth problems, sandbox refusals).

```bash
source "<workdir>/env.sh"
command -v codex >/dev/null || { echo "codex CLI not found — install it first"; exit 1; }
MODEL="$(cat "$DIR/model")"
cd "$REPO" && codex_to "$SMOKE_TIMEOUT" codex exec --json --skip-git-repo-check \
  -m "$MODEL" -c model_reasoning_effort="low" \
  -s read-only -C "$REPO" -o "$DIR/smoke.txt" \
  "Reply with exactly: ok" < /dev/null > "$DIR/smoke.jsonl" 2> "$DIR/smoke.err"
echo "exit=$? model=$MODEL"
if codex_flagged "$DIR/smoke.jsonl" "$DIR/smoke.err"; then echo "SMOKE FLAGGED"
elif grep -qiw "ok" "$DIR/smoke.txt" 2>/dev/null; then echo "SMOKE OK"
else echo "SMOKE FAILED"; tail -5 "$DIR/smoke.err"; fi
```

- **`SMOKE OK`** — continue to Step 1.
- **`SMOKE FLAGGED`** — follow [Flags](#flags), then re-run the preflight.
- **`SMOKE FAILED`** — stop. Report a one-line diagnosis from `$DIR/smoke.err`,
  for example "Codex hooks are failing — check the `~/.codex` plugin cache",
  "Codex is not signed in", or "`gpt-6-astra` is not available to this
  account". The ending condition is "critic unavailable". Every pressure test
  needs an independent critic, so do not continue with self-critique only.

## Step 1 — Kickoff

1. Form your **honest initial position** on the goal (claim + reasoning). Show it
   to the user.
2. Write the kickoff prompt to `$DIR/prompt.md`: the goal, your position, and the
   critic prompt. The quoted heredoc keeps your text literal, so backticks, `$`,
   and quotes in it are safe. Write every prompt this way: in a double-quoted
   shell variable, a backtick in your text would run as a command.
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

- **`FLAGGED`** — follow [Flags](#flags).
- **`rc` is non-zero (124 = timed out)** — the call failed. Follow the
  **Error** stop condition: retry the kickoff once; if it still fails, write
  the conclusion with what exists and end with "cut short".
- **`rc` is zero but `thread_id` is empty** — the call succeeded yet did
  not emit a `thread.started` event, which means the event shape changed.
  **STOP** and report the last lines of `$DIR/err.log` and
  `$DIR/events.jsonl`; do not fall back to the `--last` form.

## Step 2 — Review loop (repeat until a stop condition)

Each round:
1. Read the critic's objections from `$DIR/msg.txt`.
2. For **each** objection, decide: **concede & revise** or **rebut with evidence**.
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
<per-objection: conceded & revised, or rebutted with evidence>

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

## Flags

Codex flags a request with a policy error, for example "This request has been
flagged for possible cybersecurity risk." (`cyber_policy`), a biological-risk
flag (`bio_policy`), or a misalignment policy block. Codex can also reroute a
flagged account to another model. `codex_flagged` detects these cases.

- **Flag on the critic model** — switch to the fallback model and re-run the
  same block once; `prompt.md` is unchanged:

  ```bash
  source "<workdir>/env.sh"; echo "$FALLBACK_MODEL" > "$DIR/model"
  ```

  For the kickoff, the retry starts a new thread. For a resume, it continues
  the same thread on the fallback model. Codex then warns that the session "was
  recorded with model `gpt-6-astra`"; ignore that warning. Keep the fallback
  model for the rest of the pressure test, and name the switch in the round
  block.
- **Flag on the fallback model** — stop. Use no other model, and do not
  continue without a critic. Write the conclusion with what exists; the ending
  condition is "critic flagged".
- A flag is not an **Error**: it does not use the Error retry.

## Stop conditions

- **Converged** — any of:
  - The critic replies `NO SUBSTANTIVE OBJECTION`, or only restates points you
    have already addressed (no new substantive objection); or
  - **Goal convergence** — the original goal question now has a stable answer and
    the critic's new objections have drifted to out-of-scope refinements (deeper
    implementation details, adjacent APIs, edge cases that don't change the
    answer to the goal). An always-adversarial critic keeps finding *some*
    new edge case, so do not wait for it to run dry on a tangent.
  Judge against the critic's actual words, not your preference — only call goal
  convergence when the goal is genuinely settled (often the critic itself
  signals it, e.g. "the core question is solid"), not merely because you want to
  stop. Record the accepted out-of-scope refinements in the conclusion.
- **Round cap** — 6 rounds reached. Carry any live disagreements into the
  conclusion as explicitly unresolved.
- **Error** — a codex call exits non-zero or times out (exit code 124 = timed
  out) without a flag → retry the same call once → if it still fails, write the
  conclusion with what exists and end with "cut short".
- **Critic flagged** — the fallback model was also flagged (see [Flags](#flags)).

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
Critic: strongest objections, faithfully summarized.
Disposition: conceded and revised, or rebutted with evidence.
Current position: updated position.
```

## Step 3 — Conclusion (always)

Write the conclusion to `CONCLUSION_PATH` and present it in chat.

Include:

- settled position
- key decisions
- strongest objections and dispositions
- unresolved tensions, if any, with your chosen resolution and why
- ending condition: converged, round cap, critic unavailable, critic flagged,
  or cut short
- the critic model or models that took part

Then tell the user the path and show the conclusion.
