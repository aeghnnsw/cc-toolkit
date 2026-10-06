#!/usr/bin/env python3
"""Lint a slide deck for the mechanical sci-slides rules.

Reads one deck: reveal.js HTML (including inline or external data-markdown
sections), Markdown (Marp, Slidev, reveal.js, Quarto), LaTeX Beamer, or PPTX.
Prints one finding per line on stdout as ``<file>:<slide>: <rule>: <detail>``
and a summary line on stderr.

Exit status: 0 with no findings, 1 with findings, 2 on an error.

Slide 1 is the title slide: the title and figure-source rules skip it.
Findings are advisory. The skill's slide-text and design references hold
the rules; this script finds the mechanical cases.
"""

from __future__ import annotations

import argparse
import html
import posixpath
import re
import sys
import zipfile
import zlib
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable
from xml.etree import ElementTree

RULES = {
    "title-missing": "a content slide has no title",
    "title-length": "the title is longer than --max-title-chars",
    "title-question": "the title is a question",
    "contrast-form": 'the title or a text line uses the "X, not Y" form',
    "title-precision": "a number in the title has more than --max-title-sig-figs significant figures",
    "bullet-count": "the slide has more than --max-bullets bullets",
    "bullet-words": "a bullet has more than --max-bullet-words words",
    "text-lines": "the slide has more than --max-lines text lines",
    "image-alt": "an image has no alt text, or a file name as alt text (not checked for Beamer)",
    "figure-source": "the slide shows a figure and no source line",
    "notes-words": "the notes have more than --max-note-words words",
}

