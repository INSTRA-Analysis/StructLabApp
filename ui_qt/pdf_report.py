"""PDF report generator for StructLab.

Produces a multi-page A4 PDF using matplotlib PdfPages.
Call generate_report() with the model state, rendered canvas image,
solve cache, and a human-readable report_basis label.
"""
from __future__ import annotations

import datetime
import math
from pathlib import Path
from typing import Any

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import FancyBboxPatch

from ui_qt.model_state import ModelState, SupportType

# ── Layout constants ──────────────────────────────────────────────────────────

_A4_W   = 8.27    # inches
_A4_H   = 11.69   # inches
_L      = 0.08    # left margin (figure fraction)
_R      = 0.92    # right margin (figure fraction)
_CYAN   = "#00ACC1"
_LIGHT  = "#f7f9fb"
_TEXT   = "#222222"
_GREY   = "#888888"
_GREEN  = "#4CAF50"
_RED    = "#f44336"
_AMBER  = "#FFA500"

_STATUS_COLORS = {
    "Preliminary": (_AMBER,   "white"),
    "For Review":  ("#2196F3", "white"),
    "Approved":    (_GREEN,    "white"),
}

_SLS_VERT_LIMIT  = 300   # L / 300  EN 1990 beam serviceability
_SLS_SWAY_LIMIT  = 300   # H / 300  sway


# ── Public entry point ────────────────────────────────────────────────────────

def generate_report(
    filepath: str,
    state: ModelState,
    canvas_image_path: str | None,
    solve_cache: dict | None,
    report_basis: str = "",
) -> None:
    """Write a multi-page A4 PDF to *filepath*.

    Parameters
    ----------
    filepath          : destination .pdf path
    state             : ModelState (geometry + metadata + loads)
    canvas_image_path : path to a PNG rendered from the canvas (may be None)
    solve_cache       : dict from _solve_engine(), or None if not solved
    report_basis      : human-readable label, e.g. "LC0: Dead (G)" or
                        "Combination: 1.35G + 1.5Q [ULS]"
    """
    meta     = state.metadata
    now      = datetime.datetime.now()
    date_str = now.strftime("%d %B %Y")

    with PdfPages(filepath) as pdf:
        _page_title(pdf, meta, date_str, report_basis)
        _page_model(pdf, meta, state, date_str, report_basis)
        if canvas_image_path and Path(canvas_image_path).exists():
            _page_diagram(pdf, meta, canvas_image_path, date_str, report_basis)
        _page_loads(pdf, meta, state, date_str, report_basis)
        if solve_cache is not None:
            _page_reactions(pdf, meta, state, solve_cache, date_str, report_basis)
            _page_checks(pdf, meta, state, solve_cache, date_str, report_basis)
            _page_member_forces(pdf, meta, state, solve_cache, date_str, report_basis)
            _page_diagrams(pdf, meta, state, solve_cache, date_str, report_basis)
        _page_signoff(pdf, meta, date_str, report_basis)

        info = pdf.infodict()
        info["Title"]        = meta.title
        info["Author"]       = meta.designer_name or "StructLab"
        info["Subject"]      = "Structural Analysis Report"
        info["Creator"]      = "StructLab V1.0.0 — Direct Stiffness Method"
        info["CreationDate"] = now


# ── Page / figure scaffolding ─────────────────────────────────────────────────

def _new_fig() -> tuple[plt.Figure, plt.Axes]:
    fig = plt.figure(figsize=(_A4_W, _A4_H))
    fig.patch.set_facecolor("white")
    ax  = fig.add_axes([0, 0, 1, 1])
    ax.set_axis_off()
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    return fig, ax


def _header(ax: plt.Axes, meta: Any, page_title: str,
            report_basis: str = "") -> None:
    fig = ax.figure

    # Cyan bar
    fig.add_artist(FancyBboxPatch(
        (0, 1 - 0.050), 1, 0.050,
        transform=fig.transFigure, boxstyle="square,pad=0",
        facecolor=_CYAN, edgecolor="none", zorder=5,
    ))
    fig.text(0.04, 1 - 0.025, "StructLab",
             fontsize=13, fontweight="bold", color="white",
             va="center", transform=fig.transFigure, zorder=6)
    fig.text(0.5, 1 - 0.025, meta.title,
             fontsize=10, color="white", va="center", ha="center",
             transform=fig.transFigure, zorder=6)
    ref = meta.project_ref or ""
    fig.text(0.96, 1 - 0.025, ref,
             fontsize=8, color="white", va="center", ha="right",
             transform=fig.transFigure, zorder=6)

    # Page heading
    fig.text(0.5, 1 - 0.075, page_title,
             fontsize=12, fontweight="bold", color=_TEXT,
             va="top", ha="center", transform=fig.transFigure)

    # Report basis sub-label
    if report_basis:
        fig.text(0.5, 1 - 0.100, report_basis,
                 fontsize=8, color=_GREY,
                 va="top", ha="center", transform=fig.transFigure)


