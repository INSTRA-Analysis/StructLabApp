"""Canvas overlay drawing functions for StructLab.

Returns lists of QGraphicsItem objects (not added to scene here) that
represent BMD, SFD, AFD, deformed shape, and value labels, drawn directly
on top of the structural canvas rather than in a separate Matplotlib dock.

Coordinate convention
---------------------
scene_x =  model_x * PX_PER_M
scene_y = -model_y * PX_PER_M   (Qt y-down; structural y-up)

Perpendicular direction
-----------------------
For a member with unit direction (cos_s, sin_s) in scene space, the
perpendicular "below" the member (i.e. toward positive structural y when
the member is horizontal) is (-sin_s, cos_s).  Positive M (sagging)
should plot in this +perp direction, which visually appears below a
horizontal beam.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np

from PyQt6.QtWidgets import QGraphicsItem, QGraphicsPathItem, QGraphicsSimpleTextItem
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QPen, QBrush, QColor, QPainterPath, QFont

if TYPE_CHECKING:
    from core.model import Model
    from solver.postprocessor import ElementResult

# Must match canvas.py
PX_PER_M: float = 80.0

# Z-values
_Z_ORIG     = 2.5   # original grey lines in deformed view
_Z_OVERLAY  = 3.0   # filled diagram polygons / deformed curves
_Z_LABEL    = 4.0   # text labels


# ─────────────────────────────────────────────────────────────────────────────
# Utility helpers
# ─────────────────────────────────────────────────────────────────────────────

def _model_to_scene(x: float, y: float) -> tuple[float, float]:
    return x * PX_PER_M, -y * PX_PER_M


def _node_to_scene(node, model: "Model") -> tuple[float, float]:
    """Return (scene_x, scene_y) using isometric projection for 3D models."""
    if model.is_3d:
        from ui_qt.projection import isometric
        return isometric(node.x, node.y, node.z)
    return _model_to_scene(node.x, node.y)


def _node_scene(model: "Model", node_id: int) -> tuple[float, float]:
    for n in model.nodes:
        if n.id == node_id:
            return _node_to_scene(n, model)
    raise KeyError(f"Node {node_id} not found in model")


def _find_element(model: "Model", element_id: int):
    for el in model.elements:
        if el.id == element_id:
            return el
    return None


def _make_T6(angle: float) -> np.ndarray:
    """Standard 6×6 rotation matrix for a 2-D frame element."""
    c = math.cos(angle)
    s = math.sin(angle)
    T = np.zeros((6, 6))
    for b in (0, 3):
        T[b,     b]     =  c;  T[b,     b + 1] =  s
        T[b + 1, b]     = -s;  T[b + 1, b + 1] =  c
        T[b + 2, b + 2] = 1.0
    return T


# ─────────────────────────────────────────────────────────────────────────────
# Public: build_load_map
# ─────────────────────────────────────────────────────────────────────────────

def build_load_map(model: "Model") -> dict[int, list]:
    """Return {element_id: [ElementLoad, ...]} for all element loads in model."""
    from core.load import LoadType  # local import keeps module importable early
    lmap: dict[int, list] = {}
    for eload in model.element_loads:
        lmap.setdefault(eload.element_id, []).append(eload)
    return lmap


# ─────────────────────────────────────────────────────────────────────────────
# Public: compute_auto_scales
# ─────────────────────────────────────────────────────────────────────────────

def compute_auto_scales(
    model: "Model",
    sub_results: "list[ElementResult]",
    displacements: np.ndarray,
) -> tuple[float, float]:
    """Compute diagram and deformed-shape auto-scale factors.

    Returns
    -------
    diag_auto_scale_px_per_Nm : float
        Multiply by M value (N·m) to get pixel offset from baseline.
        Chosen so the maximum |M| across all elements occupies 15 % of the
        median element span in pixels.
    def_auto_scale_dimensionless : float
        Multiply by displacement (m) × PX_PER_M to get pixel offset.
        Chosen so the maximum nodal displacement (in metres) × PX_PER_M ×
        def_auto occupies 15 % of the median element span in pixels.
    """
    TARGET = 0.15  # 15 % of median span

    # Collect element spans in pixels
    spans_px: list[float] = []
    for el in model.elements:
        ni = next(n for n in model.nodes if n.id == el.node_i.id)
        nj = next(n for n in model.nodes if n.id == el.node_j.id)
        ix_s, iy_s = _node_to_scene(ni, model)
        jx_s, jy_s = _node_to_scene(nj, model)
        L_px = math.hypot(jx_s - ix_s, jy_s - iy_s)
        if L_px > 0:
            spans_px.append(L_px)

    median_span_px = float(np.median(spans_px)) if spans_px else PX_PER_M

    # Diagram scale: based on maximum |M| across all sub-results
    max_M = 0.0
    for res in sub_results:
        el = _find_element(model, res.element_id)
        if el is None:
            continue
        ni = next(n for n in model.nodes if n.id == el.node_i.id)
        nj = next(n for n in model.nodes if n.id == el.node_j.id)
        L  = math.hypot(nj.x - ni.x, nj.y - ni.y)
        # Sample M(x) at 20 points to find true maximum (UDL produces mid-span peak)
        xs = np.linspace(0.0, L, 20)
        M_vals = res.M_i + res._bmd_V_i * xs
        for eload in model.element_loads:
            if eload.element_id == res.element_id:
                from core.load import LoadType
                if eload.load_type == LoadType.UDL:
                    M_vals = M_vals - eload.magnitude * xs ** 2 / 2
        max_M = max(max_M, float(np.max(np.abs(M_vals))))

    if max_M > 0.0:
        diag_auto = (TARGET * median_span_px) / max_M
    else:
        diag_auto = 1e-6   # fallback — effectively zero diagram

    # Deformed scale: normalize to 0.3% of structure bounding box.
    # Using bounding box (not median sub-element span) keeps the visual
    # deformation consistent regardless of n_sub (bars use n_sub=1,
    # frame elements use n_sub=10, which would otherwise produce a 10×
    # difference in def_auto for the same physical structure size).
    dpn = model.dofs_per_node
    n_dofs = len(displacements)
    max_disp_m = 0.0
    for node in model.nodes:
        i0 = node.id * dpn
        if i0 + 1 < n_dofs:
            dx = float(displacements[i0])
            dy = float(displacements[i0 + 1])
            dz = float(displacements[i0 + 2]) if (dpn >= 6 and i0 + 2 < n_dofs) else 0.0
            d_mag = math.sqrt(dx*dx + dy*dy + dz*dz)
            max_disp_m = max(max_disp_m, d_mag)

    if max_disp_m > 0.0:
        node_xs = [n.x for n in model.nodes]
        node_ys = [n.y for n in model.nodes]
        node_zs = [getattr(n, 'z', 0.0) for n in model.nodes]
        bbox_m = max(
            max(node_xs) - min(node_xs),
            max(node_ys) - min(node_ys),
            max(node_zs) - min(node_zs),
            1.0,
        )
        def_auto = 0.015 * bbox_m / max_disp_m
    else:
        def_auto = 1.0   # fallback

    return diag_auto, def_auto


# ─────────────────────────────────────────────────────────────────────────────
# Internal: member-level M and V profile helpers
# ─────────────────────────────────────────────────────────────────────────────

def _member_scene_geometry(
    model: "Model",
    el_ids: list[int],
    el_by_id: dict,
) -> tuple | None:
    """Return (ix_s, iy_s, jx_s, jy_s, L_px, cos_s, sin_s, perp_x, perp_y, L_total)
    for the UI member defined by ordered sub-element IDs, or None if degenerate."""
    first_el = el_by_id.get(el_ids[0])
    last_el  = el_by_id.get(el_ids[-1])
    if first_el is None or last_el is None:
        return None

    ni = first_el.node_i
    nj = last_el.node_j
    ix_s, iy_s = _node_to_scene(ni, model)
    jx_s, jy_s = _node_to_scene(nj, model)
    dx_s = jx_s - ix_s
    dy_s = jy_s - iy_s
    L_px = math.hypot(dx_s, dy_s)
    if L_px < 1e-6:
        return None

    cos_s  = dx_s / L_px
    sin_s  = dy_s / L_px
    perp_x = -sin_s
    perp_y =  cos_s
    # Normalise perp to a consistent half-plane so that reversed ni↔nj node
    # ordering doesn't flip the BMD to the wrong side.  Convention: sagging
    # (positive M) always draws toward the lower-right of the screen, i.e. the
    # perp should satisfy perp_y > 0 (downward), or perp_x > 0 when the member
    # is exactly vertical on screen (perp_y ≈ 0).
    if perp_y < -1e-9 or (abs(perp_y) < 1e-9 and perp_x < 0):
        perp_x = -perp_x
        perp_y = -perp_y
    L_total = sum(el_by_id[e].length for e in el_ids if e in el_by_id)
    return ix_s, iy_s, jx_s, jy_s, L_px, cos_s, sin_s, perp_x, perp_y, L_total


def _stitch_M(
    el_ids: list[int],
    res_by_id: dict,
    el_by_id: dict,
    load_map: dict,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (t_norm, M_vals) stitched across all sub-elements, t in [0,1]."""
    from core.load import LoadType
    all_t: list[float] = []
    all_M: list[float] = []
    x_acc = 0.0
    L_total = sum(el_by_id[e].length for e in el_ids if e in el_by_id)
    if L_total < 1e-10:
        return np.array([]), np.array([])

    for k, el_id in enumerate(el_ids):
        res = res_by_id.get(el_id)
        el  = el_by_id.get(el_id)
        if res is None or el is None:
            continue
        L_sub = el.length
        xs    = np.linspace(0.0, L_sub, 12)
        M_sub = res.M_i + res._bmd_V_i * xs
        for eload in load_map.get(el_id, []):
            if eload.load_type == LoadType.UDL:
                M_sub = M_sub - eload.magnitude * xs ** 2 / 2
        t_vals = (x_acc + xs) / L_total
        # exclude last point on all but final sub-element to avoid duplication
        end = len(t_vals) if k == len(el_ids) - 1 else len(t_vals) - 1
        all_t.extend(t_vals[:end].tolist())
        all_M.extend(M_sub[:end].tolist())
        x_acc += L_sub

    return np.array(all_t), np.array(all_M)


