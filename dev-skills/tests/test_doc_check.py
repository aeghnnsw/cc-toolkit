"""Command-line checks for the doc-update doc check script."""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PLUGIN_ROOT / "skills" / "doc-update" / "scripts" / "doc_check.py"
COPIES = ("skills", "codex-skills", "antigravity-skills")
FINDING = re.compile(r"^(.+?):(\d+): ([a-z-]+): ", re.MULTILINE)

GUIDE = """\
# Setup guide

## 1. Install the tools

Text.

## Usage

## Usage

Configuration
-------------

<a id="custom-anchor"></a>
"""


def run_check(docs: dict[str, str], *names: str) -> tuple[int, set, str]:
    """Write the docs to a temporary repository and check the named docs.

    Return the exit status, the findings as (doc, line, rule), and all output.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".git").mkdir()
        for name, text in docs.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(SCRIPT), *names], cwd=root, capture_output=True, text=True
        )
    findings = {(doc, int(line), rule) for doc, line, rule in FINDING.findall(result.stdout)}
    return result.returncode, findings, result.stdout + result.stderr


class LinkTests(unittest.TestCase):
    def test_a_missing_link_target_fails(self):
        doc = "# Readme\n\nRead [the setup](docs/setup.md) and ![logo](img/logo.png).\n"
        code, findings, output = run_check({"README.md": doc}, "README.md")
        self.assertEqual(code, 1, output)
        self.assertEqual(findings, {("README.md", 3, "broken-link")}, output)
        self.assertIn("docs/setup.md does not exist", output)
        self.assertIn("img/logo.png does not exist", output)

    def test_links_that_resolve_pass(self):
        doc = (
            "# Readme\n\n"
            "Read [the guide](docs/guide.md), [the root guide](/docs/guide.md), and\n"
            "[the docs folder](docs/). See [the site](https://example.com/missing.md).\n"
            '<img src="docs/guide.md"> and [a definition][guide].\n\n'
            "[guide]: docs/guide.md\n\n"
            "```markdown\n[missing](missing.md)\n```\n\n"
            "Write `[missing](missing.md)` to link.\n"
        )
        code, findings, output = run_check({"README.md": doc, "docs/guide.md": GUIDE}, "README.md")
        self.assertEqual((code, findings), (0, set()), output)

    def test_a_missing_anchor_fails(self):
        doc = "# Readme\n\nRead [install](docs/guide.md#install).\n\nRead [usage](#usage).\n"
        code, findings, output = run_check({"README.md": doc, "docs/guide.md": GUIDE}, "README.md")
        self.assertEqual(code, 1, output)
        self.assertEqual(findings, {("README.md", 3, "broken-anchor"), ("README.md", 5, "broken-anchor")}, output)

    def test_anchors_that_resolve_pass(self):
        doc = (
            "# Readme\n\n"
            "## Next steps\n\n"
            "Read [install](docs/guide.md#1-install-the-tools), [usage](docs/guide.md#usage),\n"
            "[usage again](docs/guide.md#usage-1), [config](docs/guide.md#configuration),\n"
            "[custom](docs/guide.md#custom-anchor), and [next](#next-steps).\n"
        )
        code, findings, output = run_check({"README.md": doc, "docs/guide.md": GUIDE}, "README.md")
        self.assertEqual((code, findings), (0, set()), output)


class PathTests(unittest.TestCase):
    def test_a_missing_code_path_is_reported_and_does_not_fail(self):
        doc = "# Readme\n\nThe entry point is `src/missing.py`.\n"
        code, findings, output = run_check({"README.md": doc}, "README.md")
        self.assertEqual(code, 0, output)
        self.assertEqual(findings, {("README.md", 3, "path")}, output)

    def test_existing_paths_and_other_code_pass(self):
        doc = (
            "# Readme\n\n"
            "Edit `src/app.py`, `src/app.py:12`, `src/`, and `guide.md`, from the doc folder `../src/app.py`.\n"
            "Push to `origin/master`; run `git diff --stat`; set `<skill-dir>/scripts/x.py`.\n"
        )
        code, findings, output = run_check({"docs/README.md": doc, "src/app.py": ""}, "docs/README.md")
        self.assertEqual((code, findings), (0, set()), output)


class PhraseTests(unittest.TestCase):
    def test_backward_narrative_is_reported_and_does_not_fail(self):
        doc = (
            "# Install\n\n"
            "Previously, the installer used npm.\n"
            "The build used to run twice.\n"
            "We changed the default port.\n"
            "As of v1 this was optional.\n"
        )
        code, findings, output = run_check({"README.md": doc}, "README.md")
        self.assertEqual(code, 0, output)
        self.assertEqual(findings, {("README.md", line, "history") for line in (3, 4, 5, 6)}, output)

    def test_current_truth_and_quoted_phrases_pass(self):
        doc = (
            "# Install\n\n"
            "The installer uses pnpm. `oldFn` is deprecated; use `newFn`.\n"
            "Do not write `previously` in a doc.\n\n"
            "```text\nWe changed this as of v1.\n```\n"
        )
        code, findings, output = run_check({"README.md": doc}, "README.md")
        self.assertEqual((code, findings), (0, set()), output)

    def test_a_vague_reference_is_reported_and_does_not_fail(self):
        doc = "# Install\n\nSet the port (see above).\n\nAs mentioned earlier, run the build.\n"
        code, findings, output = run_check({"README.md": doc}, "README.md")
        self.assertEqual(code, 0, output)
        self.assertEqual(findings, {("README.md", 3, "see-above"), ("README.md", 5, "see-above")}, output)

    def test_explicit_references_pass(self):
        doc = "# Install\n\n## Port\n\nSet the port that [Port](#port) names. Run the build that the table below lists.\n"
        code, findings, output = run_check({"README.md": doc}, "README.md")
        self.assertEqual((code, findings), (0, set()), output)


class CommandTests(unittest.TestCase):
    def test_a_missing_doc_is_a_usage_error(self):
        code, findings, output = run_check({"README.md": "# Readme\n"}, "README.md", "missing.md")
        self.assertEqual(code, 2, output)
        self.assertIn("missing.md is not a file", output)

    def test_each_copy_runs_the_script(self):
        for copy in COPIES:
            with self.subTest(copy=copy):
                skill = (PLUGIN_ROOT / copy / "doc-update" / "SKILL.md").read_text(encoding="utf-8")
                self.assertTrue("python3 <skill-dir>/scripts/doc_check.py" in skill,
                                f"{copy}/doc-update/SKILL.md does not run the doc check")


if __name__ == "__main__":
    unittest.main()
