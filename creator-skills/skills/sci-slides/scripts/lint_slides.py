#!/usr/bin/env python3
"""Lint a slide deck for the mechanical sci-slides rules.

Reads one deck: reveal.js HTML, Markdown (Marp, Slidev, reveal.js, Quarto),
LaTeX Beamer, or PPTX. Prints one finding per line as
``<file>:<slide>: <rule>: <detail>``, then a summary line.

Exit status: 0 with no findings, 1 with findings, 2 on an error.

Slide 1 is the title slide: the title and figure-source rules skip it.
Findings are advisory. The skill's slide-text and design references hold
the rules; this script finds the mechanical cases.
"""

from __future__ import annotations

import argparse
import posixpath
import re
import sys
import zipfile
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree

RULES = {
    "title-missing": "a content slide has no title",
    "title-length": "the title is longer than --max-title-chars",
    "title-question": "the title is a question",
    "contrast-form": 'the title or a text line uses the "X, not Y" form',
    "title-precision": "a number in the title has more than three significant figures",
    "bullet-count": "the slide has more than --max-bullets bullets",
    "bullet-words": "a bullet has more than --max-bullet-words words",
    "text-lines": "the slide has more than --max-lines text lines",
    "image-alt": "an image has no alt text (not checked for Beamer)",
    "figure-source": "the slide shows a figure and no source line",
    "notes-words": "the notes have more than --max-note-words words",
}
FORMATS = {
    ".html": "html",
    ".htm": "html",
    ".md": "markdown",
    ".markdown": "markdown",
    ".qmd": "markdown",
    ".rmd": "markdown",
    ".tex": "beamer",
    ".pptx": "pptx",
}

QUESTION = re.compile(r"\?\s*$")
CONTRAST = re.compile(r"(?:[,;—–]|\s-)\s*not\s+\w", re.IGNORECASE)
DECIMAL = re.compile(r"(?<![\w.])(\d+)\.(\d+)(?![\w.])")
SOURCE = re.compile(
    r"\b(?:sources?|credits?|courtesy)\s*:"
    r"|\b(?:adapted|reproduced|reprinted|modified)\s+from\b"
    r"|\bet al\b|\bdoi\b|©|\bthis work\b"
    r"|\\(?:foot)?(?:full)?cite"
    r"|\([^()]*\b(?:19|20)\d{2}[a-z]?\s*\)",
    re.IGNORECASE,
)


class LintError(Exception):
    """The deck cannot be read."""


@dataclass
class Slide:
    title: str | None = None
    bullets: list[str] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)  # every text line except the title
    images: list[str | None] = field(default_factory=list)  # alt text; None when absent
    notes: str = ""
    source_text: str = ""  # extra text that may hold a source, such as a citation command


def clean(text: str) -> str:
    return " ".join(text.split())


# --- HTML (reveal.js) ---------------------------------------------------------

HEADINGS = {"h1", "h2", "h3"}
BLOCKS = {
    "p", "h4", "h5", "h6", "figcaption", "blockquote", "td", "th", "dt", "dd",
    "pre", "caption", "small", "footer", "cite",
}