def _footer(fig: plt.Figure, date_str: str, page_note: str = "") -> None:
    fig.add_artist(plt.Line2D(
        [_L, _R], [0.038, 0.038],
        transform=fig.transFigure, color="#cccccc", linewidth=0.8, zorder=5,
    ))
    fig.text(_L, 0.022, f"Generated: {date_str}  |  StructLab V1.0.0",
             fontsize=7, color=_GREY, va="center", transform=fig.transFigure)
    note = page_note or (
        "Results are for engineering review only — "
        "verify with a qualified engineer before use."
    )
    fig.text(_R, 0.022, note,
             fontsize=7, color=_GREY, va="center", ha="right",
             transform=fig.transFigure)


# ── Page 1: Title ─────────────────────────────────────────────────────────────

def _page_title(pdf: PdfPages, meta: Any, date_str: str,
                report_basis: str) -> None:
    fig, ax = _new_fig()

    # Brand
    fig.text(0.5, 0.82, "StructLab",
             fontsize=46, fontweight="bold", color=_CYAN,
             ha="center", va="center", transform=fig.transFigure)
    fig.text(0.5, 0.768, "2D Structural Analysis  —  Direct Stiffness Method",
             fontsize=10, color=_GREY, ha="center", va="center",
             transform=fig.transFigure)
    ax.axhline(0.745, xmin=0.10, xmax=0.90, color=_CYAN, linewidth=1.5)

    # Project info block
    rows = [
        ("Project Title",  meta.title),
        ("Project Ref",    meta.project_ref or "—"),
        ("Client",         meta.client      or "—"),
        ("Company",        meta.company     or "—"),
        ("Status",         meta.status),
        ("Date",           date_str),
    ]
    if report_basis:
        rows.append(("Report basis", report_basis))

    y0, dy = 0.71, 0.046
    for label, value in rows:
        fig.text(0.22, y0, label + ":",
                 fontsize=9, color=_GREY, ha="right", va="top",
                 transform=fig.transFigure)
        fig.text(0.24, y0, value,
                 fontsize=9, color=_TEXT, fontweight="bold", va="top",
                 transform=fig.transFigure)
        y0 -= dy

    # Status badge (top-right of info block)
    bg, fg = _STATUS_COLORS.get(meta.status, ("#999", "white"))
    fig.add_artist(FancyBboxPatch(
        (0.64, 0.695), 0.20, 0.034,
        transform=fig.transFigure, boxstyle="round,pad=0.005",
        facecolor=bg, edgecolor="none",
    ))
    fig.text(0.74, 0.712, meta.status,
             fontsize=9, color=fg, fontweight="bold",
             ha="center", va="center", transform=fig.transFigure)

    # Description
    if meta.description:
        desc_y = y0 - 0.01
        ax.axhline(desc_y, xmin=0.10, xmax=0.90, color="#dddddd", linewidth=0.7)
        fig.text(0.5, desc_y - 0.012, "Project Description",
                 fontsize=9, fontweight="bold", color=_GREY,
                 ha="center", va="top", transform=fig.transFigure)
        fig.text(0.5, desc_y - 0.035, meta.description,
                 fontsize=8.5, color=_TEXT, ha="center", va="top",
                 wrap=True, transform=fig.transFigure, multialignment="center")

    _footer(fig, date_str,
            page_note="CONFIDENTIAL — Not for construction without approval")
    pdf.savefig(fig, bbox_inches="tight", dpi=150)
    plt.close(fig)


