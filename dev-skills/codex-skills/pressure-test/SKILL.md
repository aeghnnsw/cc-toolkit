---
name: pressure-test
description: Use when a design, plan, rubric, PR, failure diagnosis, or task orchestration decision needs independent adversarial review before conclusion, including when another skill needs its decisions reviewed by an independent critic. A read-only Claude critic, run through the Claude Code CLI, supplies the pressure.
---

# Pressure Test

Run an independent adversarial review before making a decision. The main Codex agent owns the position and conclusion. A read-only Claude critic, run through the Claude Code CLI in non-interactive mode (`claude -p`), supplies pressure. A critic from another model family shares fewer blind spots with the main agent.

## Core Principle

Pressure testing only matters when the critic has enough context and independence to find real weaknesses. Do not replace the critic with inline self-critique or with a Codex subagent.

## When To Use

Use for design decisions, architecture choices, task-loop aims, rubrics, plans, PRs, failure diagnoses, re-attack plans, and aim-fidelity checks.

Another skill can use it at a decision point and then continue its own work with the conclusion.

Do not use for a routine edit that has no judgment call. This skill changes no project files except its session record and conclusion.

## Defaults

- `ROUND_CAP = 6`
- `CALL_TIMEOUT = 900` seconds per critic call; `SMOKE_TIMEOUT = 120` for preflight.
- Critic model: `claude-opus-5-5`. The fallback model is `claude-sonnet-5-5`; use it only after a flag (see [Flags](#flags)). Use no other model. Pass `--model` on every call, and accept a reply only from the current critic model.
- Effort: `xhigh` on critic rounds and `low` on the smoke call.
- `CLAUDE_CODE_DISABLE_REFUSAL_FALLBACK=1`: Claude Code otherwise picks its own model after a refusal. This skill switches models itself.
- Read-only critic: `--tools "Read,Grep,Glob"` gives the critic no shell, edit, or write tool. `--permission-mode dontAsk` denies anything that is not pre-approved. `--strict-mcp-config` loads no MCP servers, and `--disable-slash-commands` loads no skills. `--add-dir "$DIR"` lets the critic read evidence files in the work directory.
- Critic session: the kickoff starts a session with a new `--session-id`; later rounds pass `--resume` with that ID. Run every call from `$REPO`, because Claude Code stores sessions per project directory.
- `SESSION_PATH = docs/pressure-test/sessions/YYYY-MM-DD-topic-slug-session.md`
- `CONCLUSION_PATH = docs/pressure-test/YYYY-MM-DD-topic-slug-conclusion.md`
- An explicit direction from the user or from a calling skill overrides the corresponding output path.
- One goal per critic session. A new goal starts a new pressure test with its own setup. Send no critic call after convergence or the round cap.
- Stop early on convergence.
- Always save and present a conclusion.

## Shell Access

- The `claude` CLI needs network access and write access to `~/.claude`. If the Codex sandbox blocks either, run each `claude` command with escalated permissions. If escalation is unavailable or denied, stop and report that the critic could not run.
- Each shell command starts a new shell. Setup writes the shared settings to `env.sh` and prints its directory. Start every later command with `source "<workdir>/env.sh"`, where `<workdir>` is that printed directory.
- Give each critic command a shell timeout above `CALL_TIMEOUT`, for example 960000 ms, or poll the command until it exits.
- Write each prompt with the quoted heredoc shown below. The quotes keep backticks, `$`, and quotes in the packet literal.

## Setup

Replace `<skill-dir>` with this skill's directory, the folder that holds this `SKILL.md`.

```bash
DIR="$(mktemp -d)"
REPO="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
{
  printf 'DIR="%s"\nREPO="%s"\nSKILL_DIR="%s"\n' "$DIR" "$REPO" "<skill-dir>"
  cat <<'ENV'
PRIMARY_MODEL="claude-opus-5-5"
FALLBACK_MODEL="claude-sonnet-5-5"      # only after a flag
CALL_TIMEOUT=900
SMOKE_TIMEOUT=120
export CLAUDE_CODE_DISABLE_REFUSAL_FALLBACK=1

# Portable per-call timeout. macOS has no `timeout`; perl ships at /usr/bin/perl.
run_to() {                              # usage: run_to <seconds> <cmd...>
  local s="$1"; shift
  if command -v timeout  >/dev/null 2>&1; then timeout  "$s" "$@"
  elif command -v gtimeout >/dev/null 2>&1; then gtimeout "$s" "$@"
  else perl -e 'my $t=shift; my $p=fork; if(!$p){exec @ARGV;exit 127} eval{local $SIG{ALRM}=sub{die};alarm $t;waitpid($p,0);alarm 0}; if($@){kill "TERM",$p;exit 124} exit($?>>8)' "$s" "$@"
  fi
}

# One read-only critic call. The prompt comes from stdin. Prints the exit code
# and one status from critic_status.py, and writes the reply to $DIR/msg.txt.
# Only the current critic model may answer; any other model is wrong_model.
critic() {                              # usage: critic <seconds> <effort> [session flags] < prompt
  local s="$1" effort="$2"; shift 2
  (cd "$REPO" && run_to "$s" claude -p --model "$(cat "$DIR/model")" --effort "$effort" "$@" \
    --output-format stream-json --verbose --tools "Read,Grep,Glob" \
    --permission-mode dontAsk --strict-mcp-config --disable-slash-commands \
    --add-dir "$DIR") > "$DIR/events.jsonl" 2> "$DIR/err.log"
  echo "exit=$? model=$(cat "$DIR/model")"
  python3 "$SKILL_DIR/scripts/critic_status.py" "$DIR/events.jsonl" "$DIR/msg.txt" \
    "$(cat "$DIR/model")"
}

new_session() { python3 -c 'import uuid; print(uuid.uuid4())' > "$DIR/session_id"; }
ENV
} > "$DIR/env.sh"
source "$DIR/env.sh"
echo "$PRIMARY_MODEL" > "$DIR/model"    # the current critic model

cat > "$DIR/critic.txt" <<'CRITIC'

You are an independent adversarial critic. Do not approve, praise, or soften the review.

When the packet lists question IDs, first give a one-line assessment of the current answer for every ID: objection, no substantive objection, or not assessed with the reason. Then develop the strongest objection.

Find the single weakest point in the current position. Surface hidden assumptions, edge cases, failure modes, and missing evidence. Ground objections in the provided evidence and inspect the repo read-only when needed. If a better alternative exists, propose it concretely. If the options omit a better option or frame the choice falsely, say so and propose the missing option.

Avoid repeating prior objections unless the handling was insufficient. If no substantive objection remains, reply with: NO SUBSTANTIVE OBJECTION. Then give one sentence explaining why the position holds.
CRITIC
echo "workdir: $DIR"; echo "repo: $REPO"
```

## Preflight

A real smoke call catches problems that `command -v` cannot: a missing sign-in, a model that the account cannot use, or a sandbox that blocks the network.

```bash
source "<workdir>/env.sh"
command -v claude  >/dev/null || { echo "claude CLI not found"; exit 1; }
command -v python3 >/dev/null || { echo "python3 not found"; exit 1; }
printf 'Reply with exactly: ok\n' | critic "$SMOKE_TIMEOUT" low --no-session-persistence
grep -qiw "ok" "$DIR/msg.txt" && echo "REPLY OK" || { echo "REPLY MISSING"; tail -5 "$DIR/err.log"; }
```

- Status `ok` and `REPLY OK` — continue to the loop.
- Status `flagged` — follow [Flags](#flags), then re-run the preflight.
- Any other result — stop. Report a one-line diagnosis from `$DIR/err.log`, for example "Claude Code is not signed in", "`claude-opus-5-5` is not available to this account", or "the sandbox blocked network access". The ending condition is "critic unavailable".

## Loop

1. State the current position: claim, reasoning, and decision boundary.
2. Build a [pressure-test packet](#pressure-test-packet).
3. Send the packet to the Claude critic (kickoff or resume, below).
4. Read the critic's objections from `$DIR/msg.txt`.
5. Handle every substantive objection: concede and revise when it holds against the evidence, or rebut with evidence. Do not concede only to end a round.
6. Print the round block (see [Progress Format](#progress-format)) and update the [session record](#session-record), including the coverage table when the packet has question IDs.
7. Stop if converged; otherwise repeat until round 6.
8. Write and present the conclusion.

## Pressure-Test Packet

The kickoff packet has these fields:

```text
GOAL
The question, design, plan, rubric, PR, or failure diagnosis under review.

CURRENT POSITION
The current answer and reasoning. For several questions, one entry per ID (Q1, Q2, ...) with its current answer.

OPTIONS
For a choice: each option with its evidence, and the option the position recommends. Per ID for several questions. Omit when the goal is not a choice.

DECISION BOUNDARY
What is in scope, what is out of scope, and what kind of objection would change the decision.

EVIDENCE
Relevant files, diffs, command outputs, proposal sections, rubric text, PR body, task-loop state, or other concrete artifacts.

ASSUMPTIONS
Known constraints and assumptions to attack.

PRIOR ROUNDS
Objections already raised and how they were handled.
```

The critic instructions in `$DIR/critic.txt` follow the packet in every prompt.

If the packet lacks enough evidence for reliable judgment, gather the missing evidence before calling the critic, or state the gap in ASSUMPTIONS.

The critic can read files in the repository and in `$DIR`, but it cannot run commands. Put command output, such as a diff or test log, in the packet or in a file under `$DIR`, and name that file in EVIDENCE.

Give each question an ID when the packet holds several questions.

The critic keeps earlier rounds in its session. After the kickoff, a packet states the changes since the last round:

```text
HOW I HANDLED YOUR LAST OBJECTIONS
Per objection: conceded and revised, or rebutted with evidence.

CURRENT POSITION
The revised position. Restate each changed answer in full and list the IDs that changed.

NEW EVIDENCE
New files or command output, or "none".
```

## Calling The Critic

Kickoff (round 1):

```bash
source "<workdir>/env.sh"
cat > "$DIR/prompt.md" <<'__PROMPT_END__'
<pressure-test packet>
__PROMPT_END__
cat "$DIR/critic.txt" >> "$DIR/prompt.md"
new_session
critic "$CALL_TIMEOUT" xhigh --session-id "$(cat "$DIR/session_id")" < "$DIR/prompt.md"
cat "$DIR/msg.txt"
```

Later rounds:

```bash
source "<workdir>/env.sh"
cat > "$DIR/prompt.md" <<'__PROMPT_END__'
<pressure-test packet for this round>
__PROMPT_END__
cat "$DIR/critic.txt" >> "$DIR/prompt.md"
critic "$CALL_TIMEOUT" xhigh --resume "$(cat "$DIR/session_id")" < "$DIR/prompt.md"
cat "$DIR/msg.txt"
```

Act on the status line:

- `ok` — read the objections in `$DIR/msg.txt`.
- `flagged` — follow [Flags](#flags).
- `wrong_model:<ids>` — stop. Report that a model other than the current critic model answered, and do not use the reply.
- `error:<detail>`, or a non-zero exit code (124 means timed out) — follow [Failure Behavior](#failure-behavior).

Record each failed or retried call in the session record, with its `exit=` line and its status.

## Flags

Any safeguard action flags the call, even when the critic finished its answer. `critic_status.py` reports `flagged` when a response ends with `stop_reason: "refusal"`, when the result reports `safety_stops` above zero, or when Claude Code reports a `model_refusal_fallback` or `model_refusal_no_fallback` event.

- **Flag on the critic model** — switch to the fallback model and re-run the same block once; `prompt.md` is unchanged:

  ```bash
  source "<workdir>/env.sh"; echo "$FALLBACK_MODEL" > "$DIR/model"
  ```

  For the kickoff, the block calls `new_session` again, because Claude Code refuses to reuse a session ID. For a later round, the retry resumes the same session on the fallback model. Keep the fallback model for the rest of the pressure test, and record the switch in the session record.
- **Flag on the fallback model** — stop. Use no other model, and do not continue without a critic. Write a partial conclusion; the ending condition is "critic flagged".
- A flag is not a failed round: it does not use the failure retry.

## Convergence

Stop before round 6 only when:

- the critic reports no substantive objection, or
- the original decision is stable and remaining objections are out-of-scope refinements that do not change the decision.

The main agent's own disposition never makes the packet converged: a critic that repeats a rebutted objection still objects.

With question IDs, the packet converges only when the critic's latest reply clears every ID: each ID has no substantive objection, or only out-of-scope refinements. An ID that the latest reply does not assess counts as not assessed and does not converge.

Do not stop because the current position feels persuasive. Judge convergence against the critic's actual objections and the decision boundary.

## Progress Format

Print one block per round, as it happens:

```text
─── Round N ───
Critic ▸ <faithful 2-4 bullet objections — no softening>
Codex ▸ <concede/rebut per objection, condensed>
```

End with the ending condition, for example `Converged after N rounds.` or `Round cap reached — K tension(s) unresolved.`

## Session Record

After each round, update `SESSION_PATH` with the complete session so later turns can resume from it:

```text
Round N (critic model: <model>)
Calls: <each failed or retried call, with its exit= line and status; or "ok">
Critic: strongest objections, faithfully summarized.
Disposition: conceded and revised, or rebutted with evidence.
Current position: updated position.
```

With question IDs, keep a coverage table:

```text
| ID | Latest critic assessment | Round | Revised after last assessment |
```

An ID is reviewed when the critic has assessed some version of its answer. It is converged when the critic's latest assessment covers its current answer and raises no substantive objection, or only out-of-scope refinements. Mark "revised after last assessment" when the main agent changes an answer after the critic's latest reply.

## Conclusion

Write the conclusion to `CONCLUSION_PATH`.

Include:

- final position
- key decisions
- strongest objections and dispositions
- the coverage table, when the packet had question IDs
- unresolved tensions, if any
- failed and retried critic calls, with their `exit=` lines and statuses
- ending condition: converged, round cap, critic unavailable, critic flagged, or cut short
- the critic model or models that took part

Present the same conclusion in chat. When another skill called this skill, that skill reads the conclusion and continues its own work; do not wait for the user.

## Failure Behavior

If the `claude` CLI is missing, the preflight fails, or the sandbox blocks the critic and escalation is unavailable, stop and report that an independent critic could not run. Write a short conclusion with the diagnosis; the ending condition is "critic unavailable". Do not silently run inline self-critique or a Codex subagent instead.

If a critic round fails mid-loop, retry that round once. If it still fails, write a partial conclusion with the last stable position, unresolved objections, and the failure point; the ending condition is "cut short".
