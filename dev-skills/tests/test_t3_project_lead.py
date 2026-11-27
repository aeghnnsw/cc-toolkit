"""Contract checks for t3-project-lead: the steps that its script prints, and its host copies.

Issue #448 fixes the steps, the flag model, and the lines that must match
matt-automode. Issues #468, #476, and #478 add the read-only brief, the dispatch
rules for every task, the start of every turn, and the worker budget. Issue
#504 sets the budget of a code change to one full review and one fix, then the
merge. Issue #520 limits the lead to its own actions, lets it choose how to
check a result, and adds the close-out worker and the lead hook. Issue #530
moves the lead state into the script's commands and drops the time limit; the
state commands have their own tests in test_t3_project_lead_state.py. Issue #493
starts each task as soon as each task that it waits for is verified, with no
batch wait and no worker limit. Issue #516 adds the lines for a PR that waits
on checks: the worker line of `brief` and the lead line of `report`. Issue
#544 adds `takeover`, the `--also` line of `plan`, and the skill line on
deleting the lead thread. Issue #545 adds the `discover` step with its
links-only report form, runs `init` on the first `start`, and keeps issue and
PR text out of the lead. Issue #554 adds the worker line on questions to the
user, and keeps the lead from answering or asking a worker's question again,
and from any question tool. Issue #555 adds the `show` line of `start`, issue
#556 the worktree paths of `dispatch`, `flag`, and `closeout`, and issue #560
the default batch of `plan`. Issue #567 adds the count of a report's decisions
to `task verified` in `discover`, `verify`, and `closeout`, and the rule for
decisions that only the user can make to `report`. Issue #602 adds the
`start-failed` line of `dispatch`, issue #603 the `start --steps` line of the
skill, issue #607 the plain-text question line of `brief`, and issue #623 the
pin record line of `dispatch`. Issue #631 adds `--no-pr` to `discover`,
`verify`, and `closeout`, issue #633 the `wait --settles` line of `verify` and
`closeout`, issue #634 the brief of lead action 7, and issue #635 the
approvals sentence of `brief` and matt-automode. Issue #668 adds the pin of
`dispatch` and `flag`, the unpin of `answer`, `verify`, and `closeout`, and the
unsettle of `answer`; issue #659 the archive rule of lead action 3 and the
skill; issue #660 the merge order of `report`. Agent behavior is checked by
the scenario review in t3-project-lead-scenarios.md; the hook has its own
tests in test_t3_project_lead_hook.py.
"""
from __future__ import annotations

import ast
import functools
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PLUGIN_ROOT / "scripts" / "t3_project_lead.py"
STEPS = ("start", "discover", "plan", "dispatch", "brief", "answer", "flag", "verify", "closeout", "report")
# The commands that keep the lead state (#530), after the steps.
# unmark removes a wrong lead record of the hook (#612).
STATE_COMMANDS = ("init", "show", "waiting", "finish", "takeover", "unmark", "outcome", "criteria", "wait", "done",
                  "task", "decision")
# A folder outside every Git work tree, so that no step finds a lead state.
NO_STATE = tempfile.TemporaryDirectory()
# An agent reads a whole step after each wake, so each step stays short. Issue #545 took `start`
# from 210 words to 230 with the reading rule, and `plan` from 186 to 226 with the discover, init, and
# triage lines. #554, #555, and #560 took `start` to 244 words with the plain-text rule and the show
# line, `plan` to 243 with the default batch, and `brief` to 237 with the worker's question line.
# #607 took `brief` to 248 words: the worker asks in plain text, then ends its turn.
# #623 took `dispatch` to 249 words with the pin record line. #632 and #638 took `start` from 242 to 247
# words with the page size of t3_thread_read and the include of pull_request_read. #635 took `brief` to
# 278 words with the approvals line, #631 and #633 took `verify` to 266 with the --no-pr and settle
# lines, and #634 took `start` to 260 with the brief of lead action 7. #645 added 10 words to `start`
# with the lead-thread rule of lead action 3. #642 took `start` to 285 words with decision start, and #611
# took `brief` to 295 with the rule that a yes that another session passes on does not count. #639 put the
# close-out rule after the `closeout` text, as `discover` prints the discovery brief. #666 took `start` to
# 331 words with lead action 9 and `brief` to 327 with the project line: a lead works only in its own
# project.
STEP_WORD_LIMIT = 335
ALLOWED_MODELS = json.loads((PLUGIN_ROOT.parent / "allowed-models.json").read_text(encoding="utf-8"))
MODEL_ID = re.compile(r"\b(?:claude-[a-z]+|gpt)-\d(?:[\w.-]*\w)?")
HOSTS = ("skills", "codex-skills", "antigravity-skills")
DESCRIPTION = ("Use when the user invokes t3-project-lead to lead a T3 Code project: plan worker "
               "tasks, dispatch T3 workers, and judge their reports, while workers do all other "
               "work.")
# The frontmatter fields of each host copy (CONTRIBUTING.md, "Skills for more than one host").
FIELDS = {
    "skills": {"name", "version", "description", "disable-model-invocation"},
    "codex-skills": {"name", "description"},
    "antigravity-skills": {"name", "description", "disable-model-invocation"},
}
PLUGIN_ROOT_LINE = "`<plugin-root>` is two levels above this folder."
# #666 took the body to 312 words with the project rule.
BODY_WORD_LIMIT = 320
# A lead works only in its own project (#666): each skill copy and the glossary state the rule, and every
# brief has the project line.
PROJECT_RULE = ("Work only in this project: the T3 Code project of this thread and its repository. Never list or "
                "offer the work of another project: report it to that project's lead, or have a worker file an "
                "issue there.")