def _signature_block(fig: plt.Figure, meta: Any, y_top: float) -> None:
    """Three-column Designed / Reviewed / Approved block."""
    ax = fig.get_axes()[0]
    ax.axhline(y_top + 0.008, xmin=0.10, xmax=0.90,
               color="#dddddd", linewidth=0.7)
    fig.text(0.5, y_top + 0.002, "Sign-off",
             fontsize=9, fontweight="bold", color=_GREY,
             ha="center", va="bottom", transform=fig.transFigure)

    cols = [
        ("Designed by",  meta.designer_name),
        ("Reviewed by",  meta.reviewer_name),
        ("Approved by",  meta.approver_name),
    ]
    xs = [0.18, 0.50, 0.82]
    for (role, name), x in zip(cols, xs):
        # Roles and names sit 0.028 / 0.052 below the separator (was 0.012 / 0.034)
        fig.text(x, y_top - 0.028, role,
                 fontsize=8, color=_GREY, ha="center", va="top",
                 transform=fig.transFigure)
        fig.text(x, y_top - 0.050, name or "—",
                 fontsize=9, color=_TEXT, fontweight="bold",
                 ha="center", va="top", transform=fig.transFigure)
        # Signature line
        sig = fig.add_axes([x - 0.11, y_top - 0.108, 0.22, 0.001])
        sig.set_facecolor("#aaaaaa")
        sig.set_xticks([]); sig.set_yticks([])
        fig.text(x, y_top - 0.118, "Signature",
                 fontsize=7, color=_GREY, ha="center", va="top",
                 transform=fig.transFigure)
        fig.text(x, y_top - 0.140, "Date: _______________",
                 fontsize=7, color=_GREY, ha="center", va="top",
                 transform=fig.transFigure)


# ── Page 2: Model description ─────────────────────────────────────────────────

def _page_model(pdf: PdfPages, meta: Any, state: ModelState,
                date_str: str, report_basis: str) -> None:
    fig, ax = _new_fig()
    _header(ax, meta, "Model Description", report_basis)
    _footer(fig, date_str)

    y = 0.860

    y = _section_label(fig, "Nodes", y)
    y = _draw_table(fig, ["ID", "X (m)", "Y (m)", "Support"],
                    [[str(n.id), f"{n.x:.3f}", f"{n.y:.3f}",
                      n.support_type.name]
                     for n in state.nodes],
                    y)
    y -= 0.018

    y = _section_label(fig, "Members", y)
    y = _draw_table(fig,
                    ["ID", "i", "j", "Type", "E (GPa)", "A (cm²)", "I (cm⁴)"],
                    [[str(m.id), str(m.node_i), str(m.node_j),
                      m.element_type.name,
                      f"{m.E/1e9:.1f}", f"{m.A*1e4:.2f}",
                      f"{m.I*1e8:.2f}"]
                     for m in state.members],
                    y)
    y -= 0.018

    y = _section_label(fig, "Load Cases", y)
    _draw_table(fig, ["ID", "Name", "Category", "Self-weight"],
                [[str(lc.id), lc.name, lc.category,
                  "Yes" if lc.include_self_weight else "No"]
                 for lc in state.load_cases],
                y)

    pdf.savefig(fig, bbox_inches="tight", dpi=150)
    plt.close(fig)


# ── Page 3: Structural diagram ────────────────────────────────────────────────

def _page_diagram(pdf: PdfPages, meta: Any, image_path: str,
                  date_str: str, report_basis: str) -> None:
    from matplotlib.image import imread
    fig, ax = _new_fig()
    _header(ax, meta, "Structural Model", report_basis)
    _footer(fig, date_str)

    img    = imread(image_path)
    img_h  = img.shape[0]
    img_w  = img.shape[1]
    aspect = img_h / img_w  # height / width

    # Available area below header (top ~0.115) above footer (bottom ~0.055)
    avail_w  = _R - _L        # figure-fraction width
    avail_h  = 0.855 - 0.055  # figure-fraction height (header to footer)
    img_frac = min(avail_w, avail_h / aspect)
    img_frac_h = img_frac * aspect
    left   = 0.5 - img_frac / 2
    bottom = 0.055 + (avail_h - img_frac_h) / 2

    img_ax = fig.add_axes([left, bottom, img_frac, img_frac_h])
    img_ax.imshow(img)
    img_ax.set_axis_off()

    pdf.savefig(fig, bbox_inches="tight", dpi=150)
    plt.close(fig)


# ── Page 4: Loading summary ───────────────────────────────────────────────────

