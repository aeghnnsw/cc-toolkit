#!/usr/bin/env python3
"""Check target docs for the mechanical doc-update rules.

Reads each Markdown doc given. Prints one finding per line on stdout as
``<doc>:<line>: <rule>: <detail>`` and a summary line on stderr. The rules:

  broken-link    a relative link or image whose target does not exist
  broken-anchor  a relative link whose #anchor matches no heading of its
                 Markdown target
  path           a relative path in inline code that does not exist
  history        a backward-narrative phrase, such as "previously"
  see-above      a vague reference, such as "see above"

A link is relative when it has no URL scheme. A link that starts with "/"
resolves from the repository root: the nearest folder above the doc that
holds ".git", or the doc's folder when none does. A path in inline code
resolves from the doc's folder or from the repository root. A path is
inline code that holds a "/" and ends with "/" or with a file extension.
The checks skip front matter and fenced code blocks; the link and phrase
checks also skip inline code.

Only broken-link and broken-anchor findings fail. The other findings are
for judgment: a phrase can be part of a forward-looking pointer or a false
match in current-state text, and a doc can name a path that the reader
creates. "used to" after a form of "be", as in "is used to check", is not a
history phrase.

Exit status: 0 with no broken link or anchor, 1 with one or more, 2 on an
error, such as a doc that is not a UTF-8 text file.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import unquote

HISTORY = (
    r"previously",
    r"formerly",
    r"originally",
    # After a form of "be", as in "is used to check", "used to" states a current purpose.
    r"".join(rf"(?<!\b{verb} )" for verb in ("is", "are", "was", "were", "be", "been", "being")) + r"used to",
    r"no longer",
    r"we (?:changed|switched|moved|replaced|removed|renamed|dropped)",
    r"(?:was|were|has been|have been) (?:changed|renamed|replaced|removed|moved|dropped)",
    r"as of v(?:ersion)? ?\d[\w.]*",
    r"in (?:earlier|older|previous|prior) versions?",
)
SEE_ABOVE = (
    r"see (?:above|below|earlier)",
    r"(?:mentioned|noted|described|discussed|explained|shown|stated) (?:above|earlier|previously|before)",
    r"(?:above|preceding) (?:section|example|table|list|paragraph|step)s?",
    r"(?:section|example|table|list|paragraph)s? above",
)
PHRASES = {
    rule: re.compile(r"\b(?:" + "|".join(patterns) + r")\b", re.IGNORECASE)
    for rule, patterns in (("history", HISTORY), ("see-above", SEE_ABOVE))
}
FAILING = ("broken-link", "broken-anchor")

FENCE = re.compile(r"^[ \t]*(`{3,}|~{3,})")
CODE_SPAN = re.compile(r"(`+)(.+?)\1")
INLINE_LINK = re.compile(r"\]\(\s*(?:<([^<>\n]+)>|([^\s)]+))")
REFERENCE = re.compile(r"^ {0,3}\[(?!\^)[^\]]+\]:[ \t]*(?:<([^<>\n]+)>|(\S+))")
HTML_LINK = re.compile(r"""<(?:a|img)\b[^>]*?\b(?:href|src)\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:")
CODE_PATH = re.compile(r"[\w.@+-]+(?:/[\w.@+-]+)*/?")
EXTENSION = re.compile(r"\.[A-Za-z]\w{0,9}$")
LOCATION = re.compile(r"(?::\d+(?::\d+)?|#L\d+(?:-L\d+)?)$")

ATX = re.compile(r"^ {0,3}#{1,6}(?:[ \t]+(.*?))?(?:[ \t]+#+)?[ \t]*$")
SETEXT = re.compile(r"^ {0,3}(?:=+|-+)[ \t]*$")
NOT_SETEXT_TEXT = re.compile(r"^ {0,3}(?:[-*+>|]|\d+[.)])")
CUSTOM_ID = re.compile(r"[ \t]*\{#([\w-]+)[^}]*\}$")
LINK_TEXT = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
HTML_TAG = re.compile(r"<[^>]+>")
HTML_ID = re.compile(r"""\b(?:id|name)\s*=\s*["']([^"']+)["']""")
MARKDOWN = {".md", ".markdown"}


class CheckError(Exception):
    """A doc cannot be read."""


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise CheckError(f"{path} is not UTF-8 text") from error
    except OSError as error:
        raise CheckError(f"cannot read {path}: {error.strerror}") from error


def content_lines(text: str) -> list[tuple[int, str]]:
    """Return the numbered lines outside front matter and fenced code blocks."""
    lines = text.splitlines()
    start = 0
    if lines and lines[0].strip() == "---":
        for index in range(1, len(lines)):
            if lines[index].strip() in ("---", "..."):
                start = index + 1
                break
    result = []
    fence = ""
    for number, line in enumerate(lines[start:], start=start + 1):
        match = FENCE.match(line)
        if fence:
            if match and match.group(1).startswith(fence) and not line[match.end():].strip():
                fence = ""
        elif match:
            fence = match.group(1)
        else:
            result.append((number, line))
    return result


def slug(heading: str) -> str:
    """Return the GitHub anchor of a heading's text."""
    text = HTML_TAG.sub("", LINK_TEXT.sub(r"\1", heading))
    return re.sub(r"[^\w\- ]", "", text.strip().lower()).replace(" ", "-")


