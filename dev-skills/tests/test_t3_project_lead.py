"""The t3-project-lead script prints the step that an agent asks for, and its skill copies match."""
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
STEPS = ("start", "plan", "dispatch", "brief", "answer", "flag", "verify", "report")
# An agent reads a whole step after each wake, so each step stays short.
STEP_WORD_LIMIT = 120
ALLOWED_MODELS = json.loads((PLUGIN_ROOT.parent / "allowed-models.json").read_text(encoding="utf-8"))
MODEL_ID = re.compile(r"\b(?:claude-[a-z]+|gpt)-\d(?:[\w.-]*\w)?")
HOSTS = ("skills", "codex-skills", "antigravity-skills")
DESCRIPTION = ("Use when the user invokes t3-project-lead to lead a T3 Code project: plan worker tasks, dispatch T3 "
               "workers, and verify their results, without implementing in the lead.")
# The frontmatter fields of each host copy (CONTRIBUTING.md, "Skills for more than one host").
FIELDS = {
    "skills": {"name", "version", "description", "disable-model-invocation"},
    "codex-skills": {"name", "description"},
    "antigravity-skills": {"name", "description", "disable-model-invocation"},
}
PLUGIN_ROOT_LINE = "`<plugin-root>` is two levels above this folder."
BODY_WORD_LIMIT = 300
MATT_AUTOMODE = [PLUGIN_ROOT / folder / "matt-automode" / "SKILL.md"
                 for folder in ("skills", "codex-skills", "antigravity-skills")]


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, check=False)


@functools.lru_cache(maxsize=None)
def step(name):
    result = run(name)
    if result.returncode:
        raise AssertionError(f"{name} exited {result.returncode}: {result.stderr}")
    return result.stdout


def next_line(name):
    """Return the text from the step's last "Next:" to its end, on one line."""
    text = step(name)
    return " ".join(text[text.rfind("Next:"):].split())


def references(name):
    """Return the steps that a step names: after t3_project_lead.py anywhere, and each step word in its Next line."""
    text = step(name)
    named = set(re.findall(r"t3_project_lead\.py (\w+)", text))
    named |= {word for word in re.findall(r"\w+", next_line(name)) if word in STEPS}
    unknown = named - set(STEPS)
    if unknown:
        raise AssertionError(f"{name} names unknown steps {sorted(unknown)}")
    return named


def split_skill(host):
    _, header, body = (PLUGIN_ROOT / host / "t3-project-lead" / "SKILL.md").read_text(encoding="utf-8").split("---\n", 2)
    fields = {}
    for line in header.splitlines():
        key, sep, value = line.partition(":")
        if sep:
            fields[key.strip()] = value.strip().strip('"')
    return fields, body


def shared_text(host):
    """Return a copy's body on one line, with the plugin-root path written as in the Codex copy."""
    text = " ".join(split_skill(host)[1].split())
    return text.replace("${CLAUDE_PLUGIN_ROOT}", "<plugin-root>").replace(f" {PLUGIN_ROOT_LINE}", "")


class SkillCopyTests(unittest.TestCase):
    def test_each_copy_has_the_frontmatter_of_its_host(self):
        for host in HOSTS:
            with self.subTest(host=host):
                fields, _ = split_skill(host)
                self.assertEqual(set(fields), FIELDS[host])
                self.assertEqual(fields["name"], "t3-project-lead")
                self.assertEqual(fields["description"], DESCRIPTION)
                if "disable-model-invocation" in fields:
                    self.assertEqual(fields["disable-model-invocation"], "true")

    def test_codex_copy_is_user_invoked(self):
        text = (PLUGIN_ROOT / "codex-skills" / "t3-project-lead" / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^policy:\n  allow_implicit_invocation: false$")
        self.assertIn("$dev-skills:t3-project-lead", text)

    def test_copies_say_the_same(self):
        for host in HOSTS[1:]:
            with self.subTest(host=host):
                self.assertIn(PLUGIN_ROOT_LINE, " ".join(split_skill(host)[1].split()))
                self.assertEqual(shared_text(host), shared_text("skills"))

    def test_skill_starts_the_script_and_stays_short(self):
        _, body = split_skill("skills")
        self.assertIn('python3 "${CLAUDE_PLUGIN_ROOT}/scripts/t3_project_lead.py" start', body)
        self.assertLessEqual(len(body.split()), BODY_WORD_LIMIT)


class StepTests(unittest.TestCase):
    def test_start_prints_the_lead_role(self):
        self.assertIn("You plan, dispatch, and verify. Workers implement.", step("start"))

    def test_each_step_is_short(self):
        for name in STEPS:
            with self.subTest(step=name):
                self.assertLessEqual(len(step(name).split()), STEP_WORD_LIMIT)

    def test_each_step_ends_with_real_next_steps(self):
        for name in STEPS:
            with self.subTest(step=name):
                self.assertRegex(next_line(name), r"^Next: .*\bt3_project_lead\.py \w+")
                references(name)

    def test_every_step_can_be_reached_from_start(self):
        reached, queue = {"start"}, ["start"]
        while queue:
            for name in references(queue.pop()) - reached:
                reached.add(name)
                queue.append(name)
        self.assertEqual(reached, set(STEPS))

    def test_flag_retries_on_the_claude_fallback_model(self):
        fallback = ALLOWED_MODELS["claude"]["fallback"]
        self.assertIn(f"new worker on {fallback}", " ".join(step("flag").split()))
        for name in STEPS:
            with self.subTest(step=name):
                self.assertLessEqual(set(MODEL_ID.findall(step(name))), {fallback})

    def test_worker_lines_match_matt_automode(self):
        brief = " ".join(step("brief").split())
        verify = " ".join(step("verify").split())
        self.assertIn('Line 2: "A leader runs the retrospective for this run."', brief)
        self.assertIn("Run only its Navigation retrospective", verify)
        for path in MATT_AUTOMODE:
            with self.subTest(path=path.relative_to(PLUGIN_ROOT)):
                text = path.read_text(encoding="utf-8")
                self.assertIn("When the task says that a leader runs the retrospective for this run",
                              " ".join(text.split()))
                self.assertRegex(text, r"(?m)^## Navigation retrospective$")

    def test_grill_with_research_lets_the_brief_continue_in_matt_automode(self):
        self.assertIn("continue in this thread with the matt-automode skill of dev-skills", " ".join(step("brief").split()))
        for host in HOSTS:
            with self.subTest(host=host):
                text = (PLUGIN_ROOT / host / "grill-with-research" / "SKILL.md").read_text(encoding="utf-8")
                self.assertIn("Start no implementation or automode unless the task says so.", " ".join(text.split()))

    def test_script_uses_only_the_standard_library_and_runs_no_command(self):
        tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
        modules = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import)
                   for alias in node.names}
        modules |= {node.module.split(".")[0] for node in ast.walk(tree)
                    if isinstance(node, ast.ImportFrom) and node.module}
        self.assertLessEqual(modules, set(sys.stdlib_module_names))
        self.assertFalse(modules & {"os", "subprocess", "shutil", "pty"}, modules)

    def test_an_unknown_step_fails(self):
        result = run("merge")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid choice", result.stderr)


if __name__ == "__main__":
    unittest.main()
