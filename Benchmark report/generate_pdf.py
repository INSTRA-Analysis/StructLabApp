"""Convert benchmarking.txt to a formatted PDF report using reportlab.

Run:
    python "Benchmark report/generate_pdf.py"

Output:  Benchmark report/benchmarking_report.pdf
"""
from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    HRFlowable,
    KeepTogether,
    PageBreak,
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER

# ── Paths ─────────────────────────────────────────────────────────────────────
REPORT_DIR = Path(__file__).parent
INPUT_TXT  = REPORT_DIR / "benchmarking.txt"
OUTPUT_PDF = REPORT_DIR / "benchmarking_report.pdf"

# ── Page geometry ─────────────────────────────────────────────────────────────
PAGE_W, PAGE_H = A4          # 595.28 × 841.89 pt
TOP_BAND_H     = 28 * mm     # decorative band height (title page top)
BOT_BAND_H     = 20 * mm     # decorative band height (all pages bottom)
TOP_MARGIN     = TOP_BAND_H  # content starts just below top band
BOT_MARGIN     = BOT_BAND_H + 6 * mm
SIDE_MARGIN    = 20 * mm

# ── Colour palette ────────────────────────────────────────────────────────────
C_DARK_BLUE  = colors.HexColor("#1a3a5c")
C_MID_BLUE   = colors.HexColor("#2c5f8a")
C_LIGHT_BLUE = colors.HexColor("#6aafd6")
C_ACCENT_BG  = colors.HexColor("#e8f0f8")
C_PASS_GREEN = colors.HexColor("#1e7a34")
C_PASS_BG    = colors.HexColor("#d4edda")
C_RULE       = colors.HexColor("#4a90c4")
C_SECTION_BG = colors.HexColor("#dce8f5")
C_CASE_BG    = colors.HexColor("#f0f4f8")
C_BODY_TXT   = colors.HexColor("#1a1a2e")
C_GREY       = colors.HexColor("#555566")
C_WHITE      = colors.white

# ── Paragraph styles ─────────────────────────────────────────────────────────
def _style(name, **kw) -> ParagraphStyle:
    return ParagraphStyle(name, **kw)

# Title-page styles
STYLE_TP_MAIN = _style(
    "TpMain",
    fontName="Helvetica-Bold",
    fontSize=44,
    textColor=C_DARK_BLUE,
    alignment=TA_CENTER,
    spaceAfter=0,
    leading=52,
)
STYLE_TP_PHASE = _style(
    "TpPhase",
    fontName="Helvetica",
    fontSize=13,
    textColor=C_LIGHT_BLUE,
    alignment=TA_CENTER,
    spaceAfter=0,
    leading=18,
    letterSpacing=2,
)
STYLE_TP_REPORT = _style(
    "TpReport",
    fontName="Helvetica-Bold",
    fontSize=18,
    textColor=C_MID_BLUE,
    alignment=TA_CENTER,
    spaceAfter=0,
    leading=24,
)
STYLE_TP_VS = _style(
    "TpVs",
    fontName="Helvetica-Bold",
    fontSize=12,
    textColor=C_MID_BLUE,
    alignment=TA_CENTER,
    spaceAfter=0,
)
STYLE_TP_SUB = _style(
    "TpSub",
    fontName="Helvetica",
    fontSize=10,
    textColor=C_GREY,
    alignment=TA_CENTER,
    spaceAfter=0,
)
STYLE_TP_STATS = _style(
    "TpStats",
    fontName="Helvetica-Bold",
    fontSize=10,
    textColor=C_PASS_GREEN,
    backColor=C_PASS_BG,
    borderPad=8,
    alignment=TA_CENTER,
    spaceAfter=0,
)

# Content styles
STYLE_SECTION = _style(
    "Section",
    fontName="Helvetica-Bold",
    fontSize=12,
    textColor=C_DARK_BLUE,
    backColor=C_SECTION_BG,
    borderPad=6,
    spaceBefore=12,
    spaceAfter=4,
)
STYLE_CASE = _style(
    "Case",
    fontName="Helvetica-Bold",
    fontSize=9,
    textColor=C_MID_BLUE,
    backColor=C_CASE_BG,
    borderPad=4,
    spaceBefore=8,
    spaceAfter=3,
)
STYLE_SUMMARY_LINE = _style(
    "SummaryLine",
    fontName="Helvetica",
    fontSize=9,
    textColor=C_BODY_TXT,
    leftIndent=8,
    spaceAfter=2,
)
STYLE_ROW = _style(
    "Row",
    fontName="Courier",
    fontSize=7.5,
    textColor=C_BODY_TXT,
    leftIndent=12,
    spaceAfter=1,
)
STYLE_RESULT_PASS = _style(
    "ResultPass",
    fontName="Helvetica-Bold",
    fontSize=9,
    textColor=C_PASS_GREEN,
    backColor=C_PASS_BG,
    borderPad=4,
    leftIndent=12,
    spaceBefore=3,
    spaceAfter=6,
)
STYLE_SUMMARY_PASS = _style(
    "SummaryPass",
    fontName="Helvetica-Bold",
    fontSize=10,
    textColor=C_PASS_GREEN,
    alignment=TA_CENTER,
    spaceBefore=6,
    spaceAfter=6,
)


