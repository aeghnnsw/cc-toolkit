# goal-rubric — Design

## Goal

A `dev-skills` skill that turns a one-line goal into a **binary rubric** a `/goal`
grader can reliably check against. The skill drafts the rubric from the goal plus
a read-only look at the repo, asks the user only about gaps it can't infer, then
saves the rubric to a file and renders a ready-to-paste `/goal` condition.

The deliverable is a rubric — not code changes and not a running loop.

## Why this skill exists

Both Claude Code (`/goal`, v2.1.139+) and Codex CLI (`/goal`, 0.128.0+) run an
agent in a loop and, after each turn, hand the work to a separate small/fast
"grader" model that decides whether to stop. The grader checks the work against a
completion condition. The recurring failure mode in the docs: when a `/goal` loop
never closes, the cause is almost always an **unmeasurable or unobservable
completion condition**. A well-formed binary rubric is the fix — this skill
produces that rubric.

## Grader constraints that shape every rubric

These come from how `/goal` actually evaluates, and they are the reason a `/goal`
rubric differs from a generic eval rubric:

- **Transcript-only.** The grader sees only what the agent surfaced in the
  conversation. It does not run commands or read files itself. → Every criterion
  must be provable from the agent's own output (**transcript-observable**).
- **Small/fast model.** The grader defaults to a Haiku-class model and returns
  yes/no + a short reason. → Criteria must be atomic and unambiguous
  (**small-model-judgeable**).
- **Codex framing.** Codex `/goal` expects a goal to state: what to achieve, what
  not to change, how to validate, and when to stop.

## Rubric design rules (1–6, binary)

Every rubric the skill produces must satisfy:

1. **Measurable end state** — each criterion names an observable signal: a test
   result, build/exit code, file count, or empty queue.
2. **Stated check** — how the end state is proven (e.g. "`pytest test/auth` exits 0").
3. **Constraints / guardrails** — what must not change on the way there (e.g.
   "no other test file is modified").
4. **Stop / budget clause** — a turn or time cap (e.g. "or stop after 20 turns").
5. **Independent criteria** — no double-counting; each criterion stands alone.
6. **Binary AND** — every criterion is a hard gate; the goal is done only when
   *all* criteria pass. (Going binary collapses the gate-vs-preference split into
   "all gates.")

**Overlay (the skill's value-add):** on top of rules 1–6, every criterion must be
*transcript-observable* and *small-model-judgeable*, per the grader constraints
above. This is what neither the `/goal` docs nor a generic rubric guide give you.

## Scope

In scope:
- One goal in → one binary rubric out (saved file + rendered `/goal` condition).
- Read-only repo inspection to infer end states and the checks that prove them.
- Hybrid drafting: draft first, then ask targeted questions only for gaps.
- Render the condition for Claude or Codex (default Claude).

Out of scope (YAGNI):
- Diagnosing or repairing an existing rubric (draft only).
- Scoring scales, per-criterion anchors/examples, calibration steps.
- Running `/goal` itself — the skill produces the string; the user runs it.
- Executable code, scripts, or dependencies.
- Worked examples embedded in the skill.

## Workflow (hybrid)

1. **Take the goal** — a one-line or short description from the user.
2. **Inspect (read-only)** — read test config, build/lint commands, and file
   layout to infer measurable end states and the commands/artifacts that prove
   them.
3. **Draft the binary rubric** — independent pass/fail criteria, each with end
   state + check + constraint, plus one overall stop clause.
4. **Ask gap questions** — only for what inspection couldn't settle (e.g. which
   command proves the feature works, which files must not change, the turn/time
   cap). Keep them concise; never re-ask what inspection already answered.
5. **Finalize** — save the rubric markdown file and render the `/goal` condition
   string for the named tool.

## Output

Rubric file (default `./goal-rubric-<slug>.md` in the working dir, overridable):

```
# Goal rubric: <goal one-liner>

## Criteria (all must pass)
1. <name> — End state: <observable signal>. Check: <how it's proven in the
   transcript>. Constraint: <what must not change>.
2. ...

## Stop clause
<turn or time cap>

## /goal condition (<tool>)
<a fenced code block holding the ready-to-paste condition string>
```

The rubric core (criteria + stop clause) is tool-agnostic. The rendered condition
targets the named tool:
- **Claude** — a single condition string (≤4,000 chars) phrased around
  transcript-observable proof ("… and `npm test` output shows 0 failures").
- **Codex** — the what / what-not-to-change / how-to-validate / when-to-stop
  framing.

Default to Claude; confirm the tool if it's ambiguous.

## Skill file structure

```
dev-skills/skills/goal-rubric/
└── SKILL.md
```

Single file. No scripts, references, or examples. Triggers: "draft a rubric for
/goal", "write a goal rubric", "make a rubric for this goal", "rubric for goal".

## Defaults summary

| Setting | Default |
|---|---|
| Rubric type | binary (pass/fail per criterion) |
| Workflow | hybrid (draft → targeted gap questions) |
| Output | rubric file + rendered `/goal` condition |
| Target tool | Claude `/goal` (Codex on request) |
| Save path | `./goal-rubric-<slug>.md` (overridable) |
| Scope | draft only |

## Future / non-goals

- Diagnose/repair mode for failing rubrics — only if a real need appears.
- A multi-example reference library.
- Auto-running `/goal` with the produced rubric.