def anchors(text: str) -> set[str]:
    """Return the anchors of a Markdown text; a repeated heading gets a numeric suffix."""
    counts: Counter[str] = Counter()
    result = set()
    previous = (0, "")
    for number, line in content_lines(text):
        heading = None
        atx = ATX.match(line)
        if atx:
            heading = atx.group(1) or ""
        elif (SETEXT.match(line) and previous[0] == number - 1 and previous[1].strip()
              and not NOT_SETEXT_TEXT.match(previous[1]) and not ATX.match(previous[1])):
            heading = previous[1].strip()
        if heading is not None:
            custom = CUSTOM_ID.search(heading)
            if custom:
                result.add(custom.group(1).lower())
                heading = heading[:custom.start()]
            name = slug(heading)
            result.add(f"{name}-{counts[name]}" if counts[name] else name)
            counts[name] += 1
        result.update(value.lower() for value in HTML_ID.findall(line))
        previous = (number, line)
    return result


class Checker:
    def __init__(self) -> None:
        self.anchor_cache: dict[Path, set[str] | None] = {}

    def target_anchors(self, path: Path) -> set[str] | None:
        if path not in self.anchor_cache:
            try:
                self.anchor_cache[path] = anchors(read_text(path))
            except CheckError:
                self.anchor_cache[path] = None
        return self.anchor_cache[path]

    def check_link(self, doc: Path, root: Path, target: str) -> tuple[str, str] | None:
        """Return a broken-link or broken-anchor finding for a relative link, or None."""
        target = target.strip()
        if not target or SCHEME.match(target) or target.startswith("//") or "{" in target:
            return None
        path, _, fragment = target.partition("#")
        path = unquote(path.split("?", 1)[0])
        if not path:
            file = doc
        elif path.startswith("/"):
            file = root / path.lstrip("/")
        else:
            file = doc.parent / path
        if not file.exists():
            return "broken-link", f"{target} does not exist"
        if fragment and file.is_file() and file.suffix.lower() in MARKDOWN:
            found = self.target_anchors(file)
            if found is not None and unquote(fragment).lower() not in found:
                return "broken-anchor", f"{target}: no heading has the anchor #{fragment}"
        return None

    def check(self, doc: Path, text: str) -> list[tuple[int, str, str]]:
        """Return the findings of one doc as (line, rule, detail)."""
        root = repository_root(doc)
        findings = []
        for number, line in content_lines(text):
            spans = [match.group(2).strip() for match in CODE_SPAN.finditer(line)]
            prose = CODE_SPAN.sub(" ", line)
            targets = [a or b for a, b in INLINE_LINK.findall(prose)]
            targets += [a or b for a, b in REFERENCE.findall(prose)]
            targets += HTML_LINK.findall(prose)
            for target in dict.fromkeys(targets):
                finding = self.check_link(doc, root, target)
                if finding:
                    findings.append((number, *finding))
            for span in dict.fromkeys(spans):
                path = LOCATION.sub("", span)
                if (CODE_PATH.fullmatch(path) and "/" in path and not path.startswith("/")
                        and (path.endswith("/") or EXTENSION.search(path))
                        and not (doc.parent / path).exists() and not (root / path).exists()):
                    findings.append((number, "path", f"{span} does not exist"))
            for rule, pattern in PHRASES.items():
                matches = dict.fromkeys(match.group(0).lower() for match in pattern.finditer(prose))
                if matches:
                    findings.append((number, rule, ", ".join(f'"{phrase}"' for phrase in matches)))
        return findings


def repository_root(doc: Path) -> Path:
    for folder in doc.parents:
        if (folder / ".git").exists():
            return folder
    return doc.parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="doc_check.py",
        description="Report broken relative links, anchors, and paths, and backward-narrative and "
        "vague-reference phrases, in Markdown docs.",
        epilog="Only broken-link and broken-anchor findings fail. history phrases: "
        + "; ".join(HISTORY) + ". see-above phrases: " + "; ".join(SEE_ABOVE) + ".",
    )
    parser.add_argument("docs", nargs="+", metavar="doc", help="a Markdown doc to check")
    options = parser.parse_args(argv)
    texts = {}
    for name in dict.fromkeys(options.docs):
        doc = Path(os.path.abspath(name))
        if not doc.is_file():
            print(f"{parser.prog}: error: {name} is not a file", file=sys.stderr)
            return 2
        try:
            texts[name] = (doc, read_text(doc))
        except CheckError as error:
            print(f"{parser.prog}: error: {error}", file=sys.stderr)
            return 2
    checker = Checker()
    counts: Counter[str] = Counter()
    for name, (doc, text) in texts.items():
        for number, rule, detail in checker.check(doc, text):
            print(f"{name}:{number}: {rule}: {detail}")
            counts[rule] += 1
    failing = sum(counts[rule] for rule in FAILING)
    print(
        f"docs: {len(texts)}; broken links or anchors: {failing}; unresolved paths: {counts['path']}; "
        f"history lines: {counts['history']}; see-above lines: {counts['see-above']}",
        file=sys.stderr,
    )
    return 1 if failing else 0


if __name__ == "__main__":
    sys.exit(main())
