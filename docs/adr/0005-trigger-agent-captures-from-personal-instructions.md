# Trigger agent captures from personal instructions

Agents on large tasks found decisions that only the user could make, and
results that needed review. These items stayed in agent sessions, so the
user's list of next actions was not complete. Agents now add an agent
capture to the GTD inbox when a task that they were given stops and waits
on the user. The user processes each agent capture with `gtd-process` and
completes each record. An agent only adds inbox items.

One sentence in the user's global `CLAUDE.md` and `AGENTS.md` turns this on.
The user-invoked `gtd-setup` skill adds the sentence after the user agrees.
The rules for what to capture, the item format, and the limits are in the
`gtd-inbox` skill, which loads only when it is used. A person who installs
the plugin and does not turn on agent captures gets no new behavior.

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
- **The agent completes its own capture** after the user answers. The user
  completes each record, so an agent never changes a record.

Consequences:

- An agent that does not follow the rule misses an item. If a navigation
  retrospective finds missed items, a user can add a personal hook.
- A tool that replaces a global instruction file removes the sentence. A new
  run of `gtd-setup` adds it again.

See [#406](https://github.com/aeghnnsw/cc-toolkit/issues/406).