QUESTION = re.compile(r"\?\s*$")
CONTRAST = re.compile(r"(?:[,;—–]|\s-)\s*not\s+\w", re.IGNORECASE)
NUMBER = re.compile(r"(?<![\w.,])(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?(?![\w.]|,\d)")
FILE_NAME = re.compile(r"^[\w\-. ]+\.(?:png|jpe?g|gif|svg|tiff?|bmp|emf|wmf|eps|pdf|webp)$", re.IGNORECASE)
CITE = r"\\[A-Za-z]*cite[A-Za-z]*\*?"
SOURCE = re.compile(
    r"\b(?:sources?|credits?|courtesy)\s*:"
    r"|\b(?:adapted|reproduced|reprinted|modified)\s+from\b"
    r"|\bet al\b|\bdoi\b|©|\bthis work\b"
    r"|" + CITE + r"|\([^()]*\b(?:19|20)\d{2}[a-z]?\s*\)",
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
    source_text: str = ""  # text that may hold a source but is not a slide line

    def add_bullet(self, text: str) -> None:
        self.bullets.append(text)
        self.lines.append(text)


@dataclass(frozen=True)
class Limits:
    title_chars: int = 60
    title_sig_figs: int = 3
    bullets: int = 5
    bullet_words: int = 10
    lines: int = 9
    note_words: int = 80


def clean(text: str) -> str:
    return " ".join(text.split())


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        raise LintError(f"cannot read {path}: {error.strerror}") from None


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
NOTE_LINE = re.compile(r"^\s*notes?:\s*(.*)$", re.IGNORECASE)
TAG = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class Flavour:
    """Markdown deck conventions that differ between tools."""

    heading_split: bool  # Quarto and Pandoc start a slide at each level 1-2 heading
    yaml_chunks: bool  # Slidev puts per-slide front matter between separators
    note_lines: bool  # reveal.js starts the notes at a "Note:" line


REVEAL_MARKDOWN = Flavour(heading_split=False, yaml_chunks=False, note_lines=True)


def md_inline(text: str) -> str:
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = TAG.sub(" ", text)
    return clean(text.replace("**", "").replace("__", "").replace("`", "").replace("*", ""))


def outside_fences(lines: list[str]):
    """Yield (line, is_code) pairs; fence lines themselves count as code."""
    in_fence = False
    for line in lines:
        if FENCE.match(line):
            in_fence = not in_fence
            yield line, True
        else:
            yield line, in_fence


def separator_chunks(lines: list[str]) -> list[list[str]]:
    chunks: list[list[str]] = [[]]
    for line, code in outside_fences(lines):
        if not code and SEPARATOR.match(line):
            chunks.append([])
        else:
            chunks[-1].append(line)
    return chunks


def is_yaml(chunk: list[str]) -> bool:
    content = [line for line in chunk if line.strip()]
    return bool(content) and all(YAML_LINE.match(line) for line in content)


def split_markdown(lines: list[str], flavour: Flavour) -> list[list[str]]:
    chunks = separator_chunks(lines)
    if flavour.heading_split:
        split: list[list[str]] = []
        for chunk in chunks:
            current: list[str] = []
            has_heading = False
            for line, code in outside_fences(chunk):
                heading = None if code else MD_HEADING.match(line)
                if heading and len(heading.group(1)) <= 2 and has_heading:
                    split.append(current)
                    current, has_heading = [], False
                has_heading = has_heading or bool(heading)
                current.append(line)
            split.append(current)
        chunks = split
    chunks = [chunk for chunk in chunks if any(line.strip() for line in chunk)]
    if not flavour.yaml_chunks:
        return chunks
    # Slidev: a YAML block between separators is the front matter of the next
    # chunk, which is that slide's body even when it looks like YAML too.
    slides: list[list[str]] = []
    after_front_matter = False
    for chunk in chunks:
        if is_yaml(chunk) and not after_front_matter:
            after_front_matter = True
            continue
        slides.append(chunk)
        after_front_matter = False
    return slides


def parse_markdown_slide(lines: list[str], flavour: Flavour) -> Slide:
    slide = Slide()
    text = "\n".join(lines)
    for body in COMMENT.findall(text):
        body_lines = [line for line in body.splitlines() if line.strip()]
        if body_lines and not all(DIRECTIVE.match(line) for line in body_lines):
            slide.notes += " " + body
    in_notes_div = in_note_tail = False
    for line, code in outside_fences(COMMENT.sub("", text).splitlines()):
        if in_note_tail:
            slide.notes += " " + line
            continue
        if code:
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
        note = NOTE_LINE.match(line) if flavour.note_lines else None
        if note:
            in_note_tail = True
            slide.notes += " " + note.group(1)
            continue
        slide.images.extend(MD_IMAGE.findall(line))
        for tag in HTML_IMAGE.findall(line):
            alt = ALT.search(tag)
            slide.images.append(html.unescape(alt.group(2)) if alt else None)
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
                slide.add_bullet(content)
        else:
            content = md_inline(line)
            if re.search(r"\w", content):
                slide.lines.append(content)
    return slide


def markdown_slides(text: str, flavour: Flavour) -> list[Slide]:
    return [parse_markdown_slide(chunk, flavour) for chunk in split_markdown(text.splitlines(), flavour)]


def parse_markdown(path: Path) -> list[Slide]:
    lines = read_text(path).splitlines()
    front_keys: set[str] | None = None
    if lines and lines[0].strip() == "---":
        for end in range(1, len(lines)):
            if lines[end].strip() in ("---", "..."):
                front_keys = {l.split(":", 1)[0].strip() for l in lines[1:end] if YAML_LINE.match(l)}
                lines = lines[end + 1:]
                break
    keys = front_keys or set()
    quarto = path.suffix.lower() in (".qmd", ".rmd") or "format" in keys
    chunks = separator_chunks(lines)
    layout_blocks = any(is_yaml(c) and any(l.startswith("layout:") for l in c) for c in chunks)
    slidev = not quarto and "marp" not in keys and (front_keys is not None or layout_blocks)
    flavour = Flavour(
        heading_split=quarto or len(chunks) == 1,
        yaml_chunks=slidev,
        note_lines=front_keys is None and not slidev,
    )
    slides = markdown_slides("\n".join(lines), flavour)
    # Quarto and Pandoc build a title slide from the front matter title.
    if quarto and "title" in keys:
        slides.insert(0, Slide())
    return slides


# --- HTML (reveal.js) ---------------------------------------------------------

HEADINGS = {"h1", "h2", "h3"}
BLOCKS = {
    "p", "h4", "h5", "h6", "figcaption", "blockquote", "td", "th", "dt", "dd",
    "pre", "caption", "small", "footer", "cite",
}
BOUNDARIES = {
    "address", "article", "aside", "blockquote", "br", "dd", "details", "div", "dl",
    "dt", "figcaption", "figure", "footer", "h1", "h2", "h3", "h4", "h5", "h6",
    "header", "hr", "li", "main", "nav", "ol", "p", "pre", "section", "table", "tbody",
    "td", "tfoot", "th", "thead", "tr", "ul",
}
TEMPLATE = re.compile(r"<(textarea|script)\b[^>]*>(.*?)</\1\s*>", re.IGNORECASE | re.DOTALL)


@dataclass
class _Section:
    slide: Slide
    has_child: bool = False
    markdown_start: int | None = None  # offset after the start tag of a data-markdown section
    markdown_file: str = ""
    separators: tuple[str, ...] = ()  # data-separator and data-separator-vertical patterns


@dataclass
class _Buffer:
    tag: str
    kind: str  # "heading", "bullet", or "block"
    parts: list[str] = field(default_factory=list)


class _RevealParser(HTMLParser):
    def __init__(self, raw: str, base: Path) -> None:
        super().__init__(convert_charrefs=True)
        self.slides: list[Slide] = []
        self._raw = raw
        self._base = base
        self._line_starts = [0] + [m.end() for m in re.finditer("\n", raw)]
        self._sections: list[_Section] = []
        self._buffers: list[_Buffer] = []
        self._loose: list[str] = []
        self._notes_depth = 0
        self._skip_depth = 0

    def parse(self) -> list[Slide]:
        self.feed(self._raw)
        self.close()
        while self._sections:
            self.handle_endtag("section")
        return self.slides

    def _offset(self) -> int:
        line, column = self.getpos()
        return self._line_starts[line - 1] + column

    @property
    def _section(self) -> _Section | None:
        return self._sections[-1] if self._sections else None

    def _in_markdown(self) -> bool:
        return self._section is not None and self._section.markdown_start is not None

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if self._in_markdown():
            return
        attributes = dict(attrs)
        if tag in BOUNDARIES:
            self._flush_loose()
        if tag == "section":
            if self._section:
                self._section.has_child = True
            section = _Section(Slide())
            if "data-markdown" in attributes:
                section.markdown_start = self._offset() + len(self.get_starttag_text() or "")
                section.markdown_file = attributes.get("data-markdown") or ""
                section.separators = tuple(
                    attributes[name] for name in ("data-separator", "data-separator-vertical") if attributes.get(name)
                )
            self._sections.append(section)
            return
        slide = self._section.slide if self._section else None
        if slide is None:
            return
        if tag in ("script", "style"):
            self._skip_depth += 1
        elif tag == "aside" and "notes" in (attributes.get("class") or "").split():
            self._notes_depth += 1
        elif self._notes_depth:
            return
        elif tag == "img":
            slide.images.append(attributes.get("alt"))
        elif tag in HEADINGS or tag in BLOCKS or tag == "li":
            if tag in ("li", "p") and self._buffers and self._buffers[-1].tag == tag:
                self._close_buffer()
            kind = "heading" if tag in HEADINGS else "bullet" if tag == "li" else "block"
            self._buffers.append(_Buffer(tag, kind))

    def handle_endtag(self, tag: str) -> None:
        if tag == "section":
            self._end_section()
            return
        if self._in_markdown():
            return
        if tag in BOUNDARIES:
            self._flush_loose()
        if tag in ("script", "style") and self._skip_depth:
            self._skip_depth -= 1
        elif tag == "aside" and self._notes_depth:
            self._notes_depth -= 1
        elif tag in ("ul", "ol"):
            while self._buffers and self._buffers[-1].kind in ("bullet", "block"):
                closed = self._buffers[-1].kind
                self._close_buffer()
                if closed == "bullet":
                    break
        elif any(buffer.tag == tag for buffer in self._buffers):
            while self._buffers:
                closing = self._buffers[-1].tag
                self._close_buffer()
                if closing == tag:
                    break

    def handle_data(self, data: str) -> None:
        section = self._section
        if section is None or self._in_markdown() or self._skip_depth:
            return
        if self._notes_depth:
            section.slide.notes += " " + data
        elif self._buffers:
            self._buffers[-1].parts.append(data)
        else:
            self._loose.append(data)

    def _end_section(self) -> None:
        if not self._sections:
            return
        if not self._in_markdown():
            self._flush_loose()
            while self._buffers:
                self._close_buffer()
        section = self._sections.pop()
        if section.markdown_start is not None:
            self.slides.extend(self._markdown(section))
        elif not section.has_child:
            self.slides.append(section.slide)

    def _markdown(self, section: _Section) -> list[Slide]:
        # reveal.js splits an external file on "---" lines, and an inline
        # section only when it sets a separator attribute.
        if section.markdown_file:
            if re.match(r"[a-z][a-z0-9+.-]*://", section.markdown_file, re.IGNORECASE):
                raise LintError(f"data-markdown source {section.markdown_file} is remote; lint the Markdown file itself")
            return markdown_slides(read_text(self._base / section.markdown_file), REVEAL_MARKDOWN)
        raw = self._raw[section.markdown_start:self._offset()]
        template = TEMPLATE.search(raw)
        if template:
            raw = html.unescape(template.group(2)) if template.group(1).lower() == "textarea" else template.group(2)
        parts = [raw]
        for pattern in section.separators:
            try:
                parts = [piece for part in parts for piece in re.split(pattern, part, flags=re.MULTILINE)]
            except re.error as error:
                raise LintError(f"data-separator {pattern!r} is not a usable pattern: {error}") from None
        slides = [parse_markdown_slide(part.splitlines(), REVEAL_MARKDOWN) for part in parts if part.strip()]
        return slides or [Slide()]

    def _flush_loose(self) -> None:
        text = clean(" ".join(self._loose))
        self._loose = []
        if text and self._section:
            self._section.slide.lines.append(text)

    def _close_buffer(self) -> None:
        buffer = self._buffers.pop()
        text = clean(" ".join(buffer.parts))
        slide = self._section.slide if self._section else None
        if not text or slide is None:
            return
        parent = self._buffers[-1] if self._buffers else None
        if buffer.kind == "heading" and slide.title is None:
            slide.title = text
        elif buffer.kind == "block" and parent is not None and parent.kind != "heading":
            parent.parts.append(text)
        elif buffer.kind == "bullet":
            slide.add_bullet(text)
        else:
            slide.lines.append(text)


def parse_html(path: Path) -> list[Slide]:
    return _RevealParser(read_text(path), path.parent).parse()


# --- LaTeX Beamer --------------------------------------------------------------

DROPPED_COMMANDS = re.compile(
    r"(?:\\(?:includegraphics|vspace|hspace|label|ref|eqref|input|url|pause)|" + CITE + r")"
    r"\*?(?:\[[^\]]*\])*(?:\{[^}]*\})?"
)
ITEM = re.compile(
    r"\\item(?:\s*<[^>]*>)?(?:\s*\[[^\]]*\])?(.*?)"
    r"(?=\\item|\\end\{(?:itemize|enumerate|description)\}|\\begin\{|\Z)",
    re.DOTALL,
)


def read_group(text: str, start: int, opening: str = "{", closing: str = "}") -> tuple[str, int] | None:
    """Return the balanced group at ``start`` (after whitespace) and the index after it."""
    index = start
    while index < len(text) and text[index] in " \t\r\n":
        index += 1
    if index >= len(text) or text[index] != opening:
        return None
    depth = 0
    position = index
    while position < len(text):
        char = text[position]
        if char == "\\":
            position += 2
            continue
        if char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return text[index + 1:position], position + 1
        position += 1
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
    text = DROPPED_COMMANDS.sub(" ", text)
    text = re.sub(r"\\[A-Za-z]+\*?|\\\\", " ", text)
    return clean(text.replace("{", "").replace("}", "").replace("~", " "))


def parse_beamer(path: Path) -> list[Slide]:
    text = re.sub(r"(?<!\\)%.*", "", read_text(path))
    slides: list[Slide] = []
    for match in re.finditer(r"\\begin\{frame\}", text):
        end = text.find(r"\end{frame}", match.end())
        if end == -1:
            end = len(text)
        index = skip_options(text, match.end())
        slide = Slide()
        group = read_group(text, index)
        if group:
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
        for content in ITEM.findall(body):
            bullet = latex_text(content)
            if bullet:
                slide.add_bullet(bullet)
        for line in ITEM.sub(" ", body).splitlines():
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
    except (zipfile.BadZipFile, zlib.error, EOFError, OSError, RuntimeError, NotImplementedError) as error:
        raise LintError(f"cannot read PPTX part {name}: {error}") from None


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


def placeholder_type(shape: ElementTree.Element) -> str | None:
    placeholder = shape.find(f"{P}nvSpPr/{P}nvPr/{P}ph")
    return None if placeholder is None else placeholder.get("type", "obj")


def is_bullet(paragraph: ElementTree.Element, kind: str | None) -> bool:
    properties = paragraph.find(A + "pPr")
    if properties is not None:
        if properties.find(A + "buNone") is not None:
            return False
        if properties.find(A + "buChar") is not None or properties.find(A + "buAutoNum") is not None:
            return True
    return kind in BULLET_PLACEHOLDERS


def parse_pptx_slide(package: zipfile.ZipFile, part: str) -> Slide:
    root = read_xml(package, part)
    slide = Slide()
    furniture_text = []
    for shape in root.iter(P + "sp"):
        kind = placeholder_type(shape)
        paragraphs = [(p, paragraph_text(p)) for p in shape.iter(A + "p")]
        paragraphs = [(p, text) for p, text in paragraphs if text]
        if kind in ("title", "ctrTitle"):
            if slide.title is None and paragraphs:
                slide.title = " ".join(text for _, text in paragraphs)
        elif kind in FURNITURE:
            furniture_text.extend(text for _, text in paragraphs)
        else:
            for paragraph, text in paragraphs:
                if is_bullet(paragraph, kind):
                    slide.add_bullet(text)
                else:
                    slide.lines.append(text)
    for picture in root.iter(P + "pic"):
        properties = picture.find(f"{P}nvPicPr/{P}cNvPr")
        slide.images.append(properties.get("descr") if properties is not None else None)
    for frame in root.iter(P + "graphicFrame"):
        data = frame.find(f"{A}graphic/{A}graphicData")
        if data is not None and data.get("uri", "").endswith("/chart"):
            properties = frame.find(f"{P}nvGraphicFramePr/{P}cNvPr")
            slide.images.append(properties.get("descr") if properties is not None else None)
    slide.source_text = " ".join(furniture_text)
    for rel_type, target in relationships(package, part).values():
        if rel_type.endswith("/notesSlide") and target in package.namelist():
            for shape in read_xml(package, target).iter(P + "sp"):
                if placeholder_type(shape) == "body":
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


@dataclass(frozen=True)
class DeckFormat:
    parse: Callable[[Path], list[Slide]]
    check_alt: bool


FORMATS = {
    "html": DeckFormat(parse_html, check_alt=True),
    "markdown": DeckFormat(parse_markdown, check_alt=True),
    "beamer": DeckFormat(parse_beamer, check_alt=False),
    "pptx": DeckFormat(parse_pptx, check_alt=True),
}
EXTENSIONS = {
    ".html": "html", ".htm": "html", ".md": "markdown", ".markdown": "markdown",
    ".qmd": "markdown", ".rmd": "markdown", ".tex": "beamer", ".pptx": "pptx",
}


def significant_figures(whole: str, fraction: str) -> int:
    digits = whole.replace(",", "").lstrip("0")
    if fraction:
        return len(digits + fraction) if digits else len(fraction.lstrip("0"))
    return len(digits.rstrip("0"))


def unrounded_numbers(title: str, limit: int) -> list[str]:
    found = []
    for match in NUMBER.finditer(title):
        whole, fraction = match.group(1), match.group(2) or ""
        is_year = not fraction and len(whole) == 4 and 1900 <= int(whole) <= 2099
        if not is_year and significant_figures(whole, fraction) > limit:
            found.append(match.group(0))
    return found


def alt_problem(alt: str | None) -> str | None:
    text = (alt or "").strip()
    if not text:
        return "has no alt text"
    if FILE_NAME.match(text):
        return f'has a file name as alt text ("{text}")'
    return None


def lint(slides: list[Slide], limits: Limits, check_alt: bool) -> list[tuple[int, str, str]]:
    findings: list[tuple[int, str, str]] = []
    for number, slide in enumerate(slides, start=1):

        def report(rule: str, detail: str) -> None:
            findings.append((number, rule, detail))

        title_slide = number == 1
        title = slide.title or ""
        if not title_slide and not title and (slide.lines or slide.images):
            report("title-missing", "content slide with no title")
        if not title_slide and title:
            if len(title) > limits.title_chars:
                report("title-length", f'{len(title)} characters (max {limits.title_chars}): "{title}"')
            if QUESTION.search(title):
                report("title-question", f'"{title}"')
            if CONTRAST.search(title):
                report("contrast-form", f'title: "{title}"')
            for value in unrounded_numbers(title, limits.title_sig_figs):
                report("title-precision", f"{value} has more than {limits.title_sig_figs} significant figures")
        for line in slide.lines:
            if CONTRAST.search(line):
                report("contrast-form", f'"{line}"')
        if len(slide.bullets) > limits.bullets:
            report("bullet-count", f"{len(slide.bullets)} bullets (max {limits.bullets})")
        for bullet in slide.bullets:
            words = bullet.split()
            if len(words) > limits.bullet_words:
                report("bullet-words", f'{len(words)} words (max {limits.bullet_words}): "{" ".join(words[:6])} ..."')
        if len(slide.lines) > limits.lines:
            report("text-lines", f"{len(slide.lines)} text lines (max {limits.lines})")
        if check_alt:
            for index, alt in enumerate(slide.images, start=1):
                problem = alt_problem(alt)
                if problem:
                    report("image-alt", f"image {index} {problem}")
        source = " ".join([title, *slide.lines, slide.source_text])
        if slide.images and not title_slide and not SOURCE.search(source):
            report("figure-source", "figure with no source line; add one if the figure is reused")
        note_words = len(slide.notes.split())
        if note_words > limits.note_words:
            report("notes-words", f"{note_words} words (max {limits.note_words})")
    return findings


def main(argv: list[str] | None = None) -> int:
    defaults = Limits()
    parser = argparse.ArgumentParser(
        prog="lint_slides.py",
        description="Report mechanical sci-slides rule findings for one deck.",
        epilog="Rules: " + "; ".join(f"{rule}: {text}" for rule, text in RULES.items()),
    )
    parser.add_argument("deck", type=Path, help="deck file: .html, .md, .qmd, .tex, or .pptx")
    parser.add_argument("--format", choices=sorted(FORMATS), help="override detection by extension")
    parser.add_argument("--max-title-chars", type=int, default=defaults.title_chars, metavar="N")
    parser.add_argument("--max-title-sig-figs", type=int, default=defaults.title_sig_figs, metavar="N")
    parser.add_argument("--max-bullets", type=int, default=defaults.bullets, metavar="N")
    parser.add_argument("--max-bullet-words", type=int, default=defaults.bullet_words, metavar="N")
    parser.add_argument("--max-lines", type=int, default=defaults.lines, metavar="N")
    parser.add_argument("--max-note-words", type=int, default=defaults.note_words, metavar="N")
    options = parser.parse_args(argv)

    def fail(message: str) -> int:
        print(f"{parser.prog}: error: {message}", file=sys.stderr)
        return 2

    name = options.format or EXTENSIONS.get(options.deck.suffix.lower())
    if name is None:
        return fail(f"unknown deck format '{options.deck.suffix}'; pass --format")
    if not options.deck.is_file():
        return fail(f"{options.deck} is not a file")
    deck_format = FORMATS[name]
    try:
        slides = deck_format.parse(options.deck)
    except LintError as error:
        return fail(str(error))
    if not slides:
        return fail(f"no slides found in {options.deck} as {name}")
    limits = Limits(
        title_chars=options.max_title_chars,
        title_sig_figs=options.max_title_sig_figs,
        bullets=options.max_bullets,
        bullet_words=options.max_bullet_words,
        lines=options.max_lines,
        note_words=options.max_note_words,
    )
    findings = lint(slides, limits, deck_format.check_alt)
    for number, rule, detail in findings:
        print(f"{options.deck}:{number}: {rule}: {detail}")
    print(f"{len(slides)} slides, {len(findings)} findings", file=sys.stderr)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