# ── Canvas callbacks ──────────────────────────────────────────────────────────

def on_first_page(canvas, doc):
    """Title page: top and bottom dark bands with wordmark / date."""
    canvas.saveState()

    # ── Top band ─────────────────────────────────────────────────────────────
    canvas.setFillColor(C_DARK_BLUE)
    canvas.rect(0, PAGE_H - TOP_BAND_H, PAGE_W, TOP_BAND_H, fill=1, stroke=0)

    # Thin accent stripe below top band
    canvas.setFillColor(C_RULE)
    canvas.rect(0, PAGE_H - TOP_BAND_H - 3, PAGE_W, 3, fill=1, stroke=0)

    # Wordmark inside top band
    canvas.setFillColor(C_WHITE)
    canvas.setFont("Helvetica-Bold", 11)
    canvas.drawCentredString(PAGE_W / 2, PAGE_H - TOP_BAND_H + 10, "S T R U C T L A B")

    # ── Bottom band ───────────────────────────────────────────────────────────
    canvas.setFillColor(C_DARK_BLUE)
    canvas.rect(0, 0, PAGE_W, BOT_BAND_H, fill=1, stroke=0)

    canvas.setFillColor(C_RULE)
    canvas.rect(0, BOT_BAND_H, PAGE_W, 3, fill=1, stroke=0)

    canvas.setFillColor(C_WHITE)
    canvas.setFont("Helvetica", 8)
    canvas.drawCentredString(
        PAGE_W / 2, BOT_BAND_H / 2 - 4,
        "Phase 7  ·  StructLab vs OpenSeesPy  ·  May 2026",
    )

    canvas.restoreState()


def on_later_pages(canvas, doc):
    """Content pages: bottom accent line + page number footer."""
    canvas.saveState()

    canvas.setFillColor(C_DARK_BLUE)
    canvas.rect(0, 0, PAGE_W, BOT_BAND_H, fill=1, stroke=0)

    canvas.setFillColor(C_RULE)
    canvas.rect(0, BOT_BAND_H, PAGE_W, 2, fill=1, stroke=0)

    canvas.setFillColor(C_WHITE)
    canvas.setFont("Helvetica", 7.5)
    canvas.drawString(SIDE_MARGIN, BOT_BAND_H / 2 - 4,
                      "StructLab Phase 7 — Benchmark Report")
    canvas.drawRightString(
        PAGE_W - SIDE_MARGIN, BOT_BAND_H / 2 - 4,
        f"Page {canvas.getPageNumber()}",
    )

    canvas.restoreState()


# ── Line classifier ───────────────────────────────────────────────────────────

def _classify(line: str) -> str:
    s = line.strip()
    if s.startswith("###") or s.startswith("==="):
        return "section_border"
    if s.startswith("#  StructLab Phase"):
        return "section_title"
    if s.startswith("#") and s.endswith("#") and len(s) > 4:
        return "section_padding"
    if s.startswith("--- Case"):
        return "case"
    if "Analytical:" in s or "StructLab:" in s or "OpenSeesPy:" in s \
            or "Total applied" in s or "SL SumFy" in s:
        return "summary"
    if "Result: ALL PASS" in s:
        return "result_pass"
    if "All" in s and "cases PASSED" in s:
        return "all_pass"
    if s.startswith("---") or s.startswith("==="):
        return "divider"
    if "SL=" in s and "Ref=" in s and "err=" in s:
        return "row"
    if not s:
        return "blank"
    return "other"


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ── Title page flowables ──────────────────────────────────────────────────────