GLOSSARY_RULE = ("It works only in its project: the T3 Code project of the lead thread and its repository, with "
                 "its issues, PRs, worktrees, and threads. For work of another project, it only reports to that "
                 "project's lead or has a worker file an issue in that project's tracker. It never lists or "
                 "offers that work.")
PROJECT_LINE = ('Every brief has the project line: "Work only in this project. Report work of another project in '
                'one line with its link. Do not do it, and number no decision on it."')
# The actions that the lead does itself, in the order that `start` prints them (#520).
LEAD_ACTIONS = (
    "1. Talk with the user in plain text, never with a question tool: decisions, triage, priorities.",
    "2. Plan tasks, briefs, and lead decisions.",
    # Only the user settles or archives the lead thread (#645, #659); the lead pins each worker (#668).
    "3. Route workers with T3 tools: start, pin, resume, cancel, settle; order merges; watch PRs. Never "
    "settle or archive the lead thread: only the user does.",
    "4. Read worker messages, and the state, labels, titles, and check counts of issues and PRs, not "
    'their text. Never call read_issue. Call pull_request_read only with sections or include ["checks"]. '
    "No diff, code, or log.",
    "5. Run this script; it keeps the lead state.",
    "6. Judge reports: accept, start a follow-up, or ask the user.",
    # The lead cannot set a label (#604); it names the label in the brief of the worker that files the
    # issue (#634).
    "7. Set issue state. A worker sets triage labels: name the label in the brief of the worker that files "
    "the issue.",
    "8. Keep agent captures of what waits on the user when your instructions ask for them. "
    "Write gtd-inbox files with your edit tool, not the shell.",
)
# Lines that each step must keep, from the decisions of issues #448, #468, #476, #478, #493, #520,
# and #529. Each brief, the close-out brief too, tells its worker to add no GTD capture (#529).
NO_GTD_CAPTURE = '"Add no GTD capture; report what waits on the user."'
# A task starts as soon as each task that it waits for is verified; no task waits for its batch
# (#493).
START_RULE = ("Start each planned task as soon as each task that it waits for is verified, also "
              "while other workers run; do not wait for the rest of its batch.")
# A worker whose PR waits on checks ends its turn; the lead watches the PR and resumes the worker
# (#516).
PR_WAIT_WORKER = ('"When your PR waits on checks, report its URL and full head SHA, and end your '
                  'turn. Do not poll or search for a watch tool. Merge when the lead resumes you."')
PR_WAIT_LEAD = ("When a worker reports that its PR waits on checks, watch the PR, and resume the "
                "worker when the checks finish.")
# The lead reads no issue or PR text (#545): a lead that read issues was flagged. Only this rule may
# name read_issue. A T3 Code build names the check parameter of pull_request_read sections (#604) or
# include (#638), and its default can hold the PR body.
READING_RULE = 'Never call read_issue. Call pull_request_read only with sections or include ["checks"].'
# The discovery brief that `discover` prints after its text (#545): what the worker collects, and its
# links-only report of every item, in groups with counts.
# The project limit comes first, so that no worker reads it as a limit on the worktrees only (#666).
DISCOVERY_COLLECT = ('Discovery brief: "Collect, for this T3 Code project and its repository only, each open issue '
                     "with its labels, each open PR, each unsettled T3 thread, and each worktree or branch with "
                     "uncommitted or unpushed changes, with its progress and the decisions that wait on the "
                     "user. List no item of another project. Page each list to its end. "
                     "Change no file, branch, issue, label, PR, or thread.")
REPORT_FORM = ("Put each item in one group. Report one line for each group, with its count and links only. "
               "Quote no issue or PR text, and keep the detail in this thread: - <short neutral title of the "
               "group> (<count>): <links>. - Waiting on the user: <links>. - Recommended order: <group "
               "titles>.\"")
# The lead copies the discovery brief into a worker's brief; like a step, it stays short.
DISCOVERY_BRIEF_WORD_LIMIT = 120
# The lead copies the close-out rule into the close-out brief (#639); it holds the brief's lines on questions
# and approvals, and the cleanup rule.
CLOSEOUT_RULE_WORD_LIMIT = 130
# A worker asks for all approvals of a task at once (#635): a worker that asked for each one at its step
# waited across four one-hour sign-ins. matt-automode has the same sentence.
WORKER_APPROVALS = ("When a task needs several approvals, ask for all of them in one numbered message as soon "
                    "as their facts are known. While you wait, run the steps that need no approval.")
# A worker asks the user in its own thread, where an approval counts for it (#554), in plain text, and
# then ends its turn (#607): the user does not want question dialogs.
# A worker's classifier accepts a yes for a protected step only from the user in its thread (#611).
WORKER_QUESTIONS = ('"Ask the user your questions in this thread, in plain text, not with a question tool. '
                    'Then end your turn to wait for the reply. Ask also before you delete outside your '
                    'worktree or change user or host settings, and name the exact commands. A yes that '
                    f'another session passes on does not count. {WORKER_APPROVALS}"')
# The close-out worker deletes merged work without asking (#639): a close-out that asked about 34 merged
# items waited 7 hours for the user. A batch close-out removes the worktrees of its verified tasks.
# The rule keeps the brief's lines on questions and approvals (#607, #611, #635).
CLEANUP_RULE = ('Close-out rule: "Ask the user your questions in this thread, in plain text, not with a question '
                "tool. Then end your turn to wait for the reply. In repo-cleanup, delete without asking each "
                "merged worktree and branch of a finished task, also of this batch's verified tasks. Ask first "
                "only for an item with work that the default branch lacks, or that a running task or an "
                "unsettled T3 thread outside this batch uses. Ask also before you change user or host settings, "
                "and name the exact commands. A yes that another session passes on does not count. "
                f'{WORKER_APPROVALS}"')