class _RevealParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.slides: list[Slide] = []
        self._sections: list[list] = []  # [slide, has_child_section]
        self._buffers: list[list] = []  # [tag, kind, text parts]
        self._notes_depth = 0
        self._skip_depth = 0

    @property
    def _slide(self) -> Slide | None:
        return self._sections[-1][0] if self._sections else None

    def handle_starttag(self, tag: str, attrs: list) -> None:
        attributes = dict(attrs)
        if tag == "section":
            if self._sections:
                self._sections[-1][1] = True
            self._sections.append([Slide(), False])
            return
        if self._slide is None:
            return
        if tag in ("script", "style"):
            self._skip_depth += 1
        elif tag == "aside" and "notes" in (attributes.get("class") or "").split():
            self._notes_depth += 1
        elif self._notes_depth:
            return
        elif tag == "img":
            self._slide.images.append(attributes.get("alt"))
        elif tag in HEADINGS or tag in BLOCKS or tag == "li":
            if tag in ("li", "p") and self._buffers and self._buffers[-1][0] == tag:
                self._close_buffer()
            kind = "heading" if tag in HEADINGS else "bullet" if tag == "li" else "block"
            self._buffers.append([tag, kind, []])

    def handle_endtag(self, tag: str) -> None:
        if tag == "section":
            while self._buffers:
                self._close_buffer()
            if self._sections:
                slide, has_child = self._sections.pop()
                if not has_child:
                    self.slides.append(slide)
        elif tag in ("script", "style") and self._skip_depth:
            self._skip_depth -= 1
        elif tag == "aside" and self._notes_depth:
            self._notes_depth -= 1
        elif tag in ("ul", "ol"):
            while self._buffers and self._buffers[-1][1] in ("bullet", "block"):
                closed = self._buffers[-1][1]
                self._close_buffer()
                if closed == "bullet":
                    break
        elif any(buffer[0] == tag for buffer in self._buffers):
            while self._buffers:
                closing = self._buffers[-1][0]
                self._close_buffer()
                if closing == tag:
                    break

    def handle_data(self, data: str) -> None:
        slide = self._slide
        if slide is None or self._skip_depth or not data.strip():
            return
        if self._notes_depth:
            slide.notes += " " + data
        elif self._buffers:
            self._buffers[-1][2].append(data)
        else:
            slide.lines.append(clean(data))

    def _close_buffer(self) -> None:
        tag, kind, parts = self._buffers.pop()
        text = clean(" ".join(parts))
        slide = self._slide
        if not text or slide is None:
            return
        parent = self._buffers[-1] if self._buffers else None
        if kind == "heading" and slide.title is None:
            slide.title = text
        elif kind == "block" and parent is not None and parent[1] != "heading":
            parent[2].append(text)
        else:
            if kind == "bullet":
                slide.bullets.append(text)
            slide.lines.append(text)


def parse_html(text: str) -> list[Slide]:
    parser = _RevealParser()
    parser.feed(text)
    parser.close()
    while parser._sections:
        parser.handle_endtag("section")
    return parser.slides


# --- Markdown (Marp, Slidev, reveal.js, Quarto) --------------------------------

FENCE = re.compile(r"^\s*(```|~~~)")
SEPARATOR = re.compile(r"^(?:---|\*\*\*)\s*$")
MD_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
MD_BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.*)$")
MD_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
HTML_IMAGE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
ALT = re.compile(r"\balt\s*=\s*([\"'])(.*?)\1", re.IGNORECASE | re.DOTALL)
COMMENT = re.compile(r"<!--(.*?)-->", re.DOTALL)
DIRECTIVE = re.compile(r"^\s*_?[A-Za-z][\w-]*\s*:\s*(?:\S+|\"[^\"]*\"|'[^']*')\s*$")
YAML_LINE = re.compile(r"^[A-Za-z_][\w-]*:(?:\s.*)?$")
NOTES_DIV = re.compile(r"^\s*:::+\s*(?:\{[^}]*\.notes[^}]*\}|notes)\s*$")
DIV_FENCE = re.compile(r"^\s*:::+")
NOTE_LINE = re.compile(r"^\s*Notes?:\s*(.*)$")
TAG = re.compile(r"<[^>]+>")


def md_inline(text: str) -> str:
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = TAG.sub(" ", text)
    return clean(text.replace("**", "").replace("__", "").replace("`", "").replace("*", ""))


