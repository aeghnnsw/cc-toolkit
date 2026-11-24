"""Each plugin Python file reads under its Python floor, and plugin text runs a newer script with uv.

A skill that runs a helper with `python3` gets Python 3.9 on macOS, from /usr/bin/python3. Python-version
mistakes recurred in new places after each fix (#401, #405, #457). A file's floor is the
`requires-python = ">=X.Y"` line of its inline script metadata (PEP 723), or 3.9 without one.
CONTRIBUTING.md, "Python requirements", lists the floors. A shipped file is in a plugin directory that a
marketplace registry selects, outside the plugin's tests/ folder. The rules:

- Each shipped Python file parses with ast.parse(feature_version=floor). This finds syntax such as `match`
  (3.10) and `except*` (3.11). Under Python 3.12 or newer, it does not find an f-string that only 3.12
  reads (PEP 701), such as a nested quote of the same kind.
- Below 3.10, an `X | Y` annotation that Python evaluates, of a function or at module or class level,
  needs `from __future__ import annotations`. Without it, Python 3.9 raises TypeError at import.
- Shipped text other than Python files does not run a script of its plugin whose floor is above 3.9 with
  `python` or `python3`, unless `uv run` comes first on the line.
"""
import ast
from pathlib import Path, PurePosixPath
import re
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from package_support import ROOT, git_files, validator

DEFAULT_FLOOR = (3, 9)  # macOS /usr/bin/python3
REQUIRES = re.compile(r'^# requires-python = (.*)$', re.MULTILINE)
FLOOR = re.compile(r'">=(\d+)\.(\d+)"')
# A python or python3 command, its options, and the word after them. `<python>` is a placeholder, and
# `python3.11` names a version.
RUN = re.compile(r'(?<![\w.<-])(python3?)(?![\w.>-])((?:[ \t]+-[A-Za-z]+)*)[ \t]+(\S+)')
ASSIGNMENT = re.compile(r'\b(\w+)=["\']?([^"\'\s;]+\.py)\b')  # RUNNER=".../codex_critic.py"
VARIABLE = re.compile(r'\$\{?(\w+)')
SCRIPT = re.compile(r'[\w.-]+\.py\b')


def plugin_sources(root):
    return {package.source for package in validator.load_packages(root).values()}


def plugin_of(path, sources):
    return next((source for source in sources if path.startswith(f'{source}/')), None)


def shipped_texts(root, sources):
    """Return {path: text} for each UTF-8 file in a plugin directory in sources, outside the plugin's tests/."""
    texts = {}
    for name in sorted(git_files(root)):
        source = plugin_of(name, sources)
        if source and not name.startswith(f'{source}/tests/') and (root / name).is_file():
            try:
                texts[name] = (root / name).read_text(encoding='utf-8')
            except UnicodeDecodeError:
                continue
    return texts


def floor(text):
    """Return the (major, minor) floor of a Python file, or None when its requires-python line has another form."""
    match = REQUIRES.search(text)
    if not match:
        return DEFAULT_FLOOR
    version = FLOOR.fullmatch(match[1].strip())
    return (int(version[1]), int(version[2])) if version else None


