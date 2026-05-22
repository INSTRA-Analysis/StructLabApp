"""ViewCube: Autodesk-style 3D orientation indicator for the canvas.

Draws a labeled isometric cube in the top-right corner of the viewport.
Clicking a face snaps to that elevation; clicking a top corner snaps to
the nearest isometric view.

Coordinate convention matches the model: +X = right, +Y = back, +Z = up.
"""
from __future__ import annotations

import math

from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QPolygonF, QFont,
)

import ui_qt.projection as _proj

# ── cube geometry ─────────────────────────────────────────────────────────────

# 8 corners ordered as: 0-3 bottom ring, 4-7 top ring
# (+x=Right, +y=Back, +z=Top)
_C: list[tuple[int, int, int]] = [
    (-1, -1, -1),  # 0  Left-Front-Bottom
    (+1, -1, -1),  # 1  Right-Front-Bottom
    (+1, +1, -1),  # 2  Right-Back-Bottom
    (-1, +1, -1),  # 3  Left-Back-Bottom
    (-1, -1, +1),  # 4  Left-Front-Top
    (+1, -1, +1),  # 5  Right-Front-Top
    (+1, +1, +1),  # 6  Right-Back-Top
    (-1, +1, +1),  # 7  Left-Back-Top
]

# (corner_indices, outward_normal, label, target_az, target_el)
# target_az = None  →  keep current azimuth (for Top/Bottom faces)
_FACES: list[tuple] = [
    ((4, 5, 6, 7), ( 0,  0, +1), "Top",   None,    87.0),
    ((0, 1, 2, 3), ( 0,  0, -1), "Btm",   None,   -87.0),
    ((1, 5, 6, 2), (+1,  0,  0), "Right",  90.0,    2.0),
    ((0, 4, 7, 3), (-1,  0,  0), "Left",  -90.0,    2.0),
    ((2, 6, 7, 3), ( 0, +1,  0), "Back",  180.0,    2.0),
    ((0, 1, 5, 4), ( 0, -1,  0), "Front",   0.0,    2.0),
]

# 12 edges as corner-index pairs
_EDGES: list[tuple[int, int]] = [
    (0, 1), (1, 2), (2, 3), (3, 0),   # bottom ring
    (4, 5), (5, 6), (6, 7), (7, 4),   # top ring
    (0, 4), (1, 5), (2, 6), (3, 7),   # verticals
]

# Top 4 corners → isometric view shortcuts
# Each entry: corner_index → (target_az_deg, target_el_deg)
_ISO: dict[int, tuple[float, float]] = {
    6: (-45.0,  30.0),   # Right-Back-Top  → SW default
    5: ( 45.0,  30.0),   # Right-Front-Top → SE
    7: (-135.0, 30.0),   # Left-Back-Top   → NW
    4: ( 135.0, 30.0),   # Left-Front-Top  → NE
}

# ── palette ───────────────────────────────────────────────────────────────────
_CF   = QColor( 68,  68,  80, 218)   # face
_CFF  = QColor( 90,  90, 104, 225)   # top face (slightly brighter)
_CFH  = QColor(  0, 175, 198, 228)   # face hovered
_CE   = QColor(112, 112, 126)        # edge
_CEH  = QColor(  0, 218, 238)        # edge hovered (unused for now)
_CL   = QColor(192, 192, 208)        # face label
_CLH  = QColor(255, 255, 255)        # face label hovered
_CCP  = QColor(  0, 170, 198, 200)   # corner dot
_CCH  = QColor(  0, 232, 255, 255)   # corner dot hovered
_CBG  = QColor( 26,  26,  33, 195)   # background circle fill


