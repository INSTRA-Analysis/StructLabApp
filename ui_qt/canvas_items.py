"""Visual QGraphicsItems for the StructLab canvas: NodeItem and MemberItem.

Extracted from canvas.py to keep the scene-management and rendering concerns
separate.  No scene-management logic here — just how nodes and members look.
"""

from __future__ import annotations

import math

import numpy as np

from PyQt6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsLineItem, QGraphicsItem, QGraphicsPathItem,
    QGraphicsSimpleTextItem, QStyle,
)
from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QPen, QBrush, QColor, QPainterPath, QFont, QTransform, QPolygonF

from ui_qt.model_state import (
    ModelState, NodeData, MemberData,
    SupportType, ElementType, PointLoadData,
    LoadCase, NodeLoad, MemberLoad,
)
from ui_qt.projection import isometric, is_3d_model, inverse_isometric
import ui_qt.projection as _proj_mod

# ── local axis triad toggle ───────────────────────────────────────────────────
_SHOW_LOCAL_AXES_ALL: bool = False

def set_show_local_axes(show: bool) -> None:
    global _SHOW_LOCAL_AXES_ALL
    _SHOW_LOCAL_AXES_ALL = show

_VERT_THRESHOLD = 0.95   # same as FrameElement._VERTICAL_THRESHOLD

def _compute_local_axes(xi: float, yi: float, zi: float,
                        xj: float, yj: float, zj: float,
                        beta_rad: float
                        ) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    """Return (x̂, ŷ, ẑ) local axis triad matching the solver convention."""
    dx, dy, dz = xj - xi, yj - yi, zj - zi
    L = math.sqrt(dx*dx + dy*dy + dz*dz)
    if L < 1e-12:
        return None
    x_hat = np.array([dx/L, dy/L, dz/L])
    ref   = np.array([0.0, 0.0, 1.0])
    if abs(np.dot(x_hat, ref)) > _VERT_THRESHOLD:
        z_hat = np.cross(x_hat, np.array([1.0, 0.0, 0.0]))
    else:
        z_hat = np.cross(x_hat, ref)
    z_hat /= np.linalg.norm(z_hat)
    y_hat = np.cross(z_hat, x_hat)
    if beta_rad != 0.0:
        cb, sb  = math.cos(beta_rad), math.sin(beta_rad)
        y_hat, z_hat = cb*y_hat + sb*z_hat, -sb*y_hat + cb*z_hat
    return x_hat, y_hat, z_hat

# ── visual constants ──────────────────────────────────────────────────────────
PX_PER_M   = 80
GRID_STEP  = PX_PER_M          # major grid lines every 1 m
GRID_SUB   = GRID_STEP // 4    # minor grid lines every 0.25 m
NODE_R     = 6
SNAP_PX    = NODE_R * 3
_SUPP_S_PX      = 16.0                    # base support-glyph unit, screen-px at zoom=1
_SUPP_S_M       = _SUPP_S_PX / PX_PER_M   # ~0.20 m
_SUPP_STANDOFF_M = NODE_R / PX_PER_M      # gap between the node dot and glyph geometry
ARROW_LEN  = 40                # px — nodal load arrow shaft
ARROW_HEAD = 7                 # px — arrowhead half-width
UDL_LEN    = 22                # px — UDL arrow shaft

_BEAM_PEN  = QPen(QColor("#2255cc"), 2)
_BAR_PEN   = QPen(QColor("#22aa44"), 2)
_GHOST_PEN = QPen(QColor("#aaaaaa"), 1, Qt.PenStyle.DashLine)
_LOAD_PEN  = QPen(QColor("#cc2200"), 2.5)
_UDL_PEN   = QPen(QColor("#cc2200"), 1)
_LAT_PEN   = QPen(QColor("#E65100"), 1.5)   # orange — lateral (global X) loads

_LABEL_COLOR = QColor("#cc2200")
_LABEL_FONT  = QFont()
_LABEL_FONT.setPointSize(7)
_LABEL_FONT.setBold(True)


# ── member group colouring ("Colour by Group" view mode) ──────────────────────
# Fixed colours for the common structural roles so the same label always renders
# the same colour regardless of insertion order; everything else cycles through
# a distinct fallback palette.
_GROUP_FIXED: dict[str, str] = {
    "leg":        "#d62728",  # red    — primary load-carrying legs
    "diagonal":   "#1f77b4",  # blue   — diagonal bracing
    "horizontal": "#2ca02c",  # green  — horizontal / plan bracing
    "bracing":    "#9467bd",  # purple
    "redundant":  "#7f7f7f",  # grey
    "chord":      "#ff7f0e",  # orange
    "post":       "#17becf",  # cyan
}
_GROUP_PALETTE: list[str] = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#17becf", "#bcbd22", "#7f7f7f",
]
_group_colour_cache: dict[str, QColor] = {}


def group_colour(group: str) -> QColor:
    """Return a stable QColor for a member group label (case-insensitive).

    Known role names get a fixed colour; unknown labels are hashed onto the
    fallback palette so the mapping is deterministic across runs.
    """
    key = (group or "").strip().lower()
    cached = _group_colour_cache.get(key)
    if cached is not None:
        return cached
    if key in _GROUP_FIXED:
        col = QColor(_GROUP_FIXED[key])
    else:
        h = 0
        for ch in key:
            h = (h * 31 + ord(ch)) & 0xFFFFFFFF
        col = QColor(_GROUP_PALETTE[h % len(_GROUP_PALETTE)])
    _group_colour_cache[key] = col
    return col


def _fmt(value: float, unit: str) -> str:
    """Format a load value compactly: 3 sig-figs, strip trailing zeros."""
    abs_v = abs(value)
    if abs_v >= 100:
        s = f"{value:.0f}"
    elif abs_v >= 10:
        s = f"{value:.1f}".rstrip("0").rstrip(".")
    else:
        s = f"{value:.2f}".rstrip("0").rstrip(".")
    return f"{s} {unit}"


def _make_label(text: str, sx: float, sy: float, z: float = 1.8,
                color: QColor | None = None) -> QGraphicsSimpleTextItem:
    lbl = QGraphicsSimpleTextItem(text)
    lbl.setFont(_LABEL_FONT)
    lbl.setBrush(QBrush(color if color else _LABEL_COLOR))
    lbl.setPos(sx, sy)
    lbl.setZValue(z)
    return lbl


def m_to_px(m: float) -> float:
    return m * PX_PER_M


def px_to_m(px: float) -> float:
    return px / PX_PER_M


def _display_3d(ms) -> bool:
    """True when the model should be drawn with the 3D isometric projection.

    2D models are always drawn flat, even though their XZ geometry has z != 0.
    """
    if getattr(ms, "is_2d", False):
        return False
    return ms.mode_3d or is_3d_model(ms.nodes)


def _node_pos(node: NodeData, scene=None) -> tuple[float, float]:
    """Return (scene_x, scene_y) for a node.

    3D → isometric; 2D → flat (X right, Y up). 2D is the native XY plane.
    """
    if scene is not None and scene.model_state is not None:
        if _display_3d(scene.model_state):
            return isometric(node.x, node.y, node.z)
    return (m_to_px(node.x), -m_to_px(node.y))


def _proj_x_screen_dir() -> tuple[float, float]:
    """Normalized screen direction of the 3D X axis under the current projection."""
    az = math.radians(_proj_mod.ISO_AZIMUTH)
    el = math.radians(_proj_mod.ISO_ELEVATION)
    sx = math.cos(az)
    sy = -math.sin(az) * math.sin(el)
    mag = math.hypot(sx, sy)
    return (sx / mag, sy / mag) if mag > 1e-9 else (1.0, 0.0)


def _proj_y_screen_dir() -> tuple[float, float]:
    """Normalized screen direction of the 3D Y axis under the current projection."""
    az = math.radians(_proj_mod.ISO_AZIMUTH)
    el = math.radians(_proj_mod.ISO_ELEVATION)
    sx = math.sin(az)
    sy = math.cos(az) * math.sin(el)
    mag = math.hypot(sx, sy)
    return (sx / mag, sy / mag) if mag > 1e-9 else (0.0, 1.0)


def _support_bar_axis_world() -> tuple[float, float, float]:
    """World unit ground-plane axis (X or Y), whichever reads widest on screen
    under the current orbit — keeps FIXED/PIN/ROLLER glyphs' base bar readable
    from any orbit angle (avoids a nearly edge-on bar when one axis nearly
    vanishes on screen). Screen-x extent of world X is cos(az), of world Y is
    sin(az) — independent of elevation.
    """
    az = math.radians(_proj_mod.ISO_AZIMUTH)
    x_bx = math.cos(az)
    y_bx = math.sin(az)
    return (1.0, 0.0, 0.0) if abs(x_bx) >= abs(y_bx) else (0.0, 1.0, 0.0)


