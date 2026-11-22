"""Checks that each sci-figure-format copy states each rule value once."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
COPIES = sorted(PLUGIN_ROOT.glob("*skills/sci-figure-format/SKILL.md"))
VALUE = re.compile(r"\d[\d.]*\s*(?:pt|DPI|\"|inch(?:es)?|cm|mm)(?!\w)", re.IGNORECASE)
FORMAT = re.compile(r"\b(?:PDF|EPS|TIFF|PNG|JPE?G|SVG)\b")
# These lists give a value for one text element or one journal, not a rule.
DETAIL_LISTS = ("**Sizes:**", "**Journal-specific widths:**")


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


class SciFigureFormatTest(unittest.TestCase):
    def test_each_host_copy_is_checked(self) -> None:
        self.assertEqual(len(COPIES), 3, COPIES)

    def test_rule_values_are_only_in_the_standards_table(self) -> None:
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


if __name__ == "__main__":
    unittest.main()
