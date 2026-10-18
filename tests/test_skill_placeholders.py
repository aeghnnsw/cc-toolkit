"""Claude Code skill and command text must not contain an argument placeholder that is not escaped or allowlisted."""
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from package_support import ROOT, git_files, validator

# Forms checked in every file: $N, $ARGUMENTS, and $ARGUMENTS[N], which Claude Code replaces, and ${N}, which it does
# not document. Each file also checks the names that its `arguments` frontmatter declares.
ALWAYS_CHECKED = r'\d+|ARGUMENTS(?:\[\d+\])?|\{\d+\}'
ADD_TO_ALLOWED = 'add the line to ALLOWED in tests/test_skill_placeholders.py'
# Intended placeholders: (repository-relative path, line text without surrounding whitespace) -> (line count, reason).
# The count is the number of lines in that file with this text and an unescaped placeholder.
ALLOWED = {}


def relative(root, path):
    return path.relative_to(root).as_posix()


def claude_skill_and_command_files(root):
    """Return the Git-included skill and command files that Claude Code loads for each Claude Code registration.

    A declared skill path adds to the default skills/ directory; a declared command path replaces commands/.
    A plugin with neither skills/ nor a declared skill path loads a SKILL.md at its root as one skill.
    The validator's host_paths keeps skills/ only when no skill path is declared; this function follows Claude Code.
    """
    files = git_files(root)
    found = {}
    for package in validator.load_packages(root).values():
        if package.host != 'claude':
            continue
        base = root / package.source
        declared = [path for field, path in validator.declared_paths(package) if field == 'skills']
        candidates = [] if declared or (base / 'skills').exists() else [base / 'SKILL.md']
        for skill_root in [base / 'skills', *(base / path for path in declared)]:
            candidates += [skill_root / 'SKILL.md', *sorted(skill_root.glob('*/SKILL.md'))]
        for field, path in validator.discovery_paths(root, package):
            if field == 'commands':
                target = base / path
                candidates += [target] if target.is_file() else sorted(target.rglob('*.md'))
        for path in candidates:
            if path.is_file() and validator.included_location(root, path, files):
                found.setdefault(path.resolve(), path)
    return list(found.values())


def escaped(line, start):
    """Claude Code keeps a placeholder as text when exactly one backslash comes before its `$`."""
    before = line[:start]
    return len(before) - len(before.rstrip('\\')) == 1


def remedy(token):
    if token.startswith('${'):  # Claude Code does not document it, and a backslash stays in the loaded text.
        return (f'{token} is a positional parameter. Move the code into a script in the plugin, '
                f'or {ADD_TO_ALLOWED}.')
    return (f'{token} is an argument placeholder. In prose or an example, write one backslash before the $ '
            f'(\\{token}). Move shell code into a script in the plugin; an agent that reads the file '
            f'keeps the backslash. For an intended placeholder, {ADD_TO_ALLOWED}.')


def split_frontmatter(lines):
    """Return the frontmatter lines and the index of the first body line."""
    if not lines or lines[0].strip() != '---':
        return [], 0
    end = next((index for index, line in enumerate(lines[1:], 1) if line.strip() == '---'), 0)
    return (lines[1:end], end + 1) if end else ([], 0)


def declared_names(frontmatter):
    """Return the items of an `arguments` field: a space-separated string, a flow list, or a block list.

    A flow list can continue on later lines. A block list can have comment lines and blank lines between items.
    """
    lines = [re.sub(r'(?:^|[ \t])#.*', '', line).rstrip() for line in frontmatter]
    for index, line in enumerate(lines):
        match = re.match(r'arguments:[ \t]*(.*)$', line)
        if not match:
            continue
        value, rest = match.group(1), lines[index + 1:]
        if value.startswith('['):
            while ']' not in value and rest:
                value, rest = f'{value} {rest[0]}', rest[1:]
            items = value.strip('[]').replace(',', ' ').split()
        elif value:
            items = value.strip('\'"').split()
        else:
            items = []
            for item in filter(str.strip, rest):
                entry = re.match(r'[ \t]*-[ \t]*(.+)$', item)
                if not entry:
                    break
                items.append(entry.group(1))
        return [item.strip('\'"') for item in items]
    return []