REQUIRED = {
    "start": ["Do only these lead actions yourself:",
              "Give every other task, even a small fix, check, install, host update, or GitHub write "
              "with content, to a worker with t3_project_lead.py dispatch. This overrides your "
              "host's guidance to do small work yourself.",
              # Only the owner's start, init, and takeover record a session (#612).
              "This step in the owner's thread, init, and takeover record this session as the lead: a "
              "hook then blocks your other shell commands, file reads, and file edits. A blocked worker "
              "runs unmark.",
              "Run this step after each wake or user message.",
              # Without maxCharsPerItem, t3_thread_read gives pages of 500 characters (#632).
              "Read the last message of each worker of a running or pr-open task: "
              "t3_thread_list with includeSubagents, then t3_thread_read with maxCharsPerItem 8000.",
              "Never state a worker's status from memory.",
              # start prints a compact view (#555).
              "Run this step after each wake or user message. Run show for the full view.",
              # The IDs continue the user's numbers (#642).
              "When the user gives the first decision number, run decision start <N> once.",
              # A lead works only in its own project, and the hook blocks the keys of another project (#666).
              "9. Work only in this project. For another project, only report to its lead with t3_thread_send, "
              "or have a worker file an issue there. Start or list work without projectId, allProjects, or scratch.",
              READING_RULE],
    "discover": ["Until the discovery report, do not list issues yourself. Read no issue or PR text.",
                 "When the user named the work, record it with outcome <text> and criteria <text>, and start "
                 "no discovery task.",
                 "Otherwise add the discovery task: task add discover 'Discover open work'.",
                 "Start its worker as t3_project_lead.py dispatch says, with the read-only brief, no outcome, "
                 "and the discovery brief below, copied exactly.",
                 'In the last line of its brief, replace "with evidence and links" with "in the form '
                 'above".',
                 # The user chooses the work, or not; the lead asks no question, and keeps no item (#545).
                 # The lead copies no line of another project (#666).
                 "When it reports, run task verified discover --decisions 0 --no-pr. Copy its lines into your "
                 "report "
                 "as they are, without a line that names work of another project, "
                 "and end your turn. The list is not a waiting item: add no wait item or GTD capture for it. "
                 "Do not ask the user to choose, with a question tool or in text. When the user names the "
                 "work, run outcome <text> and criteria <text>. When discover is verified and the user named "
                 "no work, start no second discovery.",
                 "Next: t3_project_lead.py plan after the user names the work; else report.",
                 DISCOVERY_COLLECT, REPORT_FORM],
    "plan": ["Use this step when the lead state has an outcome; without one, run t3_project_lead.py "
             "discover first.",
             "A task is one brief for one worker; it can cover several issues.",
             "Give a task that needs another task's result, or edits the same files, --after "
             "that task.",
             START_RULE,
             "A batch (--batch) only decides when its workers are closed out and settled.",
             "Text is at most 200 characters",
             # init runs on the first start, before the discovery task; outcome waits for the user (#545).
             "init <slug>, once, on the first start;",
             "outcome <text>, after the user names the work;",
             # The lead has no tool that sets labels (#604).
             "A triage that needs issue text is a read-only task: its worker recommends labels; another "
             "worker sets them.",
             # A second lead state needs the user's confirmation (#544).
             "add --also only after the user confirms a second lead state",
             # A batch stops growing when its first PR merges (#560).
             "Without --batch, a work task joins a new batch once a PR of the highest batch merged.",
             # decision start sets the first number, and the lead cites the printed ID (#642, #614).
             "decision start <N>, once, when the user gives the first decision number. Give a decision "
             "without a label such as D7: the script prints its ID; cite that ID."],
    "dispatch": [START_RULE,
                 "A due line names each task that is ready to start.",
                 "Start no second worker for work that already runs",
                 'Start each worker with delegate_task, isolation "worktree", and no role.',
                 "Start every task this way, research and review tasks included. Never use your "
                 "host's native subagent tool.",
                 '"You may start your own subagents. Keep your report short, and leave the '
                 'detail in this thread."',
                 "tell the worker to start from the default branch that contains it",
                 # A follow-up worker checks the pin record of the earlier one (#623).
                 "Name each earlier pin record of the task's issue.",
                 'In the last line of its brief, replace "with evidence and links" with "in one '
                 'line, with links. Keep scientific detail in this thread and the PR".',
                 # The close-out passes each worker's worktree to retro_sessions.py (#556).
                 # The worker link is the T3 link that the lists print as a link that opens (#669).
                 "Then run task start <name> <worker link> --worktree <path> [--branch NAME]. Take the link "
                 "and the path from the delegate_task result, or from link and worktreePath of t3_thread_read.",
                 # T3 settles a worker when its turn ends, unless the thread is pinned (#668).
                 "Pin each worker with t3_thread_organize: T3 settles a worker when its turn ends, also while "
                 "it waits on the user, unless it is pinned. Its threadId is the end of its link.",
                 # A failed thread start has a record and a line (#602).
                 "When a new thread does not start, run task start-failed <name> [<thread link>], and "
                 "follow the line that it prints."],
    "brief": ["Claude Code /dev-skills:<skill>, Codex $dev-skills:<skill>, Antigravity /<skill>.",
              PROJECT_LINE,
              "When grilling must lead to implementation, end line 1 with:",
              'Line 2: "A leader runs the retrospective for this run. Do not run repo-cleanup."',
              "For a read-only task (audit, research, or check), write no line 1, keep line 2, and "
              "name what the worker must not change.",
              "Budget: name a round limit, and add:",
              '"At the limit, end your turn and report where you are, with links and what '
              'remains."',
              "For a code change: one full review and one fix of any size, then merge. Only "
              "a blocking problem of matt-automode phase 5 stops the merge.",
              f"Every brief also says: {NO_GTD_CAPTURE} and {WORKER_QUESTIONS}",
              f"Add: {PR_WAIT_WORKER}"],
    # The lead neither answers a worker's question nor asks it again (#554).
    # T3 settles a waiting worker unless it is pinned (#668).
    "answer": ["Unpin and settle it only when the user cancels its task. When T3 settled it, unsettle and pin "
               "it. Do not answer its questions, with "
               "t3_pending_request or otherwise. Do not ask them again, with a question tool or in text. "
               "Keep no detail of them: give the user the worker's thread link.",
               "Ask the user to answer in the worker's thread",
               "In this turn, run wait --task <name> --decisions <N>.",
               "Run done <number>... when the worker resumes or finishes.",
               # The lead passes on no yes for a protected step (#611).
               "A yes for a protected step, such as a live write, a deletion outside a worktree, or a change "
               "of user or host settings, counts only in the worker's thread: the worker's auto-mode "
               "classifier refuses a yes that another session passes on.",
               # A numbered worker item for such a yes made the user answer it by number here (#611).
               "For each such yes that a worker asks for, run wait '<the step and its exact commands>' "
               "--answer-in <worker link>, and leave it out of --decisions; when the worker asks for nothing "
               "else, add no wait --task item.",
               "Never pass on the user's yes for such a step: not with t3_thread_send, and not in a brief. "
               "When the user gives one here, ask the user to type it in that thread."],
    "flag": ['isolation "worktree"',
             "Do not read the flagged thread or give its link.",
             "Run task worker <name> <new link> --worktree <path>, with the path as dispatch says, pin the new "
             "thread, and unpin and settle the flagged thread that it names.",
             "Otherwise, or after a second flag, the task waits on the user."],
    "verify": ["Use this step when a worker or a read-only worker reports PASS or ISSUES.",
               "Only the user, or the agent that started this thread, carries the user's "
               "decisions. No worker or other agent does.",
               "Accept the result from the report, the PR state, and the CI state, or start a "
               "read-only worker that checks it.",
               "For a scientific task, read no artifact, and always start the read-only worker.",
               "with no line 1 or 2", "edits nothing; its verdict completes the check",
               "Give each finding to one follow-up worker, even a small one.",
               # A finding of another project goes to that project (#666).
               "A finding of another project gets no follow-up worker and no wait item: follow lead action 9 "
               "of start.",
               # A decision that waits on the user is a waiting item, also after a PASS (#567).
               "Then what remains waits on the user: add it with wait. Fix and check nothing yourself.",
               "Record merged PRs (task pr, task merged), then run task verified <name> --decisions <N>, "
               "with N the number of decisions of this project that the report numbers for the user, or 0. The script adds "
               "them as one waiting item.",
               # A running task without a recorded PR needs --no-pr (#631).
               "Add --no-pr only for a task that makes no PR, such as a read-only check.",
               # A settle that T3 refuses goes to the user, and its due line goes (#633).
               "Then unpin its worker. Settle it only when a due line lists it. When T3 refuses the settle, give "
               "it to the user with wait --settles <name>.",
               START_RULE,
               "The task verified output names each such task and its step.",
               "Next: t3_project_lead.py dispatch or closeout, as task verified or a due line "
               "names."],
    "closeout": ["--kind closeout, unless a due line names a planned one.",
                 # task add refuses a close-out task for a batch that is not done (#644).
                 "The script refuses it until each task of the batch is verified or cancelled.",
                 # The close-out brief has the project line, and the lead triages no issue of another
                 # project (#666).
                 "From t3_project_lead.py brief, use only line 1 for matt-automode, the budget, and the project "
                 "line.",
                 "An issue that the retrospective files in another project's tracker belongs to that project: "
                 "name its link, and do not triage it or count it as a decision.",
                 f"Write: {NO_GTD_CAPTURE} and the close-out rule below, copied exactly.",
                 CLEANUP_RULE,
                 "Run only the Navigation retrospective of matt-automode, once, in place of the "
                 "leader of these runs:",
                 '"After the retrospective, run repo-cleanup."',
                 "with this thread's link and the worker links, worktree paths, and merged PRs below.",
                 '"Pass each worktree path to retro_sessions.py with --worktree."',
                 "List the lead thread's tool calls other than T3, GitHub, and GTD tools and "
                 "t3_project_lead.py.",
                 "When it reports, run task verified <name> --decisions <N> --no-pr, as verify says; the "
                 "batch's verified tasks are then closed out.",
                 "Unpin and settle each worker that a due line lists with t3_thread_organize, and run task "
                 "settled <name>...; never reuse one. When T3 refuses a settle, give it to the user with "
                 "wait --settles <name>."],
    "report": ['End with the "Waiting on you" list and the "Type in that thread" section below, copied as '
               "they are.",
               # A yes for a worker's protected step waits in the worker's thread (#611).
               "For a yes that the user must type in a worker's thread, run wait <text> --answer-in <worker "
               "link>, as t3_project_lead.py answer says.",
               # Each decision for the user is on the waiting list, and nowhere else (#567).
               # A step that leaves the project is no decision for the user (#666).
               "add each new decision that only the user can make, such as an approval, access, or a step "
               "that cannot be undone: wait <text> [--link URL] [--recommend TEXT]. Work of another project "
               "is no decision for the user: after it is reported or filed there, name its link in one line, "
               "and add no wait item for it.",
               "The discovery list is not a waiting item. Write no other list of decisions for the user.",
               "Name no detail of a worker's decisions.",
               "Run done <number> when the user decides an item.",
               "When your instructions ask for agent captures, keep one for each waiting item.",
               PR_WAIT_LEAD,
               # The open PRs of one package merge one at a time, so the others do not rebase (#660).
               "Run task pr with --package <name> for a PR that raises a package version, such as a plugin's; "
               "then resume only the worker of the first PR that the merge-order due line names. The others do "
               "not rebase until their turn.",
               # Only the user settles the lead thread (#645).
               "When a due line says to run finish, first add each such decision. Run finish only when "
               "nothing waits. Leave this thread open: only the user settles the lead thread.",
               "Next: after a wake or a user message, t3_project_lead.py start.",
               "Make no promise that needs a signal from the middle of a worker's run."],
}
# Lines that tell the lead to do a worker's task itself (#520). No step may print them.
FORBIDDEN_LINES = ("Fix a small non-scientific finding yourself",
                   "You may fix a small non-scientific finding yourself",
                   "Check a non-scientific result against its criteria on the artifact")