def split_markdown(lines: list[str]) -> list[list[str]]:
    chunks: list[list[str]] = [[]]
    in_fence = False
    for line in lines:
        if FENCE.match(line):
            in_fence = not in_fence
        if not in_fence and SEPARATOR.match(line):
            chunks.append([])
            continue
        chunks[-1].append(line)
    slides: list[list[str]] = []
    for chunk in chunks:
        current: list[str] = []
        has_heading = False
        in_fence = False
        for line in chunk:
            if FENCE.match(line):
                in_fence = not in_fence
            heading = None if in_fence else MD_HEADING.match(line)
            if heading and len(heading.group(1)) <= 2 and has_heading:
                slides.append(current)
                current, has_heading = [], False
            if heading:
                has_heading = True
            current.append(line)
        slides.append(current)
    return [s for s in slides if any(l.strip() for l in s) and not is_yaml_chunk(s)]


def is_yaml_chunk(lines: list[str]) -> bool:
    content = [l for l in lines if l.strip()]
    return all(YAML_LINE.match(l) for l in content)


def parse_markdown_slide(lines: list[str]) -> Slide:
    slide = Slide()
    text = "\n".join(lines)
    for body in COMMENT.findall(text):
        body_lines = [l for l in body.splitlines() if l.strip()]
        if body_lines and not all(DIRECTIVE.match(l) for l in body_lines):
            slide.notes += " " + body
    text = COMMENT.sub("", text)
    in_fence = in_notes_div = in_note_tail = False
    for line in text.splitlines():
        if in_note_tail:
            slide.notes += " " + line
            continue
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if in_notes_div:
            if DIV_FENCE.match(line) and not line.strip(": \t"):
                in_notes_div = False
            else:
                slide.notes += " " + line
            continue
        if NOTES_DIV.match(line):
            in_notes_div = True
            continue
        if DIV_FENCE.match(line):
            continue
        note = NOTE_LINE.match(line)
        if note:
            in_note_tail = True
            slide.notes += " " + note.group(1)
            continue
        for alt in MD_IMAGE.findall(line):
            slide.images.append(alt)
        for tag in HTML_IMAGE.findall(line):
            alt = ALT.search(tag)
            slide.images.append(alt.group(2) if alt else None)
        line = HTML_IMAGE.sub(" ", MD_IMAGE.sub(" ", line))
        heading = MD_HEADING.match(line)
        bullet = MD_BULLET.match(line)
        if heading:
            content = md_inline(heading.group(2))
            if slide.title is None:
                slide.title = content
            elif content:
                slide.lines.append(content)
        elif bullet:
            content = md_inline(bullet.group(1))
            if content:
                slide.bullets.append(content)
                slide.lines.append(content)
        else:
            content = md_inline(line)
            if re.search(r"\w", content):
                slide.lines.append(content)
    return slide


def parse_markdown(text: str, suffix: str) -> list[Slide]:
    lines = text.splitlines()
    front_keys: set[str] = set()
    if lines and lines[0].strip() == "---":
        for end in range(1, len(lines)):
            if lines[end].strip() in ("---", "..."):
                front_keys = {l.split(":", 1)[0].strip() for l in lines[1:end] if YAML_LINE.match(l)}
                lines = lines[end + 1:]
                break
    slides = [parse_markdown_slide(chunk) for chunk in split_markdown(lines)]
    # Quarto and Pandoc build a title slide from the front matter title.
    if "title" in front_keys and ("format" in front_keys or suffix in (".qmd", ".rmd")):
        slides.insert(0, Slide())
    return slides


# --- LaTeX Beamer --------------------------------------------------------------

DROPPED_COMMANDS = (
    "includegraphics", "vspace", "hspace", "label", "ref", "eqref", "cite", "citep",
    "citet", "footcite", "footfullcite", "input", "url", "pause",
)


def read_group(text: str, start: int, opening: str = "{", closing: str = "}") -> tuple[str, int] | None:
    """Return the balanced group at ``start`` (after whitespace) and the index after it."""
    index = start
    while index < len(text) and text[index] in " \t\r\n":
        index += 1
    if index >= len(text) or text[index] != opening:
        return None
    depth = 0
    for position in range(index, len(text)):
        char = text[position]
        if char == "\\":
            continue
        if position > 0 and text[position - 1] == "\\":
            continue
        if char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return text[index + 1:position], position + 1
    return None


