"""Structural canvas: QGraphicsScene-based interactive model editor.

NodeItem and MemberItem visual classes live in canvas_items.py.
"""

from __future__ import annotations

import math
from enum import Enum, auto

from PyQt6.QtWidgets import (
    QGraphicsScene, QGraphicsView,
    QGraphicsLineItem, QMenu, QInputDialog,
)
from PyQt6.QtCore import Qt, QPointF, QLineF, QTimer, pyqtSignal, QRect, QPoint
from PyQt6.QtGui import QPen, QBrush, QColor, QPainter, QTransform, QLinearGradient, QPixmap, QPainterPath
from PyQt6.QtCore import QRectF as _QRectF

from ui_qt.model_state import (
    ModelState, NodeData, MemberData,
    ElementType, SupportType,
)

from ui_qt.canvas_items import (
    PX_PER_M, GRID_STEP, SNAP_PX,
    _GHOST_PEN, m_to_px, px_to_m,
    NodeItem, MemberItem, _node_pos, group_colour,
)
import ui_qt.projection as _proj
from ui_qt.projection import (
    isometric, inverse_isometric,
    inverse_isometric_xz, inverse_isometric_yz,
)
from ui_qt.view_cube import ViewCube

# Distinct palette for "All Cases" overlay — one colour per load case
_LC_COLORS = [
    QColor("#00BFFF"),  # deep sky blue
    QColor("#FF8C00"),  # dark orange
    QColor("#44DD44"),  # lime green
    QColor("#FF69B4"),  # hot pink
    QColor("#FFD700"),  # gold
    QColor("#BA55D3"),  # medium orchid
    QColor("#FF4500"),  # orange-red
    QColor("#00CED1"),  # dark turquoise
]
_PERP_OFFSET_STEP = 10.0  # px between successive LC arrow groups


class CanvasMode(Enum):
    SELECT     = auto()
    ADD_NODE   = auto()
    ADD_MEMBER = auto()


class WorkingPlane(Enum):
    XY   = auto()  # lock Z — place nodes on the X-Y plane
    XZ   = auto()  # lock Y — place nodes on the X-Z plane
    YZ   = auto()  # lock X — place nodes on the Y-Z plane
    FREE = auto()  # no lock — project to XY ground (Z=0)


# ─────────────────────────────────────────────────────────────────────────────
# NodeItem
# ─────────────────────────────────────────────────────────────────────────────

# StructCanvas
# ─────────────────────────────────────────────────────────────────────────────