def _title_page_story() -> list:
    """Return flowables that make up a vertically centred title page."""
    avail_h = PAGE_H - TOP_MARGIN - BOT_MARGIN

    # Estimated height of the title block below:
    #   44pt text + spacers + HR + lines + stats box  ≈ 260 pt
    BLOCK_H = 260
    top_spacer = (avail_h - BLOCK_H) / 2

    items: list = [
        Spacer(1, top_spacer),

        # ── Product name ──────────────────────────────────────────────────────
        Paragraph("StructLab", STYLE_TP_MAIN),
        Spacer(1, 4 * mm),

        # ── Phase label ───────────────────────────────────────────────────────
        Paragraph("P H A S E  7", STYLE_TP_PHASE),
        Spacer(1, 2 * mm),
        Paragraph("Benchmark Report", STYLE_TP_REPORT),
        Spacer(1, 8 * mm),

        # ── Divider ───────────────────────────────────────────────────────────
        HRFlowable(width="70%", thickness=2, color=C_RULE, hAlign="CENTER"),
        Spacer(1, 8 * mm),

        # ── Comparison detail ─────────────────────────────────────────────────
        Paragraph("StructLab  vs  OpenSeesPy", STYLE_TP_VS),
        Spacer(1, 3 * mm),
        Paragraph(
            "Linear-Elastic Static Analysis · Direct Stiffness Method",
            STYLE_TP_SUB,
        ),
        Spacer(1, 10 * mm),

        # ── Pass summary badge ────────────────────────────────────────────────
        Paragraph(
            "9 Cases  ·  Beams  ·  Frames  ·  Trusses  ·  All PASS",
            STYLE_TP_STATS,
        ),
    ]
    return items


# ── Build full story ──────────────────────────────────────────────────────────

def build_story(txt_path: Path) -> list:
    lines = txt_path.read_text(encoding="utf-8", errors="replace").splitlines()

    story: list = _title_page_story()

    pending: list = []

    def flush():
        if pending:
            story.append(KeepTogether(pending[:]))
            pending.clear()

    i = 0
    while i < len(lines):
        line  = lines[i]
        kind  = _classify(line)

        if kind in ("section_border", "section_padding", "divider"):
            i += 1
            continue

        if kind == "section_title":
            flush()
            story.append(PageBreak())
            title_text = line.strip().strip("#").strip()
            story.append(Paragraph(_escape(title_text), STYLE_SECTION))
            story.append(HRFlowable(width="100%", thickness=1, color=C_RULE, spaceAfter=4))
            i += 1
            continue

        if kind == "case":
            flush()
            case_text = line.strip().strip("-").strip()
            pending.append(Paragraph(_escape(case_text), STYLE_CASE))
            i += 1
            continue

        if kind == "summary":
            pending.append(Paragraph(_escape(line.strip()), STYLE_SUMMARY_LINE))
            i += 1
            continue

        if kind == "row":
            raw = _escape(line.strip())
            raw = raw.replace("[PASS]", '<font color="#1e7a34"><b>[PASS]</b></font>')
            raw = raw.replace("[FAIL]", '<font color="#c0392b"><b>[FAIL]</b></font>')
            pending.append(Paragraph(raw, STYLE_ROW))
            i += 1
            continue

        if kind == "result_pass":
            pending.append(Paragraph("&#10003;  ALL PASS", STYLE_RESULT_PASS))
            i += 1
            continue

        if kind == "all_pass":
            flush()
            text = line.strip().strip("-").strip()
            story.append(Paragraph(_escape(text), STYLE_SUMMARY_PASS))
            story.append(HRFlowable(width="60%", thickness=1, color=C_RULE,
                                    hAlign="CENTER", spaceAfter=8))
            i += 1
            continue

        if kind == "blank":
            i += 1
            continue

        stripped = line.strip()
        if stripped:
            pending.append(Paragraph(_escape(stripped), STYLE_ROW))
        i += 1

    flush()
    return story


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    if not INPUT_TXT.exists():
        print(f"ERROR: input file not found: {INPUT_TXT}")
        return

    doc = SimpleDocTemplate(
        str(OUTPUT_PDF),
        pagesize=A4,
        leftMargin=SIDE_MARGIN,
        rightMargin=SIDE_MARGIN,
        topMargin=TOP_MARGIN,
        bottomMargin=BOT_MARGIN,
        title="StructLab Phase 7 Benchmark Report",
        author="StructLab",
    )

    story = build_story(INPUT_TXT)
    doc.build(story, onFirstPage=on_first_page, onLaterPages=on_later_pages)
    print(f"PDF written to:  {OUTPUT_PDF}")


if __name__ == "__main__":
    main()
