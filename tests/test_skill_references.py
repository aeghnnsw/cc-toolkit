"""Each `<plugin>:<name>` reference to a plugin of this marketplace names one of its skills or agents.

Skill text names a skill as `<plugin>:<skill>`, such as `dev-skills:repo-cleanup`, and an agent as
`<plugin>:<agent>`, also in the `/<plugin>:<skill>` and `$<plugin>:<skill>` forms. Stale names stayed after
renames and were fixed by hand each time (#457). The check reads each shipped file: a file in a plugin
directory that a marketplace registry selects, outside the plugin's tests/ folder. A skill counts when any
host discovers it. A reference to a plugin outside this marketplace, such as `mattpocock-skills:grilling`,
is not checked.
"""
from pathlib import Path
import re
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from package_support import ROOT, agent_files, frontmatter, validator
from test_script_python_floor import plugin_sources, shipped_texts
from test_skill_links import discover

NAME = r'[a-z0-9]+(?:-[a-z0-9]+)*'
REFERENCE = re.compile(rf'(?<![\w.-])({NAME}):({NAME})')
AGENT_NAME = re.compile(r'^name:\s*["\']?([^"\'\s]+)', re.MULTILINE)


def plugin_names(root):
    """Return {plugin: the names of its skills and agents} for each registered plugin."""
    names = {}
    for package, _, skills in discover():
        names.setdefault(package.name, set()).update(skill.parent.name for skill in skills)
    sources = {package.source: package.name for package in validator.load_packages(root).values()}
    for agent in agent_files(root):
        relative = agent.relative_to(root).as_posix()
        plugin = next(name for source, name in sources.items() if relative.startswith(f'{source}/'))
        match = AGENT_NAME.search(frontmatter(agent.read_text(encoding='utf-8')))
        names[plugin].add(match[1] if match else agent.stem)
    return names


def problems(texts, names):
    """Return each reference in texts {path: text} to a plugin in names {plugin: names} that names neither."""
    return [f'{path}:{number}: {plugin}:{name}' for path, text in texts.items()
            for number, line in enumerate(text.splitlines(), 1)
            for plugin, name in REFERENCE.findall(line) if plugin in names and name not in names[plugin]]


class SkillReferenceTests(unittest.TestCase):
    def test_references_name_a_skill_or_agent(self):
        names = plugin_names(ROOT)
        self.assertIn('repo-cleanup', names.get('dev-skills', set()), 'no dev-skills skills discovered')
        self.assertEqual(problems(shipped_texts(ROOT, plugin_sources(ROOT)), names), [],
                         'write the current name of the skill or agent, and its plugin when it moved')

    def test_fixture(self):
        text = ('Use `demo:one`, `demo:helper`, `/demo:gone`, `$demo:old`, "demo:two".\n'
                'Follow `mattpocock-skills:grilling`; see `error:timeout` and localhost:9876 and xdemo:gone.\n'
                'subagent_type: "demo:retired-agent"\n')
        self.assertEqual(problems({'demo/skills/one/SKILL.md': text}, {'demo': {'one', 'two', 'helper'}}), [
            'demo/skills/one/SKILL.md:1: demo:gone',
            'demo/skills/one/SKILL.md:1: demo:old',
            'demo/skills/one/SKILL.md:3: demo:retired-agent',
        ])


if __name__ == '__main__':
    unittest.main()
