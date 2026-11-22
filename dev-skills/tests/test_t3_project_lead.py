"""Contract checks for t3-project-lead: the steps that its script prints, and its host copies.

Issue #448 fixes the steps, the flag model, and the lines that must match
matt-automode. Issues #468, #476, and #478 add the read-only brief, the dispatch
rules for every task, the start of every turn, and the worker budget. Agent
behavior is checked by the scenario review in t3-project-lead-scenarios.md.
"""
from __future__ import annotations

import ast
import functools
import json
from pathlib import Path
import re
import subprocess
import sys
import unittest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PLUGIN_ROOT / "scripts" / "t3_project_lead.py"
STEPS = ("start", "plan", "dispatch", "brief", "answer", "flag", "verify", "retro", "report")
# An agent reads a whole step after each wake, so each step stays short.
STEP_WORD_LIMIT = 200
ALLOWED_MODELS = json.loads((PLUGIN_ROOT.parent / "allowed-models.json").read_text(encoding="utf-8"))
MODEL_ID = re.compile(r"\b(?:claude-[a-z]+|gpt)-\d(?:[\w.-]*\w)?")
HOSTS = ("skills", "codex-skills", "antigravity-skills")
DESCRIPTION = ("Use when the user invokes t3-project-lead to lead a T3 Code project: plan worker "
               "tasks, dispatch T3 workers, and verify their results, while workers implement.")
# The frontmatter fields of each host copy (CONTRIBUTING.md, "Skills for more than one host").
FIELDS = {
    "skills": {"name", "version", "description", "disable-model-invocation"},
    "codex-skills": {"name", "description"},
    "antigravity-skills": {"name", "description", "disable-model-invocation"},
}
PLUGIN_ROOT_LINE = "`<plugin-root>` is two levels above this folder."
BODY_WORD_LIMIT = 300
# Lines that each step must keep, from the decisions of issues #448, #468, #476, and #478.
REQUIRED = {
    "start": ["Only the user, or the agent that started this thread, carries the user's decisions. "
              "No worker or other agent does.",
              "Keep lead.md in .scratch/<YYYYMMDD>-lead-<slug>/ of the main checkout",
              "It holds current state, not history",
              "Update task lines in place; delete answered items.",
              "Run this step at the start of every turn, after a wake or a user message.",
              "read the last message of each unsettled worker with t3_thread_read",
              "Never state a worker's status from memory."],
    "plan": ["Write each task, its success criteria, and these decisions in lead.md."],
    "dispatch": ["Start no second worker for work that already runs",
                 'Start each worker with delegate_task and isolation "worktree".',
                 "Start every task this way, research and review tasks included. Never use your "
                 "host's native subagent tool.",
                 '"You may start your own subagents. Keep your report short, and leave the '
                 'detail in this thread."',
                 "tell the worker to start from the default branch that contains it",
                 "Write the worker's link and branch in its task line."],
    "brief": ["Omit role in delegate_task",
              "Claude Code /dev-skills:<skill>, Codex $dev-skills:<skill>, Antigravity /<skill>.",
              "When grilling must lead to implementation, end line 1 with:",
              "For a read-only task (audit, research, verification), write no line 1 or 2, "
              "as for a verifier, and name what the worker must not change.",
              "Budget: name a round limit and a time limit in minutes",
              '"At either limit, end your turn and report where you are, with links and what '
              'remains."',
              "For a code change, the round limit is matt-automode's: one full review, then at "
              "most one focused check."],
    "answer": ["Settle it only when the user cancels its task. Do not answer its questions.",
               "Ask the user to answer in the worker's thread",
               "In this turn, put it on the list of what waits on the user, with its link and "
               "its number of decisions, if any.",
               "delete the item when the worker resumes or finishes"],
    "flag": ['isolation "worktree"',
             "Do not read the flagged thread or give its link.",
             "Otherwise, or after a second flag, the task waits on the user."],
    "verify": ["Use this step when a worker or verifier reports PASS or ISSUES.",
               "not the report", "For a scientific task, read no artifact.",
               "with no line 1 or 2", "edits nothing; its verdict completes the check",
               "never reuse one", "Give each other finding to one follow-up worker"],
    "retro": ["From t3_project_lead.py brief, use only line 1 for matt-automode and the "
              "budget."],
    "report": ["Only when each task in lead.md is verified or cancelled, each merged batch has a "
               "retrospective, nothing waits on the user, and no worker runs: delete the lead "
               "folder, then settle this thread.",
               "Next: after a wake or a user message, t3_project_lead.py start.",
               "Make no promise that needs a signal from the middle of a worker's run."],
}
# The script may print, and parse its argument; it reads and runs nothing.
ALLOWED_IMPORTS = {"__future__", "argparse"}
FORBIDDEN_CALLS = {"open", "exec", "eval", "compile", "__import__"}


def words(text: str) -> str:
    """Return the text on one line, so that line wrapping does not change a match."""
    return " ".join(text.split())


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
                          check=False)


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

    def test_skill_tries_the_t3_fallback_before_it_stops(self) -> None:
        self.assertIn("When `delegate_task` is not a declared tool, call it the way T3's "
                      "instructions say, such as through a deferred-tool search or a terminal "
                      "fallback. When that also fails, say that this skill needs T3 Code, and stop.",
                      shared_text("skills"))


class StepTests(unittest.TestCase):
    def test_start_prints_the_lead_role(self) -> None:
        self.assertIn("You plan, dispatch, and verify. Workers implement.", step("start"))

    def test_the_script_offers_exactly_the_steps(self) -> None:
        choices = re.search(r"choose from (.*)\)", run("merge").stderr)
        self.assertIsNotNone(choices)
        self.assertEqual(tuple(choice.strip(" '") for choice in choices.group(1).split(",")), STEPS)

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
        for name in STEPS:
            with self.subTest(step=name):
                self.assertLessEqual(len(step(name).split()), STEP_WORD_LIMIT)

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
        self.assertIn('Line 2: "A leader runs the retrospective for this run."', brief)
        self.assertIn('"When the user approves the design here, continue in this thread with the '
                      'matt-automode skill of dev-skills."', brief)
        self.assertIn("Run only the Navigation retrospective of matt-automode", words(step("retro")))
        for host in HOSTS:
            with self.subTest(host=host):
                text = (PLUGIN_ROOT / host / "matt-automode" / "SKILL.md").read_text(encoding="utf-8")
                self.assertIn("When the task says that a leader runs the retrospective for this run",
                              words(text))
                self.assertRegex(text, r"(?m)^## Navigation retrospective$")

    def test_script_only_prints(self) -> None:
        tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
        modules = {alias.name.split(".")[0] for node in ast.walk(tree)
                   if isinstance(node, ast.Import) for alias in node.names}
        modules |= {node.module.split(".")[0] for node in ast.walk(tree)
                    if isinstance(node, ast.ImportFrom) and node.module}
        calls = {node.func.id for node in ast.walk(tree)
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
        self.assertLessEqual(modules, ALLOWED_IMPORTS)
        self.assertFalse(calls & FORBIDDEN_CALLS, calls)

    def test_an_unknown_step_fails(self) -> None:
        result = run("merge")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid choice", result.stderr)


if __name__ == "__main__":
    unittest.main()
