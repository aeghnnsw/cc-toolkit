"""The Antigravity project-eval references keep the text of the Claude Code agents.

The Antigravity copy has no plugin agents, so its evaluator and verifier
instructions are skill-local copies of the Claude Code agent bodies. Each
comparison allows only the listed host-specific substitutions.
tests/test_host_copies.py compares the files that both skill copies have.
The calibration examples of real issues in both copies follow the evidence
rule, because evaluators copy them.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
CLAUDE_SKILL = PLUGIN_ROOT / "skills" / "project-eval"
ANTIGRAVITY_SKILL = PLUGIN_ROOT / "antigravity-skills" / "project-eval"
AGENTS = PLUGIN_ROOT / "claude-agents"

# A location that a verifier can check: `path:N` or `path:N-M`, a URL, or a command.
CHECKABLE_LOCATION = re.compile(r"`[^`\s]+:\d+(?:-\d+)?`|https?://\S+|command `[^`]+`")

SKILL_DIR_SENTENCE = "`<skill-dir>` is the parent of the `references/` folder that holds this file."
COMMON_SUBSTITUTIONS = (
    ("${CLAUDE_PLUGIN_ROOT}/skills/project-eval/references/", "<skill-dir>/references/"),
    ("The dispatch prompt gives you:", "The prompt that started you gives you:"),
)
REFERENCES = {
    "evaluator.md": ("project-evaluator.md", COMMON_SUBSTITUTIONS + (
        ("have an app URL.", "have an app URL and the session has browser tools."),
        ("If you have no browser tools, or the session refuses",
         "If the session has no browser tools, or it refuses"),
    )),
    "verifier.md": ("finding-verifier.md", COMMON_SUBSTITUTIONS),
}


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


class ProjectEvalCopiesTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
