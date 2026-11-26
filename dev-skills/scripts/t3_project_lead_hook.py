#!/usr/bin/env python3
"""Hold a t3-project-lead session to lead actions (issue #520).

Claude Code, Codex, and Antigravity run this hook before a tool call
(PreToolUse), and Claude Code and Codex also run it on each user message
(UserPromptSubmit). It reads the host's JSON payload on stdin. Run it as
`python3 t3_project_lead_hook.py --host claude|codex|antigravity`.

- Record: when a shell call runs `python3 <path>/t3_project_lead.py start`,
  and the script is this hook's sibling or a copy outside every Git work
  tree, the hook writes an empty file named by the session ID to the state
  folder. The call can be one simple command, or a command list in which
  one simple command is exactly these three words (issue #574), as in
  `S=<script>; python3 $S start 2>&1 | head -80`. An assignment of an
  earlier command in the list sets `$S`. A copy inside a Git work tree,
  such as a developer's worktree, records nothing, and so do `start` with
  more words and a script path that the hook cannot resolve. Each new
  record deletes records older than 30 days. Issue #612, the next bullet,
  limits which `start` records and adds `init` and `takeover`.
- Lead threads only (issue #612): a worker ran `start`, and the hook blocked
  its work. So `start` records a session only when `T3CODE_THREAD_ID` in the
  hook's environment is the owner of the lead state in the Git working tree
  of the call's cwd; a working tree without a lead state records nothing.
  `init <slug>` with an optional `--also`, and `takeover`, record a session
  in any thread, in the same command forms as `start`. The check fails closed: when a lead state may be there and
  the hook cannot tell its owner, as without `T3CODE_THREAD_ID` (a Codex
  hook may lack it) or an absolute cwd, or with a lead state that it cannot
  read or that has no owner, `start` records the session.
- Unmark (issue #612): in a recorded session, `python3 <script> unmark`
  removes the record before the script runs, only when the hook can tell
  that the thread is not the lead: `unmark_refusal` of the step script finds
  a lead state in the worktrees of the repository of the session's cwd, and
  another thread owns each one. Otherwise the hook blocks the call with the
  reason and keeps the record, also when no lead state is left, as after
  `finish` (only the user settles a lead thread), and when a Codex `workdir`
  or an Antigravity `Cwd` names another folder.
- Other sessions: without a record, the hook exits 0 with no output, even on
  an error.
- Gate (issue #530): in a recorded session, the hook allows one simple shell
  command `python3 <script> <subcommand> [arguments...]`, where the script
  passes the record check, and file reads in T3 Code's attachments folder,
  also through one cat, head, tail, wc, ls, grep, or `sed -n` command. It
  blocks every other shell command, every other file read, every file
  edit, and native subagents, so only the script reads or writes the lead
  state. Other tools pass, and so do MCP tools, except the reads of issue
  and PR text, the questions, the thread reads, the settles of a lead
  thread, and the calls of another project below. A blocked call exits 2
  with the reason on stderr. A call that the hook cannot check also
  exits 2.
- Issue and PR text (issue #545): a lead that read open issues itself was
  flagged by the model provider's safeguards, and a flag stops the whole lead
  thread. So in a recorded session, the hook blocks two T3 Code MCP tools:
  `read_issue`, which always returns the body and the comments, and
  `pull_request_read` unless its check parameter is exactly `["checks"]`.
  T3 Code builds name that parameter `sections` (issue #604) or `include`
  (issue #638); when a call has both, each must be `["checks"]`. A call
  with neither blocks, because a default, such as `summary` and `checks`,
  can return the PR body. Any other value blocks. The hook cannot tell
  which name the host's build uses. Claude Code names the tools
  `mcp__t3-code__<tool>`. Codex changes `-` to `_`, as in
  `mcp__t3_code__<tool>`, puts a 12-character environment hash after
  `mcp__` for a server of one environment, as in
  `mcp__<hash>__t3_code__<tool>`, and its sessions also use the server key
  `t3-code-direct`. A read-only worker reads the text instead. Antigravity
  has no known hook payload for MCP calls, so there only the step text holds
  the rule.
- Questions (issue #554): a new-project lead asked the user to pick an
  outcome with AskUserQuestion, and a lead read a worker's question with
  `t3_pending_request` and asked it again with AskUserQuestion. The question
  changed in meaning, and the worker removed a table that the user needed.
  So in a recorded session, the hook blocks the question tools
  `AskUserQuestion` (Claude Code) and `request_user_input` and
  `request_user_input_async` (Codex): the lead lists in plain text and ends
  its turn. It also blocks `t3_pending_request` unless its `action` is `list`
  or `read`, so the lead answers no worker's question; the block names the
  `answer` step. Codex 0.170.0 runs PreToolUse for `request_user_input` in
  every mode (`codex-rs/core/src/tools/registry.rs`). Antigravity has no known
  hook payload for its question tool, so there only the step text holds the
  rule.
- Thread reads (issue #632): without `maxCharsPerItem`, `t3_thread_read`
  gives each item in pages of 500 characters, and a lead spent 8 calls on
  one worker report and stopped before its end. So in a recorded session, the hook blocks
  `t3_thread_read` unless `maxCharsPerItem` is a positive integer; the
  block names 8000. In Antigravity, only the step text holds the rule.
- Lead thread (issue #645): a lead settled its own thread because the
  `finish` output told it to, and only the user settles a lead thread. So
  in a recorded session, the hook blocks `t3_thread_organize` with `action`
  `settle` when the call names no `threadId`, which settles the calling
  thread, or names the calling thread (`T3CODE_THREAD_ID` in the hook's
  environment) or the owner of the lead state in the Git working tree of
  the call's `cwd`. A settle that names another thread, such as a worker's,
  passes, and so do the other actions. The check fails closed: a tool input
  that is not an object, an action that is not a string, and a settle that
  names a thread when the hook knows no lead thread, the call has no
  absolute `cwd`, or the lead state cannot be read block. The block's first
  line says that only the user settles a lead thread, in place of the line
  that gives the call to a worker. In Antigravity, only the step text holds
  the rule.
- Project (issue #666): a lead offered the work of another project to the
  user. A lead works only in its own project. So in a recorded session, the
  hook blocks the T3 Code MCP calls that aim at another project:
  `delegate_task` with `projectId` in `target`, `create_threads` with
  `projectId` in the `target` of a thread, `t3_thread_launch` with
  `projectId` or a `scratch` other than false, `t3_thread_list` with
  `projectId` or an `allProjects` other than false, and `list_issues` with
  `projectId`. A call that names no project uses the project of the calling
  thread, and passes. The hook cannot learn the project ID of the lead: no
  environment variable names it, and the lead state records none. So the
  check fails closed: a call that names a project blocks, also the lead's
  own project, and so do an input, a `target`, or a thread that is not an
  object, and `threads` that is not a list. The check reads no
  `T3CODE_THREAD_ID`, so a Codex hook without it acts the same, as the
  record rule of #612 and the settle check of #645 fail closed. The hook
  does not check `t3_thread_send`, `t3_thread_search`, or `create_issue`: a
  report to another project's lead and an issue in its tracker are allowed.
  The Claude Code and Codex matchers select the five checked tools. The
  block's first line says that a lead works only in its own project. In
  Antigravity, only the step text holds the rule.
- GTD (issue #531): the gate also allows the calls of a gtd-inbox capture:
  reads of the GTD binding and of an installed Productivity Skills plugin
  outside every Git work tree; one simple command `uv run --no-project
  [uv options] python <plugin>/scripts/gtd_sql.py [arguments...]`; and a
  whole-file write, with the file edit tool, of a `.json` file at an
  absolute path outside every Git work tree and outside the binding's
  folder, whose content is a GTD binding or a GTD request. The written file
  must be new or hold a GTD binding or request already.
- Reads of a lead's own files (issue #621): the gate also allows reads of
  the tool outputs that Claude Code saved for this session, in
  `<folder>/<session>/tool-results/` next to the transcript
  `<folder>/<session>.jsonl` that the payload names, and of a `.json` file
  outside every Git work tree that holds a GTD binding or request, by the
  content check of the write rule. A payload without such a transcript path, as from Codex
  and Antigravity, allows no saved output.
- Reminder: on a user message in a recorded session, Claude Code and Codex
  get additional context that tells the lead to run `start` first, and a
  thread that is not the lead to run `unmark`.

`T3_PROJECT_LEAD_STATE_DIR` sets the state folder; the default is
`${XDG_STATE_HOME:-$HOME/.local/state}/dev-skills/t3-project-lead/sessions`.
"""

