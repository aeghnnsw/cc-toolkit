"""The changelog entry files, the release step, and the version script at their command interfaces (#298)."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
LINK = ' See [#{0}](https://github.com/aeghnnsw/cc-toolkit/issues/{0}).'
CHANGELOG = ('# Changelog\n\n## [Unreleased]\n\n### Added\n\n### Changed\n\n- Repository: an old entry.'
             + LINK.format(1) + '\n\n## 2026-11-22\n\n### Changed\n\n- Repository: a released entry.'
             + LINK.format(1) + '\n')


class ReleaseFixture(unittest.TestCase):
    """A repository with a demo plugin on three hosts and a versioned Claude Code skill, on branch master."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.git('init', '-q', '-b', 'master')
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.write('package-validation.json', {'version': 1, 'defaults': {'exempt': ['tests/']}, 'plugins': {}})
        self.write('.claude-plugin/marketplace.json', {'name': 'fixture', 'plugins': [{'name': 'demo',
                                                                                     'source': './demo'}]})
        self.write('.agents/plugins/marketplace.json', {'name': 'fixture', 'plugins': [
            {'name': 'demo', 'source': {'source': 'local', 'path': './demo'}}]})
        self.write('demo/.claude-plugin/plugin.json', {'name': 'demo', 'version': '1.0.0'})
        self.write('demo/.codex-plugin/plugin.json', {'name': 'demo', 'version': '1.0.0', 'skills': './codex-skills/'})
        self.write('demo/.antigravity-plugin/plugin.json', {'name': 'demo', 'version': '1.0.0',
                                                            'skills': './antigravity-skills/'})
        self.write('demo/skills/greet/SKILL.md', '---\nname: greet\nversion: 1.0.0\ndescription: Hello.\n---\nHello.\n')
        for folder in ('codex-skills', 'antigravity-skills'):
            self.write(f'demo/{folder}/greet/SKILL.md', '---\nname: greet\ndescription: Hello.\n---\nHello.\n')
        self.write('CHANGELOG.md', CHANGELOG)
        self.commit()

    def git(self, *args, check=True):
        result = subprocess.run(['git', '-c', 'core.hooksPath=/dev/null', *args], cwd=self.root, text=True,
                                capture_output=True)
        if check and result.returncode:
            self.fail(f'git {" ".join(args)} failed: {result.stdout}{result.stderr}')
        return result

    def write(self, path, value):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(value, indent=2) + '\n' if isinstance(value, dict) else value)

    def read(self, path):
        return (self.root / path).read_text()

    def commit(self, message='Fixture change'):
        self.git('add', '-A')
        self.git('commit', '-qm', message)

    def run_script(self, name, *args):
        result = subprocess.run([sys.executable, str(SCRIPTS / name), *args], cwd=self.root, text=True,
                                capture_output=True)
        self.assertNotIn('Traceback', result.stderr)
        return result

    def validate(self, base='master'):
        return self.run_script('validate_packages.py', '--base', base)

    def snapshot(self):
        return {path: path.read_bytes() for path in self.root.rglob('*') if path.is_file() and '.git' not in path.parts}


