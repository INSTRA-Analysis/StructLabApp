"""Structural canvas: QGraphicsScene-based interactive model editor.

NodeItem and MemberItem visual classes live in canvas_items.py.
"""

from __future__ import annotations

import math
from enum import Enum, auto

from PyQt6.QtWidgets import (
    QGraphicsScene, QGraphicsView,
    QGraphicsLineItem, QMenu,
)
from PyQt6.QtCore import Qt, QPointF, QLineF, QTimer, pyqtSignal
from PyQt6.QtGui import QPen, QBrush, QColor, QPainter, QTransform

from ui_qt.model_state import (
    ModelState, NodeData, MemberData,
    ElementType, SupportType,
)

from ui_qt.canvas_items import (
    PX_PER_M, GRID_STEP, SNAP_PX,
    _GHOST_PEN, m_to_px, px_to_m,
    NodeItem, MemberItem, _node_pos,
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

    model_changed = pyqtSignal()   # emitted after any structural change
    view_changed  = pyqtSignal()   # emitted when 3D projection angles change (orbit end)
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

        # ── overlay state ─────────────────────────────────────────────────────
        self._overlay_items: dict[str, list] = {}
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

    def set_next_member_type(self, element_type: ElementType) -> None:
        self._next_member_type = element_type

    def set_plane_offset(self, offset: float) -> None:
        """Set the locked coordinate on the active working plane axis."""
        self._plane_offset = offset
        self.update()

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
        sel_nodes = [it.node for it in selected if isinstance(it, NodeItem)]
        if not sel_nodes:
            return

        sel_node_ids = {n.id for n in sel_nodes}
        # Include all members whose both endpoints are in the selection
        # (whether or not the member item itself was explicitly selected)
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
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        pos = event.scenePos()

        if self._mode == CanvasMode.ADD_NODE:
            snapped = self._snap(pos)
            ms = self.model_state
            is_3d = ms.mode_3d or any(n.z != 0.0 for n in ms.nodes)
            if is_3d:
                plane  = self._working_plane
                offset = self._plane_offset
                az = _proj.ISO_AZIMUTH
                el = _proj.ISO_ELEVATION
                ppm = PX_PER_M
                sx, sy = snapped.x(), snapped.y()
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
            else:
                mx = px_to_m(snapped.x())
                my = px_to_m(-snapped.y())
                mz = 0.0
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
        ctrl = mods & Qt.KeyboardModifier.ControlModifier
        shift = mods & Qt.KeyboardModifier.ShiftModifier
        if event.key() == Qt.Key.Key_Delete:
            self.save_snapshot()
            self._delete_selected()
        elif event.key() == Qt.Key.Key_A and ctrl and shift:
            self.clearSelection()
        elif event.key() == Qt.Key.Key_A and ctrl:
            for item in self.items():
                item.setSelected(True)
        elif event.key() == Qt.Key.Key_I and ctrl:
            for item in self.items():
                item.setSelected(not item.isSelected())
        elif event.key() == Qt.Key.Key_Z and ctrl:
            self.undo()
        elif event.key() == Qt.Key.Key_Y and ctrl:
            self.redo()
        else:
            super().keyPressEvent(event)

    # ── scene manipulation ────────────────────────────────────────────────────

    def _add_node_item(self, node: NodeData) -> NodeItem:
        item = NodeItem(node, self)
        self.addItem(item)
        self._node_items[node.id] = item
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

        layer_items: dict[str, list] = {
            'BMD':      draw_bmd(model, sub_results, load_map, diag_scale, member_el_map),
            'SFD':      draw_sfd(model, sub_results, load_map, diag_scale, member_el_map),
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

    def reproject(self) -> None:
        """Reposition all items after the isometric projection angles change."""
        for nitem in self._node_items.values():
            nitem.refresh()
        self.update_depth_order()
        self.invalidate(self.sceneRect())

    def set_view(self, azimuth: float = -45.0, elevation: float = 30.0) -> None:
        """Set the 3D view angle and reproject.  Elevation clamped to 2–88°."""
        _proj.ISO_AZIMUTH = azimuth
        _proj.ISO_ELEVATION = max(2.0, min(88.0, elevation))
        self.reproject()

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

    def set_overlay_visible(self, layer: str, visible: bool) -> None:
        """Toggle visibility of a named overlay layer."""
        self._overlay_visible[layer] = visible
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

    def clear_model(self) -> None:
        """Clear all scene items, overlay items, and model state."""
        self.clear()   # removes ALL items; drawBackground() handles the grid
        self._overlay_items.clear()
        self._node_items.clear()
        self._member_items.clear()
        self.model_state.clear()

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
            new_node = self.model_state.add_node(nd["x"] + offset_x, nd["y"])
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
        self._view_cube = ViewCube()
        self.setMouseTracking(True)  # needed for hover updates

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

        ms = self.scene().model_state
        mode_3d = ms.mode_3d or any(n.z != 0.0 for n in ms.nodes)

        if mode_3d:
            self._draw_iso_grid(painter, rect)
        else:
            self._draw_flat_grid(painter, rect)

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

    def _draw_iso_grid(self, painter: QPainter, rect) -> None:
        """Isometric grid: XY ground plane + active working plane overlay."""
        minor_pen = QPen(QColor(55, 55, 62)); minor_pen.setCosmetic(True)
        major_pen = QPen(QColor(75, 75, 85)); major_pen.setCosmetic(True)
        pl_minor  = QPen(QColor(0, 120, 140, 110)); pl_minor.setCosmetic(True)
        pl_major  = QPen(QColor(0, 155, 175, 180)); pl_major.setCosmetic(True)

        scene  = self.scene()
        plane  = scene._working_plane
        offset = scene._plane_offset
        GR  = range(-2, 25)   # horizontal extent
        ZR  = range(-2, 20)   # vertical (Z) extent for XZ/YZ planes

        # ── XY ground floor (always drawn as orientation reference) ─────────────
        for y_val in GR:
            p1 = isometric(GR.start, y_val, 0)
            p2 = isometric(GR.stop - 1, y_val, 0)
            painter.setPen(major_pen if y_val % 5 == 0 else minor_pen)
            painter.drawLine(QLineF(*p1, *p2))
        for x_val in GR:
            p1 = isometric(x_val, GR.start, 0)
            p2 = isometric(x_val, GR.stop - 1, 0)
            painter.setPen(major_pen if x_val % 5 == 0 else minor_pen)
            painter.drawLine(QLineF(*p1, *p2))

        # ── Active working plane overlay ─────────────────────────────────────────
        if plane == WorkingPlane.XY and offset != 0.0:
            # Elevated XY floor at Z = offset
            for y_val in GR:
                p1 = isometric(GR.start, y_val, offset)
                p2 = isometric(GR.stop - 1, y_val, offset)
                painter.setPen(pl_major if y_val % 5 == 0 else pl_minor)
                painter.drawLine(QLineF(*p1, *p2))
            for x_val in GR:
                p1 = isometric(x_val, GR.start, offset)
                p2 = isometric(x_val, GR.stop - 1, offset)
                painter.setPen(pl_major if x_val % 5 == 0 else pl_minor)
                painter.drawLine(QLineF(*p1, *p2))
        elif plane == WorkingPlane.XZ:
            # Vertical XZ plane at Y = offset
            for z_val in ZR:
                p1 = isometric(GR.start, offset, z_val)
                p2 = isometric(GR.stop - 1, offset, z_val)
                painter.setPen(pl_major if z_val % 5 == 0 else pl_minor)
                painter.drawLine(QLineF(*p1, *p2))
            for x_val in GR:
                p1 = isometric(x_val, offset, ZR.start)
                p2 = isometric(x_val, offset, ZR.stop - 1)
                painter.setPen(pl_major if x_val % 5 == 0 else pl_minor)
                painter.drawLine(QLineF(*p1, *p2))
        elif plane == WorkingPlane.YZ:
            # Vertical YZ plane at X = offset
            for z_val in ZR:
                p1 = isometric(offset, GR.start, z_val)
                p2 = isometric(offset, GR.stop - 1, z_val)
                painter.setPen(pl_major if z_val % 5 == 0 else pl_minor)
                painter.drawLine(QLineF(*p1, *p2))
            for y_val in GR:
                p1 = isometric(offset, y_val, ZR.start)
                p2 = isometric(offset, y_val, ZR.stop - 1)
                painter.setPen(pl_major if y_val % 5 == 0 else pl_minor)
                painter.drawLine(QLineF(*p1, *p2))

        # ── ViewCube (top-right corner) ──────────────────────────────────────────
        scale = self.transform().m11()
        vc_cx, vc_cy = self._view_cube.scene_center(rect, scale)
        self._view_cube.paint(painter, vc_cx, vc_cy, scale)

        # ── Working plane label (just below the ViewCube) ────────────────────────
        lbl_pen = QPen(QColor("#00cccc")); lbl_pen.setCosmetic(True)
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
        lbl_y = rect.top() + (self._view_cube.MARGIN * 2 + self._view_cube.HALF * 2 + 16) / scale
        painter.drawText(QPointF(rect.right() - 215 / scale, lbl_y), plane_text)
        z_font.setBold(False)
        painter.setFont(z_font)

        # Axis labels
        origin_pen = QPen(QColor(100, 100, 112)); origin_pen.setCosmetic(True)
        painter.setPen(origin_pen)
        font = painter.font()
        font.setPointSize(7)
        painter.setFont(font)
        ox, oy = isometric(0, 0, 0)
        xa, ya = isometric(2, 0, 0); painter.drawLine(QLineF(ox, oy, xa, ya))
        painter.drawText(QPointF(xa + 4, ya + 4), "X")
        ya_pos = isometric(0, 2, 0); painter.drawLine(QLineF(ox, oy, ya_pos[0], ya_pos[1]))
        painter.drawText(QPointF(ya_pos[0] - 16, ya_pos[1] + 4), "Y")
        za = oy - 2 * PX_PER_M; painter.drawLine(QLineF(ox, oy, ox, za))
        painter.drawText(QPointF(ox + 4, za - 4), "Z")

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

    def wheelEvent(self, event) -> None:
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)

    # ── middle-mouse pan (ScrollHandDrag only works with left button) ─────────

    def mousePressEvent(self, event) -> None:
        # ── ViewCube click (3D mode only) ─────────────────────────────────────
        if (event.button() == Qt.MouseButton.LeftButton
                and self.scene().model_state.mode_3d):
            scale = self.transform().m11()
            vr    = self.mapToScene(self.viewport().rect()).boundingRect()
            vc_cx, vc_cy = self._view_cube.scene_center(vr, scale)
            sp    = self.mapToScene(event.pos())
            result = self._view_cube.hit_test(
                sp, vc_cx, vc_cy, scale, _proj.ISO_AZIMUTH
            )
            if result is not None:
                az, el = result
                self.scene().set_view(az, el)
                self.scene().view_changed.emit()
                self._view_cube.hovered = None
                self.viewport().update()
                event.accept()
                return

        # ── Middle mouse: orbit (3D) or pan ──────────────────────────────────
        if event.button() == Qt.MouseButton.MiddleButton:
            shift = event.modifiers() & Qt.KeyboardModifier.ShiftModifier
            if self.scene().model_state.mode_3d and not shift:
                self._orbit_last = event.pos()
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
            _proj.ISO_AZIMUTH   = _proj.ISO_AZIMUTH + delta.x() * 0.3
            _proj.ISO_ELEVATION = max(5.0, min(85.0, _proj.ISO_ELEVATION - delta.y() * 0.3))
            self.scene().reproject()
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

        # ── ViewCube hover highlight (3D mode, no drag active) ────────────────
        if self.scene().model_state.mode_3d:
            scale = self.transform().m11()
            vr    = self.mapToScene(self.viewport().rect()).boundingRect()
            vc_cx, vc_cy = self._view_cube.scene_center(vr, scale)
            sp = self.mapToScene(event.pos())
            if self._view_cube.update_hover(sp, vc_cx, vc_cy, scale):
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
        super().mouseReleaseEvent(event)

    # ── right-click context menu ──────────────────────────────────────────────

    def contextMenuEvent(self, event) -> None:
        scene = self.scene()
        sel   = scene.selectedItems()
        nodes   = [it.node   for it in sel if isinstance(it, NodeItem)]
        members = [it.member for it in sel if isinstance(it, MemberItem)]
        is_3d   = scene.model_state.mode_3d

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
                ("Pinned",   SupportType.PINNED),
                ("Roller X", SupportType.ROLLER_X),
                ("Roller Y", SupportType.ROLLER_Y),
                ("None",     SupportType.FREE),
            ]
            if is_3d:
                _SUPPORT_LABELS.insert(4, ("Roller Z", SupportType.ROLLER_Z))
            for label, stype in _SUPPORT_LABELS:
                a = sup_menu.addAction(label)
                a.triggered.connect(
                    lambda _checked=False, st=stype: self._set_support(nodes, st)
                )
            menu.addSeparator()

        # ── Modeling tools (members selected) ────────────────────────────────
        if members:
            act_sub = menu.addAction("Subdivide…")
            act_sub.triggered.connect(
                lambda _checked=False, ms=members: self._on_subdivide(ms)
            )
            menu.addSeparator()

        # ── Mirror (any selection) ────────────────────────────────────────────
        if nodes or members:
            act_mir = menu.addAction("Mirror…")
            act_mir.triggered.connect(
                lambda _checked=False: self._on_mirror(is_3d)
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
