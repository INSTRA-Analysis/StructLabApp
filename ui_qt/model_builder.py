"""Model builder: converts UI ModelState into a StructLab core Model.

Each UI member is subdivided into n_sub FrameElements with auto-generated
intermediate nodes.  Physical joints (supports, hinges, connections) are
always at the original UI nodes; intermediate nodes are free with no loads.

Loads are read from the supplied LoadCase (defaults to state.active_case).
No Qt dependency. Called by MainWindow._on_solve().
"""

import math

import numpy as np

from core.model import Model
from core.node import Node
from core.support import Support
from core.support import SupportType as CoreSupportType
from core.material import Material
from core.section import Section
from core.load import NodalLoad, ElementLoad, LoadType, LoadDirection
from elements.frame_element import FrameElement
from elements.bar_element import BarElement

from ui_qt.model_state import (
    ANALYSIS_TYPES, ModelState, NodeData, SupportType, ElementType,
    LoadCase, NodeLoad, MemberLoad, PointLoadData, PartialDistLoad, DistLoad, LoadCombination,
)


_RIGID_MAP = {
    SupportType.FREE:     CoreSupportType.FREE,
    SupportType.FIXED:    CoreSupportType.FIXED,
    SupportType.PIN:      CoreSupportType.PINNED,
    SupportType.ROLLER:   CoreSupportType.ROLLER_X,
    SupportType.ROLLER_Y: CoreSupportType.ROLLER_Y,
    SupportType.ROLLER_Z: CoreSupportType.ROLLER_Z,
    SupportType.SPRING:   CoreSupportType.FREE,
    SupportType.CUSTOM:   CoreSupportType.FREE,     # label only: Support.restrained carries the DOFs
}

_GRAVITY = 9.81  # m/s²


def _add_self_weight_3d(model: Model, el, weight_per_length: float) -> None:
    """Apply one sub-element's self-weight in a 3D (Z-up) model; gravity is -Z.

    BAR: half the weight lumped to each end node (axial-only member; the truss
    carries load through its joints).
    FrameElement: the load is resolved on the element's own local axes
    (``el._R3``, so ``beta_angle`` is honoured). The transverse parts become a
    true UDL along local y / local z (exact parabolic M and V on the span); the
    axial part is lumped half-and-half to the end nodes.
    """
    weight = weight_per_length * el.length
    if isinstance(el, BarElement):
        for node in (el.node_i, el.node_j):
            model.nodal_loads.append(NodalLoad(node_id=node.id, fz=-weight / 2.0))
        return

    gravity = np.array([0.0, 0.0, -weight_per_length])
    _add_line_load_3d(model, el, gravity, gravity)


_LOCAL_AXES = (LoadDirection.LOCAL_X, LoadDirection.LOCAL_Y, LoadDirection.LOCAL_Z)


def _add_line_load_3d(model: Model, el, q_i: np.ndarray, q_j: np.ndarray) -> None:
    """A distributed load given as global vectors (N per m of member) at the element's ends,
    varying linearly, applied EXACTLY: resolved on the element's own axes (``el._R3``) into
    axial (LOCAL_X) and transverse (LOCAL_Y / LOCAL_Z) element loads, each a UDL or UVL.
    ElementLoad magnitudes are positive along the negative local axis."""
    scale = max(float(np.abs(q_i).max()), float(np.abs(q_j).max()))
    if scale == 0.0:
        return
    for k, axis in enumerate(_LOCAL_AXES):
        hat = el._R3[:, k]
        w1, w2 = -float(q_i @ hat), -float(q_j @ hat)
        if abs(w1) <= 1e-12 * scale and abs(w2) <= 1e-12 * scale:
            continue
        if abs(w1 - w2) <= 1e-12 * scale:
            model.element_loads.append(ElementLoad(
                element_id=el.id, load_type=LoadType.UDL, magnitude=w1, direction=axis))
        else:
            model.element_loads.append(ElementLoad(
                element_id=el.id, load_type=LoadType.UVL, magnitude=w1, position=w2,
                direction=axis))


