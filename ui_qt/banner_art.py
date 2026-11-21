"""Start-page banner art: a Pratt truss assembling its global stiffness matrix.

Every member of an 8-panel Pratt truss has its own colour (blue at the left support to aqua
at the right, the theme's blue-cyan ramp) and paints the 4 × 4 block it adds to the global
stiffness matrix K. Where members share a joint their colours mix in K, so the picture shows
the Direct Stiffness Method's scatter assembly: K = Σ Aᵉᵀ kᵉ Aᵉ.

``ASSEMBLY`` is computed once with NumPy (EA = 1, panel = 1); ``paint_assembly`` draws the
first ``count`` members (all by default) into a QPainter, so the start page can animate the
assembly member by member. No Qt widgets here, only painting.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPolygonF

from ui_qt import theme

PANELS = 8
DEPTH = 1.1                 # truss depth in panel widths


@dataclass
class Assembly:
    """Geometry, global stiffness matrix and per-member scatter blocks of the truss."""
    nodes: np.ndarray                         # (n_nodes, 2) x, y in panel widths
    bars: list[tuple[int, int]]               # member end nodes, listed left to right
    K: np.ndarray                             # (n_dof, n_dof) global stiffness, EA = 1
    blocks: list[list[tuple[int, int]]] = field(default_factory=list)   # (row, col) per member

    @property
    def n_dof(self) -> int:
        return self.K.shape[0]


def pratt_assembly(panels: int = PANELS, depth: float = DEPTH) -> Assembly:
    """Assemble K for a Pratt truss, nodes numbered left to right (b0, b1, t1, …, b8)."""
    ids: dict[str, int] = {}
    coords: list[tuple[float, float]] = []

    def add(key: str, x: float, y: float) -> None:
        ids[key] = len(coords)
        coords.append((x, y))

    add("b0", 0.0, 0.0)
    for i in range(1, panels):
        add(f"b{i}", float(i), 0.0)
        add(f"t{i}", float(i), depth)
    add(f"b{panels}", float(panels), 0.0)

    bars: list[tuple[int, int]] = []

    def bar(a: str, b: str) -> None:
        bars.append((ids[a], ids[b]))

    bar("b0", "b1")
    bar("b0", "t1")
    for i in range(1, panels):
        bar(f"b{i}", f"t{i}")
        if i < panels // 2:
            bar(f"t{i}", f"b{i + 1}")             # Pratt: diagonals slope down to midspan
        if i > panels // 2:
            bar(f"t{i}", f"b{i - 1}")
        if i < panels - 1:
            bar(f"t{i}", f"t{i + 1}")
        bar(f"b{i}", f"b{i + 1}")
    bar(f"t{panels - 1}", f"b{panels}")

    nodes = np.array(coords)
    n_dof = 2 * len(nodes)
    K = np.zeros((n_dof, n_dof))
    blocks: list[list[tuple[int, int]]] = []
    for i, j in bars:
        delta = nodes[j] - nodes[i]
        length = float(np.hypot(*delta))
        c, s = delta / length
        k_member = np.outer([c, s, -c, -s], [c, s, -c, -s]) / length      # EA/L · eeᵀ
        dofs = [2 * i, 2 * i + 1, 2 * j, 2 * j + 1]
        K[np.ix_(dofs, dofs)] += k_member
        blocks.append([(r, cc) for r in dofs for cc in dofs])
    return Assembly(nodes, bars, K, blocks)


ASSEMBLY = pratt_assembly()

_RAMP = (theme.BLUE, theme.SKY, theme.CYAN, theme.AQUA)


def member_colour(k: int, n: int) -> QColor:
    """Colour of member k of n along the blue → sky → cyan → aqua ramp."""
    t = 0.0 if n <= 1 else k / (n - 1)
    s = t * (len(_RAMP) - 1)
    i = min(int(s), len(_RAMP) - 2)
    a, b, f = QColor(_RAMP[i]), QColor(_RAMP[i + 1]), s - i
    return QColor(round(a.red() + (b.red() - a.red()) * f),
                  round(a.green() + (b.green() - a.green()) * f),
                  round(a.blue() + (b.blue() - a.blue()) * f))


def cell_colours(asm: Assembly, count: int) -> dict[tuple[int, int], QColor]:
    """Colour of every K cell assembled by the first ``count`` members (mixed where shared).

    Cells that end up exactly zero in the finished K are left out once all members are in.
    Opacity grows with √|Kᵢⱼ| (from 60 %) so the diagonal reads brightest.
    """
    n = len(asm.bars)
    k_max = float(np.max(np.abs(np.diag(asm.K))))
    acc: dict[tuple[int, int], list[float]] = {}
    for k in range(min(count, n)):
        col = member_colour(k, n)
        for cell in asm.blocks[k]:
            a = acc.setdefault(cell, [0.0, 0.0, 0.0, 0.0])
            a[0] += col.red(); a[1] += col.green(); a[2] += col.blue(); a[3] += 1
    out: dict[tuple[int, int], QColor] = {}
    for (r, c), (rr, gg, bb, m) in acc.items():
        value = abs(float(asm.K[r, c]))
        if value < 1e-12 and count >= n:
            continue
        strength = np.sqrt(value / k_max) if value > 1e-12 else 0.3
        out[(r, c)] = QColor(round(rr / m), round(gg / m), round(bb / m), round(255 * (0.6 + 0.4 * strength)))
    return out


def paint_assembly(p: QPainter, origin: QPointF, count: int | None = None, flash: int = -1,
                   asm: Assembly = ASSEMBLY) -> None:
    """Draw truss + arrow + K into a 455 × 150 area whose top-left corner is ``origin``.

    ``count`` members are assembled (all when None); member ``flash`` is drawn bold and its
    block in K is highlighted white (used while animating).
    """
    n = len(asm.bars)
    count = n if count is None else count
    ox, oy = origin.x(), origin.y()
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Formula
    p.setFont(_mono(10.5))
    p.setPen(QColor(theme.TEXT_DIM))
    p.drawText(QPointF(ox, oy + 26), "[K] = Σ Aᵉᵀ kᵉ Aᵉ")

    # Truss: members coloured along the span, not-yet-assembled ones as faint ghosts
    sx, sy, base = 30.0, 52.0, oy + 112.0

    def at(i: int) -> QPointF:
        x, y = asm.nodes[i]
        return QPointF(ox + x * sx, base - y * sy)

    for k, (i, j) in enumerate(asm.bars):
        if k < count:
            pen = QPen(member_colour(k, n), 3.2 if k == flash else 2.2)
        else:
            ghost = QColor(theme.TEXT_DIM); ghost.setAlpha(50)
            pen = QPen(ghost, 1.0)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawLine(at(i), at(j))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(QColor("#e8eef6")))
    for i in range(len(asm.nodes)):
        p.drawEllipse(at(i), 1.8, 1.8)
    support = QColor(theme.SUPPORT); support.setAlpha(215)
    p.setBrush(QBrush(support))
    for i in (0, len(asm.nodes) - 1):                       # pin left, roller right
        pt = at(i)
        p.drawPolygon(QPolygonF([pt, QPointF(pt.x() - 6, pt.y() + 8), QPointF(pt.x() + 6, pt.y() + 8)]))

    # Arrow: truss → matrix
    arrow = QColor(theme.TEXT_DIM); arrow.setAlpha(150)
    pen = QPen(arrow, 1.0, Qt.PenStyle.DashLine)
    p.setPen(pen)
    p.drawLine(QPointF(ox + 250, oy + 75), QPointF(ox + 287, oy + 75))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(arrow))
    p.drawPolygon(QPolygonF([QPointF(ox + 292, oy + 75), QPointF(ox + 286, oy + 72), QPointF(ox + 286, oy + 78)]))
    p.setFont(_mono(8.5))
    p.setPen(QColor(theme.TEXT_DIM))
    label = "assemble" if count >= n else f"{count} / {n}"
    p.drawText(QRectF(ox + 238, oy + 56, 60, 14), Qt.AlignmentFlag.AlignCenter, label)

    # K: one cell per term, colours mixed from the members that share it
    nd, cell = asm.n_dof, 3.8
    mx, my = ox + 300, oy + (150 - nd * cell) / 2
    p.setBrush(QBrush(QColor(0, 0, 0, 56)))
    p.drawRect(QRectF(mx - 2, my - 2, nd * cell + 4, nd * cell + 4))
    flash_cells = set(asm.blocks[flash]) if 0 <= flash < n else set()
    for (r, c), col in cell_colours(asm, count).items():
        p.setBrush(QBrush(QColor("#ffffff") if (r, c) in flash_cells else col))
        p.drawRect(QRectF(mx + c * cell + 0.3, my + r * cell + 0.3, cell - 0.6, cell - 0.6))
    bracket = QColor(theme.TEXT); bracket.setAlpha(170)
    p.setPen(QPen(bracket, 1.0))
    p.setBrush(Qt.BrushStyle.NoBrush)
    left, right, top, bottom = mx - 4, mx + nd * cell + 4, my - 3, my + nd * cell + 3
    for x, lip in ((left, 4), (right, -4)):
        p.drawPolyline(QPolygonF([QPointF(x + lip, top), QPointF(x, top),
                                  QPointF(x, bottom), QPointF(x + lip, bottom)]))
    p.restore()


def _mono(size: float) -> QFont:
    f = QFont("Consolas")
    f.setStyleHint(QFont.StyleHint.Monospace)
    f.setPointSizeF(size * 0.75)          # px-ish sizes from the preview, as points
    return f
