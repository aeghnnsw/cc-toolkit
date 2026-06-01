# discuss-with-codex Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `dev-skills` skill that runs an autonomous turn-by-turn adversarial discussion between Claude and the Codex CLI, converging on a saved written conclusion.

**Architecture:** Single-file procedural skill (`SKILL.md`). Claude is one debater and the harness; it shells out to `codex exec` / `codex exec resume` for an always-adversarial, read-only critic. Conversational state lives in each model's own session (Codex via `thread_id` resume), so the "harness" is a simple loop, not a phase machine. Every codex call is wrapped in `timeout`.

**Tech Stack:** Markdown skill (`SKILL.md` with YAML frontmatter), Codex CLI (`codex exec`, v0.135.0), bash, `jq`-free JSONL parsing via `grep`/`sed`, portable timeout (`timeout`/`gtimeout`/`perl` fallback), stdin pinned to `/dev/null`.

**Verified on real CLI (2026-05-30):** kickoff (clean `ok`, exit 0), `thread_id` capture from the `thread.started` event, and `resume` retaining context. Three live-testing findings are baked into the SKILL.md below: (a) macOS has no `timeout`; (b) `codex exec` blocks on stdin unless given `</dev/null`; (c) the one-time hook-loop was a transient `1.0.7→1.0.10` upgrade race that self-healed.

**Spec:** `docs/superpowers/specs/2026-05-30-discuss-with-codex-design.md`

---

## File Structure

- **Create** `dev-skills/skills/discuss-with-codex/SKILL.md` — the entire skill: frontmatter (triggering description) + the procedural workflow Claude follows (preflight, kickoff, discussion loop, stop conditions, conclusion, progress format, error handling). All codex command templates live here.
- **Modify** `dev-skills/.claude-plugin/plugin.json` — bump `version` `3.6.0` → `3.7.0` (added skill).
- **Modify** `README.md` — add a one-line bullet for the new skill under the `dev-skills` "Skills:" list (optional, curated highlight list).

No agents, scripts, hooks, or marketplace/`.codex-plugin` changes — skills are auto-discovered.

---

## Task 1: Create the SKILL.md

**Files:**
- Create: `dev-skills/skills/discuss-with-codex/SKILL.md`

- [ ] **Step 1: Write the skill file**

Create `dev-skills/skills/discuss-with-codex/SKILL.md` with EXACTLY this content:

````markdown
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
- `CALL_TIMEOUT=180` seconds per codex call; `SMOKE_TIMEOUT=60` for preflight
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
codex_to 60 codex exec --json -s read-only -C "$REPO" -o "$DIR/smoke.txt" \
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

codex_to 180 codex exec --json -s read-only -C "$REPO" \
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
# the session at kickoff and `resume` rejects those flags. Always use the
# explicit THREAD_ID form captured in Step 1.
codex_to 180 codex exec resume "$THREAD_ID" --json \
  -o "$DIR/msg.txt" "$PROMPT" \
  > "$DIR/events.jsonl" 2> "$DIR/err.log"
echo "exit=$?"
cat "$DIR/msg.txt"
```

## Stop conditions

- **Converged** — Codex's reply contains `NO FURTHER OBJECTIONS`, or it only
  restates points you have already addressed (no new substantive objection).
  Judge this against Codex's actual words, not your preference.
- **Round cap** — 6 rounds reached. Carry any live disagreements into the
  conclusion as explicitly unresolved.
- **Error** — a codex call exits non-zero or times out (`timeout` exit code 124)
  → retry the same call once → if it still fails, conclude with what exists and
  state the discussion was cut short.

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
````

- [ ] **Step 2: Verify the file exists and frontmatter is well-formed**

Run:
```bash
test -f dev-skills/skills/discuss-with-codex/SKILL.md && echo EXISTS
head -3 dev-skills/skills/discuss-with-codex/SKILL.md
grep -c '^name: discuss-with-codex$' dev-skills/skills/discuss-with-codex/SKILL.md
grep -c '^description: ' dev-skills/skills/discuss-with-codex/SKILL.md
```
Expected: `EXISTS`, the first line is `---`, and both `grep -c` print `1`.

- [ ] **Step 3: Verify required sections are present**

Run:
```bash
for s in "## Overview" "## Step 0 — Preflight" "## Step 1 — Kickoff" "## Step 2 — Discussion loop" "## Stop conditions" "## Step 3 — Conclusion"; do
  grep -qF "$s" dev-skills/skills/discuss-with-codex/SKILL.md && echo "OK  $s" || echo "MISSING  $s"