def _add_line_load_2d(model: Model, el, q_i: np.ndarray, q_j: np.ndarray) -> None:
    """2D counterpart of _add_line_load_3d: global (X, Y) load vectors at the element ends,
    resolved on its axes (x̂ = (c, s), ŷ = (−s, c)) into exact LOCAL_X / LOCAL_Y loads."""
    c, s = math.cos(el.angle), math.sin(el.angle)
    scale = max(float(np.abs(q_i).max()), float(np.abs(q_j).max()))
    if scale == 0.0:
        return
    for axis, hat in ((LoadDirection.LOCAL_X, np.array([c, s])),
                      (LoadDirection.LOCAL_Y, np.array([-s, c]))):
        w1, w2 = -float(q_i @ hat), -float(q_j @ hat)
        if abs(w1) <= 1e-12 * scale and abs(w2) <= 1e-12 * scale:
            continue
        if abs(w1 - w2) <= 1e-12 * scale:
            model.element_loads.append(ElementLoad(
                element_id=el.id, load_type=LoadType.UDL, magnitude=w1, direction=axis))
        else:
            model.element_loads.append(ElementLoad(
                element_id=el.id, load_type=LoadType.UVL, magnitude=w1, position=w2,
                direction=axis))


def _global_line_load(ml: MemberLoad, t: float) -> np.ndarray:
    """The member's qx / qy / qz at fraction ``t`` of its length as a global vector (N/m):
    qx along +X, qy along +Y, qz positive DOWNWARD (−Z), like 'w'."""
    (xs, xe), (ys, ye), (zs, ze) = ml.net("qx"), ml.net("qy"), ml.net("qz")
    return np.array([xs + t * (xe - xs), ys + t * (ye - ys), -(zs + t * (ze - zs))])


