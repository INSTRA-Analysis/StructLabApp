"""Build guide/StructLab_User_Guide.pdf from the Markdown chapters (no pandoc needed).

Run from the repository root:  python guide/tools/build_pdf.py

Each chapter (guide/NN_*.md, in file-name order) is read by Qt's own Markdown reader,
images are scaled to the text width, and the chapters are printed to one A4 PDF after a
title page, each chapter starting on a new page. The version comes from ui_qt/version.py.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "guide"
OUTPUT = GUIDE / "StructLab_User_Guide.pdf"
sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import QMarginsF, QUrl  # noqa: E402
from PyQt6.QtGui import (QGuiApplication, QImage, QPageLayout, QPageSize, QPdfWriter,  # noqa: E402
                         QTextDocument)

from ui_qt.version import VERSION_LABEL  # noqa: E402

RESOLUTION = 96                      # document units = pixels at 96 dpi
MARGIN_MM = 18.0
SCREEN_TO_PAGE = 0.75                # a screenshot pixel drawn this many page pixels wide

STYLE = """
body   { font-family: 'Segoe UI'; font-size: 10.5pt; color: #1d2430; }
h1     { font-size: 22pt; color: #0b6f86; margin-top: 0; margin-bottom: 10px; }
h2     { font-size: 15pt; color: #0b6f86; margin-top: 18px; margin-bottom: 6px; }
h3     { font-size: 12pt; color: #1d2430; margin-top: 12px; margin-bottom: 4px; }
p, li  { line-height: 135%; }
code   { font-family: 'Consolas'; font-size: 9.5pt; color: #4a2a7a; }
pre    { font-family: 'Consolas'; font-size: 9pt; background-color: #f1f4f8; }
table  { border-collapse: collapse; margin-top: 4px; margin-bottom: 8px; }
th     { background-color: #e4eef3; font-weight: bold; padding: 4px; }
td     { padding: 4px; }
blockquote { color: #3d4a5c; background-color: #eef6f9; }
"""


def chapters() -> list[Path]:
    return sorted(p for p in GUIDE.glob("[0-9][0-9]_*.md"))


def chapter_html(path: Path, text_width: float) -> str:
    """The chapter's Markdown as HTML body content, images sized to fit the page."""
    doc = QTextDocument()
    doc.setMarkdown(path.read_text(encoding="utf-8"),
                    QTextDocument.MarkdownFeature.MarkdownDialectGitHub)
    html = doc.toHtml()
    body = html[html.index("<body"):]
    body = body[body.index(">") + 1:body.rindex("</body>")]

    def sized(match: re.Match) -> str:
        file = (path.parent / match.group(1)).resolve()
        image = QImage(str(file))
        width = text_width if image.isNull() else min(text_width, image.width() * SCREEN_TO_PAGE)
        # an absolute file URL: a relative one, resolved against the base URL, prints nothing
        return f'<img src="{QUrl.fromLocalFile(str(file)).toString()}" width="{int(width)}" />'

    body = re.sub(r'<img src="([^"]+)"[^>]*/?>', sized, body)
    # Qt writes inline block margins and heading sizes; let the style sheet decide those,
    # but keep span styles (bold, italic, code)
    body = re.sub(r'(<(?:p|h[1-6]|li|ul|ol|table|tr|td|th|pre)\b[^>]*?) style="[^"]*"', r"\1", body)
    body = re.sub(r'(<span style="[^"]*?)\s*font-size:[^;"]*;?', r"\1", body)
    # Qt marks code as the generic 'monospace', which prints in a tiny fallback font
    return body.replace("font-family:'monospace';", "font-family:'Consolas'; color:#4a2a7a;")


def title_page() -> str:
    return (
        '<p style="margin-top: 260px;"><span style="font-size: 40pt; font-weight: bold; '
        'color: #0b6f86;">StructLab</span></p>'
        '<p><span style="font-size: 20pt;">User Guide</span></p>'
        f'<p><span style="font-size: 13pt; color: #5a6676;">{VERSION_LABEL}</span></p>'
        '<p style="margin-top: 320px;"><span style="color: #5a6676;">Plane and space frame '
        'analysis by the direct stiffness method.<br/>Free and open source under the GNU GPL v3.'
        '<br/>© 2024–2026 Imed Mhamdi / INSTRA Analysis</span></p>'
    )


def build() -> Path:
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)  # noqa: F841 (needed for fonts)
    writer = QPdfWriter(str(OUTPUT))
    writer.setResolution(RESOLUTION)
    writer.setPageLayout(QPageLayout(QPageSize(QPageSize.PageSizeId.A4),
                                     QPageLayout.Orientation.Portrait,
                                     QMarginsF(MARGIN_MM, MARGIN_MM, MARGIN_MM, MARGIN_MM),
                                     QPageLayout.Unit.Millimeter))
    writer.setTitle(f"StructLab User Guide {VERSION_LABEL}")
    writer.setCreator("INSTRA Analysis")
    page_px = writer.pageLayout().paintRectPixels(RESOLUTION)
    text_width = page_px.width() - 8

    parts = [title_page()]
    for path in chapters():
        parts.append('<div style="page-break-before: always;">' + chapter_html(path, text_width)
                     + "</div>")
    doc = QTextDocument()
    doc.setDefaultStyleSheet(STYLE)
    doc.setHtml("<html><body>" + "".join(parts) + "</body></html>")
    doc.print(writer)
    return OUTPUT


if __name__ == "__main__":
    print("wrote", build())