done
```
Expected: all six lines print `OK`.

- [ ] **Step 4: Verify the critical codex command lines are present and correct**

Run:
```bash
F=dev-skills/skills/discuss-with-codex/SKILL.md
grep -qF 'codex_to()' "$F" && echo "OK timeout helper defined"
grep -qF 'open(STDIN,"<","/dev/null")' "$F" && echo "OK stdin redirect in helper"
grep -qF 'codex_to 180 codex exec --json -s read-only -C "$REPO" \' "$F" && echo "OK kickoff call"
grep -qF 'codex_to 180 codex exec resume "$THREAD_ID" --json \' "$F" && echo "OK resume call"
grep -qE 'sed -nE .*"thread\\\.started"' "$F" && echo "OK thread_id capture (single-sed, tolerant)"
grep -qF 'codex_to 60 codex exec --json -s read-only -C "$REPO" -o "$DIR/smoke.txt" \' "$F" && echo "OK smoke call"
# Invariants protecting the resume-flag/empty-THREAD_ID fix (issue #113):
grep -qF 'codex exec resume --last' "$F" && echo "FAIL --last fallback present" || echo "OK no --last fallback"
grep -qF '# NOTE: do NOT pass -s/-C to' "$F" && echo "OK Step 2 NOTE present" || echo "FAIL Step 2 NOTE missing"
grep -qF 'Only this first call carries' "$F" && echo "OK Step 1 asymmetry prose present" || echo "FAIL Step 1 asymmetry prose missing"
grep -qF 'sed -nE' "$F" && echo "OK tolerant thread_id parser" || echo "FAIL parser not whitespace-tolerant"
grep -qF 'status=$?' "$F" && echo "OK kickoff exit status captured" || echo "FAIL kickoff exit status not captured"
```
Expected: all `OK ...` lines print, no `FAIL` lines. This confirms the command
templates survived authoring AND the resume-flag invariants are locked in.

- [ ] **Step 5: Commit**

```bash
git add dev-skills/skills/discuss-with-codex/SKILL.md
git commit -m "Add discuss-with-codex skill"
```

---

## Task 2: Bump dev-skills plugin version

**Files:**
- Modify: `dev-skills/.claude-plugin/plugin.json`

- [ ] **Step 1: Verify current version**

Run:
```bash
grep '"version"' dev-skills/.claude-plugin/plugin.json
```
Expected: `"version": "3.6.0"`

- [ ] **Step 2: Bump to 3.7.0**

Edit `dev-skills/.claude-plugin/plugin.json`, changing the version line from
`"version": "3.6.0"` to `"version": "3.7.0"`.

- [ ] **Step 3: Verify JSON is valid and version updated**

Run:
```bash
python3 -c "import json;print(json.load(open('dev-skills/.claude-plugin/plugin.json'))['version'])"
```
Expected: `3.7.0`

- [ ] **Step 4: Commit**

```bash
git add dev-skills/.claude-plugin/plugin.json
git commit -m "Bump dev-skills to 3.7.0 for discuss-with-codex"
```

---

## Task 3: Add README entry (optional highlight)

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Locate the dev-skills Skills list**

Run:
```bash
grep -n "step-workflow\*\*:" README.md
```
Expected: one match — the line listing `**step-workflow**: ...` under dev-skills.

- [ ] **Step 2: Add the new bullet immediately after the step-workflow bullet**

Insert this line directly after the `**step-workflow**:` bullet:
```markdown
- **discuss-with-codex**: Autonomous turn-by-turn adversarial discussion with the Codex CLI that converges on a saved written conclusion
```

- [ ] **Step 3: Verify it was added**

Run:
```bash
grep -c "discuss-with-codex" README.md
```
Expected: `1`

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "Document discuss-with-codex in README"
```

---

