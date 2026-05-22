"""Geometry sketch helpers for benchmark cases.

Each function returns a matplotlib Figure showing the structural geometry,
supports, loads, and key dimensions. Figures are embedded in the PDF report.
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np

# ── Shared style constants ────────────────────────────────────────────────────

MEMBER_COLOR   = "#1a3a5c"
SUPPORT_COLOR  = "#2c5f8a"
LOAD_COLOR     = "#c0392b"
REACTION_COLOR = "#1e7a34"
NODE_COLOR     = "#f39c12"
DIM_COLOR      = "#555566"
BG_COLOR       = "#f8fafc"
GRID_COLOR     = "#dce8f5"

FIG_W, FIG_H = 5.2, 2.6   # inches — sized to fit PDF column


def _fig() -> tuple[plt.Figure, plt.Axes]:
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
    fig.patch.set_facecolor(BG_COLOR)
    ax.set_facecolor(BG_COLOR)
    ax.set_aspect("equal")
    ax.axis("off")
    return fig, ax


def _pin_support(ax: plt.Axes, x: float, y: float, size: float = 0.18) -> None:
    triangle = plt.Polygon(
        [[x, y], [x - size, y - size * 1.5], [x + size, y - size * 1.5]],
        closed=True, facecolor=SUPPORT_COLOR, edgecolor=SUPPORT_COLOR, zorder=3,
    )
    ax.add_patch(triangle)
    ax.plot([x - size * 1.3, x + size * 1.3], [y - size * 1.5, y - size * 1.5],
            color=SUPPORT_COLOR, lw=1.5, zorder=3)


def _roller_support(ax: plt.Axes, x: float, y: float, size: float = 0.18) -> None:
    triangle = plt.Polygon(
        [[x, y], [x - size, y - size * 1.4], [x + size, y - size * 1.4]],
        closed=True, facecolor="white", edgecolor=SUPPORT_COLOR, lw=1.5, zorder=3,
    )
    ax.add_patch(triangle)
    circle = plt.Circle((x, y - size * 1.4 - size * 0.35), size * 0.25,
                         facecolor=SUPPORT_COLOR, edgecolor=SUPPORT_COLOR, zorder=3)
    ax.add_patch(circle)


def _fixed_wall(ax: plt.Axes, x: float, y_bot: float, height: float,
                side: str = "left") -> None:
    """Hatch rectangle representing a fixed wall."""
    rect = mpatches.FancyBboxPatch(
        (x - 0.05, y_bot), 0.1, height,
        boxstyle="square,pad=0", facecolor=SUPPORT_COLOR,
        edgecolor=SUPPORT_COLOR, zorder=3,
    )
    ax.add_patch(rect)
    # Hatching lines
    n = int(height / 0.15) + 2
    for i in range(n):
        yy = y_bot + i * 0.15
        dx = 0.12 if side == "left" else -0.12
        ax.plot([x - 0.05 + (0 if side == "left" else 0.1),
                 x - 0.05 + (0 if side == "left" else 0.1) - dx],
                [yy, yy + 0.08],
                color=SUPPORT_COLOR, lw=0.8, alpha=0.7, zorder=3)


def _udl_arrow(ax: plt.Axes, x0: float, x1: float, y: float,
               label: str = "w", n: int = 7) -> None:
    """Draw UDL arrows above the beam."""
    top = y + 0.28
    ax.plot([x0, x1], [top, top], color=LOAD_COLOR, lw=1.5, zorder=4)
    xs = np.linspace(x0, x1, n)
    for xi in xs:
        ax.annotate("", xy=(xi, y), xytext=(xi, top),
                    arrowprops=dict(arrowstyle="-|>", color=LOAD_COLOR, lw=1.0),
                    zorder=4)
    mx = (x0 + x1) / 2
    ax.text(mx, top + 0.06, label, color=LOAD_COLOR, ha="center", va="bottom",
            fontsize=7.5, fontweight="bold")


def _point_load(ax: plt.Axes, x: float, y: float, downward: bool = True,
                label: str = "P") -> None:
    dy = -0.4 if downward else 0.4
    ax.annotate("", xy=(x, y), xytext=(x, y - dy),
                arrowprops=dict(arrowstyle="-|>", color=LOAD_COLOR, lw=1.5),
                zorder=4)
    ax.text(x, y - dy - 0.06 if downward else y - dy + 0.06,
            label, color=LOAD_COLOR, ha="center",
            va="top" if downward else "bottom", fontsize=7.5, fontweight="bold")


def _lateral_load(ax: plt.Axes, x: float, y: float, direction: int = 1,
                  label: str = "H") -> None:
    """Horizontal (lateral) point load arrow."""
    dx = 0.4 * direction
    ax.annotate("", xy=(x, y), xytext=(x - dx, y),
                arrowprops=dict(arrowstyle="-|>", color=LOAD_COLOR, lw=1.5),
                zorder=4)
    ax.text(x - dx - 0.06 * direction, y, label,
            color=LOAD_COLOR, ha="right" if direction > 0 else "left",
            va="center", fontsize=7.5, fontweight="bold")


def _dim(ax: plt.Axes, x0: float, x1: float, y: float, label: str) -> None:
    """Horizontal dimension annotation."""
    ax.annotate("", xy=(x1, y), xytext=(x0, y),
                arrowprops=dict(arrowstyle="<->", color=DIM_COLOR, lw=0.8),
                zorder=2)
    ax.text((x0 + x1) / 2, y - 0.12, label, color=DIM_COLOR,
            ha="center", va="top", fontsize=6.5)


def _vdim(ax: plt.Axes, x: float, y0: float, y1: float, label: str) -> None:
    """Vertical dimension annotation."""
    ax.annotate("", xy=(x, y1), xytext=(x, y0),
                arrowprops=dict(arrowstyle="<->", color=DIM_COLOR, lw=0.8),
                zorder=2)
    ax.text(x + 0.1, (y0 + y1) / 2, label, color=DIM_COLOR,
            ha="left", va="center", fontsize=6.5)


def _node(ax: plt.Axes, x: float, y: float) -> None:
    ax.plot(x, y, "o", color=NODE_COLOR, ms=4, zorder=5)


def _beam(ax: plt.Axes, x0: float, y0: float, x1: float, y1: float) -> None:
    ax.plot([x0, x1], [y0, y1], color=MEMBER_COLOR, lw=3, solid_capstyle="round", zorder=2)


def _label_node(ax: plt.Axes, x: float, y: float, label: str,
                dx: float = 0.0, dy: float = 0.15) -> None:
    ax.text(x + dx, y + dy, label, color=DIM_COLOR, ha="center", va="bottom", fontsize=6)


# ── Case sketch factories ────────────────────────────────────────────────────


def sketch_b1() -> plt.Figure:
    """B1: Simply supported beam, mid-span point load."""
    fig, ax = _fig()
    L = 4.0
    _beam(ax, 0, 0, L, 0)
    _pin_support(ax, 0, 0)
    _roller_support(ax, L, 0)
    _point_load(ax, L / 2, 0, label="P")
    _node(ax, 0, 0); _node(ax, L / 2, 0); _node(ax, L, 0)
    _dim(ax, 0, L / 2, -0.55, "L/2"); _dim(ax, L / 2, L, -0.55, "L/2")
    ax.set_xlim(-0.5, L + 0.5); ax.set_ylim(-1.1, 0.9)
    ax.set_title("B1 — Simply Supported Beam, Mid-span Point Load",
                 fontsize=8, color=MEMBER_COLOR, pad=4)
    fig.tight_layout()
    return fig


def sketch_b2() -> plt.Figure:
    """B2: Simply supported beam, UDL."""
    fig, ax = _fig()
    L = 4.0
    _beam(ax, 0, 0, L, 0)
    _pin_support(ax, 0, 0)
    _roller_support(ax, L, 0)
    _udl_arrow(ax, 0, L, 0, label="w")
    _node(ax, 0, 0); _node(ax, L, 0)
    _dim(ax, 0, L, -0.55, "L")
    ax.set_xlim(-0.5, L + 0.5); ax.set_ylim(-1.1, 0.9)
    ax.set_title("B2 — Simply Supported Beam, UDL", fontsize=8, color=MEMBER_COLOR, pad=4)
    fig.tight_layout()
    return fig


def sketch_b3() -> plt.Figure:
    """B3: Propped cantilever, mid-span point load."""
    fig, ax = _fig()
    L = 4.0
    _beam(ax, 0, 0, L, 0)
    _fixed_wall(ax, 0, -0.5, 1.0)
    _roller_support(ax, L, 0)
    _point_load(ax, L / 2, 0, label="P")
    _node(ax, 0, 0); _node(ax, L / 2, 0); _node(ax, L, 0)
    _dim(ax, 0, L / 2, -0.55, "L/2"); _dim(ax, L / 2, L, -0.55, "L/2")
    ax.set_xlim(-0.5, L + 0.5); ax.set_ylim(-1.1, 0.9)
    ax.set_title("B3 — Propped Cantilever, Mid-span Point Load",
                 fontsize=8, color=MEMBER_COLOR, pad=4)
    fig.tight_layout()
    return fig


def sketch_b4() -> plt.Figure:
    """B4: Propped cantilever, UDL."""
    fig, ax = _fig()
    L = 4.0
    _beam(ax, 0, 0, L, 0)
    _fixed_wall(ax, 0, -0.5, 1.0)
    _roller_support(ax, L, 0)
    _udl_arrow(ax, 0, L, 0, label="w")
    _node(ax, 0, 0); _node(ax, L, 0)
    _dim(ax, 0, L, -0.55, "L")
    ax.set_xlim(-0.5, L + 0.5); ax.set_ylim(-1.1, 0.9)
    ax.set_title("B4 — Propped Cantilever, UDL", fontsize=8, color=MEMBER_COLOR, pad=4)
    fig.tight_layout()
    return fig


def sketch_b5() -> plt.Figure:
    """B5: 2-span continuous beam, UDL on both spans."""
    fig, ax = _fig()
    L = 3.0
    _beam(ax, 0, 0, L, 0); _beam(ax, L, 0, 2 * L, 0)
    _pin_support(ax, 0, 0); _roller_support(ax, L, 0); _roller_support(ax, 2 * L, 0)
    _udl_arrow(ax, 0, 2 * L, 0, label="w", n=11)
    for x in (0, L, 2 * L):
        _node(ax, x, 0)
    _dim(ax, 0, L, -0.55, "L"); _dim(ax, L, 2 * L, -0.55, "L")
    ax.set_xlim(-0.5, 2 * L + 0.5); ax.set_ylim(-1.1, 0.9)
    ax.set_title("B5 — 2-span Continuous Beam, UDL", fontsize=8, color=MEMBER_COLOR, pad=4)
    fig.tight_layout()
    return fig


def sketch_b6() -> plt.Figure:
    """B6: 3-span continuous beam, UDL."""
    fig, ax = _fig()
    L = 2.5
    for k in range(3):
        _beam(ax, k * L, 0, (k + 1) * L, 0)
    _pin_support(ax, 0, 0)
    for k in (1, 2):
        _roller_support(ax, k * L, 0)
    _roller_support(ax, 3 * L, 0)
    _udl_arrow(ax, 0, 3 * L, 0, label="w", n=13)
    for k in range(4):
        _node(ax, k * L, 0)
    _dim(ax, 0, L, -0.55, "L"); _dim(ax, L, 2 * L, -0.55, "L"); _dim(ax, 2 * L, 3 * L, -0.55, "L")
    ax.set_xlim(-0.5, 3 * L + 0.5); ax.set_ylim(-1.1, 0.9)
    ax.set_title("B6 — 3-span Continuous Beam, UDL", fontsize=8, color=MEMBER_COLOR, pad=4)
    fig.tight_layout()
    return fig


def sketch_b7() -> plt.Figure:
    """B7: Fixed-fixed beam, UDL."""
    fig, ax = _fig()
    L = 4.0
    _beam(ax, 0, 0, L, 0)
    _fixed_wall(ax, 0, -0.5, 1.0)
    _fixed_wall(ax, L, -0.5, 1.0, side="right")
    _udl_arrow(ax, 0, L, 0, label="w")
    _node(ax, 0, 0); _node(ax, L, 0)
    _dim(ax, 0, L, -0.55, "L")
    ax.set_xlim(-0.5, L + 0.5); ax.set_ylim(-1.1, 0.9)
    ax.set_title("B7 — Fixed-Fixed Beam, UDL", fontsize=8, color=MEMBER_COLOR, pad=4)
    fig.tight_layout()
    return fig


def sketch_f1() -> plt.Figure:
    """F1: Portal frame, lateral point load."""
    fig, ax = _fig()
    W, H = 3.0, 2.5
    _beam(ax, 0, 0, 0, H)       # left col
    _beam(ax, W, 0, W, H)       # right col
    _beam(ax, 0, H, W, H)       # beam
    _fixed_wall(ax, 0, -0.3, 0.6)
    _fixed_wall(ax, W, -0.3, 0.6, side="right")
    _lateral_load(ax, 0, H, direction=1, label="H")
    for pt in [(0, 0), (0, H), (W, 0), (W, H)]:
        _node(ax, *pt)
    _dim(ax, 0, W, -0.5, "L"); _vdim(ax, -0.4, 0, H, "H")
    ax.set_xlim(-0.8, W + 0.6); ax.set_ylim(-0.9, H + 0.5)
    ax.set_title("F1 — Portal Frame, Lateral Point Load",
                 fontsize=8, color=MEMBER_COLOR, pad=4)
    fig.tight_layout()
    return fig


def sketch_f2() -> plt.Figure:
    """F2: 2-storey portal frame, gravity loads."""
    fig, ax = _fig()
    W, H = 3.0, 1.8
    for iy in range(3):
        y = iy * H
        if iy < 2:
            _beam(ax, 0, y, 0, y + H)  # left col
            _beam(ax, W, y, W, y + H)  # right col
        _beam(ax, 0, y, W, y)           # floor/beam
    _fixed_wall(ax, 0, -0.3, 0.6)
    _fixed_wall(ax, W, -0.3, 0.6, side="right")
    for iy in (1, 2):
        _udl_arrow(ax, 0, W, iy * H, label="w", n=7)
    for iy in range(3):
        for x in (0, W):
            _node(ax, x, iy * H)
    _dim(ax, 0, W, -0.4, "L"); _vdim(ax, -0.4, 0, H, "h")
    ax.set_xlim(-0.8, W + 0.6); ax.set_ylim(-0.7, 2 * H + 0.5)
    ax.set_title("F2 — 2-storey Frame, Gravity Loads",
                 fontsize=8, color=MEMBER_COLOR, pad=4)
    fig.tight_layout()
    return fig


def sketch_f3() -> plt.Figure:
    """F3: 2-bay portal frame, gravity + lateral load."""
    fig, ax = _fig()
    bays = [0.0, 3.0, 5.5]; H = 2.5
    for x in bays:
        _beam(ax, x, 0, x, H)
        _fixed_wall(ax, x, -0.3, 0.6, side="right" if x == bays[-1] else "left")
    for i in range(len(bays) - 1):
        _beam(ax, bays[i], H, bays[i + 1], H)
    _udl_arrow(ax, bays[0], bays[1], H, label="w", n=7)
    _lateral_load(ax, 0, H, direction=1, label="H")
    for x in bays:
        _node(ax, x, 0); _node(ax, x, H)
    _dim(ax, bays[0], bays[1], -0.5, "L₁"); _dim(ax, bays[1], bays[2], -0.5, "L₂")
    _vdim(ax, -0.5, 0, H, "H")
    ax.set_xlim(-0.8, bays[-1] + 0.5); ax.set_ylim(-0.9, H + 0.6)
    ax.set_title("F3 — 2-bay Frame, Gravity + Lateral Loads",
                 fontsize=8, color=MEMBER_COLOR, pad=4)
    fig.tight_layout()
    return fig


def sketch_t1() -> plt.Figure:
    """T1: Pratt truss (5 panels)."""
    fig, ax = _fig()
    n = 5; P = 1.5; H = 1.0
    # Bottom chord
    for i in range(n):
        _beam(ax, i * P, 0, (i + 1) * P, 0)
    # Top chord
    for i in range(n):
        _beam(ax, i * P, H, (i + 1) * P, H)
    # Verticals
    for i in range(1, n):
        _beam(ax, i * P, 0, i * P, H)
    # Diagonals (Pratt: lean toward midspan)
    for i in range(n // 2):
        _beam(ax, i * P, H, (i + 1) * P, 0)
    for i in range(n // 2 + 1, n):
        _beam(ax, i * P, 0, (i + 1) * P, H)
    _beam(ax, n // 2 * P, H, (n // 2 + 1) * P, 0)

    _pin_support(ax, 0, 0); _roller_support(ax, n * P, 0)
    # Panel point loads
    for i in range(1, n):
        _point_load(ax, i * P, 0, label="P" if i == 1 else "")
    _dim(ax, 0, n * P, -0.55, f"{n}×L")
    ax.set_xlim(-0.5, n * P + 0.5); ax.set_ylim(-1.0, H + 0.5)
    ax.set_title("T1 — Pratt Truss, Panel Point Loads", fontsize=8, color=MEMBER_COLOR, pad=4)
    fig.tight_layout()
    return fig


def sketch_t2() -> plt.Figure:
    """T2: Simply supported truss (Warren), tip load."""
    fig, ax = _fig()
    n = 4; P = 1.5; H = 1.0
    # Bottom chord
    for i in range(n):
        _beam(ax, i * P, 0, (i + 1) * P, 0)
    # Top chord (Warren: no verticals, diagonals alternate)
    for i in range(n):
        if i % 2 == 0:
            _beam(ax, i * P, 0, (i + 1) * P, H)
            _beam(ax, (i + 1) * P, H, (i + 2) * P, 0)
    for i in range(1, n):
        if i % 2 == 1:
            _beam(ax, i * P, 0, i * P, H)  # keep some verticals for Warren-with-verticals
    _pin_support(ax, 0, 0); _roller_support(ax, n * P, 0)
    _point_load(ax, n // 2 * P, 0, label="P")
    _dim(ax, 0, n * P, -0.55, "L")
    ax.set_xlim(-0.5, n * P + 0.5); ax.set_ylim(-1.0, H + 0.5)
    ax.set_title("T2 — Warren Truss, Mid-span Point Load", fontsize=8, color=MEMBER_COLOR, pad=4)
    fig.tight_layout()
    return fig


def _beam3d(ax, nodes: dict, i: str, j: str, lw: float = 2.5, col: str = MEMBER_COLOR) -> None:
    """Draw a 3D beam projected to 2D isometric view (simple)."""
    xi, yi, zi = nodes[i]
    xj, yj, zj = nodes[j]
    # Simple 2D projection: x_screen = x - y*cos30, y_screen = z + y*sin30
    def proj(x, y, z):
        return x - y * 0.5, z + y * 0.35
    si = proj(xi, yi, zi)
    sj = proj(xj, yj, zj)
    ax.plot([si[0], sj[0]], [si[1], sj[1]], color=col, lw=lw,
            solid_capstyle="round", zorder=2)


def sketch_3d1() -> plt.Figure:
    """3D-1: 3D cantilever column, tip point load in Z."""
    fig, ax = _fig()
    H = 4.0
    # Single column along Z
    ax.plot([0, 0], [0, H], color=MEMBER_COLOR, lw=3, zorder=2)
    _fixed_wall(ax, 0, -0.3, 0.6)
    # Tip load in Z (upward in 2D sketch = Z direction)
    _point_load(ax, 0, H, downward=False, label="Fz")
    _node(ax, 0, 0); _node(ax, 0, H)
    _vdim(ax, 0.25, 0, H, "L")
    ax.set_xlim(-0.8, 1.0); ax.set_ylim(-0.8, H + 0.6)
    ax.set_title("3D-1 — Cantilever Column, Tip Load (Z)", fontsize=8, color=MEMBER_COLOR, pad=4)
    fig.tight_layout()
    return fig


def sketch_3d2() -> plt.Figure:
    """3D-2: 3D cantilever beam, tip load in Y."""
    fig, ax = _fig()
    L = 4.0
    ax.plot([0, L], [0, 0], color=MEMBER_COLOR, lw=3, zorder=2)
    _fixed_wall(ax, 0, -0.4, 0.8)
    _point_load(ax, L, 0, label="Fy")
    _node(ax, 0, 0); _node(ax, L, 0)
    _dim(ax, 0, L, -0.55, "L")
    ax.set_xlim(-0.5, L + 0.5); ax.set_ylim(-1.1, 0.9)
    ax.set_title("3D-2 — Cantilever Beam, Tip Load (Y)", fontsize=8, color=MEMBER_COLOR, pad=4)
    fig.tight_layout()
    return fig


def sketch_3d3() -> plt.Figure:
    """3D-3: 3D simply supported beam, UDL in Z."""
    fig, ax = _fig()
    L = 4.0
    ax.plot([0, L], [0, 0], color=MEMBER_COLOR, lw=3, zorder=2)
    _pin_support(ax, 0, 0); _roller_support(ax, L, 0)
    _udl_arrow(ax, 0, L, 0, label="w (Z-dir)")
    _node(ax, 0, 0); _node(ax, L, 0)
    _dim(ax, 0, L, -0.55, "L")
    ax.set_xlim(-0.5, L + 0.5); ax.set_ylim(-1.1, 0.9)
    ax.set_title("3D-3 — Simply Supported Beam, UDL (Z)", fontsize=8, color=MEMBER_COLOR, pad=4)
    fig.tight_layout()
    return fig


def _iso_proj(x, y, z):
    """Simple oblique projection for 3D sketches."""
    sx = x + y * 0.4
    sy = z + y * 0.2
    return sx, sy


def sketch_3d4() -> plt.Figure:
    """3D-4: Space frame — 2-storey, 1-bay each direction."""
    fig, ax = _fig()
    pts = {
        "A": (0, 0, 0), "B": (3, 0, 0), "C": (3, 3, 0), "D": (0, 3, 0),
        "E": (0, 0, 3), "F": (3, 0, 3), "G": (3, 3, 3), "H": (0, 3, 3),
        "I": (0, 0, 6), "J": (3, 0, 6), "K": (3, 3, 6), "L": (0, 3, 6),
    }
    cols = [("A", "E"), ("B", "F"), ("C", "G"), ("D", "H"),
            ("E", "I"), ("F", "J"), ("G", "K"), ("H", "L")]
    beams = [("E", "F"), ("F", "G"), ("G", "H"), ("H", "E"),
             ("I", "J"), ("J", "K"), ("K", "L"), ("L", "I")]
    for i, j in cols:
        x0, y0 = _iso_proj(*pts[i]); x1, y1 = _iso_proj(*pts[j])
        ax.plot([x0, x1], [y0, y1], color=MEMBER_COLOR, lw=2, alpha=0.8, zorder=2)
    for i, j in beams:
        x0, y0 = _iso_proj(*pts[i]); x1, y1 = _iso_proj(*pts[j])
        ax.plot([x0, x1], [y0, y1], color="#2c5f8a", lw=1.8, alpha=0.7, zorder=2)
    for k, v in pts.items():
        if "A" <= k <= "D":
            sx, sy = _iso_proj(*v)
            ax.plot(sx, sy, "s", color=SUPPORT_COLOR, ms=5, zorder=5)
    ax.set_xlim(-0.5, 5); ax.set_ylim(-0.5, 7)
    ax.set_title("3D-4 — 2-storey Space Frame", fontsize=8, color=MEMBER_COLOR, pad=4)
    ax.set_aspect("equal")
    fig.tight_layout()
    return fig


def sketch_3d5() -> plt.Figure:
    """3D-5: L-shaped 3D frame."""
    fig, ax = _fig()
    pts = {
        "A": (0, 0, 0), "B": (3, 0, 0), "C": (3, 3, 0),
        "D": (0, 0, 3), "E": (3, 0, 3), "F": (3, 3, 3),
    }
    members = [("A", "D"), ("B", "E"), ("C", "F"), ("D", "E"), ("E", "F")]
    for i, j in members:
        x0, y0 = _iso_proj(*pts[i]); x1, y1 = _iso_proj(*pts[j])
        col = MEMBER_COLOR if pts[i][2] > 0 or pts[j][2] > 0 else "#2c5f8a"
        ax.plot([x0, x1], [y0, y1], color=col, lw=2.5, zorder=2)
    for k in ("A", "B", "C"):
        sx, sy = _iso_proj(*pts[k])
        ax.plot(sx, sy, "s", color=SUPPORT_COLOR, ms=5, zorder=5)
    # tip load
    sx, sy = _iso_proj(*pts["F"])
    ax.annotate("", xy=(sx, sy), xytext=(sx, sy + 0.5),
                arrowprops=dict(arrowstyle="-|>", color=LOAD_COLOR, lw=1.5), zorder=4)
    ax.set_xlim(-0.5, 4.5); ax.set_ylim(-0.5, 4.5)
    ax.set_title("3D-5 — L-shaped 3D Frame, Tip Load", fontsize=8, color=MEMBER_COLOR, pad=4)
    ax.set_aspect("equal")
    fig.tight_layout()
    return fig


def sketch_3d6() -> plt.Figure:
    """3D-6: 3D portal frame with gravity + lateral load."""
    fig, ax = _fig()
    pts = {
        "A": (0, 0, 0), "B": (4, 0, 0),
        "C": (0, 0, 3), "D": (4, 0, 3),
    }
    _beam(ax, 0, 0, 0, 3); _beam(ax, 4, 0, 4, 3); _beam(ax, 0, 3, 4, 3)
    _fixed_wall(ax, 0, -0.3, 0.6)
    _fixed_wall(ax, 4, -0.3, 0.6, side="right")
    _udl_arrow(ax, 0, 4, 3, label="w")
    _lateral_load(ax, 0, 3, direction=1, label="H")
    ax.set_xlim(-0.8, 5); ax.set_ylim(-0.8, 3.8)
    ax.set_title("3D-6 — 3D Portal Frame, Gravity + Lateral", fontsize=8, color=MEMBER_COLOR, pad=4)
    fig.tight_layout()
    return fig


def sketch_3d7() -> plt.Figure:
    """3D-7: 3D space truss (tetrahedral unit)."""
    fig, ax = _fig()
    pts = {
        "A": (0, 0, 0), "B": (2, 0, 0), "C": (2, 2, 0), "D": (0, 2, 0),
        "T": (1, 1, 2),
    }
    base = [("A", "B"), ("B", "C"), ("C", "D"), ("D", "A"), ("A", "C"), ("B", "D")]
    apex = [("A", "T"), ("B", "T"), ("C", "T"), ("D", "T")]
    for i, j in base:
        x0, y0 = _iso_proj(*pts[i]); x1, y1 = _iso_proj(*pts[j])
        ax.plot([x0, x1], [y0, y1], color=MEMBER_COLOR, lw=2, zorder=2)
    for i, j in apex:
        x0, y0 = _iso_proj(*pts[i]); x1, y1 = _iso_proj(*pts[j])
        ax.plot([x0, x1], [y0, y1], color="#2c5f8a", lw=1.8, zorder=2)
    for k in ("A", "B", "C", "D"):
        sx, sy = _iso_proj(*pts[k])
        ax.plot(sx, sy, "^", color=SUPPORT_COLOR, ms=5, zorder=5)
    sx, sy = _iso_proj(*pts["T"])
    ax.annotate("", xy=(sx, sy), xytext=(sx, sy + 0.4),
                arrowprops=dict(arrowstyle="-|>", color=LOAD_COLOR, lw=1.5), zorder=4)
    ax.set_xlim(-0.3, 3.5); ax.set_ylim(-0.4, 3.2)
    ax.set_title("3D-7 — Space Truss, Apex Point Load", fontsize=8, color=MEMBER_COLOR, pad=4)
    ax.set_aspect("equal")
    fig.tight_layout()
    return fig


def sketch_3d8() -> plt.Figure:
    """3D-8: 3-bay 3D frame (single storey)."""
    fig, ax = _fig()
    bays_x = [0, 3, 6]; bays_y = [0, 3]; H = 3
    for y in bays_y:
        for i in range(len(bays_x) - 1):
            x0, x1 = bays_x[i], bays_x[i + 1]
            sx0, sy0 = _iso_proj(x0, y, H); sx1, sy1 = _iso_proj(x1, y, H)
            ax.plot([sx0, sx1], [sy0, sy1], color=MEMBER_COLOR, lw=2, zorder=2)
    for x in bays_x:
        for y in bays_y:
            sx0, sy0 = _iso_proj(x, y, 0); sx1, sy1 = _iso_proj(x, y, H)
            ax.plot([sx0, sx1], [sy0, sy1], color="#2c5f8a", lw=2.5, zorder=2)
            ax.plot(sx0, sy0, "s", color=SUPPORT_COLOR, ms=4, zorder=5)
    for i in range(len(bays_x) - 1):
        x0, x1 = bays_x[i], bays_x[i + 1]
        sx0, sy0 = _iso_proj(x0, bays_y[0], H); sx1, sy1 = _iso_proj(x1, bays_y[1], H)
        ax.plot([sx0, sx1], [sy0, sy1], color=MEMBER_COLOR, lw=2, alpha=0.6, zorder=2)
    ax.set_xlim(-0.5, 7); ax.set_ylim(-0.5, 4.5)
    ax.set_title("3D-8 — 3-bay Single-storey 3D Frame", fontsize=8, color=MEMBER_COLOR, pad=4)
    ax.set_aspect("equal")
    fig.tight_layout()
    return fig
