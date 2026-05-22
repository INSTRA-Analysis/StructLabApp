"""Professional benchmark PDF report generator for StructLab Phase 8.

Takes a list of BenchResult objects and produces a multi-page A4 PDF.

Structure:
  Page 1  — Cover page
  Page 2  — Executive summary table (all cases at a glance)
  Pages … — One section per category; each case: sketch + comparison table
  Last    — Methodology notes

Run standalone:
    python "Benchmark report/generate_report.py"

Or called programmatically:
    from generate_report import generate
    generate(results)  # returns PDF path
"""
from __future__ import annotations

import io
import os
import sys
from datetime import date
from pathlib import Path
from typing import List

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, HRFlowable, Image, KeepTogether,
    NextPageTemplate, PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle,
)

REPORT_DIR = Path(__file__).parent
OUTPUT_PDF  = REPORT_DIR / f"StructLab_Benchmark_Report_{date.today().strftime('%Y-%m-%d')}.pdf"

# ── Colour palette ─────────────────────────────────────────────────────────────
C_NAVY     = colors.HexColor("#1a3a5c")
C_BLUE     = colors.HexColor("#2c5f8a")
C_SKY      = colors.HexColor("#6aafd6")
C_ACCENT   = colors.HexColor("#4a90c4")
C_GREEN    = colors.HexColor("#1e7a34")
C_GREEN_BG = colors.HexColor("#d4edda")
C_RED      = colors.HexColor("#c0392b")
C_RED_BG   = colors.HexColor("#fde8e6")
C_PALE_BG  = colors.HexColor("#e8f0f8")
C_ROW_ALT  = colors.HexColor("#f0f4f8")
C_RULE     = colors.HexColor("#4a90c4")
C_GREY     = colors.HexColor("#555566")
C_DARK     = colors.HexColor("#1a1a2e")
C_WHITE    = colors.white
C_LIGHT    = colors.HexColor("#f8fafc")

# ── Page geometry ──────────────────────────────────────────────────────────────
PW, PH    = A4
BAND_TOP  = 22 * mm
BAND_BOT  = 18 * mm
MARGIN_LR = 18 * mm
MARGIN_T  = BAND_TOP + 6 * mm
MARGIN_B  = BAND_BOT + 8 * mm

# ── Styles ─────────────────────────────────────────────────────────────────────

def _sty(name, **kw) -> ParagraphStyle:
    return ParagraphStyle(name, **kw)


STY_COVER_TITLE = _sty("CoverTitle", fontName="Helvetica-Bold", fontSize=42,
                        textColor=C_NAVY, alignment=TA_CENTER, leading=50, spaceAfter=0)
STY_COVER_SUB   = _sty("CoverSub",   fontName="Helvetica",     fontSize=13,
                        textColor=C_SKY,  alignment=TA_CENTER, leading=18, letterSpacing=2)
STY_COVER_BODY  = _sty("CoverBody",  fontName="Helvetica",     fontSize=10,
                        textColor=C_GREY, alignment=TA_CENTER, spaceAfter=0)
STY_COVER_BADGE = _sty("CoverBadge", fontName="Helvetica-Bold", fontSize=11,
                        textColor=C_GREEN, backColor=C_GREEN_BG,
                        borderPad=8, alignment=TA_CENTER)
STY_COVER_VS    = _sty("CoverVs",    fontName="Helvetica-Bold", fontSize=14,
                        textColor=C_BLUE, alignment=TA_CENTER)

STY_SECTION_HDR = _sty("SectionHdr", fontName="Helvetica-Bold", fontSize=13,
                        textColor=C_WHITE, backColor=C_NAVY,
                        borderPad=7, spaceBefore=10, spaceAfter=4)
STY_CASE_TITLE  = _sty("CaseTitle",  fontName="Helvetica-Bold", fontSize=10,
                        textColor=C_NAVY, spaceBefore=8, spaceAfter=3)
STY_CASE_DESC   = _sty("CaseDesc",   fontName="Helvetica",      fontSize=8.5,
                        textColor=C_GREY, spaceAfter=4, leading=12)
STY_SUMMARY     = _sty("Summary",    fontName="Helvetica",      fontSize=8,
                        textColor=C_DARK, spaceAfter=2)
STY_PASS_BADGE  = _sty("PassBadge",  fontName="Helvetica-Bold", fontSize=9,
                        textColor=C_GREEN, backColor=C_GREEN_BG, borderPad=4,
                        spaceBefore=3, spaceAfter=6)
