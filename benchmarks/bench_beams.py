"""Phase 7 — Beam benchmarks: StructLab vs OpenSeesPy.

Four cases, all linear-elastic static:
  1. Simply supported beam — midspan point load P
  2. Propped cantilever    — midspan point load P
  3. 2-span continuous     — UDL w on both spans
  4. 3-span continuous     — UDL w (continuous_beam_ms geometry, IPE 500)

Run:
    python benchmarks/bench_beams.py

Requires:  pip install openseespy
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np

from core.model import Model
from core.node import Node
from core.support import Support
from core.support import SupportType as ST

# Convenience aliases matching StructLab core names
_PIN    = ST.PINNED
_ROLLER = ST.ROLLER_X
_FIXED  = ST.FIXED
_FREE   = ST.FREE
from core.material import Material
from core.section import Section
from core.load import NodalLoad, ElementLoad, LoadType
from elements.frame_element import FrameElement
from solver.assembler import Assembler
from solver.linear_solver import LinearSolver
from solver.postprocessor import Postprocessor

from benchmarks.utils import print_header, print_case, compare_table


# ══════════════════════════════════════════════════════════════════════════════
# StructLab helpers
# ══════════════════════════════════════════════════════════════════════════════

def _sl_run(model: Model):
    """Full StructLab solve pipeline. Returns (SolverResult, list[ElementResult])."""
    asm = Assembler(model)
    K = asm.global_stiffness_matrix(model.elements)
    F = asm.global_force_vector(model.elements)
    result = LinearSolver(model).solve(K, F)
    post = Postprocessor(model.elements, model.element_loads, result.displacements)
    return result, post.compute()


def _sl_reaction(result, node_id: int, dof: int) -> float:
    """Return one reaction component (dof 0=Fx, 1=Fy, 2=Mz)."""
    return result.reactions[node_id * 3 + dof]


def _sl_disp(result, node_id: int, dof: int) -> float:
    """Return one displacement (dof 0=dx, 1=dy, 2=θ)."""
    return result.displacements[node_id * 3 + dof]


def _sl_moment(el_results, el_id: int, end: str) -> float:
    """Return moment at element end ('i' or 'j')."""
    er = next(e for e in el_results if e.element_id == el_id)
    return er.M_i if end == "i" else er.M_j


def _sl_make_model(
    xs: list[float],
    support_types: list[ST],
    E: float,
    A: float,
    I: float,
    point_loads: list[tuple[int, float, float, float]] | None = None,
    udl_elements: list[tuple[int, float]] | None = None,
) -> Model:
    """Build a StructLab horizontal beam model from node x-coords and supports.

    point_loads : [(node_id, Fx, Fy, Mz), ...]
    udl_elements: [(el_id, w), ...]  w positive = downward
    """
    model = Model()
    mat = Material(name="m", elastic_modulus=E, poisson_ratio=0.3)
    sec = Section(name="s", area=A, moment_of_inertia=I)

    for i, (x, sup) in enumerate(zip(xs, support_types)):
        n = Node(id=i, x=x, y=0.0)
        model.nodes.append(n)
        if sup != _FREE:
            model.supports.append(Support(node_id=i, support_type=sup))

    for k in range(len(xs) - 1):
        el = FrameElement(
            id=k,
            node_i=model.nodes[k],
            node_j=model.nodes[k + 1],
            material=mat,
            section=sec,
        )
        model.elements.append(el)

    if point_loads:
        for nid, fx, fy, mz in point_loads:
            model.nodal_loads.append(NodalLoad(node_id=nid, fx=fx, fy=fy, moment=mz))

    if udl_elements:
        for eid, w in udl_elements:
            model.element_loads.append(
                ElementLoad(element_id=eid, load_type=LoadType.UDL, magnitude=w)
            )

    return model


# ══════════════════════════════════════════════════════════════════════════════
# OpenSeesPy helpers
# ══════════════════════════════════════════════════════════════════════════════

def _ops_build(
    xs: list[float],
    support_types: list[ST],
    E: float,
    A: float,
    I: float,
    point_loads: list[tuple[int, float, float, float]] | None = None,
    udl_map: dict[int, float] | None = None,
):
    """Set up and solve an OpenSeesPy beam. Returns the ops module after solve.

    support_types use StructLab ST enum — translated to ops.fix() here.
    node tags and element tags are 1-indexed (OpenSeesPy convention).
    """
    import openseespy.opensees as ops

    _FIX = {
        ST.FIXED:    (1, 1, 1),
        ST.PINNED:   (1, 1, 0),
        ST.ROLLER_X: (0, 1, 0),
        ST.ROLLER_Y: (1, 0, 0),
        ST.FREE:     None,
    }

    ops.wipe()
    ops.model("basic", "-ndm", 2, "-ndf", 3)

    for i, x in enumerate(xs):
        ops.node(i + 1, x, 0.0)

    for i, sup in enumerate(support_types):
        fix = _FIX.get(sup)
        if fix is not None:
            ops.fix(i + 1, *fix)

    ops.geomTransf("Linear", 1)
    for k in range(len(xs) - 1):
        ops.element("elasticBeamColumn", k + 1, k + 1, k + 2, A, E, I, 1)

    ops.timeSeries("Constant", 1)
    ops.pattern("Plain", 1, 1)

    if point_loads:
        for nid, fx, fy, mz in point_loads:
            ops.load(nid + 1, fx, fy, mz)   # nid is 0-indexed → +1

    if udl_map:
        for eid, wy in udl_map.items():
            # eid is 0-indexed element id; OpenSeesPy tag is eid+1
            ops.eleLoad("-ele", eid + 1, "-type", "-beamUniform", wy, 0.0)

    ops.system("BandGeneral")
    ops.numberer("Plain")
    ops.constraints("Plain")
    ops.integrator("LoadControl", 1.0)
    ops.algorithm("Linear")
    ops.analysis("Static")
    ops.analyze(1)
    ops.reactions()

    return ops


def _ops_Ry(ops_mod, node_0idx: int) -> float:
    """Vertical reaction at 0-indexed node (upward positive)."""
    return ops_mod.nodeReaction(node_0idx + 1, 2)


def _ops_Mz(ops_mod, node_0idx: int) -> float:
    """Moment reaction at 0-indexed node (CCW positive)."""
    return ops_mod.nodeReaction(node_0idx + 1, 3)


def _ops_dy(ops_mod, node_0idx: int) -> float:
    """Vertical displacement at 0-indexed node."""
    return ops_mod.nodeDisp(node_0idx + 1, 2)


# ══════════════════════════════════════════════════════════════════════════════
# Case 1 — Simply supported beam, midspan point load
# ══════════════════════════════════════════════════════════════════════════════

def case1_simply_supported_point_load() -> bool:
    """L=4m, P=10kN at midspan, E=200GPa, I=1e-4 m⁴."""
    print_case("Case 1 — Simply supported beam, midspan point load")
    L, P = 4.0, 10_000.0
    E, A, I = 200e9, 0.03, 1e-4

    # Nodes: 0(PIN) — 1(free, load point) — 2(ROLLER)
    xs   = [0.0, L / 2, L]
    sups = [_PIN, _FREE, _ROLLER]

    # ── StructLab ─────────────────────────────────────────────────────────────
    sl_model = _sl_make_model(xs, sups, E, A, I, point_loads=[(1, 0, -P, 0)])
    sl_res, sl_el = _sl_run(sl_model)

    sl_R0y  = _sl_reaction(sl_res, 0, 1)
    sl_R2y  = _sl_reaction(sl_res, 2, 1)
    sl_dmid = _sl_disp(sl_res, 1, 1)

    # ── OpenSeesPy ────────────────────────────────────────────────────────────
    ops = _ops_build(xs, sups, E, A, I, point_loads=[(1, 0.0, -P, 0.0)])

    ops_R0y  = _ops_Ry(ops, 0)
    ops_R2y  = _ops_Ry(ops, 2)
    ops_dmid = _ops_dy(ops, 1)

    # ── Analytical reference ──────────────────────────────────────────────────
    ref_Ry   = P / 2                # = 5 000 N
    ref_dmid = -P * L**3 / (48 * E * I)  # negative (downward)

    print(f"    Analytical:  R_y={ref_Ry:.1f} N,  d_mid={ref_dmid*1e3:.4f} mm")
    print(f"    StructLab:   R_0y={sl_R0y:.1f} N,  d_mid={sl_dmid*1e3:.4f} mm")
    print(f"    OpenSeesPy:  R_0y={ops_R0y:.1f} N,  d_mid={ops_dmid*1e3:.4f} mm")

    ok_sl = compare_table([
        ("R_0y (StructLab vs Analytical)", sl_R0y,  ref_Ry,   "N"),
        ("R_2y (StructLab vs Analytical)", sl_R2y,  ref_Ry,   "N"),
        ("d_mid (StructLab vs Analytical)", sl_dmid, ref_dmid, "m"),
        ("R_0y (StructLab vs OpenSeesPy)",  sl_R0y,  ops_R0y,  "N"),
        ("d_mid (StructLab vs OpenSeesPy)", sl_dmid, ops_dmid, "m"),
    ])
    return ok_sl


# ══════════════════════════════════════════════════════════════════════════════
# Case 2 — Propped cantilever, midspan point load
# ══════════════════════════════════════════════════════════════════════════════

def case2_propped_cantilever_point_load() -> bool:
    """L=4m, P=10kN at midspan, E=200GPa, I=1e-4 m⁴."""
    print_case("Case 2 — Propped cantilever, midspan point load")
    L, P = 4.0, 10_000.0
    E, A, I = 200e9, 0.03, 1e-4

    # Nodes: 0(FIXED) — 1(free, load point) — 2(ROLLER)
    xs   = [0.0, L / 2, L]
    sups = [_FIXED, _FREE, _ROLLER]

    # ── StructLab ─────────────────────────────────────────────────────────────
    sl_model = _sl_make_model(xs, sups, E, A, I, point_loads=[(1, 0, -P, 0)])
    sl_res, sl_el = _sl_run(sl_model)

    sl_R0y  = _sl_reaction(sl_res, 0, 1)
    sl_R2y  = _sl_reaction(sl_res, 2, 1)
    sl_M0   = _sl_reaction(sl_res, 0, 2)

    # ── OpenSeesPy ────────────────────────────────────────────────────────────
    ops = _ops_build(xs, sups, E, A, I, point_loads=[(1, 0.0, -P, 0.0)])

    ops_R0y = _ops_Ry(ops, 0)
    ops_R2y = _ops_Ry(ops, 2)
    ops_M0  = _ops_Mz(ops, 0)

    # ── Analytical reference (textbook: Hibbeler or equivalent) ───────────────
    # Roller = propped end (x=L), fixed at x=0.
    # For point load P at a = L/2:
    #   R_roller = P * a^2 * (3L - a) / (2 * L^3)
    #            = P * (L/2)^2 * (3L - L/2) / (2L^3)
    #            = P * L^2/4 * 5L/2 / (2L^3)
    #            = 5P/16
    a = L / 2
    ref_R2y = P * a**2 * (3 * L - a) / (2 * L**3)  # 5P/16 = 3125 N
    ref_R0y = P - ref_R2y                            # 11P/16 = 6875 N
    ref_M0  = P * a * (L**2 - a**2) / (2 * L**2)    # +3PL/16 (CCW at fixed end)

    print(f"    Analytical:  R_0y={ref_R0y:.1f} N,  R_2y={ref_R2y:.1f} N,  M_0={ref_M0:.1f} N·m")
    print(f"    StructLab:   R_0y={sl_R0y:.1f} N,  R_2y={sl_R2y:.1f} N,  M_0={sl_M0:.1f} N·m")
    print(f"    OpenSeesPy:  R_0y={ops_R0y:.1f} N,  R_2y={ops_R2y:.1f} N,  M_0={ops_M0:.1f} N·m")

    ok_sl = compare_table([
        ("R_0y (StructLab vs Analytical)", sl_R0y, ref_R0y, "N"),
        ("R_2y (StructLab vs Analytical)", sl_R2y, ref_R2y, "N"),
        ("M_0  (StructLab vs Analytical)", sl_M0,  ref_M0,  "N·m"),
        ("R_0y (StructLab vs OpenSeesPy)", sl_R0y, ops_R0y, "N"),
        ("R_2y (StructLab vs OpenSeesPy)", sl_R2y, ops_R2y, "N"),
        ("M_0  (StructLab vs OpenSeesPy)", sl_M0,  ops_M0,  "N·m"),
    ])
    return ok_sl


# ══════════════════════════════════════════════════════════════════════════════
# Case 3 — 2-span continuous beam, UDL
# ══════════════════════════════════════════════════════════════════════════════

def case3_two_span_continuous_udl() -> bool:
    """2 × L=8m spans, w=20 kN/m, PIN — ROLLER — PIN, E=200GPa, I=300e-6 m⁴."""
    print_case("Case 3 — 2-span continuous beam, UDL")
    L, w = 8.0, 20_000.0
    E, A, I = 200e9, 0.03, 300e-6

    # Nodes: 0(PIN) — 1(ROLLER) — 2(PIN)
    xs   = [0.0, L, 2 * L]
    sups = [_PIN, _ROLLER, _PIN]

    # ── StructLab ─────────────────────────────────────────────────────────────
    sl_model = _sl_make_model(xs, sups, E, A, I, udl_elements=[(0, w), (1, w)])
    sl_res, sl_el = _sl_run(sl_model)

    sl_R0y = _sl_reaction(sl_res, 0, 1)
    sl_R1y = _sl_reaction(sl_res, 1, 1)
    sl_R2y = _sl_reaction(sl_res, 2, 1)

    # ── OpenSeesPy ────────────────────────────────────────────────────────────
    ops = _ops_build(xs, sups, E, A, I, udl_map={0: -w, 1: -w})

    ops_R0y = _ops_Ry(ops, 0)
    ops_R1y = _ops_Ry(ops, 1)
    ops_R2y = _ops_Ry(ops, 2)

    # ── Analytical (three-moment equation, symmetric 2-span) ──────────────────
    # R_end = 3wL/8,  R_center = 5wL/4
    ref_Rend    = 3 * w * L / 8   # 60 000 N
    ref_Rcenter = 5 * w * L / 4   # 200 000 N

    print(f"    Analytical:  R_end={ref_Rend:.0f} N,  R_center={ref_Rcenter:.0f} N")
    print(f"    StructLab:   R_0y={sl_R0y:.0f} N,  R_1y={sl_R1y:.0f} N,  R_2y={sl_R2y:.0f} N")
    print(f"    OpenSeesPy:  R_0y={ops_R0y:.0f} N,  R_1y={ops_R1y:.0f} N,  R_2y={ops_R2y:.0f} N")

    ok_sl = compare_table([
        ("R_0y (StructLab vs Analytical)",   sl_R0y, ref_Rend,    "N"),
        ("R_1y (StructLab vs Analytical)",   sl_R1y, ref_Rcenter, "N"),
        ("R_2y (StructLab vs Analytical)",   sl_R2y, ref_Rend,    "N"),
        ("R_0y (StructLab vs OpenSeesPy)",   sl_R0y, ops_R0y,     "N"),
        ("R_1y (StructLab vs OpenSeesPy)",   sl_R1y, ops_R1y,     "N"),
        ("R_2y (StructLab vs OpenSeesPy)",   sl_R2y, ops_R2y,     "N"),
    ])
    return ok_sl


# ══════════════════════════════════════════════════════════════════════════════
# Case 4 — 3-span continuous beam, UDL (continuous_beam_ms geometry)
# ══════════════════════════════════════════════════════════════════════════════

def case4_three_span_continuous_udl() -> bool:
    """3 × L=4m spans, w=35 kN/m.

    Support:  FIXED — ROLLER — ROLLER — PIN
    Profile:  IPE 500 — E=210 GPa, A=0.0116 m², I=4.82e-4 m⁴
    Reference: OpenSeesPy with n=10 sub-elements per span.
    """
    print_case("Case 4 — 3-span continuous beam, UDL (IPE 500, FIXED–ROLLER–ROLLER–PIN)")
    L, w = 4.0, 35_000.0
    E, A, I = 210e9, 0.0116, 4.82e-4

    xs   = [0.0, L, 2 * L, 3 * L]
    sups = [_FIXED, _ROLLER, _ROLLER, _PIN]

    # ── StructLab (single element per span + FEF — exact for UDL) ─────────────
    sl_model = _sl_make_model(xs, sups, E, A, I, udl_elements=[(0, w), (1, w), (2, w)])
    sl_res, sl_el = _sl_run(sl_model)

    sl_R0y = _sl_reaction(sl_res, 0, 1)
    sl_R1y = _sl_reaction(sl_res, 1, 1)
    sl_R2y = _sl_reaction(sl_res, 2, 1)
    sl_R3y = _sl_reaction(sl_res, 3, 1)
    sl_M0  = _sl_reaction(sl_res, 0, 2)

    # ── OpenSeesPy reference (n=10 sub-elements per span for convergence) ─────
    n_sub = 10
    xs_ops   = [span * L + k * L / n_sub for span in range(3) for k in range(n_sub)] + [3 * L]
    n_nodes  = len(xs_ops)
    sups_ops: list[ST] = [_FREE] * n_nodes
    sups_ops[0]           = _FIXED
    sups_ops[n_sub]        = _ROLLER
    sups_ops[2 * n_sub]    = _ROLLER
    sups_ops[3 * n_sub]    = _PIN

    ops = _ops_build(xs_ops, sups_ops, E, A, I,
                     udl_map={k: -w for k in range(3 * n_sub)})

    ops_R0y = _ops_Ry(ops, 0)
    ops_R1y = _ops_Ry(ops, n_sub)
    ops_R2y = _ops_Ry(ops, 2 * n_sub)
    ops_R3y = _ops_Ry(ops, 3 * n_sub)
    ops_M0  = _ops_Mz(ops, 0)

    total_load = w * 3 * L

    print(f"    Total applied load = {total_load:.0f} N")
    print(f"    StructLab:   R_0y={sl_R0y:.0f}  R_1y={sl_R1y:.0f}  R_2y={sl_R2y:.0f}  R_3y={sl_R3y:.0f}  M_0={sl_M0:.0f}")
    print(f"    OpenSeesPy:  R_0y={ops_R0y:.0f}  R_1y={ops_R1y:.0f}  R_2y={ops_R2y:.0f}  R_3y={ops_R3y:.0f}  M_0={ops_M0:.0f}")
    print(f"    SL SumFy = {sl_R0y + sl_R1y + sl_R2y + sl_R3y:.1f} N  (check: {total_load:.0f})")

    ok_sl = compare_table([
        ("R_0y (StructLab vs OpenSeesPy)", sl_R0y, ops_R0y, "N"),
        ("R_1y (StructLab vs OpenSeesPy)", sl_R1y, ops_R1y, "N"),
        ("R_2y (StructLab vs OpenSeesPy)", sl_R2y, ops_R2y, "N"),
        ("R_3y (StructLab vs OpenSeesPy)", sl_R3y, ops_R3y, "N"),
        ("M_0  (StructLab vs OpenSeesPy)", sl_M0,  ops_M0,  "N·m"),
    ])
    return ok_sl


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print_header("StructLab Phase 7 — Beam Benchmarks (StructLab vs OpenSeesPy)")

    results = [
        case1_simply_supported_point_load(),
        case2_propped_cantilever_point_load(),
        case3_two_span_continuous_udl(),
        case4_three_span_continuous_udl(),
    ]

    n_pass = sum(results)
    n_total = len(results)
    print()
    print("=" * 72)
    if all(results):
        print(f"  \033[1m\033[32mAll {n_total} cases PASSED\033[0m")
    else:
        print(f"  \033[1m\033[31m{n_total - n_pass} / {n_total} cases FAILED\033[0m")
    print("=" * 72)
    print()


if __name__ == "__main__":
    main()
