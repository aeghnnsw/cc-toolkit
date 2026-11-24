"""Ordinary prose in CLAUDE.md and CONTRIBUTING.md wraps at 78 characters.

CONTRIBUTING.md, "Coding standards", sets the rule and exempts headings, tables, links, and code examples,
including inline commands. While the rule was prose only, agents guessed 80 or 120 columns or looked for a
linter configuration (#457). This test measures each line in characters. It skips fenced code, `#` headings,
and `|` table rows. It also skips a line whose overflow is inside a link or inline code: the 79th character is
in a `[text](target)` link, a URL, or a code span, and no space follows that span, so no word can wrap.
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from package_support import FENCE, ROOT

WIDTH = 78
FILES = ('CLAUDE.md', 'CONTRIBUTING.md')
HEADING = re.compile(r'#{1,6}(?:\s|$)')
# An inline link or image, an autolink or bare URL, or a code span.
SPAN = re.compile(r'!?\[[^\]\n]*\]\([^)\s]*\)|<?https?://[^\s>]+>?|(`+).+?\1')


def fenced_lines(text):
    """Return the 1-based numbers of the lines from each opening code fence to its closing fence."""
    numbers = set()
    for match in FENCE.finditer(text):
        numbers.update(range(text.count('\n', 0, match.start()) + 1, text.count('\n', 0, match.end()) + 2))
    return numbers


def exempt_overflow(line):
    """Return whether the characters past WIDTH are one link or code span and the punctuation after it."""
    return any(match.start() <= WIDTH < match.end() and ' ' not in line[match.end():]
               for match in SPAN.finditer(line))


def wide_lines(name, text):
    """Return 'name:line:width' for each prose line of text that is wider than WIDTH characters."""
    fenced = fenced_lines(text)
    return [f'{name}:{number}:{len(line)}' for number, line in enumerate(text.splitlines(), 1)
            if len(line) > WIDTH and number not in fenced and not HEADING.match(line)
            and not line.lstrip().startswith('|') and not exempt_overflow(line)]


def problems(root):
    return [problem for name in FILES
            for problem in wide_lines(name, (root / name).read_text(encoding='utf-8'))]


class ProseWidthTests(unittest.TestCase):
    def test_prose_wraps_at_78_characters(self):
        self.assertEqual(problems(ROOT), [], f'rewrap each listed line (file:line:width) at {WIDTH} characters; '
                         'fenced code, headings, | table rows, and an overflow inside a link or inline code '
                         'are exempt')

    def test_fixture(self):
        prose = 'word ' * 15 + 'last'  # 79 characters
        link = '[a long link title](docs/design/package-validation.md#host-ownership)'
        cases = {  # line: whether the check reports it
            prose: True,
            prose[:WIDTH]: False,
            '## ' + prose: False,
            '| ' + prose + ' |': False,
            'x' * 20 + ' manifests and ' + link + '.': False,
            'x' * 20 + ' manifests and ' + link + ' and more': True,
            'x' * 60 + ' run `uv run --no-project python -m unittest`.': False,
            'x' * 60 + ' see https://example.com/a/long/path/to/a/page': False,
            'x' * 70 + ' `ls`' + ' word': True,
        }
        for line, reported in cases.items():
            with self.subTest(line=line):
                self.assertEqual(wide_lines('demo.md', f'Intro.\n\n{line}\n'),
                                 [f'demo.md:3:{len(line)}'] if reported else [])
        fenced = f'Intro.\n\n```bash\n{prose}\n```\n\n  ~~~\n  {prose}\n  ~~~\n{prose}\n'
        self.assertEqual(wide_lines('demo.md', fenced), [f'demo.md:10:{len(prose)}'])


if __name__ == '__main__':
    unittest.main()
