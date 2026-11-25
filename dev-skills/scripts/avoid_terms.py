#!/usr/bin/env python3
"""Print the glossary _Avoid_ terms in the added Markdown lines or named files.

Usage:

    python3 dev-skills/scripts/avoid_terms.py --base <ref>
    python3 dev-skills/scripts/avoid_terms.py <file>...
    python3 dev-skills/scripts/avoid_terms.py --base <ref> <file>...

The glossary is every tracked file named GLOSSARY.md in the repository. A
glossary term is a line that starts with a bold name, such as "**Worker**:".
The "_Avoid_: term one, term two" line under it gives the comma-separated
terms that the glossary term replaces.

With --base, the added lines are the lines of the Markdown files (*.md) that
the diff adds from the merge base of <ref> and HEAD to the working tree, so
committed and uncommitted changes both count. Every line of an untracked
Markdown file that Git does not ignore also counts.

Each named file counts with every line, whatever its extension, for example
a draft of an issue under .scratch/ that no diff holds. A file path is
relative to the current folder. With --base and files, both count, and a
changed file that is also named counts with every line. A named path that
leads to a changed file or a glossary file, such as a symbolic link, counts
as that file. The glossary files are not checked.

A term matches without regard to case, as a whole word or phrase. Inline code
spans in backticks and the lines of fenced code blocks are code or quotations,
not prose, so the script does not check them. It prints one line for each hit,
sorted by path and line, for example:

    docs/setup.md:12: "Subagent" (glossary term: Worker)

Run it from any folder of the checkout. A path in the output is relative to
the repository root, or absolute for a named file outside the checkout.

Exit status: 0 when no checked line has an _Avoid_ term, or when the
repository has no tracked glossary; 1 when a hit exists; 2 for a usage error,
a named file that cannot be read, or a git failure, such as an unknown ref.
The message goes to stderr.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

GLOSSARY = "GLOSSARY.md"
TERM = re.compile(r"\*\*([^*]+)\*\*")
AVOID = re.compile(r"_Avoid_:(.*)")
HUNK = re.compile(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
CODE_SPAN = re.compile(r"(`+).*?\1")
FENCE = re.compile(r"\s*(`{3,}|~{3,})")


def git(root: Path | None, *args: str) -> str:
    """Return the output of a git command, or exit 2 with its error."""
    command = ["git", "-c", "core.quotepath=off"]
    if root:
        command += ["-C", str(root)]
    try:
        result = subprocess.run(command + list(args), capture_output=True,
                                encoding="utf-8", errors="replace")
    except FileNotFoundError:
        fail("git is not installed")
    if result.returncode:
        fail(f"git {' '.join(args)} failed:\n{result.stderr.strip()}")
    return result.stdout


def fail(message: str) -> None:
    """Print the message on stderr and exit 2."""
    print(f"FAIL: {message}", file=sys.stderr)
    sys.exit(2)


def read_terms(text: str, terms: dict[str, tuple[str, list[str]]]) -> None:
    """Map each lowercase _Avoid_ term in text to its spelling and its glossary terms."""
    current = ""
    for line in text.splitlines():
        heading, avoid = TERM.match(line), AVOID.match(line)
        if heading:
            current = heading.group(1).strip()
        elif avoid and current:
            for avoided in avoid.group(1).split(","):
                avoided = " ".join(avoided.split()).rstrip(".")
                if avoided:
                    entry = terms.setdefault(avoided.lower(), (avoided, []))
                    if current not in entry[1]:
                        entry[1].append(current)


def term_pattern(terms: dict[str, tuple[str, list[str]]]) -> re.Pattern:
    """Return one pattern that matches every term as a whole word or phrase."""
    # The longest term goes first, so a phrase wins over a word inside it.
    phrases = [r"\s+".join(map(re.escape, key.split()))
               for key in sorted(terms, key=len, reverse=True)]
    return re.compile(r"(?<!\w)(?:" + "|".join(phrases) + r")(?!\w)", re.IGNORECASE)


def find_hits(text: str, lines: set[int] | None, pattern: re.Pattern,
              terms: dict[str, tuple[str, list[str]]]) -> list[tuple[int, str, str]]:
    """Return (line, avoided term, glossary terms) for each hit in the given lines.

    With lines None, every line counts. The whole text is read so that the
    lines of a fenced code block are known.
    """
    hits, fence = [], ""
    # Git counts lines by newline only, so the text is not split at other line breaks.
    for number, line in enumerate(text.split("\n"), 1):
        mark = FENCE.match(line)
        # A backtick fence has no backtick after it; such a line is an inline span.
        if mark and mark.group(1)[0] == "`" and "`" in line[mark.end():]:
            mark = None
        if fence:
            if mark and mark.group(1)[0] == fence[0] and len(mark.group(1)) >= len(fence) \
                    and not line[mark.end():].strip():
                fence = ""
            continue
        if mark:
            fence = mark.group(1)
            continue
        if lines is not None and number not in lines:
            continue
        seen = set()
        for match in pattern.finditer(CODE_SPAN.sub(" ", line)):
            spelling, glossary = terms[" ".join(match.group(0).lower().split())]
            if spelling not in seen:
                seen.add(spelling)
                hits.append((number, spelling, ", ".join(glossary)))
    return hits


def added_lines(root: Path, base: str, skip: set[str]) -> dict[str, set[int] | None]:
    """Map each changed Markdown path to its added line numbers, or None for all."""
    added: dict[str, set[int] | None] = {}
    path, number, header = "", 0, False
    diff = git(root, "diff", "--no-color", "--no-ext-diff", "--no-textconv", "-M", "-U0",
               "--src-prefix=a/", "--dst-prefix=b/", base, "--", "*.md")
    for line in diff.split("\n"):
        if line.startswith("diff --git "):
            path, header = "", True
        elif header and line.startswith("+++ "):
            # Git ends the name with a tab when it has a space.
            name = line[4:].rstrip("\t")
            path = name[2:] if name.startswith("b/") else ""
        elif line.startswith("@@"):
            hunk = HUNK.match(line)
            number, header = (int(hunk.group(1)) if hunk else 0), False
        elif not header and line.startswith("+") and path and path not in skip:
            added.setdefault(path, set()).add(number)
            number += 1
    for name in git(root, "ls-files", "-z", "--others", "--exclude-standard",
                    "--", "*.md").split("\0"):
        if name and name not in skip:
            added[name] = None
    return added


def file_id(path: Path) -> tuple[int, int] | None:
    """Return the device and inode of a file, or None when it cannot be read."""
    try:
        status = path.stat()
    except OSError:
        return None
    return status.st_dev, status.st_ino


def read_named(files: list[str], root: Path) -> dict[tuple[int, int] | None, tuple[str, str]]:
    """Map the file_id of each named file to its output path and its text.

    Exit 2 when a file cannot be read. The output path is relative to the
    repository root, or absolute for a file outside the checkout. Only the
    folder of a path is resolved, so a symbolic link keeps its own name.
    """
    named, real_root = {}, root.resolve()
    for name in files:
        absolute = Path(os.path.abspath(name))
        path = absolute.parent.resolve() / absolute.name
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as error:
            fail(f"cannot read {name}: {error.strerror or error}")
        try:
            shown = path.relative_to(real_root).as_posix()
        except ValueError:
            shown = str(path)
        named[file_id(path)] = (shown, text)
    return named


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", help="ref whose merge base with HEAD starts the diff")
    parser.add_argument("files", nargs="*", metavar="FILE",
                        help="file whose every line is checked")
    args = parser.parse_args()
    if args.base is None and not args.files:
        parser.error("give --base <ref>, a file, or both")
    if args.base is not None and args.base.startswith("-"):
        parser.error(f"--base must name a ref, not an option: {args.base}")
    root = Path(git(None, "rev-parse", "--show-toplevel").strip())
    named = read_named(args.files, root)
    glossaries = [name for name in git(root, "ls-files", "-z", "--", "*" + GLOSSARY).split("\0")
                  if name.rsplit("/", 1)[-1] == GLOSSARY]
    skip = set(glossaries)
    terms: dict[str, tuple[str, list[str]]] = {}
    for name in glossaries:
        try:
            read_terms((root / name).read_text(encoding="utf-8", errors="replace"), terms)
        except FileNotFoundError:
            continue
    if not terms:
        print(f"No tracked {GLOSSARY} with _Avoid_ terms; nothing was checked.")
        return
    checked: dict[str, set[int] | None] = {}
    if args.base is not None:
        base = git(root, "merge-base", args.base, "HEAD").strip()
        checked = added_lines(root, base, skip)
    # File identity, not path text, finds a named file among the changed and
    # glossary files, also through a link or a letter case that differs.
    known = {file_id(root / name): name for name in [*skip, *checked]}
    known.pop(None, None)
    texts = {}
    for identity, (shown, text) in named.items():
        name = known.get(identity, shown)
        if name not in skip:
            checked[name], texts[name] = None, text
    pattern = term_pattern(terms)
    hits = []
    for name, lines in checked.items():
        text = texts.get(name)
        if text is None:
            try:
                text = (root / name).read_text(encoding="utf-8", errors="replace")
            except (FileNotFoundError, IsADirectoryError):
                continue
        hits += [(name, *hit) for hit in find_hits(text, lines, pattern, terms)]
    for name, number, avoided, glossary in sorted(hits):
        print(f'{name}:{number}: "{avoided}" (glossary term: {glossary})')
    if hits:
        sys.exit(1)
    print("No checked line has a glossary _Avoid_ term." if args.files
          else "No added Markdown line has a glossary _Avoid_ term.")


if __name__ == "__main__":
    main()
