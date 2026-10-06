"""Links and required resources for every skill a registered host discovers."""
import importlib.util
import json
import os
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('validate_packages', ROOT / 'scripts' / 'validate_packages.py')
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)

FENCE = re.compile(r'^[ \t]*(```|~~~).*?^[ \t]*\1', re.MULTILINE | re.DOTALL)
LINK = re.compile(r'\[[^\]]*\]\(([^)\s]+)\)')
HEADING = re.compile(r'^#{1,6}\s+(.+?)\s*$', re.MULTILINE)
RUN_PATH = re.compile(r'(\$\{CLAUDE_PLUGIN_ROOT\}|<plugin-root>|<skill-dir>)/([\w./-]+)')


def discover():
    """Return each host package with the SKILL.md files found in its skill roots."""
    found = []
    for package in validator.load_packages(ROOT).values():
        roots = [ROOT / package.source / path
                 for field, path in validator.discovery_paths(ROOT, package) if field == 'skills']
        found.append((package, roots, [skill for root in roots for skill in sorted(root.glob('*/SKILL.md'))]))
    return found


def anchors(document):
    text = FENCE.sub('', document.read_text(encoding='utf-8'))
    return {re.sub(r'[^\w\- ]', '', heading.strip().lower()).replace(' ', '-')
            for heading in HEADING.findall(text)}


def references(package, skill):
    """Yield (document, reference, target, fragment) for each document a skill reaches."""
    source = ROOT / package.source
    pending, seen = [skill], {skill}
    while pending:
        document = pending.pop()
        text = document.read_text(encoding='utf-8')
        found = [(document.parent, value) for value in LINK.findall(FENCE.sub('', text))
                 if not re.match(r'[a-z]+:', value)]
        found += [(skill.parent if base == '<skill-dir>' else source, path.rstrip('.'))
                  for base, path in RUN_PATH.findall(text)]
        for base, value in dict.fromkeys(found):
            path, _, fragment = value.partition('#')
            target = Path(os.path.normpath(base / path)) if path else document
            yield document, value, target, fragment
            if (target.suffix == '.md' and target.name != 'SKILL.md' and target.is_file()
                    and target not in seen and target.resolve().is_relative_to(source.resolve())):
                seen.add(target)
                pending.append(target)


class SkillLinkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.packages = discover()
        cls.skills = [(package, skill) for package, _, skills in cls.packages for skill in skills]
        cls.discovered = {(package.host, skill) for package, skill in cls.skills}

    def test_each_skill_root_has_skills(self):
        for package, roots, skills in self.packages:
            if roots:
                with self.subTest(plugin=package.name, host=package.host):
                    self.assertTrue(skills, f'no SKILL.md found under {roots}')
        self.assertEqual({package.host for package, _ in self.skills}, set(validator.REGISTRIES))

    def test_references_resolve_inside_package(self):
        checked = 0
        for package, skill in self.skills:
            source = (ROOT / package.source).resolve()
            for document, value, target, fragment in references(package, skill):
                checked += 1
                with self.subTest(host=package.host, document=document.relative_to(ROOT).as_posix(), target=value):
                    self.assertTrue(target.resolve().is_relative_to(source), 'target is outside the plugin package')
                    self.assertTrue(target.exists(), f'missing {target.relative_to(ROOT).as_posix()}')
                    if fragment:
                        self.assertIn(fragment, anchors(target), 'no heading has this anchor')
        self.assertTrue(checked, 'no skill references found')

    def test_linked_and_run_files_are_required_resources(self):
        rules = json.loads((ROOT / validator.RULES_PATH).read_text(encoding='utf-8'))
        for package, skill in self.skills:
            source = ROOT / package.source
            resources = [entry['path'] for entry in rules['plugins'].get(package.name, {}).get('resources', [])
                         if package.host in entry['hosts']]
            for document, value, target, _ in references(package, skill):
                if (target == document or (package.host, target) in self.discovered or not target.exists()
                        or not target.resolve().is_relative_to(source.resolve())):
                    continue  # Same document, host-discovered skill, or reported by the resolve test.
                relative = target.relative_to(source).as_posix()
                with self.subTest(host=package.host, document=document.relative_to(ROOT).as_posix(), target=value):
                    self.assertTrue(any(validator.matches(relative, path) for path in resources),
                                    f'list {relative} for {package.host} under {package.name} resources '
                                    f'in {validator.RULES_PATH}')


if __name__ == '__main__':
    unittest.main()