STY_FAIL_BADGE  = _sty("FailBadge",  fontName="Helvetica-Bold", fontSize=9,
                        textColor=C_RED,   backColor=C_RED_BG,   borderPad=4,
                        spaceBefore=3, spaceAfter=6)
STY_TOC_SECTION = _sty("TocSection", fontName="Helvetica-Bold", fontSize=10,
                        textColor=C_NAVY, spaceBefore=6, spaceAfter=1)
STY_TOC_CASE    = _sty("TocCase",    fontName="Helvetica",      fontSize=9,
                        textColor=C_DARK, leftIndent=16, spaceAfter=1)
STY_NOTES       = _sty("Notes",      fontName="Helvetica",      fontSize=8.5,
                        textColor=C_GREY, spaceAfter=3, leading=13)
STY_TABLE_HDR   = _sty("TblHdr",     fontName="Helvetica-Bold", fontSize=8,
                        textColor=C_WHITE, alignment=TA_CENTER)
STY_TABLE_BODY  = _sty("TblBody",    fontName="Helvetica",      fontSize=8,
                        textColor=C_DARK, alignment=TA_LEFT)
STY_TABLE_MONO  = _sty("TblMono",    fontName="Courier",        fontSize=7.5,
                        textColor=C_DARK, alignment=TA_RIGHT)
STY_SUMMARY_HDR = _sty("SumHdr",     fontName="Helvetica-Bold", fontSize=10,
                        textColor=C_NAVY, spaceBefore=14, spaceAfter=4)


# ── Canvas callbacks ───────────────────────────────────────────────────────────

def _cover_canvas(canvas, doc):
    canvas.saveState()
    # Top navy band
    canvas.setFillColor(C_NAVY)
    canvas.rect(0, PH - BAND_TOP, PW, BAND_TOP, fill=1, stroke=0)
    canvas.setFillColor(C_ACCENT)
    canvas.rect(0, PH - BAND_TOP - 2, PW, 2, fill=1, stroke=0)
    canvas.setFillColor(C_WHITE)
    canvas.setFont("Helvetica-Bold", 10)
    canvas.drawCentredString(PW / 2, PH - BAND_TOP + 7, "S T R U C T L A B")
    # Bottom band
    canvas.setFillColor(C_NAVY)
    canvas.rect(0, 0, PW, BAND_BOT, fill=1, stroke=0)
    canvas.setFillColor(C_ACCENT)
    canvas.rect(0, BAND_BOT, PW, 2, fill=1, stroke=0)
    canvas.setFillColor(C_WHITE)
    canvas.setFont("Helvetica", 8)
    canvas.drawCentredString(PW / 2, BAND_BOT / 2 - 4,
                             f"Phase 8  ·  Validation Report  ·  {date.today().strftime('%B %Y')}")
    canvas.restoreState()


def _content_canvas(canvas, doc):
    canvas.saveState()
    # Thin top accent bar
    canvas.setFillColor(C_NAVY)
    canvas.rect(0, PH - BAND_TOP, PW, BAND_TOP, fill=1, stroke=0)
    canvas.setFillColor(C_ACCENT)
    canvas.rect(0, PH - BAND_TOP - 2, PW, 2, fill=1, stroke=0)
    canvas.setFillColor(C_WHITE)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(MARGIN_LR, PH - BAND_TOP + 7, "StructLab")
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(PW - MARGIN_LR, PH - BAND_TOP + 7, "Benchmark & Validation Report")
    # Bottom footer
    canvas.setFillColor(C_NAVY)
    canvas.rect(0, 0, PW, BAND_BOT, fill=1, stroke=0)
    canvas.setFillColor(C_ACCENT)
    canvas.rect(0, BAND_BOT, PW, 2, fill=1, stroke=0)
    canvas.setFillColor(C_WHITE)
    canvas.setFont("Helvetica", 7.5)
    canvas.drawString(MARGIN_LR, BAND_BOT / 2 - 4, "StructLab — Direct Stiffness Method Engine")
    canvas.drawRightString(PW - MARGIN_LR, BAND_BOT / 2 - 4,
                           f"Page {canvas.getPageNumber()}")
    canvas.restoreState()


# ── Figure → ReportLab Image ───────────────────────────────────────────────────

