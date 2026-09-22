# Efficiency

- Use the simplest solution that meets the request.
- Use subagents for independent tasks. Use multiple CPU cores when this reduces
  run time.
- A subagent starts with a fresh context. It does not see the conversation, the
  skills already invoked, or the files already read. Give it a self-contained
  prompt: objective, relevant facts and decisions, file paths, constraints,
  expected result, and edit ownership when it applies. Do not copy CLAUDE.md or
  git status into the prompt; both load automatically. Preload skills with the
  agent's `skills` field.
- Prefer a fresh subagent. Use `subagent_type: "fork"` only when the task needs
  the full conversation, and explain why. Continue an existing subagent with
  `SendMessage`; a new `Agent` call starts fresh.
- Report what matters from a subagent's result. The user does not see it.
- Run the relevant tests. Add broader checks when risk or requirements justify
  them.
- Reuse valid results. Repeat costly work only when conditions change or
  verification requires it.
- Check a running job before you restart it.
- On a long task, keep brief progress notes. Reassess the approach when progress
  stops.

# Communication style

Write user-facing prose in clear, concise English based on ASD-STE100
principles. This covers replies, plans, summaries, documentation, and generated
issue or pull-request text.

- Give the result first. Add the context needed to understand it.
- Write short sentences, one topic each. Use active voice and direct verbs.
- Use the imperative for instructions. Put the condition before the action.
- Number procedure steps. Put one action in each step.
- Reuse one term per concept. Avoid synonyms, idioms, slang, metaphors, filler,
  and vague pronouns.
- Explain a technical term on first use.
- Reproduce commands, filenames, code identifiers, API names, log messages, and
  quotations exactly.
- Never drop technical requirements, risks, errors, or uncertainty to save words.
- Do not rename identifiers or rewrite code to satisfy these rules.

Accuracy and explicit user instructions override this style.

# Git hosting

- Do not add "created by Claude Code" or similar messages to commits, issues, or
  pull requests.
- Do not add a test plan to a pull request.
- Keep pull-request comments simple, concise, and accurate.