## Task 4: Live end-to-end verification

**Precondition:** the user's Codex environment must be healthy. A one-time
hook-loop on 2026-05-30 was traced to a transient `core-hooks` `1.0.7→1.0.10`
upgrade race in `~/.codex` and has since self-healed (verified: clean smoke +
resume). Still, always confirm the preflight smoke call passes before running
this task — it is the cheap guard against any future environment breakage.

**Files:** none modified (manual run).

- [ ] **Step 1: Run the preflight smoke call standalone**

Run:
```bash
DIR="$(mktemp -d)"; REPO="$(git rev-parse --show-toplevel)"
# Portable timeout + stdin /dev/null (macOS has no `timeout`; codex blocks on stdin).
perl -e 'my $t=shift; my $p=fork; if(!$p){open(STDIN,"<","/dev/null");exec @ARGV;exit 127} eval{local $SIG{ALRM}=sub{die};alarm $t;waitpid($p,0);alarm 0}; if($@){kill "TERM",$p;exit 124} exit($?>>8)' \
  60 codex exec --json -s read-only -C "$REPO" -o "$DIR/smoke.txt" "Reply with exactly: ok" \
  > "$DIR/smoke.jsonl" 2> "$DIR/smoke.err"
echo "exit=$?"; grep -qi ok "$DIR/smoke.txt" && echo "SMOKE OK" || { echo "SMOKE FAILED"; tail -5 "$DIR/smoke.err"; }
```
Expected: `exit=0` and `SMOKE OK`. If `SMOKE FAILED`, STOP and fix the Codex
environment (see Precondition) before continuing.

- [ ] **Step 2: Drive the skill on a trivial goal**

Invoke the skill yourself (follow `SKILL.md`) with a tiny goal, e.g.
*"Should a coin-flip helper default to returning a boolean or the string
'heads'/'tails'?"*. Run kickoff, capture `thread_id`, do at most 2 rounds, and
write the conclusion.

- [ ] **Step 3: Verify the loop mechanics worked**

Confirm during the run:
- `thread_id` was captured non-empty from the `thread.started` event.
- `codex exec resume "$THREAD_ID"` produced a second-round reply.
- A conclusion file `docs/superpowers/specs/$(date +%F)-*-conclusion.md` was written.

Run:
```bash
ls docs/superpowers/specs/$(date +%F)-*-conclusion.md
```
Expected: the conclusion file path prints.

- [ ] **Step 4: Clean up the throwaway conclusion**

The trivial-goal conclusion is a test artifact, not a real deliverable.

```bash
rm docs/superpowers/specs/$(date +%F)-*-conclusion.md 2>/dev/null
git status --short
```
Expected: no staged conclusion file remains.

---

## Self-Review

**Spec coverage:**
- Thin-harness architecture (Claude debater + Codex critic) → Task 1 SKILL.md Overview + loop.
- Truth-seeking asymmetry → Task 1 Overview + critic block.
- Preflight smoke call → Task 1 Step 0; Task 4 Step 1.
- `thread_id` capture + resume → Task 1 Steps 1-2.
- Portable per-call timeout (180s / 60s smoke) + stdin `</dev/null` → Task 1 `codex_to` helper, all codex calls.
- Adversarial critic block every turn → Task 1 kickoff + loop prompts.
- Stop: converged / round cap 6 / error-retry-once → Task 1 Stop conditions.
- Conclusion always saved + shown → Task 1 Step 3.
- Per-round progress format → Task 1 Progress format.
- Read-only repo sandbox → Task 1 (`-s read-only -C "$REPO"`).
- Auto-discovery (no marketplace change) + version bump → Task 2.

**Placeholder scan:** The `<the goal>`, `<your position>`, `<topic-slug>` markers
inside the SKILL.md are intentional runtime fill-ins for the executing agent, not
plan placeholders — they are the parts Claude composes each run. All verification
commands are concrete.

**Type consistency:** Variable names consistent across tasks: `$DIR`, `$REPO`,
`$THREAD_ID`, `$PROMPT`, `$DIR/msg.txt`, `$DIR/events.jsonl`. The capture field is
`thread_id` from the `thread.started` event everywhere.