from __future__ import annotations

import os
import sys

SCRIPT_NAME = "t3_project_lead.py"
ANTIGRAVITY = "antigravity"
SESSION_CHARACTERS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-")
RECORD_DAYS = 30
BLOCK_LINE = ("BLOCKED: t3-project-lead: This is not a lead action. Give it to a worker with "
              "`t3_project_lead.py dispatch`.")
# The first line of a block that is not BLOCK_LINE: no worker may settle a lead thread (#645) or do
# the work of another project (#666) either.
FIRST_LINES = {"settle": "BLOCKED: t3-project-lead: Only the user settles a lead thread.",
               "unmark": "BLOCKED: t3-project-lead: The hook keeps the lead record of this session.",
               "project": "BLOCKED: t3-project-lead: A lead works only in its own project."}
ALLOWED = {
    "project": ("Leave out projectId, allProjects, and scratch: the call then uses this project. For work of "
                "another project, report it to that project's lead with t3_thread_send, or have a worker file "
                "an issue there. Do not list or offer that work."),
    "shell": ('Allowed commands: python3 "{script}" <step or command> [arguments]; uv run '
              "--no-project --python '>=3.11' python <installed Productivity Skills>/scripts/gtd_sql.py "
              "[arguments]; one cat, head, tail, wc, ls, grep, or sed -n of the files that the read tools "
              "may read. Each is one simple command: no "
              "pipe, redirect, list, or substitution. Write a gtd-inbox file with the file edit tool. "
              "Quote text with single quotes."),
    "read": ("Allowed reads: T3 attachments, the GTD binding, gtd-inbox .json files outside every Git "
             "work tree, the installed Productivity Skills plugin, and the tool outputs that Claude Code "
             "saved for this session. Print the lead state with t3_project_lead.py show."),
    "edit": ("No file edits, except a whole-file write of a gtd-inbox .json file (a GTD binding copy "
             "or request, new or replacing one) at an absolute path outside every Git work tree. "
             "Change the lead state with t3_project_lead.py commands."),
    "agent": "Start a worker with delegate_task, as t3_project_lead.py dispatch says.",
    "question": ("Ask no question with a question tool. List in plain text and end your turn. Write a "
                 "decision that only the user can make in plain text, with your recommendation. Never ask "
                 "the user to choose which task to do. For a worker's question, run t3_project_lead.py "
                 "answer."),
    "respond": ("Do not answer a worker's question: run t3_project_lead.py answer, and give the user the "
                "worker's thread link. t3_pending_request may only list or read."),
    "text": ("Read no issue or PR text: a lead that read issues was flagged. Allowed: list_issues, "
             'pull_request_list, and pull_request_read with sections or include, as your tool names it, '
             'set to ["checks"]. Give a triage that needs issue text to a read-only worker.'),
    "thread": ("Call t3_thread_read with maxCharsPerItem, such as 8000. Without it, a worker report "
               "comes in pages of 500 characters."),
    "settle": ("Leave the lead thread open, and give its settle to no worker. To settle a worker's thread, "
               "name its threadId. When the hook blocks the settle of a worker's thread, give it to the "
               "user with t3_project_lead.py wait --settles <task>."),
    "unmark": "It removes the record only when it can tell that this thread is not the lead: {reason}.",
    "error": "The hook could not check this call ({error}). Allowed: the lead actions that "
             "t3_project_lead.py start lists.",
}

# Tool names of each kind, for all three hosts.
SHELL_TOOLS = {"Bash": "command", "Monitor": "command", "exec_command": "cmd", "shell": "command",
               "run_command": "CommandLine"}
READ_TOOLS = frozenset({"Read", "Grep", "Glob", "read_file", "view_file", "view_file_outline",
                        "view_code_item", "list_dir", "grep_search", "find_by_name", "codebase_search"})
EDIT_TOOLS = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit", "write_file", "edit_file",
                        "write_to_file", "replace_file_content", "multi_replace_file_content"})
AGENT_TOOLS = frozenset({"Agent", "Task", "spawn_agent", "invoke_subagent"})
# The question tools of Claude Code and Codex (#554), and the t3_pending_request actions that answer
# nothing.
# The T3 Code tools that can aim a lead at another project, and the keys that name a project or leave
# it (#666). A call without these keys uses the project of the calling thread.
PROJECT_TOOLS = frozenset({"delegate_task", "create_threads", "t3_thread_launch", "t3_thread_list",
                           "list_issues"})
