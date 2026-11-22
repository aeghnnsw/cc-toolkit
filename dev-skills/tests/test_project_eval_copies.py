"""The Antigravity project-eval references keep the text of the Claude Code agents.

The Antigravity copy has no plugin agents, so its evaluator and verifier
instructions are skill-local copies of the Claude Code agent bodies. Each
comparison allows only the listed host-specific substitutions.
tests/test_host_copies.py compares the files that both skill copies have.
"""

from __future__ import annotations

import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
ANTIGRAVITY_SKILL = PLUGIN_ROOT / "antigravity-skills" / "project-eval"
AGENTS = PLUGIN_ROOT / "claude-agents"

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


if __name__ == "__main__":
    unittest.main()
