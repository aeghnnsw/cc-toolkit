"""Model pins, pressure-test critic models, and model-config must name allowed models."""
import importlib.util
import json
from pathlib import Path
import re
import tempfile
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('validate_packages', ROOT / 'scripts' / 'validate_packages.py')
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)

ALLOWED_MODELS = 'allowed-models.json'
# Each pressure-test copy calls a critic from the model family of the other host.
CRITIC_SKILLS = {'dev-skills/skills/pressure-test/SKILL.md': 'gpt',
                 'dev-skills/codex-skills/pressure-test/SKILL.md': 'claude'}
MODEL_CONFIG = 'cc-customize/skills/model-config/SKILL.md'
AGENT_MODEL = re.compile(r'^model:[ \t]*(.*?)[ \t]*$', re.MULTILINE)
FENCE = re.compile(r'^[ \t]*```[^\n]*\n(.*?)^[ \t]*```', re.MULTILINE | re.DOTALL)


def load_allowed(root):
    return json.loads((root / ALLOWED_MODELS).read_text(encoding='utf-8'))


def relative(root, path):
    return path.relative_to(root).as_posix()


def agent_files(root):
    """Return the Markdown agents of each registered plugin, from the agents paths the validator finds."""
    files = {}
    for package in validator.load_packages(root).values():
        for field, path in validator.discovery_paths(root, package):
            if field == 'agents':
                target = root / package.source / path
                files.update(dict.fromkeys([target] if target.is_file() else sorted(target.rglob('*.md'))))
    return list(files)


def codex_agent_files(root):
    """Return the Codex agent TOML files in the codex-agents directory of each registered plugin."""
    sources = dict.fromkeys(package.source for package in validator.load_packages(root).values())
    return [path for source in sources for path in sorted((root / source / 'codex-agents').glob('*.toml'))]


def frontmatter(text):
    lines = text.splitlines()
    if not lines or lines[0].strip() != '---':
        return ''
    end = next((index for index, line in enumerate(lines[1:], 1) if line.strip() == '---'), 0)
    return '\n'.join(lines[1:end])


def section(text, heading):
    """Return the text under a Markdown heading, up to the next heading of the same or a higher level."""
    match = re.search(rf'^(#+)[ \t]+{re.escape(heading)}[ \t]*$', text, re.MULTILINE)
    if not match:
        return ''
    end = re.compile(rf'^#{{1,{len(match.group(1))}}}[ \t]', re.MULTILINE).search(text, match.end())
    return text[match.end():end.start() if end else len(text)]


def check_agent_pins(root, allowed):
    """An agent pins the Claude primary model or inherit; an agent with no model line inherits."""
    valid = (allowed['claude']['primary'], 'inherit')
    problems = []
    for path in agent_files(root):
        for value in AGENT_MODEL.findall(frontmatter(path.read_text(encoding='utf-8'))):
            value = value.strip('\'"')
            if value not in valid:
                problems.append(f'{relative(root, path)}: model {value!r} is not {valid[0]!r} or {valid[1]!r}')
    return problems


def check_codex_agent_pins(root, allowed):
    """A Codex agent that sets a model pins the GPT primary model."""
    primary = allowed['gpt']['primary']
    problems = []
    for path in codex_agent_files(root):
        model = tomllib.loads(path.read_text(encoding='utf-8')).get('model')
        if model is not None and model != primary:
            problems.append(f'{relative(root, path)}: model {model!r} is not {primary!r}')
    return problems


def check_critic_models(root, allowed):
    """Each pressure-test copy names the primary and fallback models of its critic family."""
    problems = []
    for path, family in CRITIC_SKILLS.items():
        text = (root / path).read_text(encoding='utf-8')
        for setting, role in (('PRIMARY_MODEL', 'primary'), ('FALLBACK_MODEL', 'fallback')):
            expected = allowed[family][role]
            values = re.findall(rf'^[ \t]*{setting}="([^"\n]*)"', text, re.MULTILINE)
            if not values:
                problems.append(f'{path}: no {setting} setting')
            problems += [f'{path}: {setting} {value!r} is not {expected!r}' for value in values if value != expected]
    return problems


def check_model_config(root, allowed):
    """model-config names the Claude primary and fallback models in its model table and fallback list."""
    text = (root / MODEL_CONFIG).read_text(encoding='utf-8')
    rows = re.findall(r'^\|([^|\n]*)\|', section(text, 'Models and effort levels'), re.MULTILINE)
    table = {model for cell in rows for model in re.findall(r'`([^`]+)`', cell)}
    fence = FENCE.search(section(text, 'Step 5a: Select Base Model'))
    offered = set(re.findall(r'^[ \t]*\d+\.[ \t]+(\S+)[ \t]*$', fence.group(1) if fence else '', re.MULTILINE))
    problems = []
    for role in ('primary', 'fallback'):
        model = allowed['claude'][role]
        if model not in table:
            problems.append(f'{MODEL_CONFIG}: the "Models and effort levels" table has no {model!r} row')
        if model not in offered:
            problems.append(f'{MODEL_CONFIG}: the Step 5a fallback list does not offer {model!r}')
    return problems


