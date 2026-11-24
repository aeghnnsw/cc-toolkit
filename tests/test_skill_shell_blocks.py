"""Each shell block of a shipped Markdown file parses in bash and zsh and has no zsh or BSD tool trap.

A skill's shell blocks run in the user's shell, which can be bash or zsh. Prose fixes of single skills did not
stop shell mistakes from coming back, and tests ran the blocks of only two skills (#457). This check reads each
bash, sh, zsh, or shell fenced block of a shipped Markdown file: a file in a plugin directory that a marketplace
registry selects, outside its tests/. It replaces each placeholder without a space, such as <plugin-root> or
<work-dir>, with a word. Then `bash -n` and `zsh -n -f` parse the block without running it, and the Core Hooks
zsh_traps check reads it as Claude Code would. tests/test_mktemp_form.py checks the mktemp form.
"""
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from package_support import ROOT, git_files, validator

HOOK_SCRIPTS = ROOT / 'core-hooks' / 'scripts'
SPEC = importlib.util.spec_from_file_location('zsh_traps', HOOK_SCRIPTS / 'zsh_traps.py')
zsh_traps = importlib.util.module_from_spec(SPEC)
sys.path.insert(0, str(HOOK_SCRIPTS))  # zsh_traps imports hook_payload and safety_guard from its folder
try:
    SPEC.loader.exec_module(zsh_traps)
finally:
    sys.path.remove(str(HOOK_SCRIPTS))

LANGUAGES = {'bash', 'sh', 'zsh', 'shell'}
# An opening fence: its indentation, its fence characters, and the first word of its info string.
OPENING = re.compile(r'([ \t]*)(`{3,}|~{3,})[ \t]*([^\s`]*)')
PLACEHOLDER = re.compile(r'<[^<>\s]+>')
SHELLS = {'bash': ['bash', '-n', '-c'], 'zsh': ['zsh', '-n', '-f', '-c']}  # -n: parse only; -f: no startup files
FIX = ('make each block parse in bash and zsh, apply the fix that each message names, or write a placeholder '
       'without a space, such as <work-dir>')


def shipped(files, sources):
    """Return the names in files under a plugin directory in sources, outside the plugin's tests/ folder."""
    return sorted({name for name in files for source in sources
                   if name.startswith(f'{source}/') and not name.startswith(f'{source}/tests/')})


def shell_blocks(text):
    """Yield the line number of the opening fence and the code of each shell block, with placeholders replaced.

    A block ends at a fence of the same character that is at least as long, so a ```` block can hold a ``` block
    as text. The indentation of the opening fence is removed from each line.
    """
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        opening = OPENING.match(lines[index])
        index += 1
        if not opening:
            continue
        indent, fence, language = opening.groups()
        closing = re.compile(rf'[ \t]*{re.escape(fence[0])}{{{len(fence)},}}[ \t]*')
        start = index
        while index < len(lines) and not closing.fullmatch(lines[index]):
            index += 1
        if language in LANGUAGES:
            code = '\n'.join(line[len(indent):] if line.startswith(indent) else line.lstrip()
                             for line in lines[start:index])
            yield start, PLACEHOLDER.sub('placeholder', code) + '\n'
        index += 1


def markdown_blocks(root, names):
    """Yield the location and code of each shell block of the Markdown files in names."""
    for name in names:
        path = root / name
        if name.endswith('.md') and path.is_file():
            for line, code in shell_blocks(path.read_text(encoding='utf-8')):
                yield f'{name}:{line}', code


def syntax_problems(root, names, shell):
    """Return each shell block of the Markdown files in names that the shell cannot parse, with its error."""
    found = []
    for location, code in markdown_blocks(root, names):
        result = subprocess.run([*SHELLS[shell], code], capture_output=True, text=True, timeout=30)
        if result.returncode:
            found.append(f'{location}: {shell}: {result.stderr.strip().splitlines()[0]}')
    return found


def trap_problems(root, names):
    """Return each zsh or BSD tool trap that zsh_traps finds in a shell block of the Markdown files in names.

    The check runs with an empty PATH, so it treats `timeout` as missing, as on macOS releases without it.
    """
    with mock.patch.dict(os.environ, {'PATH': ''}):
        return [f'{location}: {trap.message}' for location, code in markdown_blocks(root, names)
                for trap in zsh_traps.zsh_traps(code, host='claude')]


def shipped_markdown(root):
    sources = {package.source for package in validator.load_packages(root).values()}
    return shipped(git_files(root), sources)


class SkillShellBlockTests(unittest.TestCase):
    def require_shell(self, shell):
        if shutil.which(shell) is None:
            self.skipTest(f'{shell} is not installed')

    def test_blocks_parse_in_bash(self):
        self.require_shell('bash')
        self.assertEqual(syntax_problems(ROOT, shipped_markdown(ROOT), 'bash'), [], FIX)

    def test_blocks_parse_in_zsh(self):
        self.require_shell('zsh')
        self.assertEqual(syntax_problems(ROOT, shipped_markdown(ROOT), 'zsh'), [], FIX)

    def test_blocks_have_no_zsh_or_bsd_tool_trap(self):
        self.assertEqual(trap_problems(ROOT, shipped_markdown(ROOT)), [], FIX)

    def test_fixture(self):
        skill = '\n'.join([
            '```bash',
            'cat "<work-dir>/run.env" "${CLAUDE_PLUGIN_ROOT}/x" && "<plugin-root>/scripts/x.sh"',
            '```',
            '````markdown',
            '```bash',
            'for x in a; echo $x; done',
            '```',
            '````',
            '```python',
            'for x in a; echo $x; done',
            '```',
            '1. Run:',
            '   ```sh',
            '   for x in a; echo $x; done',
            '   ```',
            '~~~zsh',
            '[[ a == (b|c) ]] && echo ${!x}',
            '~~~',
            '```bash',
            '[ "$a" == b ] && cat -A x && timeout 5 make',
            '```',
        ])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('demo/skills/one/SKILL.md', 'demo/tests/notes.md'):
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                (root / name).write_text(skill, encoding='utf-8')
            names = shipped(['demo/skills/one/SKILL.md', 'demo/tests/notes.md'], {'demo'})
            location = 'demo/skills/one/SKILL.md:{}'.format
            self.assertEqual([found for found, _ in markdown_blocks(root, names)],
                             [location(line) for line in (1, 13, 16, 19)])
            # Both shells reject the for loop. bash rejects the (b|c) pattern; zsh rejects ${!x} and `==` in [ ].
            for shell, lines in (('bash', (13, 16)), ('zsh', (13, 16, 19))):
                with self.subTest(shell=shell):
                    self.require_shell(shell)
                    found = syntax_problems(root, names, shell)
                    self.assertEqual([problem.split(f': {shell}: ')[0] for problem in found],
                                     [location(line) for line in lines], found)
            found = trap_problems(root, names)
            self.assertEqual(len(found), 3, found)
            for problem, text in zip(found, ('`==` starts with `=`', 'option `-A`', 'no `timeout` command')):
                self.assertTrue(problem.startswith(f'{location(19)}: '), problem)
                self.assertIn(text, problem)


if __name__ == '__main__':
    unittest.main()