PROJECT_KEY = "projectId"
ALL_PROJECT_KEYS = ("allProjects", "scratch")
QUESTION_TOOLS = frozenset({"AskUserQuestion", "request_user_input", "request_user_input_async"})
PENDING_READS = frozenset({"list", "read"})
# T3 Code MCP servers, with "-" read as "_" (issue #545): Claude Code and Codex name a tool
# mcp__<server>__<tool>, and Codex can put an environment segment after mcp__. The check
# parameters of pull_request_read in T3 Code builds, sections (#604) and include (#638), and the one
# value with which the tool returns no PR text. A list, because JSON gives one.
T3_SERVERS = frozenset({"t3_code", "t3_code_direct"})
PR_CHECK_PARAMETERS = ("sections", "include")
PR_CHECKS_ONLY = ["checks"]
# Path arguments: Claude Code first, then Antigravity.
PATH_KEYS = ("file_path", "notebook_path", "path", "AbsolutePath", "Path", "File", "FilePath",
             "TargetFile", "DirectoryPath", "SearchPath", "SearchDirectory")
WRAPPER_SHELLS = frozenset({"bash", "sh", "zsh"})
# Command lists that start_run does not read (issue #574): a group, a reserved word of a
# compound command, and a builtin that changes variables or runs other code. After a word
# of LIST_ENDS, no later command runs.
UNREAD_COMMANDS = frozenset({"{", "}", "!", "if", "then", "elif", "else", "fi", "case", "esac", "for",
                             "select", "while", "until", "do", "done", "function", "time", "coproc",
                             "[[", "unset", "declare", "typeset", "local", "readonly", "read",
                             "readarray", "mapfile", "printf", "getopts", "eval", "source", ".",
                             "builtin", "command", "alias", "set", "shopt", "trap", "enable"})
LIST_ENDS = frozenset({"exit", "exec", "return", "logout"})
# gtd-inbox (issue #531): the renderer, its contract, the uv options that
# may come with the required --no-project, and the whole-file write tools with
# their path and content arguments. The contract is
# productivity-skills/references/gtd-cloud.md; the GTD JSON checks below
# follow the validation of productivity-skills/scripts/gtd_sql.py.
GTD_SCRIPT = "gtd_sql.py"
GTD_CONTRACT = "gtd-cloud.md"
UV_OPTIONS = frozenset({"--no-cache", "--offline", "-q", "--quiet"})
WRITE_TOOLS = {"Write": ("file_path", "content"), "write_file": ("Path", "Content"),
               "write_to_file": ("TargetFile", "CodeContent")}


class Blocked(Exception):
    """The call is not a lead action. The argument names the kind of call."""


def host_argument(argv):
    for index, argument in enumerate(argv[:-1]):
        if argument == "--host":
            return argv[index + 1]
    return "claude"


def session_id(payload, host):
    """Return the session ID of `payload`, or None when it has no valid one."""
    value = payload.get("conversationId" if host == ANTIGRAVITY else "session_id")
    if (not isinstance(value, str) or not value or value.strip(".") == ""
            or not SESSION_CHARACTERS.issuperset(value)):
        return None
    return value


def state_dir():
    folder = os.environ.get("T3_PROJECT_LEAD_STATE_DIR")
    if folder:
        return folder
    base = os.environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state")
    return os.path.join(base, "dev-skills", "t3-project-lead", "sessions")


def sibling_script():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), SCRIPT_NAME)


def main(argv):
    host = host_argument(argv)
    try:
        raw = sys.stdin.read()
        folder = state_dir()
        try:
            names = os.listdir(folder)
        except OSError:
            names = []
        # Fast path, with no JSON import: when no record name is in the
        # payload, the session has no record, and only a start run matters.
        if SCRIPT_NAME not in raw and not any(name in raw for name in names):
            return 0
        import json

        payload = json.loads(raw)
        session = session_id(payload, host) if isinstance(payload, dict) else None
        if session is None:
            return 0
        recorded = os.path.isfile(os.path.join(folder, session))
        if not recorded and SCRIPT_NAME not in raw:
            return 0
    except Exception:
        return 0
    if not recorded:
        try:
            start_run(payload, host, folder, session)
        except Exception:
            pass
        return 0
    event = payload.get("hookEventName" if host == ANTIGRAVITY else "hook_event_name")
    if event == "UserPromptSubmit":
        if host != ANTIGRAVITY:
            reminder = ("This is a t3-project-lead session. Before anything else in this turn, run: "
                        f'python3 "{sibling_script()}" start. When this thread is not the lead, as in a '
                        f'worker, run python3 "{sibling_script()}" unmark instead.')
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                                     "additionalContext": reminder}}))
        return 0
    if event not in (None, "PreToolUse"):
        return 0
    try:
        gate(payload, host, folder, session)
    except Blocked as blocked:
        kind, reason = blocked.args[0], blocked.args[1] if len(blocked.args) > 1 else ""
        return block(ALLOWED[kind].format(script=sibling_script(), reason=reason),
                     FIRST_LINES.get(kind, BLOCK_LINE))
    except Exception as error:
        return block(ALLOWED["error"].format(error=f"{type(error).__name__}: {error}"))
    return 0


def block(allowed_line, first_line=BLOCK_LINE):
    print(first_line, file=sys.stderr)
    print(allowed_line, file=sys.stderr)
    return 2


# Tool calls.

def tool_call(payload, host):
    """Return the tool name and input of a PreToolUse payload."""
    if host == ANTIGRAVITY:
        call = payload["toolCall"]
        name, arguments = call["name"], call["args"]
    else:
        name, arguments = payload["tool_name"], payload.get("tool_input")
    if not isinstance(name, str):
        raise ValueError("the tool name is not a string")
    return name, arguments


def payload_cwd(payload):
    cwd = payload.get("cwd")
    return cwd if isinstance(cwd, str) and os.path.isabs(cwd) else None


def start_run(payload, host, folder, session):
    """Write the record when `payload` runs a step of a qualifying script that records a lead (#612):
    `init`, `takeover`, or a `start` of the thread that owns the lead state (owns_lead).

    The step can also be one simple command of a command list (issue #574),
    as in `S=<script>; python3 $S start 2>&1 | head -80`.
    """
    event = payload.get("hookEventName" if host == ANTIGRAVITY else "hook_event_name")
    if event not in (None, "PreToolUse"):
        return
    name, arguments = tool_call(payload, host)
    if name not in SHELL_TOOLS or not isinstance(arguments, dict):
        return
    for words, cwd in start_commands(arguments, SHELL_TOOLS[name], payload_cwd(payload)):
        if (len(words) >= 3 and None not in words and words[0] in ("python3", "python")
                and is_record_step(words[2:]) and step_script(words, cwd)
                and (words[2] != "start" or owns_lead(cwd))):
            write_record(folder, session)
            return