def build_model(state: ModelState,
                load_case: LoadCase | None = None) -> tuple[Model, list[list[int]]]:
    """Convert ModelState into a core Model with sub-element discretisation.

    Parameters
    ----------
    state : ModelState
        UI model (geometry + section properties).
    load_case : LoadCase | None
        Which load case to apply. Defaults to ``state.active_case``.

    Returns
    -------
    model : Model
        Core model with UI nodes + auto-generated intermediate nodes and all
        sub-elements.
    member_element_map : list[list[int]]
        ``member_element_map[i]`` = ordered list of element IDs for UI member
        *i*, from node_i end to node_j end.
    """
    lc = load_case if load_case is not None else state.active_case
    # 2D models are native to the engine: all nodes have z == 0 → it builds a
    # 3-DOF (XY, Y-vertical) model automatically. No remap needed.
    # The analysis follows the declared mode, never the coordinates: a 3D model may lie
    # entirely at z = 0 (a grillage, a floor) and is still solved with 6 DOF per node.
    has_3d = state.mode_3d
    dimension = 3 if has_3d else 2
    if not has_3d and any(nd.z != 0.0 for nd in state.nodes):
        raise ValueError("A 2D model must lie in the XY plane (z = 0 for every node).")
    model = Model(dimension=dimension)
    if has_3d:                                  # a plane frame holds its out-of-plane DOFs
        model.locked_dofs = ANALYSIS_TYPES[state.analysis_type]

    # ── UI nodes ──────────────────────────────────────────────────────────────
    node_registry: dict[int, Node] = {}
    for nd in state.nodes:
        n = Node(id=nd.id, x=nd.x, y=nd.y, z=nd.z)
        model.nodes.append(n)
        node_registry[nd.id] = n

    # ── supports ──────────────────────────────────────────────────────────────
    # The node's six restraint flags go to the solver as they are (same table in 2D and 3D);
    # springs act wherever a stiffness is set (a rigid preset clears them, see NodeData).
    for nd in state.nodes:
        if not any(nd.restraints) and not nd.has_springs():
            continue
        model.supports.append(Support(
            node_id=nd.id,
            support_type=_RIGID_MAP[nd.support_type],
            spring_stiffness_x=nd.spring_kx,
            spring_stiffness_y=nd.spring_ky,
            spring_stiffness_theta=nd.spring_ktheta,
            spring_stiffness_z=nd.spring_kz,
            spring_stiffness_rx=nd.spring_krx,
            spring_stiffness_ry=nd.spring_kry,
            restrained=tuple(nd.restraints),
        ))

    # ── elements with sub-division ────────────────────────────────────────────
    # Intermediate node IDs start strictly after the highest UI node ID so they
    # never collide with user-placed nodes.
    next_node_id = (max(nd.id for nd in state.nodes) + 1) if state.nodes else 0
    next_el_id   = 0
    member_element_map: list[list[int]] = []

    ui_node_map = {nd.id: nd for nd in state.nodes}

    for md in state.members:
        # BAR elements don't need sub-division (pure axial, no UDL).
        n_sub = 1 if md.element_type == ElementType.BAR else max(1, md.n_sub)
        ni_data = ui_node_map[md.node_i]
        nj_data = ui_node_map[md.node_j]

        # Build ordered node-ID chain: [node_i, interm_1, …, node_j]
        chain: list[int] = [md.node_i]
        for k in range(1, n_sub):
            t = k / n_sub
            x = ni_data.x + t * (nj_data.x - ni_data.x)
            y = ni_data.y + t * (nj_data.y - ni_data.y)
            z = ni_data.z + t * (nj_data.z - ni_data.z)
            interm = Node(id=next_node_id, x=x, y=y, z=z)
            model.nodes.append(interm)
            node_registry[next_node_id] = interm
            chain.append(next_node_id)
            next_node_id += 1
        chain.append(md.node_j)

        material = Material(name=f"mat_{md.id}", elastic_modulus=md.E, poisson_ratio=0.3)
        section  = Section(name=f"sec_{md.id}", area=md.A, moment_of_inertia=md.I,
                           I_y=md.I_y, J=md.J)

        el_ids: list[int] = []
        sub_els: list = []
        ml = lc.get_member_load(md.id)   # MemberLoad for this member

        for k in range(n_sub):
            start = node_registry[chain[k]]
            end   = node_registry[chain[k + 1]]

            if md.element_type == ElementType.BAR:
                el = BarElement(
                    id=next_el_id, node_i=start, node_j=end,
                    material=material, area=md.A, dimension=dimension,
                )
            else:
                pin_i = (md.element_type == ElementType.PIN_LEFT)  and (k == 0)
                pin_j = (md.element_type == ElementType.PIN_RIGHT) and (k == n_sub - 1)
                el = FrameElement(
                    id=next_el_id, node_i=start, node_j=end,
                    material=material, section=section,
                    pin_i=pin_i, pin_j=pin_j,
                    beta_angle=md.beta_angle, dimension=dimension,
                )

            model.elements.append(el)
            el_ids.append(next_el_id)
            sub_els.append(el)

            if lc.include_self_weight and has_3d and md.density > 0.0:
                _add_self_weight_3d(
                    model, el, lc.self_weight_factor * md.density * md.A * _GRAVITY)

            # Distributed load: sum all 'w' dist_loads; UDL when uniform, UVL when varying
            w_i = sum(dl.w_start + k       / n_sub * (dl.w_end - dl.w_start)
                      for dl in ml.dist_loads if dl.direction == "w")
            w_j = sum(dl.w_start + (k + 1) / n_sub * (dl.w_end - dl.w_start)
                      for dl in ml.dist_loads if dl.direction == "w")
            if w_i != 0.0 or w_j != 0.0:
                if abs(w_i - w_j) < 1e-12:
                    model.element_loads.append(ElementLoad(
                        element_id=next_el_id,
                        load_type=LoadType.UDL,
                        magnitude=w_i,
                    ))
                else:
                    model.element_loads.append(ElementLoad(
                        element_id=next_el_id,
                        load_type=LoadType.UVL,
                        magnitude=w_i,   # w at sub-element start
                        position=w_j,    # w at sub-element end (repurposed field)
                    ))

            next_el_id += 1

        # ── point loads: distribute each to the containing sub-element ────────
        dx = nj_data.x - ni_data.x
        dy = nj_data.y - ni_data.y
        dz = nj_data.z - ni_data.z
        member_length = math.sqrt(dx * dx + dy * dy + dz * dz)
        for pl in ml.point_loads:
            t = max(0.0, min(1.0, pl.position))
            sub_idx  = min(int(t * n_sub), n_sub - 1)
            local_t  = t * n_sub - sub_idx
            local_pos = local_t * (member_length / n_sub)
            if pl.load_type == "FORCE":
                model.element_loads.append(ElementLoad(
                    element_id=el_ids[sub_idx],
                    load_type=LoadType.POINT_FORCE,
                    magnitude=pl.magnitude,
                    position=local_pos,
                ))
            elif pl.load_type == "MOMENT":
                model.element_loads.append(ElementLoad(
                    element_id=el_ids[sub_idx],
                    load_type=LoadType.POINT_MOMENT,
                    magnitude=pl.magnitude,
                    position=local_pos,
                ))

        # Partial-span distributed loads (local ⊥ to member, same convention as w).
        # Each PartialDistLoad specifies an intensity ramp over a fraction [a, b] of
        # the member.  Strategy:
        #   • Sub-elements fully within [a, b] → exact UDL / UVL.
        #   • Sub-elements partially overlapping [a, b] → an exact PARTIAL element load on
        #     the covered stretch (it used to be a point force at its centroid).
        for pdl in ml.partial_loads:
            a = max(0.0, min(1.0, pdl.start_pos))
            b = max(0.0, min(1.0, pdl.end_pos))
            if b <= a + 1e-12:
                continue
            w_a, w_b = pdl.w_start, pdl.w_end

            for k in range(n_sub):
                t_k  = k       / n_sub
                t_k1 = (k + 1) / n_sub
                ol_s = max(a, t_k)
                ol_e = min(b, t_k1)
                if ol_s >= ol_e - 1e-14:
                    continue

                # Intensity at overlap boundaries via linear interpolation
                span = b - a
                w_ol_s = w_a + (ol_s - a) / span * (w_b - w_a)
                w_ol_e = w_a + (ol_e - a) / span * (w_b - w_a)

                full = (ol_s <= t_k + 1e-12) and (ol_e >= t_k1 - 1e-12)
                if full:
                    if abs(w_ol_s - w_ol_e) < 1e-12:
                        model.element_loads.append(ElementLoad(
                            element_id=el_ids[k],
                            load_type=LoadType.UDL,
                            magnitude=w_ol_s,
                        ))
                    else:
                        model.element_loads.append(ElementLoad(
                            element_id=el_ids[k],
                            load_type=LoadType.UVL,
                            magnitude=w_ol_s,
                            position=w_ol_e,
                        ))
                else:
                    # Partial overlap → the exact partial load on that stretch of the element
                    if abs(w_ol_s) < 1e-12 and abs(w_ol_e) < 1e-12:
                        continue
                    model.element_loads.append(ElementLoad(
                        element_id=el_ids[k],
                        load_type=LoadType.PARTIAL,
                        magnitude=w_ol_s,
                        position=(ol_s - t_k) * member_length,
                        end_position=(ol_e - t_k) * member_length,
                        magnitude_end=w_ol_e,
                    ))

        # Global distributed loads qx / qy / qz: exact element loads on every sub-element of
        # a beam (resolved onto its local axes; 2D takes qx, qy — qz is out of its plane).
        # Bars: lumped to their ends, which is exact statics between their pins.
        exact_global = md.element_type != ElementType.BAR
        if exact_global and any(v != 0.0 for a in ("qx", "qy", "qz") for v in ml.net(a)):
            for k, sub_el in enumerate(sub_els):
                q_i, q_j = _global_line_load(ml, k / n_sub), _global_line_load(ml, (k + 1) / n_sub)
                if has_3d:
                    _add_line_load_3d(model, sub_el, q_i, q_j)
                else:
                    _add_line_load_2d(model, sub_el, q_i[:2], q_j[:2])
        qxs, qxe = ml.net("qx") if not exact_global else (0.0, 0.0)
        if qxs != 0.0 or qxe != 0.0:
            sub_L = member_length / n_sub
            for k in range(n_sub):
                qx_k  = qxs + k       / n_sub * (qxe - qxs)
                qx_k1 = qxs + (k + 1) / n_sub * (qxe - qxs)
                fx_sub = (qx_k + qx_k1) / 2.0 * sub_L
                for nid in (chain[k], chain[k + 1]):
                    model.nodal_loads.append(NodalLoad(
                        node_id=nid, fx=fx_sub / 2.0,
                    ))

        # Global Y distributed load: lump as nodal Y-forces per sub-element.
        qys, qye = ml.net("qy") if not exact_global else (0.0, 0.0)
        if qys != 0.0 or qye != 0.0:
            sub_L = member_length / n_sub
            for k in range(n_sub):
                qy_k  = qys + k       / n_sub * (qye - qys)
                qy_k1 = qys + (k + 1) / n_sub * (qye - qys)
                fy_sub = (qy_k + qy_k1) / 2.0 * sub_L
                for nid in (chain[k], chain[k + 1]):
                    model.nodal_loads.append(NodalLoad(
                        node_id=nid, fy=fy_sub / 2.0,
                    ))

        # Global Z distributed load: lump as nodal Z-forces per sub-element.
        # Sign convention: positive qz = downward (gravity direction), same as w.
        # Applied as negative fz so that +qz produces -Z (downward) nodal forces.
        qzs, qze = ml.net("qz") if not exact_global else (0.0, 0.0)
        if qzs != 0.0 or qze != 0.0:
            sub_L = member_length / n_sub
            for k in range(n_sub):
                qz_k  = qzs + k       / n_sub * (qze - qzs)
                qz_k1 = qzs + (k + 1) / n_sub * (qze - qzs)
                fz_sub = (qz_k + qz_k1) / 2.0 * sub_L
                for nid in (chain[k], chain[k + 1]):
                    model.nodal_loads.append(NodalLoad(
                        node_id=nid, fz=-fz_sub / 2.0,
                    ))

        member_element_map.append(el_ids)

    # ── nodal loads ───────────────────────────────────────────────────────────
    for nd in state.nodes:
        nl = lc.get_node_load(nd.id)
        if not nl.is_zero():
            model.nodal_loads.append(NodalLoad(
                node_id=nd.id,
                fx=nl.fx,
                fy=nl.fy,
                moment=nl.moment,
                fz=nl.fz,
                moment_x=nl.moment_x,
                moment_y=nl.moment_y,
            ))

    # ── self-weight ───────────────────────────────────────────────────────────
    # Applied only when the load case carries self-weight (typically the G case).
    #
    # BAR elements (pin-pin, axial only): full weight lumped as nodal forces
    # (half at each end, straight downward).  Bars have no transverse stiffness,
    # so a distributed transverse UDL would make K singular.
    #
    # BEAM/FRAME elements: transverse component w·cos(α) applied as a UDL on
    # each sub-element (gives correct parabolic BMD); axial component w·sin(α)
    # lumped as nodal forces so inclined members / columns get correct compression.
    # 3D models are handled per sub-element in the loop above, along -Z.
    if lc.include_self_weight and not has_3d:
        _G = _GRAVITY
        el_by_id = {el.id: el for el in model.elements}
        for mi, md in enumerate(state.members):
            if md.density <= 0.0:
                continue
            ni_d = ui_node_map[md.node_i]
            nj_d = ui_node_map[md.node_j]
            dx = nj_d.x - ni_d.x
            dy = nj_d.y - ni_d.y
            dz = nj_d.z - ni_d.z
            L  = math.sqrt(dx * dx + dy * dy + dz * dz)
            if L < 1e-10:
                continue
            angle = math.atan2(dy, dx)
            sin_a = math.sin(angle)
            cos_a = math.cos(angle)
            w_self = lc.self_weight_factor * md.density * md.A * _G   # N/m

            is_bar = md.element_type == ElementType.BAR

            if is_bar:
                # Lump full self-weight as half downward force at each end node.
                # Bars carry axial only; a transverse UDL would singular the K.
                F_end = -w_self * L / 2.0
                for nid in (md.node_i, md.node_j):
                    model.nodal_loads.append(NodalLoad(
                        node_id=nid,
                        fx=0.0,
                        fy=F_end,
                        moment=0.0,
                    ))
            else:
                # Exact on every sub-element: transverse and axial parts of the weight
                # (as in 3D), so N varies along the member as it really does.
                gravity = np.array([0.0, -w_self])
                for el_id in member_element_map[mi]:
                    _add_line_load_2d(model, el_by_id[el_id], gravity, gravity)

    return model, member_element_map


