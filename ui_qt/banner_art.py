"""Start-page banner art. Two pieces, each drawn into a 480 × 150 area with a QPainter:

``ElementArt`` (the banner in use) — "the element, inside and out": a simply supported beam
with its principal stress trajectories under a uniform load (tension aqua, compression
blue) and its six end freedoms drawn as arrows (u blue, v aqua, θ sky), beside the 2D frame
element stiffness matrix kᵉ typeset in symbols, rows and columns labelled with the same
freedoms in the same colours. The trajectories are traced through the beam-theory stress
field; the matrix is the one ``elements.frame_element`` uses (checked in the tests).

``paint_assembly`` (kept as an alternative) — an 8-panel Pratt truss whose members, coloured
along the theme's blue-cyan ramp, scatter their 4 × 4 blocks into the global stiffness
matrix K (colours mix where members share a joint): K = Σ Aᵉᵀ kᵉ Aᵉ.

Both draw progressively (``step`` of ``steps``) so the start page can animate them once.
No Qt widgets here, only painting.
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


# ── "The element, inside and out" ────────────────────────────────────────────

#: The 2D frame element stiffness matrix in local coordinates, DOFs [uᵢ vᵢ θᵢ uⱼ vⱼ θⱼ].
FRAME_TERMS: tuple[tuple[str, ...], ...] = (
    ("EA/L", "0", "0", "−EA/L", "0", "0"),
    ("0", "12EI/L³", "6EI/L²", "0", "−12EI/L³", "6EI/L²"),
    ("0", "6EI/L²", "4EI/L", "0", "−6EI/L²", "2EI/L"),
    ("−EA/L", "0", "0", "EA/L", "0", "0"),
    ("0", "−12EI/L³", "−6EI/L²", "0", "12EI/L³", "−6EI/L²"),
    ("0", "6EI/L²", "2EI/L", "0", "−6EI/L²", "4EI/L"),
)
#: (label, colour) per DOF: axial u blue, transverse v aqua, rotation θ sky
FRAME_DOFS: tuple[tuple[str, str], ...] = (
    ("uᵢ", theme.BLUE), ("vᵢ", theme.AQUA), ("θᵢ", theme.SKY),
    ("uⱼ", theme.BLUE), ("vⱼ", theme.AQUA), ("θⱼ", theme.SKY),
)


def evaluate_frame_term(term: str, E: float, A: float, I: float, L: float) -> float:
    """Numeric value of one ``FRAME_TERMS`` entry (used to check it against the solver)."""
    if term == "0":
        return 0.0
    sign = -1.0 if term.startswith("−") else 1.0
    body = term.lstrip("−")
    if body == "EA/L":
        return sign * E * A / L
    coef, power = body.split("EI/L")
    exponent = {"": 1, "²": 2, "³": 3}[power]
    return sign * float(coef) * E * I / L ** exponent


def stress_trajectories(span_to_depth: float = 6.0, seeds: int = 6,
                        step: float = 0.01) -> list[tuple[int, np.ndarray]]:
    """Principal stress trajectories of a simply supported beam under uniform load.

    Beam of depth 1 and span ``span_to_depth``; y up from the neutral axis. Stresses from
    beam theory (w = 1): σx = −M·y/I, τ = 3V/2A·(1 − 4y²). Each trajectory starts at
    midspan and is traced outward until it leaves the beam. Returns (family, points)
    with family 0 = tension (σ1), 1 = compression (σ2); points are (x, y) arrays that start
    at midspan, so drawing a prefix makes the lines grow outward.
    """
    span, depth = span_to_depth, 1.0
    inertia, area = depth ** 3 / 12, depth

    def direction(x: float, y: float, family: int) -> np.ndarray:
        moment, shear = x * (span - x) / 2, span / 2 - x
        sx = -moment * y / inertia
        tau = 1.5 * shear / area * (1 - 4 * y * y / depth ** 2)
        theta = 0.5 * np.arctan2(2 * tau, sx) + (np.pi / 2 if family else 0.0)
        return np.array([np.cos(theta), np.sin(theta)])

    def trace(y0: float, family: int, sign: float) -> np.ndarray:
        pt, prev, pts = np.array([span / 2, y0]), None, [(span / 2, y0)]
        for _ in range(4000):
            d = direction(pt[0], pt[1], family)
            if (prev is not None and d @ prev < 0) or (prev is None and d[0] * sign < 0):
                d = -d
            prev = d
            pt = pt + d * step
            if pt[0] < 0 or pt[0] > span or abs(pt[1]) > depth / 2:
                break
            pts.append((pt[0], pt[1]))
        return np.array(pts)

    out: list[tuple[int, np.ndarray]] = []
    for k in range(1, seeds + 1):
        y = -depth / 2 + k * (depth / 2) / (seeds + 1)   # tension seeds: bottom half
        for sign in (1.0, -1.0):
            out.append((0, trace(y, 0, sign)))
            out.append((1, trace(-y, 1, sign)))
    return out


class ElementArt:
    """Beam element with stress trajectories and end freedoms, beside its labelled kᵉ."""

    steps = 30                       # draw-in: trajectories first, then the matrix rows
    tooltip = ("The frame element, inside and out: stress trajectories in the beam, "
               "and the stiffness matrix the solver uses for it (click to replay)")

    BEAM = (0.0, 150.0, 82.0)            # x0, x1, centre-line y (art coordinates)
    MATRIX = (203.0, 32.0, 38.0, 15.5)   # x0, y0, column width, row height
    fade = (-80.0, -50.0)                # fade-in from the left, ends before the uᵢ label

    def __init__(self) -> None:
        self.trajectories = stress_trajectories()

    def paint(self, p: QPainter, origin: QPointF, step: int | None = None) -> None:
        step = self.steps if step is None else step
        f = step / self.steps
        grow = min(1.0, f / 0.65)                   # trajectories: first 65 % of the time
        rows_shown = 0 if f < 0.65 else min(6, 1 + int((f - 0.65) / 0.35 * 6))
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.translate(origin)
        self._paint_beam(p, grow)
        self._paint_matrix(p, rows_shown, labels=f >= 0.65)
        p.restore()

    # ── beam ──────────────────────────────────────────────────────────────────

    def _paint_beam(self, p: QPainter, grow: float) -> None:
        x0, x1, yc = self.BEAM
        scale = (x1 - x0) / 6.0                     # span/depth = 6, depth = 1
        half = scale / 2
        for family, pts in self.trajectories:
            n = max(2, int(len(pts) * grow))
            colour = QColor(theme.AQUA if family == 0 else theme.BLUE)
            colour.setAlpha(230)
            p.setPen(QPen(colour, 1.1))
            p.drawPolyline(QPolygonF([QPointF(x0 + x * scale, yc - y * scale) for x, y in pts[:n]]))
        outline = QColor(theme.TEXT_DIM); outline.setAlpha(200)
        p.setPen(QPen(outline, 1.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(QRectF(x0, yc - half, x1 - x0, 2 * half))
        axis = QColor(theme.TEXT_DIM); axis.setAlpha(80)
        p.setPen(QPen(axis, 1.0, Qt.PenStyle.DashLine))
        p.drawLine(QPointF(x0, yc), QPointF(x1, yc))
        for x, sub, out in ((x0, "ᵢ", -1), (x1, "ⱼ", 1)):
            self._paint_freedoms(p, x, yc, half, sub, out)

    def _paint_freedoms(self, p: QPainter, x: float, yc: float, half: float, sub: str,
                        out: int) -> None:
        """u (axial), v (transverse) and θ (rotation) arrows at one end of the element."""
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor("#e8eef6")))
        p.drawEllipse(QPointF(x, yc), 2.6, 2.6)
        p.setFont(_mono(9.5))
        u, v, th = QColor(theme.BLUE), QColor(theme.AQUA), QColor(theme.SKY)
        side = (Qt.AlignmentFlag.AlignLeft if out > 0 else Qt.AlignmentFlag.AlignRight)
        # u (axial)
        p.setPen(QPen(u, 1.5))
        p.drawLine(QPointF(x, yc), QPointF(x + out * 18, yc))
        _arrow_head(p, QPointF(x + out * 22, yc), out, 0, u)
        p.setPen(u)
        p.drawText(QRectF(x + out * 26 - (0 if out > 0 else 22), yc - 7, 22, 14),
                   side | Qt.AlignmentFlag.AlignVCenter, "u" + sub)
        # v (transverse)
        top = yc - half
        p.setPen(QPen(v, 1.5))
        p.drawLine(QPointF(x, top), QPointF(x, top - 22))
        _arrow_head(p, QPointF(x, top - 26), 0, -1, v)
        p.setPen(v)
        p.drawText(QPointF(x + 6, top - 19), "v" + sub)
        # θ (rotation, anticlockwise)
        cy, r = yc + half + 14, 13.0
        p.setPen(QPen(th, 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        # arc under the node, from lower-left round to lower-right; the head at the lower
        # right points up-right, so the bottom of the circle moves right: anticlockwise,
        # StructLab's positive θ
        p.drawArc(QRectF(x - r, cy - r, 2 * r, 2 * r), -27 * 16, -126 * 16)
        a = 0.15 * np.pi                                    # screen angle of the head (y down)
        end = np.array([x + r * np.cos(a), cy + r * np.sin(a)])
        t = np.array([np.sin(a), -np.cos(a)])               # tangent of anticlockwise motion
        n = np.array([-t[1], t[0]])
        tip, back = end + 4 * t, end - 3 * t
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(th))
        p.drawPolygon(QPolygonF([QPointF(*tip), QPointF(*(back + 3 * n)), QPointF(*(back - 3 * n))]))
        p.setPen(th)
        label_x = x + out * 16
        p.drawText(QRectF(label_x - (0 if out > 0 else 22), cy + 11, 22, 14),
                   side | Qt.AlignmentFlag.AlignVCenter, "θ" + sub)

    # ── matrix ────────────────────────────────────────────────────────────────

    def _paint_matrix(self, p: QPainter, rows_shown: int, labels: bool) -> None:
        x0, y0, cw, rh = self.MATRIX
        ox = x0 + 12
        p.setFont(_mono(13))
        p.setPen(QColor(theme.BLUE).lighter(150))
        p.drawText(QRectF(x0 - 30, y0 - 30, 28, 22), Qt.AlignmentFlag.AlignCenter, "kᵉ")
        bracket = QColor(theme.TEXT); bracket.setAlpha(190)
        p.setPen(QPen(bracket, 1.1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        left, right, top, bottom = x0 + 4, x0 + 4 + 6 * cw + 16, y0 - 4, y0 + 6 * rh + 2
        for x, lip in ((left, 5), (right, -5)):
            p.drawPolyline(QPolygonF([QPointF(x + lip, top), QPointF(x, top),
                                      QPointF(x, bottom), QPointF(x + lip, bottom)]))
        p.setFont(_mono(7.8))
        dim = QColor(theme.TEXT_DIM); dim.setAlpha(110)
        for r in range(rows_shown):
            for c, term in enumerate(FRAME_TERMS[r]):
                colour = dim if term == "0" else QColor(theme.BLUE if "EA" in term else theme.AQUA)
                p.setPen(colour)
                p.drawText(QRectF(ox + c * cw, y0 + r * rh, cw, rh), Qt.AlignmentFlag.AlignCenter, term)
        if labels:
            p.setFont(_mono(7.8))
            for i, (name, col) in enumerate(FRAME_DOFS):
                p.setPen(QColor(col))
                p.drawText(QRectF(ox + i * cw, y0 - 18, cw, 12), Qt.AlignmentFlag.AlignCenter, name)
                p.drawText(QRectF(x0 + 6 * cw + 24, y0 + i * rh, 24, rh),
                           Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)


class AssemblyArt:
    """The Pratt-truss assembly (``paint_assembly``) behind the same interface."""

    steps = len(ASSEMBLY.bars)
    fade = (-90.0, 80.0)
    tooltip = ("Direct Stiffness Method: each member adds its block to K "
               "(click to replay the assembly)")

    def paint(self, p: QPainter, origin: QPointF, step: int | None = None) -> None:
        step = self.steps if step is None else step
        flash = step - 1 if 0 < step < self.steps else -1
        paint_assembly(p, origin, step, flash)


def _arrow_head(p: QPainter, tip: QPointF, dx: int, dy: int, colour: QColor) -> None:
    """Small filled arrow head pointing along (dx, dy); axis-aligned only."""
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(colour))
    if dx:
        pts = [tip, QPointF(tip.x() - dx * 6, tip.y() - 3), QPointF(tip.x() - dx * 6, tip.y() + 3)]
    else:
        pts = [tip, QPointF(tip.x() - 3, tip.y() - dy * 6), QPointF(tip.x() + 3, tip.y() - dy * 6)]
    p.drawPolygon(QPolygonF(pts))
