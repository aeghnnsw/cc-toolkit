"""Checks that each sci-figure-format copy states each rule value once, and that its font sizes meet the Font row."""

from __future__ import annotations

import itertools
import re
import tempfile
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
COPIES = sorted(PLUGIN_ROOT.glob("*skills/sci-figure-format/SKILL.md"))
VALUE = re.compile(r"\d[\d.]*\s*(?:pt|DPI|\"|inch(?:es)?|cm|mm)(?!\w)", re.IGNORECASE)
FORMAT = re.compile(r"\b(?:PDF|EPS|TIFF|PNG|JPE?G|SVG)\b")
# These lists give a value for one text element or one journal, not a rule.
# size_problems checks the Sizes list against the Font row.
DETAIL_LISTS = ("**Sizes:**", "**Journal-specific widths:**")
FONT_LIMITS = re.compile(r"(\d[\d.]*)-(\d[\d.]*) pt target, (\d[\d.]*) pt hard minimum")
SIZE = re.compile(r"- [^:]+: (\d[\d.]*) pt")


def split_body(path: Path) -> tuple[list[str], list[str]]:
    """Return the Universal Standards table rows and the other body lines, without the detail lists."""
    table, other = [], []
    in_standards = in_detail = False
    for line in path.read_text(encoding="utf-8").split("---\n", 2)[2].splitlines():
        if line.startswith("## "):
            in_standards = line.startswith("## Universal Standards")
        if line.strip() in DETAIL_LISTS:
            in_detail = True
        elif not line.strip():
            in_detail = False
        if in_standards and line.startswith("|"):
            table.append(line)
        elif not in_detail:
            other.append(line)
    return table, other


def size_problems(path: Path) -> list[str]:
    """Return each Sizes item without a pt size, under the Font row minimum, or outside its target range."""
    table, _ = split_body(path)
    font_row = next(row for row in table if row.startswith("| **Font**"))
    limits = FONT_LIMITS.search(font_row)
    if not limits:
        return [f"no target range and minimum in the Font row: {font_row}"]
    low, high, minimum = (float(value) for value in limits.groups())
    lines = path.read_text(encoding="utf-8").splitlines()
    items = itertools.takewhile(str.strip, lines[lines.index("**Sizes:**") + 1 :])
    problems = []
    for item in items:
        size = SIZE.fullmatch(item.strip())
        if not size or not (minimum <= float(size[1]) and low <= float(size[1]) <= high):
            problems.append(item.strip())
    return problems


class SciFigureFormatTest(unittest.TestCase):
    def test_rule_values_are_only_in_the_standards_table(self) -> None:
        self.assertEqual(len(COPIES), 3, COPIES)
        for path in COPIES:
            table, other = split_body(path)
            with self.subTest(copy=str(path.relative_to(PLUGIN_ROOT))):
                self.assertTrue(table)
                repeated = [line.strip() for line in other if VALUE.search(line)]
                self.assertEqual(repeated, [], "give the value once, in the Universal Standards table")

    def test_each_named_format_is_in_the_standards_table(self) -> None:
        for path in COPIES:
            table, other = split_body(path)
            with self.subTest(copy=str(path.relative_to(PLUGIN_ROOT))):
                format_row = next(row for row in table if row.startswith("| **Format**"))
                named = {name for line in other for name in FORMAT.findall(line)}
                self.assertLessEqual(named, set(FORMAT.findall(format_row)))

    def test_each_size_meets_the_font_row(self) -> None:
        for path in COPIES:
            with self.subTest(copy=str(path.relative_to(PLUGIN_ROOT))):
                self.assertEqual(size_problems(path), [], "give each size inside the Font row limits")

    def test_a_size_under_the_minimum_fails(self) -> None:
        text, count = re.subn(r"(?m)^- Legend: .*$", "- Legend: 4 pt", COPIES[0].read_text(encoding="utf-8"))
        self.assertEqual(count, 1)
        with tempfile.TemporaryDirectory() as folder:
            copy = Path(folder) / "SKILL.md"
            copy.write_text(text, encoding="utf-8")
            self.assertEqual(size_problems(copy), ["- Legend: 4 pt"])


if __name__ == "__main__":
    unittest.main()