def _fig_to_image(fig: plt.Figure, width_mm: float = 155) -> Image:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    img = Image(buf, width=width_mm * mm)
    img.hAlign = "LEFT"
    return img


# ── Comparison table ──────────────────────────────────────────────────────────

def _quantity_table(br) -> Table:
    from benchmarks.result import QuantityResult

    header = [
        Paragraph("Quantity", STY_TABLE_HDR),
        Paragraph("StructLab", STY_TABLE_HDR),
        Paragraph("Reference", STY_TABLE_HDR),
        Paragraph("Ref. type", STY_TABLE_HDR),
        Paragraph("Rel. error", STY_TABLE_HDR),
        Paragraph("Status", STY_TABLE_HDR),
    ]
    data = [header]

    for i, q in enumerate(br.quantities):
        err_str = f"{q.rel_error * 100:.4f}%"
        status_txt = "PASS" if q.passed else "FAIL"
        status_hex = "#1e7a34" if q.passed else "#c0392b"

        row = [
            Paragraph(f"{q.label} ({q.unit})", STY_TABLE_BODY),
            Paragraph(f"{q.structlab:.4f}", STY_TABLE_MONO),
            Paragraph(f"{q.reference:.4f}", STY_TABLE_MONO),
            Paragraph(q.reference_type, STY_TABLE_BODY),
            Paragraph(err_str, STY_TABLE_MONO),
            Paragraph(f"<font color='{status_hex}'>{status_txt}</font>", STY_TABLE_BODY),
        ]
        data.append(row)

    col_widths = [58*mm, 22*mm, 22*mm, 25*mm, 20*mm, 14*mm]
    tbl = Table(data, colWidths=col_widths, repeatRows=1)

    style = [
        ("BACKGROUND", (0, 0), (-1, 0), C_NAVY),
        ("TEXTCOLOR",  (0, 0), (-1, 0), C_WHITE),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, 0), 8),
        ("ALIGN",      (0, 0), (-1, -1), "LEFT"),
        ("ALIGN",      (1, 0), (4, -1), "RIGHT"),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_WHITE, C_ROW_ALT]),
        ("LINEBELOW", (0, 0), (-1, 0), 1, C_ACCENT),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, C_ACCENT),
        ("GRID",      (0, 0), (-1, -1), 0.3, C_SKY),
    ]

    # Colour the Status column per row
    for i, q in enumerate(br.quantities):
        bg = C_GREEN_BG if q.passed else C_RED_BG
        style.append(("BACKGROUND", (5, i+1), (5, i+1), bg))

    tbl.setStyle(TableStyle(style))
    return tbl


# ── Executive summary table ───────────────────────────────────────────────────

def _summary_table(results) -> Table:
    header = [
        Paragraph("ID",        STY_TABLE_HDR),
        Paragraph("Title",     STY_TABLE_HDR),
        Paragraph("Category",  STY_TABLE_HDR),
        Paragraph("Reference", STY_TABLE_HDR),
        Paragraph("Q",         STY_TABLE_HDR),
        Paragraph("Max err",   STY_TABLE_HDR),
        Paragraph("Status",    STY_TABLE_HDR),
    ]
    data = [header]
    for r in results:
        refs = " + ".join(set(q.reference_type for q in r.quantities))
        status_txt = "ALL PASS" if r.passed else f"{r.n_total - r.n_pass} FAIL"
        row = [
            Paragraph(r.case_id,          STY_TABLE_BODY),
            Paragraph(r.title[:48],        STY_TABLE_BODY),
            Paragraph(r.category,          STY_TABLE_BODY),
            Paragraph(refs,                STY_TABLE_BODY),
            Paragraph(str(r.n_total),      STY_TABLE_MONO),
            Paragraph(f"{r.max_error_pct:.4f}%", STY_TABLE_MONO),
            Paragraph(status_txt,          STY_TABLE_BODY),
        ]
        data.append(row)

    col_widths = [12*mm, 58*mm, 24*mm, 32*mm, 8*mm, 18*mm, 18*mm]
    tbl = Table(data, colWidths=col_widths, repeatRows=1)

    style = [
        ("BACKGROUND",    (0, 0), (-1, 0), C_NAVY),
        ("TEXTCOLOR",     (0, 0), (-1, 0), C_WHITE),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 8),
        ("ALIGN",         (0, 0), (-1, -1), "LEFT"),
        ("ALIGN",         (4, 0), (6, -1), "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [C_WHITE, C_ROW_ALT]),
        ("LINEBELOW",     (0, 0), (-1, 0), 1, C_ACCENT),
        ("GRID",          (0, 0), (-1, -1), 0.3, C_SKY),
    ]
    for i, r in enumerate(results):
        bg = C_GREEN_BG if r.passed else C_RED_BG
        style.append(("BACKGROUND", (6, i+1), (6, i+1), bg))
        style.append(("TEXTCOLOR",  (6, i+1), (6, i+1),
                       C_GREEN if r.passed else C_RED))
        style.append(("FONTNAME",   (6, i+1), (6, i+1), "Helvetica-Bold"))
    tbl.setStyle(TableStyle(style))
    return tbl