def is_record_step(words):
    """Return whether `words`, a step and its arguments, can record a lead (#612): `start`, `takeover`, or
    `init <slug>` with an optional `--also`."""
    step, rest = words[0], words[1:]
    if step == "init":
        slugs = [word for word in rest if word != "--also"]
        return len(rest) <= 2 and len(slugs) == 1 and not slugs[0].startswith("-")
    return step in ("start", "takeover") and not rest


def owns_lead(cwd):
    """Return whether a `start` in `cwd` records the session (#612): T3CODE_THREAD_ID of the hook owns the
    lead state in the Git working tree of `cwd`.

    A working tree without a lead state gives False, so a worker in its own worktree is no lead. The
    check fails closed: when a lead state may be there and the hook cannot tell its owner, as without an
    absolute cwd or T3CODE_THREAD_ID, or with a lead state that it cannot read or that has no owner, the
    result is True.
    """
    if cwd is None:
        return True
    try:
        lead = step_module()
        folder = lead.find_lead(tree_top(cwd))
        if folder is None:
            return False
        owner, thread = lead.load(folder).get("owner"), lead.current_thread()
    except Exception:
        return True
    if not isinstance(owner, str) or not owner.strip() or not thread:
        return True
    return owner.strip() == thread


def check_unmark(cwd, session_cwd, folder, session):
    """Remove the record of `session` when this thread is not the lead (#612); raise Blocked otherwise.

    unmark_refusal of the step script decides, with T3CODE_THREAD_ID of the hook's environment. The record
    covers the whole session, so the call must run in the session's cwd: a Codex `workdir` or an
    Antigravity `Cwd` could name a folder of another repository. The check fails closed: without an
    absolute cwd, in another folder, or when the check fails, the record stays.
    """
    if cwd is None or session_cwd is None:
        raise Blocked("unmark", "the call has no absolute cwd")
    if os.path.realpath(cwd) != os.path.realpath(session_cwd):
        raise Blocked("unmark", "the call names a folder other than the session's cwd")
    try:
        lead = step_module()
        reason = lead.unmark_refusal(tree_top(cwd), lead.current_thread())
    except Exception as error:
        reason = f"the hook could not check the lead states ({type(error).__name__}: {error})"
    if reason is not None:
        raise Blocked("unmark", reason)
    try:
        os.unlink(os.path.join(folder, session))
    except FileNotFoundError:
        pass


def step_module():
    """Import and return the step script, this hook's sibling, which finds and reads the lead state."""
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import t3_project_lead

    return t3_project_lead


def tree_top(cwd):
    """Return the top of the Git working tree of `cwd`, or `cwd` outside every work tree; raise an error
    when Git fails otherwise."""
    result = git_run(cwd, "rev-parse", "--show-toplevel")
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    if "not a git repository" in result.stderr:
        return cwd
    raise OSError(result.stderr.strip() or f"git exited {result.returncode}")


def gate(payload, host, folder, session):
    """Return when the call is a lead action; raise Blocked otherwise."""
    name, arguments = tool_call(payload, host)
    if name in AGENT_TOOLS or name.endswith("spawn_agent"):
        raise Blocked("agent")
    if name in QUESTION_TOOLS:
        raise Blocked("question")
    tool = t3_tool(name)
    cwd = payload_cwd(payload)
    saved_outputs = tool_results(payload, host, session)
    check_text_read(tool, arguments)
    check_pending_request(tool, arguments)
    check_thread_read(tool, arguments)
    check_settle(tool, arguments, cwd)
    check_project(tool, arguments)
    if name == "apply_patch" or name in EDIT_TOOLS:
        # Only t3_project_lead.py writes the lead state; the lead writes only gtd-inbox files.
        check_gtd_write(name, arguments, cwd)
        return
    if name in SHELL_TOOLS:
        kind = "shell"
    elif name in READ_TOOLS:
        kind = "read"
    else:
        return  # Other MCP tools and all other tools pass.
    if not isinstance(arguments, dict):
        raise Blocked(kind)
    if kind == "shell":
        check_shell(arguments, SHELL_TOOLS[name], cwd, folder, session, saved_outputs)
        return
    if name == "Glob":
        pattern = arguments.get("pattern")
        if not isinstance(pattern, str) or pattern.startswith(("/", "~")) or ".." in pattern.split("/"):
            raise Blocked(kind)
    default = cwd if name in ("Grep", "Glob") else None
    check_reads(tool_paths(arguments, default), cwd, saved_outputs)


def tool_results(payload, host, session):
    """Return the real path of the folder of tool outputs that Claude Code saved for this session, or None
    (#621).

    Claude Code keeps a session's transcript at <folder>/<session>.jsonl and saves a tool output over its
    inline limit in <folder>/<session>/tool-results/. A payload without such a transcript path, as from
    Codex or Antigravity, gives None.
    """
    path = payload.get("transcript_path")
    if (host == ANTIGRAVITY or not isinstance(path, str) or not os.path.isabs(path)
            or os.path.basename(path) != session + ".jsonl"):
        return None
    return os.path.realpath(os.path.join(os.path.dirname(path), session, "tool-results"))


def t3_tool(name):
    """Return the tool name of a T3 Code MCP call, such as `read_issue`, or None.

    The name is mcp__[<segments>__]<server>__<tool>, where Codex can add an
    environment segment before the server.
    """
    parts = name.split("__")
    if len(parts) < 3 or parts[0] != "mcp":
        return None
    return parts[-1] if parts[-2].replace("-", "_") in T3_SERVERS else None


def check_text_read(tool, arguments):
    """Raise Blocked when a T3 Code MCP call can return issue or PR text (issue #545).

    `read_issue` always returns the body and the comments. `pull_request_read`
    passes only when one of its check parameters, `sections` (#604) or
    `include` (#638), is present, and each present one equals PR_CHECKS_ONLY.
    Without either, the tool returns a default that can hold the PR body; two
    different values and any other input fail closed.
    """
    if tool == "read_issue":
        raise Blocked("text")
    if tool != "pull_request_read":
        return
    if not isinstance(arguments, dict):
        raise Blocked("text")
    values = [arguments[key] for key in PR_CHECK_PARAMETERS if key in arguments]
    if not values or any(value != PR_CHECKS_ONLY for value in values):
        raise Blocked("text")


def check_pending_request(tool, arguments):
    """Raise Blocked when a `t3_pending_request` call can answer a worker's question (#554).

    Only the actions `list` and `read` pass; `respond`, a missing or unknown
    action, and an input that is not an object fail closed.
    """
    if tool != "t3_pending_request":
        return
    action = arguments.get("action") if isinstance(arguments, dict) else None
    if not isinstance(action, str) or action not in PENDING_READS:
        raise Blocked("respond")


