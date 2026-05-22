"""Pure solver functions extracted from MainWindow.

These functions have no Qt dependencies and can be tested independently.
They are called by MainWindow's thin wrapper methods.
"""
from __future__ import annotations

from typing import Any

import numpy as np


# ── Pre-solve validation ──────────────────────────────────────────────────────

def validate_model(state) -> tuple[list[str], list[str]]:
    """Return (errors, warnings) for the given ModelState.

    Errors block solving. Warnings are shown but solving continues.
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Connected node IDs
    connected = {m.node_i for m in state.members} | {m.node_j for m in state.members}

    # Floating nodes
    floating = [n for n in state.nodes if n.id not in connected]
    if floating:
        ids = ", ".join(str(n.id) for n in floating)
        errors.append(f"Floating node(s) with no members attached: {ids}")

    # Support checks
    from ui_qt.model_state import SupportType
    supports = [n for n in state.nodes if n.support_type != SupportType.FREE]
    if not supports:
        errors.append("No supports defined — structure is unsupported (will be singular)")
    else:
        has_pin_or_fixed = any(
            n.support_type in (SupportType.PIN, SupportType.FIXED)
            for n in state.nodes
        )
        if not has_pin_or_fixed:
            errors.append(
                "No PIN or FIXED support — only ROLLERs found.\n"
                "Structure cannot resist horizontal forces (likely singular).\n"
                "Change at least one ROLLER to PIN."
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
                    f"(nodes {m.node_i} and {m.node_j} are at the same point)"
                )

    # No loads in the active case
    lc = state.active_case
    has_node_loads = any(not lc.get_node_load(n.id).is_zero() for n in state.nodes)
    has_member_loads = bool(lc.member_loads)
    if not has_node_loads and not has_member_loads:
        warnings.append("No loads applied in the active case — all results will be zero")

    return errors, warnings


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

    return {
        'model':          model,
        'sub_results':    sub_results,
        'displacements':  result.displacements,
        'reactions':      result.reactions,
        'member_el_map':  member_el_map,
        'member_results': member_results,
    }
