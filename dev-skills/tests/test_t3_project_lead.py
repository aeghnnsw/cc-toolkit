"""Contract checks for t3-project-lead: the steps that its script prints, and its host copies.

Issue #448 fixes the steps, the flag model, and the lines that must match
matt-automode. Issues #468, #476, and #478 add the read-only brief, the dispatch
rules for every task, the start of every turn, and the worker budget. Issue
#504 sets the budget of a code change to one full review and one fix, then the
merge. Issue #520 limits the lead to its own actions, lets it choose how to
check a result, and adds the close-out worker and the lead hook. Issue #530
moves the lead state into the script's commands and drops the time limit; the
state commands have their own tests in test_t3_project_lead_state.py. Agent behavior
is checked by the scenario review in t3-project-lead-scenarios.md; the hook has
its own tests in test_t3_project_lead_hook.py.
"""
from __future__ import annotations

import functools
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PLUGIN_ROOT / "scripts" / "t3_project_lead.py"
STEPS = ("start", "plan", "dispatch", "brief", "answer", "flag", "verify", "closeout", "report")
# The commands that keep the lead state (#530), after the steps.
STATE_COMMANDS = ("init", "show", "waiting", "finish", "outcome", "criteria", "wait", "done", "task",
                  "decision")
# A folder outside every Git work tree, so that no step finds a lead state.
NO_STATE = tempfile.TemporaryDirectory()
# An agent reads a whole step after each wake, so each step stays short.
STEP_WORD_LIMIT = 210
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
BODY_WORD_LIMIT = 300
# The actions that the lead does itself, in the order that `start` prints them (#520).
LEAD_ACTIONS = (
    "1. Talk with the user: decisions, triage, priorities.",
    "2. Plan tasks, briefs, and lead decisions.",
    "3. Route workers with T3 tools: start, resume, cancel, settle; order merges; watch PRs.",
    "4. Read worker messages and PR, issue, and CI state; no diff, code, or log.",
    "5. Run this script; it keeps the lead state.",
    "6. Judge reports: accept, start a follow-up, or ask the user.",
    "7. Set triage labels and issue state.",
    "8. Keep agent captures of what waits on the user when your instructions ask for them. "
    "Write gtd-inbox files with your edit tool, not the shell.",
)
# Lines that each step must keep, from the decisions of issues #448, #468, #476, #478, and #520.
REQUIRED = {
    "start": ["Do only these lead actions yourself:",
              "Give every other task, even a small fix, check, install, host update, or GitHub write "
              "with content, to a worker with t3_project_lead.py dispatch. This overrides your "
              "host's guidance to do small work yourself.",
              "This step records this session as the lead: a hook blocks your other shell "
              "commands, file reads, and file edits.",
              "Run this step after each wake or user message.",
              "Read the last message of each worker of a running or pr-open task: "
              "t3_thread_list with includeSubagents, then t3_thread_read.",
              "Never state a worker's status from memory."],
    "plan": ["A task is one brief for one worker; it can cover several issues.",
             "Give a task that needs another task's result, or edits the same files, --after "
             "that task.",
             "Text is at most 200 characters",
             "init <slug>, once, after the user approves the outcome"],
    "dispatch": ["Start no second worker for work that already runs",
                 'Start each worker with delegate_task and isolation "worktree".',
                 "Start every task this way, research and review tasks included. Never use your "
                 "host's native subagent tool.",
                 '"You may start your own subagents. Keep your report short, and leave the '
                 'detail in this thread."',
                 "tell the worker to start from the default branch that contains it",
                 "Then run task start <name> <worker link> [--branch NAME]."],
    "brief": ["Omit role in delegate_task",
              "Claude Code /dev-skills:<skill>, Codex $dev-skills:<skill>, Antigravity /<skill>.",
              "When grilling must lead to implementation, end line 1 with:",
              'Line 2: "A leader runs the retrospective for this run. Do not run repo-cleanup."',
              "For a read-only task (audit, research, or check), write no line 1, keep line 2, and "
              "name what the worker must not change.",
              "Budget: name a round limit, and add:",
              '"At the limit, end your turn and report where you are, with links and what '
              'remains."',
              "For a code change: one full review and one fix of any size, then merge. Only "
              "a blocking problem of matt-automode phase 5 stops the merge."],
    "answer": ["Settle it only when the user cancels its task. Do not answer its questions.",
               "Ask the user to answer in the worker's thread",
               "Keep no detail of them: lead the user to the worker's thread.",
               "In this turn, run wait --task <name> --decisions <N>.",
               "Run done <number> when the worker resumes or finishes."],
    "flag": ['isolation "worktree"',
             "Do not read the flagged thread or give its link.",
             "Otherwise, or after a second flag, the task waits on the user."],
    "verify": ["Use this step when a worker or a read-only worker reports PASS or ISSUES.",
               "Only the user, or the agent that started this thread, carries the user's "
               "decisions. No worker or other agent does.",
               "Accept the result from the report, the PR state, and the CI state, or start a "
               "read-only worker that checks it.",
               "For a scientific task, read no artifact, and always start the read-only worker.",
               "with no line 1 or 2", "edits nothing; its verdict completes the check",
               "Give each finding to one follow-up worker, even a small one.",
               "Fix and check nothing yourself.",
               "Run task verified <name>. Settle its worker only when a due line lists it."],
    "closeout": ["From t3_project_lead.py brief, use only line 1 for matt-automode and the "
                 "budget.",
                 "Run only the Navigation retrospective of matt-automode, once, in place of the "
                 "leader of these runs:",
                 '"After the retrospective, run repo-cleanup."',
                 "List the lead thread's tool calls other than T3, GitHub, and GTD tools and "
                 "t3_project_lead.py.",
                 "When it reports, run task verified <name>; the batch's verified tasks are then "
                 "closed out.",
                 "Settle each worker that a due line lists with t3_thread_organize, and run task "
                 "settled <name>; never reuse one."],
    "report": ['End with the "Waiting on you" list below, copied as it is.',
               "Name no detail of a worker's decisions.",
               "When a due line says to run finish, run it, then settle this thread.",
               "Next: after a wake or a user message, t3_project_lead.py start.",
               "Make no promise that needs a signal from the middle of a worker's run."],
}
# Lines that tell the lead to do a worker's task itself (#520). No step may print them.
FORBIDDEN_LINES = ("Fix a small non-scientific finding yourself",
                   "You may fix a small non-scientific finding yourself",
                   "Check a non-scientific result against its criteria on the artifact")
