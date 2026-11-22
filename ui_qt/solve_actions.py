"""Pure solver functions extracted from MainWindow.

These functions have no Qt dependencies and can be tested independently.
They are called by MainWindow's thin wrapper methods.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


# ── Pre-solve validation ──────────────────────────────────────────────────────

@dataclass(frozen=True)
class Issue:
    """One validation finding, with the nodes / members it is about (for select-and-zoom)."""
    severity: str                       # "error" | "warning"
    text: str
    node_ids: tuple[int, ...] = ()
    member_ids: tuple[int, ...] = ()


def validate_model(state) -> tuple[list[str], list[str]]:
    """Return (errors, warnings) for the given ModelState.

    Errors block solving. Warnings are shown but solving continues.
    """
    issues = validate_model_issues(state)
    return ([i.text for i in issues if i.severity == "error"],
            [i.text for i in issues if i.severity == "warning"])


def validate_model_issues(state) -> list[Issue]:
    """Validate ``state``; each Issue names the nodes / members involved."""
    issues: list[Issue] = []

    class _Sink(list):
        def __init__(self, severity: str) -> None:
            super().__init__()
            self._severity = severity

        def append(self, text: str, nodes=(), members=()) -> None:     # type: ignore[override]
            issues.append(Issue(self._severity, text, tuple(nodes), tuple(members)))

    errors, warnings = _Sink("error"), _Sink("warning")

    # Connected node IDs
    connected = {m.node_i for m in state.members} | {m.node_j for m in state.members}

    # Floating nodes
    floating = [n for n in state.nodes if n.id not in connected]
    if floating:
        ids = ", ".join(str(n.id) for n in floating)
        errors.append(f"Floating node(s) with no members attached: {ids}",
                      nodes=[n.id for n in floating])

    # Support checks
    from ui_qt.model_state import SPRING_FOR_DOF, SupportType
    supports = [n for n in state.nodes if n.support_type != SupportType.FREE]
    if not supports:
        errors.append("No supports defined — structure is unsupported (will be singular)")
    else:
        # Every translation direction must be held somewhere (restraint or spring); judged
        # from the per-axis restraints, so any mix of rollers and custom supports is fine.
        axes = (0, 1) if state.is_2d else (0, 1, 2)
        unheld = ["XYZ"[d] for d in axes
                  if not any(n.restraints[d] or getattr(n, SPRING_FOR_DOF[d]) > 0 for n in supports)]
        if unheld:
            along = " or ".join(unheld)
            errors.append(
                f"No support restrains translation along {along} — the structure can slide "
                "that way (it will be singular).\n"
                f"Restrain {along} at one or more supports, for example change a roller to a pin.",
                nodes=[n.id for n in supports],
            )

    # Zero-length members
    for m in state.members:
        ni = state.get_node(m.node_i)
        nj = state.get_node(m.node_j)
        if ni and nj:
            dx = nj.x - ni.x
            dy = nj.y - ni.y
            dz = nj.z - ni.z
            length = (dx * dx + dy * dy + dz * dz) ** 0.5
            if length < 1e-6:
                errors.append(
                    f"Member {m.id} has zero length "
                    f"(nodes {m.node_i} and {m.node_j} are at the same point)",
                    nodes=[m.node_i, m.node_j], members=[m.id],
                )

    # Coincident nodes / duplicate members (e.g. left by rotate, mirror or paste)
    from ui_qt.model_checks import DEFAULT_TOL, check_duplicates
    dup = check_duplicates(state, DEFAULT_TOL)
    if dup.node_clusters:
        warnings.append(
            f"{dup.extra_nodes} node(s) coincide with another node (closer than "
            f"{DEFAULT_TOL * 1e3:g} mm) without being the same node — the structure is not "
            "connected there.\nUse Check Duplicates (Model tab, or Tools menu) to merge them.",
            nodes=dup.node_ids(),
        )
    if dup.member_groups:
        warnings.append(
            f"{dup.extra_members} duplicate member(s) join the same two points as another "
            "member — their stiffness is counted twice.\nUse Check Duplicates (Model tab, or Tools menu) to remove them.",
            members=[m for g in dup.member_groups for m in g],
        )

    if dup.overlaps:
        warnings.append(
            f"{len(dup.overlaps)} pair(s) of members overlap — collinear and sharing part of their "
            "length (e.g. a member drawn over a divided one), so that stretch is stiffened twice.\n"
            "Use Check Duplicates (Model tab, or Tools menu) to find them.",
            members=sorted({m for pair in dup.overlaps for m in pair}),
        )

    # No loads in the active case
    lc = state.active_case
    has_node_loads = any(not lc.get_node_load(n.id).is_zero() for n in state.nodes)
    has_member_loads = bool(lc.member_loads)
    # Self-weight is a load too: it needs the case flag AND at least one member with density.
    has_self_weight = lc.include_self_weight and any(m.density > 0.0 for m in state.members)
    if not has_node_loads and not has_member_loads and not has_self_weight:
        warnings.append("No loads applied in the active case — all results will be zero")

    # Out-of-plane loads on a 2D model (e.g. left over from a 3D model switched to 2D):
    # a 2D analysis has no out-of-plane freedoms, so nodal Fz/Mx/My and 'qz' member loads
    # cannot act.  A 3D model is always solved in 3D, even when it lies at z = 0.
    if state.nodes and state.is_2d:
        oop_nodes: list[int] = []
        for n in state.nodes:
            nl = lc.get_node_load(n.id)
            if nl.fz != 0.0 or nl.moment_x != 0.0 or nl.moment_y != 0.0:
                oop_nodes.append(n.id)
        oop_members = [
            mid for mid, ml in lc.member_loads.items()
            if any(v != 0.0 for v in ml.net("qz"))
        ]
        if oop_nodes or oop_members:
            detail: list[str] = []
            if oop_nodes:
                detail.append("nodal Fz/Mx/My at node(s) "
                              + ", ".join(str(i) for i in oop_nodes))
            if oop_members:
                detail.append("out-of-plane 'qz' load on member(s) "
                              + ", ".join(str(i) for i in oop_members))
            warnings.append(
                "Out-of-plane load on a 2D model: " + "; ".join(detail) + ".\n"
                "A 2D analysis has no out-of-plane freedoms, so these actions are IGNORED.\n"
                "To include them, switch the model to 3D.",
                nodes=oop_nodes, members=oop_members,
            )

    if not state.is_2d and state.analysis_type == "plane_xz" and state.nodes:
        _check_plane_frame(state, lc, errors, warnings)

    return issues


# A node counts as in the frame's XZ plane within this distance (m) of the median y.
_PLANE_TOLERANCE_M = 1e-6


def _check_plane_frame(state, lc, errors, warnings) -> None:
    """Plane frame (XZ): one plane, sections in the plane, loads in the plane."""
    import math
    ys = sorted(n.y for n in state.nodes)
    plane_y = ys[len(ys) // 2]
    off = [n.id for n in state.nodes if abs(n.y - plane_y) > _PLANE_TOLERANCE_M]
    if off:
        errors.append(
            f"Plane frame (XZ): node(s) {', '.join(map(str, off[:12]))}"
            f"{' …' if len(off) > 12 else ''} lie outside the frame's plane y = {plane_y:g} m.\n"
            "A plane frame must lie in one XZ plane. Move them, or switch the analysis "
            "type to Space frame.",
            nodes=off,
        )
    rolled = [m.id for m in state.members if abs(math.sin(m.beta_angle)) > 1e-9]
    if rolled:
        warnings.append(
            f"Plane frame (XZ): member(s) {', '.join(map(str, rolled[:12]))} have a section "
            "rotation β other than 0° or 180°, so their in-plane bending uses a mix of the "
            "strong and weak axes. Set β to 0° unless that is intended.",
            members=rolled,
        )
    oop_nodes = [n.id for n in state.nodes
                 if (lambda nl: nl.fy != 0.0 or nl.moment_x != 0.0 or nl.moment != 0.0)(
                     lc.get_node_load(n.id))]
    oop_members = [mid for mid, ml in lc.member_loads.items()
                   if any(v != 0.0 for v in ml.net("qy"))]
    if oop_nodes or oop_members:
        detail = []
        if oop_nodes:
            detail.append("nodal Fy/Mx/Mz at node(s) " + ", ".join(map(str, oop_nodes)))
        if oop_members:
            detail.append("'qy' load on member(s) " + ", ".join(map(str, oop_members)))
        warnings.append(
            "Plane frame (XZ): out-of-plane load — " + "; ".join(detail) + ".\n"
            "The plane frame holds uy, θx and θz at every node, so these actions are taken "
            "by those locks and do NOT reach the structure. Use Space frame to include them.",
            nodes=oop_nodes, members=oop_members,
        )


def lock_force_note(cache) -> str | None:
    """After a plane-frame solve: a note if the out-of-plane locks carried real force
    (anything out of plane that the plane frame did not let act), else None."""
    lock = cache.get("lock_forces")
    if lock is None or not np.any(lock):
        return None
    worst = float(np.abs(lock).max())
    scale = max(float(np.abs(cache["reactions"]).max()), 1.0)
    if worst <= 1e-6 * scale:
        return None
    return (f"The plane-frame locks carried up to {worst / 1e3:.3g} kN (or kN·m) out of plane: "
            "those actions are not in the results. Use Space frame to include them.")


# ── Peak moment along a member ────────────────────────────────────────────────

_STATIONS_PER_SUB = 9          # fixed stations per sub-element (ends + midpoint included)


def member_moment_peaks(el_ids, res_by_id, el_by_id, load_map
                        ) -> tuple[float, float, np.ndarray]:
    """(peak resultant moment, governing signed moment, moments at fixed stations) of one member.

    The moment is evaluated exactly (``bending_profile``) in both bending planes on every
    sub-element, at fixed stations plus both sides of each point load: the peak is found
    wherever it is, not only at the member ends (a simply supported beam's ends carry none).
    The fixed-station array is the same for every load case, so cases can be superposed.
    """
    from solver.postprocessor import bending_profile, sample_points
    stations: list[np.ndarray] = []
    peak, signed = 0.0, 0.0
    for el_id in el_ids:
        res, el = res_by_id[el_id], el_by_id[el_id]
        loads = load_map.get(el_id, [])
        planes = ("y", "z") if res.is_3d else ("z",)
        fixed = np.linspace(0.0, el.length, _STATIONS_PER_SUB)
        every = sample_points(el.length, loads, _STATIONS_PER_SUB)
        m_fixed = np.column_stack([bending_profile(res.end_forces, loads, el.length, fixed, p)[1]
                                   for p in planes])
        m_every = np.column_stack([bending_profile(res.end_forces, loads, el.length, every, p)[1]
                                   for p in planes])
        stations.append(m_fixed)
        size = np.hypot.reduce(m_every, axis=1) if m_every.shape[1] > 1 else np.abs(m_every[:, 0])
        k = int(np.argmax(size))
        if size[k] > peak:
            row = m_every[k]
            peak, signed = float(size[k]), float(row[np.argmax(np.abs(row))])
    return peak, signed, np.vstack(stations)


def member_peak_moment(result) -> float:
    """Largest moment resultant along one member result (N·m), see design_checks.member_forces."""
    from ui_qt.design_checks import member_forces
    return member_forces(result)[1]


def largest_member_moment(member_results) -> tuple[float, int | None]:
    """(largest moment along any member in N·m, that member's id) — for the summaries."""
    best = max(member_results, key=member_peak_moment, default=None)
    return (member_peak_moment(best), best.element_id) if best is not None else (0.0, None)


def peak_from_stations(stations: np.ndarray) -> float:
    """Largest moment resultant over a (k, planes) station array (e.g. a factored sum)."""
    if stations.shape[1] > 1:
        return float(np.hypot(stations[:, 0], stations[:, 1]).max())
    return float(np.abs(stations[:, 0]).max())


# ── Solve engine pipeline ─────────────────────────────────────────────────────

def solve_engine(model, member_el_map, state) -> dict[str, Any]:
    """Run assemble → solve → postprocess → aggregate pipeline.

    Takes an already-built core Model and member-element map.
    Returns a cache dict with keys: model, sub_results, displacements,
    reactions, member_el_map, member_results.
    """
    from solver.assembler import Assembler
    from solver.linear_solver import LinearSolver
    from solver.postprocessor import Postprocessor, ElementResult

    asm = Assembler(model)
    K = asm.global_stiffness_matrix(model.elements)
    F = asm.global_force_vector(model.elements)
    result = LinearSolver(model).solve(K, F)
    sub_results = Postprocessor(
        model.elements, model.element_loads, result.displacements
    ).compute()

    res_by_id = {r.element_id: r for r in sub_results}
    el_by_id = {el.id: el for el in model.elements}
    load_map: dict[int, list] = {}
    for eload in model.element_loads:
        load_map.setdefault(eload.element_id, []).append(eload)
    member_results = []
    for i, md in enumerate(state.members):
        el_ids = member_el_map[i]
        first = res_by_id[el_ids[0]]
        last = res_by_id[el_ids[-1]]
        if model.is_3d:
            # 3D: 12-component end forces
            member_results.append(ElementResult(
                element_id=md.id,
                end_forces=np.array([
                    first.N_i, first.V_y_i, first.V_z_i,
                    first.T_i, first.M_y_i, first.M_z_i,
                    last.N_j,  last.V_y_j,  last.V_z_j,
                    last.T_j,  last.M_y_j,  last.M_z_j,
                ])
            ))
        else:
            # 2D: 6-component end forces
            member_results.append(ElementResult(
                element_id=md.id,
                end_forces=np.array([
                    first.N_i, first.V_i, first.M_i,
                    last.N_j,  last.V_j,  last.M_j,
                ])
            ))
        peaks = member_moment_peaks(el_ids, res_by_id, el_by_id, load_map)
        member_results[-1].peak_moment, member_results[-1].peak_moment_signed, \
            member_results[-1].moment_stations = peaks

    return {
        'model':          model,
        'sub_results':    sub_results,
        'displacements':  result.displacements,
        'reactions':      result.reactions,
        'lock_forces':    result.lock_forces,
        'member_el_map':  member_el_map,
        'member_results': member_results,
    }
