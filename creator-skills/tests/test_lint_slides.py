"""Command-line checks for the sci-slides lint script."""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PLUGIN_ROOT / "skills" / "sci-slides" / "scripts" / "lint_slides.py"
FINDING = re.compile(r"^.+:(\d+): ([a-z-]+): ", re.MULTILINE)
LONG_NOTES = " ".join(["word"] * 90)

P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG = "http://schemas.openxmlformats.org/package/2006/relationships"


def run_lint(name: str, content: str | bytes, *args: str) -> tuple[int, set, str]:
    with tempfile.TemporaryDirectory() as tmp:
        deck = Path(tmp) / name
        if isinstance(content, bytes):
            deck.write_bytes(content)
        else:
            deck.write_text(content, encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(SCRIPT), str(deck), *args],
            capture_output=True,
            text=True,
        )
    findings = {(int(slide), rule) for slide, rule in FINDING.findall(result.stdout)}
    return result.returncode, findings, result.stdout + result.stderr


def html_deck(*sections: str) -> str:
    body = "\n".join(f"<section>{s}</section>" for s in sections)
    return f'<html><body><div class="reveal"><div class="slides">{body}</div></div></body></html>'


TITLE_SLIDE = "<h1>Kinase selectivity in docking benchmarks</h1><p>A. Speaker</p>"
CLEAN_SLIDE = (
    "<h2>Docking recall drops by 40% on unseen kinases</h2>"
    "<ul><li>Recall falls from 0.82 to 0.49</li><li>Same scoring function</li></ul>"
    '<img src="recall.png" alt="Recall by kinase family">'
    "<p>Source: Smith et al., J. Med. Chem. 2021</p>"
    '<aside class="notes">Mention split by family</aside>'
)


def pptx_deck(slides: list[str], notes: dict[int, str]) -> bytes:
    """Build a minimal PPTX: slides are spTree inner XML; notes are keyed by 1-based slide number."""
    ns = f'xmlns:p="{P}" xmlns:a="{A}" xmlns:r="{R}"'
    ids = "".join(f'<p:sldId id="{255 + i}" r:id="rId{i}"/>' for i in range(1, len(slides) + 1))
    rels = "".join(
        f'<Relationship Id="rId{i}" Type="{R}/slide" Target="slides/slide{i}.xml"/>'
        for i in range(1, len(slides) + 1)
    )
    buffer = tempfile.SpooledTemporaryFile()
    with zipfile.ZipFile(buffer, "w") as pkg:
        pkg.writestr("ppt/presentation.xml", f"<p:presentation {ns}><p:sldIdLst>{ids}</p:sldIdLst></p:presentation>")
        pkg.writestr("ppt/_rels/presentation.xml.rels", f'<Relationships xmlns="{PKG}">{rels}</Relationships>')
        for i, tree in enumerate(slides, start=1):
            pkg.writestr(f"ppt/slides/slide{i}.xml", f"<p:sld {ns}><p:cSld><p:spTree>{tree}</p:spTree></p:cSld></p:sld>")
            if i in notes:
                pkg.writestr(
                    f"ppt/slides/_rels/slide{i}.xml.rels",
                    f'<Relationships xmlns="{PKG}"><Relationship Id="rId9" '
                    f'Type="{R}/notesSlide" Target="../notesSlides/notesSlide{i}.xml"/></Relationships>',
                )
                notes_body = pptx_shape(notes[i], ph='type="body" idx="1"')
                pkg.writestr(
                    f"ppt/notesSlides/notesSlide{i}.xml",
                    f"<p:notes {ns}><p:cSld><p:spTree>{notes_body}</p:spTree></p:cSld></p:notes>",
                )
    buffer.seek(0)
    return buffer.read()


def pptx_shape(*paragraphs: str, ph: str | None = None) -> str:
    placeholder = f"<p:ph {ph}/>" if ph is not None else ""
    body = "".join(f"<a:p><a:r><a:t>{text}</a:t></a:r></a:p>" for text in paragraphs)
    return (
        f'<p:sp><p:nvSpPr><p:cNvPr id="2" name="Shape"/><p:cNvSpPr/><p:nvPr>{placeholder}</p:nvPr></p:nvSpPr>'
        f"<p:txBody>{body}</p:txBody></p:sp>"
    )