def _page_loads(pdf: PdfPages, meta: Any, state: ModelState,
                date_str: str, report_basis: str) -> None:
    fig, ax = _new_fig()
    _header(ax, meta, "Loading Summary", report_basis)
    _footer(fig, date_str)
    y = 0.860

    for lc in state.load_cases:
        y = _section_label(fig, f"LC{lc.id}: {lc.name}  [{lc.category}]", y)

        # Node loads — skip if all zero
        nl_rows = []
        for nid, nl in lc.node_loads.items():
            if not nl.is_zero():
                nl_rows.append([
                    str(nid),
                    f"{nl.fx/1e3:.3f}"     if nl.fx     else "—",
                    f"{nl.fy/1e3:.3f}"     if nl.fy     else "—",
                    f"{nl.moment/1e3:.3f}" if nl.moment  else "—",
                ])
        if nl_rows:
            y = _mini_label(fig, "Node Loads", y)
            y = _draw_table(fig,
                            ["Node", "Fx (kN)", "Fy (kN)", "M (kN·m)"],
                            nl_rows, y)

        # Member loads — include qx columns
        ml_rows = []
        for mid, ml in lc.member_loads.items():
            if ml.is_zero():
                continue
            w_s,  w_e  = ml.net("w")
            qx_s, qx_e = ml.net("qx")
            ml_rows.append([
                str(mid),
                f"{w_s/1e3:.3f}"   if w_s   else "—",
                f"{w_e/1e3:.3f}"   if w_e   else "—",
                f"{qx_s/1e3:.3f}"  if qx_s  else "—",
                f"{qx_e/1e3:.3f}"  if qx_e  else "—",
                f"{len(ml.point_loads)} pt" if ml.point_loads else "—",
            ])
        if ml_rows:
            y = _mini_label(fig, "Member Loads", y)
            y = _draw_table(fig,
                            ["Mbr", "w_i (kN/m)", "w_j (kN/m)",
                             "qx_i (kN/m)", "qx_j (kN/m)", "Pt loads"],
                            ml_rows, y,
                            col_widths=[0.07, 0.148, 0.148, 0.148, 0.148, 0.100])

        if not nl_rows and not ml_rows:
            fig.text(_L + 0.02, y - 0.010, "(No loads defined in this case)",
                     fontsize=8.5, color=_GREY, va="top",
                     transform=fig.transFigure)
            y -= 0.035

        y -= 0.012
        if y < 0.12:
            break

    pdf.savefig(fig, bbox_inches="tight", dpi=150)
    plt.close(fig)


# ── Page 5: Support reactions ─────────────────────────────────────────────────

