#!/usr/bin/env python3
"""Copy the sci-project-layout templates into a project, as the Set up mode does.

Usage: python3 set_up.py <package> [--root DIR]

The script does the copy step of the Set up mode in the project at DIR, by
default the current folder:

- Copies layout.md, layout-notes.md, and experiment-README.md to
  docs/agents/, paths.py to src/<package>/paths.py, and the gitignore
  template to .gitignore when the project has no .gitignore. In each file
  that it copies, it replaces myproj with the package name and MYPROJ with
  the package name in capitals.
- Adds to an existing .gitignore each template line that the file does not
  have, with the comment of its template group when the file lacks it.

It never overwrites a file, and it skips a .gitignore that is a symbolic
link, so it writes nothing outside DIR. It prints one line for each target
as it goes: `added <path>`, `skipped <path>: it exists`, `updated
.gitignore: added N lines`, `skipped .gitignore: it has every template
line`, `skipped .gitignore: it is a symbolic link`, or `error <path>:
<reason>`. After an error line it continues with the other targets and
exits 1. It exits 2, and writes nothing, when the package name is not a
Python package name, contains the template name myproj in any case, or DIR
is not a folder.
"""

from __future__ import annotations

import argparse
import functools
import keyword
import sys
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
INPUT_EXIT = 2


def template_targets(package: str) -> list[tuple[str, str]]:
    """Return each template file name with its path in the project."""
    return [
        ("layout.md", "docs/agents/layout.md"),
        ("layout-notes.md", "docs/agents/layout-notes.md"),
        ("experiment-README.md", "docs/agents/experiment-README.md"),
        ("paths.py", f"src/{package}/paths.py"),
    ]


def copy_new(template: str, target: Path, package: str) -> bool:
    """Write a template with the package name to a new file; return False when the file exists."""
    text = (TEMPLATES / template).read_text(encoding="utf-8")
    text = text.replace("myproj", package).replace("MYPROJ", package.upper())
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(target, "x", encoding="utf-8") as handle:  # "x" never replaces a file
            handle.write(text)
    except FileExistsError:
        return False
    return True


def missing_lines(template: str, existing: str) -> list[str]:
    """Return the template lines that existing lacks, each after its group comment when existing lacks that."""
    have = {line.strip() for line in existing.splitlines()}
    added: list[str] = []
    comment = ""
    for line in template.splitlines():
        if line.startswith("#"):
            comment = line
        elif line.strip() and line.strip() not in have:
            if comment and comment not in have and comment not in added:
                added.append(comment)
            added.append(line)
    return added


def update_gitignore(path: Path) -> int:
    """Add the template lines that an existing .gitignore lacks; return their number, comments included."""
    existing = path.read_text(encoding="utf-8")
    lines = missing_lines((TEMPLATES / "gitignore").read_text(encoding="utf-8"), existing)
    if lines:
        prefix = "" if not existing or existing.endswith("\n") else "\n"
        prefix += "\n" if existing.strip() else ""
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(prefix + "\n".join(lines) + "\n")
    return len(lines)


def copy_template(root: Path, template: str, name: str, package: str) -> str:
    """Copy one template to a new file; return its report line."""
    return f"added {name}" if copy_new(template, root / name, package) else f"skipped {name}: it exists"


def set_up_gitignore(root: Path, package: str) -> str:
    """Copy the gitignore template, or add its missing lines to .gitignore; return the report line."""
    gitignore = root / ".gitignore"
    if gitignore.is_symlink():  # its target can be outside the project
        return "skipped .gitignore: it is a symbolic link"
    if copy_new("gitignore", gitignore, package):
        return "added .gitignore"
    count = update_gitignore(gitignore)
    return f"updated .gitignore: added {count} lines" if count else "skipped .gitignore: it has every template line"


def set_up(root: Path, package: str) -> int:
    """Copy the templates into root, and print one line for each target as it goes; return the exit code."""
    targets = [(name, functools.partial(copy_template, root, template, name, package))
               for template, name in template_targets(package)]
    targets.append((".gitignore", functools.partial(set_up_gitignore, root, package)))
    code = 0
    for name, action in targets:
        try:
            line = action()
        except OSError as error:
            line, code = f"error {name}: {error.strerror or error}", 1
        print(line, flush=True)
    return code


def package_error(package: str) -> str:
    """Return why the name cannot be the package name, or ""."""
    if not (package.isascii() and package.isidentifier()) or keyword.iskeyword(package):
        return f"not a Python package name: {package!r}"
    if "myproj" in package.lower():  # the last Set up step looks for this template name
        return f"the package name contains the template name myproj: {package!r}"
    return ""


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("package", help="the Python package name, as in src/<package>/")
    parser.add_argument("--root", default=".", help="the project root (default: the current folder)")
    args = parser.parse_args(argv[1:])
    root = Path(args.root)
    error = package_error(args.package)
    if error:
        print(f"error: {error}", file=sys.stderr)
        return INPUT_EXIT
    if not root.is_dir():
        print(f"error: the project root is not a folder: {root}", file=sys.stderr)
        return INPUT_EXIT
    return set_up(root, args.package)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
