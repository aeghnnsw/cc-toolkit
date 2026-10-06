"""Links and required resources for every skill a registered host discovers."""
from collections import Counter
import importlib.util
import os
from pathlib import Path
import re
from typing import NamedTuple
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('validate_packages', ROOT / 'scripts' / 'validate_packages.py')
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)

FENCE = re.compile(r'^[ \t]*(```|~~~).*?^[ \t]*\1', re.MULTILINE | re.DOTALL)
# An inline link or image destination, or a reference definition.
LINK = re.compile(r'\]\(\s*<?([^\s)>]+)|^[ \t]*\[[^\]]+\]:[ \t]*<?([^\s>]+)', re.MULTILINE)
SCHEME = re.compile(r'[A-Za-z][A-Za-z0-9+.-]*:')
HEADING = re.compile(r'^#{1,6}\s+(.+?)(?:\s+#+)?\s*$', re.MULTILINE)
RUN_PATH = re.compile(r'(\$\{CLAUDE_PLUGIN_ROOT\}|<plugin-root>|<skill-dir>)/([\w./-]+)')


class Reference(NamedTuple):
    document: Path
    text: str
    target: Path
    fragment: str


def discover():
    """Return (package, skill roots, SKILL.md files) for each host registration, as the validator finds them."""
    files = set(validator.git(ROOT, 'ls-files', '--cached', '--others', '--exclude-standard', '-z')
                .decode().split('\0'))
    registrations = []
    for package in validator.load_packages(ROOT).values():
        roots = [ROOT / package.source / path
                 for field, path in validator.discovery_paths(ROOT, package) if field == 'skills']
        skills = [skill for root in roots for skill in sorted(root.glob('*/SKILL.md'))
                  if validator.included_location(ROOT, skill, files)]
        registrations.append((package, roots, skills))
    return registrations


def inside(package, path):
    return path.resolve().is_relative_to((ROOT / package.source).resolve())


def anchors(document):
    """Return GitHub-style heading anchors; a repeated heading gets a numeric suffix."""
    seen = Counter()
    result = set()
    for heading in HEADING.findall(FENCE.sub('', document.read_text(encoding='utf-8'))):
        slug = re.sub(r'[^\w\- ]', '', heading.strip().lower()).replace(' ', '-')
        result.add(f'{slug}-{seen[slug]}' if seen[slug] else slug)
        seen[slug] += 1
    return result


def references(package, skill):
    """Yield each reference in a skill and in the Markdown files it reaches inside its package."""
    pending, seen = [skill], {skill}
    while pending:
        document = pending.pop()
        content = document.read_text(encoding='utf-8')
        candidates = [(document.parent, link) for match in LINK.findall(FENCE.sub('', content))
                      for link in match if link and not SCHEME.match(link)]
        candidates += [(skill.parent if base == '<skill-dir>' else ROOT / package.source, path.rstrip('.'))
                       for base, path in RUN_PATH.findall(content)]
        for base, text in dict.fromkeys(candidates):
            path, _, fragment = text.partition('#')
            target = Path(os.path.normpath(base / path)) if path else document
            yield Reference(document, text, target, fragment)
            if (target.suffix == '.md' and target.name != 'SKILL.md' and target.is_file()
                    and target not in seen and inside(package, target)):
                seen.add(target)
                pending.append(target)


class SkillLinkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registrations = discover()
        cls.skills = [(package, skill) for package, _, skills in cls.registrations for skill in skills]
        cls.discovered = {(package.host, skill) for package, skill in cls.skills}

    def reference_test(self, package, reference):
        return self.subTest(host=package.host, document=reference.document.relative_to(ROOT).as_posix(),
                            target=reference.text)

    def test_skills_are_discovered_for_each_host(self):
        for package, roots, skills in self.registrations:
            if roots:
                with self.subTest(plugin=package.name, host=package.host):
                    self.assertTrue(skills, f'no SKILL.md found under {roots}')
        self.assertEqual({package.host for package, _ in self.skills}, set(validator.REGISTRIES))

    def test_references_resolve_inside_package(self):
        checked = 0
        for package, skill in self.skills:
            for reference in references(package, skill):
                checked += 1
                with self.reference_test(package, reference):
                    self.assertTrue(inside(package, reference.target), 'target is outside the plugin package')
                    self.assertTrue(reference.target.is_file(),
                                    f'missing file {reference.target.relative_to(ROOT).as_posix()}')
                    if reference.fragment:
                        self.assertIn(reference.fragment, anchors(reference.target), 'no heading has this anchor')
        self.assertTrue(checked, 'no skill references found')

    def test_linked_and_run_files_are_required_resources(self):
        rules = validator.validate_rules(validator.read_json(ROOT, validator.RULES_PATH))
        for package, skill in self.skills:
            rule = rules.get('plugins', {}).get(package.name, {})
            resources = [entry['path'] for entry in rule.get('resources', []) if package.host in entry['hosts']]
            for reference in references(package, skill):
                target = reference.target
                if (target == reference.document or (package.host, target) in self.discovered
                        or not target.is_file() or not inside(package, target)):
                    continue  # Same document, host-discovered skill, or reported by the resolve test.
                relative = target.relative_to(ROOT / package.source).as_posix()
                with self.reference_test(package, reference):
                    self.assertTrue(any(validator.matches(relative, path) for path in resources),
                                    f'list {relative} for {package.host} under {package.name} resources '
                                    f'in {validator.RULES_PATH}')


if __name__ == '__main__':
    unittest.main()
