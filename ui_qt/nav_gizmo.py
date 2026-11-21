"""Navigation gizmo: Blender-style axis balls for the 3D canvas (replaces the ViewCube).

Six balls on a faint disc show the world axes as seen from the current view: the positive
ends are coloured and lettered (X red, Y green, Z blue), the negative ends are smaller and
dimmer. Clicking a ball looks along that axis (+X → Right view, -Y → Front view, +Z → Top
…); the small round button at the lower left returns to the home view. Right-click opens
the named-views menu (handled by the canvas).

The interface matches the old ViewCube, so the canvas positions, hit-tests and repaints it
the same way: centre at (width - (MARGIN + HALF), MARGIN + HALF) in viewport pixels.
Coordinate convention: +X = right, +Y = back, +Z = up.
"""

from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPolygonF

import ui_qt.projection as _proj
from ui_qt import theme

# Named views for the right-click menu: name → (az, el); az None = keep current azimuth.
NAMED_VIEWS: list[tuple[str, float | None, float]] = [
    ("Top",       None,   90.0),
    ("Bottom",    None,  -90.0),
    ("Front",      0.0,    0.0),
    ("Back",     180.0,    0.0),
    ("Right",     90.0,    0.0),
    ("Left",     -90.0,    0.0),
    ("Isometric", -45.0,  30.0),
]

# (key, unit vector, label, colour, target az (None = keep), target el)
_AXES: list[tuple[str, tuple[int, int, int], str, str, float | None, float]] = [
    ("+X", (1, 0, 0),  "X", theme.AXIS_X,  90.0,   0.0),
    ("-X", (-1, 0, 0), "",  theme.AXIS_X, -90.0,   0.0),
    ("+Y", (0, 1, 0),  "Y", theme.AXIS_Y, 180.0,   0.0),
    ("-Y", (0, -1, 0), "",  theme.AXIS_Y,   0.0,   0.0),
    ("+Z", (0, 0, 1),  "Z", theme.AXIS_Z,  None,  90.0),
    ("-Z", (0, 0, -1), "",  theme.AXIS_Z,  None, -90.0),
]