def check_thread_read(tool, arguments):
    """Raise Blocked when a `t3_thread_read` call has no page size (#632).

    Without `maxCharsPerItem`, the tool gives each item in pages of 500
    characters, so a lead spent 8 calls on one worker report and stopped
    before its end. Only a positive integer passes; a missing or other
    value, and an input that is not an object, fail closed.
    """
    if tool != "t3_thread_read":
        return
    size = arguments.get("maxCharsPerItem") if isinstance(arguments, dict) else None
    if type(size) is not int or size < 1:
        raise Blocked("thread")


def check_settle(tool, arguments, cwd):
    """Raise Blocked when a `t3_thread_organize` call is a settle of a lead thread (#645).

    Only the user settles a lead thread. A settle with no `threadId` settles
    the calling thread, which is a lead thread in a recorded session. A
    settle that names a thread of lead_threads also blocks. A settle that
    names another thread, such as a worker's, passes, and so do the other
    actions. An input that is not an object, an action that is not a
    string, and a settle that names a thread when the hook knows no lead
    thread or cannot read the lead state fail closed.
    """
    if tool != "t3_thread_organize":
        return
    action = arguments.get("action") if isinstance(arguments, dict) else None
    if not isinstance(action, str):
        raise Blocked("settle")
    if action.strip().lower() != "settle":
        return
    thread = arguments.get("threadId")
    if not isinstance(thread, str) or not thread.strip():
        raise Blocked("settle")
    try:
        leads = lead_threads(cwd)
    except Exception:
        raise Blocked("settle") from None
    if not leads or thread.strip() in leads:
        raise Blocked("settle")


def check_project(tool, arguments):
    """Raise Blocked when a T3 Code MCP call aims a lead at another project (#666).

    A call that names no project uses the project of the calling thread. The
    hook cannot learn the project ID of the lead, so a `projectId` key blocks
    in the input, in the `target` of `delegate_task`, and in each thread of
    `create_threads` and its `target`. An `allProjects` or a `scratch` other
    than false blocks. An input, a `target`, or a thread that is not an
    object, and `threads` that is not a list, fail closed.
    """
    if tool not in PROJECT_TOOLS:
        return
    if not isinstance(arguments, dict):
        raise Blocked("project")
    scopes = [arguments]
    if tool == "create_threads":
        threads = arguments.get("threads")
        if not isinstance(threads, list):
            raise Blocked("project")
        scopes += threads
    for scope in list(scopes):
        if isinstance(scope, dict) and "target" in scope:
            scopes.append(scope["target"])
    for scope in scopes:
        if (not isinstance(scope, dict) or PROJECT_KEY in scope
                or any(key in scope and scope[key] is not False for key in ALL_PROJECT_KEYS)):
            raise Blocked("project")


def lead_threads(cwd):
    """Return the IDs of the lead threads (#645), and raise an error when the lead state cannot be read.

    They are the calling thread, from `T3CODE_THREAD_ID`, and the owner of
    the lead state in the Git working tree of `cwd`, or in `cwd` outside a
    work tree. The step script, this hook's sibling, finds and reads the
    lead state.
    """
    if cwd is None:
        raise ValueError("the call has no absolute cwd")
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import t3_project_lead

    threads = {t3_project_lead.current_thread()}
    folder = t3_project_lead.find_lead(git(cwd, "rev-parse", "--show-toplevel") or cwd)
    if folder is not None:
        owner = t3_project_lead.load(folder).get("owner")
        threads.add(owner.strip() if isinstance(owner, str) else "")
    threads.discard("")
    return threads


def tool_paths(arguments, default):
    """Return the path arguments of a file tool call."""
    paths = []
    for key in PATH_KEYS:
        value = arguments.get(key)
        if value is not None:
            paths.append(value)
    if not paths and default is not None:
        paths.append(default)
    return paths


def check_reads(paths, cwd, saved_outputs):
    """Raise Blocked unless `paths` is not empty and each path is in T3
    attachments, is the GTD binding, is in an installed Productivity Skills plugin,
    is in `saved_outputs`, the folder of this session's saved tool outputs or None
    (#621), or is a gtd-inbox file (#621)."""
    if not paths:
        raise Blocked("read")
    for path in paths:
        resolved = resolve(path, cwd)
        if resolved is None or not (in_attachments(resolved) or resolved == gtd_binding()
                                    or (saved_outputs is not None and inside(resolved, saved_outputs))
                                    or productivity_root(resolved) is not None or gtd_file(resolved)):
            raise Blocked("read")


def resolve(path, cwd):
    """Return the real absolute path of `path`, or None when it cannot be resolved.

    A `..` after a symbolic link can lead to one file when the system follows
    the link first and to another when a host tool removes `..` first, as
    Node.js does. When the two differ, the path cannot be resolved.
    """
    if not isinstance(path, str) or not path or "\0" in path:
        return None
    path = os.path.expanduser(path)
    if not os.path.isabs(path):
        if cwd is None:
            return None
        path = os.path.join(cwd, path)
    real = os.path.realpath(path)
    return real if os.path.realpath(os.path.normpath(path)) == real else None


def in_attachments(path):
    """Return whether `path` is in T3 Code's attachments folder, where the user's files arrive."""
    return inside(path, os.path.realpath(os.path.join(os.path.expanduser("~"), ".t3", "userdata", "attachments")))


def inside(path, folder):
    """Return whether the real path `path` is `folder` or in it."""
    return path == folder or path.startswith(folder + os.sep)


def gtd_binding():
    """Return the real path of the GTD binding that gtd-inbox reads."""
    return os.path.realpath(os.path.join(os.path.expanduser("~"), ".config", "cc-toolkit", "gtd.json"))


def in_binding_folder(path):
    """Return whether `path` is in the folder of the GTD binding, under any spelling of its name."""
    try:
        return os.path.samefile(os.path.dirname(path), os.path.dirname(gtd_binding()))
    except OSError:
        return False


def productivity_root(path):
    """Return the root of the installed Productivity Skills plugin that holds `path`, or None.

    A root holds scripts/gtd_sql.py and references/gtd-cloud.md and is outside
    every Git work tree, as an installed plugin is; a developer's checkout is not.
    """
    folder = path
    while True:
        if (os.path.isfile(os.path.join(folder, "scripts", GTD_SCRIPT))
                and os.path.isfile(os.path.join(folder, "references", GTD_CONTRACT))):
            return folder if outside_work_trees(folder) else None
        parent = os.path.dirname(folder)
        if parent == folder:
            return None
        folder = parent


def outside_work_trees(path):
    """Return whether the nearest existing folder of `path` is in no Git repository.

    Git must report "not a git repository"; any other result, such as a Git
    folder, counts as inside. A Git run that fails raises, and the hook blocks.
    """
    folder = path
    while not os.path.isdir(folder):
        folder = os.path.dirname(folder)
    result = git_run(folder, "rev-parse", "--is-inside-work-tree")
    return result.returncode != 0 and "not a git repository" in result.stderr