CHECKS = (check_agent_pins, check_codex_agent_pins, check_critic_models, check_model_config)


def check_all(root):
    allowed = load_allowed(root)
    return [problem for check in CHECKS for problem in check(root, allowed)]


FIXTURE = {
    ALLOWED_MODELS: json.dumps({'claude': {'primary': 'claude-opus-5-5', 'fallback': 'claude-sonnet-5-5'},
                                'gpt': {'primary': 'gpt-6-astra', 'fallback': 'gpt-6.1-sol'}}),
    '.claude-plugin/marketplace.json': json.dumps({'name': 'fixture', 'plugins': [
        {'name': 'demo', 'source': './demo'}]}),
    '.agents/plugins/marketplace.json': json.dumps({'name': 'fixture', 'plugins': [
        {'name': 'demo', 'source': {'source': 'local', 'path': './demo'}}]}),
    'demo/.claude-plugin/plugin.json': json.dumps({'name': 'demo', 'version': '1.0.0'}),
    'demo/.codex-plugin/plugin.json': json.dumps({'name': 'demo', 'version': '1.0.0'}),
    'demo/agents/pinned.md': '---\nname: pinned\nmodel: claude-opus-5-5\n---\nBody.\n',
    'demo/agents/inherits.md': '---\nname: inherits\nmodel: inherit\n---\nBody.\n',
    'demo/agents/unpinned.md': '---\nname: unpinned\n---\nBody.\n',
    'demo/codex-agents/worker.toml': 'name = "worker"\nmodel = "gpt-6-astra"\n',
    'dev-skills/skills/pressure-test/SKILL.md':
        'PRIMARY_MODEL="gpt-6-astra"\nFALLBACK_MODEL="gpt-6.1-sol"   # only after a flag\n',
    'dev-skills/codex-skills/pressure-test/SKILL.md':
        'PRIMARY_MODEL="claude-opus-5-5"\nFALLBACK_MODEL="claude-sonnet-5-5"   # only after a flag\n',
    MODEL_CONFIG: ('### Models and effort levels\n\n| Model | Effort levels |\n|---|---|\n'
                   '| `claude-opus-5-5` | low, max |\n| `claude-sonnet-5-5` | low, max |\n\n'
                   '### Step 5a: Select Base Model\n\n```\n1. claude-opus-5-5\n2. claude-sonnet-5-5\n```\n'),
}


class ModelPinTests(unittest.TestCase):
    def fixture(self, changes=None):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        for path, text in {**FIXTURE, **(changes or {})}.items():
            (root / path).parent.mkdir(parents=True, exist_ok=True)
            (root / path).write_text(text, encoding='utf-8')
        return root

    def test_repository_names_only_allowed_models(self):
        self.assertTrue(agent_files(ROOT), 'no agent files found')
        self.assertTrue(codex_agent_files(ROOT), 'no Codex agent files found')
        allowed = load_allowed(ROOT)
        for check in CHECKS:
            with self.subTest(check=check.__name__):
                self.assertEqual(check(ROOT, allowed), [])

    def test_fixture_with_allowed_models_passes(self):
        self.assertEqual(check_all(self.fixture()), [])

    def test_fixture_with_a_wrong_model_fails(self):
        cases = [  # (file, wrong text, model that the problem names)
            ('demo/agents/pinned.md', '---\nname: pinned\nmodel: claude-haiku-4-5\n---\n', 'claude-haiku-4-5'),
            ('demo/agents/inherits.md', '---\nname: inherits\nmodel: "claude-sonnet-5-5"\n---\n',
             'claude-sonnet-5-5'),
            ('demo/codex-agents/worker.toml', 'name = "worker"\nmodel = "gpt-6.1-sol"\n', 'gpt-6.1-sol'),
            ('dev-skills/skills/pressure-test/SKILL.md',
             'PRIMARY_MODEL="claude-opus-5-5"\nFALLBACK_MODEL="gpt-6.1-sol"\n', 'claude-opus-5-5'),
            ('dev-skills/codex-skills/pressure-test/SKILL.md',
             'PRIMARY_MODEL="claude-opus-5-5"\nFALLBACK_MODEL="claude-haiku-5-5"\n', 'claude-haiku-5-5'),
            ('dev-skills/codex-skills/pressure-test/SKILL.md', 'PRIMARY_MODEL="claude-opus-5-5"\n',
             'FALLBACK_MODEL'),
            (MODEL_CONFIG, FIXTURE[MODEL_CONFIG].replace('2. claude-sonnet-5-5\n', ''), 'claude-sonnet-5-5'),
            (MODEL_CONFIG, FIXTURE[MODEL_CONFIG].replace('| `claude-opus-5-5` | low, max |\n', ''),
             'claude-opus-5-5'),
        ]
        for path, text, named in cases:
            with self.subTest(path=path, named=named):
                problems = check_all(self.fixture({path: text}))
                self.assertEqual(len(problems), 1, problems)
                self.assertIn(path, problems[0])
                self.assertIn(named, problems[0])


if __name__ == '__main__':
    unittest.main()