def skip_options(text: str, index: int) -> int:
    for opening, closing in (("<", ">"), ("[", "]")):
        group = read_group(text, index, opening, closing)
        if group:
            index = group[1]
    return index


def take_command(body: str, name: str) -> tuple[list[str], str]:
    """Remove every ``\\name[opts]{arg}`` from ``body``; return the arguments and the rest."""
    found: list[str] = []
    pattern = re.compile(r"\\" + name + r"\*?(?![A-Za-z])")
    while True:
        match = pattern.search(body)
        if not match:
            return found, body
        group = read_group(body, skip_options(body, match.end()))
        end = group[1] if group else match.end()
        if group:
            found.append(group[0])
        body = body[:match.start()] + " " + body[end:]


def latex_text(text: str) -> str:
    text = re.sub(r"\\([%&_#$])", r"\1", text)
    text = re.sub(r"\\(?:begin|end)\{[^}]*\}(?:\[[^\]]*\])?", " ", text)
    commands = "|".join(DROPPED_COMMANDS)
    text = re.sub(r"\\(?:" + commands + r")\*?(?:\[[^\]]*\])?(?:\{[^}]*\})?", " ", text)
    text = re.sub(r"\\[A-Za-z]+\*?", " ", text)
    return clean(text.replace("{", "").replace("}", "").replace("~", " "))


def parse_beamer(text: str) -> list[Slide]:
    text = re.sub(r"(?<!\\)%.*", "", text)
    slides: list[Slide] = []
    for match in re.finditer(r"\\begin\{frame\}", text):
        end = text.find(r"\end{frame}", match.end())
        if end == -1:
            end = len(text)
        index = skip_options(text, match.end())
        slide = Slide()
        group = read_group(text, index)
        if group and text[index:group[1]].lstrip().startswith("{"):
            slide.title = latex_text(group[0]) or None
            index = group[1]
        body = text[index:end]
        titles, body = take_command(body, "frametitle")
        if slide.title is None and titles:
            slide.title = latex_text(titles[0]) or None
        _, body = take_command(body, "framesubtitle")
        notes, body = take_command(body, "note")
        slide.notes = " ".join(latex_text(n) for n in notes)
        slide.source_text = body
        slide.images = [None] * len(re.findall(r"\\includegraphics", body))
        item = re.compile(
            r"\\item(?:\s*<[^>]*>)?(?:\s*\[[^\]]*\])?(.*?)"
            r"(?=\\item|\\end\{(?:itemize|enumerate|description)\}|\\begin\{|\Z)",
            re.DOTALL,
        )
        for content in item.findall(body):
            bullet = latex_text(content)
            if bullet:
                slide.bullets.append(bullet)
                slide.lines.append(bullet)
        for line in item.sub(" ", body).splitlines():
            content = latex_text(line)
            if re.search(r"[A-Za-z]", content):
                slide.lines.append(content)
        slides.append(slide)
    return slides


# --- PPTX ---------------------------------------------------------------------

P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PKG = "{http://schemas.openxmlformats.org/package/2006/relationships}"
BULLET_PLACEHOLDERS = {"obj", "body"}
FURNITURE = {"dt", "ftr", "sldNum", "hdr"}


def read_xml(package: zipfile.ZipFile, name: str) -> ElementTree.Element:
    try:
        return ElementTree.fromstring(package.read(name))
    except KeyError:
        raise LintError(f"PPTX part {name} is missing") from None
    except ElementTree.ParseError as error:
        raise LintError(f"PPTX part {name} is not valid XML: {error}") from None