def _page_reactions(pdf: PdfPages, meta: Any, state: ModelState,
                    cache: dict, date_str: str, report_basis: str) -> None:
    fig, ax = _new_fig()
    _header(ax, meta, "Support Reactions", report_basis)
    _footer(fig, date_str)
    y = 0.860

    reactions = cache.get("reactions")
    if reactions is None:
        fig.text(0.5, 0.5, "No reaction data available.",
                 ha="center", va="center", fontsize=11, color=_GREY,
                 transform=fig.transFigure)
        pdf.savefig(fig, bbox_inches="tight", dpi=150)
        plt.close(fig)
        return

    # Reactions table
    rows     = []
    sum_rx   = 0.0
    sum_ry   = 0.0
    for n in state.nodes:
        if n.support_type == SupportType.FREE:
            continue
        rx = float(reactions[n.id * 3])
        ry = float(reactions[n.id * 3 + 1])
        rm = float(reactions[n.id * 3 + 2])
        sum_rx += rx
        sum_ry += ry
        rows.append([str(n.id), n.support_type.name,
                     f"{rx/1e3:.4f}", f"{ry/1e3:.4f}", f"{rm/1e3:.4f}"])

    y = _draw_table(fig, ["Node", "Support", "Rx (kN)", "Ry (kN)", "M (kN·m)"],
                    rows, y)

    # ── Equilibrium check ─────────────────────────────────────────────────────
    # Applied loads = total of all equivalent nodal forces assembled by the solver.
    # F[0::3] = Fx, F[1::3] = Fy at every DOF in the model (incl. sub-nodes).
    # For a correct DSM solution: ΣR + ΣF_applied = 0 to machine precision.
    y -= 0.025
    try:
        from solver.assembler import Assembler
        model = cache["model"]
        asm   = Assembler(model)
        F     = asm.global_force_vector(model.elements)
        fx_applied = float(np.sum(F[0::3]))
        fy_applied = float(np.sum(F[1::3]))
        res_x      = abs(sum_rx + fx_applied)
        res_y      = abs(sum_ry + fy_applied)
        tol        = max(1.0, abs(sum_ry) * 1e-4)
        ok_x       = res_x < tol
        ok_y       = res_y < tol

        # Applied load row
        fig.text(_L, y,
                 f"Applied:   ΣFx = {fx_applied/1e3:.3f} kN    "
                 f"ΣFy = {fy_applied/1e3:.3f} kN",
                 fontsize=8.5, color=_GREY, va="top",
                 transform=fig.transFigure)
        y -= 0.022
        fig.text(_L, y,
                 f"Reactions: ΣRx = {sum_rx/1e3:.3f} kN    "
                 f"ΣRy = {sum_ry/1e3:.3f} kN",
                 fontsize=8.5, color=_GREY, va="top",
                 transform=fig.transFigure)
        y -= 0.022

        # Residual check row
        cx = _GREEN if ok_x else _RED
        cy = _GREEN if ok_y else _RED
        fig.text(_L, y,
                 f"Residual:  |ΣFx| = {res_x/1e3:.2e} kN",
                 fontsize=8.5, color=cx, va="top",
                 transform=fig.transFigure)
        fig.text(0.48, y,
                 f"|ΣFy| = {res_y/1e3:.2e} kN",
                 fontsize=8.5, color=cy, va="top",
                 transform=fig.transFigure)
        y -= 0.022

        verdict = "✓  Global equilibrium satisfied" if (ok_x and ok_y) else \
                  "⚠  Equilibrium residual exceeds tolerance"
        fig.text(0.5, y, verdict,
                 fontsize=9, fontweight="bold",
                 color=_GREEN if (ok_x and ok_y) else _RED,
                 ha="center", va="top", transform=fig.transFigure)

    except Exception as exc:
        fig.text(_L, y, f"Equilibrium check skipped: {exc}",
                 fontsize=8, color=_GREY, va="top",
                 transform=fig.transFigure)

    pdf.savefig(fig, bbox_inches="tight", dpi=150)
    plt.close(fig)


# ── Page 6: Serviceability checks ────────────────────────────────────────────

