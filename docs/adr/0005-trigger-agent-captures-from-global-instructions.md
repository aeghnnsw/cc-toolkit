# Trigger agent captures from global instruction files

Agents on large tasks found decisions that only the user could make, and
results that needed review. These items stayed in agent sessions, so the
user's list of next actions was not complete. Agents now add an agent
capture to the GTD inbox when a task that they were given stops and waits
on the user. The user processes each agent capture with `gtd-process` and
completes each record. The agent that adds an agent capture only creates
inbox items.

One rule in the user's global instruction files, `CLAUDE.md` for Claude
Code and `AGENTS.md` for Codex, turns this on. The user-invoked `gtd-setup`
skill adds the rule after the user agrees. The rules for what to capture,
the item format, and the limits are in the `gtd-inbox` skill, which loads
only when it is used and adds agent captures only when the user's
instructions ask for them. A person who installs the plugin and does
not turn on agent captures gets no new behavior.

An agent capture holds a proposal in its notes: a next action, a GTD
project, a priority, a GTD deadline, and an effort. The other record fields
keep their defaults, so a proposal never becomes a commitment before the
user approves it in `gtd-process`.

Rejected alternatives:

- **A shipped `Stop` hook** that blocks the end of a turn until the agent
  checks for items. It would run in every session of every person who
  installs the plugin, and it costs one more agent turn at each stop. A hook
  cannot judge whether an item needs the user; only the agent can.
- **A narrow database function** that only inserts inbox items. The
  connected route can run any SQL, so the function would not restrict an
  agent. The limit is a rule in the skill.
- **The agent completes its own capture** after the user answers. After
  `gtd-process`, the record is a next action that the user approved. An
  agent that completes it could complete work that the user has not
  checked, and the user already confirms each item.

Consequences:

- An agent that does not follow the rule misses an item. If a navigation
  retrospective finds missed items, a user can add a personal hook.
- A tool that replaces a global instruction file removes the rule. A new
  run of `gtd-setup` adds it again.

See [#406](https://github.com/aeghnnsw/cc-toolkit/issues/406).
