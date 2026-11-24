"""Each mktemp call in a shipped Markdown or shell file makes its file or folder under "${TMPDIR:-/tmp}".

On macOS, a bare `mktemp -d` and `mktemp -d -t <name>` ignore TMPDIR and write under /var/folders, which a
sandboxed shell cannot write. A template under /tmp or a relative template ignores TMPDIR too, and a
"$TMPDIR/..." template fails where TMPDIR is not set. Prose fixed single skills, and the bare form came back
(#457). The form is `mktemp -d "${TMPDIR:-/tmp}/<name>.XXXXXX"`, or `mktemp "${TMPDIR:-/tmp}/<name>.XXXXXX"`
for a file. A shipped file is in a plugin directory that a marketplace registry selects, outside its tests/.
"""
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from package_support import ROOT, git_files, validator

# The command word mktemp, not part of a name such as tempfile.mktemp or make_mktemp.
MKTEMP = re.compile(r'(?<![\w.$-])mktemp(?![\w.-])')
FORM = re.compile(r'mktemp(?: -d)? "\$\{TMPDIR:-/tmp\}/[A-Za-z0-9_-]+\.XXXXXX"')
SHELL_SUFFIXES = ('.sh', '.bash', '.zsh')
SHEBANG = re.compile(r'#!.*\b(?:ba|z)?sh\b')
FIX = 'write mktemp -d "${TMPDIR:-/tmp}/<name>.XXXXXX", or mktemp "${TMPDIR:-/tmp}/<name>.XXXXXX" for a file'


def shipped(files, sources):
    """Return the names in files under a plugin directory in sources, outside the plugin's tests/ folder."""
    return sorted({name for name in files for source in sources
                   if name.startswith(f'{source}/') and not name.startswith(f'{source}/tests/')})


def problems(root, names):
    """Return each line of a Markdown or shell file in names that calls mktemp without the TMPDIR form."""
    found = []
    for name in names:
        path = root / name
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            continue
        if not name.endswith(('.md', *SHELL_SUFFIXES)) and not SHEBANG.match(text):
            continue
        found += [f'{name}:{number}: {line.strip()}' for number, line in enumerate(text.splitlines(), 1)
                  if any(not FORM.match(line, match.start()) for match in MKTEMP.finditer(line))]
    return found


class MktempFormTests(unittest.TestCase):
    def test_shipped_files_make_temporary_paths_under_tmpdir(self):
        sources = {package.source for package in validator.load_packages(ROOT).values()}
        self.assertEqual(problems(ROOT, shipped(git_files(ROOT), sources)), [], FIX)

    def test_fixture(self):
        cases = {  # line: is a problem
            'mktemp -d': True,
            'DIR=$(mktemp -d -t demo)': True,
            'DIR="$(mktemp -d /tmp/demo.XXXXXX)"': True,
            'DIR="$(mktemp -d "$TMPDIR/demo.XXXXXX")"': True,
            'cd "$(mktemp -d demo.XXXXXX)"': True,
            'Make it with `mktemp -d "${TMPDIR:-/tmp}/demo.XXXXXX"`, then `mktemp -d`.': True,
            'Make it with `mktemp -d "${TMPDIR:-/tmp}/demo.XXXXXX"`.': False,
            'new="$(mktemp "${TMPDIR:-/tmp}/demo-file.XXXXXX")"': False,
            'path = tempfile.mkdtemp(); make_mktemp_dir': False,
        }
        files = {  # file: (first line, is checked)
            'demo/skills/one/SKILL.md': ('# One', True),
            'demo/scripts/run.sh': ('set -eu', True),
            'demo/scripts/tool': ('#!/usr/bin/env bash', True),
            'demo/hooks/hooks.json': ('{}', False),
            'demo/tests/notes.md': ('# Notes', False),
            'other/skills/two/SKILL.md': ('# Two', False),
        }
        for line, bad in cases.items():
            with self.subTest(line=line), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                for name, (first, _) in files.items():
                    (root / name).parent.mkdir(parents=True, exist_ok=True)
                    (root / name).write_text(f'{first}\n{line}\n', encoding='utf-8')
                expected = [f'{name}:2: {line}' for name, (_, checked) in sorted(files.items()) if checked and bad]
                self.assertEqual(problems(root, shipped(files, {'demo'})), expected)


if __name__ == '__main__':
    unittest.main()