def is_gtd_json(text):
    """Return whether `text` is a GTD binding or a GTD request, as gtd_sql.py reads them."""
    import json

    try:
        value = json.loads(text)
    except ValueError:
        return False
    if not isinstance(value, dict):
        return False
    if set(value) == {"project_id", "owner_id"}:
        return all(isinstance(item, str) for item in value.values())
    return set(value) == {"request_id", "operations"} and isinstance(value["operations"], list)


def gtd_file(path):
    """Return whether the real path `path` is a gtd-inbox file (#621): a .json file outside every Git work
    tree whose content is a GTD binding or request, the content that check_gtd_write requires."""
    if not path.endswith(".json") or not os.path.isfile(path):
        return False
    try:
        with open(path, encoding="utf-8") as handle:
            if not is_gtd_json(handle.read(1_000_000)):
                return False
    except (OSError, ValueError):
        return False
    return outside_work_trees(path)


def check_gtd_write(name, arguments, cwd):
    """Return when the call writes one whole gtd-inbox file; raise Blocked otherwise.

    The file is a .json file at an absolute path, outside every Git work tree
    and outside the folder of the GTD binding, which changes only through
    gtd-setup. A host can resolve a relative path or `~` in its own way, so
    neither passes. The new content is a GTD binding or request, and the file
    is new or holds one already.
    """
    if not isinstance(arguments, dict):
        raise Blocked("edit")
    if name == "apply_patch":
        target = patch_file(arguments.get("command"))
    elif name in WRITE_TOOLS and not arguments.get("Append"):
        path_key, content_key = WRITE_TOOLS[name]
        target = arguments.get(path_key), arguments.get(content_key)
    else:
        target = None
    if target is None:
        raise Blocked("edit")
    path, content = target
    if not isinstance(path, str) or not os.path.isabs(path) or not isinstance(content, str):
        raise Blocked("edit")
    resolved = resolve(path, cwd)
    if (resolved is None or not resolved.endswith(".json") or in_binding_folder(resolved)
            or not is_gtd_json(content) or not outside_work_trees(resolved)):
        raise Blocked("edit")
    if os.path.lexists(resolved):
        if not os.path.isfile(resolved):
            raise Blocked("edit")
        with open(resolved, encoding="utf-8") as existing:
            if not is_gtd_json(existing.read(1_000_000)):
                raise Blocked("edit")


def patch_file(command):
    """Return (path, content) of a Codex patch that only adds one file, or None."""
    if not isinstance(command, str):
        return None
    lines = command.strip("\n").split("\n")
    if len(lines) < 3 or lines[0] != "*** Begin Patch" or lines[-1] != "*** End Patch":
        return None
    header, body = lines[1], lines[2:-1]
    if not header.startswith("*** Add File: ") or not all(line.startswith("+") for line in body):
        return None
    return header[len("*** Add File: "):].strip(), "".join(line[1:] + "\n" for line in body)


def git_run(cwd, *args):
    """Run a git command in `cwd` and return the completed process.

    The caller's Git variables are removed, and the C locale keeps Git's
    messages in English.
    """
    import subprocess

    env = {key: value for key, value in os.environ.items()
           if key not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR")}
    env["LC_ALL"] = "C"
    return subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, env=env,
                          timeout=10, check=False)


def git(cwd, *args):
    """Return the stripped stdout of a git command in `cwd`, or "" on failure."""
    result = git_run(cwd, *args)
    return result.stdout.strip() if result.returncode == 0 else ""


# Records.

def write_record(folder, session):
    import time

    os.makedirs(folder, mode=0o700, exist_ok=True)
    record = os.path.join(folder, session)
    with open(record, "a", encoding="utf-8"):
        pass
    os.utime(record, None)
    oldest = time.time() - RECORD_DAYS * 24 * 60 * 60
    for entry in os.scandir(folder):
        try:
            if entry.is_file(follow_symlinks=False) and entry.stat().st_mtime < oldest:
                os.unlink(entry.path)
        except OSError:
            pass


# Shell commands.

def check_shell(arguments, key, cwd, folder, session, saved_outputs):
    """Return when the shell command is a lead action; raise Blocked otherwise.

    The command is `python3|python <script> <subcommand> [arguments...]`, the
    gtd-inbox renderer, or one read command of the files that check_reads
    allows. Only an exact `python3|python <script> start` refreshes the record,
    and only an exact `python3|python <script> unmark` can remove it (#612).
    """
    session_cwd = cwd
    words, cwd = shell_words(arguments, key, cwd)
    if not words:
        raise Blocked("shell")
    if words[0] == "uv":
        if not renderer_command(words, cwd):
            raise Blocked("shell")
        return
    if words[0] not in ("python3", "python"):
        # One read command, for a host whose reads go through the shell.
        paths = read_paths(words[0], words[1:])
        if paths is None:
            raise Blocked("shell")
        try:
            check_reads(paths, cwd, saved_outputs)
        except Blocked:
            raise Blocked("shell") from None
        return
    if len(words) < 3 or not is_step(words[2]) or not step_script(words, cwd):
        raise Blocked("shell")
    if words[2:] == ["unmark"]:
        check_unmark(cwd, session_cwd, folder, session)
    elif words[2:] == ["start"]:
        try:
            write_record(folder, session)
        except OSError:
            pass  # The record exists; a failed refresh does not stop the step.


def renderer_command(words, cwd):
    """Return whether `words` run gtd_sql.py of an installed Productivity Skills plugin:
    `uv run --no-project [uv options] python|python3 <script> [arguments...]`.

    Without --no-project, uv would create an environment in a project folder,
    and a --python value other than a version could name any program.
    """
    import re

    if words[:2] != ["uv", "run"]:
        return False
    index, options = 2, []
    while index < len(words) and words[index].startswith("-"):
        if words[index] == "--python" and index + 1 < len(words):
            options.append("--python=" + words[index + 1])
            index += 2
        else:
            options.append(words[index])
            index += 1
    if "--no-project" not in options:
        return False
    for option in options:
        if option.startswith("--python="):
            if re.fullmatch(r"(?:>=|<=|==|~=|>|<)?\d+(?:\.\d+){0,2}", option[len("--python="):]) is None:
                return False
        elif option != "--no-project" and option not in UV_OPTIONS:
            return False
    if index + 1 >= len(words) or words[index] not in ("python", "python3"):
        return False
    path = resolve(words[index + 1], cwd)
    if path is None or os.path.basename(path) != GTD_SCRIPT:
        return False
    root = os.path.dirname(os.path.dirname(path))
    return os.path.basename(os.path.dirname(path)) == "scripts" and productivity_root(path) == root


