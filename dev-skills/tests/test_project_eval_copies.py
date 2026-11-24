"""The Antigravity project-eval references keep the text of the Claude Code agents.

The Antigravity copy has no plugin agents, so its evaluator and verifier
instructions are skill-local copies of the Claude Code agent bodies. Each
comparison allows only the listed host-specific substitutions.
tests/test_host_copies.py compares the files that both skill copies have.
The calibration examples of real issues in both copies follow the evidence
rule, because evaluators copy them. The Set Up block of each copy runs in
bash and zsh with TMPDIR set, and writes the run state under TMPDIR (#457).
The two Claude Code agents have one tools line, with no tool that writes
files and with the browser tool prefixes that the SKILL.md "Browser Servers"
section lists.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
CLAUDE_SKILL = PLUGIN_ROOT / "skills" / "project-eval"
ANTIGRAVITY_SKILL = PLUGIN_ROOT / "antigravity-skills" / "project-eval"
AGENTS = PLUGIN_ROOT / "claude-agents"

# A location that a verifier can check: `path:N` or `path:N-M`, a URL, or a command.
CHECKABLE_LOCATION = re.compile(r"`[^`\s]+:\d+(?:-\d+)?`|https?://\S+|command `[^`]+`")

# Tools that write files: evaluators and verifiers return their results as text.
WRITE_TOOLS = ("Write", "Edit", "NotebookEdit")
BROWSER_PREFIX = re.compile(r"`(mcp__[^`<>\s]+__\*)`")

SKILL_DIR_SENTENCE = "`<skill-dir>` is the parent of the `references/` folder that holds this file."
COMMON_SUBSTITUTIONS = (
    ("${CLAUDE_PLUGIN_ROOT}/skills/project-eval/references/", "<skill-dir>/references/"),
    ("The dispatch prompt gives you:", "The prompt that started you gives you:"),
)
EVAL_AGENTS = ("project-evaluator.md", "finding-verifier.md")
REFERENCES = {
    "evaluator.md": ("project-evaluator.md", COMMON_SUBSTITUTIONS + (
        ("have an app URL.", "have an app URL and the session has browser tools."),
        ("If you have no browser tools, or the session refuses",
         "If the session has no browser tools, or it refuses"),
    )),
    "verifier.md": ("finding-verifier.md", COMMON_SUBSTITUTIONS),
}
SHELLS = {"bash": ["bash", "-c"], "zsh": ["zsh", "-f", "-c"]}  # -f: no user startup files
BASH_FENCE = re.compile(r"^[ \t]*```bash[ \t]*\n(.*?)^[ \t]*```", re.MULTILINE | re.DOTALL)
SET_UP = re.compile(r"^### \d+\. Set Up the Run$(.*?)^#", re.MULTILINE | re.DOTALL)
RUN_LINE = re.compile(r'^RUN="(.+)"$', re.MULTILINE)


def words(text: str) -> str:
    """Return the text with each run of whitespace as one space."""
    return " ".join(text.split())


def agent_body(path: Path) -> str:
    """Return the agent file without its YAML frontmatter."""
    _, _, body = path.read_text().split("---\n", 2)
    return body


def translated(text: str, substitutions) -> str:
    text = words(text)
    for old, new in substitutions:
        old, new = words(old), words(new)
        assert old in text, f"substitution source not found: {old}"
        text = text.replace(old, new)
    return text


def tools(agent: str) -> list[str]:
    """Return the entries of the tools line in the frontmatter of an agent file."""
    frontmatter = agent.split("---\n", 2)[1]
    lines = [line for line in frontmatter.splitlines() if line.startswith("tools:")]
    assert len(lines) == 1, f"{len(lines)} tools lines"
    return [entry.strip() for entry in lines[0][len("tools:"):].split(",")]


def browser_prefixes(skill: str) -> list[str]:
    """Return the browser tool prefixes that the Browser Servers section of SKILL.md lists."""
    section = skill.split("\n## Browser Servers\n", 1)[1].split("\n## ", 1)[0]
    return sorted(BROWSER_PREFIX.findall(section))


def tools_problems(agents: dict[str, str], skill: str) -> list[str]:
    """Return the problems of the tools lines of the agent files against SKILL.md."""
    lines = {name: tools(text) for name, text in agents.items()}
    prefixes = browser_prefixes(skill)
    problems = []
    if len({tuple(line) for line in lines.values()}) > 1:
        problems.append("the tools lines differ: " + "; ".join(f"{n}: {', '.join(t)}" for n, t in lines.items()))
    for name, line in lines.items():
        problems += [f"{name} has {tool}" for tool in line if tool.split("(")[0] in WRITE_TOOLS]
        browser = sorted(tool for tool in line if tool.startswith("mcp__"))
        if browser != prefixes:
            problems.append(f"{name} has the browser tools {browser}, and Browser Servers lists {prefixes}")
    return problems


def real_issue_examples(text: str):
    """Yield the line number and lines of each REAL ISSUE example.

    An example ends at the next line that starts with a bold label or a heading.
    """
    example = None
    for number, line in enumerate(text.splitlines(), 1):
        if line.startswith(("**", "#")):
            if example:
                yield example
            example = (number, [line]) if line.startswith("**REAL ISSUE") else None
        elif example:
            example[1].append(line)
    if example:
        yield example


def set_up_block(text: str) -> str:
    """Return the first bash block under the "Set Up the Run" heading, or ""."""
    section = SET_UP.search(text)
    block = section and BASH_FENCE.search(section.group(1))
    return block.group(1) if block else ""


class ProjectEvalCopiesTest(unittest.TestCase):
    def test_set_up_block_writes_the_run_state_under_tmpdir_in_bash_and_zsh(self) -> None:
        for skill in (CLAUDE_SKILL, ANTIGRAVITY_SKILL):
            block = set_up_block((skill / "SKILL.md").read_text())
            for shell, command in SHELLS.items():
                with self.subTest(copy=str(skill.relative_to(PLUGIN_ROOT)), shell=shell), \
                        tempfile.TemporaryDirectory() as temp:
                    if shutil.which(shell) is None:
                        self.skipTest(f"{shell} is not installed")
                    self.assertTrue(block, "no bash block under Set Up the Run")
                    env = dict(os.environ, TMPDIR=temp)
                    started = time.time()
                    result = subprocess.run([*command, block], cwd=temp, env=env, capture_output=True,
                                            text=True, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    run = RUN_LINE.search(result.stdout)
                    self.assertIsNotNone(run, f"the block printed no RUN line:\n{result.stdout}")
                    self.assertEqual(Path(run.group(1)).parent, Path(temp), "the block ignored TMPDIR")
                    # A later shell reads the run state from run.env.
                    state = subprocess.run(
                        [*command, f'. "{run.group(1)}/run.env"; printf "%s\\n" "$RUN" "$DEADLINE" "$STARTED"'],
                        cwd=temp, env=env, capture_output=True, text=True, timeout=30, check=True,
                    ).stdout.splitlines()
                    self.assertEqual(len(state), 3, state)
                    self.assertEqual(state[0], run.group(1))
                    self.assertRegex(state[1], r"^\d+$")
                    self.assertAlmostEqual(int(state[1]), started + 30 * 60, delta=60)
                    self.assertRegex(state[2], r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2} \S+$")

    def test_references_keep_the_claude_agent_bodies(self) -> None:
        for reference, (agent, substitutions) in REFERENCES.items():
            with self.subTest(reference=reference):
                copy = words((ANTIGRAVITY_SKILL / "references" / reference).read_text())
                self.assertIn(SKILL_DIR_SENTENCE, copy)
                self.assertEqual(
                    translated(agent_body(AGENTS / agent), substitutions),
                    words(copy.replace(SKILL_DIR_SENTENCE, "")),
                )

    def test_real_issue_examples_give_a_checkable_location_and_evidence(self) -> None:
        for skill in (CLAUDE_SKILL, ANTIGRAVITY_SKILL):
            path = skill / "references" / "dimensions.md"
            examples = list(real_issue_examples(path.read_text()))
            self.assertTrue(examples, f"{path} has no REAL ISSUE example")
            for number, lines in examples:
                with self.subTest(path=str(path.relative_to(PLUGIN_ROOT)), line=number):
                    location = next((line for line in lines if line.startswith("Location: ")), "")
                    self.assertRegex(location, CHECKABLE_LOCATION)
                    self.assertTrue(any(line.startswith("Evidence:") for line in lines),
                                    "no Evidence field")

    def test_agent_tools_lines_write_no_file_and_match_the_browser_servers(self) -> None:
        agents = {name: (AGENTS / name).read_text() for name in EVAL_AGENTS}
        self.assertEqual(tools_problems(agents, (CLAUDE_SKILL / "SKILL.md").read_text()), [])

    def test_tools_check_fails_on_a_planted_tool_or_a_dropped_prefix(self) -> None:
        agents = {name: (AGENTS / name).read_text() for name in EVAL_AGENTS}
        skill = (CLAUDE_SKILL / "SKILL.md").read_text()
        drop = (", mcp__playwright__*", "")
        cases = (
            ("Write in one agent", {"finding-verifier.md": ("tools: Read,", "tools: Read, Write,")},
             ["the tools lines differ", "finding-verifier.md has Write"]),
            ("Edit and NotebookEdit in both agents",
             {name: ("WebSearch,", "WebSearch, Edit, NotebookEdit,") for name in EVAL_AGENTS},
             [f"{name} has {tool}" for name in EVAL_AGENTS for tool in ("Edit", "NotebookEdit")]),
            ("a prefix dropped from one agent", {"project-evaluator.md": drop},
             ["the tools lines differ", "project-evaluator.md has the browser tools"]),
            ("a prefix dropped from both agents", {name: drop for name in EVAL_AGENTS},
             [f"{name} has the browser tools" for name in EVAL_AGENTS]),
        )
        for name, edits, expected in cases:
            with self.subTest(name):
                planted = dict(agents)
                for agent, (old, new) in edits.items():
                    self.assertIn(old, planted[agent])
                    planted[agent] = planted[agent].replace(old, new, 1)
                problems = tools_problems(planted, skill)
                self.assertEqual(len(problems), len(expected), problems)
                for problem, start in zip(problems, expected):
                    self.assertTrue(problem.startswith(start), problem)


if __name__ == "__main__":
    unittest.main()