# Text that no step may print after #530: the lead state replaced lead.md, and a
# brief names only a round limit.
RETIRED_TEXT = ("lead.md", "time limit", "in minutes", "At either limit",
                # init no longer waits for the approved outcome (#545).
                "init <slug>, once, after the user approves the outcome",
                "After the user approves the outcome, run",
                # No step asks the user to approve an outcome (#545).
                "approved outcome",
                # The lead lists the open work and asks the user no question (#545).
                "one to three outcomes", "Choose an outcome", "Propose its outcomes",
                # The include rule of #545 and the sections-only rule of #604 (#638), and the lead sets
                # no labels (#604).
                "with an include", 'only with sections ["checks"]', "Set triage labels", "and you set them",
                # A step that leaves the project is no decision for the user (#666).
                "leaves the project")
# Text that tells the lead to read issue or PR text (#545). No step may print it.
TEXT_READS = ("read_issue", "PR, issue, and CI state", "include body", "include comments", "include threads",
              "include diff", "issue body", "PR body", "read the issue", "read the PR")
# Text that makes a task wait for its batch or for a free worker (#493). No step and no skill copy
# may have it.
BATCH_WAIT_TEXT = ("start together", "slot", "worker limit", "wave")


# A settle (#645) or an archive (#659) of the lead thread, which only the user does.
SELF_SETTLE = re.compile(r"\b(?:settle|archive)(?: or (?:settle|archive))? (?:this|the lead|a lead|your|your own|its own) "
                         r"thread\b", re.IGNORECASE)