# ── true-3D support-glyph geometry primitives ─────────────────────────────────
# Vertices are world-metre offsets FROM THE NODE. isometric() is linear/
# homogeneous (no translation term), so projecting an offset directly gives
# the correct NodeItem-local (child) point — no need to subtract the node's
# own projected position.

def _node_local_pt(dx: float, dy: float, dz: float) -> QPointF:
    sx, sy = isometric(dx, dy, dz)
    return QPointF(sx, sy)


def _project_poly_3d(offsets_m: list[tuple[float, float, float]]) -> QPolygonF:
    return QPolygonF([_node_local_pt(*p) for p in offsets_m])


def _project_path_3d(offsets_m: list[tuple[float, float, float]], closed: bool = True) -> QPainterPath:
    path = QPainterPath()
    pts = [_node_local_pt(*p) for p in offsets_m]
    path.moveTo(pts[0])
    for pt in pts[1:]:
        path.lineTo(pt)
    if closed:
        path.closeSubpath()
    return path


def _project_polyline_3d(strokes: list[list[tuple[float, float, float]]]) -> QPainterPath:
    """One QPainterPath combining several disjoint open polylines (hatch
    lines, arrow segments, a helix/spiral point sequence, ...)."""
    path = QPainterPath()
    for stroke in strokes:
        if not stroke:
            continue
        pts = [_node_local_pt(*p) for p in stroke]
        path.moveTo(pts[0])
        for pt in pts[1:]:
            path.lineTo(pt)
    return path


def _face_towards_camera(offsets_m: list[tuple[float, float, float]]) -> bool:
    """True if a planar face (3+ world-metre points, CCW winding as seen from
    outside the solid) faces the viewer under the current orbit."""
    p0, p1, p2 = (np.array(offsets_m[i]) for i in (0, 1, 2))
    normal = np.cross(p1 - p0, p2 - p0)
    cam = np.array(_proj_mod.camera_dir())
    return float(np.dot(normal, cam)) >= 0.0


def _circle_poly_points(center_m: tuple[float, float, float],
                        u: tuple[float, float, float], v: tuple[float, float, float],
                        radius_m: float, n: int = 12) -> list[tuple[float, float, float]]:
    """N-gon approximating a 3D circle of given radius, centered at center_m
    (world offset), lying in the plane spanned by unit vectors u, v."""
    pts = []
    for i in range(n):
        th = 2 * math.pi * i / n
        pts.append(tuple(center_m[k] + radius_m * (math.cos(th) * u[k] + math.sin(th) * v[k])
                          for k in range(3)))
    return pts


_AXIS_PERP_BASIS: dict[tuple[float, float, float], tuple] = {
    (1.0, 0.0, 0.0):  ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
    (-1.0, 0.0, 0.0): ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
    (0.0, 1.0, 0.0):  ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    (0.0, -1.0, 0.0): ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    (0.0, 0.0, 1.0):  ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
    (0.0, 0.0, -1.0): ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
}


def _perp_basis(axis: tuple[float, float, float]):
    """(u, v) unit vectors perpendicular to axis, for circles/helices/spirals."""
    basis = _AXIS_PERP_BASIS.get(axis)
    if basis is not None:
        return basis
    helper = (0.0, 0.0, 1.0) if abs(axis[2]) < 0.9 else (1.0, 0.0, 0.0)
    u = np.cross(axis, helper); u = tuple(u / np.linalg.norm(u))
    v = tuple(np.cross(axis, u))
    return u, v


def _helix_points(axis: tuple[float, float, float], turns: float, n_per_turn: int,
                  length_m: float, radius_m: float, standoff: float = 0.0
                  ) -> list[tuple[float, float, float]]:
    """Translational-spring coil points: a helix along axis starting at
    `standoff` from the node."""
    u, v = _perp_basis(axis)
    n = max(1, int(turns * n_per_turn))
    pts = []
    for i in range(n + 1):
        t = i / n
        along = standoff + t * length_m
        ang = t * turns * 2 * math.pi
        pts.append(tuple(along * axis[k] + radius_m * (math.cos(ang) * u[k] + math.sin(ang) * v[k])
                          for k in range(3)))
    return pts


def _spiral_points(axis: tuple[float, float, float], wraps: float, n_per_wrap: int,
                   r_start_m: float, r_end_m: float, standoff: float = 0.0
                   ) -> list[tuple[float, float, float]]:
    """Rotational-spring coil points: a flat spiral in the plane perpendicular
    to axis, offset `standoff` along axis from the node."""
    u, v = _perp_basis(axis)
    n = max(1, int(wraps * n_per_wrap))
    pts = []
    for i in range(n + 1):
        t = i / n
        r = r_start_m + t * (r_end_m - r_start_m)
        ang = t * wraps * 2 * math.pi
        pts.append(tuple(standoff * axis[k] + r * (math.cos(ang) * u[k] + math.sin(ang) * v[k])
                          for k in range(3)))
    return pts


# ─────────────────────────────────────────────────────────────────────────────
# NodeItem
# ─────────────────────────────────────────────────────────────────────────────

