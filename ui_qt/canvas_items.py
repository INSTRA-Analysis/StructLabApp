"""Visual QGraphicsItems for the StructLab canvas: NodeItem and MemberItem.

Extracted from canvas.py to keep the scene-management and rendering concerns
separate.  No scene-management logic here — just how nodes and members look.
"""

from __future__ import annotations

import math

from PyQt6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsLineItem, QGraphicsItem, QGraphicsPathItem,
    QGraphicsSimpleTextItem, QStyle,
)
from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QPen, QBrush, QColor, QPainterPath, QFont, QTransform

from ui_qt.model_state import (
    ModelState, NodeData, MemberData,
    SupportType, ElementType, PointLoadData,
    LoadCase, NodeLoad, MemberLoad,
)
from ui_qt.projection import isometric, is_3d_model, inverse_isometric
import ui_qt.projection as _proj_mod

# ── visual constants ──────────────────────────────────────────────────────────
PX_PER_M   = 80
GRID_STEP  = PX_PER_M          # major grid lines every 1 m
GRID_SUB   = GRID_STEP // 4    # minor grid lines every 0.25 m
NODE_R     = 6
SNAP_PX    = NODE_R * 3
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


def _node_pos(node: NodeData, scene=None) -> tuple[float, float]:
    """Return (scene_x, scene_y) for a node, using isometric if 3D model."""
    if scene is not None and scene.model_state is not None:
        ms = scene.model_state
        if ms.mode_3d or is_3d_model(ms.nodes):
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


def _proj_z_screen_dir() -> tuple[float, float]:
    """Normalized screen direction of the 3D Z axis (always straight up on screen)."""
    el = math.radians(_proj_mod.ISO_ELEVATION)
    # Z projects as: sx=0, sy=-cos(el)*ppm  →  normalised = (0, -1) upward in Qt
    sy = -math.cos(el)
    return (0.0, sy / abs(sy)) if abs(sy) > 1e-9 else (0.0, -1.0)