def pptx_picture(alt: str | None) -> str:
    descr = f' descr="{alt}"' if alt is not None else ""
    return f'<p:pic><p:nvPicPr><p:cNvPr id="3" name="Picture"{descr}/><p:cNvPicPr/><p:nvPr/></p:nvPicPr></p:pic>'


class LintSlidesHtmlTest(unittest.TestCase):
    def test_clean_deck_reports_nothing(self) -> None:
        code, findings, output = run_lint("talk.html", html_deck(TITLE_SLIDE, CLEAN_SLIDE))
        self.assertEqual((code, findings), (0, set()), output)

    def test_title_rules(self) -> None:
        deck = html_deck(
            TITLE_SLIDE,
            "<h2>How well does docking rank kinase binders?</h2><p>Benchmark of 120 kinases</p>",
            "<h2>Binding pose drives selectivity, not affinity</h2><p>Pose RMSD below 2 Å</p>",
            "<h2>Docking recall drops sharply on kinases from families that were absent in training</h2><p>x</p>",
            "<h2>Recall reaches 87.34% on the held-out set</h2><p>x</p>",
            "<p>Text with no title</p>",
        )
        code, findings, output = run_lint("talk.html", deck)
        self.assertEqual(code, 1, output)
        self.assertEqual(
            findings,
            {(2, "title-question"), (3, "contrast-form"), (4, "title-length"), (5, "title-precision"), (6, "title-missing")},
        )

    def test_text_figure_and_notes_rules(self) -> None:
        bullets = "".join(f"<li>Point {i}</li>" for i in range(5))
        long_bullet = "<li>" + " ".join(["many"] * 12) + "</li>"
        paragraphs = "".join(f"<p>Line {i}</p>" for i in range(4))
        slide = (
            "<h2>Recall drops by 40% on unseen kinases</h2>"
            f"<ul>{bullets}{long_bullet}</ul>{paragraphs}"
            '<img src="fig.png">'
            f'<aside class="notes">{LONG_NOTES}</aside>'
        )
        code, findings, output = run_lint("talk.html", html_deck(TITLE_SLIDE, slide))
        self.assertEqual(code, 1, output)
        self.assertEqual(
            findings,
            {
                (2, "bullet-count"),
                (2, "bullet-words"),
                (2, "text-lines"),
                (2, "image-alt"),
                (2, "figure-source"),
                (2, "notes-words"),
            },
        )

    def test_nested_sections_count_leaf_slides(self) -> None:
        deck = html_deck(
            TITLE_SLIDE,
            f"<section>{CLEAN_SLIDE}</section><section><h2>Why does recall drop?</h2><p>x</p></section>",
        )
        code, findings, output = run_lint("talk.html", deck)
        self.assertEqual((code, findings), (1, {(3, "title-question")}), output)

    def test_first_slide_is_exempt_from_title_rules(self) -> None:
        deck = html_deck("<h1>Can docking rank kinase binders?</h1>", CLEAN_SLIDE)
        code, findings, output = run_lint("talk.html", deck)
        self.assertEqual((code, findings), (0, set()), output)

    def test_threshold_flags(self) -> None:
        code, findings, output = run_lint("talk.html", html_deck(TITLE_SLIDE, CLEAN_SLIDE), "--max-title-chars", "20")
        self.assertEqual((code, findings), (1, {(2, "title-length")}), output)


