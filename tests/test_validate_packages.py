"""Package validation behavior at the command interface."""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest


COMMAND = Path(__file__).resolve().parents[1] / 'scripts' / 'validate_packages.py'
SEVERAL_ISSUES_FORM = '- Repository: <change> (#M, #K). See [#N](https://github.com/aeghnnsw/cc-toolkit/issues/N).'


class PackageValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git('init', '-q')
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.write('package-validation.json', {
            'version': 1, 'defaults': {'exempt': ['tests/', 'README.md', 'CHANGELOG.md']},
            'plugins': {},
        })
        self.write('.claude-plugin/marketplace.json', {
            'name': 'fixture', 'plugins': [{'name': 'demo', 'source': './demo'}],
        })
        self.write('demo/.claude-plugin/plugin.json', {'name': 'demo', 'version': '1.0.0'})
        self.write('demo/skills/greet/SKILL.md', '---\nname: greet\ndescription: Say hello.\n---\nHello.\n')
        self.commit()
        self.git('tag', 'baseline')

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.root, text=True, stderr=subprocess.STDOUT).strip()

    def write(self, path, value):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(value) + '\n' if isinstance(value, (dict, list)) else value)

    def read_json(self, path):
        return json.loads((self.root / path).read_text())

    def commit(self):
        self.git('add', '.')
        self.git('-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'Fixture change')

    def run_check(self, base='baseline', env=None):
        result = subprocess.run([sys.executable, str(COMMAND), '--base', base], cwd=self.root,
                                text=True, capture_output=True, env=env)
        self.assertNotIn('Traceback', result.stderr)
        return result

    def assert_failure(self, text):
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(text, result.stderr + result.stdout)
        return result

    def test_valid_single_host_package_passes_without_writes(self):
        before = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*')
                  if p.is_file() and '.git' not in p.relative_to(self.root).parts}
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('1 host registration', result.stdout)
        after = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*')
                 if p.is_file() and '.git' not in p.relative_to(self.root).parts}
        self.assertEqual(before, after)

    def test_invalid_registration_reports_its_location(self):
        self.write('.claude-plugin/marketplace.json', {
            'name': 'fixture', 'plugins': [{'name': 'demo', 'source': './missing'}],
        })
        self.assert_failure('missing')

    def test_duplicate_registration_is_rejected(self):
        data = self.read_json('.claude-plugin/marketplace.json')
        data['plugins'].append(data['plugins'][0])
        self.write('.claude-plugin/marketplace.json', data)
        self.assert_failure('duplicate')

    def test_malformed_manifest_reports_file_without_traceback(self):
        self.write('demo/.claude-plugin/plugin.json', '{broken')
        self.assert_failure('demo/.claude-plugin/plugin.json')

    def test_manifest_identity_must_match_registration(self):
        self.write('demo/.claude-plugin/plugin.json', {'name': 'other', 'version': '1.0.0'})
        self.assert_failure('identity')

    def test_declared_resources_must_exist_inside_the_package(self):
        for value, expected in [('./missing/', 'missing'), ('../outside/', 'inside')]:
            with self.subTest(value=value):
                self.write('demo/.claude-plugin/plugin.json', {
                    'name': 'demo', 'version': '1.0.0', 'skills': value,
                })
                self.assert_failure(expected)
        self.write('demo/.claude-plugin/plugin.json', {
            'name': 'demo', 'version': '1.0.0', 'skills': './linked',
        })
        (self.root / 'outside').mkdir()
        (self.root / 'demo/linked').symlink_to(self.root / 'outside', target_is_directory=True)
        self.assert_failure('outside')

    def test_skill_header_contract(self):
        self.bump()  # Only a header error can fail.
        for header in [
            'name: greet',
            'name: greet\ndescription: ',
            'name: INVALID\ndescription: Hello',
            'name: greet\nname: greet\ndescription: Hello',
            'name: greet\ndescription: Hello\nversion: 1.0',
            'name: greet\ndescription: Hello\nversion: 1.0.0\nversion: 1.0.1',
        ]:
            with self.subTest(header=header):
                self.write('demo/skills/greet/SKILL.md', '---\n' + header + '\n---\n')
                self.assert_failure('SKILL.md')
        self.write('demo/skills/greet/SKILL.md', 'name: greet\ndescription: Hello')
        self.assert_failure('SKILL.md')

    def test_explicit_resource_contract(self):
        rules = self.read_json('package-validation.json')
        rules['plugins']['demo'] = {'resources': [{'path': 'worker.toml', 'hosts': ['claude']}]}
        self.write('package-validation.json', rules)
        self.assert_failure('worker.toml')
        self.write('demo/worker.toml', 'broken = [')
        self.assert_failure('worker.toml')
        self.write('demo/worker.toml', 'name = "worker"')
        self.commit()
        self.git('tag', '-f', 'baseline')
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)

    def add_codex(self, skills=True):
        self.write('.agents/plugins/marketplace.json', {
            'name': 'fixture', 'plugins': [{'name': 'demo', 'source': {'source': 'local', 'path': './demo'}}],
        })
        manifest = {'name': 'demo', 'version': '1.0.0'}
        if skills:
            manifest['skills'] = './codex-skills/'
            self.write('demo/codex-skills/greet/SKILL.md', '---\nname: greet\ndescription: Hello.\n---\n')
        self.write('demo/.codex-plugin/plugin.json', manifest)
        self.commit()
        self.git('tag', '-f', 'baseline')

    def add_antigravity(self, fields=None, skills=True, commit=True):
        manifest = {'name': 'demo', 'version': '1.0.0'}
        if skills:
            manifest['skills'] = './antigravity-skills/'
            self.write('demo/antigravity-skills/greet/SKILL.md', '---\nname: greet\ndescription: Hello.\n---\n')
        self.write('demo/.antigravity-plugin/plugin.json', {**manifest, **(fields or {})})
        if commit:
            self.commit()
            self.git('tag', '-f', 'baseline')

    def test_antigravity_manifest_in_a_registered_folder_is_a_registration(self):
        self.add_antigravity()
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('2 host registration', result.stdout)

    def test_antigravity_manifest_identity_version_and_fields(self):
        for fields, expected in [({'name': 'other'}, 'identity must match demo'),
                                 ({'version': '1.0'}, 'invalid plugin version'),
                                 ({'hooks': './hooks.json'}, "unknown field 'hooks'")]:
            with self.subTest(fields=fields):
                self.add_antigravity(fields, commit=False)
                self.assert_failure(expected)

    def test_each_claude_copy_needs_an_antigravity_copy_of_the_same_name(self):
        self.add_antigravity(commit=False)
        self.write('demo/skills/wave/SKILL.md', '---\nname: wave\ndescription: Wave.\n---\n')
        self.bump()
        self.assert_failure('demo/skills/wave/SKILL.md: skill wave has no Antigravity copy; '
                            'add demo/antigravity-skills/wave/SKILL.md')
        self.write('demo/antigravity-skills/wave/SKILL.md', '---\nname: wave\ndescription: Wave.\n---\n')
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_antigravity_manifest_without_a_skills_path_fails_on_claude_copies(self):
        self.add_antigravity(skills=False, commit=False)
        self.assert_failure('skill greet has no Antigravity copy; declare a skills path in '
                            'demo/.antigravity-plugin/plugin.json')

    def test_antigravity_skills_path_cannot_be_the_claude_skills_folder(self):
        self.add_antigravity({'skills': './skills/'}, skills=False, commit=False)
        self.assert_failure('demo/.antigravity-plugin/plugin.json: the skills path skills is the Claude Code '
                            'skills folder')

    def test_antigravity_copy_with_another_name_names_the_file_to_fix(self):
        self.add_antigravity(commit=False)
        self.write('demo/antigravity-skills/greet/SKILL.md', '---\nname: hello\ndescription: Hello.\n---\n')
        self.assert_failure('skill greet has no Antigravity copy; set name: greet in '
                            'demo/antigravity-skills/greet/SKILL.md')

    def test_new_antigravity_registration_needs_no_version_increase(self):
        self.add_antigravity(commit=False)
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_antigravity_owned_files_require_only_an_antigravity_version(self):
        self.add_antigravity()
        cases = [('antigravity-skills/greet/SKILL.md', '---\nname: greet\ndescription: Changed.\n---\n'),
                 ('hooks.json', {'hooks': {}}), ('mcp_config.json', {'mcpServers': {}}), ('rules/style.md', 'Rule.\n')]
        for path, value in cases:
            with self.subTest(path=path):
                self.git('reset', '--hard', 'baseline')
                self.git('clean', '-fd')
                self.write(f'demo/{path}', value)
                self.assert_failure(f'demo [antigravity]: version must increase above 1.0.0; changed demo/{path}')
                self.bump('antigravity')
                result = self.run_check()
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_claude_copy_and_agents_follow_their_hosts(self):
        self.add_antigravity()
        self.write('demo/skills/greet/SKILL.md', '---\nname: greet\ndescription: Claude change.\n---\n')
        self.bump()
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.write('demo/agents/worker.md', '---\nname: worker\ndescription: Work.\n---\n')
        self.assert_failure('demo [antigravity]: version must increase above 1.0.0; changed demo/agents/worker.md')

    def test_rules_accept_the_antigravity_host(self):
        self.add_antigravity()
        rules = self.read_json('package-validation.json')
        rules['plugins']['demo'] = {'ownership': [{'path': 'scripts/', 'hosts': ['antigravity']}]}
        self.write('package-validation.json', rules)
        self.write('demo/scripts/run.py', '# Run.\n')
        self.bump('antigravity')
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_claude_agents_may_be_declared_markdown_files_that_claude_owns(self):
        self.add_antigravity()
        manifest = self.read_json('demo/.claude-plugin/plugin.json')
        self.write('demo/.claude-plugin/plugin.json', {**manifest, 'agents': ['./claude-agents/worker.md']})
        self.write('demo/claude-agents/worker.md', '---\nname: worker\ndescription: Work.\n---\n')
        self.bump()
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.commit()
        self.git('tag', '-f', 'baseline')
        self.write('demo/claude-agents/worker.md', '---\nname: worker\ndescription: Changed.\n---\n')
        self.assert_failure('demo [claude]: version must increase above 1.0.1; changed demo/claude-agents/worker.md '
                            '(host discovery path)')
        self.bump(value='1.0.2')
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_shared_file_and_antigravity_manifest_require_an_antigravity_version(self):
        self.add_antigravity()
        self.write('demo/shared.txt', 'Shared runtime data.\n')
        self.bump()
        self.assert_failure('demo [antigravity]: version must increase above 1.0.0; changed demo/shared.txt '
                            '(unclassified file; all registered hosts)')
        self.bump('antigravity')
        self.assertEqual(self.run_check().returncode, 0)
        self.commit()
        self.git('tag', '-f', 'baseline')
        manifest = self.read_json('demo/.antigravity-plugin/plugin.json')
        self.write('demo/.antigravity-plugin/plugin.json', {**manifest, 'description': 'Changed.'})
        self.assert_failure('demo [antigravity]: version must increase above 1.0.1; '
                            'changed demo/.antigravity-plugin/plugin.json (host manifest)')

    def test_two_registered_names_are_rejected_only_for_an_antigravity_registration(self):
        self.write('.agents/plugins/marketplace.json', {
            'name': 'fixture', 'plugins': [{'name': 'other', 'source': {'source': 'local', 'path': './demo'}}],
        })
        self.write('demo/.codex-plugin/plugin.json', {'name': 'other', 'version': '1.0.0'})
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.add_antigravity(commit=False)
        self.assert_failure('demo: registered as both demo and other; Antigravity needs one name')

    def test_claude_code_still_loads_agents_when_agent_files_are_declared(self):
        self.write('demo/agents/legacy.md', '---\nname: legacy\ndescription: Old.\n---\n')
        manifest = self.read_json('demo/.claude-plugin/plugin.json')
        self.write('demo/.claude-plugin/plugin.json', {**manifest, 'agents': ['./claude-agents/worker.md']})
        self.write('demo/claude-agents/worker.md', '---\nname: worker\ndescription: Work.\n---\n')
        self.add_antigravity()
        self.write('demo/agents/legacy.md', '---\nname: legacy\ndescription: Changed.\n---\n')
        self.bump('antigravity')
        self.assert_failure('demo [claude]: version must increase above 1.0.0; changed demo/agents/legacy.md')

    def test_dual_host_and_hooks_only_packages_accept_optional_roots(self):
        (self.root / 'demo/skills/greet/SKILL.md').unlink()
        (self.root / 'demo/skills/greet').rmdir()
        (self.root / 'demo/skills').rmdir()
        self.write('demo/hooks/hooks.json', {'hooks': {}})
        self.write('demo/agents/worker.md', '---\nname: worker\nexamples:\n  - nested YAML\n---\n')
        self.add_codex(skills=False)
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('2 host registration', result.stdout)

    def bump(self, host='claude', value='1.0.1'):
        path = f'demo/.{host}-plugin/plugin.json'
        data = self.read_json(path)
        data['version'] = value
        self.write(path, data)

    def test_changed_skill_requires_one_version_increase_for_the_branch(self):
        self.write('demo/skills/greet/SKILL.md', '---\nname: greet\ndescription: Changed.\n---\n')
        self.assert_failure('version')
        self.bump()
        self.commit()
        self.write('demo/skills/greet/SKILL.md', '---\nname: greet\ndescription: Changed again.\n---\n')
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_host_specific_change_requires_only_that_host(self):
        self.add_codex()
        self.write('demo/codex-skills/greet/SKILL.md', '---\nname: greet\ndescription: Codex change.\n---\n')
        self.bump('codex')
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_explicit_ownership_and_contributor_exemptions(self):
        self.add_codex()
        self.write('demo/scripts/sync.py', '# original\n')
        rules = self.read_json('package-validation.json')
        rules['plugins']['demo'] = {
            'ownership': [{'path': 'scripts/sync.py', 'hosts': ['codex']}],
            'resources': [{'path': 'scripts/sync.py', 'hosts': ['codex']}],
        }
        self.write('package-validation.json', rules)
        self.commit()
        self.git('tag', '-f', 'baseline')
        self.write('demo/scripts/sync.py', '# changed\n')
        self.write('demo/tests/test_example.py', '# test\n')
        self.write('demo/README.md', 'Contributor information.\n')
        self.bump('codex')
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_shared_unknown_file_requires_both_hosts_and_explains_why(self):
        self.add_codex()
        self.write('demo/shared.txt', 'Shared runtime data.\n')
        self.assert_failure('unclassified file; all registered hosts')
        self.bump('claude')
        self.assert_failure('demo [codex]')
        self.bump('codex')
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_required_readme_overrides_contributor_exemption(self):
        self.write('demo/README.md', 'Runtime instructions.\n')
        rules = self.read_json('package-validation.json')
        rules['plugins']['demo'] = {'resources': [{'path': 'README.md', 'hosts': ['claude']}]}
        self.write('package-validation.json', rules)
        self.commit()
        self.git('tag', '-f', 'baseline')
        self.write('demo/README.md', 'Changed runtime instructions.\n')
        self.assert_failure('version')

    def test_missing_target_and_unrelated_history_fail_clearly(self):
        result = self.run_check('missing-ref')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('baseline', result.stderr)
        self.assertIn('--base', result.stderr)
        self.git('checkout', '--orphan', 'unrelated')
        self.git('-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'Unrelated history')
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('baseline', result.stderr)

    def test_python_without_tomllib_names_the_uv_command(self):
        with tempfile.TemporaryDirectory() as shadow:
            Path(shadow, 'tomllib.py').write_text(
                "raise ModuleNotFoundError(\"No module named 'tomllib'\", name='tomllib')\n")
            result = self.run_check('abc123', env={**os.environ, 'PYTHONPATH': shadow})
        self.assertEqual(result.returncode, 1)
        self.assertIn(f'Python {sys.version.split()[0]} is running.', result.stderr)
        self.assertIn(f"uv run --no-project --python '>=3.11' python {shlex.quote(str(COMMAND))} --base abc123",
                      result.stderr)

    def test_root_tests_without_tomllib_stop_with_one_uv_message(self):
        tests = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory() as shadow:
            Path(shadow, 'tomllib.py').write_text(
                "raise ModuleNotFoundError(\"No module named 'tomllib'\", name='tomllib')\n")
            # Every root test module except this one, so that a broken guard cannot start this test again.
            command = [sys.executable, '-m', 'unittest', 'discover', '-s', str(tests), '-p', 'test_[!v]*.py']
            result = subprocess.run(command, cwd=tests.parent, text=True, capture_output=True,
                                    env={**os.environ, 'PYTHONPATH': shadow})
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stderr.count('FAIL: the root tests need Python 3.11'), 1, result.stderr)
        self.assertIn(f'Python {sys.version.split()[0]} is running.', result.stderr)
        self.assertIn("uv run --no-project --python '>=3.11' python -m unittest discover -s tests -p 'test_*.py'",
                      result.stderr)
        self.assertNotIn('Traceback', result.stderr)

    def test_version_only_increases_pass_and_regressions_fail(self):
        self.bump(value='1.0.1')
        self.assertEqual(self.run_check().returncode, 0)
        self.bump(value='0.9.9')
        self.assert_failure('version must increase')
        self.bump(value='1.0.01')
        self.assert_failure('invalid plugin version')

    def write_skill(self, description, version=None, path='demo/skills/greet/SKILL.md'):
        line = f'version: {version}\n' if version else ''
        self.write(path, f'---\nname: {Path(path).parent.name}\ndescription: {description}\n{line}---\n')

    def version_baseline_skill(self):
        self.write_skill('Say hello.', '1.0.0')
        self.commit()
        self.git('tag', '-f', 'baseline')

    def test_changed_versioned_skill_requires_a_skill_version_increase(self):
        self.version_baseline_skill()
        self.write('demo/skills/greet/references/notes.md', 'Changed reference.\n')
        self.bump()
        result = self.assert_failure('demo [claude]: skill greet version must increase above 1.0.0')
        self.assertIn('changed demo/skills/greet/references/notes.md (host discovery path)', result.stderr)
        self.write_skill('Say hello.', '1.1.0')
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_new_skill_and_first_skill_version_need_no_increase(self):
        self.write_skill('Changed.', '1.0.0')
        self.write_skill('Wave.', '1.0.0', 'demo/skills/wave/SKILL.md')
        self.bump()
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_source_move_keeps_skill_version_history(self):
        self.version_baseline_skill()
        self.git('mv', 'demo', 'relocated')
        registry = self.read_json('.claude-plugin/marketplace.json')
        registry['plugins'][0]['source'] = './relocated'
        self.write('.claude-plugin/marketplace.json', registry)
        self.write('relocated/.claude-plugin/plugin.json', {'name': 'demo', 'version': '1.0.1'})
        self.assert_failure('skill greet version must increase above 1.0.0')
        self.write_skill('Say hello.', '1.0.1', 'relocated/skills/greet/SKILL.md')
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_exempt_skill_file_needs_no_skill_version_increase(self):
        self.version_baseline_skill()
        rules = self.read_json('package-validation.json')
        rules['plugins']['demo'] = {'exempt': ['skills/greet/evals/']}
        self.write('package-validation.json', rules)
        self.write('demo/skills/greet/evals/case.json', {'prompt': 'Hello'})
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_removing_a_skill_version_fails(self):
        self.version_baseline_skill()
        self.write_skill('Say hello.')
        self.bump()
        self.assert_failure('demo [claude]: skill greet lost its version 1.0.0 in demo/skills/greet/SKILL.md')

    def changelog_baseline(self, old='- Dev Skills: an old entry. See [#1](https://example.invalid/1).'):
        self.write('CHANGELOG.md', f'# Changelog\n\n## [Unreleased]\n\n### Added\n\n### Changed\n\n{old}\n')
        self.commit()
        self.git('tag', '-f', 'baseline')

    def reset_changelog(self):
        self.git('checkout', '-q', 'baseline', '--', 'CHANGELOG.md')
        shutil.rmtree(self.root / 'changelog.d', ignore_errors=True)

    def add_bullet(self, bullet, issue=2, section='### Changed', path='changelog.d/2.md'):
        """Add a bullet first in its section of an entry file, and the section when the file lacks it."""
        if issue:
            bullet += f' See [#{issue}](https://github.com/aeghnnsw/cc-toolkit/issues/{issue}).'
        target = self.root / path
        text = target.read_text() if target.exists() else ''
        if f'{section}\n' not in text:
            text += f'{section}\n\n'
        self.write(path, text.replace(f'{section}\n\n', f'{section}\n\n{bullet}\n', 1))

    def test_new_entry_file_bullet_must_use_the_entry_form(self):
        self.changelog_baseline()
        self.add_bullet('- Repository: add a check.')
        self.assertEqual(self.run_check().returncode, 0)
        self.reset_changelog()
        self.add_bullet('- Repository: add a check for several issues (#3, #4).')
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)
        for bullet, issue in [
            ('- Repository: two issues. See [#2](https://github.com/aeghnnsw/cc-toolkit/issues/2) and '
             '[#3](https://github.com/aeghnnsw/cc-toolkit/issues/3).', None),
            ('- Repository: a wrong link. See [#2](https://github.com/aeghnnsw/cc-toolkit/issues/3).', None),
            ('- Repository: no link.', None),
            ('- Repository: two links. See [#2](https://github.com/aeghnnsw/cc-toolkit/issues/2).', 3),
            ('- Repository (Claude Code 1.0.0): a version.', 2),
            ('- Demo (Claude Code 1.0.1): a display name.', 2),
        ]:
            with self.subTest(bullet=bullet):
                self.reset_changelog()
                self.add_bullet(bullet, issue)
                result = self.assert_failure('changelog.d/2.md:3: the new bullet breaks the entry form')
                self.assertIn(SEVERAL_ISSUES_FORM, result.stderr)
        linked = '- Repository: a change. See [#2](https://github.com/aeghnnsw/cc-toolkit/issues/2).'
        for index, bullet in enumerate(['* Repository: another marker.', linked + '\n  ' + 'y' * 600,
                                        linked + '\n#' + 'y' * 600]):
            with self.subTest(index=index):
                self.reset_changelog()
                self.add_bullet(bullet, None)
                self.assert_failure('a new line must be a one-line bullet that starts with "- "')

    def test_new_plugin_bullet_names_each_increased_host_at_its_version(self):
        self.add_codex()
        self.add_antigravity()
        self.changelog_baseline()
        self.bump('claude', '1.1.0')
        self.bump('antigravity', '1.1.0')
        for hosts, error in [
            ('Antigravity 1.1.0, Claude Code 1.1.0', 'in that order'),
            ('Claude Code 1.1.0, Antigravity 1.1.0', 'with one version for hosts that ship the same version'),
            ('Claude Code and Antigravity 1.0.1', 'demo Claude Code is version 1.1.0 in demo/.claude-plugin/plugin.json, '
                                                  'not 1.0.1'),
            ('Claude Code 1.1.0', 'name each host whose demo version increased (Claude Code, Antigravity) and no other'),
            ('Claude Code, Codex, and Antigravity 1.1.0', 'demo Codex is version 1.0.0'),
            ('Claude Code 1.1.0, Codex 1.0.0, Antigravity 1.1.0', 'name each host whose demo version increased'),
        ]:
            with self.subTest(hosts=hosts):
                self.reset_changelog()
                self.add_bullet(f'- demo ({hosts}): a change.')
                self.assert_failure(error)
        self.reset_changelog()
        self.add_bullet('- other (Claude Code 1.0.0): a change.')
        self.assert_failure('other is not a registered plugin')
        self.reset_changelog()
        self.add_bullet('- demo (Claude Code and Antigravity 1.1.0): a change.')
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_version_increase_needs_a_new_entry_file_bullet(self):
        self.changelog_baseline()
        self.bump()
        self.add_bullet('- Repository: a change.')
        self.assert_failure('demo version increased (Claude Code 1.0.1); add a bullet for it to an entry file, '
                            'changelog.d/<issue>.md')
        (self.root / 'CHANGELOG.md').unlink()
        self.assert_failure('CHANGELOG.md: missing')

    def test_new_entry_file_bullet_length_and_placement(self):
        self.changelog_baseline()
        self.add_bullet('- Repository: ' + 'x' * 526 + '.')
        self.assertEqual(self.run_check().returncode, 0)
        self.add_bullet('- Repository: ' + 'y' * 527 + '.')
        self.assert_failure('changelog.d/2.md:3: the new bullet has 601 characters; the limit is 600')
        linked = '- Repository: a change. See [#2](https://github.com/aeghnnsw/cc-toolkit/issues/2).\n'
        for text, error in [
            (f'### Fixed\n\n{linked}', 'changelog.d/2.md:1: an entry file has only the headings ### Added, '
                                       '### Removed, and ### Changed'),
            (f'## [Unreleased]\n\n### Changed\n\n{linked}', 'an entry file has only the headings'),
            (linked, 'changelog.d/2.md:1: put the new bullet under ### Added, ### Removed, or ### Changed'),
            ('### Changed\n\n', 'changelog.d/2.md: add a bullet, or delete the empty entry file'),
        ]:
            with self.subTest(text=text):
                self.reset_changelog()
                self.write('changelog.d/2.md', text)
                self.assert_failure(error)

    def add_plugin(self):
        """Register the Claude Code plugin other; its new registration needs a bullet at version 1.0.0."""
        registry = self.read_json('.claude-plugin/marketplace.json')
        registry['plugins'].append({'name': 'other', 'source': './other'})
        self.write('.claude-plugin/marketplace.json', registry)
        self.write('other/.claude-plugin/plugin.json', {'name': 'other', 'version': '1.0.0'})

    def test_branch_adds_at_most_one_bullet_for_each_plugin_and_one_repository_bullet(self):
        self.changelog_baseline()
        self.bump()
        placements = [  # the (path, section) of each bullet, then the locations of the two bullets
            ([('changelog.d/2.md', '### Changed')] * 2, 'changelog.d/2.md:3', 'changelog.d/2.md:4'),
            ([('changelog.d/2.md', '### Changed'), ('changelog.d/3.md', '### Changed')],
             'changelog.d/2.md:3', 'changelog.d/3.md:3'),
            ([('changelog.d/2.md', '### Added'), ('changelog.d/2.md', '### Changed')],
             'changelog.d/2.md:3', 'changelog.d/2.md:6'),
        ]
        for start, label in [('- Repository:', 'Repository'), ('- demo (Claude Code 1.0.1):', 'demo')]:
            for places, first, second in placements:
                with self.subTest(label=label, places=places):
                    self.reset_changelog()
                    for index, (path, section) in enumerate(places):
                        self.add_bullet(f'{start} change {index}.', section=section, path=path)
                    result = self.assert_failure(
                        f'{second}: this branch adds a second {label} bullet; {first} has the first. A branch adds '
                        'at most one new bullet for each plugin and one new Repository bullet')
                    self.assertIn(SEVERAL_ISSUES_FORM, result.stderr)
        self.reset_changelog()
        self.add_plugin()
        self.add_bullet('- demo (Claude Code 1.0.1): a change.')
        self.add_bullet('- other (Claude Code 1.0.0): a change.', path='changelog.d/3.md')
        self.add_bullet('- Repository: a change (#3, #4).', section='### Added')
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_bullets_at_the_merge_base_are_not_counted(self):
        self.changelog_baseline()
        self.add_bullet('- Repository: an old change.')
        self.add_bullet('- Repository: another old change.', 3, path='changelog.d/3.md')
        self.commit()
        self.git('tag', '-f', 'baseline')
        self.add_bullet('- Repository: a new change.', 4, path='changelog.d/4.md')
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)
        (self.root / 'changelog.d/4.md').unlink()
        self.add_bullet('- Repository: a new change.')
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)
        # The release step moves the bullets of both entry files into CHANGELOG.md.
        self.git('checkout', '-q', 'baseline', '--', 'changelog.d')
        bullets = [(self.root / path).read_text().splitlines()[2] for path in ('changelog.d/2.md', 'changelog.d/3.md')]
        for path in ('changelog.d/2.md', 'changelog.d/3.md'):
            (self.root / path).unlink()
        text = (self.root / 'CHANGELOG.md').read_text()
        self.write('CHANGELOG.md', text.replace('### Changed\n\n', '### Changed\n\n' + '\n'.join(bullets) + '\n'))
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_entry_file_name_starts_with_the_issue_number(self):
        self.changelog_baseline()
        for path in ('changelog.d/2-second-change.md', 'changelog.d/3.md'):
            with self.subTest(path=path):
                self.reset_changelog()
                self.add_bullet('- Repository: a change.', path=path)
                self.assertEqual(self.run_check().returncode, 0)
        for path in ('changelog.d/notes.md', 'changelog.d/2.txt', 'changelog.d/2-Upper.md', 'changelog.d/sub/2.md'):
            with self.subTest(path=path):
                self.reset_changelog()
                self.add_bullet('- Repository: a change.', path=path)
                self.assert_failure(f'{path}: name the entry file changelog.d/<issue>.md')

    def test_new_changelog_md_bullet_fails_and_preamble_prose_passes(self):
        self.changelog_baseline()
        text = (self.root / 'CHANGELOG.md').read_text()
        self.write('CHANGELOG.md', text.replace('# Changelog\n', '# Changelog\n\nNew entries are in changelog.d/.\n'))
        self.assertEqual(self.run_check().returncode, 0)
        self.write('CHANGELOG.md', text.replace('### Changed\n\n', '### Changed\n\n- Repository: a change. '
                                                'See [#2](https://github.com/aeghnnsw/cc-toolkit/issues/2).\n'))
        self.assert_failure('CHANGELOG.md:9: add the new bullet to an entry file, changelog.d/<issue>.md, '
                            'not to CHANGELOG.md; the release step moves it')
        self.write('CHANGELOG.md', text + '\n## 2026-11-22\n\nA paragraph.\n')
        self.assert_failure('CHANGELOG.md:13: a new line must be a one-line bullet that starts with "- "')

    def test_moved_and_unchanged_changelog_bullets_are_not_checked(self):
        self.changelog_baseline()
        text = (self.root / 'CHANGELOG.md').read_text()
        self.write('CHANGELOG.md', text.replace('### Changed\n\n', '### Changed\n\n## 2026-11-22\n\n### Changed\n\n'))
        self.add_bullet('- Repository: a change.')
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_release_branch_moves_each_entry_file_bullet_and_changes_no_other_file(self):
        self.changelog_baseline()
        self.bump()
        self.add_bullet('- demo (Claude Code 1.0.1): a change.')
        self.commit()
        self.git('tag', '-f', 'baseline')
        entry = (self.root / 'changelog.d/2.md').read_text()
        bullet = entry.splitlines()[2]
        text = (self.root / 'CHANGELOG.md').read_text()
        (self.root / 'changelog.d/2.md').unlink()
        self.assert_failure('changelog.d/2.md:3: this branch deletes the entry file, but CHANGELOG.md lacks its bullet')
        self.write('CHANGELOG.md', text.replace('### Changed\n\n', f'### Changed\n\n{bullet}\n'))
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.write('demo/skills/greet/SKILL.md', '---\nname: greet\ndescription: Changed.\n---\n')
        self.bump(value='1.0.2')
        self.add_bullet('- demo (Claude Code 1.0.2): a change.', path='changelog.d/3.md')
        self.assert_failure('changelog.d/2.md: this branch deletes an entry file and changes changelog.d/3.md; run '
                            'the release step in a pull request of its own')

    def test_staged_unstaged_new_and_deleted_files_require_versions(self):
        for state in ('new', 'staged', 'unstaged', 'deleted'):
            with self.subTest(state=state):
                self.git('reset', '--hard', 'baseline')
                self.git('clean', '-fd')
                path = 'demo/skills/greet/SKILL.md'
                if state == 'deleted':
                    (self.root / path).unlink()
                else:
                    self.write('demo/runtime.txt' if state == 'new' else path,
                               'data' if state == 'new' else '---\nname: greet\ndescription: Changed\n---\n')
                if state == 'staged':
                    self.git('add', '.')
                self.assert_failure('version')

    def test_new_and_removed_registrations_need_no_old_host_version(self):
        self.write('.agents/plugins/marketplace.json', {
            'name': 'fixture', 'plugins': [{'name': 'demo', 'source': {'source': 'local', 'path': './demo'}}],
        })
        self.write('demo/.codex-plugin/plugin.json', {'name': 'demo', 'version': '1.0.0', 'skills': './codex-skills/'})
        self.write('demo/codex-skills/greet/SKILL.md', '---\nname: greet\ndescription: New\n---\n')
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.commit()
        self.git('tag', '-f', 'baseline')
        self.write('.claude-plugin/marketplace.json', {'name': 'fixture', 'plugins': []})
        (self.root / 'demo/.claude-plugin/plugin.json').unlink()
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_package_source_move_preserves_version_history(self):
        self.git('mv', 'demo', 'relocated')
        registry = self.read_json('.claude-plugin/marketplace.json')
        registry['plugins'][0]['source'] = './relocated'
        self.write('.claude-plugin/marketplace.json', registry)
        self.assert_failure('version')
        data = self.read_json('relocated/.claude-plugin/plugin.json')
        data['version'] = '1.0.1'
        self.write('relocated/.claude-plugin/plugin.json', data)
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_old_ownership_still_applies_when_rules_change(self):
        self.add_codex()
        self.write('demo/shared.txt', 'Original.\n')
        self.commit()
        self.git('tag', '-f', 'baseline')
        self.write('demo/shared.txt', 'Changed.\n')
        rules = self.read_json('package-validation.json')
        rules['plugins']['demo'] = {'ownership': [{'path': 'shared.txt', 'hosts': ['codex']}]}
        self.write('package-validation.json', rules)
        self.bump('codex')
        self.assert_failure('demo [claude]')

    def test_ignored_file_cannot_satisfy_a_required_resource(self):
        self.write('.gitignore', 'demo/generated.txt\n')
        self.write('demo/generated.txt', 'Only exists locally.\n')
        rules = self.read_json('package-validation.json')
        rules['plugins']['demo'] = {'resources': [{'path': 'generated.txt', 'hosts': ['claude']}]}
        self.write('package-validation.json', rules)
        self.assert_failure('not included')

    def test_bad_host_rules_report_diagnostics_without_a_traceback(self):
        rules = self.read_json('package-validation.json')
        rules['plugins']['demo'] = {'ownership': [{'path': 'scripts/', 'hosts': [[]]}]}
        self.write('package-validation.json', rules)
        self.assert_failure('hosts')

    def test_declared_hook_configuration_must_be_valid_json(self):
        data = self.read_json('demo/.claude-plugin/plugin.json')
        data['hooks'] = './hooks/custom.json'
        self.write('demo/.claude-plugin/plugin.json', data)
        self.write('demo/hooks/custom.json', '{broken')
        self.assert_failure('custom.json')

    def test_invalid_text_and_symlink_loops_have_actionable_errors(self):
        path = self.root / 'demo/skills/greet/SKILL.md'
        path.write_bytes(b'\xff')
        self.assert_failure('SKILL.md')
        path.unlink()
        path.symlink_to('SKILL.md')
        self.assert_failure('SKILL.md')

    def test_declared_path_cannot_contain_a_null_byte(self):
        data = self.read_json('demo/.claude-plugin/plugin.json')
        data['skills'] = 'invalid\x00path'
        self.write('demo/.claude-plugin/plugin.json', data)
        self.assert_failure('path')

    def test_discovered_skill_symlink_cannot_use_an_ignored_target(self):
        self.write('.gitignore', 'demo/generated.md\n')
        self.write('demo/generated.md', '---\nname: greet\ndescription: Generated\n---\n')
        skill = self.root / 'demo/skills/greet/SKILL.md'
        skill.unlink()
        skill.symlink_to('../../generated.md')
        self.bump()
        self.assert_failure('not included')

    def test_skill_directory_symlink_does_not_skip_header_validation(self):
        self.git('mv', 'demo/skills', 'demo/actual-skills')
        (self.root / 'demo/skills').symlink_to('actual-skills', target_is_directory=True)
        self.write('demo/actual-skills/greet/SKILL.md', 'Missing header.\n')
        self.bump()
        self.assert_failure('header')
        self.write('demo/actual-skills/greet/SKILL.md', '---\nname: greet\ndescription: Valid\n---\n')
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_removing_final_registration_is_allowed(self):
        self.write('.claude-plugin/marketplace.json', {'name': 'fixture', 'plugins': []})
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('0 host registration', result.stdout)

    def test_nested_directory_aliases_require_each_link_to_be_included(self):
        self.git('mv', 'demo/skills', 'demo/shared')
        (self.root / 'demo/actual-skills').mkdir()
        (self.root / 'demo/actual-skills/greet').symlink_to('../shared/greet', target_is_directory=True)
        (self.root / 'demo/skills').symlink_to('actual-skills', target_is_directory=True)
        rules = self.read_json('package-validation.json')
        rules['plugins']['demo'] = {'resources': [{'path': 'skills/greet/SKILL.md', 'hosts': ['claude']}]}
        self.write('package-validation.json', rules)
        self.bump()
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.write('demo/actual-skills/keep.txt', 'Keep directory included.\n')
        self.write('.gitignore', 'demo/actual-skills/greet\n')
        self.assert_failure('not included')


if __name__ == '__main__':
    unittest.main()
