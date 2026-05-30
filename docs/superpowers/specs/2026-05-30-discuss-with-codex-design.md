# discuss-with-codex — Design

## Goal

A `dev-skills` skill that, given a goal, runs an autonomous turn-by-turn
deliberation between Claude and the Codex CLI and converges on a written
conclusion. Claude harnesses the turns; Codex is an adversarial critic. The
deliverable is a reasoned conclusion, not code changes.

Inspired by PolyArch/humanize, but deliberately leaner: no fixed phase machine
(gen-idea / gen-plan / refine-plan), no Gemini, no heavyweight progress monitor.
The "harness" is a single loop because conversational state lives inside each
model's own session.

## Core idea: truth-seeking asymmetry

The two participants play different games on purpose:

- **Codex is adversarial** — every turn it is told to find the weakest part of
  the current position, push back hard, and propose a better alternative.
- **Claude is truth-seeking** — it holds its genuine best position and updates
  it honestly under pressure, conceding or rebutting each objection.

The conclusion is Claude's position *after* it has survived adversarial
pressure, plus any objections that could not be dissolved (flagged as unresolved
with Claude's chosen resolution and reasoning).

## Scope

In scope:
- One goal in → autonomous Claude↔Codex loop → one conclusion out.
- Codex read-only, grounded in the actual repo.
- Conclusion always saved to a dated file and presented in chat.

Out of scope (YAGNI):
- Codex editing files or running the project.
- A neutral third judge or a Claude-subagent debater (rejected: extra layers).
- Gemini / other backends.
- User checkpoints mid-loop (the loop is fully autonomous).
- Resuming a past discussion across skill invocations.

## Architecture: thin harness (Approach A)

Claude *is* one of the two debaters. It holds the position in its own context
and shells out to `codex exec` / `codex exec resume` for the critic each round.
The discussion runs inline in the main session. Claude is simultaneously the
participant and the harness.

Rejected alternatives:
- **B — neutral orchestrator + Claude-subagent debater.** Cleaner separation of
  judge from debater, but adds a subagent layer (the humanize heaviness we are
  avoiding) and weakens the "Claude vs Codex" framing.
- **C — Codex-only, Claude as scribe.** Throws away the two-model value.

Honest weakness of A: Claude both argues and judges convergence. Mitigated by
defining the stop condition from *Codex's* words, not Claude's preference (see
Convergence).

## Codex invocation

Codex CLI: `codex-cli 0.135.0` (`codex exec`).

Key mechanics verified:
- `codex exec [PROMPT]` runs non-interactively and prints the final message.
- `-o, --output-last-message <FILE>` writes exactly the agent's final message to
  a file — read Codex's reply from here, no log scraping.
- `--json` prints JSONL events to stdout, including the session id.
- `-s, --sandbox read-only` and `-C, --cd <DIR>` set the sandbox and working
  root **on the first call only**.
- `codex exec resume <SESSION_ID> [PROMPT]` continues the same session,
  preserving Codex's own context. `resume` supports `--json` and `-o` but
  **not** `-s` or `-C` — it inherits the original session's sandbox and cwd.

**Session id (pinned empirically):** the first JSONL event is
`{"type":"thread.started","thread_id":"<uuid>"}`. Capture `thread_id` from that
line; `codex exec resume <thread_id>` continues the session. Fallback if capture
fails: `codex exec resume --last`.

**Every codex call is wrapped in `timeout`.** Testing showed a single broken
Codex hook can send `codex exec` into a near-infinite emit loop (it answered
correctly, then repeated a hook-failure message 45+ times). A per-call wall-clock
cap (default **180s**) is mandatory so one bad call cannot hang the skill. A
timeout counts as a failed call (see Error handling).

Patterns:

First turn (kickoff):
```
timeout 180 codex exec --json -s read-only -C "$REPO" \
  -o "$DIR/codex_msg.txt" "$PROMPT" \
  > "$DIR/codex_events.jsonl" 2> "$DIR/codex_err.log"
```
- Read Codex's reply from `$DIR/codex_msg.txt`.
- Capture the thread id: first line of `$DIR/codex_events.jsonl` of type
  `thread.started`, field `thread_id`.

Later turns:
```
timeout 180 codex exec resume "$THREAD_ID" --json \
  -o "$DIR/codex_msg.txt" "$PROMPT" \
  > "$DIR/codex_events.jsonl" 2> "$DIR/codex_err.log"
```

Working files live under a per-run temp dir (e.g. `$CLAUDE_JOB_DIR/tmp` when set,
else a `mktemp -d`). The `codex_msg.txt` files double as the raw transcript the
user can open.

## Turn protocol

1. **Preflight** — confirm `command -v codex`, then run a **real smoke call**
   (`timeout 60 codex exec --json -s read-only -C "$REPO" -o smoke.txt "Reply
   with exactly: ok"`). The smoke call catches a broken environment that
   `command -v` cannot — missing/failed Codex hooks, auth problems, sandbox
   refusals. If codex is missing, the smoke call fails/times out, or `smoke.txt`
   doesn't contain the expected reply, stop with a one-line diagnosis (e.g.
   "Codex hooks are failing — check `~/.codex` plugin cache") plus a fix hint.
   No Claude-only fallback (the skill is pointless without Codex).