def shell_words(arguments, key, cwd):
    """Return the words of the shell command in `arguments` and the folder where it runs.

    The words are None when the command is not one simple command. A Codex
    `bash -lc <script>` wrapper gives the words of the script.
    """
    command = arguments.get(key)
    if isinstance(command, list) and all(isinstance(word, str) for word in command):
        words = list(command)
    elif isinstance(command, str):
        words = split_words(command)
    else:
        raise ValueError(f"the shell command is not a string: {key}")
    if words is not None and len(words) == 3 and words[0] in WRAPPER_SHELLS and words[1] in ("-c", "-lc"):
        words = split_words(words[2])
    workdir = arguments.get("workdir", arguments.get("Cwd"))
    if isinstance(workdir, str) and workdir:
        cwd = os.path.join(cwd, workdir) if cwd is not None else workdir
        cwd = cwd if os.path.isabs(cwd) else None
    return words, cwd


def start_commands(arguments, key, cwd):
    """Return the simple commands of the shell call in `arguments` as (words, cwd) pairs.

    One simple command gives the words of shell_words. Otherwise the command,
    or the script of a `bash|sh|zsh -c|-lc <script>` wrapper, is read as a
    command list (issue #574). A list that command_list cannot read gives no
    commands.
    """
    words, cwd = shell_words(arguments, key, cwd)
    if words is not None:
        return [(words, cwd)]
    command = arguments.get(key)
    if isinstance(command, list):
        if len(command) != 3 or command[0] not in WRAPPER_SHELLS or command[1] not in ("-c", "-lc"):
            return []
        command = command[2]
    commands = command_list(command, cwd) or []
    if len(commands) == 1:
        words = commands[0][0]
        if (len(words) == 3 and words[0] in WRAPPER_SHELLS and words[1] in ("-c", "-lc")
                and words[2] is not None):
            commands = command_list(words[2], cwd) or []
    return commands


def command_list(command, cwd):
    """Return the simple commands of a command list as (words, cwd) pairs, or None (issue #574).

    A word is None when it cannot be known: it has an unquoted glob or brace,
    `~user`, or an unset variable. A command of assignments only, also after
    `export`, sets its variables for the later commands, unless it is in a
    pipeline or runs with `&`: bash runs those in a subshell. An assignment
    before a command word changes no word of that command, as in bash. After
    cd, pushd, popd, or a command word that is None, the cwd is None, so a
    relative path cannot resolve. The result is None for a `{` or `}` word,
    a command of UNREAD_COMMANDS, an `IFS` or `NAME+=` assignment, or an
    empty command before an operator, such as `;;`. The list ends at a
    command of LIST_ENDS.
    """
    tokens = command_tokens(command)
    if tokens is None:
        return None
    variables = {}
    commands = []
    raw = []
    previous = ";"
    for kind, text in tokens + [("op", None)]:
        if kind == "word":
            if text in ("{", "}"):
                return None
            raw.append(text)
            continue
        if not raw:
            if text not in ("\n", None):
                return None
            previous = text
            continue
        if raw[:1] == ["export"] and all(map(is_assignment, raw[1:])):
            prefix, rest = raw[1:], []
        else:
            count = 0
            while count < len(raw) and is_assignment(raw[count]):
                count += 1
            prefix, rest = raw[:count], raw[count:]
        if any(word.startswith("IFS=") for word in prefix) or rest and appends(rest[0]):
            return None
        if rest:
            words = [word_value(word, variables) for word in rest]
            if words[0] in UNREAD_COMMANDS:
                return None
            if words[0] in LIST_ENDS:
                break
            commands.append((words, cwd))
            if words[0] in (None, "cd", "pushd", "popd"):
                cwd = None
        elif previous not in ("|", "|&") and text not in ("|", "|&", "&"):
            for assignment in prefix:
                name, value = assignment.split("=", 1)
                variables[name] = word_value(value, variables) if value else ""
        raw, previous = [], text
    return commands


def command_tokens(command):
    """Split a command list into ("word", raw text) and ("op", operator) tokens, or return None.

    A word keeps its quotes and `$` expansions for split_words. The operators
    are ;, &, &&, ||, |, |&, and a new line. A comment, a redirect, its
    target word, and a file descriptor before it, as in `2>&1`, give no
    token. The result is None for a subshell, a command or process
    substitution, a here-document, a redirect with no target, or a quote that
    does not end.
    """
    tokens = []
    word = None
    target = False
    index = 0
    length = len(command)
    while index < length:
        char = command[index]
        if char in "()`" or command.startswith("<<", index) and not command.startswith("<<<", index):
            return None
        if char in " \t\n;&|<>":
            if word is not None:
                if target:
                    target = False
                elif not (char in "<>" and "".join(word).isdigit()):
                    tokens.append(("word", "".join(word)))
                word = None
            if char in " \t":
                index += 1
            elif char in "<>" or command.startswith("&>", index):
                if target:
                    return None
                index += 1
                while index < length and command[index] in "<>&|":
                    index += 1
                target = True
            elif target:
                return None
            else:
                operator = command[index:index + 2] if command[index:index + 2] in ("&&", "||", "|&") else char
                tokens.append(("op", operator))
                index += len(operator)
            continue
        if char == "#" and word is None:
            end = command.find("\n", index)
            index = length if end < 0 else end
            continue
        if command.startswith("\\\n", index):
            index += 2
            continue
        start = index
        if char == "\\":
            index += 2
        elif char == "'":
            end = command.find("'", index + 1)
            if end < 0:
                return None
            index = end + 1
        elif char == '"':
            index += 1
            while index < length and command[index] != '"':
                if command[index] == "`" or command.startswith("$(", index):
                    return None
                index += 2 if command[index] == "\\" else 1
            if index >= length:
                return None
            index += 1
        elif command.startswith("$(", index):
            return None
        elif command.startswith("${", index):
            end = command.find("}", index)
            if end < 0:
                return None
            index = end + 1
        else:
            index += 1
        if word is None:
            word = []
        word.append(command[start:index])
    if target and word is None:
        return None
    if word is not None and not target:
        tokens.append(("word", "".join(word)))
    return tokens


def appends(word):
    """Return whether `word` is a `NAME+=value` assignment."""
    name, sign, _ = word.partition("+=")
    return bool(sign) and name.isidentifier() and name.isascii()


def is_assignment(word):
    name, sign, _ = word.partition("=")
    return bool(sign) and name.isidentifier() and name.isascii()