# ── Cover page ────────────────────────────────────────────────────────────────

_COVER_SCREENSHOT = Path(r"C:\Users\imeng\OneDrive\Desktop\Screenshot 2026-05-18 161123.png")


def _cover_story(results) -> list:
    n_cases = len(results)
    n_pass  = sum(r.passed for r in results)
    n_q     = sum(r.n_total for r in results)
    n_qpass = sum(r.n_pass  for r in results)

    cats = ["2D Beams", "2D Frames", "2D Trusses", "3D Frames"]
    cat_counts = {c: sum(1 for r in results if r.category == c) for c in cats}

    # Available content width for the screenshot
    content_w = PW - 2 * MARGIN_LR
    img_w = content_w * 0.92   # 92% of text width

    items: list = [
        Spacer(1, 8*mm),
        Paragraph("StructLab", STY_COVER_TITLE),
        Spacer(1, 3*mm),
        Paragraph("P H A S E  8", STY_COVER_SUB),
        Spacer(1, 1*mm),
        Paragraph("Benchmark &amp; Validation Report", _sty("R", fontName="Helvetica-Bold",
            fontSize=17, textColor=C_BLUE, alignment=TA_CENTER, leading=22)),
        Spacer(1, 5*mm),
        HRFlowable(width="65%", thickness=2, color=C_ACCENT, hAlign="CENTER"),
        Spacer(1, 5*mm),
        Paragraph("StructLab  vs  OpenSeesPy  ·  PyNite  ·  Analytical", STY_COVER_VS),
        Spacer(1, 2*mm),
        Paragraph("Linear-Elastic Static Analysis · Direct Stiffness Method",
                  STY_COVER_BODY),
        Spacer(1, 2*mm),
        Paragraph(
            f"2D Beams ({cat_counts['2D Beams']})  ·  "
            f"2D Frames ({cat_counts['2D Frames']})  ·  "
            f"2D Trusses ({cat_counts['2D Trusses']})  ·  "
            f"3D Frames ({cat_counts['3D Frames']})",
            STY_COVER_BODY),
        Spacer(1, 6*mm),
        Paragraph(
            f"{n_pass}/{n_cases} Cases PASS  ·  {n_qpass}/{n_q} Quantities ≤ 0.10% Error",
            STY_COVER_BADGE,
        ),
        Spacer(1, 7*mm),
    ]

    # App screenshot
    if _COVER_SCREENSHOT.exists():
        from PIL import Image as PILImage
        with PILImage.open(_COVER_SCREENSHOT) as _pil:
            _iw, _ih = _pil.size
        img_h = img_w * (_ih / _iw)
        img = Image(str(_COVER_SCREENSHOT), width=img_w, height=img_h)
        img.hAlign = "CENTER"
        # Wrap in a single-cell table to draw a thin border / drop-shadow effect
        tbl = Table([[img]], colWidths=[img_w + 4])
        tbl.setStyle(TableStyle([
            ("BOX",        (0, 0), (-1, -1), 0.5, C_ACCENT),
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#0d1117")),
            ("ALIGN",      (0, 0), (-1, -1), "CENTER"),
            ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",    (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING",   (0, 0), (-1, -1), 3),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 3),
        ]))
        items.append(tbl)
        items.append(Spacer(1, 5*mm))

    items.append(Paragraph(
        f"Generated {date.today().strftime('%d %B %Y')} · Python 3.12 · PyQt6",
        STY_COVER_BODY,
    ))
    return items


# ── Methodology page ──────────────────────────────────────────────────────────

