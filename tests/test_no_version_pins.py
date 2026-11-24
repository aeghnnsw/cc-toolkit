"""Fail on a test that pins a release version of a plugin or a skill.

A test that compares a manifest or SKILL.md version with a literal fails at the next release (#397). A test
reads such a version from its file instead. Fixture repositories also use version strings, and a release can
reach one of them, so every version string in a test must be listed below for its file.
"""
import ast
import json
import re
import unittest

from package_support import ROOT, frontmatter, git_files


TEST_FILE = re.compile(r'(?:[^/]+/)?tests/[^/]+\.py')
SELF = 'tests/test_no_version_pins.py'  # its version strings are the list below
MANIFEST = re.compile(r'[^/]+/\.[a-z]+-plugin/plugin\.json')
VERSION = re.compile(r'(?<![\d.])\d+\.\d+\.\d+(?!\.?\d)')
SKILL_VERSION = re.compile(r'^version:\s*["\']?([^"\'\s]+)', re.MULTILINE)

# The version strings that each test writes to a fixture or quotes from another tool. They are not releases of
# this repository. A test that pins a release at one of these versions in the same file is not found.
FIXTURE_VERSIONS = {
    'core-hooks/tests/test_antigravity_host_adapter.py': {'1.5.13'},  # the agy version that sent the payloads
    'core-hooks/tests/test_pre_git_hook.py': {'1.2.0'},  # the tag v1.2.0 in a git worktree command
    'core-hooks/tests/test_stale_install_check.py': {  # fixture repository, install, and cache versions
        '1.0.1', '1.0.2', '1.0.3', '1.0.9', '1.0.10', '1.0.11', '1.0.12', '1.0.26', '1.0.27', '1.9.0', '1.10.0',
        '1.55.0', '1.59.0', '3.9.0', '3.52.0', '3.68.0', '3.72.0'},
    'dev-skills/tests/test_resolve_skill.py': {'1.0.0', '1.9.0', '1.10.0'},  # installed fixture plugin versions
    'dev-skills/tests/test_t3_project_lead.py': {'0.0.1', '0.1.1', '0.2.1', '0.9.1'},  # fixture manifest versions
    'dev-skills/tests/test_sci_project_layout.py': {'1.2.5'},  # a fixture tool version in a run record
    'tests/test_agent_fields.py': {'1.0.0'},
    'tests/test_host_copies.py': {'4.17.15', '8.5.1', '9.0.0'},  # quoted skill text
    'tests/test_model_pins.py': {'1.0.0'},
    'tests/test_release_scripts.py': {'1.0.0', '1.0.1', '1.0.2', '1.1.0', '1.2.0', '1.3.0'},  # fixture manifest and skill versions
    'tests/test_skill_placeholders.py': {'1.0.0'},
    'tests/test_validate_packages.py': {'0.9.9', '1.0.0', '1.0.01', '1.0.1', '1.0.2', '1.1.0'},
}


def release_versions(files):
    """Map each manifest and SKILL.md version to the files that hold it."""
    sources = {}
    for path in sorted(files):
        if MANIFEST.fullmatch(path):
            value = json.loads((ROOT / path).read_text(encoding='utf-8')).get('version')
        elif path.endswith('/SKILL.md'):
            match = SKILL_VERSION.search(frontmatter((ROOT / path).read_text(encoding='utf-8')))
            value = match and match[1]
        else:
            continue
        if isinstance(value, str):
            sources.setdefault(value, []).append(path)
    return sources


def version_strings(path):
    """Yield (line, version) for each version in a string literal of a Python file."""
    tree = ast.parse((ROOT / path).read_text(encoding='utf-8'), path)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for value in VERSION.findall(node.value):
                yield node.lineno, value


class VersionPinTests(unittest.TestCase):
    def test_tests_hold_no_release_version(self):
        files = {path for path in git_files(ROOT) if path and (ROOT / path).is_file()}
        sources = release_versions(files)
        problems, used = [], set()
        for path in sorted(path for path in files if TEST_FILE.fullmatch(path) and path != SELF):
            for line, value in version_strings(path):
                if value in FIXTURE_VERSIONS.get(path, ()):
                    used.add((path, value))
                elif value in sources:
                    problems.append(f'{path}:{line}: "{value}" pins the release version in {", ".join(sources[value])}; '
                                    'read the version from that file')
                else:
                    problems.append(f'{path}:{line}: "{value}" is not a listed fixture version; when the test writes '
                                    'it to a fixture, add it to FIXTURE_VERSIONS for this file')
        problems += [f'FIXTURE_VERSIONS: {path} no longer holds "{value}"; delete the entry'
                     for path, values in FIXTURE_VERSIONS.items() for value in sorted(values)
                     if (path, value) not in used]
        self.assertEqual(problems, [], '\n' + '\n'.join(problems))


if __name__ == '__main__':
    unittest.main()
