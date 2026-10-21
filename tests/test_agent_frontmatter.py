"""Plugin agents must not set the frontmatter fields that Claude Code ignores for plugin agents."""
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from package_support import ROOT, agent_files, frontmatter

# Claude Code ignores these fields when it loads an agent from a plugin, without an error.
IGNORED_FIELDS = ('hooks', 'mcpServers', 'permissionMode', 'initialPrompt')
TOP_LEVEL_KEY = re.compile(r'^([A-Za-z][\w-]*)[ \t]*:', re.MULTILINE)


def check_agent_fields(root):
    """A plugin agent sets no top-level frontmatter field that Claude Code ignores for plugin agents."""
    problems = []
    for path in agent_files(root):
        for key in TOP_LEVEL_KEY.findall(frontmatter(path.read_text(encoding='utf-8'))):
            if key in IGNORED_FIELDS:
                problems.append(f'{path.relative_to(root).as_posix()}: {key!r} is ignored for plugin agents')
    return problems


FIXTURE = {
    '.claude-plugin/marketplace.json': json.dumps({'name': 'fixture', 'plugins': [
        {'name': 'demo', 'source': './demo'}]}),
    '.agents/plugins/marketplace.json': json.dumps({'name': 'fixture', 'plugins': [
        {'name': 'demo', 'source': {'source': 'local', 'path': './demo'}}]}),
    'demo/.claude-plugin/plugin.json': json.dumps({'name': 'demo', 'version': '1.0.0'}),
    'demo/.codex-plugin/plugin.json': json.dumps({'name': 'demo', 'version': '1.0.0'}),
    'demo/agents/worker.md': ('---\nname: worker\ntools: ["Read", "mcp__demo__*"]\nmodel: inherit\n---\n'
                              'Do not set mcpServers: or hooks: here.\n'),
}


class AgentFrontmatterTests(unittest.TestCase):
    def fixture(self, changes=None):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        subprocess.run(['git', 'init', '-q'], cwd=root, check=True)
        for path, text in {**FIXTURE, **(changes or {})}.items():
            (root / path).parent.mkdir(parents=True, exist_ok=True)
            (root / path).write_text(text, encoding='utf-8')
        return root

    def test_repository_agents_set_no_ignored_fields(self):
        self.assertTrue(agent_files(ROOT), 'no agent files found')
        self.assertEqual(check_agent_fields(ROOT), [])

    def test_fixture_agent_with_supported_fields_passes(self):
        self.assertEqual(check_agent_fields(self.fixture()), [])

    def test_fixture_agent_with_an_ignored_field_fails(self):
        for field in IGNORED_FIELDS:
            with self.subTest(field=field):
                text = f'---\nname: worker\n{field}:\n  - value\nmodel: inherit\n---\nBody.\n'
                problems = check_agent_fields(self.fixture({'demo/agents/worker.md': text}))
                self.assertEqual(problems, [f"demo/agents/worker.md: '{field}' is ignored for plugin agents"])


if __name__ == '__main__':
    unittest.main()