def _page_checks(pdf: PdfPages, meta: Any, state: ModelState,
                 cache: dict, date_str: str, report_basis: str) -> None:
    disps = cache.get("displacements")
    if disps is None:
        return

    fig, ax = _new_fig()
    _header(ax, meta, "Serviceability Checks", report_basis)
    _footer(fig, date_str)
    y = 0.860

    # Build node-coordinate map and connectivity lookup
    node_map   = {n.id: n for n in state.nodes}
    free_nodes = [n for n in state.nodes if n.support_type == SupportType.FREE]

    # For each free node, find the longest connected member (used as reference L)
    member_len: dict[int, float] = {}   # member id → length
    node_members: dict[int, list] = {}  # node id → list of member lengths
    for m in state.members:
        ni = node_map[m.node_i]
        nj = node_map[m.node_j]
        L  = math.hypot(nj.x - ni.x, nj.y - ni.y)
        member_len[m.id] = L
        node_members.setdefault(m.node_i, []).append(L)
        node_members.setdefault(m.node_j, []).append(L)

    def _ref_len(nid: int) -> float:
        return max(node_members.get(nid, [1.0]))

    # Collect deflections for all free nodes
    vert_data  = []   # (|dy|, node_id, L_ref)
    horiz_data = []   # (|dx|, node_id, L_ref)

    for n in free_nodes:
        dx = float(disps[n.id * 3])
        dy = float(disps[n.id * 3 + 1])
        L  = _ref_len(n.id)
        vert_data.append( (abs(dy), n.id, L) )
        horiz_data.append((abs(dx), n.id, L) )

    if not vert_data:
        fig.text(0.5, 0.5, "No free nodes — checks not applicable.",
                 ha="center", va="center", fontsize=10, color=_GREY,
                 transform=fig.transFigure)
        pdf.savefig(fig, bbox_inches="tight", dpi=150)
        plt.close(fig)
        return

    # ── Deflection summary table ──────────────────────────────────────────────
    y = _section_label(fig, "Nodal Displacements", y)

    disp_rows = []
    for n in free_nodes:
        dx  = float(disps[n.id * 3])
        dy  = float(disps[n.id * 3 + 1])
        rot = float(disps[n.id * 3 + 2])
        disp_rows.append([
            str(n.id),
            f"{dx*1e3:.3f}",
            f"{dy*1e3:.3f}",
            f"{math.degrees(rot):.4f}",
        ])
    y = _draw_table(fig,
                    ["Node", "dx (mm)", "dy (mm)", "θ (°)"],
                    disp_rows, y,
                    col_widths=[0.10, 0.20, 0.20, 0.22])
    y -= 0.020

    # ── Vertical (transverse) deflection check ────────────────────────────────
    y = _section_label(fig, "Vertical Deflection Check  (limit L / 300)", y)

    max_dy, ctrl_nid_v, ctrl_L_v = max(vert_data, key=lambda t: t[0])
    ratio_v = (ctrl_L_v / max_dy) if max_dy > 1e-9 else float("inf")
    pass_v  = max_dy < ctrl_L_v / _SLS_VERT_LIMIT
    tag_v   = "PASS ✓" if pass_v else "FAIL ✗"
    col_v   = _GREEN   if pass_v else _RED

    y = _draw_table(fig,
                    ["Max |dy|", "Node", "Ref. length L", "δ/L",
                     "Limit", "Result"],
                    [[f"{max_dy*1e3:.2f} mm", str(ctrl_nid_v),
                      f"{ctrl_L_v:.3f} m",
                      f"L/{ratio_v:.0f}" if ratio_v < 1e6 else "—",
                      f"L/{_SLS_VERT_LIMIT}",
                      tag_v]],
                    y,
                    col_widths=[0.16, 0.10, 0.18, 0.14, 0.12, 0.12],
                    highlight_col=5, highlight_color=col_v)
    y -= 0.020

    # ── Horizontal (sway) deflection check ────────────────────────────────────
    y = _section_label(fig, "Lateral Sway Check  (limit H / 300)", y)

    max_dx, ctrl_nid_h, ctrl_L_h = max(horiz_data, key=lambda t: t[0])
    ratio_h = (ctrl_L_h / max_dx) if max_dx > 1e-9 else float("inf")
    pass_h  = max_dx < ctrl_L_h / _SLS_SWAY_LIMIT
    tag_h   = "PASS ✓" if pass_h else "FAIL ✗"
    col_h   = _GREEN   if pass_h else _RED

    y = _draw_table(fig,
                    ["Max |dx|", "Node", "Ref. height H", "δ/H",
                     "Limit", "Result"],
                    [[f"{max_dx*1e3:.2f} mm", str(ctrl_nid_h),
                      f"{ctrl_L_h:.3f} m",
                      f"H/{ratio_h:.0f}" if ratio_h < 1e6 else "—",
                      f"H/{_SLS_SWAY_LIMIT}",
                      tag_h]],
                    y,
                    col_widths=[0.16, 0.10, 0.18, 0.14, 0.12, 0.12],
                    highlight_col=5, highlight_color=col_h)
    y -= 0.020

    # ── Disclaimer ────────────────────────────────────────────────────────────
    fig.text(0.5, y - 0.005,
             "Reference length = longest member connected to the controlling node.  "
             "Checks are SLS only (linear-elastic).",
             fontsize=7.5, color=_GREY, ha="center", va="top",
             transform=fig.transFigure)

    pdf.savefig(fig, bbox_inches="tight", dpi=150)
    plt.close(fig)


# ── Page 7: Member end forces ─────────────────────────────────────────────────

def _page_member_forces(pdf: PdfPages, meta: Any, state: ModelState,
                        cache: dict, date_str: str, report_basis: str) -> None:
    fig, ax = _new_fig()
    _header(ax, meta, "Member End Forces", report_basis)
    _footer(fig, date_str)
    y = 0.860

    member_results = cache.get("member_results", [])
    if not member_results:
        fig.text(0.5, 0.5, "No member force data available.",
                 ha="center", va="center", fontsize=11, color=_GREY,
                 transform=fig.transFigure)
        pdf.savefig(fig, bbox_inches="tight", dpi=150)
        plt.close(fig)
        return

    headers = ["Mbr", "N_i (kN)", "V_i (kN)", "M_i (kN·m)",
               "N_j (kN)", "V_j (kN)", "M_j (kN·m)"]
    rows = [
        [str(r.element_id),
         f"{r.N_i/1e3:.3f}", f"{r.V_i/1e3:.3f}", f"{r.M_i/1e3:.3f}",
         f"{r.N_j/1e3:.3f}", f"{r.V_j/1e3:.3f}", f"{r.M_j/1e3:.3f}"]
        for r in member_results
    ]
    _draw_table(fig, headers, rows, y,
                col_widths=[0.06, 0.13, 0.13, 0.15, 0.13, 0.13, 0.15])

    pdf.savefig(fig, bbox_inches="tight", dpi=150)
    plt.close(fig)


