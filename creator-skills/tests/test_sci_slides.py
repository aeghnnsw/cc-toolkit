"""Host parity and link checks for the sci-slides skill."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PLUGIN_ROOT.parent
HOST_SKILLS = {
    "claude": PLUGIN_ROOT / "skills" / "sci-slides",
    "codex": PLUGIN_ROOT / "codex-skills" / "sci-slides",
}
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.MULTILINE)


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


def anchor(heading: str) -> str:
    slug = re.sub(r"[^\w\- ]", "", heading.strip().lower())
    return slug.replace(" ", "-")


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

    def test_relative_links_resolve(self) -> None:
        for skill_dir in HOST_SKILLS.values():
            for document in sorted(skill_dir.rglob("*.md")):
                for target in LINK.findall(document.read_text(encoding="utf-8")):
                    if re.match(r"[a-z]+:", target):
                        continue
                    path_part, _, fragment = target.partition("#")
                    linked = (document.parent / path_part).resolve() if path_part else document
                    with self.subTest(document=str(document), target=target):
                        self.assertTrue(linked.is_file(), f"missing {linked}")
                        if fragment:
                            headings = HEADING.findall(linked.read_text(encoding="utf-8"))
                            self.assertIn(fragment, [anchor(h) for h in headings])

    def test_supporting_files_registered_per_host(self) -> None:
        rules = json.loads((REPO_ROOT / "package-validation.json").read_text(encoding="utf-8"))
        registered = {
            (entry["path"], host)
            for entry in rules["plugins"]["creator-skills"]["resources"]
            for host in entry["hosts"]
        }
        for host, skill_dir in HOST_SKILLS.items():
            for name in supporting_files(skill_dir):
                path = (skill_dir / name).relative_to(PLUGIN_ROOT).as_posix()
                self.assertIn((path, host), registered)


if __name__ == "__main__":
    unittest.main()
