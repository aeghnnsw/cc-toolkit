"""A Claude skill writes each Claude configuration path in the CLAUDE_CONFIG_DIR form.

Claude Code reads its configuration from CLAUDE_CONFIG_DIR when the variable is set, as in a T3 Code
profile. A skill that names ~/.claude/settings.json on a line with no CLAUDE_CONFIG_DIR reads or writes
a file that the running Claude Code does not load (#464). The form is
"${CLAUDE_CONFIG_DIR:-$HOME/.claude}/<file>", as in gtd-setup.
"""
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from package_support import ROOT, git_files

# A home-relative path to a Claude configuration file: settings.json, settings.local.json, CLAUDE.md and its
# backups, or the statusline script.
CONFIG_PATH = re.compile(r'(?:~|\$HOME|\$\{HOME\})/\.claude/(?:settings(?:\.local)?\.json|CLAUDE\.md|'
                         r'statusline-command\.sh)')
CLAUDE_COPY = re.compile(r'^[^/]+/skills/')


def problems(root):
    """Return each line of a Claude skill copy that names a configuration path with no CLAUDE_CONFIG_DIR."""
    found = []
    for name in sorted(git_files(root)):
        path = root / name
        if not CLAUDE_COPY.match(name) or name.startswith('task-loop/') or not path.is_file():
            continue
        try:
            lines = path.read_text(encoding='utf-8').splitlines()
        except UnicodeDecodeError:
            continue
        found += [f'{name}:{number}: {match}' for number, line in enumerate(lines, 1)
                  if 'CLAUDE_CONFIG_DIR' not in line for match in CONFIG_PATH.findall(line)]
    return found


class ConfigDirTests(unittest.TestCase):
    def test_claude_skills_read_claude_config_dir(self):
        self.assertEqual(problems(ROOT), [], 'write "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/<file>"')

    def test_fixture(self):
        cases = {  # text: number of problems
            'Read `~/.claude/settings.json`.\n': 1,
            'cp a ~/.claude/statusline-command.sh\n': 1,
            'Copy `$HOME/.claude/CLAUDE.md` to `~/.claude/CLAUDE.md.bak-1`.\n': 2,
            'Read `~/.claude/settings.local.json`.\n': 1,
            'Read `${CLAUDE_CONFIG_DIR:-$HOME/.claude}/settings.json`.\n': 0,
            'Plugins live in ~/.claude/plugins/cache/.\n': 0,
        }
        for text, count in cases.items():
            with self.subTest(text=text), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / 'demo/skills/one').mkdir(parents=True)
                (root / 'demo/skills/one/SKILL.md').write_text(text, encoding='utf-8')
                (root / 'demo/codex-skills/one').mkdir(parents=True)
                (root / 'demo/codex-skills/one/SKILL.md').write_text(text, encoding='utf-8')
                subprocess.run(['git', 'init', '-q'], cwd=root, check=True)
                found = problems(root)
                self.assertEqual(len(found), count, found)
                self.assertTrue(all(problem.startswith('demo/skills/one/SKILL.md:1: ') for problem in found))


if __name__ == '__main__':
    unittest.main()