# ── Pages 8+: SFD / BMD per member ───────────────────────────────────────────

def _page_diagrams(pdf: PdfPages, meta: Any, state: ModelState,
                   cache: dict, date_str: str, report_basis: str) -> None:
    member_el_map = cache.get("member_el_map", [])
    model         = cache.get("model")
    displacements = cache.get("displacements")
    if not member_el_map or model is None or displacements is None:
        return

    from solver.postprocessor import Postprocessor

    pp          = Postprocessor(model.elements, model.element_loads, displacements)
    sfd_bmd_map = {r.element_id: r for r in pp.sfd_bmd(n_points=30)}
    el_map      = {el.id: el for el in model.elements}

    for member, sub_ids in zip(state.members, member_el_map):
        x_parts, V_parts, M_parts = [], [], []
        x_offset = 0.0
        for eid in sub_ids:
            r  = sfd_bmd_map.get(eid)
            el = el_map.get(eid)
            if r is None or el is None:
                continue
            x_parts.append(r.x + x_offset)
            V_parts.append(r.V)
            M_parts.append(r.M)
            x_offset += el.length

        if not x_parts:
            continue

        x_arr = np.concatenate(x_parts)
        V_arr = np.concatenate(V_parts)
        M_arr = np.concatenate(M_parts)

        fig, axes = plt.subplots(2, 1, figsize=(_A4_W, _A4_H * 0.42))
        fig.patch.set_facecolor("white")
        fig.suptitle(
            f"Member {member.id}   "
            f"(node {member.node_i} → node {member.node_j})   "
            f"| {report_basis}",
            fontsize=10, fontweight="bold", color=_TEXT,
        )

        ax_sfd = axes[0]
        ax_sfd.fill_between(x_arr, V_arr / 1e3, alpha=0.20, color="#2196F3")
        ax_sfd.plot(x_arr, V_arr / 1e3, color="#2196F3", linewidth=1.2)
        ax_sfd.axhline(0, color="#555", linewidth=0.7)
        ax_sfd.set_ylabel("V (kN)", fontsize=9)
        ax_sfd.set_title("Shear Force Diagram", fontsize=9)
        ax_sfd.grid(True, alpha=0.25)

        ax_bmd = axes[1]
        M_plot = -M_arr / 1e3           # flip: sagging below baseline
        ax_bmd.fill_between(x_arr, M_plot, alpha=0.20, color=_GREEN)
        ax_bmd.plot(x_arr, M_plot, color=_GREEN, linewidth=1.2)
        ax_bmd.axhline(0, color="#555", linewidth=0.7)
        ax_bmd.invert_yaxis()
        ax_bmd.set_ylabel("M (kN·m)", fontsize=9)
        ax_bmd.set_xlabel("x (m)", fontsize=9)
        ax_bmd.set_title("Bending Moment Diagram  (sagging ↓)", fontsize=9)
        ax_bmd.grid(True, alpha=0.25)

        fig.tight_layout(rect=[0, 0, 1, 0.94])
        pdf.savefig(fig, bbox_inches="tight", dpi=150)
        plt.close(fig)


# ── Last page: sign-off ───────────────────────────────────────────────────────