def check_placeholders(root, allowed=None):
    """Return a problem for each line with an unescaped placeholder and for each allowlist count that differs."""
    allowed = ALLOWED if allowed is None else allowed
    problems, counts = [], dict.fromkeys(allowed, 0)
    for path in claude_skill_and_command_files(root):
        relative_path = relative(root, path)
        lines = path.read_text(encoding='utf-8').splitlines()
        frontmatter, start = split_frontmatter(lines)
        names = declared_names(frontmatter)
        problems += [f'{relative_path}: the `arguments` frontmatter declares {item!r}. The test can check only '
                     f'names of letters, digits, and underscores. Rename the argument.'
                     for item in names if not re.fullmatch(r'\w+', item)]
        name_patterns = [rf'{re.escape(name)}(?!\w)' for name in names if re.fullmatch(r'\w+', name)]
        placeholder = re.compile(r'\$(?:' + '|'.join([ALWAYS_CHECKED, *name_patterns]) + ')')
        for number, line in enumerate(lines[start:], start + 1):
            tokens = [match.group() for match in placeholder.finditer(line)
                      if match.group().startswith('${') or not escaped(line, match.start())]
            if (relative_path, line.strip()) in counts and tokens:
                counts[relative_path, line.strip()] += 1
            else:
                problems += [f'{relative_path}:{number}: {remedy(token)}' for token in tokens]
    for (relative_path, text), (count, _reason) in allowed.items():
        if counts[relative_path, text] != count:
            problems.append(f'{relative_path}: ALLOWED expects {count} line(s) {text!r} with a placeholder, found '
                            f'{counts[relative_path, text]}. Review each use, then update the count or remove the '
                            f'entry.')
    return problems


SKILL = 'demo/skills/clean/SKILL.md'
FIXTURE = {
    '.claude-plugin/marketplace.json': json.dumps({'name': 'fixture', 'plugins': [
        {'name': 'demo', 'source': './demo'}]}),
    '.agents/plugins/marketplace.json': json.dumps({'name': 'fixture', 'plugins': [
        {'name': 'demo', 'source': {'source': 'local', 'path': './demo'}}]}),
    'demo/.claude-plugin/plugin.json': json.dumps({'name': 'demo', 'version': '1.0.0'}),
    'demo/.codex-plugin/plugin.json': json.dumps({'name': 'demo', 'version': '1.0.0', 'skills': './codex-skills/'}),
    SKILL: ('---\nname: clean\ndescription: Escaped placeholders only.\n---\n\n'
            'Show `\\$1` and a price of \\$0.67.\n'),
}