class NavGizmo:
    """Axis-ball orientation gizmo drawn in the canvas top-right corner."""

    HALF:   int = 48    # disc radius in screen pixels
    MARGIN: int = 14    # gap between the disc and the viewport edge
    ARM:    int = 34    # distance from the centre to a ball
    BALL:   float = 9.0     # positive-axis ball radius
    BALL_NEG: float = 6.5   # negative-axis ball radius
    HOME:   int = 11    # home button radius

    def __init__(self) -> None:
        self.hovered: str | None = None   # '+X' … '-Z', 'home', 'disc' or None
        self.home_az: float = -45.0       # default SW isometric — editable via menu
        self.home_el: float = 30.0

    # ── public API (same as the old ViewCube) ─────────────────────────────────

    def paint(self, painter: QPainter, cx: float, cy: float, scale: float) -> None:
        """Draw the gizmo centred at (cx, cy)."""
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Disc — faint, a touch brighter while the pointer is over the gizmo
        disc_r = self.HALF / scale
        over = self.hovered is not None
        painter.setPen(QPen(QColor(255, 255, 255, 34 if over else 18), 1.0 / scale))
        painter.setBrush(QBrush(QColor(255, 255, 255, 26 if over else 12)))
        painter.drawEllipse(QPointF(cx, cy), disc_r, disc_r)

        # Balls back → front so the near ones overlap the far ones
        balls = self._balls(cx, cy, scale)
        for key, (bx, by, depth) in sorted(balls.items(), key=lambda kv: kv[1][2]):
            _, _, label, colour, _, _ = _axis(key)
            positive = key.startswith("+")
            hov = self.hovered == key
            col = QColor(colour)
            if positive:
                # Connector line from the centre, then the lettered ball
                line = QPen(col, 2.0 / scale)
                line.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(line)
                painter.drawLine(QPointF(cx, cy), QPointF(bx, by))
                r = (self.BALL + (1.5 if hov else 0.0)) / scale
                painter.setPen(QPen(QColor("#ffffff") if hov else col.darker(130), 1.2 / scale))
                painter.setBrush(QBrush(col.lighter(118) if hov else col))
                painter.drawEllipse(QPointF(bx, by), r, r)
                f = QFont("Segoe UI"); f.setPointSizeF(7.5 / scale); f.setBold(True)
                painter.setFont(f)
                painter.setPen(QPen(QColor("#15161a")))
                painter.drawText(QRectF(bx - r, by - r, 2 * r, 2 * r),
                                 Qt.AlignmentFlag.AlignCenter, label)
            else:
                r = (self.BALL_NEG + (1.5 if hov else 0.0)) / scale
                fill = QColor(col); fill.setAlpha(150 if hov else 70)
                painter.setPen(QPen(QColor("#ffffff") if hov else col, 1.2 / scale))
                painter.setBrush(QBrush(fill))
                painter.drawEllipse(QPointF(bx, by), r, r)

        # Home button — lower left of the disc
        hx, hy = self._home_center(cx, cy, scale)
        hr = self.HOME / scale
        hov = self.hovered == "home"
        painter.setPen(QPen(QColor(theme.CYAN) if hov else QColor(theme.BORDER), 1.0 / scale))
        painter.setBrush(QBrush(QColor(theme.SURFACE2)))
        painter.drawEllipse(QPointF(hx, hy), hr, hr)
        s = hr * 1.1
        icon = QPen(QColor(theme.CYAN) if hov else QColor(theme.TEXT), 1.3 / scale)
        icon.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(icon)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolyline(QPolygonF([
            QPointF(hx - s * 0.42, hy - s * 0.02), QPointF(hx, hy - s * 0.42),
            QPointF(hx + s * 0.42, hy - s * 0.02),
        ]))
        painter.drawRect(QRectF(hx - s * 0.28, hy - s * 0.06, s * 0.56, s * 0.40))

        painter.restore()

    def update_hover(self, pos: QPointF | None, cx: float, cy: float, scale: float) -> bool:
        """Update the hovered region; True if it changed (repaint needed)."""
        old = self.hovered
        self.hovered = self._hit(pos, cx, cy, scale) if pos is not None else None
        return self.hovered != old

    def hit_test(self, pos: QPointF, cx: float, cy: float, scale: float,
                 current_az: float) -> tuple[float, float] | None:
        """(target az, target el) for a click on a ball or the home button, else None."""
        h = self._hit(pos, cx, cy, scale)
        if h is None or h == "disc":
            return None
        if h == "home":
            return (self.home_az, self.home_el)
        _, _, _, _, az, el = _axis(h)
        return (current_az if az is None else az, el)

    def contains(self, pos: QPointF, cx: float, cy: float, scale: float) -> bool:
        """True if the point is over the disc or the home button."""
        return self._hit(pos, cx, cy, scale) is not None

    # ── internals ─────────────────────────────────────────────────────────────

    def _balls(self, cx: float, cy: float, scale: float) -> dict[str, tuple[float, float, float]]:
        """Screen position and depth (toward the camera = larger) of each axis ball."""
        az = math.radians(_proj.ISO_AZIMUTH)
        el = math.radians(_proj.ISO_ELEVATION)
        cam = _proj.camera_dir(_proj.ISO_AZIMUTH, _proj.ISO_ELEVATION)
        arm = self.ARM / scale
        out: dict[str, tuple[float, float, float]] = {}
        for key, (x, y, z), *_ in _AXES:
            sx = x * math.cos(az) + y * math.sin(az)
            sy = (-x * math.sin(az) + y * math.cos(az)) * math.sin(el) - z * math.cos(el)
            depth = x * cam[0] + y * cam[1] + z * cam[2]
            out[key] = (cx + sx * arm, cy + sy * arm, depth)
        return out

    def _home_center(self, cx: float, cy: float, scale: float) -> tuple[float, float]:
        d = (self.HALF * 0.80) / scale
        return (cx - d, cy + d)

    def _hit(self, pos: QPointF | None, cx: float, cy: float, scale: float) -> str | None:
        if pos is None:
            return None
        hx, hy = self._home_center(cx, cy, scale)
        if math.hypot(pos.x() - hx, pos.y() - hy) <= (self.HOME + 2) / scale:
            return "home"
        # Nearest ball first (front to back) so an overlapped far ball never steals a click
        for key, (bx, by, _) in sorted(self._balls(cx, cy, scale).items(),
                                       key=lambda kv: -kv[1][2]):
            radius = self.BALL if key.startswith("+") else self.BALL_NEG
            if math.hypot(pos.x() - bx, pos.y() - by) <= (radius + 2) / scale:
                return key
        if math.hypot(pos.x() - cx, pos.y() - cy) <= self.HALF / scale:
            return "disc"
        return None


def _axis(key: str) -> tuple:
    for entry in _AXES:
        if entry[0] == key:
            return entry
    raise KeyError(key)