def relationships(package: zipfile.ZipFile, part: str) -> dict[str, tuple[str, str]]:
    """Map relationship ids of ``part`` to (type, resolved target)."""
    folder, name = posixpath.split(part)
    rels_name = posixpath.join(folder, "_rels", name + ".rels")
    if rels_name not in package.namelist():
        return {}
    result = {}
    for rel in read_xml(package, rels_name).iter(PKG + "Relationship"):
        target = rel.get("Target", "")
        resolved = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join(folder, target))
        result[rel.get("Id", "")] = (rel.get("Type", ""), resolved)
    return result


def paragraph_text(paragraph: ElementTree.Element) -> str:
    return clean("".join(t.text or "" for t in paragraph.iter(A + "t")))


def placeholder_type(shape: ElementTree.Element, holder: str) -> str | None:
    placeholder = shape.find(f"{P}{holder}/{P}nvPr/{P}ph")
    return None if placeholder is None else placeholder.get("type", "obj")


def parse_pptx_slide(package: zipfile.ZipFile, part: str) -> Slide:
    root = read_xml(package, part)
    slide = Slide()
    footer_text = []
    for shape in root.iter(P + "sp"):
        kind = placeholder_type(shape, "nvSpPr")
        paragraphs = [p for p in shape.iter(A + "p") if paragraph_text(p)]
        texts = [paragraph_text(p) for p in paragraphs]
        if kind in ("title", "ctrTitle"):
            if slide.title is None and texts:
                slide.title = " ".join(texts)
            continue
        if kind in FURNITURE:
            footer_text.extend(texts)
            continue
        for paragraph, text in zip(paragraphs, texts):
            properties = paragraph.find(A + "pPr")
            marked = properties is not None and (
                properties.find(A + "buChar") is not None or properties.find(A + "buAutoNum") is not None
            )
            unmarked = properties is not None and properties.find(A + "buNone") is not None
            if marked or (kind in BULLET_PLACEHOLDERS and not unmarked):
                slide.bullets.append(text)
            slide.lines.append(text)
    for picture in root.iter(P + "pic"):
        properties = picture.find(f"{P}nvPicPr/{P}cNvPr")
        slide.images.append(properties.get("descr") if properties is not None else None)
    for frame in root.iter(P + "graphicFrame"):
        data = frame.find(f"{A}graphic/{A}graphicData")
        if data is not None and data.get("uri", "").endswith("/chart"):
            properties = frame.find(f"{P}nvGraphicFramePr/{P}cNvPr")
            slide.images.append(properties.get("descr") if properties is not None else None)
    slide.source_text = " ".join(footer_text)
    for rel_type, target in relationships(package, part).values():
        if rel_type.endswith("/notesSlide"):
            notes = read_xml(package, target)
            for shape in notes.iter(P + "sp"):
                if placeholder_type(shape, "nvSpPr") == "body":
                    slide.notes += " " + " ".join(paragraph_text(p) for p in shape.iter(A + "p"))
    return slide


def parse_pptx(path: Path) -> list[Slide]:
    try:
        package = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as error:
        raise LintError(f"cannot read {path} as PPTX: {error}") from None
    with package:
        presentation = read_xml(package, "ppt/presentation.xml")
        rels = relationships(package, "ppt/presentation.xml")
        slides = []
        for slide_id in presentation.iter(P + "sldId"):
            rel = rels.get(slide_id.get(R + "id", ""))
            if rel is None:
                raise LintError(f"slide id {slide_id.get('id')} has no relationship")
            slides.append(parse_pptx_slide(package, rel[1]))
        return slides


# --- Rules --------------------------------------------------------------------


def significant_figures(whole: str, fraction: str) -> int:
    whole = whole.lstrip("0")
    return len(whole + fraction) if whole else len(fraction.lstrip("0"))


