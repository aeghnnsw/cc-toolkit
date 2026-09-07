"""Package validation behavior at the command interface."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


COMMAND = Path(__file__).resolve().parents[1] / 'scripts' / 'validate_packages.py'


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

    def run_check(self, base='baseline'):
        result = subprocess.run([sys.executable, str(COMMAND), '--base', base], cwd=self.root,
                                text=True, capture_output=True)
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
        for header in [
            'name: greet',
            'name: greet\ndescription: ',
            'name: INVALID\ndescription: Hello',
            'name: greet\nname: greet\ndescription: Hello',
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

    def test_version_only_increases_pass_and_regressions_fail(self):
        self.bump(value='1.0.1')
        self.assertEqual(self.run_check().returncode, 0)
        self.bump(value='0.9.9')
        self.assert_failure('version must increase')
        self.bump(value='1.0.01')
        self.assert_failure('invalid plugin version')

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