class StructCanvas(QGraphicsScene):
    """Interactive 2-D canvas for building structural models."""

    model_changed        = pyqtSignal()              # emitted after any structural change
    view_changed         = pyqtSignal()              # emitted when 3D projection angles change (orbit end)
    view_preset          = pyqtSignal(float, float)  # emitted when user snaps to a named view (az, el)
    plane_offset_changed = pyqtSignal(float)         # emitted whenever the working-plane offset changes
    _hide_welcome: bool = False    # once user takes action, never show welcome

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setSceneRect(-4000, -4000, 8000, 8000)
        self.model_state = ModelState()
        self._mode = CanvasMode.SELECT
        self._next_member_type = ElementType.BEAM
        self._member_start_node: NodeData | None = None
        self._ghost_line: QGraphicsLineItem | None = None
        self._working_plane: WorkingPlane = WorkingPlane.XY
        self._plane_offset: float = 0.0   # fixed coordinate on the locked axis
        self._node_items: dict[int, NodeItem] = {}
        self._member_items: dict[int, MemberItem] = {}
        self._show_all_cases: bool = False
        self._undo_stack: list[dict] = []
        self._redo_stack: list[dict] = []
        self._drag_snapshot_saved: bool = False  # avoid duplicate snapshots per drag
        self._isolated: bool = False             # isolate-selection mode
        self._isolated_member_ids: set[int] = set()

        # ── G-grab state ──────────────────────────────────────────────────────
        self._grab_active: bool = False
        self._grab_is_extrude: bool = False         # True when grab follows E-extrude
        self._grab_axis: str | None = None          # None, 'X', 'Y', or 'Z'
        self._grab_origin_pos: QPointF | None = None
        self._grab_node_origins: dict[int, tuple[float, float, float]] = {}
        self._grab_typed: str = ""                  # accumulated numeric input

        # ── util colour overlay flag ──────────────────────────────────────────
        self._util_colour_active: bool = False

        # ── "colour by group" view flag ───────────────────────────────────────
        self._colour_by_group: bool = False

        # ── load graphics visibility ──────────────────────────────────────────
        self._show_loads: bool = True

        # ── overlay state ─────────────────────────────────────────────────────
        self._overlay_items: dict[str, list] = {}
        # member_id → all overlay items (all layers) for that member — used by isolation
        self._member_overlay_items: dict[int, list] = {}
        self._overlay_visible: dict[str, bool] = {
            'BMD':      True,
            'SFD':      False,
            'AFD':      False,
            'Deformed': True,
            'Labels':   False,
        }

    # ── mode ──────────────────────────────────────────────────────────────────

    def set_mode(self, mode: CanvasMode) -> None:
        self._mode = mode
        movable = (mode == CanvasMode.SELECT)
        for item in self._node_items.values():
            item.set_movable(movable)
        if mode != CanvasMode.ADD_MEMBER:
            self._cancel_member_drag()

    def toggle_isolate(self) -> None:
        """Toggle isolate-selection mode: hide everything outside the current selection.

        If already isolated, restore all items. Endpoint nodes of selected members
        are automatically included so no member is orphaned visually.
        Overlay diagrams (BMD/SFD/AFD/Deformed/Labels) are also filtered to the
        isolated member set when items carry a UI member ID tag (set by update_overlays).
        """
        from ui_qt.canvas_items import NodeItem, MemberItem
        if self._isolated:
            for item in self._node_items.values():
                item.set_visible_all(True)
            for item in self._member_items.values():
                item.set_visible_all(True)
            # Restore overlay items according to their layer's current visibility setting
            for layer, items in self._overlay_items.items():
                layer_vis = self._overlay_visible.get(layer, True)
                for it in items:
                    it.setVisible(layer_vis)
            self._isolated = False
            self._isolated_member_ids.clear()
            # Re-apply load toggle so any previously hidden loads stay hidden
            if not self._show_loads:
                self.set_loads_visible(False)
            self.invalidate(self.sceneRect())
            return

        selected = self.selectedItems()
        sel_node_ids    = {it.node.id   for it in selected if isinstance(it, NodeItem)}
        sel_member_ids  = {it.member.id for it in selected if isinstance(it, MemberItem)}
        if not sel_node_ids and not sel_member_ids:
            return   # nothing selected — nothing to isolate

        # Include endpoint nodes of selected members so they remain visible
        for mid in sel_member_ids:
            m = self.model_state.get_member(mid)
            if m:
                sel_node_ids.add(m.node_i)
                sel_node_ids.add(m.node_j)

        for nid, item in self._node_items.items():
            item.set_visible_all(nid in sel_node_ids)
        for mid, item in self._member_items.items():
            item.set_visible_all(mid in sel_member_ids)

        # Filter overlay items via the per-member dict (no reliance on data() tags).
        # Build a set of items in currently-visible layers for fast lookup.
        visible_layer_items: set = set()
        for layer, layer_items_list in self._overlay_items.items():
            if self._overlay_visible.get(layer, True):
                visible_layer_items.update(layer_items_list)
        # Hide all overlays, then show only those for isolated members in visible layers.
        for items in self._overlay_items.values():
            for it in items:
                it.setVisible(False)
        for mid, items in self._member_overlay_items.items():
            if mid in sel_member_ids:
                for it in items:
                    if it in visible_layer_items:
                        it.setVisible(True)

        self._isolated = True
        self._isolated_member_ids = sel_member_ids
        self.invalidate(self.sceneRect())

    def set_loads_visible(self, visible: bool) -> None:
        """Toggle visibility of all load graphics (arrows, labels) without affecting
        supports, hinges, or structural geometry.  Isolation mode is respected —
        items hidden by isolation are not unintentionally revealed.
        """
        from ui_qt.canvas_items import NodeItem, MemberItem
        self._show_loads = visible
        for item in self._node_items.values():
            if item.isVisible():   # skip items hidden by isolation
                item.set_loads_visible(visible)
        for item in self._member_items.values():
            if item.isVisible():
                item.set_loads_visible(visible)

    def set_next_member_type(self, element_type: ElementType) -> None:
        self._next_member_type = element_type

    def set_plane_offset(self, offset: float) -> None:
        """Set the locked coordinate on the active working plane axis."""
        self._plane_offset = offset
        self.update()
        self.plane_offset_changed.emit(offset)

    def set_z_level(self, z: float) -> None:
        """Compatibility alias for set_plane_offset."""
        self.set_plane_offset(z)

    def set_working_plane(self, plane: WorkingPlane) -> None:
        """Switch the active working plane."""
        self._working_plane = plane
        self.update()

    # ── duplicate ─────────────────────────────────────────────────────────────

    def duplicate_selection(self, axis: str, offset: float, copies: int) -> None:
        """Duplicate selected nodes + intra-selection members along an axis.

        Each copy i is placed at original + offset * i (i = 1 … copies).
        Members connecting to nodes *outside* the selection are not duplicated.
        After the operation, all new items are selected.
        """
        from ui_qt.canvas_items import NodeItem, MemberItem

        selected = self.selectedItems()

        # Explicit node selection
        node_ids: set[int] = {it.node.id for it in selected if isinstance(it, NodeItem)}
        # Auto-include endpoint nodes of any selected member so you don't have
        # to select nodes separately when duplicating a member directly.
        for it in selected:
            if isinstance(it, MemberItem):
                node_ids.add(it.member.node_i)
                node_ids.add(it.member.node_j)

        sel_nodes = [self.model_state.get_node(nid) for nid in node_ids]
        sel_nodes = [n for n in sel_nodes if n is not None]
        if not sel_nodes:
            return

        sel_node_ids = node_ids
        # Include all members whose both endpoints are in the selection
        members_to_dup = [
            m for m in self.model_state.members
            if m.node_i in sel_node_ids and m.node_j in sel_node_ids
        ]

        self.save_snapshot()
        self._suppress_changed = True
        all_new_node_ids: list[int] = []
        try:
            dx = offset if axis == 'X' else 0.0
            dy = offset if axis == 'Y' else 0.0
            dz = offset if axis == 'Z' else 0.0

            for copy_idx in range(1, copies + 1):
                cx = dx * copy_idx
                cy = dy * copy_idx
                cz = dz * copy_idx
                id_map: dict[int, int] = {}

                for node in sel_nodes:
                    new_node = self.model_state.add_node(
                        node.x + cx, node.y + cy, node.z + cz
                    )
                    self._add_node_item(new_node)
                    id_map[node.id] = new_node.id
                    all_new_node_ids.append(new_node.id)

                for member in members_to_dup:
                    new_m = self.model_state.add_member(
                        id_map[member.node_i], id_map[member.node_j]
                    )
                    if new_m:
                        new_m.element_type = member.element_type
                        new_m.E            = member.E
                        new_m.A            = member.A
                        new_m.I            = member.I
                        new_m.I_y          = member.I_y
                        new_m.J            = member.J
                        new_m.n_sub        = member.n_sub
                        new_m.density      = member.density
                        new_m.beta_angle   = member.beta_angle
                        self._add_member_item(new_m)
        finally:
            self._suppress_changed = False

        # Select all newly created items
        self.clearSelection()
        for nid in all_new_node_ids:
            item = self._node_items.get(nid)
            if item:
                item.setSelected(True)

        self.model_changed.emit()

    # ── undo / redo ───────────────────────────────────────────────────────────

    def _make_snapshot(self) -> dict:
        return self.model_state.to_dict()

    def _apply_snapshot(self, snap: dict) -> None:
        new_state = ModelState.from_dict(snap)
        self.load_state(new_state)

    def save_snapshot(self) -> None:
        """Push current state onto the undo stack. Call before any mutating operation."""
        self._undo_stack.append(self._make_snapshot())
        if len(self._undo_stack) > 50:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def undo(self) -> None:
        if not self._undo_stack:
            return
        self._redo_stack.append(self._make_snapshot())
        self._apply_snapshot(self._undo_stack.pop())
        self.model_changed.emit()

    def redo(self) -> None:
        if not self._redo_stack:
            return
        self._undo_stack.append(self._make_snapshot())
        self._apply_snapshot(self._redo_stack.pop())
        self.model_changed.emit()

    # ── snapping ──────────────────────────────────────────────────────────────

    def _snap(self, pos: QPointF) -> QPointF:
        step = PX_PER_M * 0.25
        x = round(pos.x() / step) * step
        y = round(pos.y() / step) * step
        return QPointF(x, y)

    def _nearest_node(self, pos: QPointF, max_px: float = SNAP_PX) -> NodeData | None:
        best: NodeData | None = None
        best_d = max_px
        for node_id, item in self._node_items.items():
            d = math.hypot(item.pos().x() - pos.x(), item.pos().y() - pos.y())
            if d < best_d:
                best_d = d
                best = self.model_state.get_node(node_id)
        return best

    # ── mouse events ──────────────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:
        if self._grab_active:
            if event.button() == Qt.MouseButton.LeftButton:
                self._confirm_grab()
            elif event.button() == Qt.MouseButton.RightButton:
                self._cancel_grab()
            return

        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        pos = event.scenePos()

        if self._mode == CanvasMode.ADD_NODE:
            snapped = self._snap(pos)
            ms = self.model_state
            plane  = self._working_plane
            offset = self._plane_offset
            az = _proj.ISO_AZIMUTH
            el = _proj.ISO_ELEVATION
            ppm = PX_PER_M
            sx, sy = snapped.x(), snapped.y()
            _az_r = math.radians(az)
            _el_r = math.radians(el)
            # Guard: skip placement when the view is edge-on to the working plane.
            # inverse_isometric* returns (0,0) for degenerate views, which would
            # silently plant nodes at the origin.
            _DEGEN = 0.09  # sin/cos threshold ≈ 5°
            if plane == WorkingPlane.XZ and abs(math.cos(_az_r)) < _DEGEN:
                return   # right/left view is edge-on to XZ plane
            if plane == WorkingPlane.YZ and abs(math.sin(_az_r)) < _DEGEN:
                return   # front/back view is edge-on to YZ plane
            if plane in (WorkingPlane.XY, WorkingPlane.FREE) and abs(math.sin(_el_r)) < _DEGEN:
                return   # horizontal view is edge-on to XY plane
            if plane == WorkingPlane.XZ:
                x, z = inverse_isometric_xz(sx, sy, offset, ppm, az, el)
                mx = round(x      / 0.25) * 0.25
                my = round(offset / 0.25) * 0.25
                mz = round(z      / 0.25) * 0.25
            elif plane == WorkingPlane.YZ:
                y, z = inverse_isometric_yz(sx, sy, offset, ppm, az, el)
                mx = round(offset / 0.25) * 0.25
                my = round(y      / 0.25) * 0.25
                mz = round(z      / 0.25) * 0.25
            else:  # XY or FREE
                z_val = offset if plane == WorkingPlane.XY else 0.0
                x, y = inverse_isometric(sx, sy, z_val, ppm, az, el)
                mx = round(x     / 0.25) * 0.25
                my = round(y     / 0.25) * 0.25
                mz = z_val
            if not self.model_state.node_at(mx, my, mz, tol=0.05):
                self.save_snapshot()
                node = self.model_state.add_node(mx, my, mz)
                self._add_node_item(node)

        elif self._mode == CanvasMode.ADD_MEMBER:
            start_node = self._nearest_node(pos)
            if start_node:
                self._member_start_node = start_node
                sx, sy = _node_pos(start_node, self)
                self._ghost_line = self.addLine(sx, sy, sx, sy, _GHOST_PEN)

        elif self._mode == CanvasMode.SELECT:
            # Save snapshot before potential node drag
            item = self.itemAt(pos, QTransform())
            if isinstance(item, NodeItem):
                self.save_snapshot()
                self._drag_snapshot_saved = True
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._grab_active and not self._grab_typed:
            self._apply_grab(event.scenePos())
        if self._mode == CanvasMode.ADD_MEMBER and self._ghost_line and self._member_start_node:
            pos = event.scenePos()
            sx = m_to_px(self._member_start_node.x)
            sy = -m_to_px(self._member_start_node.y)
            self._ghost_line.setLine(sx, sy, pos.x(), pos.y())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mouseReleaseEvent(event)
            return

        if self._mode == CanvasMode.ADD_MEMBER and self._member_start_node:
            end_node = self._nearest_node(event.scenePos())
            if end_node and end_node.id != self._member_start_node.id:
                self.save_snapshot()
                member = self.model_state.add_member(
                    self._member_start_node.id, end_node.id
                )
                if member:
                    member.element_type = self._next_member_type
                    self._add_member_item(member)
            self._cancel_member_drag()
        else:
            self._drag_snapshot_saved = False

        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        mods = event.modifiers()
        ctrl  = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        key   = event.key()
        if self._grab_active:
            self._handle_grab_key(key, event.text())
            return
        if key == Qt.Key.Key_Delete:
            self.save_snapshot()
            self._delete_selected()
        elif key == Qt.Key.Key_A and ctrl and shift:
            self.clearSelection()
        elif key == Qt.Key.Key_A and ctrl:
            for item in self.items():
                item.setSelected(True)
        elif key == Qt.Key.Key_I and ctrl:
            for item in self.items():
                item.setSelected(not item.isSelected())
        elif key == Qt.Key.Key_Z and ctrl:
            self.undo()
        elif key == Qt.Key.Key_Y and ctrl:
            self.redo()
        elif key == Qt.Key.Key_I and not ctrl and not shift:
            self.toggle_isolate()
        elif key == Qt.Key.Key_G and not ctrl and not shift:
            self._start_grab()
        elif key == Qt.Key.Key_E and not ctrl and not shift:
            self._start_extrude()
        elif self._is_3d_mode():
            self._handle_view_key(key, ctrl) or super().keyPressEvent(event)
        else:
            super().keyPressEvent(event)

    # ── G-grab ────────────────────────────────────────────────────────────────

    def _start_grab(self) -> None:
        """Enter G-grab mode: move all selected nodes interactively."""
        sel_nodes = [it.node for it in self.selectedItems()
                     if isinstance(it, NodeItem)]
        if not sel_nodes:
            return
        views = self.views()
        if not views:
            return
        from PyQt6.QtGui import QCursor
        view = views[0]
        scene_pos = view.mapToScene(view.mapFromGlobal(QCursor.pos()))
        self.save_snapshot()
        self._grab_active      = True
        self._grab_is_extrude  = False
        self._grab_axis        = None
        self._grab_origin_pos  = scene_pos
        self._grab_node_origins = {n.id: (n.x, n.y, n.z) for n in sel_nodes}
        self._grab_typed       = ""
        self.invalidate(self.sceneRect())

    def _start_extrude(self) -> None:
        """E-extrude: duplicate selected nodes with new members, then grab them."""
        sel_nodes = [it.node for it in self.selectedItems()
                     if isinstance(it, NodeItem)]
        if not sel_nodes:
            return
        views = self.views()
        if not views:
            return
        from PyQt6.QtGui import QCursor
        view = views[0]
        scene_pos = view.mapToScene(view.mapFromGlobal(QCursor.pos()))

        self.save_snapshot()
        self._suppress_changed = True
        new_node_ids: list[int] = []
        try:
            for node in sel_nodes:
                new_nd = self.model_state.add_node(node.x, node.y, node.z)
                self._add_node_item(new_nd)
                new_node_ids.append(new_nd.id)
                member = self.model_state.add_member(node.id, new_nd.id)
                if member:
                    member.element_type = self._next_member_type
                    self._add_member_item(member)
        finally:
            self._suppress_changed = False

        # Select only the new nodes so grab moves them
        self.clearSelection()
        for nid in new_node_ids:
            item = self._node_items.get(nid)
            if item:
                item.setSelected(True)

        self._grab_active      = True
        self._grab_is_extrude  = True
        self._grab_axis        = None
        self._grab_origin_pos  = scene_pos
        self._grab_node_origins = {}
        for nid in new_node_ids:
            nd = self.model_state.get_node(nid)
            if nd:
                self._grab_node_origins[nid] = (nd.x, nd.y, nd.z)
        self._grab_typed = ""
        self.invalidate(self.sceneRect())

    def _apply_grab(self, current_pos: QPointF) -> None:
        """Reposition grabbed nodes to follow the mouse, respecting axis lock."""
        if not self._grab_active or self._grab_origin_pos is None:
            return
        dsx = current_pos.x() - self._grab_origin_pos.x()
        dsy = current_pos.y() - self._grab_origin_pos.y()
        self._move_grabbed_nodes_screen(dsx, dsy)

    def _move_grabbed_nodes_screen(self, dsx: float, dsy: float) -> None:
        """Convert a screen (dsx, dsy) delta to world (dx, dy, dz) and apply."""
        axis  = self._grab_axis
        is_3d = self._is_3d_mode()
        ppm   = PX_PER_M

        if is_3d:
            az = math.radians(_proj.ISO_AZIMUTH)
            el = math.radians(_proj.ISO_ELEVATION)
            cos_az, sin_az = math.cos(az), math.sin(az)
            cos_el, sin_el = math.cos(el), math.sin(el)

            if axis == 'X':
                # screen dir of X axis: (cos_az, -sin_az*sin_el)
                mag2 = cos_az**2 + (sin_az * sin_el)**2
                if mag2 < 1e-9: return
                dx = (dsx * cos_az + dsy * (-sin_az * sin_el)) / (ppm * mag2)
                dy = dz = 0.0
            elif axis == 'Y':
                # screen dir of Y axis: (sin_az, cos_az*sin_el)
                mag2 = sin_az**2 + (cos_az * sin_el)**2
                if mag2 < 1e-9: return
                dy = (dsx * sin_az + dsy * cos_az * sin_el) / (ppm * mag2)
                dx = dz = 0.0
            elif axis == 'Z':
                # screen dir of Z axis: (0, -cos_el)
                if abs(cos_el) < 1e-9: return
                dz = -dsy / (ppm * cos_el)
                dx = dy = 0.0
            else:
                # Free: project onto active workplane
                plane = self._working_plane
                z_val = self._plane_offset
                if plane == WorkingPlane.XZ:
                    # Solve: dsx = cos_az*dx*ppm ; dsy = (-sin_az*sin_el*dx - cos_el*dz)*ppm
                    if abs(cos_az * cos_el) < 1e-9: return
                    dx = (dsx / ppm) / cos_az
                    dz = (dsy / ppm - (-sin_az * sin_el) * dx) / (-cos_el)
                    dy = 0.0
                elif plane == WorkingPlane.YZ:
                    # Solve: dsx = sin_az*dy*ppm ; dsy = (cos_az*sin_el*dy - cos_el*dz)*ppm
                    if abs(sin_az * cos_el) < 1e-9: return
                    dy = (dsx / ppm) / sin_az
                    dz = (dsy / ppm - cos_az * sin_el * dy) / (-cos_el)
                    dx = 0.0
                else:
                    # XY / FREE — use inverse projection at fixed z
                    assert self._grab_origin_pos is not None
                    ox, oy = inverse_isometric(
                        self._grab_origin_pos.x(), self._grab_origin_pos.y(),
                        z_val, ppm, _proj.ISO_AZIMUTH, _proj.ISO_ELEVATION,
                    )
                    cx, cy = inverse_isometric(
                        self._grab_origin_pos.x() + dsx,
                        self._grab_origin_pos.y() + dsy,
                        z_val, ppm, _proj.ISO_AZIMUTH, _proj.ISO_ELEVATION,
                    )
                    dx, dy, dz = cx - ox, cy - oy, 0.0
        else:
            # 2D mode
            if axis == 'X':
                dx, dy, dz = dsx / ppm, 0.0, 0.0
            elif axis == 'Y':
                dx, dy, dz = 0.0, -dsy / ppm, 0.0
            else:
                dx, dy, dz = dsx / ppm, -dsy / ppm, 0.0

        self._apply_delta_to_grabbed(dx, dy, dz)

    def _apply_delta_to_grabbed(self, dx: float, dy: float, dz: float) -> None:
        """Apply world-space (dx, dy, dz) to all grabbed nodes from their origins."""
        ms = self.model_state
        self._suppress_changed = True
        try:
            for nid, (ox, oy, oz) in self._grab_node_origins.items():
                node = ms.get_node(nid)
                if node:
                    node.x = ox + dx
                    node.y = oy + dy
                    node.z = oz + dz
                    item = self._node_items.get(nid)
                    if item:
                        item.refresh()
        finally:
            self._suppress_changed = False
        self.update_depth_order()
        self.invalidate(self.sceneRect())

    def _apply_grab_typed_value(self) -> None:
        """Apply the typed numeric distance along the active constraint axis."""
        try:
            dist = float(self._grab_typed)
        except ValueError:
            return
        axis = self._grab_axis
        if axis == 'X':
            self._apply_delta_to_grabbed(dist, 0.0, 0.0)
        elif axis == 'Y':
            self._apply_delta_to_grabbed(0.0, dist, 0.0)
        elif axis == 'Z':
            self._apply_delta_to_grabbed(0.0, 0.0, dist)

    def _confirm_grab(self) -> None:
        """Commit the grab: snap to 0.25 m grid and emit model_changed."""
        if not self._grab_active:
            return
        self._grab_active     = False
        self._grab_is_extrude = False
        ms = self.model_state
        for nid in self._grab_node_origins:
            node = ms.get_node(nid)
            if node:
                node.x = round(node.x / 0.25) * 0.25
                node.y = round(node.y / 0.25) * 0.25
                node.z = round(node.z / 0.25) * 0.25
                item = self._node_items.get(nid)
                if item:
                    item.refresh()
        self._grab_node_origins = {}
        self._grab_origin_pos   = None
        self._grab_axis         = None
        self._grab_typed        = ""
        self.update_depth_order()
        self.invalidate(self.sceneRect())
        self.model_changed.emit()

    def _cancel_grab(self) -> None:
        """Cancel grab: restore original positions via undo."""
        if not self._grab_active:
            return
        self._grab_active     = False
        self._grab_is_extrude = False
        self._grab_node_origins = {}
        self._grab_origin_pos   = None
        self._grab_axis         = None
        self._grab_typed        = ""
        self.undo()

    def _handle_grab_key(self, key: int, text: str) -> None:
        """Dispatch key events while grab mode is active."""
        K = Qt.Key
        if key in (K.Key_Return, K.Key_Enter):
            if self._grab_typed:
                self._apply_grab_typed_value()
            self._confirm_grab()
        elif key == K.Key_Escape:
            self._cancel_grab()
        elif key in (K.Key_X, K.Key_Y, K.Key_Z):
            new_axis = text.upper()
            # Toggle: pressing same axis again removes constraint
            self._grab_axis = None if self._grab_axis == new_axis else new_axis
            self._grab_typed = ""
            # Re-apply from current mouse position
            views = self.views()
            if views:
                from PyQt6.QtGui import QCursor
                scene_pos = views[0].mapToScene(
                    views[0].mapFromGlobal(QCursor.pos())
                )
                self._apply_grab(scene_pos)
            self.invalidate(self.sceneRect())
        elif key == K.Key_Backspace:
            self._grab_typed = self._grab_typed[:-1]
            if self._grab_typed:
                self._apply_grab_typed_value()
            else:
                # Revert to mouse-driven
                views = self.views()
                if views:
                    from PyQt6.QtGui import QCursor
                    scene_pos = views[0].mapToScene(
                        views[0].mapFromGlobal(QCursor.pos())
                    )
                    self._apply_grab(scene_pos)
        elif text in '0123456789':
            self._grab_typed += text
            self._apply_grab_typed_value()
        elif text == '-' and not self._grab_typed:
            self._grab_typed = '-'
        elif text == '.' and '.' not in self._grab_typed:
            self._grab_typed += '.'

    def _is_3d_mode(self) -> bool:
        return True

    def _handle_view_key(self, key: int, ctrl: bool) -> bool:
        """Handle numpad-style view shortcuts (3D mode only).

        Returns True if the key was consumed, False otherwise.
        Numpad 1/3/7/5  → Front / Right / Top / Default-ISO
        Ctrl + 1/3/7    → Back  / Left  / Bottom
        2/4/6/8         → orbit  ±15° (down/left/right/up)
        9               → flip view (az + 180°)
        """
        K = Qt.Key
        az = _proj.ISO_AZIMUTH
        el = _proj.ISO_ELEVATION
        # Face-snap keys: use set_view_preset so MainWindow syncs the working plane
        if key == K.Key_1:
            self.set_view_preset(180.0 if ctrl else 0.0, 2.0)
        elif key == K.Key_3:
            self.set_view_preset(-90.0 if ctrl else 90.0, 2.0)
        elif key == K.Key_7:
            self.set_view_preset(az, -87.0 if ctrl else 87.0)
        elif key == K.Key_5:
            self.set_view_preset(-45.0, 30.0)      # default SW isometric
        # Orbit-step keys: use set_view (no plane change)
        elif key == K.Key_4:
            self.set_view(az - 15.0, el)            # orbit left
        elif key == K.Key_6:
            self.set_view(az + 15.0, el)            # orbit right
        elif key == K.Key_8:
            self.set_view(az, el + 15.0)            # orbit up
        elif key == K.Key_2:
            self.set_view(az, el - 15.0)            # orbit down
        elif key == K.Key_9:
            self.set_view(az + 180.0, el)           # flip to opposite side
        else:
            return False
        return True

    # ── scene manipulation ────────────────────────────────────────────────────

    def _current_view_scale(self) -> float:
        views = self.views()
        return views[0].transform().m11() if views else 1.0

    def _add_node_item(self, node: NodeData) -> NodeItem:
        item = NodeItem(node, self)
        self.addItem(item)
        self._node_items[node.id] = item
        item.update_visual_scale(self._current_view_scale())
        if not getattr(self, "_suppress_changed", False):
            self.model_changed.emit()
        return item

    def _add_member_item(self, member: MemberData) -> MemberItem | None:
        ni = self.model_state.get_node(member.node_i)
        nj = self.model_state.get_node(member.node_j)
        if not ni or not nj:
            return None
        item = MemberItem(member, ni, nj, self)
        self.addItem(item)
        self._member_items[member.id] = item
        item.update_visual_scale(self._current_view_scale())
        if not getattr(self, "_suppress_changed", False):
            self.model_changed.emit()
        return item

    def _delete_selected(self) -> None:
        for item in list(self.selectedItems()):
            if isinstance(item, NodeItem):
                nid = item.node.id
                for mid in [m.id for m in self.model_state.members
                            if m.node_i == nid or m.node_j == nid]:
                    if mid in self._member_items:
                        mi = self._member_items.pop(mid)
                        mi.remove_extra_items()
                        self.removeItem(mi)
                item.remove_extra_items()
                self.removeItem(item)
                self._node_items.pop(nid, None)
                self.model_state.remove_node(nid)

            elif isinstance(item, MemberItem):
                mid = item.member.id
                connected_nids = (item.member.node_i, item.member.node_j)
                item.remove_extra_items()
                self.removeItem(item)
                self._member_items.pop(mid, None)
                self.model_state.remove_member(mid)
                for nid in connected_nids:
                    nitem = self._node_items.get(nid)
                    if nitem:
                        nitem._draw_hinge_indicator()
        self.model_changed.emit()

    def _cancel_member_drag(self) -> None:
        self._member_start_node = None
        if self._ghost_line:
            self.removeItem(self._ghost_line)
            self._ghost_line = None

    # ── overlay API ───────────────────────────────────────────────────────────

    def update_overlays(
        self,
        model,
        sub_results,
        displacements,
        member_el_map,
        diag_scale_mult: float = 1.0,
        def_scale_mult:  float = 1.0,
    ) -> None:
        """Recompute and redraw all overlay layers.

        Lazy-imports canvas_overlay to avoid circular imports.
        Auto-scales are computed first, then multiplied by the user multipliers.
        """
        # Remove previous overlays before adding new ones
        self.clear_overlays()

        from ui_qt.canvas_overlay import (
            build_load_map,
            compute_auto_scales,
            draw_bmd,
            draw_sfd,
            draw_afd,
            draw_deformed,
            draw_labels,
        )

        load_map = build_load_map(model)
        diag_auto, def_auto = compute_auto_scales(model, sub_results, displacements)

        diag_scale = diag_auto * diag_scale_mult
        def_scale  = def_auto  * def_scale_mult

        # Build member ID arrays for overlay tagging (enables per-member isolation).
        # member_el_map[i] corresponds to model_state.members[i].
        member_ids = [m.id for m in self.model_state.members]
        el_id_to_member_id: dict[int, int] = {}
        for mi, el_ids in enumerate(member_el_map):
            if mi < len(member_ids):
                for eid in el_ids:
                    el_id_to_member_id[eid] = member_ids[mi]

        layer_items: dict[str, list] = {
            'BMD':      draw_bmd(model, sub_results, load_map, diag_scale, member_el_map,
                                 member_ids=member_ids),
            'SFD':      draw_sfd(model, sub_results, load_map, diag_scale, member_el_map,
                                 member_ids=member_ids),
            'AFD':      draw_afd(model, sub_results,
                                 el_id_to_member_id=el_id_to_member_id),
            'Deformed': draw_deformed(model, displacements, def_scale,
                                      el_id_to_member_id=el_id_to_member_id),
            'Labels':   draw_labels(model, sub_results, load_map, diag_scale, member_el_map,
                                    displacements=displacements, def_scale=def_scale,
                                    member_ids=member_ids),
        }

        # Build per-member item groups for isolation support.
        # Use data(0) tags set by draw_* functions; fall back to scanning all items.
        self._member_overlay_items.clear()
        for layer, items in layer_items.items():
            visible = self._overlay_visible.get(layer, True)
            for item in items:
                self.addItem(item)
                item.setVisible(visible)
                uid = item.data(0)
                if uid is not None:
                    self._member_overlay_items.setdefault(uid, []).append(item)
            self._overlay_items[layer] = items

    def update_overlays_single_combo(
        self,
        run: dict,
        combo_index: int,
        all_runs: list[dict],
        diag_scale_mult: float = 1.0,
        def_scale_mult:  float = 1.0,
    ) -> None:
        """Draw one combo at the global envelope scale and its palette colour.

        Uses compute_auto_scales_envelope across all_runs so that switching
        between individual combos preserves relative magnitudes (the same
        scale as the superposed view). The palette colour matches
        _COMBO_PALETTE[combo_index] — identical to the superposed view.
        """
        self.clear_overlays()

        from ui_qt.canvas_overlay import (
            build_load_map,
            compute_auto_scales,
            compute_auto_scales_envelope,
            draw_bmd_all_combos,
            draw_sfd_all_combos,
            draw_afd,
            draw_deformed,
            draw_labels,
        )

        model         = run['model']
        sub_results   = run['sub_results']
        displacements = run['displacements']
        member_el_map = run['member_el_map']
        load_map      = build_load_map(model)

        # Diagram scale: global across all combos so magnitudes are comparable
        diag_auto = compute_auto_scales_envelope(model, all_runs)
        # Deformed scale: per-combo so the shape stays visible even for small displacements
        _, def_auto = compute_auto_scales(model, sub_results, displacements)

        diag_scale = diag_auto * diag_scale_mult
        def_scale  = def_auto  * def_scale_mult

        layer_items: dict[str, list] = {
            'BMD': draw_bmd_all_combos(
                model, [run], diag_scale, member_el_map, start_index=combo_index
            ),
            'SFD': draw_sfd_all_combos(
                model, [run], diag_scale, member_el_map, start_index=combo_index
            ),
            'AFD':      draw_afd(model, sub_results),
            'Deformed': draw_deformed(model, displacements, def_scale),
            'Labels':   draw_labels(model, sub_results, load_map, diag_scale, member_el_map,
                                    displacements=displacements, def_scale=def_scale),
        }

        for layer, items in layer_items.items():
            visible = self._overlay_visible.get(layer, True)
            for item in items:
                self.addItem(item)
                item.setVisible(visible)
            self._overlay_items[layer] = items

    def update_overlays_envelope(
        self,
        model,
        solve_runs_rich: list[dict],
        diag_scale_mult: float = 1.0,
    ) -> None:
        """Redraw overlays showing the BMD/SFD envelope (max + min) across all combos."""
        self.clear_overlays()
        if not solve_runs_rich:
            return

        from ui_qt.canvas_overlay import (
            compute_auto_scales_envelope,
            draw_bmd_envelope,
            draw_sfd_envelope,
        )

        member_el_map_ref = solve_runs_rich[0]['member_el_map']
        diag_auto = compute_auto_scales_envelope(model, solve_runs_rich)
        scale     = diag_auto * diag_scale_mult

        layer_items: dict[str, list] = {
            'BMD':      draw_bmd_envelope(model, solve_runs_rich, scale, member_el_map_ref),
            'SFD':      draw_sfd_envelope(model, solve_runs_rich, scale, member_el_map_ref),
            'AFD':      [],
            'Deformed': [],
            'Labels':   [],
        }
        for layer, items in layer_items.items():
            visible = self._overlay_visible.get(layer, True)
            for item in items:
                self.addItem(item)
                item.setVisible(visible)
            self._overlay_items[layer] = items

    def update_overlays_all_combos(
        self,
        model,
        solve_runs_rich: list[dict],
        diag_scale_mult: float = 1.0,
    ) -> None:
        """Redraw overlays showing every combination superposed in distinct palette colours."""
        self.clear_overlays()
        if not solve_runs_rich:
            return

        from ui_qt.canvas_overlay import (
            compute_auto_scales_envelope,
            draw_bmd_all_combos,
            draw_sfd_all_combos,
        )

        member_el_map_ref = solve_runs_rich[0]['member_el_map']
        diag_auto = compute_auto_scales_envelope(model, solve_runs_rich)
        scale     = diag_auto * diag_scale_mult

        layer_items: dict[str, list] = {
            'BMD':      draw_bmd_all_combos(model, solve_runs_rich, scale, member_el_map_ref),
            'SFD':      draw_sfd_all_combos(model, solve_runs_rich, scale, member_el_map_ref),
            'AFD':      [],
            'Deformed': [],
            'Labels':   [],
        }
        for layer, items in layer_items.items():
            visible = self._overlay_visible.get(layer, True)
            for item in items:
                self.addItem(item)
                item.setVisible(visible)
            self._overlay_items[layer] = items

    def clear_overlays(self) -> None:
        """Remove all overlay graphics items from the scene."""
        for items in self._overlay_items.values():
            for item in items:
                self.removeItem(item)
        self._overlay_items.clear()
        self._member_overlay_items.clear()

    def reproject(self) -> None:
        """Reposition all items after the isometric projection angles change."""
        for nitem in self._node_items.values():
            nitem.refresh()
        self.update_depth_order()
        self.invalidate(self.sceneRect())

    def set_view(self, azimuth: float = -45.0, elevation: float = 30.0) -> None:
        """Set the 3D view angle and reproject.  Elevation clamped to 0–90°."""
        _proj.ISO_AZIMUTH = azimuth
        _proj.ISO_ELEVATION = max(0.0, min(90.0, elevation))
        self.reproject()

    def set_view_preset(self, azimuth: float, elevation: float) -> None:
        """Snap to a named view and emit view_preset so MainWindow can sync the working plane."""
        self.set_view(azimuth, elevation)
        self.view_preset.emit(azimuth, _proj.ISO_ELEVATION)  # use clamped elevation

    def reset_view(self) -> None:
        """Reset orbit to the default isometric view (↙ SW)."""
        self.set_view()

    def update_depth_order(self) -> None:
        """Update member Z-values so nearer members render on top."""
        from ui_qt.projection import depth_order
        members_coords = []
        mitem_list = list(self._member_items.values())
        for mitem in mitem_list:
            ms = self.model_state
            ni = ms.get_node(mitem.member.node_i)
            nj = ms.get_node(mitem.member.node_j)
            if ni and nj:
                members_coords.append((ni.x, ni.y, getattr(ni, 'z', 0.0),
                                       nj.x, nj.y, getattr(nj, 'z', 0.0)))
            else:
                members_coords.append((0, 0, 0, 0, 0, 0))
        if members_coords:
            order = depth_order(members_coords)
            for rank, idx in enumerate(order):
                mitem_list[idx].setZValue(1.0 + rank * 0.001)

    def update_member_colours(self, member_results: list) -> None:
        """Colour members by axial force: red=compression, blue=tension."""
        max_N = max(
            (max(abs(r.N_i), abs(r.N_j)) for r in member_results),
            default=0.0
        )
        for r in member_results:
            mitem = self._member_items.get(r.element_id)
            if mitem:
                mitem.set_force_colour((r.N_i + r.N_j) / 2, max_N)

    def clear_member_colours(self) -> None:
        """Reset all member colours back to their default type-based pens."""
        for mitem in self._member_items.values():
            mitem._update_pen()

    def set_colour_by_group(self, enabled: bool) -> None:
        """Toggle the 'Colour by Group' view: members are tinted by their group
        label instead of by element type. Result colouring (force/util) still
        overrides this until cleared."""
        self._colour_by_group = bool(enabled)
        scale = self._current_view_scale()
        for mitem in self._member_items.values():
            mitem.update_visual_scale(scale)
        self.update()

    def active_groups(self) -> list[str]:
        """Distinct non-empty member group labels, in first-seen order."""
        seen: list[str] = []
        for m in self.model_state.members:
            g = (m.group or "").strip()
            if g and g not in seen:
                seen.append(g)
        return seen

    def update_member_util_colours(self, member_results: list,
                                   members: list) -> None:
        """Colour members by EC3 utilization ratio η (combined N + M)."""
        mem_map = {m.id: m for m in members}
        for r in member_results:
            mdata = mem_map.get(r.element_id)
            mitem = self._member_items.get(r.element_id)
            if mitem is None or mdata is None:
                continue
            fy   = mdata.fy if mdata.fy > 1e3 else 275e6
            A    = mdata.A
            W_pl = mdata.W_pl
            N_Rd = A * fy if A > 0 else 1e20   # γM0 = 1.0
            M_Rd = W_pl * fy if W_pl > 0 else 0.0
            N_Ed = max(abs(r.N_i), abs(r.N_j))
            M_Ed = max(abs(r.M_i), abs(r.M_j))
            eta_N = N_Ed / N_Rd if N_Rd > 1e-12 else 0.0
            eta_M = M_Ed / M_Rd if M_Rd > 1e-12 else 0.0
            eta   = eta_N + eta_M
            mitem.set_util_colour(eta)
        self._util_colour_active = True
        self.update()

    def clear_util_colours(self) -> None:
        """Reset all member colours and hide the util legend."""
        self.clear_member_colours()
        self._util_colour_active = False
        self.update()

    def set_overlay_visible(self, layer: str, visible: bool) -> None:
        """Toggle visibility of a named overlay layer, respecting isolation mode."""
        self._overlay_visible[layer] = visible
        if self._isolated:
            # In isolation mode: only show items for visible isolated members
            isolated_items: set = set()
            for mid, items in self._member_overlay_items.items():
                if mid in self._isolated_member_ids:
                    isolated_items.update(items)
            for item in self._overlay_items.get(layer, []):
                item.setVisible(visible and item in isolated_items)
        else:
            for item in self._overlay_items.get(layer, []):
                item.setVisible(visible)

    # ── public API ────────────────────────────────────────────────────────────

    def refresh_all_loads(self) -> None:
        """Redraw load symbols.  In 'all cases' mode overlays every load case."""
        state = self.model_state
        if self._show_all_cases:
            original_id = state.active_case_id
            first = True
            for i, lc in enumerate(state.load_cases):
                state.active_case_id = lc.id
                color = _LC_COLORS[i % len(_LC_COLORS)]
                perp_off = i * _PERP_OFFSET_STEP
                lc_name = lc.name or f"LC{i}"
                for item in self._node_items.values():
                    item._draw_load_symbols(clear=first, color=color, lc_name=lc_name)
                for item in self._member_items.values():
                    item._draw_udl_arrows(clear=first, color=color,
                                          perp_offset=perp_off, lc_name=lc_name)
                    item._draw_lateral_arrows(clear=first, color=color,
                                              perp_offset=perp_off, lc_name=lc_name)
                    item._draw_point_loads(clear=first, color=color,
                                           perp_offset=perp_off, lc_name=lc_name)
                first = False
            state.active_case_id = original_id
        else:
            for item in self._node_items.values():
                item._draw_load_symbols()
            for item in self._member_items.values():
                item._draw_udl_arrows()
                item._draw_lateral_arrows()
                item._draw_point_loads()
                item._draw_partial_load_arrows()

    def clear_model(self) -> None:
        """Clear all scene items, overlay items, and model state."""
        self.clear()   # removes ALL items; drawBackground() handles the grid
        self._overlay_items.clear()
        self._node_items.clear()
        self._member_items.clear()
        self.model_state.clear()
        self._isolated = False

    def load_state(self, state: ModelState) -> None:
        self.clear_model()
        self.model_state = state
        self._suppress_changed = True
        for node in state.nodes:
            self._add_node_item(node)
        for member in state.members:
            self._add_member_item(member)
        self._suppress_changed = False
        self.model_changed.emit()
        # Redraw all load arrows now that every member exists so w_global_max
        # is correct for the whole model (each item drew its own arrows during
        # __init__ when only a partial set of members existed).
        self.refresh_all_loads()

    def paste(self, clipboard: dict) -> tuple[list[int], list[int]]:
        """Paste clipboard nodes/members into the model with an auto-computed offset.

        The X offset equals the clipboard's bounding-box width (minimum 1 m) so
        that a duplicated bay lands directly adjacent to the original.
        Returns (new_node_ids, new_member_ids).
        """
        nodes = clipboard.get("nodes", [])
        members = clipboard.get("members", [])
        if not nodes and not members:
            return [], []

        # Compute X offset from bounding-box width (min 1 m)
        xs = [n["x"] for n in nodes]
        offset_x = max((max(xs) - min(xs)) if len(xs) > 1 else 0.0, 1.0)

        self.save_snapshot()
        self._suppress_changed = True

        id_map: dict[int, int] = {}
        new_node_ids: list[int] = []
        new_member_ids: list[int] = []

        for nd in nodes:
            new_node = self.model_state.add_node(nd["x"] + offset_x, nd["y"], nd.get("z", 0.0))
            self._add_node_item(new_node)
            id_map[nd["id"]] = new_node.id
            new_node_ids.append(new_node.id)

        for md in members:
            ni_id = id_map.get(md["node_i"])
            nj_id = id_map.get(md["node_j"])
            if ni_id is None or nj_id is None:
                continue
            new_member = self.model_state.add_member(ni_id, nj_id)
            if new_member:
                new_member.element_type = ElementType[md["element_type"]]
                new_member.E = md["E"]
                new_member.A = md["A"]
                new_member.I = md["I"]
                new_member.n_sub = md["n_sub"]
                new_member.density = md["density"]
                self._add_member_item(new_member)
                new_member_ids.append(new_member.id)

        self._suppress_changed = False
        self.model_changed.emit()
        return new_node_ids, new_member_ids

    def get_node_item(self, node_id: int) -> NodeItem | None:
        return self._node_items.get(node_id)

    def get_member_item(self, member_id: int) -> MemberItem | None:
        return self._member_items.get(member_id)

    # ── modeling tools ────────────────────────────────────────────────────────

    def subdivide_member(self, member_id: int,
                         n_divisions: int,
                         nodes_only: bool = False) -> None:
        """Split a member into n_divisions segments with intermediate nodes.

        If nodes_only=True the original member is removed and only the
        intermediate nodes are placed — no sub-members created.
        """
        ms = self.model_state
        member = ms.get_member(member_id)
        if member is None or n_divisions < 2:
            return

        self.save_snapshot()
        self._suppress_changed = True

        ni = ms.get_node(member.node_i)
        nj = ms.get_node(member.node_j)

        # Create intermediate nodes
        inter: list[NodeData] = []
        for k in range(1, n_divisions):
            t = k / n_divisions
            new_nd = ms.add_node(
                ni.x + t * (nj.x - ni.x),
                ni.y + t * (nj.y - ni.y),
                ni.z + t * (nj.z - ni.z),
            )
            self._add_node_item(new_nd)
            inter.append(new_nd)

        if not nodes_only:
            chain = [ni] + inter + [nj]
            for k in range(n_divisions):
                nm = ms.add_member(chain[k].id, chain[k + 1].id)
                if nm:
                    nm.element_type = member.element_type
                    nm.E = member.E
                    nm.A = member.A
                    nm.I = member.I
                    nm.I_y = member.I_y
                    nm.J = member.J
                    nm.n_sub = member.n_sub
                    nm.density = member.density
                    nm.beta_angle = member.beta_angle
                    self._add_member_item(nm)

        # Remove original member
        mi = self._member_items.pop(member_id, None)
        if mi:
            mi.remove_extra_items()
            self.removeItem(mi)
        ms.remove_member(member_id)

        self._suppress_changed = False
        self.model_changed.emit()

    def mirror_selection(self, plane: str,
                         offset: float,
                         keep_original: bool) -> None:
        """Mirror selected nodes and members about the given plane.

        plane : 'XY' | 'XZ' | 'YZ'
        offset: coordinate of the mirror plane on the locked axis
        """
        ms = self.model_state
        sel_nodes   = [it.node   for it in self.selectedItems() if isinstance(it, NodeItem)]
        sel_members = [it.member for it in self.selectedItems() if isinstance(it, MemberItem)]
        if not sel_nodes and not sel_members:
            return

        # Include endpoints of selected members even if nodes not explicitly selected
        extra_node_ids = {m.node_i for m in sel_members} | {m.node_j for m in sel_members}
        all_src_nodes  = {n.id: n for n in sel_nodes}
        for nid in extra_node_ids:
            nd = ms.get_node(nid)
            if nd:
                all_src_nodes[nid] = nd

        self.save_snapshot()
        self._suppress_changed = True

        def _mirror_coord(x: float, y: float, z: float) -> tuple[float, float, float]:
            if plane == "XY":
                return x, y, 2 * offset - z
            if plane == "XZ":
                return x, 2 * offset - y, z
            return 2 * offset - x, y, z  # YZ

        id_map: dict[int, int] = {}
        for src_id, src in all_src_nodes.items():
            mx, my, mz = _mirror_coord(src.x, src.y, src.z)
            existing = ms.node_at(mx, my, mz)
            if existing:
                id_map[src_id] = existing.id
            else:
                new_nd = ms.add_node(mx, my, mz)
                self._add_node_item(new_nd)
                id_map[src_id] = new_nd.id

        for m in sel_members:
            ni_id = id_map.get(m.node_i)
            nj_id = id_map.get(m.node_j)
            if ni_id is None or nj_id is None:
                continue
            nm = ms.add_member(ni_id, nj_id)
            if nm:
                nm.element_type = m.element_type
                nm.E = m.E; nm.A = m.A; nm.I = m.I
                nm.I_y = m.I_y; nm.J = m.J
                nm.n_sub = m.n_sub; nm.density = m.density
                nm.beta_angle = m.beta_angle
                self._add_member_item(nm)

        if not keep_original:
            for m in list(sel_members):
                mi = self._member_items.pop(m.id, None)
                if mi:
                    mi.remove_extra_items(); self.removeItem(mi)
                ms.remove_member(m.id)
            for src_id in list(all_src_nodes):
                ni = self._node_items.pop(src_id, None)
                if ni:
                    ni.remove_extra_items(); self.removeItem(ni)
                ms.remove_node(src_id)

        self._suppress_changed = False
        self.model_changed.emit()