def string_constants(path: Path) -> list[str]:
    """Return the string constants of a Python file, also the literal parts of its f-strings."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)]


def words(text: str) -> str:
    """Return the text on one line, so that line wrapping does not change a match."""
    return " ".join(text.split())


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                          cwd=NO_STATE.name, check=False)


@functools.lru_cache(maxsize=None)
def step(name: str) -> str:
    result = run(name)
    if result.returncode:
        raise AssertionError(f"{name} exited {result.returncode}: {result.stderr}")
    return result.stdout


def next_line(name: str) -> str:
    """Return the text from the step's last "Next:" to its end, on one line."""
    text = step(name)
    return words(text[text.rfind("Next:"):])


def references(name: str) -> set[str]:
    """Return the steps that a step names: after t3_project_lead.py, and each step word in Next."""
    named = set(re.findall(r"t3_project_lead\.py (\w+)", step(name)))
    named |= {word for word in re.findall(r"\w+", next_line(name)) if word in STEPS}
    unknown = named - set(STEPS)
    if unknown:
        raise AssertionError(f"{name} names unknown steps {sorted(unknown)}")
    return named


def split_skill(host: str) -> tuple[dict[str, str], str]:
    path = PLUGIN_ROOT / host / "t3-project-lead" / "SKILL.md"
    _, header, body = path.read_text(encoding="utf-8").split("---\n", 2)
    fields = {}
    for line in header.splitlines():
        key, sep, value = line.partition(":")
        if sep:
            fields[key.strip()] = value.strip().strip('"')
    return fields, body


def shared_text(host: str) -> str:
    """Return a copy's body on one line, with the plugin-root path written as in the Codex copy."""
    text = words(split_skill(host)[1])
    return text.replace("${CLAUDE_PLUGIN_ROOT}", "<plugin-root>").replace(f" {PLUGIN_ROOT_LINE}", "")


