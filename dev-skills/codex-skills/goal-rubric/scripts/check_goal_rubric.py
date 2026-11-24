#!/usr/bin/env python3
"""Check the shape of a saved goal rubric, goal-rubric-<slug>.md.

The rubric has the Rubric Shape of the goal-rubric skill: a `## Criteria`
section with numbered criteria, a `## Stop clause` section, and a
`## /goal condition` section. The check prints one line for each finding on
stdout as ``<file>:<line>: <level>: <detail>``, then a summary line.

Errors:
- the Criteria section is missing or has no numbered criterion;
- a criterion has no "End state:" or "Check:" part, or the part is empty;
- the Stop clause section is missing or empty;
- the /goal condition section is missing or empty, or the condition is
  longer than 4,000 characters, the Claude Code /goal length limit. The
  limit applies to the condition for every tool. When the section is one
  fenced code block, the fence lines do not count.

A warning names a vague word (mostly, clean, good, appropriate) in a
criterion or in the condition, outside inline code. Warnings do not fail
the check.

Exit status: 0 with no error, 1 with an error, 2 when the file cannot be
read. Python 3.9 or newer, standard library only.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field

CONDITION_LIMIT = 4000
VAGUE_WORDS = ("mostly", "clean", "good", "appropriate")

HEADING = re.compile(r"^(#{1,2})\s+(.*?)\s*$")
FENCE = re.compile(r"^\s{0,3}(```|~~~)")
SECTIONS = {
    "criteria": re.compile(r"criteria\b", re.IGNORECASE),
    "stop": re.compile(r"stop clause\b", re.IGNORECASE),
    "condition": re.compile(r"/goal condition\b", re.IGNORECASE),
}
SECTION_NAMES = {"criteria": "Criteria", "stop": "Stop clause", "condition": "/goal condition"}
CRITERION = re.compile(r"^\s{0,3}(\d+)[.)]\s+")
PART = re.compile(r"\b(End state|Check|Constraint):", re.IGNORECASE)
REQUIRED_PARTS = ("End state", "Check")
INLINE_CODE = re.compile(r"`[^`]*`")
VAGUE = re.compile(r"\b(" + "|".join(VAGUE_WORDS) + r")\b", re.IGNORECASE)


@dataclass
class Section:
    line: int
    body: list[tuple[int, str]] = field(default_factory=list)


@dataclass
class Criterion:
    number: str
    line: int
    lines: list[tuple[int, str]] = field(default_factory=list)


def split_sections(lines: list[str]) -> dict[str, Section]:
    """Return the first Criteria, Stop clause, and /goal condition sections.

    A section runs from its `##` heading to the next `#` or `##` heading.
    A heading inside a fenced code block does not count.
    """
    sections: dict[str, Section] = {}
    current = None
    in_fence = False
    for number, line in enumerate(lines, 1):
        heading = None if in_fence else HEADING.match(line)
        if FENCE.match(line):
            in_fence = not in_fence
        if heading:
            current = None
            if heading.group(1) == "##":
                for key, pattern in SECTIONS.items():
                    if pattern.match(heading.group(2)) and key not in sections:
                        current = sections[key] = Section(number)
                        break
            continue
        if current is not None:
            current.body.append((number, line))
    return sections


def has_text(text: str) -> bool:
    return re.search(r"\w", text) is not None


def split_criteria(body: list[tuple[int, str]]) -> list[Criterion]:
    """Return the numbered criteria; a line that starts no criterion continues the one before it."""
    criteria: list[Criterion] = []
    for number, line in body:
        start = CRITERION.match(line)
        if start:
            criteria.append(Criterion(start.group(1), number))
        if criteria and line.strip():
            criteria[-1].lines.append((number, line))
    return criteria


def criterion_errors(criterion: Criterion) -> list[str]:
    text = " ".join(line.strip() for _, line in criterion.lines)
    marks = list(PART.finditer(text))
    parts: dict[str, str] = {}
    for index, mark in enumerate(marks):
        end = marks[index + 1].start() if index + 1 < len(marks) else len(text)
        name = mark.group(1).capitalize()
        parts.setdefault(name, text[mark.end():end])
    errors = []
    for name in REQUIRED_PARTS:
        if name not in parts:
            errors.append(f'criterion {criterion.number} has no "{name}:" part')
        elif not has_text(parts[name]):
            errors.append(f'criterion {criterion.number} has an empty "{name}:" part')
    return errors


def condition_text(body: list[tuple[int, str]]) -> str:
    """Return the condition: the section text, without the fence lines of one enclosing code block."""
    lines = [line for _, line in body]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if len(lines) >= 2 and FENCE.match(lines[0]) and FENCE.match(lines[-1]):
        lines = lines[1:-1]
    return "\n".join(lines).strip()


def vague_words(lines: list[tuple[int, str]]) -> list[tuple[int, str]]:
    found = []
    for number, line in lines:
        for match in VAGUE.finditer(INLINE_CODE.sub(" ", line)):
            found.append((number, match.group(1).lower()))
    return found


def check(text: str) -> tuple[list[tuple[int, str]], list[tuple[int, str]], dict]:
    """Return the errors and warnings, each as (line, detail) with line 0 for the file, and the counts."""
    sections = split_sections(text.splitlines())
    errors: list[tuple[int, str]] = []
    warned: list[tuple[int, str]] = []
    for key in ("criteria", "stop", "condition"):
        if key not in sections:
            errors.append((0, f"the rubric has no {SECTION_NAMES[key]} section"))

    criteria: list[Criterion] = []
    if "criteria" in sections:
        criteria = split_criteria(sections["criteria"].body)
        if not criteria:
            errors.append((sections["criteria"].line, "the Criteria section has no numbered criterion"))
        for criterion in criteria:
            errors.extend((criterion.line, detail) for detail in criterion_errors(criterion))
            warned.extend(vague_words(criterion.lines))

    if "stop" in sections and not any(has_text(line) for _, line in sections["stop"].body):
        errors.append((sections["stop"].line, "the Stop clause section is empty"))

    length = None
    if "condition" in sections:
        section = sections["condition"]
        condition = condition_text(section.body)
        length = len(condition)
        if not has_text(condition):
            errors.append((section.line, "the /goal condition section is empty"))
        elif length > CONDITION_LIMIT:
            errors.append((section.line, f"the /goal condition has {length:,} characters; the limit is "
                           f"{CONDITION_LIMIT:,}"))
        warned.extend(vague_words(section.body))

    warnings = [(number, f'vague word "{word}"') for number, word in sorted(set(warned))]
    return errors, warnings, {"criteria": len(criteria), "condition": length}


def plural(count: int, one: str, many: str) -> str:
    return f"{count} {one if count == 1 else many}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_goal_rubric.py",
        description="Check the shape of a saved goal rubric. Exit status: 0 with no error, 1 with an error, "
        "2 when the file cannot be read.",
    )
    parser.add_argument("rubric", help="the rubric file, for example goal-rubric-<slug>.md")
    args = parser.parse_args(argv)
    try:
        with open(args.rubric, encoding="utf-8") as handle:
            text = handle.read()
    except (OSError, UnicodeDecodeError) as error:
        reason = error.strerror if isinstance(error, OSError) else "the file is not UTF-8 text"
        print(f"check_goal_rubric.py: cannot read {args.rubric}: {reason}", file=sys.stderr)
        return 2

    errors, warnings, counts = check(text)
    findings = [(number, "error", detail) for number, detail in errors]
    findings += [(number, "warning", detail) for number, detail in warnings]
    for number, level, detail in sorted(findings, key=lambda finding: finding[0]):
        where = f"{args.rubric}:{number}" if number else args.rubric
        print(f"{where}: {level}: {detail}")
    if counts["condition"] is None:
        condition = "no condition"
    else:
        condition = f"a {counts['condition']:,}-character condition (limit {CONDITION_LIMIT:,})"
    print(f"{args.rubric}: {plural(counts['criteria'], 'criterion', 'criteria')}, {condition}: "
          f"{plural(len(errors), 'error', 'errors')}, {plural(len(warnings), 'warning', 'warnings')}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
