"""Contract checks for grill-with-research and its use in matt-automode.

The agreed decisions of issue #358 fix the description, the body limit, the
invocation policy, and the host-specific loading section. Issue #365 sets the
Matt skills that the wrapper loads. Issue #388 raises the body limit to 440
words for its condition rule. Issue #432 adds the Antigravity copies and the
Antigravity sessions of the matt-automode retrospective. Issue #448 lets a
task, such as a t3-project-lead brief, name automode for after the user
approves the design, and raises the body limit to 450 words for that rule.
Agent behavior is checked by the scenario review in
grill-with-research-scenarios.md.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
HOSTS = ("skills", "codex-skills", "antigravity-skills")
DESCRIPTION = (
    "Research the project, then grill the user only on decisions that research "
    "cannot settle; records glossary terms and ADRs. Use when the user asks to "
    "grill or stress-test a plan, design, or issue in the current project."
)
LOAD_HEADING = "## Load the Matt skills"
MATT_SKILLS = ("mattpocock-skills:grilling", "mattpocock-skills:domain-modeling")
BODY_WORD_LIMIT = 450
RESOLVER = {
    "skills": '"${CLAUDE_PLUGIN_ROOT}/scripts/resolve_skill.py"',
    "codex-skills": '"<plugin-root>/scripts/resolve_skill.py" --host codex',
    "antigravity-skills": '"<plugin-root>/scripts/resolve_skill.py" --host antigravity',
}
# Each copy stops at the setting that makes a Matt skill user-invoked on its host.
USER_INVOKED_SETTING = {
    "skills": "`disable-model-invocation: true`",
    "codex-skills": "`allow_implicit_invocation: false`",
    "antigravity-skills": "`disable-model-invocation: true`",
}
RETRO_HEADING = "## Navigation retrospective"
# Issue #458: the retrospective reads the sessions of every host, including
# Antigravity, with the session script that dev-skills ships.
SESSION_COMMAND = ('`python3 "<plugin-root>/scripts/retro_sessions.py" --repo . '
                   '--after <cutoff> --output <new-dir>`')


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


def automode(host: str) -> str:
    """Return the text of one host copy of matt-automode."""
    return (PLUGIN_ROOT / host / "matt-automode" / "SKILL.md").read_text(encoding="utf-8")


class GrillWithResearchTest(unittest.TestCase):
    def test_every_copy_carries_the_agreed_description(self) -> None:
        for host in HOSTS:
            fields, _ = wrapper(host)
            with self.subTest(host=host):
                self.assertEqual(fields["name"], "grill-with-research")
                self.assertEqual(fields["description"], DESCRIPTION)

    def test_the_model_can_start_the_skill_on_every_host(self) -> None:
        for host in ("skills", "antigravity-skills"):
            with self.subTest(host=host):
                self.assertNotIn("disable-model-invocation", wrapper(host)[0])
        policy = PLUGIN_ROOT / "codex-skills" / "grill-with-research" / "agents" / "openai.yaml"
        if policy.exists():
            self.assertNotIn("allow_implicit_invocation: false", policy.read_text(encoding="utf-8"))

    def test_copies_differ_only_in_how_they_load_skills(self) -> None:
        claude = sections(wrapper("skills")[1])
        self.assertIn(LOAD_HEADING, claude)
        for host in HOSTS[1:]:
            other = sections(wrapper(host)[1])
            with self.subTest(host=host):
                self.assertEqual(sorted(claude), sorted(other))
                for heading in claude:
                    if heading != LOAD_HEADING:
                        self.assertEqual(claude[heading], other[heading], f"{heading!r} differs from {host}")

    def test_each_copy_names_the_resolver_for_its_host(self) -> None:
        for host in HOSTS:
            with self.subTest(host=host):
                self.assertIn(RESOLVER[host], load_section(host))

    def test_each_copy_stops_at_a_user_invoked_matt_skill(self) -> None:
        for host in HOSTS:
            with self.subTest(host=host):
                self.assertIn(USER_INVOKED_SETTING[host], load_section(host))

    def test_each_copy_names_grilling_and_domain_modeling_not_grill_with_docs(self) -> None:
        for host in HOSTS:
            _, body = wrapper(host)
            with self.subTest(host=host):
                for skill in MATT_SKILLS:
                    self.assertIn(skill, sections(body)[LOAD_HEADING])
                self.assertNotIn("grill-with-docs", body)

    def test_a_task_can_start_automode_after_grilling(self) -> None:
        for host in HOSTS:
            with self.subTest(host=host):
                self.assertIn("Start no implementation. Start automode only when the task names it for "
                              "after the user approves the design.", " ".join(wrapper(host)[1].split()))

    def test_each_body_stays_within_the_word_limit(self) -> None:
        for host in HOSTS:
            words = len(wrapper(host)[1].split())
            with self.subTest(host=host, words=words):
                self.assertLessEqual(words, BODY_WORD_LIMIT)


class MattAutomodeUsesTheWrapperTest(unittest.TestCase):
    def test_phase_one_loads_the_wrapper_and_no_pressure_test_remains(self) -> None:
        for host in HOSTS:
            text = automode(host)
            with self.subTest(host=host):
                self.assertIn("(../grill-with-research/SKILL.md)", text)
                self.assertNotRegex(text, r"(?i)pressure[- ]test")
                self.assertNotIn("design-critical", text)

    def test_each_copy_names_the_resolver_for_its_host(self) -> None:
        for host in HOSTS:
            with self.subTest(host=host):
                self.assertIn(RESOLVER[host], automode(host))


class AntigravityCopiesTest(unittest.TestCase):
    """Issue #432: the Antigravity copies use Antigravity terms and sessions."""

    def test_antigravity_automode_keeps_its_task_list_in_a_task_artifact(self) -> None:
        text = automode("antigravity-skills")
        self.assertIn("Markdown task list", text)
        self.assertIn("task artifact, never in a tracked file", text)

    def test_every_retrospective_runs_the_session_script_with_one_text(self) -> None:
        # The plugin root is the one host-specific part of the retrospective (#446).
        retros = {host: sections(automode(host))[RETRO_HEADING].replace(
            "${CLAUDE_PLUGIN_ROOT}", "<plugin-root>") for host in HOSTS}
        for host in HOSTS:
            with self.subTest(host=host):
                self.assertIn(SESSION_COMMAND, retros[host])
                self.assertNotIn("conversation_summaries.db", retros[host])
                self.assertEqual(retros[host], retros["skills"])


if __name__ == "__main__":
    unittest.main()