def _methodology_story() -> list:
    items: list = [
        Paragraph("Methodology &amp; Reference Tools", STY_SECTION_HDR),
        HRFlowable(width="100%", thickness=1, color=C_ACCENT, spaceAfter=6),
        Paragraph(
            "<b>StructLab Engine</b>",
            _sty("m1", fontName="Helvetica-Bold", fontSize=9, textColor=C_NAVY, spaceAfter=2),
        ),
        Paragraph(
            "StructLab implements the Direct Stiffness Method (DSM) for 2D linear-elastic "
            "static analysis. All structure types — beams, frames, and trusses — are solved "
            "by a single unified 3-DOF/node engine (dx, dy, θ) with element type controlled "
            "by moment-release flags (pin_i, pin_j) on FrameElement objects. The global "
            "stiffness matrix is assembled by scatter-add; boundary conditions are applied "
            "by DOF elimination; the system [K]{d}={F} is solved by SciPy sparse LU "
            "factorisation. Internal forces are recovered by superposition of element "
            "stiffness and fixed-end force vectors.",
            STY_NOTES,
        ),
        Spacer(1, 4*mm),
        Paragraph("<b>Reference Tool 1 — OpenSeesPy</b>",
                  _sty("m2", fontName="Helvetica-Bold", fontSize=9, textColor=C_NAVY, spaceAfter=2)),
        Paragraph(
            "OpenSeesPy (openseespy package) provides the 2D reference for beams, frames, "
            "and trusses. elasticBeamColumn elements are used for frame members; Truss "
            "elements for pin-pin members. The same geometric and material properties are "
            "specified in both tools. Node tags and element tags are 1-indexed in OpenSeesPy.",
            STY_NOTES,
        ),
        Spacer(1, 4*mm),
        Paragraph("<b>Reference Tool 2 — PyNiteFEA</b>",
                  _sty("m3", fontName="Helvetica-Bold", fontSize=9, textColor=C_NAVY, spaceAfter=2)),
        Paragraph(
            "PyNiteFEA (v2.4.1, JWock82) provides the 3D frame reference. It is an "
            "independent Python 3D FEM library using 12-DOF beam elements (Euler–Bernoulli). "
            "Material, section, and loading properties are mirrored exactly in both tools. "
            "Load combinations are used to access result dictionaries.",
            STY_NOTES,
        ),
        Spacer(1, 4*mm),
        Paragraph("<b>Analytical Solutions</b>",
                  _sty("m4", fontName="Helvetica-Bold", fontSize=9, textColor=C_NAVY, spaceAfter=2)),
        Paragraph(
            "Where closed-form solutions exist (simply supported beams, propped cantilevers, "
            "fixed-fixed beams, Pratt/Warren truss reactions), analytical values are used as "
            "the primary reference. Analytical solutions are derived from standard structural "
            "analysis textbooks and the 3-moment theorem / force method for indeterminate beams.",
            STY_NOTES,
        ),
        Spacer(1, 4*mm),
        Paragraph("<b>Pass Criterion</b>",
                  _sty("m5", fontName="Helvetica-Bold", fontSize=9, textColor=C_NAVY, spaceAfter=2)),
        Paragraph(
            "A quantity is marked PASS if the relative error against the reference is ≤ 0.10%. "
            "Relative error = |StructLab − Reference| / |Reference|. "
            "For quantities with near-zero reference (|Ref| < 10⁻¹²), absolute error is used. "
            "A case PASSES only when every quantity comparison passes.",
            STY_NOTES,
        ),
        Spacer(1, 4*mm),
        Paragraph("<b>Sign Conventions</b>",
                  _sty("m6", fontName="Helvetica-Bold", fontSize=9, textColor=C_NAVY, spaceAfter=2)),
        Paragraph(
            "Deflections are reported as positive-downward (sagging convention). "
            "Moments are positive-sagging (bottom fibre in tension). "
            "Reactions are positive-upward. Axial forces are positive-tension. "
            "All load magnitudes in the benchmark tables are positive values; "
            "direction is noted in the case description.",
            STY_NOTES,
        ),
    ]
    return items


# ── Section flowables ──────────────────────────────────────────────────────────

