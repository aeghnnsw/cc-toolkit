"""The README.md catalog lists the skills of each plugin for each host, and the Codex longDescription names them.

CONTRIBUTING.md, "Skills for more than one host", sets the rule. Each plugin has a README.md section headed
"### <Title> (`<plugin>`)". Its **Skills:** list names each Claude copy with a one-line description, and its
**Codex skills:** and **Antigravity skills:** lists name each Codex and Antigravity copy. The validator's
discovery paths give the skill folders of each host. Adding a skill cost 44 tool calls to find these lists,
and a changed skill purpose left the Codex manifest's interface.longDescription false (#457).

LONG_DESCRIPTION gives, for each Codex copy, the phrase of longDescription that names its purpose. A new Codex
skill fails until it has an entry. When a skill purpose changes, update longDescription and the phrase.
"""
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from package_support import FENCE, ROOT, git_files, validator

LISTS = {'claude': '**Skills:**', 'codex': '**Codex skills:**', 'antigravity': '**Antigravity skills:**'}
SECTION = re.compile(r'### .+ \(`([a-z0-9-]+)`\)')
HEADING = re.compile(r'#{1,3}\s')
ITEM = re.compile(r'- \*\*([^*]+)\*\*(?::(.*))?')
LONG_DESCRIPTION = {
    'creator-skills': {
        'sci-figure-format': 'publication-quality scientific figures',
        'sci-slides': 'scientific presentations',
    },
    'dev-skills': {
        'doc-update': 'current-truth documentation updates',
        'goal-rubric': 'measurable goal rubrics',
        'grill-with-research': 'research-first grilling',
        'lean-tests': 'lean pytest suites',
        'matt-automode': 'autonomous Matt planning-to-merge workflows',
        'pressure-test': 'independent adversarial pressure tests',
        'repo-cleanup': 'repository cleanup',
        'sci-project-layout': 'scientific Python project layouts',
        'step-workflow': 'sequential file organization',
        't3-project-lead': 'T3 Code project leads',
    },
    'productivity-skills': {
        'calendar-manager': 'native macOS Calendar',
        'gtd-inbox': 'capture and process GTD inbox items',
        'gtd-next': 'select feasible work',
        'gtd-overview': 'review linked projects and actions',
        'gtd-process': 'process GTD inbox items',
        'gtd-project': 'review linked projects and actions',
        'gtd-setup': 'user-invoked setup skill',
    },
    'pymol-skills': {
        'pymol-mcp': 'molecular visualization and structural analysis',
        'pymol-setup': 'local PyMOL socket plugin',
    },
}


def catalog(text):
    """Return {plugin: {list heading: [(skill, description)]}} from the plugin sections of a README.md text."""
    sections, plugin, heading = {}, None, None
    for line in FENCE.sub('', text).splitlines():
        if HEADING.match(line):
            match = SECTION.fullmatch(line)
            plugin, heading = match and match[1], None
            if plugin:
                sections[plugin] = {}
        elif plugin and line in LISTS.values():
            heading = line
            sections[plugin][heading] = []
        elif plugin and heading and (item := ITEM.fullmatch(line)):
            sections[plugin][heading].append((item[1], (item[2] or '').strip()))
        elif line.strip():
            heading = None
    return sections


def host_skills(root, packages):
    """Return {(plugin, host): sorted skill folder names} in the skills paths that the validator discovers."""
    files = git_files(root)
    return {key: sorted(skill.parent.name for field, path in validator.discovery_paths(root, package)
                        if field == 'skills' for skill in (root / package.source / path).glob('*/SKILL.md')
                        if validator.included_location(root, skill, files))
            for key, package in packages.items()}