class VersionScriptTests(ReleaseFixture):
    def change(self, branch, issue):
        """On a new branch from master, change a shared file and the skill, and raise every version to 1.1.0."""
        self.git('switch', '-q', '-c', branch, 'master')
        self.write(f'demo/scripts/{branch}.py', f'# {branch}\n')
        self.write(f'demo/skills/greet/{branch}.md', f'{branch} notes.\n')
        for host in ('claude', 'codex', 'antigravity'):
            path = f'demo/.{host}-plugin/plugin.json'
            self.write(path, self.read(path).replace('"1.0.0"', '"1.1.0"'))
        self.write('demo/skills/greet/SKILL.md', self.read('demo/skills/greet/SKILL.md').replace('1.0.0', '1.1.0'))
        self.write(f'changelog.d/{issue}.md', f'### Changed\n\n- demo (Claude Code, Codex, and Antigravity 1.1.0): '
                                              f'{branch} change in greet 1.1.0.{LINK.format(issue)}\n')
        self.commit(branch)

    def test_rebase_has_no_changelog_conflict_and_the_script_raises_the_versions_above_master(self):
        self.change('first', 2)
        self.change('second', 3)
        result = self.validate()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.git('switch', '-q', 'master')
        self.git('merge', '-q', '--ff-only', 'first')
        self.git('switch', '-q', 'second')
        self.git('rebase', '-q', 'master')
        # Each branch adds its own entry file, so the rebase does not conflict in a changelog file. Git merges
        # the equal versions of both sides without a conflict, so the branch is left at the versions of master.
        self.assertEqual(sorted(path.name for path in (self.root / 'changelog.d').iterdir()), ['2.md', '3.md'])
        self.assertEqual(self.read('CHANGELOG.md'), CHANGELOG)
        self.assertIn('demo [claude]: version must increase above 1.1.0', self.validate().stderr)

        result = self.run_script('next_versions.py', '--base', 'master')
        self.assertEqual(result.returncode, 0, result.stderr)
        for host in ('claude', 'codex', 'antigravity'):
            path = f'demo/.{host}-plugin/plugin.json'
            with self.subTest(host=host):
                self.assertEqual(json.loads(self.read(path))['version'], '1.2.0')
                self.assertIn(f'demo [{host}]: 1.1.0 -> 1.2.0 in {path}', result.stdout)
        self.assertEqual(self.read('demo/.codex-plugin/plugin.json'),
                         json.dumps({'name': 'demo', 'version': '1.2.0', 'skills': './codex-skills/'}, indent=2) + '\n')
        self.assertIn('version: 1.2.0\n', self.read('demo/skills/greet/SKILL.md'))
        self.assertEqual(self.read('changelog.d/3.md'), '### Changed\n\n- demo (Claude Code, Codex, and Antigravity '
                         f'1.2.0): second change in greet 1.2.0.{LINK.format(3)}\n')
        self.assertEqual(self.read('changelog.d/2.md').count('1.1.0'), 2)
        result = self.validate()
        self.assertEqual(result.returncode, 0, result.stderr)

        before = self.snapshot()
        result = self.run_script('next_versions.py', '--base', 'master')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('No change', result.stdout)
        self.assertEqual(self.snapshot(), before)

    def test_patch_part_raises_only_the_affected_host_and_writes_its_bullet(self):
        self.git('switch', '-q', '-c', 'fix')
        self.write('demo/codex-skills/greet/SKILL.md', '---\nname: greet\ndescription: Hello.\n---\nFixed.\n')
        self.write('changelog.d/4.md', f'### Changed\n\n- demo (Codex 1.0.0): a fix.{LINK.format(4)}\n'
                                       f'- Repository: a test.{LINK.format(4)}\n')
        result = self.run_script('next_versions.py', '--base', 'master', '--part', 'patch')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([json.loads(self.read(f'demo/.{host}-plugin/plugin.json'))['version']
                          for host in ('claude', 'codex', 'antigravity')], ['1.0.0', '1.0.1', '1.0.0'])
        self.assertIn('- demo (Codex 1.0.1): a fix.', self.read('changelog.d/4.md'))
        result = self.validate()
        self.assertEqual(result.returncode, 0, result.stderr)


class ReleaseStepTests(ReleaseFixture):
    def test_release_moves_the_entry_files_into_their_sections_newest_first_and_deletes_them(self):
        entries = {
            4: '### Changed\n\n- Repository: change four.' + LINK.format(4) + '\n',
            5: ('### Added\n\n- Repository: addition five.' + LINK.format(5) + '\n\n### Changed\n\n'
                '- Repository: change five.' + LINK.format(5) + '\n- Repository: more of five.' + LINK.format(5) + '\n'),
            6: '### Removed\n\n- Repository: removal six.' + LINK.format(6) + '\n',
        }
        for issue, text in entries.items():
            self.write(f'changelog.d/{issue}.md', text)
            self.commit(f'Entry {issue}')
        self.git('switch', '-q', '-c', 'release')
        result = self.run_script('release_changelog.py')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Moved 5 bullet(s) from 3 entry file(s)', result.stdout)
        self.assertFalse((self.root / 'changelog.d').exists() and any((self.root / 'changelog.d').iterdir()))
        self.assertEqual(self.read('CHANGELOG.md'), (
            '# Changelog\n\n## [Unreleased]\n\n'
            '### Added\n\n- Repository: addition five.' + LINK.format(5) + '\n\n'
            '### Removed\n\n- Repository: removal six.' + LINK.format(6) + '\n\n'
            '### Changed\n\n- Repository: change five.' + LINK.format(5) + '\n- Repository: more of five.'
            + LINK.format(5) + '\n- Repository: change four.' + LINK.format(4) + '\n- Repository: an old entry.'
            + LINK.format(1) + '\n\n## 2026-11-22\n\n### Changed\n\n- Repository: a released entry.'
            + LINK.format(1) + '\n'))
        result = self.validate()
        self.assertEqual(result.returncode, 0, result.stderr)
        before = self.snapshot()
        result = self.run_script('release_changelog.py')
        self.assertIn('No entry files', result.stdout)
        self.assertEqual(self.snapshot(), before)


if __name__ == '__main__':
    unittest.main()