def _page_signoff(pdf: PdfPages, meta: Any, date_str: str,
                  report_basis: str) -> None:
    fig, ax = _new_fig()
    _header(ax, meta, "Document Sign-off", report_basis)
    _footer(fig, date_str,
            page_note="This report is generated by StructLab V1.0.0")

    fig.text(0.5, 0.84,
             "The following engineers confirm that this analysis has been",
             fontsize=10, color=_TEXT, ha="center", va="top",
             transform=fig.transFigure)
    fig.text(0.5, 0.815,
             "independently reviewed and is suitable for the stated purpose.",
             fontsize=10, color=_TEXT, ha="center", va="top",
             transform=fig.transFigure)

    # Signature block: y_top=0.70 — sits below the two intro lines with room to breathe
    _signature_block(fig, meta, y_top=0.70)

    # Disclaimer box — fixed height, text rendered inside axes so it can't overflow
    import textwrap
    disc = fig.add_axes([0.08, 0.07, 0.84, 0.24])
    disc.set_facecolor(_LIGHT)
    disc.set_xticks([]); disc.set_yticks([])
    for spine in disc.spines.values():
        spine.set_edgecolor("#cccccc"); spine.set_linewidth(0.8)

    disc.text(0.03, 0.93, "DISCLAIMER",
              fontsize=8.5, fontweight="bold", color="#333333",
              va="top", transform=disc.transAxes)

    body = (
        "This report has been produced using StructLab, a 2D linear-elastic structural "
        "analysis tool based on the Direct Stiffness Method (DSM). Results are valid "
        "for linear-elastic static conditions only. The engineer of record is responsible "
        "for verifying that all assumptions, boundary conditions, and load cases are "
        "appropriate for the actual structure. StructLab output does not constitute a "
        "structural design and must not be used for construction without independent "
        "verification by a suitably qualified and registered structural engineer."
    )
    disc.text(0.03, 0.72, textwrap.fill(body, width=115),
              fontsize=7.5, color="#444444",
              va="top", transform=disc.transAxes)

    disc.text(0.03, 0.06, "© StructLab V1.0.0 — Direct Stiffness Method Engine",
              fontsize=7, color="#888888",
              va="bottom", transform=disc.transAxes)

    pdf.savefig(fig, bbox_inches="tight", dpi=150)
    plt.close(fig)


# ── Table helpers ─────────────────────────────────────────────────────────────

def _section_label(fig: plt.Figure, text: str, y: float) -> float:
    fig.text(_L, y, text,
             fontsize=10, fontweight="bold", color=_CYAN,
             va="top", transform=fig.transFigure)
    return y - 0.028


def _mini_label(fig: plt.Figure, text: str, y: float) -> float:
    fig.text(_L + 0.02, y, text,
             fontsize=8.5, color=_GREY, va="top",
             transform=fig.transFigure)
    return y - 0.020


def _draw_table(
    fig: plt.Figure,
    headers: list[str],
    rows: list[list[str]],
    y_top: float,
    col_widths: list[float] | None = None,
    highlight_col: int | None = None,
    highlight_color: str = _GREEN,
) -> float:
    """Render a simple text table.  Returns y position after last row."""
    row_h   = 0.025
    n_cols  = len(headers)
    total_w = _R - _L
    if col_widths is None:
        col_widths = [total_w / n_cols] * n_cols

    # Normalise col_widths so they sum exactly to total_w
    cw_sum = sum(col_widths)
    col_widths = [c / cw_sum * total_w for c in col_widths]

    y = y_top

    # Header row
    x = _L
    for i, (h, cw) in enumerate(zip(headers, col_widths)):
        fig.add_artist(FancyBboxPatch(
            (x, y - row_h), cw - 0.002, row_h,
            transform=fig.transFigure, boxstyle="square,pad=0",
            facecolor=_CYAN, edgecolor="none",
        ))
        fig.text(x + cw / 2, y - row_h / 2, h,
                 fontsize=8, color="white", fontweight="bold",
                 ha="center", va="center", transform=fig.transFigure)
        x += cw
    y -= row_h

    # Data rows
    for row_idx, row in enumerate(rows):
        x        = _L
        bg_color = "#f0f4f8" if row_idx % 2 == 0 else "white"
        for i, (cell, cw) in enumerate(zip(row, col_widths)):
            cell_bg = highlight_color if i == highlight_col else bg_color
            cell_fg = "white" if i == highlight_col else _TEXT
            fig.add_artist(FancyBboxPatch(
                (x, y - row_h), cw - 0.002, row_h,
                transform=fig.transFigure, boxstyle="square,pad=0",
                facecolor=cell_bg, edgecolor="#e0e0e0", linewidth=0.5,
            ))
            fig.text(x + cw / 2, y - row_h / 2, str(cell),
                     fontsize=8, color=cell_fg,
                     ha="center", va="center", transform=fig.transFigure)
            x += cw
        y -= row_h
        if y < 0.08:
            break

    return y - 0.004