# ─────────────────────────────────────────────────────────────────────────────
# StructView
# ─────────────────────────────────────────────────────────────────────────────

class StructView(QGraphicsView):
    """Viewport for StructCanvas with zoom and pan support."""

    def __init__(self, scene: StructCanvas, parent=None) -> None:
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self._pan_last = None    # QPoint when middle-button is held (pan)
        self._orbit_last = None  # QPoint when middle is held (3D orbit)
        self._orbit_center: tuple[float,float,float] | None = None  # world pivot
        self._view_cube = ViewCube()
        self.setMouseTracking(True)  # needed for hover updates
        self._rb_start: QPoint | None = None   # rubber-band drag start (viewport px)
        self._rb_end:   QPoint | None = None   # rubber-band drag current end

        # Branding watermark — load logo once and cache it
        from pathlib import Path
        _logo = Path(__file__).parent / "assets" / "instra_logo.png"
        self._branding_pix: QPixmap | None = (
            QPixmap(str(_logo)) if _logo.exists() else None
        )

        # Refresh the foreground (HUD) whenever selection changes
        scene.selectionChanged.connect(lambda: self.viewport().update())

    # ── grid drawn here so it always fills the visible viewport ──────────────

    # Available sub-grid spacings in metres — the renderer picks the one
    # that keeps minor-line spacing between 20–50 px at the current zoom.
    _SUB_SPACINGS = (1.0, 0.5, 0.25, 0.1, 0.05, 0.025)

    def drawBackground(self, painter: QPainter, rect) -> None:
        bg = QColor("#1a1a1e")
        painter.fillRect(rect, bg)

        # Welcome overlay — only on first launch before any user action
        if not self.scene()._hide_welcome and not self.scene().model_state.nodes:
            painter.setPen(QPen(QColor("#4a4a50"), 1))
            font = painter.font()
            font.setPointSize(18)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "StructLab")
            font.setPointSize(10)
            font.setBold(False)
            painter.setFont(font)
            painter.setPen(QPen(QColor("#3a3a40"), 1))
            r2 = rect.adjusted(0, 30, 0, 0)
            painter.drawText(r2, Qt.AlignmentFlag.AlignCenter,
                             "Press N to add a node  |  Ctrl+O to open  |  Presets menu to start")
            return

        self._draw_iso_grid(painter, rect)

        if self.scene()._grab_active:
            self._draw_grab_status(painter, rect)

        if self.scene()._util_colour_active:
            self._draw_util_legend(painter, rect)
        elif self.scene()._colour_by_group:
            self._draw_group_legend(painter, rect)

    def drawForeground(self, painter: QPainter, rect) -> None:
        """Viewport-pinned overlays drawn above all scene content.

        Uses painter.resetTransform() so everything is in stable viewport pixels —
        no floating-point drift from scene coordinate mapping, and no interaction
        with the zoom level.  Draw order: rubber band → ViewCube → logo, so the
        cube and logo always appear on top of the selection rectangle.
        """
        scene = self.scene()
        if not scene._hide_welcome and not scene.model_state.nodes:
            return  # nothing to overlay in the empty welcome state

        painter.save()
        painter.resetTransform()          # switch to viewport pixel coordinates
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        vp = self.viewport()
        w, h = vp.width(), vp.height()

        # ── 1. Custom rubber-band selection rectangle ─────────────────────────
        if self._rb_start is not None and self._rb_end is not None:
            rb = QRect(self._rb_start, self._rb_end).normalized()
            if rb.width() > 2 or rb.height() > 2:
                crossing = self._rb_end.x() < self._rb_start.x()
                if crossing:
                    # Right-to-left: crossing selection — green dashed
                    rb_pen = QPen(QColor(60, 210, 90, 220))
                    rb_pen.setCosmetic(True)
                    rb_pen.setStyle(Qt.PenStyle.DashLine)
                    painter.setPen(rb_pen)
                    painter.setBrush(QBrush(QColor(40, 180, 70, 28)))
                else:
                    # Left-to-right: window selection — blue solid
                    rb_pen = QPen(QColor(0, 150, 220, 220))
                    rb_pen.setCosmetic(True)
                    painter.setPen(rb_pen)
                    painter.setBrush(QBrush(QColor(0, 120, 200, 28)))
                painter.drawRect(rb)

        # ── 2. ViewCube (top-right corner) ───────────────────────────────────
        vc = self._view_cube
        vc_cx = float(w - (vc.MARGIN + vc.HALF))
        vc_cy = float(vc.MARGIN + vc.HALF)
        vc.paint(painter, vc_cx, vc_cy, 1.0)

        # ── 3. Working plane label (just below the ViewCube) ─────────────────
        plane  = scene._working_plane
        offset = scene._plane_offset
        lbl_pen = QPen(QColor("#00cccc"))
        lbl_pen.setCosmetic(True)
        painter.setPen(lbl_pen)
        z_font = painter.font()
        z_font.setPointSize(8)
        z_font.setBold(True)
        painter.setFont(z_font)
        _axis_map = {
            WorkingPlane.XY:   f"Z = {offset:.2f} m",
            WorkingPlane.XZ:   f"Y = {offset:.2f} m",
            WorkingPlane.YZ:   f"X = {offset:.2f} m",
            WorkingPlane.FREE: "Free (XY ground)",
        }
        plane_text = f"Plane {plane.name}  |  {_axis_map[plane]}"
        lbl_y = float(vc.MARGIN * 2 + vc.HALF * 2 + 16)
        painter.drawText(QPointF(w - 215.0, lbl_y), plane_text)
        z_font.setBold(False)
        painter.setFont(z_font)

        # ── 4. Branding badge (bottom-right corner) ───────────────────────────
        margin = 10.0;  pad_x = 7.0;  pad_y = 5.0
        logo_h = 26.0;  line_h = 13.0
        box_h  = logo_h + 2 * pad_y
        box_w  = 148.0
        x0 = w - margin - box_w
        y0 = h - margin - box_h

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(18, 18, 22, 160)))
        painter.drawRoundedRect(_QRectF(x0, y0, box_w, box_h), 4.0, 4.0)

        text_x = x0 + pad_x
        if self._branding_pix and not self._branding_pix.isNull():
            asp    = self._branding_pix.width() / max(self._branding_pix.height(), 1)
            logo_w = asp * logo_h
            painter.drawPixmap(
                _QRectF(x0 + pad_x, y0 + pad_y, logo_w, logo_h),
                self._branding_pix,
                _QRectF(self._branding_pix.rect()),
            )
            text_x = x0 + pad_x + logo_w + pad_x

        font = painter.font()
        font.setPointSize(8);  font.setBold(True)
        painter.setFont(font)
        name_pen = QPen(QColor(215, 215, 215));  name_pen.setCosmetic(True)
        painter.setPen(name_pen)
        painter.drawText(QPointF(text_x, y0 + pad_y + line_h * 0.88), "StructLabPro")

        font.setPointSize(7);  font.setBold(False)
        painter.setFont(font)
        ver_pen = QPen(QColor(130, 130, 130));  ver_pen.setCosmetic(True)
        painter.setPen(ver_pen)
        painter.drawText(QPointF(text_x, y0 + pad_y + line_h * 1.90), "V 1.1")

        # ── 5. Selection shortcut HUD (bottom-left, when items are selected) ────
        from ui_qt.canvas_items import NodeItem, MemberItem
        selected = scene.selectedItems()
        if selected and scene._mode == CanvasMode.SELECT:
            _ROWS = [
                ("G",       "Move (grab)"),
                ("E",       "Extrude"),
                ("I",       "Isolate / Restore all"),
                ("Ctrl+D",  "Duplicate array"),
                ("Ctrl+I",  "Invert selection"),
                ("Del",     "Delete"),
            ]
            _hud_pad_x, _hud_pad_y = 9.0, 7.0
            _hud_row_h  = 16.0
            _hud_key_w  = 52.0
            _hud_desc_w = 132.0
            _hud_w = _hud_key_w + _hud_desc_w + _hud_pad_x * 3
            _hud_h = _hud_pad_y * 2 + 18.0 + len(_ROWS) * _hud_row_h
            _hud_x = 12.0
            _hud_y = float(h) - 12.0 - _hud_h

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(18, 18, 24, 185)))
            painter.drawRoundedRect(_QRectF(_hud_x, _hud_y, _hud_w, _hud_h), 5.0, 5.0)

            hf = painter.font()
            hf.setPointSize(8); hf.setBold(True)
            painter.setFont(hf)
            painter.setPen(QPen(QColor("#00cccc")))
            painter.drawText(QPointF(_hud_x + _hud_pad_x, _hud_y + _hud_pad_y + 12.0),
                             "Selection shortcuts")

            hf.setBold(False); hf.setPointSize(8)
            painter.setFont(hf)
            sep_pen = QPen(QColor(60, 60, 80)); sep_pen.setCosmetic(True)
            painter.setPen(sep_pen)
            painter.drawLine(
                QPointF(_hud_x + 6, _hud_y + _hud_pad_y + 17.0),
                QPointF(_hud_x + _hud_w - 6, _hud_y + _hud_pad_y + 17.0),
            )

            for ri, (key_txt, desc_txt) in enumerate(_ROWS):
                ry = _hud_y + _hud_pad_y + 17.0 + (ri + 1) * _hud_row_h
                # Key chip background
                chip_x = _hud_x + _hud_pad_x
                chip_w = _hud_key_w
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(QColor(38, 38, 52, 220)))
                painter.drawRoundedRect(_QRectF(chip_x, ry - 11.0, chip_w, 14.0), 3.0, 3.0)
                # Key label
                painter.setPen(QPen(QColor(200, 200, 220)))
                painter.drawText(
                    _QRectF(chip_x, ry - 11.0, chip_w, 14.0),
                    Qt.AlignmentFlag.AlignCenter, key_txt,
                )
                # Description
                painter.setPen(QPen(QColor(160, 160, 175)))
                painter.drawText(
                    QPointF(_hud_x + _hud_pad_x * 2 + _hud_key_w, ry), desc_txt,
                )

        # ── 6. "ISOLATED" badge (bottom-left above HUD when in isolation mode) ──
        if scene._isolated:
            _iso_font = painter.font()
            _iso_font.setPointSize(9); _iso_font.setBold(True)
            painter.setFont(_iso_font)
            _iso_txt = "  ISOLATED — press I to restore  "
            _iso_metrics = painter.fontMetrics()
            _iso_w = float(_iso_metrics.horizontalAdvance(_iso_txt)) + 4.0
            _iso_h = 22.0
            _iso_x = 12.0
            _iso_y = float(h) - 12.0 - _iso_h - (
                (_hud_h + 6.0) if (selected and scene._mode == CanvasMode.SELECT) else 0.0
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(80, 30, 0, 210)))
            painter.drawRoundedRect(_QRectF(_iso_x, _iso_y, _iso_w, _iso_h), 4.0, 4.0)
            painter.setPen(QPen(QColor("#ff9944")))
            painter.drawText(QPointF(_iso_x + 2.0, _iso_y + 15.0), _iso_txt)

        painter.restore()

    def _draw_grab_status(self, painter: QPainter, rect) -> None:
        """Draw grab/extrude status bar at the bottom-left of the viewport."""
        scene = self.scene()
        axis       = scene._grab_axis
        typed      = scene._grab_typed
        is_extrude = scene._grab_is_extrude
        scale      = self.transform().m11()

        _axis_color = {'X': "#FF4444", 'Y': "#44EE44", 'Z': "#4488FF", None: "#00CCCC"}
        pen = QPen(QColor(_axis_color.get(axis, "#00CCCC")))
        pen.setCosmetic(True)
        painter.setPen(pen)

        font = painter.font()
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)

        verb = "EXTRUDE" if is_extrude else "GRAB"
        if typed:
            status = f"{verb}  {axis or ''}  {typed}_"
        elif axis:
            status = f"{verb}  {axis}  (move mouse or type distance)"
        else:
            status = f"{verb}  (X/Y/Z to constrain · Enter/LMB confirm · Esc cancel)"

        lbl_x = rect.left()  + 12 / scale
        lbl_y = rect.bottom() - 14 / scale
        painter.drawText(QPointF(lbl_x, lbl_y), status)

    def _draw_util_legend(self, painter: QPainter, rect) -> None:
        """Draw a utilization colour bar legend in the bottom-right corner."""
        from PyQt6.QtCore import QRectF as _QRF
        scale = self.transform().m11()

        bar_w = 120 / scale
        bar_h = 14 / scale
        margin = 12 / scale
        x0 = rect.right()  - margin - bar_w
        y0 = rect.bottom() - margin - bar_h - 22 / scale

        grad = QLinearGradient(x0, 0, x0 + bar_w, 0)
        grad.setColorAt(0.00, QColor(0,   200, 80))
        grad.setColorAt(0.50, QColor(230, 210,  0))
        grad.setColorAt(1.00, QColor(230,  40,  0))

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.fillRect(_QRF(x0, y0, bar_w, bar_h), QBrush(grad))

        border_pen = QPen(QColor(180, 180, 180, 200))
        border_pen.setCosmetic(True)
        painter.setPen(border_pen)
        painter.drawRect(_QRF(x0, y0, bar_w, bar_h))

        font = painter.font()
        font.setPointSize(7)
        painter.setFont(font)
        lbl_pen = QPen(QColor(220, 220, 220))
        lbl_pen.setCosmetic(True)
        painter.setPen(lbl_pen)
        tick_y = y0 + bar_h + 9 / scale
        for label, frac in [("0%", 0.0), ("50%", 0.5), ("100%", 1.0)]:
            tx = x0 + frac * bar_w
            painter.drawLine(QPointF(tx, y0 + bar_h),
                             QPointF(tx, y0 + bar_h + 4 / scale))
            painter.drawText(QPointF(tx - len(label) * 2.5 / scale, tick_y), label)

        title_pen = QPen(QColor(200, 200, 200))
        title_pen.setCosmetic(True)
        painter.setPen(title_pen)
        painter.drawText(QPointF(x0, y0 - 5 / scale), "Utilization η  (N/Npl + M/Mpl)")
        painter.restore()

    def _draw_group_legend(self, painter: QPainter, rect) -> None:
        """Draw a swatch legend of member groups in the bottom-right corner."""
        from PyQt6.QtCore import QRectF as _QRF
        groups = self.scene().active_groups()
        if not groups:
            return
        scale = self.transform().m11()

        sw = 12 / scale          # swatch size
        gap = 6 / scale          # swatch → label gap
        row_h = 18 / scale
        margin = 12 / scale
        font_px = 8
        # widen the box to the longest label so text never clips
        label_w = max(len(g) for g in groups) * 6.5 / scale
        box_w = sw + gap + label_w + 16 / scale
        box_h = row_h * len(groups) + 22 / scale
        x0 = rect.right()  - margin - box_w
        y0 = rect.bottom() - margin - box_h

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        panel = QColor(30, 30, 36, 210)
        painter.setPen(QPen(QColor(180, 180, 180, 200)))
        painter.setBrush(QBrush(panel))
        painter.drawRect(_QRF(x0, y0, box_w, box_h))

        font = painter.font()
        font.setPointSize(font_px)
        painter.setFont(font)
        title_pen = QPen(QColor(210, 210, 210)); title_pen.setCosmetic(True)
        painter.setPen(title_pen)
        painter.drawText(QPointF(x0 + 8 / scale, y0 + 14 / scale), "Member groups")

        sx = x0 + 8 / scale
        for i, g in enumerate(groups):
            ry = y0 + 20 / scale + i * row_h
            painter.setPen(QPen(QColor(120, 120, 120, 200)))
            painter.setBrush(QBrush(group_colour(g)))
            painter.drawRect(_QRF(sx, ry, sw, sw))
            lbl_pen = QPen(QColor(225, 225, 225)); lbl_pen.setCosmetic(True)
            painter.setPen(lbl_pen)
            painter.drawText(QPointF(sx + sw + gap, ry + sw - 1 / scale), g)
        painter.restore()

    def _draw_flat_grid(self, painter: QPainter, rect) -> None:
        """Standard rectangular 2D grid."""
        # ── adaptive grid spacing ─────────────────────────────────────────────
        scale = self.transform().m11()
        px_per_m = PX_PER_M * scale
        target_px = 30

        sub_spacing = 0.25
        best_diff = 1e9
        for s in self._SUB_SPACINGS:
            spx = px_per_m * s
            diff = abs(spx - target_px)
            if diff < best_diff:
                best_diff = diff
                sub_spacing = s

        minor_step = int(round(sub_spacing * PX_PER_M))
        if minor_step < 1:
            minor_step = 1
        major_step = GRID_STEP

        minor_pen = QPen(QColor(60, 60, 66)); minor_pen.setCosmetic(True)
        major_pen = QPen(QColor(80, 80, 88)); major_pen.setCosmetic(True)

        left  = int(math.floor(rect.left()   / minor_step)) * minor_step
        right = int(math.ceil( rect.right()  / minor_step)) * minor_step
        top   = int(math.floor(rect.top()    / minor_step)) * minor_step
        bot   = int(math.ceil( rect.bottom() / minor_step)) * minor_step

        minor_v, major_v, minor_h, major_h = [], [], [], []
        x = left
        while x <= right:
            line = QLineF(x, rect.top(), x, rect.bottom())
            (major_v if x % major_step == 0 else minor_v).append(line)
            x += minor_step
        y = top
        while y <= bot:
            line = QLineF(rect.left(), y, rect.right(), y)
            (major_h if y % major_step == 0 else minor_h).append(line)
            y += minor_step

        painter.setPen(minor_pen)
        if minor_v: painter.drawLines(minor_v)
        if minor_h: painter.drawLines(minor_h)
        painter.setPen(major_pen)
        if major_v: painter.drawLines(major_v)
        if major_h: painter.drawLines(major_h)

        # ── World-origin axes (drawn on top of the grid) ──────────────────────
        def _axis_pen(r: int, g: int, b: int) -> QPen:
            p = QPen(QColor(r, g, b, 200))
            p.setCosmetic(True)
            p.setWidthF(2.0)
            return p

        painter.setPen(_axis_pen(190, 55, 55))   # X axis — red, horizontal at y=0
        painter.drawLine(QLineF(rect.left(), 0, rect.right(), 0))
        painter.setPen(_axis_pen(55, 165, 55))   # Y axis — green, vertical at x=0
        painter.drawLine(QLineF(0, rect.top(), 0, rect.bottom()))

    def _draw_iso_grid(self, painter: QPainter, rect) -> None:
        """Isometric grid: adaptive spacing + viewport-following extent."""

        # ── Adaptive spacing: pick finest that keeps lines >= 40 px apart ─────
        scale            = self.transform().m11()
        px_per_m_screen  = PX_PER_M * scale
        _SPACINGS        = [0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 25.0, 50.0]
        spacing          = 50.0
        for s in _SPACINGS:
            if s * px_per_m_screen >= 40.0:
                spacing = s
                break
        major_spacing = spacing * 5.0

        # ── Viewport centre in model space at z = 0 ───────────────────────────
        vp_rect      = self.mapToScene(self.viewport().rect()).boundingRect()
        vc           = vp_rect.center()
        cx, cy       = inverse_isometric(vc.x(), vc.y(), 0.0)

        # ── Extent: enough to fill viewport, capped at 50 m ──────────────────
        extent_m = min(
            max(vp_rect.width(), vp_rect.height()) / PX_PER_M * 1.5 + 5.0,
            50.0,
        )

        # ── Pens ──────────────────────────────────────────────────────────────
        minor_pen = QPen(QColor(52, 52, 60));  minor_pen.setCosmetic(True)
        major_pen = QPen(QColor(82, 82, 94));  major_pen.setCosmetic(True)
        major_pen.setWidthF(1.4)
        pl_minor  = QPen(QColor(0, 120, 140, 110)); pl_minor.setCosmetic(True)
        pl_major  = QPen(QColor(0, 155, 175, 180)); pl_major.setCosmetic(True)
        pl_major.setWidthF(1.4)

        scene  = self.scene()
        plane  = scene._working_plane
        offset = scene._plane_offset

        # ── Helpers ───────────────────────────────────────────────────────────
        def _range(center: float, ext: float) -> list[float]:
            i0 = math.floor((center - ext) / spacing)
            i1 = math.ceil( (center + ext) / spacing) + 1
            return [i * spacing for i in range(i0, i1)]

        def _z_range(ext: float) -> list[float]:
            i0 = math.floor(-ext / spacing)
            i1 = math.ceil(ext / spacing) + 1
            return [i * spacing for i in range(i0, i1)]

        def _is_major(val: float) -> bool:
            return abs(round(val / major_spacing) * major_spacing - val) < spacing * 0.01

        def _pen(val: float, mp: QPen, mjp: QPen) -> QPen:
            return mjp if _is_major(val) else mp

        x_vals = _range(cx, extent_m)
        y_vals = _range(cy, extent_m)
        z_vals = _z_range(extent_m)
        x0, x1 = cx - extent_m, cx + extent_m
        y0, y1 = cy - extent_m, cy + extent_m
        z0 = z_vals[0] if z_vals else -2.0

        # ── XY ground floor ───────────────────────────────────────────────────
        for y_val in y_vals:
            painter.setPen(_pen(y_val, minor_pen, major_pen))
            painter.drawLine(QLineF(*isometric(x0, y_val, 0), *isometric(x1, y_val, 0)))
        for x_val in x_vals:
            painter.setPen(_pen(x_val, minor_pen, major_pen))
            painter.drawLine(QLineF(*isometric(x_val, y0, 0), *isometric(x_val, y1, 0)))

        # ── Active working plane overlay ──────────────────────────────────────
        if plane == WorkingPlane.XY and offset != 0.0:
            for y_val in y_vals:
                painter.setPen(_pen(y_val, pl_minor, pl_major))
                painter.drawLine(QLineF(*isometric(x0, y_val, offset), *isometric(x1, y_val, offset)))
            for x_val in x_vals:
                painter.setPen(_pen(x_val, pl_minor, pl_major))
                painter.drawLine(QLineF(*isometric(x_val, y0, offset), *isometric(x_val, y1, offset)))
        elif plane == WorkingPlane.XZ:
            for z_val in z_vals:
                painter.setPen(_pen(z_val, pl_minor, pl_major))
                painter.drawLine(QLineF(*isometric(x0, offset, z_val), *isometric(x1, offset, z_val)))
            for x_val in x_vals:
                painter.setPen(_pen(x_val, pl_minor, pl_major))
                painter.drawLine(QLineF(*isometric(x_val, offset, z0), *isometric(x_val, offset, extent_m)))
        elif plane == WorkingPlane.YZ:
            for z_val in z_vals:
                painter.setPen(_pen(z_val, pl_minor, pl_major))
                painter.drawLine(QLineF(*isometric(offset, y0, z_val), *isometric(offset, y1, z_val)))
            for y_val in y_vals:
                painter.setPen(_pen(y_val, pl_minor, pl_major))
                painter.drawLine(QLineF(*isometric(offset, y_val, z0), *isometric(offset, y_val, extent_m)))

        # ── World-origin axis indicators (X=red, Y=green, Z=blue) ──────────────
        def _axis3_pen(r: int, g: int, b: int) -> QPen:
            p = QPen(QColor(r, g, b, 220))
            p.setCosmetic(True)
            p.setWidthF(2.0)
            return p

        ax_font = painter.font()
        ax_font.setPointSizeF(10.0 / scale)
        ax_font.setBold(True)
        painter.setFont(ax_font)
        ox, oy   = isometric(0, 0, 0)
        arm_m    = 40.0 / (PX_PER_M * scale)   # fixed 40 screen-px arm

        # Origin dot
        painter.setBrush(QBrush(QColor(220, 220, 235, 230)))
        painter.setPen(QPen(Qt.PenStyle.NoPen))
        painter.drawEllipse(QPointF(ox, oy), 4.0 / scale, 4.0 / scale)
        painter.setBrush(QBrush())

        # X arm — red
        xa, ya_x = isometric(arm_m, 0, 0)
        painter.setPen(_axis3_pen(210, 60, 60))
        painter.drawLine(QLineF(ox, oy, xa, ya_x))
        painter.drawText(QPointF(xa + 5 / scale, ya_x + 5 / scale), "X")

        # Y arm — green
        ya_x2, ya_y2 = isometric(0, arm_m, 0)
        painter.setPen(_axis3_pen(60, 190, 60))
        painter.drawLine(QLineF(ox, oy, ya_x2, ya_y2))
        painter.drawText(QPointF(ya_x2 - 14 / scale, ya_y2 + 5 / scale), "Y")

        # Z arm — blue (straight up in scene space)
        za_sx, za_sy = isometric(0, 0, arm_m)
        painter.setPen(_axis3_pen(70, 110, 230))
        painter.drawLine(QLineF(ox, oy, za_sx, za_sy))
        painter.drawText(QPointF(za_sx + 4 / scale, za_sy - 4 / scale), "Z")

        ax_font.setBold(False)
        painter.setFont(ax_font)

    # ── zoom ──────────────────────────────────────────────────────────────────

    def zoom_to_fit(self) -> None:
        """Fit all scene items into the viewport with one grid-unit of padding.

        Deferred via QTimer so it always runs after Qt has finished laying out
        the view geometry — safe to call immediately after load_state().
        """
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, self._fit_now)

    def _fit_now(self) -> None:
        rect = self.scene().itemsBoundingRect()
        if rect.isEmpty():
            return
        pad = 80  # one grid unit (1 m) of breathing room on each side
        self.fitInView(rect.adjusted(-pad, -pad, pad, pad),
                       Qt.AspectRatioMode.KeepAspectRatio)
        self._notify_zoom()

    def wheelEvent(self, event) -> None:
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)
        self._notify_zoom()

    def _notify_zoom(self) -> None:
        """Propagate current view scale to all node/member items for zoom-responsive sizing."""
        sc = self.scene()
        if sc is None:
            return
        view_scale = self.transform().m11()
        for item in sc._node_items.values():
            item.update_visual_scale(view_scale)
        for item in sc._member_items.values():
            item.update_visual_scale(view_scale)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self.zoom_to_fit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def _selected_centroid(self) -> tuple[float,float,float] | None:
        """World centroid of selected nodes/members, or None if nothing selected."""
        from ui_qt.canvas_items import NodeItem, MemberItem
        ms = self.scene().model_state
        xs, ys, zs = [], [], []
        for item in self.scene().selectedItems():
            if isinstance(item, NodeItem):
                xs.append(item.node.x); ys.append(item.node.y); zs.append(item.node.z)
            elif isinstance(item, MemberItem):
                ni = ms.get_node(item.member.node_i)
                nj = ms.get_node(item.member.node_j)
                if ni and nj:
                    xs += [ni.x, nj.x]; ys += [ni.y, nj.y]; zs += [ni.z, nj.z]
        if not xs:
            return None
        return (sum(xs)/len(xs), sum(ys)/len(ys), sum(zs)/len(zs))

    # ── middle-mouse pan (ScrollHandDrag only works with left button) ─────────

    def mousePressEvent(self, event) -> None:
        # ── ViewCube click — hit-test in stable viewport pixels ───────────────
        if event.button() == Qt.MouseButton.LeftButton:
            vc = self._view_cube
            vc_cx = float(self.viewport().width()  - (vc.MARGIN + vc.HALF))
            vc_cy = float(vc.MARGIN + vc.HALF)
            result = self._view_cube.hit_test(
                QPointF(event.pos()), vc_cx, vc_cy, 1.0, _proj.ISO_AZIMUTH
            )
            if result is not None:
                az, el = result
                self.scene().set_view_preset(az, el)
                self.scene().view_changed.emit()
                self._view_cube.hovered = None
                self.viewport().update()
                event.accept()
                return

        # ── Plane-label click → quick-set dialog for the working-plane offset ───
        if event.button() == Qt.MouseButton.LeftButton:
            vp   = self.viewport()
            w, h = vp.width(), vp.height()
            vc   = self._view_cube
            # The label is drawn at (w-215, lbl_y) where lbl_y = MARGIN*2+HALF*2+16
            lbl_y   = vc.MARGIN * 2 + vc.HALF * 2 + 16
            lbl_hit = QRect(w - 220, lbl_y - 16, 165, 22)
            scene   = self.scene()
            if (lbl_hit.contains(event.pos())
                    and scene._working_plane is not WorkingPlane.FREE):
                axis_name = {
                    WorkingPlane.XY: "Z",
                    WorkingPlane.XZ: "Y",
                    WorkingPlane.YZ: "X",
                }[scene._working_plane]
                val, ok = QInputDialog.getDouble(
                    self, "Set plane offset",
                    f"{axis_name} coordinate (m):",
                    scene._plane_offset,
                    -1000.0, 1000.0, 3,
                )
                if ok:
                    scene.set_plane_offset(val)
                event.accept()
                return

        # ── Start custom rubber-band on empty-space left-click in SELECT mode ──
        if (event.button() == Qt.MouseButton.LeftButton
                and self.scene()._mode == CanvasMode.SELECT):
            item_under = self.scene().itemAt(
                self.mapToScene(event.pos()), self.viewportTransform()
            )
            if item_under is None:
                self._rb_start = event.pos()
                self._rb_end   = None

        # ── Middle mouse: orbit (3D) or pan ──────────────────────────────────
        if event.button() == Qt.MouseButton.MiddleButton:
            shift = event.modifiers() & Qt.KeyboardModifier.ShiftModifier
            if shift:
                self._orbit_last = event.pos()
                self._orbit_center = self._selected_centroid()
                self.scene().clear_overlays()
                self.setCursor(Qt.CursorShape.SizeAllCursor)
            else:
                self._pan_last = event.pos()
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._orbit_last is not None:
            delta = event.pos() - self._orbit_last
            self._orbit_last = event.pos()
            # Capture pivot screen position before reprojection
            if self._orbit_center is not None:
                sx0, sy0 = _proj.isometric(*self._orbit_center)
                vp_before = self.mapFromScene(QPointF(sx0, sy0))
            _proj.ISO_AZIMUTH   = _proj.ISO_AZIMUTH + delta.x() * 0.3
            _proj.ISO_ELEVATION = max(-89.0, min(89.0, _proj.ISO_ELEVATION - delta.y() * 0.3))
            self.scene().reproject()
            # Adjust scroll bars so pivot stays at same screen position
            if self._orbit_center is not None:
                sx1, sy1 = _proj.isometric(*self._orbit_center)
                vp_after = self.mapFromScene(QPointF(sx1, sy1))
                self.horizontalScrollBar().setValue(
                    self.horizontalScrollBar().value() + int(vp_after.x() - vp_before.x())
                )
                self.verticalScrollBar().setValue(
                    self.verticalScrollBar().value() + int(vp_after.y() - vp_before.y())
                )
            event.accept()
            return
        if self._pan_last is not None:
            delta = event.pos() - self._pan_last
            self._pan_last = event.pos()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x()
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y()
            )
            event.accept()
            return

        # ── Custom rubber-band update ─────────────────────────────────────────
        if (self._rb_start is not None
                and event.buttons() & Qt.MouseButton.LeftButton):
            delta = event.pos() - self._rb_start
            if abs(delta.x()) > 3 or abs(delta.y()) > 3:
                self._rb_end = event.pos()
                self.viewport().update()
                return  # suppress item hover while dragging

        # ── ViewCube hover highlight — in stable viewport pixels ──────────────
        vc = self._view_cube
        vc_cx = float(self.viewport().width()  - (vc.MARGIN + vc.HALF))
        vc_cy = float(vc.MARGIN + vc.HALF)
        if self._view_cube.update_hover(QPointF(event.pos()), vc_cx, vc_cy, 1.0):
            self.viewport().update()

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            was_orbiting = self._orbit_last is not None
            self._pan_last = None
            self._orbit_last = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            if was_orbiting:
                self.scene().view_changed.emit()
            event.accept()
            return

        # ── Finalise rubber-band selection ────────────────────────────────────
        if event.button() == Qt.MouseButton.LeftButton:
            if self._rb_start is not None and self._rb_end is not None:
                # Determine mode BEFORE normalizing (direction carries semantic meaning)
                crossing = self._rb_end.x() < self._rb_start.x()
                sel_mode = (Qt.ItemSelectionMode.IntersectsItemShape if crossing
                            else Qt.ItemSelectionMode.ContainsItemShape)
                rb = QRect(self._rb_start, self._rb_end).normalized()
                if rb.width() > 3 or rb.height() > 3:
                    path = QPainterPath()
                    path.addPolygon(self.mapToScene(rb))
                    path.closeSubpath()
                    op = (Qt.ItemSelectionOperation.AddToSelection
                          if event.modifiers() & Qt.KeyboardModifier.ControlModifier
                          else Qt.ItemSelectionOperation.ReplaceSelection)
                    self.scene().setSelectionArea(
                        path, op,
                        sel_mode,
                        self.viewportTransform(),
                    )
                    self._rb_start = None
                    self._rb_end   = None
                    self.viewport().update()
                    event.accept()
                    return
            self._rb_start = None
            self._rb_end   = None

        super().mouseReleaseEvent(event)

    # ── right-click context menu ──────────────────────────────────────────────

    def contextMenuEvent(self, event) -> None:
        scene = self.scene()
        sel   = scene.selectedItems()

        # Right-click does not auto-select in Qt. If nothing is selected, select
        # the structural item under the cursor so the menu has something to act on.
        if not sel:
            for it in self.items(event.pos()):
                target = it
                while (target is not None
                       and not isinstance(target, (NodeItem, MemberItem))):
                    target = target.parentItem()
                if target is not None:
                    scene.clearSelection()
                    target.setSelected(True)
                    sel = [target]
                    break

        nodes   = [it.node   for it in sel if isinstance(it, NodeItem)]
        members = [it.member for it in sel if isinstance(it, MemberItem)]

        menu = QMenu(self)

        # ── Delete ────────────────────────────────────────────────────────────
        if nodes or members:
            lbl = "Delete"
            if nodes and not members:
                lbl = f"Delete {len(nodes)} node(s)"
            elif members and not nodes:
                lbl = f"Delete {len(members)} member(s)"
            act_del = menu.addAction(lbl)
            act_del.setShortcut("Del")
            act_del.triggered.connect(scene._delete_selected)
            menu.addSeparator()

        # ── Set Support (nodes only) ──────────────────────────────────────────
        if nodes:
            sup_menu = menu.addMenu("Set Support")
            _SUPPORT_LABELS = [
                ("Fixed",    SupportType.FIXED),
                ("Pinned",   SupportType.PIN),
                ("Roller",   SupportType.ROLLER),
                ("Roller Y", SupportType.ROLLER_Y),
                ("Roller Z", SupportType.ROLLER_Z),
                ("None",     SupportType.FREE),
            ]
            for label, stype in _SUPPORT_LABELS:
                a = sup_menu.addAction(label)
                a.triggered.connect(
                    lambda _checked=False, st=stype: self._set_support(nodes, st)
                )
            menu.addSeparator()

        # ── Modeling tools (members selected) ────────────────────────────────
        if members:
            # Divide — split into multiple real elements (full new nodes + sub-members)
            div_menu = menu.addMenu("Divide")
            _DIVIDE_PRESETS = [
                ("Split in half  (1 node, 2 elements)", 2),
                ("Add 5 nodes  (6 elements)",           6),
                ("Add 10 nodes  (11 elements)",         11),
            ]
            for label, n_div in _DIVIDE_PRESETS:
                a = div_menu.addAction(label)
                a.triggered.connect(
                    lambda _checked=False, ms=members, n=n_div:
                        self._divide_quick(ms, n)
                )
            div_menu.addSeparator()
            act_div_custom = div_menu.addAction("Custom…")
            act_div_custom.triggered.connect(
                lambda _checked=False, ms=members: self._on_divide_custom(ms)
            )

            # Subdivide — existing analysis-mesh / nodes-only tool (unchanged)
            act_sub = menu.addAction("Subdivide…")
            act_sub.triggered.connect(
                lambda _checked=False, ms=members: self._on_subdivide(ms)
            )
            menu.addSeparator()

        # ── Mirror (any selection) ────────────────────────────────────────────
        if nodes or members:
            act_mir = menu.addAction("Mirror…")
            act_mir.triggered.connect(
                lambda _checked=False: self._on_mirror(True)
            )

        # ── Paste ─────────────────────────────────────────────────────────────
        mw = self.window()
        if hasattr(mw, '_on_paste') and hasattr(mw, '_clipboard') and mw._clipboard:
            if nodes or members:
                menu.addSeparator()
            menu.addAction("Paste").triggered.connect(mw._on_paste)

        if not menu.isEmpty():
            menu.exec(event.globalPos())

    def _set_support(self, nodes: list, stype: SupportType) -> None:
        scene = self.scene()
        scene.save_snapshot()
        for nd in nodes:
            nd.support_type = stype
            item = scene.get_node_item(nd.id)
            if item:
                item._draw_support_symbol()
        scene.model_changed.emit()

    def _divide_quick(self, members: list, n_divisions: int) -> None:
        """Subdivide each selected member into n_divisions segments (quick preset).

        Keeps the sub-member segments (nodes_only=False) so the divided member
        stays a connected chain of elements.
        """
        scene = self.scene()
        for m in members:
            scene.subdivide_member(m.id, n_divisions, nodes_only=False)

    def _on_divide_custom(self, members: list) -> None:
        """Prompt for an element count, then divide each member into that many."""
        n, ok = QInputDialog.getInt(
            self, "Divide Member",
            "Number of elements:", value=4, min=2, max=100,
        )
        if ok:
            self._divide_quick(members, n)

    def _on_subdivide(self, members: list) -> None:
        from ui_qt.dialogs import SubdivideDialog
        dlg = SubdivideDialog(self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        scene = self.scene()
        for m in members:
            scene.subdivide_member(m.id, dlg.n_divisions, dlg.nodes_only)

    def _on_mirror(self, is_3d: bool) -> None:
        from ui_qt.dialogs import MirrorDialog
        dlg = MirrorDialog(self, is_3d=is_3d)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        self.scene().mirror_selection(dlg.plane, dlg.offset, dlg.keep_original)