def evaluated_annotations(tree):
    """Yield each annotation that Python evaluates when it defines a function, a class, or the module."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = node.args
            every = [*args.posonlyargs, *args.args, *args.kwonlyargs, args.vararg, args.kwarg]
            yield from (argument.annotation for argument in every if argument and argument.annotation)
            if node.returns:
                yield node.returns
        elif isinstance(node, (ast.Module, ast.ClassDef)):
            yield from (statement.annotation for statement in node.body if isinstance(statement, ast.AnnAssign))


def postponed(tree):
    """Return whether the module imports annotations from __future__, so that Python does not evaluate them."""
    return any(isinstance(statement, ast.ImportFrom) and statement.module == '__future__'
               and any(alias.name == 'annotations' for alias in statement.names) for statement in tree.body)


def script_problems(path, text, minimum):
    version = f'Python {minimum[0]}.{minimum[1]}'
    try:
        tree = ast.parse(text, filename=path, feature_version=minimum)
    except SyntaxError as error:
        return [f'{path}:{error.lineno}: {version} cannot parse it: {error.msg}']
    if minimum >= (3, 10) or postponed(tree):
        return []
    return [f'{path}:{annotation.lineno}: {version} evaluates this X | Y annotation'
            for annotation in evaluated_annotations(tree)
            if any(isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr)
                   for node in ast.walk(annotation))]


def run_problems(path, text, floors):
    """Return each line of a text file that runs a script above the default floor with python or python3."""
    found = []
    assigned = dict(ASSIGNMENT.findall(text))
    for number, line in enumerate(text.splitlines(), 1):
        for match in RUN.finditer(line):
            command, options, target = match.groups()
            variable = VARIABLE.match(target.strip('\\"\''))
            script = SCRIPT.search(target) or (variable and SCRIPT.search(assigned.get(variable[1], '')))
            if not script or 'uv run' in line[:match.start()] or 'c' in options or 'm' in options:
                continue
            minimum = floors.get(script[0], DEFAULT_FLOOR)
            if minimum > DEFAULT_FLOOR:
                found.append(f'{path}:{number}: {command} runs {script[0]}, which needs Python '
                             f'{minimum[0]}.{minimum[1]}')
    return found


def problems(texts, sources):
    """Return the problems of the shipped files in texts {path: text}, each in a plugin directory in sources."""
    found = []
    floors = {}  # {plugin directory: {script file name: floor}}
    for path, text in texts.items():
        if path.endswith('.py'):
            minimum = floor(text)
            if minimum is None:
                found.append(f'{path}: write the requires-python line as ">=X.Y"')
                continue
            scripts = floors.setdefault(plugin_of(path, sources), {})
            name = PurePosixPath(path).name
            scripts[name] = max(scripts.get(name, minimum), minimum)
            found += script_problems(path, text, minimum)
    for path, text in texts.items():
        if not path.endswith('.py'):
            found += run_problems(path, text, floors.get(plugin_of(path, sources), {}))
    return found


class ScriptPythonFloorTests(unittest.TestCase):
    def test_scripts_read_under_their_floor(self):
        sources = plugin_sources(ROOT)
        texts = shipped_texts(ROOT, sources)
        self.assertTrue(any(path.endswith('.py') for path in texts), 'no shipped Python file found')
        self.assertEqual(problems(texts, sources), [],
                         'keep the syntax of the floor, add `from __future__ import annotations`, or run the '
                         "script as `uv run --no-project --python '>=X.Y' python <script>`; see "
                         'CONTRIBUTING.md, "Python requirements"')

    def test_fixture(self):
        header = '# /// script\n# requires-python = "{}"\n# ///\n'
        match = 'match x:\n    case 1:\n        pass\n'
        texts = {
            'demo/scripts/new.py': header.format('>=3.11') + 'print(1)\n',
            'demo/scripts/old.py': 'print(1)\n',
            'demo/scripts/match.py': match,
            'demo/scripts/match_310.py': header.format('>=3.10') + match,
            'demo/scripts/union.py': 'def f(a: int | None) -> str | None:\n    b: int | None = a\n',
            'demo/scripts/union_postponed.py': 'from __future__ import annotations\ndef f(a: int | None): pass\n',
            'demo/scripts/range.py': header.format('>=3.10,<4'),
            'other/scripts/other.py': header.format('>=3.11'),
            'demo/skills/one/SKILL.md': (
                'python3 "${CLAUDE_PLUGIN_ROOT}/scripts/new.py" read\n'
                "uv run --no-project --python '>=3.11' python \"<plugin-root>/scripts/new.py\" read\n"
                'RUNNER="<skill-dir>/scripts/new.py"\n'
                'python3 "$RUNNER" go && python -B "$PLUGIN/scripts/new.py"\n'
                'python3 <plugin-root>/scripts/old.py && python3 -c "import new" && <python> scripts/new.py\n'
                'python3 other.py\n'),
        }
        found = [re.sub(r'(cannot parse it): .*', r'\1', problem)  # the parser message varies by version
                 for problem in problems(texts, {'demo', 'other'})]
        self.assertEqual(found, [
            'demo/scripts/match.py:3: Python 3.9 cannot parse it',
            'demo/scripts/union.py:1: Python 3.9 evaluates this X | Y annotation',
            'demo/scripts/union.py:1: Python 3.9 evaluates this X | Y annotation',
            'demo/scripts/range.py: write the requires-python line as ">=X.Y"',
            'demo/skills/one/SKILL.md:1: python3 runs new.py, which needs Python 3.11',
            'demo/skills/one/SKILL.md:4: python3 runs new.py, which needs Python 3.11',
            'demo/skills/one/SKILL.md:4: python runs new.py, which needs Python 3.11',
        ])


if __name__ == '__main__':
    unittest.main()