def problems(root, packages, phrases=LONG_DESCRIPTION):
    """Return each difference between README.md, the skill folders of packages, and the Codex longDescription.

    packages maps (plugin, host) to a validator Package, as validator.load_packages returns them.
    """
    skills = host_skills(root, packages)
    sections = catalog((root / 'README.md').read_text(encoding='utf-8'))
    plugins = {name for name, _ in packages}
    found = [f'README.md: add a section "### <Title> (`{name}`)"' for name in sorted(plugins - set(sections))]
    found += [f'README.md: no registry lists {name}; remove its section'
              for name in sorted(set(sections) - plugins)]
    for name in sorted(plugins & set(sections)):
        for host, heading in LISTS.items():
            listed = sorted(skill for skill, _ in sections[name].get(heading, []))
            expected = skills.get((name, host), [])
            if listed != expected:
                found.append(f'README.md {name} {heading} lists {listed}; the {host} skill folders are {expected}')
        found += [f'README.md {name} **Skills:** {skill}: add a one-line description'
                  for skill, description in sections[name].get(LISTS['claude'], []) if not description]
    for (name, host), package in sorted(packages.items()):
        if host != 'codex':
            continue
        table = phrases.get(name, {})
        if sorted(table) != skills[name, host]:
            found.append(f'LONG_DESCRIPTION {name} has entries for {sorted(table)}; '
                         f'the codex skill folders are {skills[name, host]}')
        interface = package.manifest.get('interface')
        text = interface.get('longDescription', '') if isinstance(interface, dict) else ''
        found += [f'{package.manifest_path}: interface.longDescription does not contain {phrase!r} for {skill}'
                  for skill, phrase in sorted(table.items()) if phrase not in text]
    return found


class ReadmeCatalogTests(unittest.TestCase):
    def test_readme_lists_match_skill_folders(self):
        self.assertEqual(problems(ROOT, validator.load_packages(ROOT)), [],
                         'list each skill in the README.md section of its plugin: under **Skills:** with a '
                         'one-line description, and under **Codex skills:** and **Antigravity skills:** for each '
                         'host that ships it. For a Codex skill, name its purpose in interface.longDescription of '
                         '.codex-plugin/plugin.json, and add that phrase to LONG_DESCRIPTION in this test')

    def test_fixture(self):
        readme = ('# Demo\n\n### Demo Skills (`demo`)\nIntro.\n\n**Skills:**\n- **one**: First skill\n'
                  '- **two**: Second skill\n\n**Codex skills:**\n- **one**\n\ntwo has no Codex copy.\n\n'
                  '```bash\n# Not a heading\n```\n\n**Antigravity skills:**\n- **one**\n- **two**\n\n'
                  '### Hooks Only (`hooks`)\n**Hooks:**\n- **guard.py**: Blocks commands\n\n## Usage\n'
                  '**Skills:**\n- **ignored**: Outside a plugin section\n')
        phrases = {'demo': {'one': 'first purpose'}}
        manifests = {('demo', 'claude'): {}, ('hooks', 'claude'): {},
                     ('demo', 'codex'): {'skills': './codex-skills/',
                                         'interface': {'longDescription': 'Use it for first purpose.'}},
                     ('demo', 'antigravity'): {'skills': './antigravity-skills/'}}
        packages = {(name, host): validator.Package(name, host, name, f'{name}/.{host}-plugin/plugin.json',
                                                    {'name': name, **fields})
                    for (name, host), fields in manifests.items()}
        cases = {  # name: (README.md text, phrase table, number of problems)
            'match': (readme, phrases, 0),
            'missing Claude entry': (readme.replace('- **two**: Second skill\n', ''), phrases, 1),
            'empty description': (readme.replace('Second skill', ''), phrases, 1),
            'extra Codex entry': (readme.replace('- **one**\n\ntwo', '- **one**\n- **two**\n\ntwo'), phrases, 1),
            'missing Antigravity list': (readme.replace('**Antigravity skills:**', '**Other:**'), phrases, 1),
            'missing section': (readme.replace('(`hooks`)', '(`other`)'), phrases, 2),
            'missing phrase entry': (readme, {}, 1),
            'phrase not in longDescription': (readme, {'demo': {'one': 'changed purpose'}}, 1),
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for folder in ('skills/one', 'skills/two', 'codex-skills/one', 'antigravity-skills/one',
                           'antigravity-skills/two'):
                (root / 'demo' / folder).mkdir(parents=True)
                (root / 'demo' / folder / 'SKILL.md').write_text('---\nname: x\ndescription: x\n---\n')
            subprocess.run(['git', 'init', '-q'], cwd=root, check=True)
            for name, (text, table, count) in cases.items():
                with self.subTest(name):
                    (root / 'README.md').write_text(text)
                    found = problems(root, packages, table)
                    self.assertEqual(len(found), count, found)


if __name__ == '__main__':
    unittest.main()