class LintSlidesMarkdownTest(unittest.TestCase):
    def test_marp_deck(self) -> None:
        deck = "\n".join(
            [
                "---",
                "marp: true",
                "---",
                "# Kinase selectivity in docking",
                "",
                "---",
                "<!-- _class: lead -->",
                "## Why does recall drop on new kinases?",
                "",
                "- Benchmark of 120 kinases",
                "",
                "![](recall.png)",
                "",
                f"<!-- {LONG_NOTES} -->",
                "",
                "---",
                "## Recall drops by 40% on unseen kinases",
                "",
                "- Recall falls from 0.82 to 0.49",
                "",
                "![Recall by family](recall.png)",
                "",
                "Source: Smith et al. (2021)",
                "",
                "<!-- Short note -->",
            ]
        )
        code, findings, output = run_lint("talk.md", deck)
        self.assertEqual(code, 1, output)
        self.assertEqual(
            findings,
            {(2, "title-question"), (2, "image-alt"), (2, "figure-source"), (2, "notes-words")},
        )

    def test_quarto_headings_split_slides(self) -> None:
        deck = "\n".join(
            [
                "---",
                "title: Kinase selectivity",
                "format: revealjs",
                "---",
                "",
                "## Pose drives selectivity",
                "",
                "- Pose matters for selectivity, not affinity",
                "",
                "::: {.notes}",
                LONG_NOTES,
                ":::",
                "",
                "## Recall drops by 40% on unseen kinases",
                "",
                "- Recall falls from 0.82 to 0.49",
                "",
                "Note: keep this short",
            ]
        )
        code, findings, output = run_lint("talk.qmd", deck)
        self.assertEqual(code, 1, output)
        # Quarto builds slide 1 from the front matter title.
        self.assertEqual(findings, {(2, "contrast-form"), (2, "notes-words")})


class LintSlidesBeamerTest(unittest.TestCase):
    def test_beamer_frames(self) -> None:
        deck = r"""
\documentclass{beamer}
\begin{document}
\begin{frame}
  \titlepage
\end{frame}
\begin{frame}{How well does docking rank binders?}
  \begin{itemize}
    \item Benchmark of 120 kinases % a comment, not slide text
  \end{itemize}
  \includegraphics[width=\textwidth]{recall.pdf}
  \note{""" + LONG_NOTES + r"""}
\end{frame}
\begin{frame}[t]
  \frametitle{Recall drops by 40\% on unseen kinases}
  \includegraphics{recall.pdf}
  \footcite{smith2021}
\end{frame}
\end{document}
"""
        code, findings, output = run_lint("talk.tex", deck)
        self.assertEqual(code, 1, output)
        self.assertEqual(findings, {(2, "title-question"), (2, "figure-source"), (2, "notes-words")})


class LintSlidesPptxTest(unittest.TestCase):
    def test_pptx_slides_and_notes(self) -> None:
        slides = [
            pptx_shape("Kinase selectivity in docking", ph='type="ctrTitle"'),
            pptx_shape("How well does docking rank binders?", ph='type="title"')
            + pptx_shape(*[f"Point {i}" for i in range(6)], ph='idx="1"')
            + pptx_picture(None),
            pptx_shape("Recall drops by 40% on unseen kinases", ph='type="title"')
            + pptx_shape("Recall falls from 0.82 to 0.49", ph='idx="1"')
            + pptx_picture("Recall by kinase family")
            + pptx_shape("Source: Smith et al. 2021"),
        ]
        deck = pptx_deck(slides, notes={2: LONG_NOTES, 3: "Short note"})
        code, findings, output = run_lint("talk.pptx", deck)
        self.assertEqual(code, 1, output)
        self.assertEqual(
            findings,
            {(2, "title-question"), (2, "bullet-count"), (2, "image-alt"), (2, "figure-source"), (2, "notes-words")},
        )


class LintSlidesErrorTest(unittest.TestCase):
    def assert_error(self, code: int, output: str) -> None:
        self.assertEqual(code, 2, output)
        self.assertIn("lint_slides.py: error:", output)
        self.assertNotIn("Traceback", output)

    def test_unknown_format(self) -> None:
        code, _, output = run_lint("talk.key", "x")
        self.assert_error(code, output)

    def test_no_slides(self) -> None:
        code, _, output = run_lint("talk.html", "<html><body><p>No sections</p></body></html>")
        self.assert_error(code, output)

    def test_unreadable_pptx(self) -> None:
        code, _, output = run_lint("talk.pptx", b"not a zip file")
        self.assert_error(code, output)

    def test_missing_file(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), str(PLUGIN_ROOT / "missing-deck.html")],
            capture_output=True,
            text=True,
        )
        self.assert_error(result.returncode, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