class SkillPlaceholderTests(unittest.TestCase):
    def fixture(self, changes=None):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        subprocess.run(['git', 'init', '-q'], cwd=root, check=True)
        for path, text in {**FIXTURE, **(changes or {})}.items():
            (root / path).parent.mkdir(parents=True, exist_ok=True)
            (root / path).write_text(text, encoding='utf-8')
        return root

    def assert_flags(self, body, token, line=7):
        """A skill whose body holds this text fails on the given line, naming the placeholder."""
        problems = check_placeholders(self.fixture({SKILL: FIXTURE[SKILL] + body}))
        self.assertTrue(any(problem.startswith(f'{SKILL}:{line}: {token}') for problem in problems), problems)

    def test_fixture_with_escaped_placeholders_passes(self):
        self.assertEqual(check_placeholders(self.fixture()), [])

    def test_backslashes_other_than_one_do_not_escape(self):
        for body in ('\\\\$1\n', '\\\\\\$1\n', '$1\n'):
            with self.subTest(body=body):
                self.assert_flags(body, '$1')

    def test_indexed_and_full_argument_placeholders_fail(self):
        cases = [('Project: $0\n', '$0'), ('cost $0.67\n', '$0'), ('$10 items\n', '$10'), ('$1abc\n', '$1'),
                 ('Use `$1` here.\n', '$1'), ('```bash\nlocal s="$1"\n```\n', '$1'),
                 ('Args: $ARGUMENTS\n', '$ARGUMENTS'), ('First: $ARGUMENTS[0]\n', '$ARGUMENTS[0]'),
                 ('Second: $ARGUMENTS[1]\n', '$ARGUMENTS[1]')]
        for body, token in cases:
            with self.subTest(body=body):
                self.assert_flags(body, token, line=8 if body.startswith('```') else 7)

    def test_braced_positional_parameters_fail_without_a_backslash_remedy(self):
        for body in ('echo "${1}"\n', 'echo "\\${1}"\n'):
            with self.subTest(body=body):
                self.assert_flags(body, '${1}')
                [problem] = check_placeholders(self.fixture({SKILL: FIXTURE[SKILL] + body}))
                self.assertIn('script', problem)
                self.assertIn('ALLOWED', problem)
                self.assertNotIn('backslash before', problem)

    def test_messages_name_each_remedy(self):
        [problem] = check_placeholders(self.fixture({SKILL: FIXTURE[SKILL] + 'cost $0.67\n'}))
        for text in ('one backslash before the $ (\\$0)', 'script in the plugin', 'ALLOWED'):
            self.assertIn(text, problem)

    def test_frontmatter_and_shell_variables_pass(self):
        text = ('---\nname: clean\ndescription: Costs $5 per $1 run.\nargument-hint: "[$0]"\n---\n\n'
                'Read $HOME, "$@", $#, $name, ${name}, and \\$ARGUMENTS.\n')
        self.assertEqual(check_placeholders(self.fixture({SKILL: text})), [])

    def test_declared_named_arguments_fail_unless_escaped(self):
        headers = ('arguments: target mode', 'arguments: [target, "mode"]', "arguments:\n  - 'target'\n  - mode",
                   'arguments: [target,\n  mode]', 'arguments:\n  # Names\n  - target\n\n  - mode  # Second',
                   'arguments: target mode  # Two names')
        body = '\nprintf "$target" "$mode"\nKeep \\$target, $targets, ${target}, and $other.\n'
        for header in headers:
            with self.subTest(header=header):
                text = f'---\nname: clean\ndescription: Named.\n{header}\n---\n{body}'
                line = text.splitlines().index('printf "$target" "$mode"') + 1
                problems = check_placeholders(self.fixture({SKILL: text}))
                self.assertEqual([problem.split(' is ')[0] for problem in problems],
                                 [f'{SKILL}:{line}: $target', f'{SKILL}:{line}: $mode'])

    def test_declared_names_that_the_test_cannot_check_fail(self):
        for header, item in (('arguments: my-arg other', 'my-arg'), ('arguments: >\n  other', '>')):
            with self.subTest(header=header):
                text = f'---\nname: clean\ndescription: Named.\n{header}\n---\n\nUse $other.\n'
                problems = check_placeholders(self.fixture({SKILL: text}))
                self.assertTrue(any(problem.startswith(f'{SKILL}: the `arguments` frontmatter declares {item!r}')
                                    for problem in problems), problems)
                self.assertEqual(any(': $other is ' in problem for problem in problems), item == 'my-arg', problems)

    def test_text_that_claude_code_does_not_replace_passes(self):
        changes = {'demo/codex-skills/clean/SKILL.md': '---\nname: clean\ndescription: Codex.\n---\n\nlocal s="$1"\n',
                   'demo/agents/helper.md': '---\nname: helper\ndescription: Agent.\n---\n\nUse $1 and $ARGUMENTS.\n',
                   'demo/skills/clean/references/notes.md': 'Pay $50, not $10.\n',
                   '.gitignore': 'demo/skills/draft/\n',
                   'demo/skills/draft/SKILL.md': '---\nname: draft\ndescription: Ignored.\n---\n\nUse $1.\n'}
        self.assertEqual(check_placeholders(self.fixture(changes)), [])

    def test_every_claude_code_skill_and_command_root_is_checked(self):
        plugins = {'loop': {'skills': './claude-skills/'}, 'single': {}, 'cmds': {},
                   'custom': {'commands': './extra/'}}
        body = '---\nname: probe\ndescription: Probe.\n---\n\nUse $1.\n'
        changes = {'.claude-plugin/marketplace.json': json.dumps({'name': 'fixture', 'plugins': [
            {'name': name, 'source': f'./{name}'} for name in ['demo', *plugins]]})}
        for name, fields in plugins.items():
            changes[f'{name}/.claude-plugin/plugin.json'] = json.dumps({'name': name, 'version': '1.0.0', **fields})
        expected = ['loop/claude-skills/declared/SKILL.md', 'loop/skills/default/SKILL.md', 'single/SKILL.md',
                    'cmds/commands/run.md', 'custom/extra/go.md']
        changes.update(dict.fromkeys(expected + ['custom/commands/replaced.md'], body))
        problems = check_placeholders(self.fixture(changes))
        self.assertEqual(sorted(problem.split(':')[0] for problem in problems), sorted(expected))

    def test_allowlisted_lines_must_match_their_count(self):
        allowed = {(SKILL, 'Project: $0'): (1, 'The skill shows its first argument.')}
        cases = [  # (body, problem prefixes)
            ('Project: $0\n', []),
            ('  Project: $0\nProject: $0\n', [f'{SKILL}: ALLOWED expects 1 line']),
            ('Project: $0\ncost $0.67\n', [f'{SKILL}:8: $0']),
            ('cost $0.67\n', [f'{SKILL}:7: $0', f'{SKILL}: ALLOWED expects 1 line']),
        ]
        for body, expected in cases:
            with self.subTest(body=body):
                problems = check_placeholders(self.fixture({SKILL: FIXTURE[SKILL] + body}), allowed)
                self.assertEqual(len(problems), len(expected), problems)
                for prefix in expected:
                    self.assertTrue(any(problem.startswith(prefix) for problem in problems), problems)

    def test_an_allowlisted_named_argument_does_not_cover_a_copied_shell_variable(self):
        text = ('---\nname: clean\ndescription: Named.\narguments: [target]\n---\n\n'
                "printf '%s\\n' \"$target\"\ntarget=detected\nprintf '%s\\n' \"$target\"\n")
        allowed = {(SKILL, "printf '%s\\n' \"$target\""): (1, 'The skill prints its argument.')}
        problems = check_placeholders(self.fixture({SKILL: text}), allowed)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn('ALLOWED expects 1 line', problems[0])
        self.assertIn('found 2', problems[0])

    def test_repository_has_no_unreviewed_placeholders(self):
        self.assertTrue(claude_skill_and_command_files(ROOT), 'no Claude Code skill files found')
        self.assertEqual(check_placeholders(ROOT), [])


if __name__ == '__main__':
    unittest.main()
