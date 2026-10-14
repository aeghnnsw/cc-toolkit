"""The package validator module, the Git file list, and the Markdown fence pattern, shared by root tests."""
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