class SkillCopyTests(unittest.TestCase):
    def test_each_copy_has_the_frontmatter_of_its_host(self) -> None:
        for host in HOSTS:
            with self.subTest(host=host):
                fields, _ = split_skill(host)
                self.assertEqual(set(fields), FIELDS[host])
                self.assertEqual(fields["name"], "t3-project-lead")
                self.assertEqual(fields["description"], DESCRIPTION)
                if "disable-model-invocation" in fields:
                    self.assertEqual(fields["disable-model-invocation"], "true")

    def test_codex_copy_is_user_invoked(self) -> None:
        path = PLUGIN_ROOT / "codex-skills" / "t3-project-lead" / "agents" / "openai.yaml"
        text = path.read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^policy:\n  allow_implicit_invocation: false$")
        self.assertIn("$dev-skills:t3-project-lead", text)

    def test_each_copy_and_the_glossary_state_the_project_rule(self) -> None:
        # A lead works only in its own project (#666).
        for host in HOSTS:
            with self.subTest(host=host):
                self.assertIn(PROJECT_RULE, words(split_skill(host)[1]))
        glossary = (PLUGIN_ROOT.parent / "GLOSSARY.md").read_text(encoding="utf-8")
        self.assertIn(GLOSSARY_RULE, words(glossary))

    def test_skill_starts_the_script_and_stays_short(self) -> None:
        _, body = split_skill("skills")
        self.assertIn('python3 "${CLAUDE_PLUGIN_ROOT}/scripts/t3_project_lead.py" start', body)
        self.assertLessEqual(len(body.split()), BODY_WORD_LIMIT)

    def test_skill_runs_start_at_the_start_of_every_turn(self) -> None:
        self.assertIn("At the start of every turn, after a wake or a user message, run `start` "
                      "again.", shared_text("skills"))

    def test_skill_names_the_lead_actions_and_the_hook(self) -> None:
        for host in HOSTS:
            with self.subTest(host=host):
                # Only the owner's start, init, and takeover record a session, and unmark removes a
                # record of another thread (#612).
                self.assertIn("Do only the lead actions that `start` lists, and give every other "
                              "task to a worker, even a small one. Running `init` or `takeover`, or "
                              "`start` in the thread that owns the lead state, records this session as "
                              "the lead: a dev-skills hook then blocks your other shell commands, file "
                              "reads, and file edits. When the hook blocks the work of a thread that is "
                              "not the lead, such as a worker, run `unmark` in that thread: it removes "
                              "the session's record and changes no lead state.", shared_text(host))

    def test_skill_names_start_steps(self) -> None:
        # start prints the fixed lead steps once in each thread (#603).
        for host in HOSTS:
            with self.subTest(host=host):
                self.assertIn("`start` prints its fixed lead steps once in each thread, and `start --steps` "
                              "prints them again.", shared_text(host))

    def test_skill_keeps_the_lead_thread_until_finish(self) -> None:
        # With worktreeOnDelete, T3 removes a thread's worktree, and the lead state, with the thread (#544).
        for host in HOSTS:
            with self.subTest(host=host):
                self.assertIn("Delete the lead thread only after `finish`.", shared_text(host))

    def test_skill_leaves_the_lead_thread_to_the_user(self) -> None:
        # Only the user settles or archives the lead thread (#645, #659).
        for host in HOSTS:
            with self.subTest(host=host):
                self.assertIn("Never settle or archive the lead thread, also after `finish`: only the user does.",
                              shared_text(host))

    def test_skill_tries_the_t3_fallback_before_it_stops(self) -> None:
        self.assertIn("When `delegate_task` is not a declared tool, call it the way T3's "
                      "instructions say, such as through a deferred-tool search. Do not use a "
                      "terminal fallback: the hook blocks it. When the call still fails, say that "
                      "this skill needs T3 Code, and stop.",
                      shared_text("skills"))


