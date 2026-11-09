"""Contract checks for grill-with-research and its use in matt-automode.

The agreed decisions of issue #358 fix the description, the body limit, the
invocation policy, and the host-specific loading section. Issue #365 sets the
Matt skills that the wrapper loads. Issue #388 raises the body limit to 440
words for its condition rule. Agent behavior is checked by the scenario review
in grill-with-research-scenarios.md.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
HOSTS = ("skills", "codex-skills")
DESCRIPTION = (
    "Research the project, then grill the user only on decisions that research "
    "cannot settle; records glossary terms and ADRs. Use when the user asks to "
    "grill or stress-test a plan, design, or issue in the current project."
)
LOAD_HEADING = "## Load the Matt skills"
MATT_SKILLS = ("mattpocock-skills:grilling", "mattpocock-skills:domain-modeling")
BODY_WORD_LIMIT = 440


def split_skill(path: Path) -> tuple[dict[str, str], str]:
    _, header, body = path.read_text(encoding="utf-8").split("---\n", 2)
    fields = {}
    for line in header.splitlines():
        key, sep, value = line.partition(":")
        if sep:
            fields[key.strip()] = value.strip()
    return fields, body


def sections(body: str) -> dict[str, str]:
    """Map each level-2 heading, or "" for the text before the first, to its text."""
    parts = re.split(r"^(## .+)$", body, flags=re.M)
    found = {"": parts[0]}
    found.update(zip(parts[1::2], parts[2::2]))
    return found


def wrapper(host: str) -> tuple[dict[str, str], str]:
    """Return the frontmatter fields and the body of one host copy."""
    return split_skill(PLUGIN_ROOT / host / "grill-with-research" / "SKILL.md")


def load_section(host: str) -> str:
    _, body = wrapper(host)
    return sections(body)[LOAD_HEADING]


class GrillWithResearchTest(unittest.TestCase):
    def test_both_copies_carry_the_agreed_description(self) -> None:
        for host in HOSTS:
            fields, _ = wrapper(host)
            with self.subTest(host=host):
                self.assertEqual(fields["name"], "grill-with-research")
                self.assertEqual(fields["description"], DESCRIPTION)

    def test_the_model_can_start_the_skill_on_both_hosts(self) -> None:
        self.assertNotIn("disable-model-invocation", wrapper("skills")[0])
        policy = PLUGIN_ROOT / "codex-skills" / "grill-with-research" / "agents" / "openai.yaml"
        if policy.exists():
            self.assertNotIn("allow_implicit_invocation: false", policy.read_text(encoding="utf-8"))

    def test_copies_differ_only_in_how_they_load_skills(self) -> None:
        claude, codex = (sections(wrapper(host)[1]) for host in HOSTS)
        self.assertIn(LOAD_HEADING, claude)
        self.assertEqual(sorted(claude), sorted(codex))
        for heading in claude:
            if heading != LOAD_HEADING:
                self.assertEqual(claude[heading], codex[heading], f"{heading!r} differs between hosts")

    def test_each_copy_names_the_resolver_for_its_host(self) -> None:
        claude, codex = (load_section(host) for host in HOSTS)
        self.assertIn('"${CLAUDE_PLUGIN_ROOT}/scripts/resolve_skill.py"', claude)
        self.assertIn('"<plugin-root>/scripts/resolve_skill.py" --host codex', codex)

    def test_each_copy_names_grilling_and_domain_modeling_not_grill_with_docs(self) -> None:
        for host in HOSTS:
            _, body = wrapper(host)
            with self.subTest(host=host):
                for skill in MATT_SKILLS:
                    self.assertIn(skill, sections(body)[LOAD_HEADING])
                self.assertNotIn("grill-with-docs", body)

    def test_each_body_stays_within_the_word_limit(self) -> None:
        for host in HOSTS:
            words = len(wrapper(host)[1].split())
            with self.subTest(host=host, words=words):
                self.assertLessEqual(words, BODY_WORD_LIMIT)


class MattAutomodeUsesTheWrapperTest(unittest.TestCase):
    def test_phase_one_loads_the_wrapper_and_no_pressure_test_remains(self) -> None:
        for host in HOSTS:
            text = (PLUGIN_ROOT / host / "matt-automode" / "SKILL.md").read_text(encoding="utf-8")
            with self.subTest(host=host):
                self.assertIn("(../grill-with-research/SKILL.md)", text)
                self.assertNotRegex(text, r"(?i)pressure[- ]test")
                self.assertNotIn("design-critical", text)


if __name__ == "__main__":
    unittest.main()