def lint(slides: list[Slide], options: argparse.Namespace, check_alt: bool) -> list[tuple[int, str, str]]:
    findings: list[tuple[int, str, str]] = []
    for number, slide in enumerate(slides, start=1):

        def report(rule: str, detail: str) -> None:
            findings.append((number, rule, detail))

        title_slide = number == 1
        title = slide.title or ""
        if not title_slide and not title and (slide.lines or slide.images):
            report("title-missing", "content slide with no title")
        if not title_slide and title:
            if len(title) > options.max_title_chars:
                report("title-length", f'{len(title)} characters (max {options.max_title_chars}): "{title}"')
            if QUESTION.search(title):
                report("title-question", f'"{title}"')
            if CONTRAST.search(title):
                report("contrast-form", f'title: "{title}"')
            for whole, fraction in DECIMAL.findall(title):
                if significant_figures(whole, fraction) > 3:
                    report("title-precision", f"{whole}.{fraction} in title; round it")
        for line in slide.lines:
            if CONTRAST.search(line):
                report("contrast-form", f'"{line}"')
        if len(slide.bullets) > options.max_bullets:
            report("bullet-count", f"{len(slide.bullets)} bullets (max {options.max_bullets})")
        for bullet in slide.bullets:
            words = len(bullet.split())
            if words > options.max_bullet_words:
                start = " ".join(bullet.split()[:6])
                report("bullet-words", f'{words} words (max {options.max_bullet_words}): "{start} ..."')
        if len(slide.lines) > options.max_lines:
            report("text-lines", f"{len(slide.lines)} text lines (max {options.max_lines})")
        if check_alt:
            for index, alt in enumerate(slide.images, start=1):
                if not (alt or "").strip():
                    report("image-alt", f"image {index} has no alt text")
        source = " ".join([title, *slide.lines, slide.source_text])
        if slide.images and not title_slide and not SOURCE.search(source):
            report("figure-source", "figure with no source line; add one if the figure is reused")
        note_words = len(slide.notes.split())
        if note_words > options.max_note_words:
            report("notes-words", f"{note_words} words (max {options.max_note_words})")
    return findings


def load(path: Path, deck_format: str) -> list[Slide]:
    if deck_format == "pptx":
        return parse_pptx(path)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        raise LintError(f"cannot read {path}: {error.strerror}") from None
    if deck_format == "html":
        return parse_html(text)
    if deck_format == "markdown":
        return parse_markdown(text, path.suffix.lower())
    return parse_beamer(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="lint_slides.py",
        description="Report mechanical sci-slides rule findings for one deck.",
        epilog="Rules: " + "; ".join(f"{rule}: {text}" for rule, text in RULES.items()),
    )
    parser.add_argument("deck", type=Path, help="deck file: .html, .md, .qmd, .tex, or .pptx")
    parser.add_argument("--format", choices=sorted(set(FORMATS.values())), help="override detection by extension")
    parser.add_argument("--max-title-chars", type=int, default=60, metavar="N")
    parser.add_argument("--max-bullets", type=int, default=5, metavar="N")
    parser.add_argument("--max-bullet-words", type=int, default=10, metavar="N")
    parser.add_argument("--max-lines", type=int, default=9, metavar="N")
    parser.add_argument("--max-note-words", type=int, default=80, metavar="N")
    options = parser.parse_args(argv)

    def fail(message: str) -> int:
        print(f"{parser.prog}: error: {message}", file=sys.stderr)
        return 2

    deck_format = options.format or FORMATS.get(options.deck.suffix.lower())
    if deck_format is None:
        return fail(f"unknown deck format '{options.deck.suffix}'; pass --format")
    if not options.deck.is_file():
        return fail(f"{options.deck} is not a file")
    try:
        slides = load(options.deck, deck_format)
    except LintError as error:
        return fail(str(error))
    if not slides:
        return fail(f"no slides found in {options.deck} as {deck_format}")
    findings = lint(slides, options, check_alt=deck_format != "beamer")
    for number, rule, detail in findings:
        print(f"{options.deck}:{number}: {rule}: {detail}")
    print(f"{len(slides)} slides, {len(findings)} findings")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