def _case_flowables(br) -> list:
    items: list = []
    items.append(Paragraph(f"{br.case_id} — {br.title}", STY_CASE_TITLE))
    items.append(Paragraph(br.description, STY_CASE_DESC))

    # Geometry sketch
    if br.sketch_func is not None:
        try:
            fig = br.sketch_func()
            items.append(_fig_to_image(fig, width_mm=155))
        except Exception as e:
            items.append(Paragraph(f"[Sketch unavailable: {e}]", STY_NOTES))

    items.append(Spacer(1, 2*mm))

    # Quantity comparison table
    if br.quantities:
        items.append(_quantity_table(br))

    # Pass/fail badge
    if br.passed:
        items.append(Paragraph(
            f"✓  ALL {br.n_total} QUANTITIES PASS  —  max error {br.max_error_pct:.4f}%",
            STY_PASS_BADGE,
        ))
    else:
        items.append(Paragraph(
            f"✗  {br.n_total - br.n_pass}/{br.n_total} QUANTITIES FAILED  —  max error {br.max_error_pct:.4f}%",
            STY_FAIL_BADGE,
        ))

    return items


def _section_flowables(category: str, results) -> list:
    cat_results = [r for r in results if r.category == category]
    if not cat_results:
        return []

    items: list = [
        PageBreak(),
        Paragraph(category, STY_SECTION_HDR),
        HRFlowable(width="100%", thickness=1, color=C_ACCENT, spaceAfter=6),
    ]
    for r in cat_results:
        items.append(KeepTogether(_case_flowables(r)))
        items.append(Spacer(1, 6*mm))
    return items


# ── Main generate function ────────────────────────────────────────────────────

def generate(results, output_path: Path | None = None) -> str:
    if output_path is None:
        output_path = OUTPUT_PDF

    # Build document with two page templates: cover + content
    doc = BaseDocTemplate(
        str(output_path),
        pagesize=A4,
        title="StructLab Phase 8 — Benchmark Report",
        author="StructLab",
        subject="FEM Validation vs OpenSeesPy, PyNite, Analytical",
    )

    content_frame = Frame(
        MARGIN_LR, MARGIN_B,
        PW - 2 * MARGIN_LR, PH - MARGIN_T - MARGIN_B,
        id="content",
    )
    doc.addPageTemplates([
        PageTemplate(id="cover",   frames=[content_frame], onPage=_cover_canvas),
        PageTemplate(id="content", frames=[content_frame], onPage=_content_canvas),
    ])

    story: list = []

    # ── Cover ─────────────────────────────────────────────────────────────────
    story += _cover_story(results)
    story.append(NextPageTemplate("content"))
    story.append(PageBreak())

    # ── Executive summary ─────────────────────────────────────────────────────
    n_cases = len(results)
    n_pass  = sum(r.passed for r in results)
    n_q     = sum(r.n_total for r in results)

    story.append(Paragraph("Executive Summary", STY_SECTION_HDR))
    story.append(HRFlowable(width="100%", thickness=1, color=C_ACCENT, spaceAfter=4))
    story.append(Paragraph(
        f"This report presents the results of {n_cases} independent benchmark cases "
        f"validating the StructLab Direct Stiffness Method engine against OpenSeesPy, "
        f"PyNiteFEA, and closed-form analytical solutions. All {n_q} compared quantities "
        f"must have a relative error ≤ 0.10% to be marked PASS.",
        STY_CASE_DESC,
    ))
    story.append(Spacer(1, 3*mm))
    story.append(_summary_table(results))
    story.append(Spacer(1, 5*mm))
    overall_txt = (
        f"✓  {n_pass}/{n_cases} cases PASS — maximum error across all quantities: "
        f"{max(r.max_error_pct for r in results):.4f}%"
    ) if n_pass == n_cases else (
        f"✗  {n_cases - n_pass}/{n_cases} cases FAILED"
    )
    sty_badge = STY_PASS_BADGE if n_pass == n_cases else STY_FAIL_BADGE
    story.append(Paragraph(overall_txt, sty_badge))

    # ── Case sections ──────────────────────────────────────────────────────────
    for cat in ["2D Beams", "2D Frames", "2D Trusses", "3D Frames"]:
        story += _section_flowables(cat, results)

    # ── Methodology ────────────────────────────────────────────────────────────
    story.append(PageBreak())
    story += _methodology_story()

    doc.build(story)
    return str(output_path)


# ── Standalone entry point ────────────────────────────────────────────────────

def main() -> None:
    print("Running all benchmark cases...")
    from benchmarks.run_all import run_cases
    results = run_cases(verbose=True)

    print("\nGenerating PDF report...")
    out = generate(results)
    print(f"PDF written to: {out}")


if __name__ == "__main__":
    main()