class StepTests(unittest.TestCase):
    def test_start_prints_the_lead_role(self) -> None:
        self.assertTrue(words(step("start")).startswith(
            f'Steps: "{SCRIPT}" Do only these lead actions yourself:'))

    def test_start_lists_the_lead_actions_before_its_other_text(self) -> None:
        text = words(step("start"))
        positions = [text.find(action) for action in LEAD_ACTIONS]
        self.assertNotIn(-1, positions, [a for a, p in zip(LEAD_ACTIONS, positions) if p < 0])
        self.assertEqual(positions, sorted(positions))
        self.assertLess(positions[-1], text.find("Give every other task"))
        self.assertLess(text.find("Give every other task"), text.find("Read the last message"))

    def test_no_step_names_lead_md_or_a_time_limit(self) -> None:
        for name in STEPS:
            for retired in RETIRED_TEXT:
                with self.subTest(step=name, text=retired):
                    self.assertNotIn(retired, words(step(name)))

    def test_no_step_or_skill_copy_waits_for_a_batch_or_a_free_worker(self) -> None:
        texts = {f"step {name}": words(step(name)) for name in STEPS}
        texts |= {f"copy {host}": words(split_skill(host)[1]) for host in HOSTS}
        for where, text in texts.items():
            for term in BATCH_WAIT_TEXT:
                with self.subTest(where=where, text=term):
                    self.assertNotIn(term, text.lower())

    def test_start_without_a_lead_state_tells_how_to_create_one(self) -> None:
        # A new lead runs init at once, then the discovery task, and asks the user only with its
        # proposals (#545).
        text = words(step("start"))
        self.assertIn("No lead state in ", text)
        self.assertIn(f'. On this first start, run: python3 "{SCRIPT}" init '
                      "<slug>, with a slug that names the project or repository. Then, unless the user named "
                      "the work, start the discovery task as t3_project_lead.py discover says, and come to "
                      "the user only with its list of open work of this project.", text)

    def test_discover_prints_a_short_discovery_brief_after_its_text(self) -> None:
        text, brief = step("discover").split("\n\n", 1)
        self.assertTrue(brief.startswith('Discovery brief:\n"'), brief)
        self.assertIn("the discovery brief below, copied exactly", words(text))
        self.assertLessEqual(len(brief.split()), DISCOVERY_BRIEF_WORD_LIMIT)

    def test_no_step_tells_the_lead_to_read_issue_or_pr_text(self) -> None:
        for name in STEPS:
            text = words(step(name)).replace(READING_RULE, "")
            for phrase in TEXT_READS:
                with self.subTest(step=name, text=phrase):
                    self.assertNotIn(phrase, text)

    def test_no_step_tells_the_lead_to_do_a_worker_task(self) -> None:
        for name in STEPS:
            for line in FORBIDDEN_LINES:
                with self.subTest(step=name, line=line):
                    self.assertNotIn(line, words(step(name)))

    def test_no_text_tells_the_lead_to_settle_its_own_thread(self) -> None:
        # A lead settled its own thread because finish and report told it to (#645). Only the user
        # settles the lead thread, so a settle of it may appear only after "never". The string constants
        # of the two scripts hold the output of each command and of the hook.
        texts = {f"step {name}": words(step(name)) for name in STEPS}
        texts |= {f"copy {host}": words(split_skill(host)[1]) for host in HOSTS}
        for script in (SCRIPT, SCRIPT.with_name("t3_project_lead_hook.py")):
            texts[script.name] = words(" ".join(string_constants(script)))
        for where, text in texts.items():
            for match in SELF_SETTLE.finditer(text):
                with self.subTest(where=where, text=match.group()):
                    self.assertTrue(text[:match.start()].lower().endswith("never "), text[:match.end()])
        self.assertNotIn("settle this thread", " ".join(texts.values()).lower())

    def test_closeout_runs_the_retrospective_before_cleanup(self) -> None:
        text = words(step("closeout"))
        self.assertLess(text.find("Run only the Navigation retrospective"),
                        text.find("run repo-cleanup"))
        self.assertLess(text.find("run repo-cleanup"), text.find("When it reports, run task verified"))

    def test_the_script_offers_exactly_the_steps_and_state_commands(self) -> None:
        choices = re.search(r"choose from (.*)\)", run("merge").stderr)
        self.assertIsNotNone(choices)
        self.assertEqual(tuple(choice.strip(" '") for choice in choices.group(1).split(",")),
                         STEPS + STATE_COMMANDS)

    def test_start_prints_the_versions_of_its_installed_copy(self) -> None:
        # A lead ran an installed copy older than its marketplace clone, and no session showed it (#576).
        def expected(root: Path) -> str:
            versions = ", ".join(
                f"{host} {json.loads((root / folder / 'plugin.json').read_text(encoding='utf-8'))['version']}"
                for host, folder in (("Claude Code", ".claude-plugin"), ("Codex", ".codex-plugin"),
                                     ("Antigravity", ".antigravity-plugin")))
            return f"Installed copy: dev-skills {versions}."

        text = step("start")
        self.assertEqual(text.split("\n\n", 2)[1].splitlines()[0], expected(PLUGIN_ROOT))
        for name in STEPS:
            if name != "start":
                with self.subTest(step=name):
                    self.assertNotIn("Installed copy:", step(name))
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "dev-skills" / "0.9.1"
            (root / "scripts").mkdir(parents=True)
            # The script imports its sibling planning_folder.py (#599), as an installed copy has it.
            for script in (SCRIPT, SCRIPT.with_name("planning_folder.py")):
                (root / "scripts" / script.name).write_bytes(script.read_bytes())
            for index, folder in enumerate((".claude-plugin", ".codex-plugin", ".antigravity-plugin")):
                (root / folder).mkdir()
                (root / folder / "plugin.json").write_text(json.dumps({"version": f"0.{index}.1"}),
                                                           encoding="utf-8")
            result = subprocess.run([sys.executable, str(root / "scripts" / SCRIPT.name), "start"],
                                    capture_output=True, text=True, cwd=NO_STATE.name, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("\n\nInstalled copy: dev-skills Claude Code 0.0.1, Codex 0.1.1, Antigravity 0.2.1.\n",
                          result.stdout)
            (root / ".codex-plugin" / "plugin.json").unlink()
            result = subprocess.run([sys.executable, str(root / "scripts" / SCRIPT.name), "start"],
                                    capture_output=True, text=True, cwd=NO_STATE.name, check=False)
            self.assertIn("Codex unknown, Antigravity 0.2.1.", result.stdout)

    def test_each_step_starts_with_the_script_path(self) -> None:
        for name in STEPS:
            with self.subTest(step=name):
                self.assertEqual(step(name).splitlines()[0], f'Steps: "{SCRIPT}"')

    def test_each_step_keeps_its_required_lines(self) -> None:
        for name, lines in REQUIRED.items():
            for line in lines:
                with self.subTest(step=name, line=line):
                    self.assertIn(line, words(step(name)))

    def test_the_close_out_brief_does_not_ask_before_each_deletion(self) -> None:
        # The close-out brief copied the worker's ask line, and the close-out asked before it deleted 34 merged
        # items (#639).
        text = words(step("closeout"))
        self.assertIn(CLEANUP_RULE, text)
        self.assertLessEqual(len(CLEANUP_RULE.split()), CLOSEOUT_RULE_WORD_LIMIT)
        for line in ("Ask also before you delete outside your worktree", 'the line "Ask the user your questions'):
            with self.subTest(line=line):
                self.assertNotIn(line, text)

    def test_each_step_is_short(self) -> None:
        # The step text ends at the first empty line; the lead state view follows it.
        for name in STEPS:
            with self.subTest(step=name):
                self.assertLessEqual(len(step(name).split("\n\n")[0].split()), STEP_WORD_LIMIT)

    def test_each_step_ends_with_real_next_steps(self) -> None:
        for name in STEPS:
            with self.subTest(step=name):
                self.assertRegex(next_line(name), r"^Next: .*\bt3_project_lead\.py \w+")
                references(name)

    def test_every_step_can_be_reached_from_start(self) -> None:
        reached, queue = {"start"}, ["start"]
        while queue:
            for name in references(queue.pop()) - reached:
                reached.add(name)
                queue.append(name)
        self.assertEqual(reached, set(STEPS))

    def test_flag_retries_on_the_claude_fallback_model(self) -> None:
        fallback = ALLOWED_MODELS["claude"]["fallback"]
        self.assertIn(f"a Claude Code provider on {fallback}", words(step("flag")))
        for name in STEPS:
            with self.subTest(step=name):
                self.assertLessEqual(set(MODEL_ID.findall(step(name))), {fallback})

    def test_worker_lines_match_matt_automode(self) -> None:
        brief = words(step("brief"))
        self.assertIn('Line 2: "A leader runs the retrospective for this run.', brief)
        self.assertIn('"When the user approves the design here, continue in this thread with the '
                      'matt-automode skill of dev-skills."', brief)
        self.assertIn("Run only the Navigation retrospective of matt-automode", words(step("closeout")))
        self.assertNotIn("focused check", brief)
        for host in HOSTS:
            with self.subTest(host=host):
                text = (PLUGIN_ROOT / host / "matt-automode" / "SKILL.md").read_text(encoding="utf-8")
                self.assertIn("When the task says that a leader runs the retrospective for this run",
                              words(text))
                self.assertRegex(text, r"(?m)^## Navigation retrospective$")
                # The worker brief and matt-automode ask for the approvals of a task at once (#635).
                self.assertIn(WORKER_APPROVALS, words(text))

    def test_the_brief_names_no_question_tool_for_the_worker(self) -> None:
        # Workers asked with the question tool, 28 and 16 calls, and the user did not want it (#607).
        brief = words(step("brief"))
        self.assertNotIn("AskUserQuestion", brief)
        self.assertNotIn("host's question tool", brief)

    def test_an_unknown_step_fails(self) -> None:
        result = run("merge")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid choice", result.stderr)


class CloseoutPathTests(unittest.TestCase):
    """The close-out lines name each worker's worktree for retro_sessions.py --worktree (#556)."""

    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        # A folder outside every Git work tree holds the lead state.
        self.folder = Path(temp.name).resolve()
        self.env = dict(os.environ, T3CODE_THREAD_ID="thread-lead", GIT_CEILING_DIRECTORIES=str(self.folder.parent))

    def lead(self, *args: str) -> str:
        result = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                                cwd=self.folder, env=self.env, check=False)
        self.assertEqual(result.returncode, 0, f"{args}: {result.stderr}")
        return result.stdout

    def batch_lines(self) -> list[str]:
        lines = self.lead("closeout").splitlines()
        return lines[lines.index("Batch 1:"):]

    def test_closeout_names_each_worktree_also_of_a_replaced_worker(self) -> None:
        self.lead("init", "demo")
        for name in ("a", "b"):
            self.lead("task", "add", name, f"Task {name}")
        self.lead("task", "start", "a", "t3-thread://v2/env/a", "--worktree", "/wt/t3-a")
        self.lead("task", "start", "b", "t3-thread://v2/env/b1", "--worktree", "/wt/t3 b1")
        # The flag step replaces b's worker; the path of the replaced worker stays (#556).
        self.lead("task", "worker", "b", "t3-thread://v2/env/b2", "--worktree", "/wt/t3-b2")
        for name, number in (("a", "5"), ("b", "6")):
            self.lead("task", "pr", name, number)
            self.lead("task", "merged", name, number, "abcdef1")
        self.lead("task", "verified", "a", "b", "--decisions", "0")
        lines = self.batch_lines()
        self.assertEqual(lines[:4], ["Batch 1:", "Workers: t3-thread://v2/env/a t3-thread://v2/env/b2", "Worktrees: /wt/t3-a '/wt/t3 b1' /wt/t3-b2",
                                     "Merged PRs in merge order: #5, #6"])
        # The close-out worker's own worktree is not in its brief.
        self.lead("task", "add", "close-1", "Task close-1", "--kind", "closeout")
        self.lead("task", "start", "close-1", "t3-thread://v2/env/c", "--worktree", "/wt/t3-c")
        self.assertNotIn("/wt/t3-c", self.lead("closeout"))

    def test_a_state_without_worktree_paths_still_prints_its_close_out(self) -> None:
        self.lead("init", "demo")
        self.lead("task", "add", "a", "Task a")
        self.lead("task", "start", "a", "t3-thread://v2/env/a")
        self.lead("task", "pr", "a", "5")
        self.lead("task", "merged", "a", "5", "abcdef1")
        self.lead("task", "verified", "a", "--decisions", "0")
        # A lead state from before #556 has no "worktrees" field.
        (state_file,) = self.folder.glob(".scratch/*-lead-demo/state.json")
        state = json.loads(state_file.read_text(encoding="utf-8"))
        for task in state["tasks"]:
            del task["worktrees"]
        state_file.write_text(json.dumps(state), encoding="utf-8")
        self.assertEqual(self.batch_lines()[:4], ["Batch 1:", "Workers: t3-thread://v2/env/a", "Worktrees: (none recorded)",
                                                  "Merged PRs in merge order: #5"])
        self.assertIn("Lead state: demo", self.lead("start"))


if __name__ == "__main__":
    unittest.main()
