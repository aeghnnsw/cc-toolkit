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

It never overwrites a file. It prints one line for each target:
`added <path>`, `skipped <path>: the file exists`, `updated .gitignore:
added N lines`, or `skipped .gitignore: it has every template line`. It
exits 2, and writes nothing, when the package name is not a Python package
name or DIR is not a folder.
"""

from __future__ import annotations

import argparse
import keyword
import sys
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
INPUT_EXIT = 2


def copies(package: str) -> list[tuple[str, str]]:
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


def set_up(root: Path, package: str) -> list[str]:
    """Copy the templates into root; return one report line for each target."""
    report = []
    for template, name in copies(package):
        added = copy_new(template, root / name, package)
        report.append(f"added {name}" if added else f"skipped {name}: the file exists")
    gitignore = root / ".gitignore"
    if copy_new("gitignore", gitignore, package):
        report.append("added .gitignore")
    else:
        count = update_gitignore(gitignore)
        report.append(f"updated .gitignore: added {count} lines" if count
                      else "skipped .gitignore: it has every template line")
    return report


def bad_package(package: str) -> bool:
    """Return True when the name cannot be a Python package name."""
    return not (package.isascii() and package.isidentifier()) or keyword.iskeyword(package)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("package", help="the Python package name, as in src/<package>/")
    parser.add_argument("--root", default=".", help="the project root (default: the current folder)")
    args = parser.parse_args(argv[1:])
    root = Path(args.root)
    if bad_package(args.package):
        print(f"error: not a Python package name: {args.package!r}", file=sys.stderr)
        return INPUT_EXIT
    if not root.is_dir():
        print(f"error: the project root is not a folder: {root}", file=sys.stderr)
        return INPUT_EXIT
    for line in set_up(root, args.package):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