def _stitch_deform(
    el_ids: list[int],
    el_by_id: dict,
    displacements: np.ndarray,
    dpn: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (t_norm, local_transverse_m) using Hermite interpolation.

    Only valid for 2D elements (is_3d=False). Returns empty arrays for 3D members.
    """
    n_dofs = len(displacements)
    all_t: list[float] = []
    all_v: list[float] = []
    x_acc = 0.0
    L_total = sum(el_by_id[e].length for e in el_ids if e in el_by_id)
    if L_total < 1e-10:
        return np.array([]), np.array([])

    _rot = 5 if dpn == 6 else 2

    for k, el_id in enumerate(el_ids):
        el = el_by_id.get(el_id)
        if el is None or getattr(el, 'is_3d', False):
            continue

        L = el.length
        ts = np.linspace(0.0, 1.0, 12)
        N1 = 1.0 - 3*ts**2 + 2*ts**3
        N2 = L * (ts - 2*ts**2 + ts**3)
        N3 = 3*ts**2 - 2*ts**3
        N4 = L * (-ts**2 + ts**3)

        ni_id = el.node_i.id
        nj_id = el.node_j.id

        def _get(nid: int, dof: int) -> float:
            idx = nid * dpn + dof
            return float(displacements[idx]) if idx < n_dofs else 0.0

        d_global = np.array([
            _get(ni_id, 0), _get(ni_id, 1), _get(ni_id, _rot),
            _get(nj_id, 0), _get(nj_id, 1), _get(nj_id, _rot),
        ])
        T6 = _make_T6(el.angle)
        dl = T6 @ d_global
        v_i, th_i = dl[1], dl[2]
        v_j, th_j = dl[4], dl[5]

        if getattr(el, 'pin_i', False) and getattr(el, 'pin_j', False):
            v_vals = (1.0 - ts) * v_i + ts * v_j
        else:
            v_vals = N1*v_i + N2*th_i + N3*v_j + N4*th_j

        t_vals = (x_acc + ts * L) / L_total
        end = len(t_vals) if k == len(el_ids) - 1 else len(t_vals) - 1
        all_t.extend(t_vals[:end].tolist())
        all_v.extend(v_vals[:end].tolist())
        x_acc += L

    return np.array(all_t), np.array(all_v)


def _stitch_V(
    el_ids: list[int],
    res_by_id: dict,
    el_by_id: dict,
    load_map: dict,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (t_norm, V_vals) stitched across all sub-elements, t in [0,1]."""
    from core.load import LoadType
    all_t: list[float] = []
    all_V: list[float] = []
    x_acc = 0.0
    L_total = sum(el_by_id[e].length for e in el_ids if e in el_by_id)
    if L_total < 1e-10:
        return np.array([]), np.array([])

    for k, el_id in enumerate(el_ids):
        res = res_by_id.get(el_id)
        el  = el_by_id.get(el_id)
        if res is None or el is None:
            continue
        L_sub = el.length
        xs    = np.linspace(0.0, L_sub, 12)
        V_sub = np.full(len(xs), res.V_i)
        for eload in load_map.get(el_id, []):
            if eload.load_type == LoadType.UDL:
                V_sub = V_sub - eload.magnitude * xs
        t_vals = (x_acc + xs) / L_total
        end = len(t_vals) if k == len(el_ids) - 1 else len(t_vals) - 1
        all_t.extend(t_vals[:end].tolist())
        all_V.extend(V_sub[:end].tolist())
        x_acc += L_sub

    return np.array(all_t), np.array(all_V)


def _diagram_polygon(
    t_arr: np.ndarray,
    vals: np.ndarray,
    ix_s: float, iy_s: float,
    L_px: float, cos_s: float, sin_s: float,
    perp_x: float, perp_y: float,
    scale: float,
    fill_color: QColor,
    outline_pen: QPen,
    z: float,
) -> list[QGraphicsItem]:
    """Build filled polygon + outline items from a diagram profile."""
    base_sx = ix_s + t_arr * L_px * cos_s
    base_sy = iy_s + t_arr * L_px * sin_s
    offset  = vals * scale
    diag_sx = base_sx + perp_x * offset
    diag_sy = base_sy + perp_y * offset

    poly = QPainterPath()
    poly.moveTo(float(base_sx[0]), float(base_sy[0]))
    for bx, by in zip(base_sx[1:], base_sy[1:]):
        poly.lineTo(float(bx), float(by))
    for dx, dy in zip(reversed(diag_sx), reversed(diag_sy)):
        poly.lineTo(float(dx), float(dy))
    poly.closeSubpath()

    fill_item = QGraphicsPathItem(poly)
    fill_item.setBrush(QBrush(fill_color))
    fill_item.setPen(QPen(Qt.PenStyle.NoPen))
    fill_item.setZValue(z)

    line = QPainterPath()
    line.moveTo(float(diag_sx[0]), float(diag_sy[0]))
    for dx, dy in zip(diag_sx[1:], diag_sy[1:]):
        line.lineTo(float(dx), float(dy))

    outline_item = QGraphicsPathItem(line)
    outline_item.setPen(outline_pen)
    outline_item.setZValue(z)

    return [fill_item, outline_item]


# ─────────────────────────────────────────────────────────────────────────────
# Public: draw_bmd
# ─────────────────────────────────────────────────────────────────────────────

def draw_bmd(
    model: "Model",
    sub_results: "list[ElementResult]",
    load_map: dict[int, list],
    scale_px_per_Nm: float,
    member_el_map: list[list[int]],
) -> list[QGraphicsItem]:
    """Draw one smooth filled BMD polygon per UI member.

    Positive M (sagging) plots in the +perp direction (below a horizontal beam).
    Using member_el_map to stitch sub-element results into one continuous curve
    gives visually correct parabolas regardless of n_sub.
    """
    fill_color = QColor("#cc4444")
    fill_color.setAlpha(55)
    outline_pen = QPen(QColor("#cc4444"), 1)

    res_by_id = {r.element_id: r for r in sub_results}
    el_by_id  = {e.id: e for e in model.elements}
    items: list[QGraphicsItem] = []

    for el_ids in member_el_map:
        if not el_ids:
            continue
        geom = _member_scene_geometry(model, el_ids, el_by_id)
        if geom is None:
            continue
        ix_s, iy_s, _, _, L_px, cos_s, sin_s, perp_x, perp_y, _ = geom

        t_arr, M_arr = _stitch_M(el_ids, res_by_id, el_by_id, load_map)
        if len(t_arr) == 0:
            continue

        items.extend(_diagram_polygon(
            t_arr, M_arr,
            ix_s, iy_s, L_px, cos_s, sin_s, perp_x, perp_y,
            scale_px_per_Nm, fill_color, outline_pen, _Z_OVERLAY,
        ))

    return items


# ─────────────────────────────────────────────────────────────────────────────
# Public: draw_sfd
# ─────────────────────────────────────────────────────────────────────────────

def draw_sfd(
    model: "Model",
    sub_results: "list[ElementResult]",
    load_map: dict[int, list],
    scale_px_per_Nm: float,
    member_el_map: list[list[int]],
) -> list[QGraphicsItem]:
    """Draw one smooth filled SFD polygon per UI member. V(x) = V_i − w·x for UDL."""
    fill_color = QColor("#2255cc")
    fill_color.setAlpha(55)
    outline_pen = QPen(QColor("#2255cc"), 1)

    res_by_id = {r.element_id: r for r in sub_results}
    el_by_id  = {e.id: e for e in model.elements}
    items: list[QGraphicsItem] = []

    for el_ids in member_el_map:
        if not el_ids:
            continue
        geom = _member_scene_geometry(model, el_ids, el_by_id)
        if geom is None:
            continue
        ix_s, iy_s, _, _, L_px, cos_s, sin_s, perp_x, perp_y, _ = geom

        t_arr, V_arr = _stitch_V(el_ids, res_by_id, el_by_id, load_map)
        if len(t_arr) == 0:
            continue

        items.extend(_diagram_polygon(
            t_arr, V_arr,
            ix_s, iy_s, L_px, cos_s, sin_s, perp_x, perp_y,
            scale_px_per_Nm, fill_color, outline_pen, _Z_OVERLAY,
        ))

    return items


# ─────────────────────────────────────────────────────────────────────────────
# Public: draw_afd
# ─────────────────────────────────────────────────────────────────────────────

def draw_afd(
    model: "Model",
    sub_results: "list[ElementResult]",
) -> list[QGraphicsItem]:
    """Draw colored thick member lines for AFD.

    Red  = compression (N_i > 0 in StructLab sign convention).
    Blue = tension     (N_i < 0).
    Skips elements where |N_i| < 1 N.
    """
    items: list[QGraphicsItem] = []

    for res in sub_results:
        N = res.N_i
        if abs(N) < 1.0:
            continue

        el = _find_element(model, res.element_id)
        if el is None:
            continue

        ni = next(n for n in model.nodes if n.id == el.node_i.id)
        nj = next(n for n in model.nodes if n.id == el.node_j.id)

        ix_s, iy_s = _node_to_scene(ni, model)
        jx_s, jy_s = _node_to_scene(nj, model)

        color_str = "#cc2222" if N > 0 else "#2255cc"
        pen = QPen(QColor(color_str), 4)

        line_path = QPainterPath()
        line_path.moveTo(ix_s, iy_s)
        line_path.lineTo(jx_s, jy_s)

        line_item = QGraphicsPathItem(line_path)
        line_item.setPen(pen)
        line_item.setZValue(_Z_OVERLAY)
        items.append(line_item)

    return items


# ─────────────────────────────────────────────────────────────────────────────
# Public: draw_deformed
# ─────────────────────────────────────────────────────────────────────────────

def draw_deformed(
    model: "Model",
    displacements: np.ndarray,
    def_scale: float,
) -> list[QGraphicsItem]:
    """Draw original grey lines and Hermite-cubic deformed curves for all elements.

    Deformed scene coordinates
    --------------------------
    The deformed position at parametric station t along the element:

        def_sx = ni_sx + cos_s * t * L_px
                 + def_scale * (u_x * cos_s - w_x * sin_s) * PX_PER_M
        def_sy = ni_sy + sin_s * t * L_px
                 + def_scale * (u_x * sin_s + w_x * cos_s) * PX_PER_M

    where (u_x, w_x) are the local axial and transverse displacements in
    metres obtained from Hermite interpolation.
    """
    grey_pen    = QPen(QColor(160, 160, 160), 1)
    deform_pen  = QPen(QColor("#cc2222"), 2, Qt.PenStyle.DashLine)
    n_dofs = len(displacements)

    items: list[QGraphicsItem] = []

    for el in model.elements:
        ni = next(n for n in model.nodes if n.id == el.node_i.id)
        nj = next(n for n in model.nodes if n.id == el.node_j.id)

        ix_s, iy_s = _node_to_scene(ni, model)
        jx_s, jy_s = _node_to_scene(nj, model)

        dx_s = jx_s - ix_s
        dy_s = jy_s - iy_s
        L_px = math.hypot(dx_s, dy_s)

        # ── original (thin grey) line ─────────────────────────────────────────
        orig_path = QPainterPath()
        orig_path.moveTo(ix_s, iy_s)
        orig_path.lineTo(jx_s, jy_s)
        orig_item = QGraphicsPathItem(orig_path)
        orig_item.setPen(grey_pen)
        orig_item.setZValue(_Z_ORIG)
        items.append(orig_item)

        if L_px < 1e-6:
            continue

        cos_s = dx_s / L_px
        sin_s = dy_s / L_px

        _dpn = model.dofs_per_node

        def _get_d(node_id: int, dof: int) -> float:
            idx = node_id * _dpn + dof
            return float(displacements[idx]) if idx < n_dofs else 0.0

        L = el.length
        N_pts = 30
        ts = np.linspace(0.0, 1.0, N_pts)

        N1 = 1.0 - 3.0 * ts ** 2 + 2.0 * ts ** 3
        N2 = L * (ts - 2.0 * ts ** 2 + ts ** 3)
        N3 = 3.0 * ts ** 2 - 2.0 * ts ** 3
        N4 = L * (-ts ** 2 + ts ** 3)

        if el.is_3d:
            # ── 3D: use element's full rotation matrix R3 ─────────────────────
            # build_model sets all z=0 nodes to z=1e-12, so every element in a
            # 3D model has is_3d=True and a valid _R3 basis.
            from ui_qt.projection import isometric as _iso
            R3 = el._R3  # 3×3 columns = [x_hat, y_hat, z_hat] in global coords

            d_gi = np.array([_get_d(ni.id, k) for k in range(6)])
            d_gj = np.array([_get_d(nj.id, k) for k in range(6)])

            d_li = R3.T @ d_gi[:3]   # [u_i, v_i, w_i] local translations
            r_li = R3.T @ d_gi[3:]   # [θx_i, θy_i, θz_i] local rotations
            d_lj = R3.T @ d_gj[:3]
            r_lj = R3.T @ d_gj[3:]

            u_i, v_yi, v_zi = d_li
            _,   thy_i, thz_i = r_li
            u_j, v_yj, v_zj = d_lj
            _,   thy_j, thz_j = r_lj

            u_t = (1.0 - ts) * u_i + ts * u_j
            if getattr(el, "pin_i", False) and getattr(el, "pin_j", False):
                vy_t = (1.0 - ts) * v_yi + ts * v_yj
                vz_t = (1.0 - ts) * v_zi + ts * v_zj
            else:
                vy_t = N1 * v_yi + N2 * thz_i + N3 * v_yj + N4 * thz_j
                # 3D local stiffness uses dw/dx = −θ_y convention
                vz_t = N1 * v_zi - N2 * thy_i + N3 * v_zj - N4 * thy_j

            x_hat, y_hat, z_hat = R3[:, 0], R3[:, 1], R3[:, 2]
            x3d = ni.x + ts*(nj.x - ni.x) + def_scale*(u_t*x_hat[0] + vy_t*y_hat[0] + vz_t*z_hat[0])
            y3d = ni.y + ts*(nj.y - ni.y) + def_scale*(u_t*x_hat[1] + vy_t*y_hat[1] + vz_t*z_hat[1])
            z3d = ni.z + ts*(nj.z - ni.z) + def_scale*(u_t*x_hat[2] + vy_t*y_hat[2] + vz_t*z_hat[2])

            def_path = QPainterPath()
            s0x, s0y = _iso(float(x3d[0]), float(y3d[0]), float(z3d[0]))
            def_path.moveTo(s0x, s0y)
            for _k in range(1, N_pts):
                skx, sky = _iso(float(x3d[_k]), float(y3d[_k]), float(z3d[_k]))
                def_path.lineTo(skx, sky)

        else:
            # ── 2D: Hermite interpolation in screen space ─────────────────────
            _rot = 5 if _dpn == 6 else 2
            d_global = np.array([
                _get_d(ni.id, 0), _get_d(ni.id, 1), _get_d(ni.id, _rot),
                _get_d(nj.id, 0), _get_d(nj.id, 1), _get_d(nj.id, _rot),
            ])
            T6 = _make_T6(el.angle)
            dl = T6 @ d_global

            u_i, v_i, th_i = dl[0], dl[1], dl[2]
            u_j, v_j, th_j = dl[3], dl[4], dl[5]

            if getattr(el, "pin_i", False) and getattr(el, "pin_j", False):
                w_x = (1.0 - ts) * v_i + ts * v_j
            else:
                w_x = N1 * v_i + N2 * th_i + N3 * v_j + N4 * th_j

            u_x = (1.0 - ts) * u_i + ts * u_j
            base_sx = ix_s + cos_s * ts * L_px
            base_sy = iy_s + sin_s * ts * L_px
            def_sx = base_sx + def_scale * (u_x * cos_s + w_x * sin_s) * PX_PER_M
            def_sy = base_sy + def_scale * (u_x * sin_s - w_x * cos_s) * PX_PER_M

            def_path = QPainterPath()
            def_path.moveTo(float(def_sx[0]), float(def_sy[0]))
            for sx, sy in zip(def_sx[1:], def_sy[1:]):
                def_path.lineTo(float(sx), float(sy))

        def_item = QGraphicsPathItem(def_path)
        def_item.setPen(deform_pen)
        def_item.setZValue(_Z_OVERLAY)
        items.append(def_item)

    return items


# ─────────────────────────────────────────────────────────────────────────────
# Public: draw_labels
# ─────────────────────────────────────────────────────────────────────────────

def draw_labels(
    model: "Model",
    sub_results: "list[ElementResult]",
    load_map: dict[int, list],
    scale_px_per_Nm: float,
    member_el_map: list[list[int]],
    displacements: np.ndarray | None = None,
    def_scale: float = 0.0,
) -> list[QGraphicsItem]:
    """Draw value labels for all active diagrams.

    Per UI member:
      - BMD: peak |M| offset to diagram edge (kN·m, red)
      - SFD: peak |V| offset to diagram edge (kN, blue)
      - AFD: representative axial N at midpoint (kN)
      - Deformed: peak transverse deflection at diagram tip (mm, red), when
        ``displacements`` and ``def_scale`` are provided.

    Labels are skipped when the corresponding value is negligible.
    """
    label_font = QFont()
    label_font.setPointSize(7)

    res_by_id = {r.element_id: r for r in sub_results}
    el_by_id  = {e.id: e for e in model.elements}
    items: list[QGraphicsItem] = []

    for el_ids in member_el_map:
        if not el_ids:
            continue
        geom = _member_scene_geometry(model, el_ids, el_by_id)
        if geom is None:
            continue
        ix_s, iy_s, _, _, L_px, cos_s, sin_s, perp_x, perp_y, _ = geom

        # ── BMD peak-M label ─────────────────────────────────────────────────
        t_arr, M_arr = _stitch_M(el_ids, res_by_id, el_by_id, load_map)
        if len(M_arr) > 0:
            peak_idx = int(np.argmax(np.abs(M_arr)))
            M_peak = float(M_arr[peak_idx])
            if abs(M_peak) >= 1.0:
                t_peak  = float(t_arr[peak_idx])
                base_sx = ix_s + t_peak * L_px * cos_s
                base_sy = iy_s + t_peak * L_px * sin_s
                offset  = M_peak * scale_px_per_Nm
                lbl = QGraphicsSimpleTextItem(f"{M_peak / 1e3:.2f} kN·m")
                lbl.setFont(label_font)
                lbl.setBrush(QBrush(QColor("#990000")))
                lbl.setPos(base_sx + perp_x * offset, base_sy + perp_y * offset)
                lbl.setZValue(_Z_LABEL)
                items.append(lbl)

        # ── SFD peak-V label ─────────────────────────────────────────────────
        t_arr_v, V_arr = _stitch_V(el_ids, res_by_id, el_by_id, load_map)
        if len(V_arr) > 0:
            peak_idx_v = int(np.argmax(np.abs(V_arr)))
            V_peak = float(V_arr[peak_idx_v])
            if abs(V_peak) >= 1.0:
                t_peak_v = float(t_arr_v[peak_idx_v])
                base_sx_v = ix_s + t_peak_v * L_px * cos_s
                base_sy_v = iy_s + t_peak_v * L_px * sin_s
                offset_v  = V_peak * scale_px_per_Nm
                lbl_v = QGraphicsSimpleTextItem(f"{V_peak / 1e3:.2f} kN")
                lbl_v.setFont(label_font)
                lbl_v.setBrush(QBrush(QColor("#2255cc")))
                lbl_v.setPos(base_sx_v + perp_x * offset_v, base_sy_v + perp_y * offset_v)
                lbl_v.setZValue(_Z_LABEL)
                items.append(lbl_v)

        # ── AFD axial-N label (first sub-element N_i, representative for member) ─
        first_res = res_by_id.get(el_ids[0])
        if first_res is not None:
            N = first_res.N_i
            if abs(N) >= 1.0:
                color_str = "#cc2222" if N > 0 else "#2255cc"
                mid_sx = ix_s + 0.5 * L_px * cos_s
                mid_sy = iy_s + 0.5 * L_px * sin_s
                lbl = QGraphicsSimpleTextItem(f"{N / 1e3:.2f} kN")
                lbl.setFont(label_font)
                lbl.setBrush(QBrush(QColor(color_str)))
                lbl.setPos(mid_sx, mid_sy)
                lbl.setZValue(_Z_LABEL)
                items.append(lbl)

        # ── Deformed peak-δ label ─────────────────────────────────────────────
        if displacements is not None and def_scale > 0.0:
            t_arr_d, v_arr = _stitch_deform(
                el_ids, el_by_id, displacements, model.dofs_per_node
            )
            if len(v_arr) > 0:
                peak_idx_d = int(np.argmax(np.abs(v_arr)))
                v_peak = float(v_arr[peak_idx_d])
                if abs(v_peak) >= 1e-5:   # skip if < 0.01 mm
                    t_peak_d = float(t_arr_d[peak_idx_d])
                    base_sx_d = ix_s + t_peak_d * L_px * cos_s
                    base_sy_d = iy_s + t_peak_d * L_px * sin_s
                    # local transverse v maps to screen as -v in perp direction
                    offset_d = -def_scale * v_peak * PX_PER_M
                    lbl_d = QGraphicsSimpleTextItem(f"{v_peak * 1e3:.2f} mm")
                    lbl_d.setFont(label_font)
                    lbl_d.setBrush(QBrush(QColor("#cc2222")))
                    lbl_d.setPos(
                        base_sx_d + perp_x * offset_d,
                        base_sy_d + perp_y * offset_d,
                    )
                    lbl_d.setZValue(_Z_LABEL)
                    items.append(lbl_d)

    return items


# ─────────────────────────────────────────────────────────────────────────────
# Public: envelope and all-combos overlay functions
# ─────────────────────────────────────────────────────────────────────────────

_COMBO_PALETTE = [
    "#e65100", "#1565c0", "#2e7d32", "#6a1b9a",
    "#00838f", "#c62828", "#f57f17", "#37474f",
]


def compute_auto_scales_envelope(
    model: "Model",
    solve_runs_rich: list[dict],
) -> float:
    """Return diag auto-scale (px per N·m) that fits all combinations on screen.

    Uses the maximum |M| across every combination and every member so all
    curves fit within 15% of the median element span regardless of which
    combo governs.
    """
    TARGET = 0.15

    spans_px: list[float] = []
    for el in model.elements:
        ni = next(n for n in model.nodes if n.id == el.node_i.id)
        nj = next(n for n in model.nodes if n.id == el.node_j.id)
        ix_s, iy_s = _node_to_scene(ni, model)
        jx_s, jy_s = _node_to_scene(nj, model)
        L_px = math.hypot(jx_s - ix_s, jy_s - iy_s)
        if L_px > 0:
            spans_px.append(L_px)

    median_span_px = float(np.median(spans_px)) if spans_px else PX_PER_M

    max_M = 0.0
    for run in solve_runs_rich:
        sub_results  = run['sub_results']
        run_model    = run['model']
        run_el_by_id = {e.id: e for e in run_model.elements}
        load_map     = build_load_map(run_model)
        res_by_id    = {r.element_id: r for r in sub_results}

        for el_ids in run['member_el_map']:
            if not el_ids:
                continue
            t_arr, M_arr = _stitch_M(el_ids, res_by_id, run_el_by_id, load_map)
            if len(M_arr) > 0:
                max_M = max(max_M, float(np.max(np.abs(M_arr))))

    if max_M > 0.0:
        return (TARGET * median_span_px) / max_M
    return 1e-6


def draw_bmd_envelope(
    model: "Model",
    solve_runs_rich: list[dict],
    scale_px_per_Nm: float,
    member_el_map_ref: list[list[int]],
) -> list[QGraphicsItem]:
    """Draw BMD envelope: orange fill for max M, blue fill for min M across all combos."""
    el_by_id = {e.id: e for e in model.elements}
    items: list[QGraphicsItem] = []

    for el_ids in member_el_map_ref:
        if not el_ids:
            continue
        geom = _member_scene_geometry(model, el_ids, el_by_id)
        if geom is None:
            continue
        ix_s, iy_s, _, _, L_px, cos_s, sin_s, perp_x, perp_y, _ = geom

        t_ref: np.ndarray | None = None
        M_max: np.ndarray | None = None
        M_min: np.ndarray | None = None

        for run in solve_runs_rich:
            res_by_id    = {r.element_id: r for r in run['sub_results']}
            run_model    = run['model']
            run_el_by_id = {e.id: e for e in run_model.elements}
            load_map     = build_load_map(run_model)

            t_arr, M_arr = _stitch_M(el_ids, res_by_id, run_el_by_id, load_map)
            if len(t_arr) == 0:
                continue

            if t_ref is None:
                t_ref = t_arr
                M_max = M_arr.copy()
                M_min = M_arr.copy()
            else:
                if len(t_arr) != len(t_ref):
                    M_arr = np.interp(t_ref, t_arr, M_arr)
                M_max = np.maximum(M_max, M_arr)
                M_min = np.minimum(M_min, M_arr)

        if t_ref is None:
            continue

        c_max = QColor("#FF8F00"); c_max.setAlpha(90)
        items.extend(_diagram_polygon(
            t_ref, M_max, ix_s, iy_s, L_px, cos_s, sin_s, perp_x, perp_y,
            scale_px_per_Nm, c_max, QPen(QColor("#E65100"), 1), _Z_OVERLAY,
        ))
        c_min = QColor("#1E88E5"); c_min.setAlpha(90)
        items.extend(_diagram_polygon(
            t_ref, M_min, ix_s, iy_s, L_px, cos_s, sin_s, perp_x, perp_y,
            scale_px_per_Nm, c_min, QPen(QColor("#1565C0"), 1), _Z_OVERLAY,
        ))

    return items


def draw_sfd_envelope(
    model: "Model",
    solve_runs_rich: list[dict],
    scale_px_per_Nm: float,
    member_el_map_ref: list[list[int]],
) -> list[QGraphicsItem]:
    """Draw SFD envelope: green fill for max V, purple fill for min V across all combos."""
    el_by_id = {e.id: e for e in model.elements}
    items: list[QGraphicsItem] = []

    for el_ids in member_el_map_ref:
        if not el_ids:
            continue
        geom = _member_scene_geometry(model, el_ids, el_by_id)
        if geom is None:
            continue
        ix_s, iy_s, _, _, L_px, cos_s, sin_s, perp_x, perp_y, _ = geom

        t_ref: np.ndarray | None = None
        V_max: np.ndarray | None = None
        V_min: np.ndarray | None = None

        for run in solve_runs_rich:
            res_by_id    = {r.element_id: r for r in run['sub_results']}
            run_model    = run['model']
            run_el_by_id = {e.id: e for e in run_model.elements}
            load_map     = build_load_map(run_model)

            t_arr, V_arr = _stitch_V(el_ids, res_by_id, run_el_by_id, load_map)
            if len(t_arr) == 0:
                continue

            if t_ref is None:
                t_ref = t_arr
                V_max = V_arr.copy()
                V_min = V_arr.copy()
            else:
                if len(t_arr) != len(t_ref):
                    V_arr = np.interp(t_ref, t_arr, V_arr)
                V_max = np.maximum(V_max, V_arr)
                V_min = np.minimum(V_min, V_arr)

        if t_ref is None:
            continue

        c_max = QColor("#43A047"); c_max.setAlpha(90)
        items.extend(_diagram_polygon(
            t_ref, V_max, ix_s, iy_s, L_px, cos_s, sin_s, perp_x, perp_y,
            scale_px_per_Nm, c_max, QPen(QColor("#2E7D32"), 1), _Z_OVERLAY,
        ))
        c_min = QColor("#AB47BC"); c_min.setAlpha(90)
        items.extend(_diagram_polygon(
            t_ref, V_min, ix_s, iy_s, L_px, cos_s, sin_s, perp_x, perp_y,
            scale_px_per_Nm, c_min, QPen(QColor("#7B1FA2"), 1), _Z_OVERLAY,
        ))

    return items


def draw_bmd_all_combos(
    model: "Model",
    solve_runs_rich: list[dict],
    scale_px_per_Nm: float,
    member_el_map_ref: list[list[int]],
    start_index: int = 0,
) -> list[QGraphicsItem]:
    """Draw BMD for every combination in a distinct palette colour.

    start_index offsets the palette lookup so a single-combo call still
    gets the colour matching its position in the full combo list.
    """
    el_by_id = {e.id: e for e in model.elements}
    items: list[QGraphicsItem] = []

    for ci, run in enumerate(solve_runs_rich):
        hex_col    = _COMBO_PALETTE[(start_index + ci) % len(_COMBO_PALETTE)]
        fill_color = QColor(hex_col); fill_color.setAlpha(55)
        outline    = QPen(QColor(hex_col), 1)

        res_by_id    = {r.element_id: r for r in run['sub_results']}
        run_model    = run['model']
        run_el_by_id = {e.id: e for e in run_model.elements}
        load_map     = build_load_map(run_model)

        for el_ids in member_el_map_ref:
            if not el_ids:
                continue
            geom = _member_scene_geometry(model, el_ids, el_by_id)
            if geom is None:
                continue
            ix_s, iy_s, _, _, L_px, cos_s, sin_s, perp_x, perp_y, _ = geom

            t_arr, M_arr = _stitch_M(el_ids, res_by_id, run_el_by_id, load_map)
            if len(t_arr) == 0:
                continue

            items.extend(_diagram_polygon(
                t_arr, M_arr, ix_s, iy_s, L_px, cos_s, sin_s, perp_x, perp_y,
                scale_px_per_Nm, fill_color, outline, _Z_OVERLAY,
            ))

    return items


def draw_sfd_all_combos(
    model: "Model",
    solve_runs_rich: list[dict],
    scale_px_per_Nm: float,
    member_el_map_ref: list[list[int]],
    start_index: int = 0,
) -> list[QGraphicsItem]:
    """Draw SFD for every combination in a distinct palette colour.

    start_index offsets the palette lookup — see draw_bmd_all_combos.
    """
    el_by_id = {e.id: e for e in model.elements}
    items: list[QGraphicsItem] = []

    for ci, run in enumerate(solve_runs_rich):
        hex_col    = _COMBO_PALETTE[(start_index + ci) % len(_COMBO_PALETTE)]
        fill_color = QColor(hex_col); fill_color.setAlpha(55)
        outline    = QPen(QColor(hex_col), 1)

        res_by_id    = {r.element_id: r for r in run['sub_results']}
        run_model    = run['model']
        run_el_by_id = {e.id: e for e in run_model.elements}
        load_map     = build_load_map(run_model)

        for el_ids in member_el_map_ref:
            if not el_ids:
                continue
            geom = _member_scene_geometry(model, el_ids, el_by_id)
            if geom is None:
                continue
            ix_s, iy_s, _, _, L_px, cos_s, sin_s, perp_x, perp_y, _ = geom

            t_arr, V_arr = _stitch_V(el_ids, res_by_id, run_el_by_id, load_map)
            if len(t_arr) == 0:
                continue

            items.extend(_diagram_polygon(
                t_arr, V_arr, ix_s, iy_s, L_px, cos_s, sin_s, perp_x, perp_y,
                scale_px_per_Nm, fill_color, outline, _Z_OVERLAY,
            ))

    return items