def word_value(word, variables):
    """Return the value of one raw word after quote removal and expansion, or None.

    The word comes second, so that split_words does not read a value such as
    `S=x; python3 $S start`, the script of a shell wrapper, as an assignment.
    """
    values = split_words("_ " + word, variables)
    return values[1] if values is not None and len(values) == 2 else None


def is_step(word):
    return word.isascii() and word.isalpha() and word.islower()


def step_script(words, cwd):
    """Return whether `words[1]` names this hook's sibling step script, or a
    copy outside every Git work tree."""
    if not words[1].endswith(SCRIPT_NAME):
        return False
    path = resolve(words[1], cwd)
    if path is None or os.path.basename(path) != SCRIPT_NAME:
        return False
    if path == os.path.realpath(sibling_script()):
        return True
    return os.path.isfile(path) and git(os.path.dirname(path), "rev-parse", "--is-inside-work-tree") != "true"


def read_paths(program, args):
    """Return the file arguments of one simple read command, or None."""
    if program == "sed":
        return sed_paths(args)
    if program == "grep":
        return grep_paths(args)
    flags = {"cat": "AbeEnstTuv", "wc": "clmwL", "ls": "1@aAcdFghilLnoprRsStu"}.get(program)
    if flags is None and program not in ("head", "tail"):
        return None
    paths = []
    index = 0
    while index < len(args):
        word = args[index]
        index += 1
        if paths or word == "-" or not word.startswith("-"):
            if word.startswith("-"):
                return None
            paths.append(word)
        elif word == "--":
            paths.extend(args[index:])
            break
        elif flags is not None:
            if not set(word[1:]) <= set(flags):
                return None
        elif word[1:].isdigit() or word in ("-q", "-v"):
            continue
        elif word[1:2] in ("n", "c"):
            value = word[2:]
            if not value:
                if index >= len(args):
                    return None
                value = args[index]
                index += 1
            if not value.lstrip("+-").isdigit():
                return None
        else:
            return None
    return paths or None


def grep_paths(args):
    """Return the file arguments of a grep command, or None."""
    flags = set("EFGHhiIlLnorRsvwxcqzaU")
    pattern_given = False
    paths = []
    index = 0
    while index < len(args):
        word = args[index]
        index += 1
        if word == "--":
            rest = args[index:]
            if not pattern_given and rest:
                pattern_given = True
                rest = rest[1:]
            paths.extend(rest)
            break
        if not word.startswith("-") or word == "-":
            if word == "-":
                return None
            if pattern_given:
                paths.append(word)
            else:
                pattern_given = True
            continue
        if paths or word.startswith("--"):
            return None
        letters = word[1:]
        while letters:
            letter, letters = letters[0], letters[1:]
            if letter in flags:
                continue
            if letter not in "eABCm":
                return None
            value = letters
            letters = ""
            if not value:
                if index >= len(args):
                    return None
                value = args[index]
                index += 1
            if letter == "e":
                pattern_given = True
            elif not value.isdigit():
                return None
    return paths if pattern_given and paths else None


def sed_paths(args):
    """Return the file arguments of `sed -n <print-only script> <file>...`, or None."""
    import re

    if len(args) >= 2 and args[0] == "-n" and args[1] == "-e":
        args = ["-n"] + args[2:]
    if len(args) < 3 or args[0] != "-n":
        return None
    address = r"(?:\d+|\$|/(?:[^/\\\n]|\\.)*/)"
    command = rf"\s*(?:{address}(?:\s*,\s*{address})?\s*)?p\s*"
    if re.fullmatch(rf"{command}(?:[;\n]{command})*;?\s*", args[1]) is None:
        return None
    paths = args[2:]
    if paths[0] == "--":
        paths = paths[1:]
    if not paths or any(path.startswith("-") for path in paths):
        return None
    return paths


def split_words(command, variables=None):
    """Return the words of one simple shell command, or None.

    The result is None for a command list, a pipe, a redirect, `&`, a
    subshell, command or process substitution, an unquoted glob or brace,
    a comment, a leading variable assignment, an unset variable, or a quote
    that does not end. Quotes and backslashes are removed, and `$NAME`,
    `${NAME}`, and a leading `~` are expanded from this process's environment.
    A name in `variables` takes its value from there; a value of None is unset.
    """
    command = command.strip()
    words = []
    word = []
    in_word = False
    index = 0
    length = len(command)
    while index < length:
        char = command[index]
        if char in " \t":
            if in_word:
                words.append("".join(word))
                word = []
                in_word = False
            index += 1
            continue
        if char in "\n\r|&;<>()`*?[]{}" or (char in "#=" and not in_word):
            return None
        if char == "~" and not in_word:
            following = command[index + 1:index + 2]
            if following not in ("", "/", " ", "\t"):
                return None
            word.append(os.path.expanduser("~"))
            in_word = True
            index += 1
            continue
        in_word = True
        if char == "\\":
            if index + 1 >= length:
                return None
            word.append(command[index + 1])
            index += 2
        elif char == "'":
            end = command.find("'", index + 1)
            if end < 0:
                return None
            word.append(command[index + 1:end])
            index = end + 1
        elif char == '"':
            index += 1
            while True:
                if index >= length:
                    return None
                char = command[index]
                if char == '"':
                    index += 1
                    break
                if char == "`":
                    return None
                if char == "\\" and command[index + 1:index + 2] in ('"', "\\", "$", "`"):
                    word.append(command[index + 1])
                    index += 2
                elif char == "$":
                    value, index = expand(command, index, quoted=True, variables=variables)
                    if value is None:
                        return None
                    word.append(value)
                else:
                    word.append(char)
                    index += 1
        elif char == "$":
            value, index = expand(command, index, quoted=False, variables=variables)
            # An unquoted expansion splits on spaces and globs in bash.
            if value is None or any(c in value for c in " \t\n*?[]{}"):
                return None
            word.append(value)
        else:
            word.append(char)
            index += 1
    if in_word:
        words.append("".join(word))
    if words and "=" in words[0] and words[0].split("=", 1)[0].isidentifier():
        return None
    return words


def expand(command, index, *, quoted, variables=None):
    """Expand the `$` at `command[index]`; return (value or None, next index)."""
    following = command[index + 1:index + 2]
    if following in ("", " ", "\t") or (quoted and following == '"'):
        return "$", index + 1
    if following == "{":
        end = command.find("}", index + 2)
        if end < 0:
            return None, index
        name, after = command[index + 2:end], end + 1
    else:
        end = index + 1
        while end < len(command) and (command[end].isalnum() or command[end] == "_"):
            end += 1
        name, after = command[index + 1:end], end
    if not name.isidentifier() or not name.isascii():
        return None, index
    value = variables[name] if variables is not None and name in variables else os.environ.get(name)
    return (value, after) if value is not None else (None, index)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
