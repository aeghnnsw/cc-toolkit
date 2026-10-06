"""Host parity checks for the sci-slides skill."""

from __future__ import annotations

import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
HOST_SKILLS = {
    "claude": PLUGIN_ROOT / "skills" / "sci-slides",
    "codex": PLUGIN_ROOT / "codex-skills" / "sci-slides",
}


def split_skill(path: Path) -> tuple[dict[str, str], str]:
    _, header, body = path.read_text(encoding="utf-8").split("---\n", 2)
    fields = {}
    for line in header.splitlines():
        key, sep, value = line.partition(":")
        if sep:
            fields[key.strip()] = value.strip()
    return fields, body


def supporting_files(skill_dir: Path) -> dict[str, bytes]:
    return {
        path.relative_to(skill_dir).as_posix(): path.read_bytes()
        for path in sorted(skill_dir.rglob("*"))
        if path.is_file()
        and path.name != "SKILL.md"
        and not path.name.startswith(".")
        and "__pycache__" not in path.parts
    }


class SciSlidesParityTest(unittest.TestCase):
    def test_bodies_match(self) -> None:
        bodies = {host: split_skill(d / "SKILL.md")[1] for host, d in HOST_SKILLS.items()}
        self.assertEqual(bodies["claude"], bodies["codex"])

    def test_name_and_description_match(self) -> None:
        fields = {host: split_skill(d / "SKILL.md")[0] for host, d in HOST_SKILLS.items()}
        self.assertEqual(fields["claude"]["name"], "sci-slides")
        self.assertEqual(fields["codex"]["name"], "sci-slides")
        self.assertEqual(fields["claude"]["description"], fields["codex"]["description"])

    def test_supporting_files_match(self) -> None:
        claude = supporting_files(HOST_SKILLS["claude"])
        codex = supporting_files(HOST_SKILLS["codex"])
        self.assertEqual(sorted(claude), sorted(codex))
        for name in claude:
            self.assertEqual(claude[name], codex[name], f"{name} differs between hosts")


if __name__ == "__main__":
    unittest.main()
