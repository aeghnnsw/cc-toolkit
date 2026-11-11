# Trigger agent captures from global instruction files

> **Superseded in part (2026-11-11, issue #416).** An agent capture whose
> work is already done now leaves the inbox by a soft delete. The agent that
> did its work deletes it, or `gtd-process` deletes it after the user
> approves the batch. Read [Done agent captures](#done-agent-captures).

Agents on large tasks found decisions that only the user could make, and
results that needed review. These items stayed in agent sessions, so the
user's list of next actions was not complete. Agents now add an agent
capture to the GTD inbox when a task that they were given stops and waits
on the user. The user processes each agent capture with `gtd-process` and
completes each record. The agent that adds an agent capture only creates
inbox items. (These two sentences are superseded in part; read
[Done agent captures](#done-agent-captures).)

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
  checked, and the user already confirms each item. (This rejection still
  holds for a processed record. It did not cover a capture that is still
  pending; read [Done agent captures](#done-agent-captures).)

Consequences:

- An agent that does not follow the rule misses an item. If a navigation
  retrospective finds missed items, a user can add a personal hook.
- A tool that replaces a global instruction file removes the rule. A new
  run of `gtd-setup` adds it again.

## Done agent captures

The user often answers an agent capture a few minutes later in the same
thread, and the agent then does the work. Before 2026-11-11, the capture
stayed pending, and `gtd-process` proposed a next action for work that was
done. On 2026-11-10, 2 of the 8 pending agent captures were done and 1 was
partly done. A pending capture is not yet a GTD action, so the rejection of
"the agent completes its own capture" did not apply to it.

From 2026-11-11, an agent capture whose work is done leaves the inbox by a
soft delete, not by completion:

- An agent deletes an agent capture when the user gave the answer that the
  capture waits on in the conversation, and the agent then did all the work
  that the answer asks for. It does this for the captures that it saved in
  the conversation. It deletes another agent capture only when it sees it
  in an inbox read that it makes anyway. It decides only from the
  conversation, and the user's answer is the confirmation. It reports the
  title and the full UUID of each deleted capture.
- `gtd-process` checks each agent capture against its source before it
  proposes work. The batch proposes each capture whose work is done as
  "Delete: already done", with the evidence, and the user's batch approval
  covers the deletion.

A soft delete keeps the record, and the user can restore it by its UUID.
The agent still never changes, completes, or restores a record, and it
deletes no other record. A subagent reports its work to its parent instead
of deleting a capture.

Rejected alternatives:

- **Complete the capture and add the evidence to its notes.** `gtd-process`
  completes a capture when it turns the capture into approved work. A
  capture whose work is done needs no processing, and no GTD skill shows a
  completed capture or its notes.
- **An agent deletes a capture from the state of another source**, such as
  a merged pull request or a closed issue. A source state does not show
  that all the work of the capture is done. `gtd-process` makes that check
  and shows its evidence to the user.

See [#406](https://github.com/aeghnnsw/cc-toolkit/issues/406) for agent
captures and [#416](https://github.com/aeghnnsw/cc-toolkit/issues/416) for
done agent captures.