class ViewCube:
    """Autodesk-style ViewCube that draws in the canvas top-right corner.

    All drawing and hit-testing work in SCENE coordinates, using the current
    view scale to compensate so the widget stays at a fixed screen size.
    """

    HALF:   int = 42   # cube half-radius in screen pixels
    MARGIN: int = 15   # corner margin from viewport edge in screen pixels
    CRAD:   int = 7    # corner-dot radius in screen pixels

    def __init__(self) -> None:
        self.hovered: str | None = None   # e.g. 'face:Top', 'corner:6', or None

    # ── public API ────────────────────────────────────────────────────────────

    def scene_center(self, rect: QRectF, scale: float) -> tuple[float, float]:
        """Return cube centre (cx, cy) in scene coordinates."""
        offset = (self.MARGIN + self.HALF) / scale
        return rect.right() - offset, rect.top() + offset

    def paint(self, painter: QPainter,
              cx: float, cy: float, scale: float) -> None:
        """Draw the ViewCube centred at (cx, cy) in scene coordinates."""
        az = _proj.ISO_AZIMUTH
        el = _proj.ISO_ELEVATION
        pts  = self._project(cx, cy, az, el, scale)
        cam  = _cam_dir(az, el)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Circular background
        bg_r = (self.HALF + 14) / scale
        bg_p = QPen(QColor(52, 52, 62, 160)); bg_p.setCosmetic(True)
        painter.setPen(bg_p)
        painter.setBrush(QBrush(_CBG))
        painter.drawEllipse(QPointF(cx, cy), bg_r, bg_r)

        # Visible faces — sorted back → front for correct painter's algorithm
        for depth, fi in _sorted_visible(cam):
            corners, normal, label, faz, fel = _FACES[fi]
            hov = (self.hovered == f"face:{label}")
            col = _CFH if hov else (_CFF if normal[2] > 0.5 else _CF)
            fp  = QPen(QColor(100, 100, 115) if not hov else _CEH)
            fp.setCosmetic(True)
            painter.setBrush(QBrush(col))
            painter.setPen(fp)
            painter.drawPolygon(QPolygonF([QPointF(*pts[c]) for c in corners]))

            # Label on faces pointing toward camera
            dot = _dot(normal, cam)
            if dot > 0.08:
                fx = sum(pts[c][0] for c in corners) / 4
                fy = sum(pts[c][1] for c in corners) / 4
                lp = QPen(_CLH if hov else _CL); lp.setCosmetic(True)
                painter.setPen(lp)
                f = QFont("Arial", 7); f.setBold(True)
                painter.setFont(f)
                half_w = len(label) * 4.2 / scale
                painter.drawText(QPointF(fx - half_w, fy + 4.5 / scale), label)

        # Edges
        ep = QPen(_CE); ep.setCosmetic(True); ep.setWidthF(1.1)
        painter.setPen(ep)
        for a, b in _EDGES:
            painter.drawLine(QPointF(*pts[a]), QPointF(*pts[b]))

        # Iso corner dots (top 4 only)
        for ci in (4, 5, 6, 7):
            hov = (self.hovered == f"corner:{ci}")
            cc  = _CCH if hov else _CCP
            r   = (self.CRAD + 2 if hov else self.CRAD) / scale
            painter.setBrush(QBrush(cc))
            cp  = QPen(cc); cp.setCosmetic(True)
            painter.setPen(cp)
            painter.drawEllipse(QPointF(*pts[ci]), r, r)

        painter.restore()

    def update_hover(self, scene_pos: QPointF | None,
                     cx: float, cy: float, scale: float) -> bool:
        """Update hovered region; return True if state changed (repaint needed)."""
        old = self.hovered
        self.hovered = self._hit(scene_pos, cx, cy, scale) if scene_pos else None
        return self.hovered != old

    def hit_test(self, scene_pos: QPointF,
                 cx: float, cy: float,
                 scale: float,
                 current_az: float) -> tuple[float, float] | None:
        """Return (target_az, target_el) for a click, or None if outside cube."""
        h = self._hit(scene_pos, cx, cy, scale)
        if h is None:
            return None
        if h.startswith("corner:"):
            return _ISO[int(h.split(":")[1])]
        label = h.split(":")[1]
        for (_, _, lbl, faz, fel) in _FACES:
            if lbl == label:
                return (current_az if faz is None else faz, fel)
        return None

    def bounding_radius_scene(self, scale: float) -> float:
        """Outer radius of the ViewCube widget in scene units (for quick bounds check)."""
        return (self.HALF + self.MARGIN) / scale

    # ── internals ─────────────────────────────────────────────────────────────

    def _project(self, cx: float, cy: float,
                 az_deg: float, el_deg: float,
                 scale: float) -> list[tuple[float, float]]:
        h  = self.HALF / scale
        az = math.radians(az_deg)
        el = math.radians(el_deg)
        out = []
        for x, y, z in _C:
            x1 =  x * math.cos(az) + y * math.sin(az)
            y1 = -x * math.sin(az) + y * math.cos(az)
            out.append((cx + x1 * h,
                        cy + (y1 * math.sin(el) - z * math.cos(el)) * h))
        return out

    def _hit(self, sp: QPointF | None,
             cx: float, cy: float, scale: float) -> str | None:
        if sp is None:
            return None
        az = _proj.ISO_AZIMUTH
        el = _proj.ISO_ELEVATION
        pts = self._project(cx, cy, az, el, scale)
        cam = _cam_dir(az, el)
        cr  = (self.CRAD + 2) / scale

        # Corner dots take priority (smaller targets, drawn on top)
        for ci in (4, 5, 6, 7):
            if math.hypot(sp.x() - pts[ci][0], sp.y() - pts[ci][1]) <= cr:
                return f"corner:{ci}"

        # Visible faces, checked front → back
        for _, fi in sorted(_sorted_visible(cam), key=lambda t: -t[0]):
            corners = _FACES[fi][0]
            poly = QPolygonF([QPointF(*pts[c]) for c in corners])
            if poly.containsPoint(sp, Qt.FillRule.OddEvenFill):
                return f"face:{_FACES[fi][2]}"

        return None


# ── module helpers ────────────────────────────────────────────────────────────

def _cam_dir(az_deg: float, el_deg: float) -> tuple[float, float, float]:
    """Unit vector pointing FROM origin TOWARD the camera in model space."""
    az = math.radians(az_deg)
    el = math.radians(el_deg)
    return (
        -math.sin(az) * math.cos(el),
         math.cos(az) * math.cos(el),
         math.sin(el),
    )


def _dot(a: tuple, b: tuple) -> float:
    return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]


def _sorted_visible(cam: tuple) -> list[tuple[float, int]]:
    """Return (depth, face_index) for faces with dot > threshold, sorted back→front."""
    result = []
    for i, (corners, normal, *_) in enumerate(_FACES):
        dot = _dot(normal, cam)
        if dot > -0.12:
            avg_depth = sum(_C[c][2] for c in corners) / 4 * cam[2]
            result.append((avg_depth, i))
    result.sort()
    return result
