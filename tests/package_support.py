"""The package validator module, the Git file list, plugin agents, and the Markdown fence pattern, shared by root tests."""
import importlib.util
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
# A fenced code block opened by ``` or ~~~; group 2 holds the block content.
FENCE = re.compile(r'^[ \t]*(```|~~~)[^\n]*\n(.*?)^[ \t]*\1', re.MULTILINE | re.DOTALL)
SPEC = importlib.util.spec_from_file_location('validate_packages', ROOT / 'scripts' / 'validate_packages.py')
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


def git_files(root):
    """Return the files that Git tracks or can add: tracked files and untracked files that are not ignored."""
    return set(validator.git(root, 'ls-files', '--cached', '--others', '--exclude-standard', '-z')
               .decode().split('\0'))


def agent_files(root):
    """Return the Markdown agents that Git includes, from the agents paths the validator finds for each plugin."""
    files = git_files(root)
    found = {}
    for package in validator.load_packages(root).values():
        for field, path in validator.discovery_paths(root, package):
            if field == 'agents':
                target = root / package.source / path
                candidates = [target] if target.is_file() else sorted(target.rglob('*.md'))
                found.update(dict.fromkeys(agent for agent in candidates
                                           if validator.included_location(root, agent, files)))
    return list(found)


def frontmatter(text):
    lines = text.splitlines()
    if not lines or lines[0].strip() != '---':
        return ''
    end = next((index for index, line in enumerate(lines[1:], 1) if line.strip() == '---'), 0)
    return '\n'.join(lines[1:end])