def _proj_support_bar_dir() -> tuple[float, float]:
    """Normalized screen direction for 3D support bar: ground-plane axis with most screen-X extent.

    Picks whichever of the projected X or Y world axes has a larger
    screen-horizontal component, ensuring the bar stays readable from
    any orbit angle (avoids a nearly-vertical bar when X nearly vanishes).
    """
    az = math.radians(_proj_mod.ISO_AZIMUTH)
    el = math.radians(_proj_mod.ISO_ELEVATION)
    x_bx = math.cos(az);     x_by = -math.sin(az) * math.sin(el)
    y_bx = math.sin(az);     y_by =  math.cos(az) * math.sin(el)
    bx, by = (x_bx, x_by) if abs(x_bx) >= abs(y_bx) else (y_bx, y_by)
    mag = math.hypot(bx, by)
    return (bx / mag, by / mag) if mag > 1e-9 else (1.0, 0.0)


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

    def itemChange(self, change, value):
        ms = self._scene.model_state
        in_3d = ms.mode_3d or is_3d_model(ms.nodes)

        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            if not in_3d:
                # Snap dragged position to 2D grid
                step = PX_PER_M * 0.25
                x = round(value.x() / step) * step
                y = round(value.y() / step) * step
                return QPointF(x, y)

        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            if not in_3d:
                # Sync NodeData coordinates from 2D scene position
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

    def _draw_support_symbol(self) -> None:
        for it in self._support_items:
            self._scene.removeItem(it)
        self._support_items.clear()

        stype = self.node.support_type
        if stype == SupportType.FREE:
            return

        s = 14
        ms = self._scene.model_state
        in_3d = ms.mode_3d or is_3d_model(ms.nodes)

        _COL = {
            SupportType.FIXED:    ("#c0392b", "#7b241c"),
            SupportType.PIN:      ("#2980b9", "#1a5276"),
            SupportType.ROLLER:   ("#f39c12", "#9a7d0a"),
            SupportType.ROLLER_Y: ("#f39c12", "#9a7d0a"),
            SupportType.SPRING:   ("#27ae60", "#1e8449"),
        }
        col, col_dk = _COL.get(stype, ("#cccccc", "#888888"))

        node_pos = self.pos()

        def _path_item(path: QPainterPath, fill: str, pen: str = "#ffffff",
                       pw: float = 1.5, z: float = 1.0) -> None:
            it = QGraphicsPathItem(path)
            it.setBrush(QBrush(QColor(fill)))
            it.setPen(QPen(QColor(pen), pw))
            it.setPos(node_pos)
            it.setZValue(z)
            self._scene.addItem(it)
            self._support_items.append(it)

        def _oval_item(cx: float, cy: float, rw: float, rh: float,
                       angle_deg: float, fill: str, z: float = 0.8) -> None:
            it = QGraphicsEllipseItem(-rw, -rh, 2 * rw, 2 * rh)
            it.setBrush(QBrush(QColor(fill)))
            it.setPen(QPen(Qt.PenStyle.NoPen))
            it.setPos(node_pos + QPointF(cx, cy))
            it.setRotation(angle_deg)
            it.setZValue(z)
            self._scene.addItem(it)
            self._support_items.append(it)

        if in_3d:
            bx, by = _proj_support_bar_dir()
            perp_x, perp_y = -by, bx
            if perp_y < 0:
                perp_x, perp_y = -perp_x, -perp_y
            el = math.radians(_proj_mod.ISO_ELEVATION)

        if stype == SupportType.FIXED:
            if in_3d:
                ox, oy = perp_x * NODE_R, perp_y * NODE_R
                pd = 7  # plate depth in screen-px
                # Filled anchor plate (parallelogram)
                plate = QPainterPath()
                plate.moveTo(ox - s * bx,             oy - s * by)
                plate.lineTo(ox + s * bx,             oy + s * by)
                plate.lineTo(ox + s * bx + perp_x*pd, oy + s * by + perp_y*pd)
                plate.lineTo(ox - s * bx + perp_x*pd, oy - s * by + perp_y*pd)
                plate.closeSubpath()
                _path_item(plate, col, col_dk, pw=1.0, z=0.9)
                # Hatching on the plate
                hatch = QPainterPath()
                for i in range(5):
                    t = -1.0 + i * (2.0 / 4)
                    x0 = ox + t * s * bx
                    y0 = oy + t * s * by
                    hatch.moveTo(x0, y0)
                    hatch.lineTo(x0 + perp_x * pd, y0 + perp_y * pd)
                _path_item(hatch, col_dk, "#ffffff", pw=1.2, z=1.0)
            else:
                plate = QPainterPath()
                plate.moveTo(-s, NODE_R)
                plate.lineTo( s, NODE_R)
                plate.lineTo( s - 4, NODE_R + 8)
                plate.lineTo(-s - 4, NODE_R + 8)
                plate.closeSubpath()
                _path_item(plate, col, col_dk, pw=0, z=0.9)
                hatch = QPainterPath()
                for i in range(5):
                    x = -s + i * (2 * s / 4)
                    hatch.moveTo(x, NODE_R)
                    hatch.lineTo(x - 6, NODE_R + 8)
                _path_item(hatch, col, "#ffffff", pw=1.5, z=1.0)

        elif stype in (SupportType.PIN, SupportType.ROLLER, SupportType.ROLLER_Y):
            if stype == SupportType.ROLLER_Y:
                tri = QPainterPath()
                tri.moveTo(-NODE_R, 0)
                tri.lineTo(-(s + NODE_R), -s)
                tri.lineTo(-(s + NODE_R),  s)
                tri.closeSubpath()
                _path_item(tri, col, "#ffffff", pw=1.5)
                wheels = QPainterPath()
                wheels.addEllipse(-(s + NODE_R + 11), -s,      8, 8)
                wheels.addEllipse(-(s + NODE_R + 11), -s + 12, 8, 8)
                _path_item(wheels, col_dk, "#ffffff", pw=1.0)
            elif in_3d:
                tip_x  = perp_x * NODE_R
                tip_y  = perp_y * NODE_R
                base_ox = perp_x * (NODE_R + s)
                base_oy = perp_y * (NODE_R + s)
                lx, ly = base_ox - s * bx, base_oy - s * by  # left corner
                rx, ry = base_ox + s * bx, base_oy + s * by  # right corner

                # Back face — shifted "up" in screen (= +Z in world = behind in depth)
                z_shift = s * 0.32 * math.cos(el)
                back = QPainterPath()
                back.moveTo(tip_x,       tip_y - z_shift)
                back.lineTo(lx,          ly    - z_shift)
                back.lineTo(rx,          ry    - z_shift)
                back.closeSubpath()
                _path_item(back, col_dk, col_dk, pw=0, z=0.85)

                # Base oval (circular base of the cone, in isometric foreshortening)
                bar_angle = math.degrees(math.atan2(by, bx))
                _oval_item(base_ox, base_oy, s * 0.95, s * 0.32, bar_angle, col_dk, z=0.8)

                # Front face (main color)
                front = QPainterPath()
                front.moveTo(tip_x, tip_y)
                front.lineTo(lx, ly)
                front.lineTo(rx, ry)
                front.closeSubpath()
                _path_item(front, col, "#ffffff", pw=1.5, z=1.0)

                if stype == SupportType.ROLLER:
                    wx = base_ox + perp_x * 4
                    wy = base_oy + perp_y * 4
                    wheels = QPainterPath()
                    wheels.addEllipse(wx - s * bx - 4,       wy - s * by - 4,       8, 8)
                    wheels.addEllipse(wx + (s - 12) * bx - 4, wy + (s - 12) * by - 4, 8, 8)
                    _path_item(wheels, col_dk, "#ffffff", pw=1.0, z=1.1)
            else:
                tri = QPainterPath()
                tri.moveTo(0, NODE_R)
                tri.lineTo(-s, s + NODE_R)
                tri.lineTo( s, s + NODE_R)
                tri.closeSubpath()
                _path_item(tri, col, "#ffffff", pw=1.5)
                if stype == SupportType.ROLLER:
                    wheels = QPainterPath()
                    wheels.addEllipse(-s,      s + NODE_R + 3, 8, 8)
                    wheels.addEllipse(-s + 12, s + NODE_R + 3, 8, 8)
                    _path_item(wheels, col_dk, "#ffffff", pw=1.0)

        elif stype == SupportType.SPRING:
            path = QPainterPath()
            y = NODE_R
            path.moveTo(0, y)
            for i in range(6):
                x = 8 * (1 if i % 2 == 0 else -1)
                path.lineTo(x, y + (i + 1) * 4)
            path.lineTo(0, y + 28)
            path.moveTo(-s, y + 30)
            path.lineTo( s, y + 30)
            _path_item(path, col, col, pw=1.5)

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
        in_3d = ms.mode_3d or is_3d_model(ms.nodes)

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
            self._scene.removeItem(it)
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

    def remove_support_symbol(self) -> None:
        for it in self._support_items:
            self._scene.removeItem(it)
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

    def _apply_pen(self) -> None:
        if self._is_selected:
            self.setPen(QPen(QColor("#ffcc00"), 5))
        elif self._base_pen is not None:
            self.setPen(self._base_pen)

    def _update_pen(self) -> None:
        pen = _BAR_PEN if self.member.element_type == ElementType.BAR else _BEAM_PEN
        pen_copy = QPen(pen)
        pen_copy.setWidth(3)
        self._base_pen = pen_copy
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
        in_3d = ms.mode_3d or is_3d_model(ms.nodes)
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
        in_3d = ms.mode_3d or is_3d_model(ms.nodes)

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
        in_3d = ms.mode_3d or is_3d_model(ms.nodes)

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
