"""The package validator module and the Git file list, shared by root tests that read registered plugins."""
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('validate_packages', ROOT / 'scripts' / 'validate_packages.py')
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


def git_files(root):
    """Return the files that Git tracks or can add: tracked files and untracked files that are not ignored."""
    return set(validator.git(root, 'ls-files', '--cached', '--others', '--exclude-standard', '-z')
               .decode().split('\0'))