class NodeItem(QGraphicsEllipseItem):
    """Visual representation of a NodeData on the canvas."""

    def __init__(self, node: NodeData, scene: "StructCanvas") -> None:
        r = NODE_R
        super().__init__(-r, -r, 2 * r, 2 * r)
        self.node = node
        self._scene = scene
        sx, sy = _node_pos(node, scene)
        self.setPos(sx, sy)
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setZValue(2)
        self.setBrush(QBrush(QColor("#2255cc")))
        self.setPen(QPen(QColor("#003399"), 1))
        self._support_items: list = []
        self._hinge_item: QGraphicsEllipseItem | None = None
        self._load_items: list = []
        self._load_label_items: list[QGraphicsSimpleTextItem] = []
        self._draw_support_symbol()
        self._draw_hinge_indicator()
        self._draw_load_symbols()

    def set_movable(self, movable: bool) -> None:
        if movable and is_3d_model(self._scene.model_state.nodes):
            movable = False  # 3D: disable drag, use properties panel for coordinates
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, movable)

    def update_visual_scale(self, view_scale: float) -> None:
        s = max(0.2, min(5.0, view_scale))
        self.setScale(1.0 / s ** 0.3)

    def itemChange(self, change, value):
        ms = self._scene.model_state
        in_3d = _display_3d(ms)

        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            if not in_3d:
                # Snap dragged position to 2D grid
                step = PX_PER_M * 0.25
                x = round(value.x() / step) * step
                y = round(value.y() / step) * step
                return QPointF(x, y)

        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            if not in_3d:
                # Sync NodeData coordinates from 2D scene position (XY plane).
                self.node.x = px_to_m(self.pos().x())
                self.node.y = -px_to_m(self.pos().y())
                # Redraw symbols at new position
                self._draw_support_symbol()
                self._draw_load_symbols()
                # Update all member lines that touch this node
                for mitem in self._scene._member_items.values():
                    m = mitem.member
                    if m.node_i == self.node.id or m.node_j == self.node.id:
                        mitem.update_endpoints()

        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            if value:
                self.setBrush(QBrush(QColor("#ffcc00")))
                self.setPen(QPen(QColor("#ffffff"), 2))
            else:
                self.setBrush(QBrush(QColor("#2255cc")))
                self.setPen(QPen(QColor("#003399"), 1))

        return super().itemChange(change, value)

    def paint(self, painter, option, widget=None) -> None:
        option.state = option.state & ~QStyle.StateFlag.State_Selected
        super().paint(painter, option, widget)

    # ── support symbol ────────────────────────────────────────────────────────

    # ── support glyph item factories ─────────────────────────────────────────

    def _supp_path_item(self, path: QPainterPath, fill: str | None, pen: str = "#ffffff",
                        pw: float = 1.5, z: float = 1.0) -> None:
        # Parent=self so Qt auto-hides this item when NodeItem is hidden.
        # path is built from world-metre offsets via _project_path_3d/_project_poly_3d/
        # _project_polyline_3d (or, for 2D glyphs, plain screen-px QPainterPath).
        it = QGraphicsPathItem(path, self)
        it.setBrush(QBrush(QColor(fill)) if fill is not None else QBrush(Qt.BrushStyle.NoBrush))
        it.setPen(QPen(QColor(pen), pw))
        it.setZValue(z)
        self._support_items.append(it)

    # ── dispatcher ────────────────────────────────────────────────────────────

    def _draw_support_symbol(self) -> None:
        for it in self._support_items:
            self._scene.removeItem(it)
        self._support_items.clear()

        stype = self.node.support_type
        if stype == SupportType.FREE:
            return

        ms = self._scene.model_state
        in_3d = _display_3d(ms)

        _COL = {
            SupportType.FIXED:    ("#c0392b", "#7b241c"),
            SupportType.PIN:      ("#2980b9", "#1a5276"),
            SupportType.ROLLER:   ("#f39c12", "#9a7d0a"),
            SupportType.ROLLER_Y: ("#f39c12", "#9a7d0a"),
            SupportType.ROLLER_Z: ("#00BCD4", "#00838F"),
            SupportType.SPRING:   ("#27ae60", "#1e8449"),
        }
        col, col_dk = _COL.get(stype, ("#cccccc", "#888888"))

        if stype == SupportType.FIXED:
            self._draw_fixed_3d(col, col_dk) if in_3d else self._draw_fixed_2d(col, col_dk)
        elif stype == SupportType.PIN:
            self._draw_pin_3d(col, col_dk) if in_3d else self._draw_pin_2d(col, col_dk)
        elif stype in (SupportType.ROLLER, SupportType.ROLLER_Y):
            axis = "x" if stype == SupportType.ROLLER else "y"
            (self._draw_roller_3d if in_3d else self._draw_roller_2d)(col, col_dk, axis)
        elif stype == SupportType.ROLLER_Z:
            self._draw_roller_z_3d(col, col_dk) if in_3d else self._draw_roller_z_2d_disabled(col)
        elif stype == SupportType.SPRING:
            self._draw_spring_3d(col) if in_3d else self._draw_spring_2d(col)

    # ── FIXED ─────────────────────────────────────────────────────────────────

    def _draw_fixed_3d(self, col: str, col_dk: str) -> None:
        bar = _support_bar_axis_world()
        perp = (-bar[1], bar[0], 0.0)
        half_w, depth, z0 = _SUPP_S_M, 0.6 * _SUPP_S_M, -_SUPP_STANDOFF_M
        corners = [tuple(t * half_w * bar[k] + u * depth * perp[k] + (z0 if k == 2 else 0.0)
                        for k in range(3))
                  for (t, u) in [(-1, 0), (1, 0), (1, 1), (-1, 1)]]
        self._supp_path_item(_project_path_3d(corners), col, col_dk, pw=1.0, z=0.9)

        strokes = []
        for i in range(5):
            t = -1.0 + i * (2.0 / 4)
            p0 = tuple(t * half_w * bar[k] + (z0 if k == 2 else 0.0) for k in range(3))
            p1 = tuple(p0[k] + depth * perp[k] for k in range(3))
            strokes.append([p0, p1])
        strokes.append([(0.0, 0.0, 0.0), (0.0, 0.0, z0)])   # "planted" stem
        self._supp_path_item(_project_polyline_3d(strokes), None, col_dk, pw=1.2, z=1.0)

    def _draw_fixed_2d(self, col: str, col_dk: str) -> None:
        s = 14
        plate = QPainterPath()
        plate.moveTo(-s, NODE_R)
        plate.lineTo( s, NODE_R)
        plate.lineTo( s - 4, NODE_R + 8)
        plate.lineTo(-s - 4, NODE_R + 8)
        plate.closeSubpath()
        self._supp_path_item(plate, col, col_dk, pw=0, z=0.9)
        hatch = QPainterPath()
        for i in range(5):
            x = -s + i * (2 * s / 4)
            hatch.moveTo(x, NODE_R)
            hatch.lineTo(x - 6, NODE_R + 8)
        self._supp_path_item(hatch, col, "#ffffff", pw=1.5, z=1.0)

    # ── PIN ───────────────────────────────────────────────────────────────────

    def _draw_pin_3d(self, col: str, col_dk: str) -> None:
        apex = (0.0, 0.0, 0.0)
        h_m, r_b = 1.0 * _SUPP_S_M, 0.55 * _SUPP_S_M
        base = [(r_b * math.cos(math.radians(a)), r_b * math.sin(math.radians(a)), -h_m)
               for a in (45, 135, 225, 315)]
        for k in range(4):
            face = [apex, base[k], base[(k + 1) % 4]]
            front = _face_towards_camera(face)
            self._supp_path_item(_project_path_3d(face), col if front else col_dk,
                                 "#ffffff", pw=1.2, z=(1.0 if front else 0.9))
        ring = _circle_poly_points((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0),
                                   0.22 * _SUPP_S_M, n=10)
        self._supp_path_item(_project_path_3d(ring), None, col_dk, pw=1.4, z=1.1)

    def _draw_pin_2d(self, col: str, col_dk: str) -> None:
        s = 14
        tri = QPainterPath()
        tri.moveTo(0, NODE_R)
        tri.lineTo(-s, s + NODE_R)
        tri.lineTo( s, s + NODE_R)
        tri.closeSubpath()
        self._supp_path_item(tri, col, "#ffffff", pw=1.5)

    # ── ROLLER / ROLLER_Y (shared, parametrized by restrained/free ground axis) ─

    _ROLLER_AXES = {
        "x": ((0.0, -1.0, 0.0), (1.0, 0.0, 0.0)),   # ROLLER:   restrained Y, free X
        "y": ((-1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),   # ROLLER_Y: restrained X, free Y
    }

    def _draw_roller_3d(self, col: str, col_dk: str, axis: str) -> None:
        r_axis, f_axis = self._ROLLER_AXES[axis]
        self._draw_roller_3d_axes(col, col_dk, r_axis, f_axis)

    def _draw_roller_3d_axes(self, col: str, col_dk: str,
                             r_axis: tuple[float, float, float],
                             f_axis: tuple[float, float, float]) -> None:
        z_axis = (0.0, 0.0, 1.0)
        apex = tuple(a * _SUPP_STANDOFF_M for a in r_axis)
        base_center = tuple(a * (_SUPP_STANDOFF_M + _SUPP_S_M) for a in r_axis)
        base = [tuple(base_center[k] + 0.55 * _SUPP_S_M
                     * (math.cos(math.radians(a)) * f_axis[k] + math.sin(math.radians(a)) * z_axis[k])
                     for k in range(3))
               for a in (90, 210, 330)]
        for k in range(3):
            face = [apex, base[k], base[(k + 1) % 3]]
            front = _face_towards_camera(face)
            self._supp_path_item(_project_path_3d(face), col if front else col_dk,
                                 "#ffffff", pw=1.2, z=(1.0 if front else 0.9))

        wheel_centers = [tuple(base_center[k] + sgn * 0.5 * _SUPP_S_M * f_axis[k] for k in range(3))
                         for sgn in (-1, 1)]
        for c in wheel_centers:
            wheel = _circle_poly_points(c, z_axis, r_axis, 0.28 * _SUPP_S_M, n=12)
            self._supp_path_item(_project_path_3d(wheel), None, col_dk, pw=1.2, z=1.1)

        # Slide-direction arrow, placed past the wheels along r so it never
        # crosses the wedge/wheel body.
        arrow_c = tuple(base_center[k] + r_axis[k] * 0.6 * _SUPP_S_M for k in range(3))
        shaft = 1.6 * _SUPP_S_M
        p0 = tuple(arrow_c[k] - f_axis[k] * shaft / 2 for k in range(3))
        p1 = tuple(arrow_c[k] + f_axis[k] * shaft / 2 for k in range(3))
        strokes = [[p0, p1]]
        second = z_axis if abs(f_axis[2]) < 0.9 else r_axis
        head = 0.28 * _SUPP_S_M
        for tip, d in ((p0, tuple(-c for c in f_axis)), (p1, f_axis)):
            for sgn in (-1, 1):
                wing = tuple(0.85 * d[k] + sgn * 0.55 * second[k] for k in range(3))
                end = tuple(tip[k] + head * wing[k] for k in range(3))
                strokes.append([tip, end])
        self._supp_path_item(_project_polyline_3d(strokes), None, "#ffffff", pw=1.6, z=1.2)

    def _draw_roller_2d(self, col: str, col_dk: str, axis: str) -> None:
        s = 14
        if axis == "y":   # ROLLER_Y: horizontal roller, symbol to the left of the node
            tri = QPainterPath()
            tri.moveTo(-NODE_R, 0)
            tri.lineTo(-(s + NODE_R), -s)
            tri.lineTo(-(s + NODE_R),  s)
            tri.closeSubpath()
            self._supp_path_item(tri, col, "#ffffff", pw=1.5)
            wheels = QPainterPath()
            wheels.addEllipse(-(s + NODE_R + 11), -s,      8, 8)
            wheels.addEllipse(-(s + NODE_R + 11), -s + 12, 8, 8)
            self._supp_path_item(wheels, col_dk, "#ffffff", pw=1.0)
        else:              # ROLLER: vertical roller, symbol below the node
            tri = QPainterPath()
            tri.moveTo(0, NODE_R)
            tri.lineTo(-s, s + NODE_R)
            tri.lineTo( s, s + NODE_R)
            tri.closeSubpath()
            self._supp_path_item(tri, col, "#ffffff", pw=1.5)
            wheels = QPainterPath()
            wheels.addEllipse(-s,      s + NODE_R + 3, 8, 8)
            wheels.addEllipse(-s + 12, s + NODE_R + 3, 8, 8)
            self._supp_path_item(wheels, col_dk, "#ffffff", pw=1.0)

    # ── ROLLER_Z (3D-only concept: free in Z, restrained in X & Y) ─────────────

    def _draw_roller_z_3d(self, col: str, col_dk: str) -> None:
        r_axis = _support_bar_axis_world()
        self._draw_roller_3d_axes(col, col_dk, r_axis, (0.0, 0.0, 1.0))

    def _draw_roller_z_2d_disabled(self, col: str) -> None:
        """ROLLER_Z is selectable/importable even for 2D models, where it has
        no meaning (2D has no out-of-plane Z-slide). Show a faded 'assigned
        but inactive' badge instead of the old, meaningless downward triangle."""
        ring = QPainterPath()
        r = NODE_R + 6
        ring.addEllipse(-r, -r, 2 * r, 2 * r)
        it = QGraphicsPathItem(ring, self)
        it.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        pen = QPen(QColor(col), 1.5)
        pen.setStyle(Qt.PenStyle.DashLine)
        it.setPen(pen)
        it.setOpacity(0.55)
        it.setZValue(1.0)
        self._support_items.append(it)
        label = QGraphicsSimpleTextItem("Z̸", self)   # Z with a slash through it
        label.setBrush(QBrush(QColor(col)))
        f = label.font(); f.setPointSize(9); f.setBold(True); label.setFont(f)
        label.setPos(-5, -r - 14)
        label.setOpacity(0.75)
        label.setZValue(1.0)
        self._support_items.append(label)

    # ── SPRING (one coil per active spring constant) ────────────────────────────

    def _draw_spring_3d(self, default_col: str) -> None:
        node = self.node
        helix_len = 2.2 * _SUPP_S_M
        specs = [
            ((1.0, 0.0, 0.0),  node.spring_kx,  node.spring_krx, "#dc3c3c"),   # X — red
            ((0.0, 1.0, 0.0),  node.spring_ky,  node.spring_kry, "#32c832"),   # Y — green
            ((0.0, 0.0, -1.0), node.spring_kz,  node.spring_krz, "#3c6ee6"),   # Z (down) — blue
        ]
        drew_any = False
        for axis, k_trans, k_rot, col_ax in specs:
            if k_trans != 0.0:
                pts = _helix_points(axis, turns=4, n_per_turn=10, length_m=helix_len,
                                    radius_m=0.12 * _SUPP_S_M, standoff=0.0)
                u, _v = _perp_basis(axis)
                end = pts[-1]
                crossbar = [tuple(end[j] - 0.25 * _SUPP_S_M * u[j] for j in range(3)),
                           tuple(end[j] + 0.25 * _SUPP_S_M * u[j] for j in range(3))]
                self._supp_path_item(_project_polyline_3d([pts, crossbar]), None, col_ax, pw=1.6, z=1.0)
                drew_any = True
            if k_rot != 0.0:
                standoff = (helix_len + 0.3 * _SUPP_S_M) if k_trans != 0.0 else 0.4 * _SUPP_S_M
                pts = _spiral_points(axis, wraps=2.5, n_per_wrap=10, r_start_m=0.15 * _SUPP_S_M,
                                     r_end_m=0.5 * _SUPP_S_M, standoff=standoff)
                u, v = _perp_basis(axis)
                tang_ang = 2.5 * 2 * math.pi
                tangent = tuple(-math.sin(tang_ang) * u[j] + math.cos(tang_ang) * v[j] for j in range(3))
                tip = pts[-1]
                arrow_tip = tuple(tip[j] + 0.12 * _SUPP_S_M * tangent[j] for j in range(3))
                self._supp_path_item(_project_polyline_3d([pts, [tip, arrow_tip]]), None, col_ax, pw=1.6, z=1.0)
                drew_any = True
        if not drew_any:
            # No spring constant set yet — show a generic placeholder coil so a
            # freshly-assigned SPRING support isn't invisible.
            pts = _helix_points((0.0, 0.0, -1.0), turns=4, n_per_turn=10, length_m=helix_len,
                                radius_m=0.12 * _SUPP_S_M, standoff=0.0)
            self._supp_path_item(_project_polyline_3d([pts]), None, default_col, pw=1.6, z=1.0)

    def _draw_spring_2d(self, col: str) -> None:
        s = 14
        path = QPainterPath()
        y = NODE_R
        path.moveTo(0, y)
        for i in range(6):
            x = 8 * (1 if i % 2 == 0 else -1)
            path.lineTo(x, y + (i + 1) * 4)
        path.lineTo(0, y + 28)
        path.moveTo(-s, y + 30)
        path.lineTo( s, y + 30)
        self._supp_path_item(path, col, col, pw=1.5)

    # ── hinge indicator ───────────────────────────────────────────────────────

    def _draw_hinge_indicator(self) -> None:
        """Draw an orange ring if this node is the pinned end of any member."""
        if self._hinge_item:
            self._scene.removeItem(self._hinge_item)
            self._hinge_item = None

        is_hinge = any(
            (m.element_type == ElementType.PIN_RIGHT and m.node_j == self.node.id)
            or (m.element_type == ElementType.PIN_LEFT  and m.node_i == self.node.id)
            for m in self._scene.model_state.members
        )
        if not is_hinge:
            return

        hr = NODE_R + 4
        item = QGraphicsEllipseItem(-hr, -hr, 2 * hr, 2 * hr)
        item.setBrush(QBrush(Qt.GlobalColor.transparent))
        item.setPen(QPen(QColor("#FF8C00"), 2.0))
        item.setPos(self.pos())
        item.setZValue(3)
        self._scene.addItem(item)
        self._hinge_item = item

    # ── load arrows ───────────────────────────────────────────────────────────

    def _draw_load_symbols(self, clear: bool = True,
                           color: QColor | None = None, lc_name: str = "") -> None:
        if clear:
            for it in self._load_items:
                self._scene.removeItem(it)
            self._load_items.clear()
            for lbl in self._load_label_items:
                self._scene.removeItem(lbl)
            self._load_label_items.clear()

        nl = self._scene.model_state.active_case.get_node_load(self.node.id)
        if nl.is_zero():
            return

        draw_color = color if color else QColor("#cc2200")
        pen = QPen(draw_color, 2.5)
        prefix = f"{lc_name}: " if lc_name else ""

        path = QPainterPath()
        ah = ARROW_HEAD
        sx, sy = self.pos().x(), self.pos().y()

        ms = self._scene.model_state
        in_3d = _display_3d(ms)

        # Scale arrow length relative to the largest nodal force in this load case
        # so different magnitudes are visually distinguishable.
        _lc = ms.active_case
        _max_nf = max(
            (max(abs(_lc.get_node_load(n.id).fx),
                 abs(_lc.get_node_load(n.id).fy),
                 abs(_lc.get_node_load(n.id).fz),
                 abs(_lc.get_node_load(n.id).moment))
             for n in ms.nodes),
            default=1.0,
        ) or 1.0
        _this_f = max(abs(nl.fx), abs(nl.fy), abs(nl.fz), abs(nl.moment))
        _f_ratio = max(0.35, _this_f / _max_nf)  # floor at 35 % so small loads stay visible
        arr_len = ARROW_LEN * _f_ratio

        if nl.fx != 0.0:
            _r = max(0.35, abs(nl.fx) / _max_nf)
            _len = ARROW_LEN * _r
            sdx = 1.0 if nl.fx > 0 else -1.0
            dir_x, dir_y = _proj_x_screen_dir() if in_3d else (1.0, 0.0)
            tail_x = -sdx * dir_x * _len
            tail_y = -sdx * dir_y * _len
            back_x = -sdx * dir_x * ah
            back_y = -sdx * dir_y * ah
            perp_x, perp_y = -dir_y, dir_x
            path.moveTo(tail_x, tail_y)
            path.lineTo(0, 0)
            path.moveTo(back_x + perp_x * ah * 0.5, back_y + perp_y * ah * 0.5)
            path.lineTo(0, 0)
            path.lineTo(back_x - perp_x * ah * 0.5, back_y - perp_y * ah * 0.5)
            lbl = _make_label(prefix + _fmt(nl.fx / 1e3, "kN"),
                               sx + tail_x - 2, sy + tail_y - 14, color=draw_color)
            self._scene.addItem(lbl)
            self._load_label_items.append(lbl)

        if nl.fy != 0.0:
            # In 3D: fy is global Y (horizontal); project along Y screen axis.
            # In 2D: fy is vertical (screen up/down), dir = (0, -1) in Qt.
            _r = max(0.35, abs(nl.fy) / _max_nf)
            _len = ARROW_LEN * _r
            sdy = 1.0 if nl.fy > 0 else -1.0
            dir_x, dir_y = _proj_y_screen_dir() if in_3d else (0.0, -1.0)
            tail_x = -sdy * dir_x * _len
            tail_y = -sdy * dir_y * _len
            back_x = -sdy * dir_x * ah
            back_y = -sdy * dir_y * ah
            perp_x, perp_y = -dir_y, dir_x
            path.moveTo(tail_x, tail_y)
            path.lineTo(0, 0)
            path.moveTo(back_x + perp_x * ah * 0.5, back_y + perp_y * ah * 0.5)
            path.lineTo(0, 0)
            path.lineTo(back_x - perp_x * ah * 0.5, back_y - perp_y * ah * 0.5)
            lbl = _make_label(prefix + _fmt(nl.fy / 1e3, "kN"),
                               sx + tail_x + 5, sy + tail_y - 8, color=draw_color)
            self._scene.addItem(lbl)
            self._load_label_items.append(lbl)

        if nl.fz != 0.0 and in_3d:
            # fz is global Z (vertical); always projects straight up/down on screen.
            _r = max(0.35, abs(nl.fz) / _max_nf)
            _len = ARROW_LEN * _r
            sdz = 1.0 if nl.fz > 0 else -1.0
            dir_x, dir_y = 0.0, -1.0  # +Z = screen up in Qt
            tail_x = -sdz * dir_x * _len   # = 0
            tail_y = -sdz * dir_y * _len   # = sdz * _len
            back_x = -sdz * dir_x * ah     # = 0
            back_y = -sdz * dir_y * ah     # = sdz * ah
            perp_x, perp_y = -dir_y, dir_x # = 1, 0
            path.moveTo(tail_x, tail_y)
            path.lineTo(0, 0)
            path.moveTo(back_x + perp_x * ah * 0.5, back_y + perp_y * ah * 0.5)
            path.lineTo(0, 0)
            path.lineTo(back_x - perp_x * ah * 0.5, back_y - perp_y * ah * 0.5)
            lbl = _make_label(prefix + _fmt(nl.fz / 1e3, "kN"),
                               sx + 5, sy + tail_y - 8, color=draw_color)
            self._scene.addItem(lbl)
            self._load_label_items.append(lbl)

        if nl.moment != 0.0:
            r = 15
            arc_rect = QRectF(-r, -r, 2 * r, 2 * r)
            span = 270 if nl.moment > 0 else -270
            path.arcMoveTo(arc_rect, 0)
            path.arcTo(arc_rect, 0, span)
            end_rad = math.radians(-span)
            ex = r * math.cos(end_rad)
            ey = -r * math.sin(end_rad)
            tang_x = -math.sin(end_rad) * (1 if nl.moment > 0 else -1)
            tang_y = -math.cos(end_rad) * (1 if nl.moment > 0 else -1)
            aw = 5
            path.moveTo(ex - tang_x * aw - tang_y * aw,
                        ey - tang_y * aw + tang_x * aw)
            path.lineTo(ex, ey)
            path.lineTo(ex - tang_x * aw + tang_y * aw,
                        ey - tang_y * aw - tang_x * aw)
            lbl = _make_label(prefix + _fmt(nl.moment / 1e3, "kN·m"),
                               sx + r + 3, sy - r - 3, color=draw_color)
            self._scene.addItem(lbl)
            self._load_label_items.append(lbl)

        item = QGraphicsPathItem(path)
        item.setPen(pen)
        item.setPos(self.pos())
        item.setZValue(1.5)
        self._scene.addItem(item)
        self._load_items.append(item)

    # ── refresh / cleanup ─────────────────────────────────────────────────────

    def refresh(self) -> None:
        sx, sy = _node_pos(self.node, self._scene)
        self.setPos(sx, sy)
        self._draw_support_symbol()
        self._draw_hinge_indicator()
        self._draw_load_symbols()
        for item in self._scene.items():
            if isinstance(item, MemberItem):
                if item.member.node_i == self.node.id or item.member.node_j == self.node.id:
                    item.refresh()

    def remove_extra_items(self) -> None:
        for it in self._support_items:
            it.setParentItem(None)   # children — detach from NodeItem, Qt removes from scene
        self._support_items.clear()
        if self._hinge_item:
            self._scene.removeItem(self._hinge_item)
            self._hinge_item = None
        for it in self._load_items:
            self._scene.removeItem(it)
        self._load_items.clear()
        for lbl in self._load_label_items:
            self._scene.removeItem(lbl)
        self._load_label_items.clear()

    def set_visible_all(self, visible: bool) -> None:
        """Show or hide this node and all its decorators (supports, hinges, loads)."""
        self.setVisible(visible)
        for it in self._support_items:
            it.setVisible(visible)
        if self._hinge_item:
            self._hinge_item.setVisible(visible)
        for it in self._load_items:
            it.setVisible(visible)
        for it in self._load_label_items:
            it.setVisible(visible)

    def set_loads_visible(self, visible: bool) -> None:
        """Show or hide only nodal load arrows/labels (leaves supports/hinges untouched)."""
        for it in self._load_items:
            it.setVisible(visible)
        for it in self._load_label_items:
            it.setVisible(visible)

    def remove_support_symbol(self) -> None:
        for it in self._support_items:
            it.setParentItem(None)   # children — detach, Qt removes from scene
        self._support_items.clear()


# ─────────────────────────────────────────────────────────────────────────────
# MemberItem
# ─────────────────────────────────────────────────────────────────────────────

class MemberItem(QGraphicsLineItem):
    """Visual representation of a MemberData on the canvas."""

    def __init__(self, member: MemberData, node_i: NodeData, node_j: NodeData,
                 scene: "StructCanvas") -> None:
        ix, iy = _node_pos(node_i, scene)
        jx, jy = _node_pos(node_j, scene)
        super().__init__(ix, iy, jx, jy)
        self.member = member
        self._scene = scene
        self._base_pen: QPen | None = None
        self._is_selected: bool = False
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setZValue(1)
        self._udl_items: list = []
        self._udl_label_items: list = []
        self._qx_items: list = []
        self._qx_label_items: list = []
        self._qy_items: list = []
        self._qy_label_items: list = []
        self._qz_items: list = []
        self._qz_label_items: list = []
        self._point_load_items: list = []
        self._partial_items: list = []
        self._update_pen()
        self._draw_udl_arrows()
        self._draw_lateral_arrows()
        self._draw_point_loads()
        self._draw_partial_load_arrows()

    def update_endpoints(self) -> None:
        """Redraw line and load arrows after a connected node has moved."""
        ni = self._scene.model_state.get_node(self.member.node_i)
        nj = self._scene.model_state.get_node(self.member.node_j)
        if ni and nj:
            ix, iy = _node_pos(ni, self._scene)
            jx, jy = _node_pos(nj, self._scene)
            self.setLine(ix, iy, jx, jy)
            self._draw_udl_arrows()
            self._draw_lateral_arrows()
            self._draw_point_loads()
            self._draw_partial_load_arrows()

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self._is_selected = bool(value)
            self._apply_pen()
        return super().itemChange(change, value)

    def paint(self, painter, option, widget=None) -> None:
        option.state = option.state & ~QStyle.StateFlag.State_Selected
        super().paint(painter, option, widget)
        if self._scene.model_state.mode_3d and (_SHOW_LOCAL_AXES_ALL or self._is_selected):
            ni = self._scene.model_state.get_node(self.member.node_i)
            nj = self._scene.model_state.get_node(self.member.node_j)
            if ni and nj:
                self._paint_triad(painter, ni, nj)

    def _paint_triad(self, painter, ni: "NodeData", nj: "NodeData") -> None:
        """Draw local axis triad (x̂=red, ŷ=green, ẑ=blue) at member midpoint."""
        views = self._scene.views()
        if not views:
            return
        scale = views[0].transform().m11()
        arm_m = 28.0 / (PX_PER_M * scale)   # fixed ~28 screen-px arms

        axes = _compute_local_axes(ni.x, ni.y, ni.z, nj.x, nj.y, nj.z,
                                   self.member.beta_angle)
        if axes is None:
            return
        mx, my, mz = (ni.x + nj.x) / 2, (ni.y + nj.y) / 2, (ni.z + nj.z) / 2
        sx0, sy0 = isometric(mx, my, mz)

        painter.save()
        ah = 5.0 / scale   # arrowhead size in scene units
        for vec, rgb in [
            (axes[0], (220,  60,  60)),   # x̂ — red
            (axes[1], ( 50, 200,  50)),   # ŷ — green
            (axes[2], ( 60, 110, 230)),   # ẑ — blue
        ]:
            ex = mx + arm_m * float(vec[0])
            ey = my + arm_m * float(vec[1])
            ez = mz + arm_m * float(vec[2])
            sx1, sy1 = isometric(ex, ey, ez)
            col = QColor(*rgb)
            pen = QPen(col); pen.setCosmetic(True); pen.setWidthF(1.8)
            painter.setPen(pen)
            painter.drawLine(QPointF(sx0, sy0), QPointF(sx1, sy1))
            # Arrowhead
            ddx, ddy = sx1 - sx0, sy1 - sy0
            dlen = math.hypot(ddx, ddy)
            if dlen > 1e-6:
                ux, uy = ddx / dlen, ddy / dlen
                px, py = -uy * ah * 0.45, ux * ah * 0.45
                tip = QPointF(sx1, sy1)
                b1  = QPointF(sx1 - ux*ah + px, sy1 - uy*ah + py)
                b2  = QPointF(sx1 - ux*ah - px, sy1 - uy*ah - py)
                painter.setBrush(QBrush(col))
                painter.setPen(QPen(Qt.PenStyle.NoPen))
                painter.drawPolygon(QPolygonF([tip, b1, b2]))
                painter.setBrush(QBrush())
        painter.restore()

    def _apply_pen(self) -> None:
        if self._is_selected:
            self.setPen(QPen(QColor("#ffcc00"), 5))
        elif self._base_pen is not None:
            self.setPen(self._base_pen)

    def _base_colour_pen(self, width: float) -> QPen:
        """Default member pen: group colour when 'Colour by Group' is on, else
        the element-type colour (green = bar, blue = beam)."""
        if getattr(self._scene, "_colour_by_group", False) and self.member.group:
            pen = QPen(group_colour(self.member.group))
        else:
            pen = QPen(_BAR_PEN if self.member.element_type == ElementType.BAR
                       else _BEAM_PEN)
        pen.setWidthF(width)
        return pen

    def _update_pen(self) -> None:
        self._base_pen = self._base_colour_pen(3)
        self._apply_pen()

    def update_visual_scale(self, view_scale: float) -> None:
        if self._is_selected:
            return
        s = max(0.2, min(5.0, view_scale))
        w = 3.0 / s ** 0.3
        self._base_pen = self._base_colour_pen(w)
        self._apply_pen()

    def set_force_colour(self, N: float, max_N: float) -> None:
        """Colour member by axial force: red=compression, blue=tension."""
        if max_N < 1e-12:
            self._update_pen()
            return
        t = min(abs(N) / max_N, 1.0)
        # Interpolate from light (t=0) to saturated (t=1)
        if N > 0:   # compression → red
            r, g, b = int(220), int(180 - 170 * t), int(180 - 170 * t)
        elif N < 0:  # tension → blue
            r, g, b = int(180 - 170 * t), int(180 - 170 * t), int(220)
        else:
            r, g, b = 160, 160, 160
        self._base_pen = QPen(QColor(r, g, b), 4)
        self._apply_pen()

    def set_util_colour(self, eta: float) -> None:
        """Colour member by utilization ratio η: green→yellow→red (0→1→>1)."""
        eta = max(0.0, eta)
        if eta <= 0.5:
            # green (0,200,80) → yellow (230,210,0)
            t = eta / 0.5
            r = int(0   + 230 * t)
            g = int(200 - 200 * t + 210 * t)   # 200 → 210
            bv = int(80 - 80 * t)
        elif eta <= 1.0:
            # yellow (230,210,0) → orange-red (230,60,0)
            t = (eta - 0.5) / 0.5
            r = int(230)
            g = int(210 - 150 * t)
            bv = 0
        else:
            # red (220,40,0) — clamped above 1.0, brighter for over-stressed
            sat = min((eta - 1.0) / 0.5, 1.0)
            r = int(220 + 35 * sat)
            g = int(40  - 40 * sat)
            bv = 0
        self._base_pen = QPen(QColor(min(r, 255), max(g, 0), max(bv, 0)), 4)
        self._apply_pen()

    # ── distributed load arrows (UDL / UVL) ──────────────────────────────────

    def _draw_udl_arrows(self, clear: bool = True, color: QColor | None = None,
                         perp_offset: float = 0.0, lc_name: str = "") -> None:
        if clear:
            for it in self._udl_items: self._scene.removeItem(it)
            self._udl_items.clear()
            for it in self._udl_label_items: self._scene.removeItem(it)
            self._udl_label_items.clear()

        ml = self._scene.model_state.active_case.get_member_load(self.member.id)
        w_start, w_end = ml.net("w")
        if w_start == 0.0 and w_end == 0.0:
            return

        ni = self._scene.model_state.get_node(self.member.node_i)
        nj = self._scene.model_state.get_node(self.member.node_j)
        if not ni or not nj:
            return

        ix, iy = _node_pos(ni, self._scene)
        jx, jy = _node_pos(nj, self._scene)
        dx = jx - ix;  dy = jy - iy
        L_px = math.hypot(dx, dy)
        if L_px < 1:
            return

        ux, uy = dx / L_px, dy / L_px
        # Member normal in screen coords (used for LC group stacking offset)
        px_n_m, py_n_m = -uy, ux
        # Arrow direction: gravity (screen-down) in 3D, member-perpendicular in 2D
        ms = self._scene.model_state
        in_3d = _display_3d(ms)
        if in_3d:
            px_n, py_n = 0.0, 1.0
        else:
            px_n, py_n = px_n_m, py_n_m

        w_ref = w_start if abs(w_start) >= abs(w_end) else w_end
        sign = 1.0 if w_ref > 0 else -1.0
        w_max = max(abs(w_start), abs(w_end))

        # Normalise arrow lengths to the model-wide max UDL so members with
        # different load intensities show proportionally different arrow lengths.
        _lc2 = self._scene.model_state.active_case
        w_global_max = max(
            (max(abs(_lc2.get_member_load(m.id).net("w")[0]),
                 abs(_lc2.get_member_load(m.id).net("w")[1]))
             for m in self._scene.model_state.members),
            default=w_max,
        ) or w_max

        # Shift entire group away from member so multiple LCs stack without overlap
        if perp_offset != 0.0:
            off_x = -sign * px_n_m * perp_offset
            off_y = -sign * py_n_m * perp_offset
            ix += off_x;  iy += off_y
            jx += off_x;  jy += off_y

        n_arr = max(3, min(14, int(L_px / 25)))
        ah = 4
        path = QPainterPath()

        for i in range(n_arr + 1):
            t = i / n_arr
            bx = ix + t * dx
            by = iy + t * dy
            w_local = w_start + t * (w_end - w_start)
            arr_len = UDL_LEN * abs(w_local) / w_global_max if w_global_max > 0 else UDL_LEN
            tx = bx - sign * px_n * arr_len
            ty = by - sign * py_n * arr_len
            path.moveTo(tx, ty)
            path.lineTo(bx, by)
            path.moveTo(bx - sign * px_n * ah + ux * ah,
                        by - sign * py_n * ah + uy * ah)
            path.lineTo(bx, by)
            path.lineTo(bx - sign * px_n * ah - ux * ah,
                        by - sign * py_n * ah - uy * ah)

        tip_ix = ix - sign * px_n * UDL_LEN * abs(w_start) / w_global_max if w_global_max > 0 else ix
        tip_iy = iy - sign * py_n * UDL_LEN * abs(w_start) / w_global_max if w_global_max > 0 else iy
        tip_jx = jx - sign * px_n * UDL_LEN * abs(w_end)   / w_global_max if w_global_max > 0 else jx
        tip_jy = jy - sign * py_n * UDL_LEN * abs(w_end)   / w_global_max if w_global_max > 0 else jy
        path.moveTo(tip_ix, tip_iy)
        path.lineTo(tip_jx, tip_jy)

        draw_color = color if color else QColor("#cc2200")
        item = QGraphicsPathItem(path)
        item.setPen(QPen(draw_color, 1))
        item.setZValue(0.5)
        self._scene.addItem(item)
        self._udl_items.append(item)

        if abs(w_start - w_end) < 1e-9:
            val_text = _fmt(w_start / 1e3, "kN/m")
        else:
            val_text = f"{w_start/1e3:.1f}→{w_end/1e3:.1f} kN/m"
        prefix = f"{lc_name}: " if lc_name else ""
        mid_bx = (tip_ix + tip_jx) / 2
        mid_by = (tip_iy + tip_jy) / 2 - sign * py_n * 8
        lbl = _make_label(prefix + val_text, mid_bx, mid_by, z=1.8, color=draw_color)
        self._scene.addItem(lbl)
        self._udl_label_items.append(lbl)

    # ── lateral load arrows (global X and Y directions) ──────────────────────

    def _draw_lateral_arrows(self, clear: bool = True, color: QColor | None = None,
                             perp_offset: float = 0.0, lc_name: str = "") -> None:
        if clear:
            for it in self._qx_items:      self._scene.removeItem(it)
            for it in self._qx_label_items: self._scene.removeItem(it)
            for it in self._qy_items:      self._scene.removeItem(it)
            for it in self._qy_label_items: self._scene.removeItem(it)
            for it in self._qz_items:      self._scene.removeItem(it)
            for it in self._qz_label_items: self._scene.removeItem(it)
            self._qx_items.clear();  self._qx_label_items.clear()
            self._qy_items.clear();  self._qy_label_items.clear()
            self._qz_items.clear();  self._qz_label_items.clear()

        ml = self._scene.model_state.active_case.get_member_load(self.member.id)
        ms = self._scene.model_state
        in_3d = _display_3d(ms)

        # Pre-compute model-wide maxima per direction so arrows on different
        # members scale proportionally to each other (same logic as w_global_max).
        _lc2    = ms.active_case
        _mlist  = ms.members
        def _gmax(direction: str) -> float:
            v = max((max(abs(_lc2.get_member_load(m.id).net(direction)[0]),
                         abs(_lc2.get_member_load(m.id).net(direction)[1]))
                     for m in _mlist), default=0.0)
            return v or 0.0

        # Draw qx arrows
        qxs, qxe = ml.net("qx")
        if qxs != 0.0 or qxe != 0.0:
            gdir = _proj_x_screen_dir() if in_3d else (1.0, 0.0)
            self._draw_global_axis_arrows(
                qxs, qxe, gdir,
                self._qx_items, self._qx_label_items,
                color or QColor("#E65100"), "kN/m X", perp_offset, lc_name,
                global_max=_gmax("qx"),
            )

        # Draw qy arrows (3D only)
        qys, qye = ml.net("qy")
        if in_3d and (qys != 0.0 or qye != 0.0):
            gdir = _proj_y_screen_dir()
            self._draw_global_axis_arrows(
                qys, qye, gdir,
                self._qy_items, self._qy_label_items,
                color or QColor("#FF6F00"), "kN/m Y", perp_offset, lc_name,
                global_max=_gmax("qy"),
            )

        # Draw qz arrows (3D only) — positive = downward (gravity convention, same as w)
        qzs, qze = ml.net("qz")
        if in_3d and (qzs != 0.0 or qze != 0.0):
            self._draw_global_axis_arrows(
                qzs, qze, (0.0, 1.0),  # screen-down = gravity direction
                self._qz_items, self._qz_label_items,
                color or QColor("#1565C0"), "kN/m Z", perp_offset, lc_name,
                global_max=_gmax("qz"),
            )

    def _draw_global_axis_arrows(
        self,
        q_start: float, q_end: float,
        gdir: tuple[float, float],
        item_list: list, label_list: list,
        draw_color: QColor,
        unit_label: str,
        perp_offset: float,
        lc_name: str,
        global_max: float = 0.0,
    ) -> None:
        """Draw a set of distributed load arrows along the member for one global axis."""
        ni = self._scene.model_state.get_node(self.member.node_i)
        nj = self._scene.model_state.get_node(self.member.node_j)
        if not ni or not nj:
            return
        ix, iy = _node_pos(ni, self._scene)
        jx, jy = _node_pos(nj, self._scene)
        dx = jx - ix;  dy = jy - iy
        L_px = math.hypot(dx, dy)
        if L_px < 1:
            return

        ux, uy = dx / L_px, dy / L_px
        px_n, py_n = -uy, ux
        gx_sx, gx_sy = gdir

        q_ref = q_start if abs(q_start) >= abs(q_end) else q_end
        sign = 1.0 if q_ref > 0 else -1.0
        q_max = max(abs(q_start), abs(q_end))
        # Use model-wide max when available so arrows across members are proportional
        eff_max = global_max if global_max > 0 else q_max

        if perp_offset != 0.0:
            ix += px_n * perp_offset;  iy += py_n * perp_offset
            jx += px_n * perp_offset;  jy += py_n * perp_offset

        n_arr = max(3, min(14, int(L_px / 25)))
        ah = 4
        path = QPainterPath()
        for i in range(n_arr + 1):
            t = i / n_arr
            bx = ix + t * dx;  by = iy + t * dy
            q_local = q_start + t * (q_end - q_start)
            arr_len = UDL_LEN * abs(q_local) / eff_max if eff_max > 0 else UDL_LEN
            tx = bx - sign * gx_sx * arr_len
            ty = by - sign * gx_sy * arr_len
            path.moveTo(tx, ty)
            path.lineTo(bx, by)
            back_x = bx - sign * gx_sx * ah
            back_y = by - sign * gx_sy * ah
            perp_x, perp_y = -gx_sy, gx_sx
            path.moveTo(back_x + perp_x * ah, back_y + perp_y * ah)
            path.lineTo(bx, by)
            path.lineTo(back_x - perp_x * ah, back_y - perp_y * ah)

        tip_ix = ix - sign * gx_sx * UDL_LEN * abs(q_start) / eff_max if eff_max > 0 else ix
        tip_iy = iy - sign * gx_sy * UDL_LEN * abs(q_start) / eff_max if eff_max > 0 else iy
        tip_jx = jx - sign * gx_sx * UDL_LEN * abs(q_end)   / eff_max if eff_max > 0 else jx
        tip_jy = jy - sign * gx_sy * UDL_LEN * abs(q_end)   / eff_max if eff_max > 0 else jy
        path.moveTo(tip_ix, tip_iy)
        path.lineTo(tip_jx, tip_jy)

        item = QGraphicsPathItem(path)
        item.setPen(QPen(draw_color, 1.5))
        item.setZValue(0.5)
        self._scene.addItem(item)
        item_list.append(item)

        if abs(q_start - q_end) < 1e-9:
            val_text = _fmt(q_start / 1e3, f"kN/m {unit_label[-1]}")
        else:
            val_text = f"{q_start/1e3:.1f}→{q_end/1e3:.1f} {unit_label}"
        prefix = f"{lc_name}: " if lc_name else ""
        mid_x = (tip_ix + tip_jx) / 2 - sign * gx_sx * 8
        mid_y = (tip_iy + tip_jy) / 2 - sign * gx_sy * 8 - 10
        lbl = _make_label(prefix + val_text, mid_x, mid_y, z=1.8, color=draw_color)
        self._scene.addItem(lbl)
        label_list.append(lbl)

    # ── point load arrows ─────────────────────────────────────────────────────

    def _draw_point_loads(self, clear: bool = True, color: QColor | None = None,
                          perp_offset: float = 0.0, lc_name: str = "") -> None:
        if clear:
            for item in self._point_load_items:
                self._scene.removeItem(item)
            self._point_load_items.clear()

        ni = self._scene.model_state.get_node(self.member.node_i)
        nj = self._scene.model_state.get_node(self.member.node_j)
        if not ni or not nj:
            return

        ix, iy = _node_pos(ni, self._scene)
        jx, jy = _node_pos(nj, self._scene)
        dx = jx - ix;  dy = jy - iy
        L_px = math.hypot(dx, dy)
        if L_px < 1:
            return

        ux, uy = dx / L_px, dy / L_px
        px_n, py_n = -uy, ux

        draw_color = color if color else QColor(180, 80, 200)
        prefix = f"{lc_name}: " if lc_name else ""

        ml = self._scene.model_state.active_case.get_member_load(self.member.id)
        for pl in ml.point_loads:
            t = max(0.0, min(1.0, pl.position))
            px = ix + t * dx
            py = iy + t * dy

            path = QPainterPath()
            if pl.load_type == "FORCE":
                sign = 1.0 if pl.magnitude > 0 else -1.0
                # Shift attachment point away from member to separate LC groups
                if perp_offset != 0.0:
                    px += -sign * px_n * perp_offset
                    py += -sign * py_n * perp_offset
                arr_len = UDL_LEN * 1.5
                ah = 5
                tx = px - sign * px_n * arr_len
                ty = py - sign * py_n * arr_len
                path.moveTo(tx, ty)
                path.lineTo(px, py)
                path.moveTo(px - sign * px_n * ah + ux * ah,
                            py - sign * py_n * ah + uy * ah)
                path.lineTo(px, py)
                path.lineTo(px - sign * px_n * ah - ux * ah,
                            py - sign * py_n * ah - uy * ah)
                label_text = prefix + _fmt(pl.magnitude / 1e3, "kN")
                lx = tx - sign * px_n * 6
                ly = ty - sign * py_n * 6
            else:  # MOMENT
                r = 14
                sign = 1.0 if pl.magnitude > 0 else -1.0
                import math as _m
                arc_path = QPainterPath()
                arc_path.moveTo(px + r, py)
                arc_path.arcTo(px - r, py - r, 2 * r, 2 * r, 0, sign * 270)
                path.addPath(arc_path)
                end_angle = _m.radians(sign * 270)
                ex = px + r * _m.cos(end_angle)
                ey = py - r * _m.sin(end_angle)
                tang_x = -_m.sin(end_angle) * sign
                tang_y =  _m.cos(end_angle) * sign
                ah = 5
                path.moveTo(ex + tang_x * ah - tang_y * ah * 0.5,
                            ey + tang_y * ah + tang_x * ah * 0.5)
                path.lineTo(ex, ey)
                path.lineTo(ex + tang_x * ah + tang_y * ah * 0.5,
                            ey + tang_y * ah - tang_x * ah * 0.5)
                label_text = prefix + _fmt(pl.magnitude / 1e3, "kN·m")
                lx = px
                ly = py - sign * (r + 10)

            item = QGraphicsPathItem(path)
            item.setPen(QPen(draw_color, 2))
            item.setZValue(1.2)
            self._scene.addItem(item)
            self._point_load_items.append(item)

            lbl = _make_label(label_text, lx, ly, z=1.8, color=draw_color)
            self._scene.addItem(lbl)
            self._point_load_items.append(lbl)

    # ── partial-span distributed load arrows ─────────────────────────────────

    def _draw_partial_load_arrows(self, clear: bool = True) -> None:
        """Draw arrows for each PartialDistLoad on this member."""
        if clear:
            for it in self._partial_items:
                self._scene.removeItem(it)
            self._partial_items.clear()

        ml = self._scene.model_state.active_case.get_member_load(self.member.id)
        if not ml.partial_loads:
            return

        ni = self._scene.model_state.get_node(self.member.node_i)
        nj = self._scene.model_state.get_node(self.member.node_j)
        if not ni or not nj:
            return

        ix, iy = _node_pos(ni, self._scene)
        jx, jy = _node_pos(nj, self._scene)
        dx = jx - ix;  dy = jy - iy
        L_px = math.hypot(dx, dy)
        if L_px < 1:
            return

        ux, uy = dx / L_px, dy / L_px
        ms    = self._scene.model_state
        in_3d = _display_3d(ms)

        if in_3d:
            px_n, py_n = 0.0, 1.0
        else:
            px_n, py_n = -uy, ux

        # Model-wide max across full-span and partial loads so sizes are comparable
        _lc2   = ms.active_case
        _mlist = ms.members
        w_global_max = max(
            (max(
                abs(_lc2.get_member_load(m.id).net("w")[0]),
                abs(_lc2.get_member_load(m.id).net("w")[1]),
                *(abs(p.w_start) for p in _lc2.get_member_load(m.id).partial_loads),
                *(abs(p.w_end)   for p in _lc2.get_member_load(m.id).partial_loads),
                0.0,
            ) for m in _mlist),
            default=1.0,
        ) or 1.0

        draw_color = QColor("#cc5500")   # orange-red: distinct from full-span red
        ah = 4

        for pdl in ml.partial_loads:
            a = max(0.0, min(1.0, pdl.start_pos))
            b = max(0.0, min(1.0, pdl.end_pos))
            if b <= a + 1e-12:
                continue
            w_a, w_b = pdl.w_start, pdl.w_end
            w_ref = w_a if abs(w_a) >= abs(w_b) else w_b
            if w_ref == 0.0:
                continue
            sign = 1.0 if w_ref > 0 else -1.0

            ax_s = ix + a * dx;  ay_s = iy + a * dy
            bx_s = ix + b * dx;  by_s = iy + b * dy
            zone_dx = bx_s - ax_s;  zone_dy = by_s - ay_s
            zone_L  = math.hypot(zone_dx, zone_dy)
            if zone_L < 1:
                continue

            n_arr = max(2, min(10, int(zone_L / 25)))
            path  = QPainterPath()

            for i in range(n_arr + 1):
                t = i / n_arr
                bx = ax_s + t * zone_dx
                by = ay_s + t * zone_dy
                w_local  = w_a + t * (w_b - w_a)
                arr_len  = UDL_LEN * abs(w_local) / w_global_max
                tx = bx - sign * px_n * arr_len
                ty = by - sign * py_n * arr_len
                path.moveTo(tx, ty)
                path.lineTo(bx, by)
                path.moveTo(bx - sign * px_n * ah + ux * ah,
                            by - sign * py_n * ah + uy * ah)
                path.lineTo(bx, by)
                path.lineTo(bx - sign * px_n * ah - ux * ah,
                            by - sign * py_n * ah - uy * ah)

            tip_ax = ax_s - sign * px_n * UDL_LEN * abs(w_a) / w_global_max
            tip_ay = ay_s - sign * py_n * UDL_LEN * abs(w_a) / w_global_max
            tip_bx = bx_s - sign * px_n * UDL_LEN * abs(w_b) / w_global_max
            tip_by = by_s - sign * py_n * UDL_LEN * abs(w_b) / w_global_max
            path.moveTo(tip_ax, tip_ay)
            path.lineTo(tip_bx, tip_by)

            # Boundary ticks at start and end of loaded zone
            tick = (UDL_LEN + 4) * max(abs(w_a), abs(w_b)) / w_global_max
            for mx, my in ((ax_s, ay_s), (bx_s, by_s)):
                path.moveTo(mx, my)
                path.lineTo(mx - sign * px_n * tick, my - sign * py_n * tick)

            item = QGraphicsPathItem(path)
            item.setPen(QPen(draw_color, 1.2))
            item.setZValue(0.55)
            self._scene.addItem(item)
            self._partial_items.append(item)

            mid_x = (tip_ax + tip_bx) / 2
            mid_y = (tip_ay + tip_by) / 2 - sign * py_n * 8
            val_text = (_fmt(w_a / 1e3, "kN/m") if abs(w_a - w_b) < 1e-9
                        else f"{w_a/1e3:.1f}→{w_b/1e3:.1f} kN/m")
            lbl = _make_label(f"{val_text} [{a:.2f}–{b:.2f}]",
                              mid_x, mid_y, z=1.8, color=draw_color)
            self._scene.addItem(lbl)
            self._partial_items.append(lbl)

    # ── refresh / cleanup ─────────────────────────────────────────────────────

    def refresh(self) -> None:
        ni = self._scene.model_state.get_node(self.member.node_i)
        nj = self._scene.model_state.get_node(self.member.node_j)
        if ni and nj:
            ix, iy = _node_pos(ni, self._scene)
            jx, jy = _node_pos(nj, self._scene)
            self.setLine(ix, iy, jx, jy)
        self._update_pen()
        self._draw_udl_arrows()
        self._draw_lateral_arrows()
        self._draw_point_loads()
        self._draw_partial_load_arrows()
        # Refresh hinge ring on both endpoint nodes (type may have just changed)
        for nid in (self.member.node_i, self.member.node_j):
            nitem = self._scene._node_items.get(nid)
            if nitem:
                nitem._draw_hinge_indicator()

    def remove_extra_items(self) -> None:
        for it in self._udl_items: self._scene.removeItem(it)
        self._udl_items.clear()
        for it in self._udl_label_items: self._scene.removeItem(it)
        self._udl_label_items.clear()
        for it in self._qx_items:       self._scene.removeItem(it)
        self._qx_items.clear()
        for it in self._qx_label_items: self._scene.removeItem(it)
        self._qx_label_items.clear()
        for it in self._qy_items:       self._scene.removeItem(it)
        self._qy_items.clear()
        for it in self._qy_label_items: self._scene.removeItem(it)
        self._qy_label_items.clear()
        for it in self._qz_items:       self._scene.removeItem(it)
        self._qz_items.clear()
        for it in self._qz_label_items: self._scene.removeItem(it)
        self._qz_label_items.clear()
        for item in self._point_load_items:
            self._scene.removeItem(item)
        self._point_load_items.clear()
        for item in self._partial_items:
            self._scene.removeItem(item)
        self._partial_items.clear()

    def set_visible_all(self, visible: bool) -> None:
        """Show or hide this member and all its load decorators."""
        self.setVisible(visible)
        for lst in (self._udl_items, self._udl_label_items,
                    self._qx_items, self._qx_label_items,
                    self._qy_items, self._qy_label_items,
                    self._qz_items, self._qz_label_items,
                    self._point_load_items, self._partial_items):
            for it in lst:
                it.setVisible(visible)

    def set_loads_visible(self, visible: bool) -> None:
        """Show or hide only member load arrows/labels (leaves the member line untouched)."""
        for lst in (self._udl_items, self._udl_label_items,
                    self._qx_items, self._qx_label_items,
                    self._qy_items, self._qy_label_items,
                    self._qz_items, self._qz_label_items,
                    self._point_load_items, self._partial_items):
            for it in lst:
                it.setVisible(visible)
