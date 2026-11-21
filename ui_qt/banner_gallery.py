"""More start-page banners, one per theme of the rotation (see ui_qt/banner_themes.py).

* ``PortalArt`` (static analysis): a fixed-base portal frame under a uniform load on the
  rafter and a wind load at the eaves, solved here by the direct stiffness method; bending
  moments on the tension side of each member and the swayed deflected shape.
* ``ModesArt`` (dynamics): the three sway modes of a uniform three-storey shear frame,
  each with a fading trail of intermediate positions and the undeformed frame as a ghost.

Each art draws into a 480 × 150 area (``paint(painter, origin, step)``) and grows in over
``steps`` frames. The numbers are computed with NumPy and checked against closed-form
results in tests/test_banner_gallery.py.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen, QPolygonF

from ui_qt import theme
from ui_qt.banner_art import _arrow_head, _mono

LABEL = "#9cc4ff"                 # light blue for values on the art


# ── shared drawing helpers ───────────────────────────────────────────────────

def _polyline(p: QPainter, pts, colour: QColor | str, width: float = 1.4, dashed: bool = False) -> None:
    pen = QPen(QColor(colour), width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    if dashed:
        pen.setDashPattern([3.5, 2.8])
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPolyline(QPolygonF([QPointF(x, y) for x, y in pts]))


def _alpha(colour: str, a: float) -> QColor:
    c = QColor(colour)
    c.setAlphaF(max(0.0, min(1.0, a)))
    return c


def _fixed_base(p: QPainter, x: float, y: float, width: float = 14.0, down: bool = True) -> None:
    """Ground line with hatching (a fixed support)."""
    p.setPen(QPen(_alpha(theme.SUPPORT, 0.85), 1.4))
    p.drawLine(QPointF(x - width / 2, y), QPointF(x + width / 2, y))
    k = -width / 2
    while k <= width / 2 + 1e-9:
        p.drawLine(QPointF(x + k, y), QPointF(x + k - 3, y + (4 if down else -4)))
        k += 4


def _text(p: QPainter, s: str, x: float, y: float, colour: QColor | str, size: float = 9.5,
          align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignHCenter) -> None:
    """Text with its baseline near y, centred (or aligned) on x."""
    p.setFont(_mono(size))
    p.setPen(QColor(colour))
    w = 120.0
    left = x - w / 2 if align == Qt.AlignmentFlag.AlignHCenter else (x if align == Qt.AlignmentFlag.AlignLeft else x - w)
    p.drawText(QRectF(left, y - 11, w, 14), align | Qt.AlignmentFlag.AlignVCenter, s)


# ── static: portal frame ─────────────────────────────────────────────────────

@dataclass
class PortalMember:
    i: int
    j: int
    q: float                       # uniform load, downward in the member's local −y
    length: float
    c: float
    s: float
    d_local: np.ndarray            # end displacements in local axes (6)
    m_i: float                     # end moments (anticlockwise on the member)
    m_j: float

    def moment(self, t: float) -> float:
        """Bending moment at t = x/L, sagging positive (tension on the local −y side)."""
        return -self.m_i * (1 - t) + self.m_j * t + self.q * self.length ** 2 * t * (1 - t) / 2


@dataclass
class PortalSolution:
    nodes: np.ndarray
    members: list[PortalMember]
    d: np.ndarray                  # global displacements, 3 per node

    @property
    def base_moments(self) -> tuple[float, float]:
        return abs(self.members[0].m_i), abs(self.members[2].m_i)

    @property
    def knee_moments(self) -> tuple[float, float]:
        return abs(self.members[1].m_i), abs(self.members[1].m_j)


def solve_portal(h: float = 4.0, span: float = 6.0, w: float = 1.0, wind: float = 2.0,
                 EA: float = 1e4, EI: float = 1.0) -> PortalSolution:
    """Fixed-base portal: UDL ``w`` on the rafter, horizontal ``wind`` at the left eave."""
    nodes = np.array([[0.0, 0.0], [0.0, h], [span, h], [span, 0.0]])
    elems = [(0, 1, 0.0), (1, 2, w), (3, 2, 0.0)]
    K = np.zeros((12, 12))
    F = np.zeros(12)
    data = []
    for i, j, q in elems:
        delta = nodes[j] - nodes[i]
        L = float(np.hypot(*delta))
        c, s = delta / L
        a, b = EA / L, EI / L ** 3
        k = np.array([[a, 0, 0, -a, 0, 0],
                      [0, 12 * b, 6 * b * L, 0, -12 * b, 6 * b * L],
                      [0, 6 * b * L, 4 * b * L * L, 0, -6 * b * L, 2 * b * L * L],
                      [-a, 0, 0, a, 0, 0],
                      [0, -12 * b, -6 * b * L, 0, 12 * b, -6 * b * L],
                      [0, 6 * b * L, 2 * b * L * L, 0, -6 * b * L, 4 * b * L * L]])
        R = np.array([[c, s, 0], [-s, c, 0], [0, 0, 1.0]])
        T = np.zeros((6, 6)); T[:3, :3] = R; T[3:, 3:] = R
        fef = np.array([0, q * L / 2, q * L * L / 12, 0, q * L / 2, -q * L * L / 12])   # StructLab convention
        dofs = [3 * i, 3 * i + 1, 3 * i + 2, 3 * j, 3 * j + 1, 3 * j + 2]
        K[np.ix_(dofs, dofs)] += T.T @ k @ T
        F[dofs] -= T.T @ fef                       # equivalent nodal loads = −FEF
        data.append((i, j, q, L, c, s, k, T, fef, dofs))
    F[3] += wind
    free = [3, 4, 5, 6, 7, 8]
    d = np.zeros(12)
    d[free] = np.linalg.solve(K[np.ix_(free, free)], F[free])
    members = []
    for i, j, q, L, c, s, k, T, fef, dofs in data:
        dl = T @ d[dofs]
        f = k @ dl + fef
        members.append(PortalMember(i, j, q, L, c, s, dl, float(f[2]), float(f[5])))
    return PortalSolution(nodes, members, d)


class PortalArt:
    """Static analysis: portal frame, bending moments and deflected shape."""

    theme = "Static analysis"
    steps = 24
    fade = (-60.0, -30.0)
    tooltip = ("A fixed-base portal frame under gravity and wind: bending moments on the "
               "tension side and the swayed deflected shape (click to replay)")

    OX, OY, SCALE, MOMENT_PX = 130.0, 128.0, 21.0, 6.5

    def __init__(self) -> None:
        self.sol = solve_portal()

    def _p(self, x: float, y: float) -> tuple[float, float]:
        return self.OX + x * self.SCALE, self.OY - y * self.SCALE

    def paint(self, p: QPainter, origin: QPointF, step: int | None = None) -> None:
        step = self.steps if step is None else step
        f = step / self.steps
        sol, P = self.sol, self._p
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.translate(origin)

        # Bending moment diagrams (grow with f)
        for m in sol.members:
            ny = np.array([-m.s, m.c])                     # local y in global axes
            base = sol.nodes[m.i]
            pts = []
            for k in range(41):
                t = k / 40
                xy = base + np.array([m.c, m.s]) * m.length * t - ny * m.moment(t) * f * self.MOMENT_PX / self.SCALE
                pts.append(P(*xy))
            poly = [P(*sol.nodes[m.i]), *pts, P(*sol.nodes[m.j])]
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(_alpha(theme.BLUE, 0.25)))
            p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in poly]))
            _polyline(p, pts, theme.BLUE, 1.3)

        # Deflected shape: Hermite interpolation of the end displacements (dashed cyan)
        dmax = max(np.hypot(sol.d[k], sol.d[k + 1]) for k in range(0, 12, 3))
        amp = 16.0 / self.SCALE / dmax * f
        for m in sol.members:
            u1, v1, t1, u2, v2, t2 = m.d_local
            L, pts = m.length, []
            for k in range(31):
                x = k / 30
                v = ((1 - 3 * x * x + 2 * x ** 3) * v1 + L * (x - 2 * x * x + x ** 3) * t1
                     + (3 * x * x - 2 * x ** 3) * v2 + L * (-x * x + x ** 3) * t2)
                u = u1 + (u2 - u1) * x
                gx = sol.nodes[m.i][0] + m.c * (L * x + u * amp) - m.s * v * amp
                gy = sol.nodes[m.i][1] + m.s * (L * x + u * amp) + m.c * v * amp
                pts.append(P(gx, gy))
            if f > 0:
                _polyline(p, pts, theme.CYAN, 1.5, dashed=True)

        # Members, supports, loads
        for m in sol.members:
            _polyline(p, [P(*sol.nodes[m.i]), P(*sol.nodes[m.j])], theme.SKY, 2.6)
        _fixed_base(p, *P(0.0, 0.0))
        _fixed_base(p, *P(sol.nodes[3][0], 0.0))
        h, span = sol.nodes[1][1], sol.nodes[2][0]
        load = _alpha(theme.LOAD, 0.65)
        for k in range(9):
            x, y = P(span * k / 8, h)
            p.setPen(QPen(load, 1.0))
            p.drawLine(QPointF(x, y - 20), QPointF(x, y - 7))
            _arrow_head(p, QPointF(x, y - 3), 0, 1, load)
        ex, ey = P(0.0, h)
        p.setPen(QPen(QColor(theme.LOAD), 1.6))
        p.drawLine(QPointF(ex - 46, ey), QPointF(ex - 10, ey))
        _arrow_head(p, QPointF(ex - 5, ey), 1, 0, QColor(theme.LOAD))
        _text(p, "W", ex - 52, ey - 4, theme.LOAD, 10)
        if f >= 1:
            a, b = sol.base_moments
            _text(p, f"{a:.2f}", *P(-0.9, 0.55), LABEL)
            _text(p, f"{b:.2f}", *P(span + 0.9, 0.55), LABEL)
        p.restore()


# ── dynamics: mode shapes ────────────────────────────────────────────────────

def shear_frame_modes(storeys: int = 3) -> tuple[np.ndarray, np.ndarray]:
    """Eigenvalues (×k/m) and mode shapes of a uniform shear frame, fixed at the base.

    Modes are columns, each scaled to a largest component of magnitude 1 with its first
    non-zero component positive (φ₁ = 0.445, 0.802, 1.000 for three storeys).
    """
    K = 2 * np.eye(storeys) - np.eye(storeys, k=1) - np.eye(storeys, k=-1)
    K[-1, -1] = 1.0
    values, vectors = np.linalg.eigh(K)
    vectors = vectors / np.abs(vectors).max(axis=0)
    first = vectors[np.argmax(np.abs(vectors) > 1e-9, axis=0), range(storeys)]
    return values, vectors * np.sign(first)


class ModesArt:
    """Dynamics: the three sway modes of a three-storey, two-bay frame."""

    theme = "Dynamics"
    steps = 24
    fade = (-60.0, -30.0)
    tooltip = ("The three sway modes of a three-storey frame, each with a trail of "
               "intermediate positions (click to replay)")

    CENTRES = (70.0, 205.0, 340.0)
    BASE, STOREY, BAY, AMP = 122.0, 30.0, 40.0, 18.0

    def __init__(self) -> None:
        self.values, self.modes = shear_frame_modes(3)

    def _frame(self, p: QPainter, cx: float, phi: np.ndarray, scale: float, colour: QColor, width: float) -> list[float]:
        u = [0.0, *(phi * scale * self.AMP)]
        pen = QPen(colour, width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for col in (-1, 0, 1):                              # columns: double curvature between floors
            pts = []
            for lv in range(3):
                for i in range(17):
                    t = i / 16
                    hh = 3 * t * t - 2 * t ** 3
                    pts.append(QPointF(cx + col * self.BAY + u[lv] + (u[lv + 1] - u[lv]) * hh,
                                       self.BASE - (lv + t) * self.STOREY))
            p.drawPolyline(QPolygonF(pts))
        for lv in range(1, 4):                              # floors stay straight
            y = self.BASE - lv * self.STOREY
            p.drawLine(QPointF(cx - self.BAY + u[lv], y), QPointF(cx + self.BAY + u[lv], y))
        return u

    def paint(self, p: QPainter, origin: QPointF, step: int | None = None) -> None:
        step = self.steps if step is None else step
        f = step / self.steps
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.translate(origin)
        for m, cx in enumerate(self.CENTRES):
            phi = self.modes[:, m]
            self._frame(p, cx, phi, 0.0, _alpha(theme.TEXT_DIM, 0.35), 1.0)            # ghost
            for k, s in enumerate((-1.0, -0.6, -0.25, 0.25, 0.6)):                    # trail
                self._frame(p, cx, phi, s * f, _alpha(theme.SKY, 0.12 + 0.05 * k), 1.0)
            u = self._frame(p, cx, phi, f, QColor(theme.CYAN), 1.8)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor("#e8eef6")))
            for lv in range(1, 4):
                for col in (-1, 0, 1):
                    p.drawEllipse(QPointF(cx + col * self.BAY + u[lv], self.BASE - lv * self.STOREY), 2.0, 2.0)
            ground = _alpha(theme.TEXT_DIM, 0.6)
            p.setPen(QPen(ground, 1.0))
            p.drawLine(QPointF(cx - self.BAY - 12, self.BASE), QPointF(cx + self.BAY + 12, self.BASE))
            x = cx - self.BAY - 10
            while x <= cx + self.BAY + 10:
                p.drawLine(QPointF(x, self.BASE), QPointF(x - 4, self.BASE + 5))
                x += 6
            _text(p, f"Mode {m + 1}", cx, self.BASE + 16, LABEL, 9)
        p.restore()