2. **Kickoff** — Claude writes its honest initial position on the goal (claim +
   reasoning). Sends goal + position + critic instructions to Codex (first call).
3. **Round** — Claude reads Codex's objections. For each objection it either
   **concedes & revises** or **rebuts with reasoning**, and updates its position.
   It sends the revised position plus its per-objection handling back via
   `resume`.
4. Repeat step 3 until a stop condition fires.

**Critic instruction sent every turn** (in spirit):
> You are an adversarial critic. Find the weakest part of this position, push
> back hard, and propose a better alternative if one exists. Be concrete and
> cite the repo where relevant. If you have no substantive objection left, reply
> `NO FURTHER OBJECTIONS` and state why the position holds.

## Convergence & stop conditions

- **Converged** — Codex replies `NO FURTHER OBJECTIONS`, or its latest reply only
  restates points Claude has already addressed (no new substantive objection).
  Judged against Codex's own words, not Claude's preference.
- **Round cap** — default **6 rounds** (one round = one Claude↔Codex exchange).
  On cap, any live disagreements are carried into the conclusion as explicitly
  unresolved.
- **Error** — a codex call fails or times out (non-zero exit, including the
  `timeout` 124 code) → retry once → if it still fails, conclude with what exists
  and state that the discussion was cut short.

## Conclusion output

Always saved to `docs/superpowers/specs/YYYY-MM-DD-<topic>-conclusion.md` **and**
presented in chat. Contents:

- The settled position.
- Key decisions made.
- The strongest objections Codex raised and how each was resolved.
- Any unresolved tensions, with Claude's chosen resolution and why.
- How the discussion ended (converged after N rounds / round cap / cut short).

## Progress monitoring

One compact, fixed-format block per round, streamed as each round completes:

```
─── Round 2 ───
Codex ▸ <faithful 2–4 bullet objections>
Claude ▸ <concede/rebut per objection, condensed>
```

Objections are shown faithfully (no softening or editorializing). The full raw
exchanges persist in the per-run `codex_msg.txt` files for the user to open.
Final status line: `Converged after N rounds` or
`Round cap reached — K tension(s) unresolved`.

## Defaults summary

| Setting | Default |
|---|---|
| Round cap | 6 |
| Per-call timeout | 180s (60s for preflight smoke call) |
| Codex sandbox | `read-only`, repo as cwd |
| Conclusion | always saved + shown in chat |
| Codex stance | adversarial critic (every turn) |
| Loop control | fully autonomous (no mid-loop checkpoints) |

## Skill file structure

```
dev-skills/skills/discuss-with-codex/
└── SKILL.md
```

Single-file skill. Triggers: "discuss with codex", "debate this with codex",
"get codex's take", "deliberate with codex on …".

## Future / non-goals

- Configurable stance (peer vs critic) — only if a real need appears.
- Multi-backend (Gemini, etc.) — explicitly excluded for now.
- Persisting/resuming discussions across invocations.