# Text that no step may print after #530: the lead state replaced lead.md, and a
# brief names only a round limit.
RETIRED_TEXT = ("lead.md", "time limit", "in minutes", "At either limit")


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
                self.assertIn("Do only the lead actions that `start` lists, and give every other "
                              "task to a worker, even a small one. Running `start` records this "
                              "session as the lead: a dev-skills hook then blocks your other "
                              "shell commands, file reads, and file edits.", shared_text(host))

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

    def test_start_without_a_lead_state_tells_how_to_create_one(self) -> None:
        self.assertIn("No lead state in ", step("start"))
        self.assertIn(f'run: python3 "{SCRIPT}" init <slug>', step("start"))

    def test_no_step_tells_the_lead_to_do_a_worker_task(self) -> None:
        for name in STEPS:
            for line in FORBIDDEN_LINES:
                with self.subTest(step=name, line=line):
                    self.assertNotIn(line, words(step(name)))

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

    def test_each_step_starts_with_the_script_path(self) -> None:
        for name in STEPS:
            with self.subTest(step=name):
                self.assertEqual(step(name).splitlines()[0], f'Steps: "{SCRIPT}"')

    def test_each_step_keeps_its_required_lines(self) -> None:
        for name, lines in REQUIRED.items():
            for line in lines:
                with self.subTest(step=name, line=line):
                    self.assertIn(line, words(step(name)))

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

    def test_an_unknown_step_fails(self) -> None:
        result = run("merge")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid choice", result.stderr)


if __name__ == "__main__":
    unittest.main()