def _merge_load_case_into(
    target: LoadCase,
    source: LoadCase,
    factor: float,
    member_filter: "set[int] | None" = None,
) -> None:
    """Scale source loads by factor and accumulate them into target in-place.

    member_filter: when given, only member loads for members in this set are
    merged (used by build_model_pattern to zero out Q on unloaded spans).
    Nodal loads are always merged regardless of the filter.
    """
    for nid, nl in source.node_loads.items():
        ex = target.node_loads.get(nid, NodeLoad())
        target.node_loads[nid] = NodeLoad(
            fx       = ex.fx       + factor * nl.fx,
            fy       = ex.fy       + factor * nl.fy,
            moment   = ex.moment   + factor * nl.moment,
            fz       = ex.fz       + factor * nl.fz,
            moment_x = ex.moment_x + factor * nl.moment_x,
            moment_y = ex.moment_y + factor * nl.moment_y,
        )

    if source.include_self_weight:
        target.include_self_weight = True
        target.self_weight_factor += factor * source.self_weight_factor

    for mid, ml in source.member_loads.items():
        if member_filter is not None and mid not in member_filter:
            continue
        ex = target.member_loads.get(mid, MemberLoad())
        scaled_pl = [
            PointLoadData(pl.load_type, pl.position, factor * pl.magnitude)
            for pl in ml.point_loads
        ]
        scaled_pdl = [
            PartialDistLoad(p.start_pos, p.end_pos, factor * p.w_start, factor * p.w_end)
            for p in ml.partial_loads
        ]
        scaled_dl = [
            DistLoad(dl.direction, factor * dl.w_start, factor * dl.w_end)
            for dl in ml.dist_loads
        ]
        target.member_loads[mid] = MemberLoad(
            dist_loads    = ex.dist_loads    + scaled_dl,
            point_loads   = ex.point_loads   + scaled_pl,
            partial_loads = ex.partial_loads + scaled_pdl,
        )


