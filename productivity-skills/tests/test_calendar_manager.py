"""Check the calendar-manager skill copies against the usage text of the Calendar CLI.

The checks read scripts/productivity-cli.swift as text. They do not run Swift and do not
open Calendar. tests/test_host_copies.py at the repository root compares the bodies of the
three copies.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
CLI = PLUGIN_ROOT / "scripts" / "productivity-cli.swift"
COPIES = {
    "claude-code": PLUGIN_ROOT / "skills" / "calendar-manager" / "SKILL.md",
    "codex": PLUGIN_ROOT / "codex-skills" / "calendar-manager" / "SKILL.md",
    "antigravity": PLUGIN_ROOT / "antigravity-skills" / "calendar-manager" / "SKILL.md",
}
FLAG = re.compile(r"--[a-z][a-z-]*")
# Words that name an edit of an existing event. The CLI has no such command.
EDIT_WORDS = ("update", "edit", "modify", "reschedule", "rename", "move", "change")


def usage() -> dict[str, tuple[set[str], set[str]]]:
    """Map each `calendars` command of printUsage to its (required, optional) flags."""
    source = CLI.read_text(encoding="utf-8")
    body = source[source.index("func printUsage()"):]
    start = body.index('"""') + 3
    commands: dict[str, list[str]] = {}
    current = None
    for line in body[start:body.index('"""', start)].splitlines():
        text = line.strip()
        if text.startswith("calendars "):
            current = text.split()[1]
            commands[current] = []
        elif not (current and text.startswith("[")):
            current = None if not text else current  # a description line keeps the command
            continue
        commands[current].append(re.split(r"\s{2,}", text)[0])  # drop the description column
    result = {}
    for command, parts in commands.items():
        syntax = " ".join(parts)
        required = set(FLAG.findall(re.sub(r"\[[^\]]*\]", "", syntax)))
        result[command] = (required, set(FLAG.findall(syntax)) - required)
    return result


def command_lines(text: str) -> list[tuple[str, str]]:
    """Return (command, arguments) for each CLI call in the text, with its continuation lines."""
    calls = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = re.search(r'productivity-cli\.swift" calendars (\S+)(.*)', line)
        if not match:
            continue
        arguments = match.group(2)
        while arguments.rstrip().endswith("\\"):
            index += 1
            arguments = arguments.rstrip()[:-1] + " " + lines[index]
        calls.append((match.group(1), arguments))
    return calls


class CalendarManagerCopies(unittest.TestCase):
    def setUp(self) -> None:
        self.usage = usage()
        self.assertIn("delete", self.usage)
        self.assertIn("create", self.usage)

    def test_delete_requires_calendar_and_one_match(self) -> None:
        required, optional = self.usage["delete"]
        self.assertEqual(required, {"--title", "--date", "--calendar"})
        self.assertEqual(optional, {"--all-future", "--all-matches"})
        source = CLI.read_text(encoding="utf-8")
        start = source.index("func deleteEvent(")
        delete = source[start:source.index("\nfunc ", start + 1)]
        # The arguments are checked before Calendar access, so a call without --calendar reads nothing.
        self.assertLess(delete.index('guard let calendarName = args["calendar"], !calendarName.isEmpty'),
                        delete.index("requestCalendarAccess()"))
        # More than one match deletes nothing unless --all-matches is given.
        guard = re.search(r'if events\.count > 1 && args\["all-matches"\] != "true" \{(.*?)\n    \}',
                          delete, re.DOTALL)
        self.assertIsNotNone(guard, "deleteEvent has no guard for more than one match")
        self.assertIn("exit(1)", guard.group(1))
        self.assertLess(guard.end(), delete.index("store.remove("))

    def test_skill_names_only_commands_and_flags_of_the_cli(self) -> None:
        flags = set().union(*(required | optional for required, optional in self.usage.values()))
        for copy, path in COPIES.items():
            text = path.read_text(encoding="utf-8")
            with self.subTest(copy=copy):
                calls = command_lines(text)
                self.assertTrue(calls)
                for command, arguments in calls:
                    self.assertIn(command, self.usage, f"{copy}: no CLI command `calendars {command}`")
                    required, optional = self.usage[command]
                    used = set(FLAG.findall(arguments))
                    self.assertLessEqual(used, required | optional, f"{copy}: calendars {command}{arguments}")
                    self.assertLessEqual(required, used, f"{copy}: calendars {command} lacks a required flag")
                self.assertLessEqual(set(FLAG.findall(text)), flags, f"{copy}: a flag that the CLI lacks")
                for word in EDIT_WORDS:
                    if word not in self.usage:
                        found = re.search(rf"\b{word}\w*", text, re.IGNORECASE)
                        self.assertIsNone(found, f"{copy}: names `{found and found.group()}`, "
                                                 "but the CLI has no command for it")


if __name__ == "__main__":
    unittest.main()
