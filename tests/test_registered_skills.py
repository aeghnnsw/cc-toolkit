"""Each SKILL.md is in a plugin directory that a marketplace registry selects.

A retired plugin folder keeps copies of shared skills. They match many search terms, so each search of current
text needed an exclusion (#370, #469). Keep a retired plugin at a tag and delete its folder from master.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from package_support import ROOT, git_files, validator


def unregistered(files, sources):
    """Return each SKILL.md in files that is not under one of the plugin directories in sources."""
    prefixes = tuple(f'{source}/' for source in sources)
    return sorted(name for name in files
                  if Path(name).name == 'SKILL.md' and not name.startswith(prefixes))


class RegisteredSkillsTests(unittest.TestCase):
    def test_skills_are_in_registered_plugins(self):
        sources = {package.source for package in validator.load_packages(ROOT).values()}
        self.assertEqual(unregistered(git_files(ROOT), sources), [],
                         'delete a retired plugin folder from master and keep it at a tag, or register the plugin')

    def test_fixture(self):
        files = {'demo/skills/one/SKILL.md', 'demo/README.md', 'retired/claude-skills/one/SKILL.md',
                 'demo-old/skills/two/SKILL.md', 'SKILL.md'}
        self.assertEqual(unregistered(files, {'demo'}),
                         ['SKILL.md', 'demo-old/skills/two/SKILL.md', 'retired/claude-skills/one/SKILL.md'])


if __name__ == '__main__':
    unittest.main()