def build_model_combined(state: ModelState,
                         combination: LoadCombination) -> tuple[Model, list[list[int]]]:
    """Build a core Model using the factored superposition of load cases in a combination.

    Each case in ``combination.factors`` is multiplied by its partial factor and
    summed into a single synthetic LoadCase that is then passed to ``build_model``.
    """
    merged = LoadCase(id=-1, name=combination.name, category="combined",
                      self_weight_factor=0.0)
    for case_id, factor in combination.factors.items():
        lc = state.get_load_case(case_id)
        if lc is None or factor == 0.0:
            continue
        _merge_load_case_into(merged, lc, factor)
    return build_model(state, merged)


def build_model_pattern(
    state: ModelState,
    g_cases: "list[LoadCase]",
    g_factor: float,
    q_cases: "list[LoadCase]",
    q_factor: float,
    q_active_member_ids: "set[int]",
) -> "tuple[Model, list[list[int]]]":
    """Build a core Model for one EN 1992-1-1 pattern loading arrangement.

    G loads are applied to all members (g_factor, typically 1.35 for ULS).
    Q loads are applied only to members in q_active_member_ids (q_factor,
    typically 1.50); members outside the set receive zero Q load, simulating
    the unloaded spans in the alternating / adjacent patterns.
    """
    merged = LoadCase(id=-1, name="pattern", category="combined",
                      self_weight_factor=0.0)
    for lc in g_cases:
        _merge_load_case_into(merged, lc, g_factor)
    for lc in q_cases:
        _merge_load_case_into(merged, lc, q_factor, member_filter=q_active_member_ids)
    return build_model(state, merged)
