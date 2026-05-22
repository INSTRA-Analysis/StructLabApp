"""Phase 7 — Frame benchmarks: StructLab vs OpenSeesPy.

Three cases, all linear-elastic static:
  1. Portal frame — lateral point load H at top-left joint (pinned bases)
  2. Portal frame — gravity UDL on beam (pinned bases)
  3. Two-story frame — dual lateral loads at floor levels (pinned bases)

Run:
    python benchmarks/bench_frames.py

Requires: pip install openseespy
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.model import Model
from core.node import Node
from core.support import Support
from core.support import SupportType as ST
from core.material import Material
from core.section import Section
from core.load import NodalLoad, ElementLoad, LoadType
from elements.frame_element import FrameElement
from solver.assembler import Assembler
from solver.linear_solver import LinearSolver
from solver.postprocessor import Postprocessor

from benchmarks.utils import print_header, print_case, compare, compare_table

_PIN   = ST.PINNED
_FIXED = ST.FIXED
_FREE  = ST.FREE


# ══════════════════════════════════════════════════════════════════════════════
# StructLab helpers
# ══════════════════════════════════════════════════════════════════════════════

def _sl_run(model: Model):
    asm = Assembler(model)
    K = asm.global_stiffness_matrix(model.elements)
    F = asm.global_force_vector(model.elements)
    result = LinearSolver(model).solve(K, F)
    post = Postprocessor(model.elements, model.element_loads, result.displacements)
    return result, post.compute()


def _sl_reaction(result, node_id: int, dof: int) -> float:
    return result.reactions[node_id * 3 + dof]


def _sl_disp(result, node_id: int, dof: int) -> float:
    return result.displacements[node_id * 3 + dof]


def _sl_make_frame(
    coords: list[tuple[float, float]],
    support_map: dict[int, ST],
    connectivity: list[tuple[int, int]],
    E: float,
    A: float,
    I: float,
    point_loads: list[tuple[int, float, float, float]] | None = None,
    udl_elements: list[tuple[int, float]] | None = None,
) -> Model:
    """Build a StructLab 2-D frame model from node coords, supports, connectivity."""
    model = Model()
    mat = Material("m", E)
    sec = Section("s", A, I)

    for i, (x, y) in enumerate(coords):
        model.nodes.append(Node(i, x, y))

    for nid, sup in support_map.items():
        model.supports.append(Support(nid, sup))

    for k, (ni, nj) in enumerate(connectivity):
        model.elements.append(
            FrameElement(k, model.nodes[ni], model.nodes[nj], mat, sec)
        )

    if point_loads:
        for nid, fx, fy, mz in point_loads:
            model.nodal_loads.append(NodalLoad(nid, fx, fy, mz))

    if udl_elements:
        for eid, w in udl_elements:
            model.element_loads.append(ElementLoad(eid, LoadType.UDL, w))

    return model


# ══════════════════════════════════════════════════════════════════════════════
# OpenSeesPy helpers
# ══════════════════════════════════════════════════════════════════════════════

def _ops_build_frame(
    coords: list[tuple[float, float]],
    support_map: dict[int, ST],
    connectivity: list[tuple[int, int]],
    E: float,
    A: float,
    I: float,
    point_loads: list[tuple[int, float, float, float]] | None = None,
    udl_map: dict[int, float] | None = None,
):
    """Set up and solve a 2-D frame in OpenSeesPy. Returns ops module after solve.

    udl_map: {element_0idx: wy} where wy is the local-y (transverse) load per
    unit length — negative = downward for horizontal members.
    """
    import openseespy.opensees as ops

    _FIX = {
        ST.FIXED:    (1, 1, 1),
        ST.PINNED:   (1, 1, 0),
        ST.ROLLER_X: (0, 1, 0),
        ST.ROLLER_Y: (1, 0, 0),
    }

    ops.wipe()
    ops.model("basic", "-ndm", 2, "-ndf", 3)

    for i, (x, y) in enumerate(coords):
        ops.node(i + 1, x, y)

    for nid, sup in support_map.items():
        ops.fix(nid + 1, *_FIX[sup])

    ops.geomTransf("Linear", 1)
    for k, (ni, nj) in enumerate(connectivity):
        ops.element("elasticBeamColumn", k + 1, ni + 1, nj + 1, A, E, I, 1)

    ops.timeSeries("Constant", 1)
    ops.pattern("Plain", 1, 1)

    if point_loads:
        for nid, fx, fy, mz in point_loads:
            ops.load(nid + 1, fx, fy, mz)

    if udl_map:
        for eid, wy in udl_map.items():
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


def _ops_Rx(ops_mod, node_0idx: int) -> float:
    return ops_mod.nodeReaction(node_0idx + 1, 1)


def _ops_Ry(ops_mod, node_0idx: int) -> float:
    return ops_mod.nodeReaction(node_0idx + 1, 2)


def _ops_dx(ops_mod, node_0idx: int) -> float:
    return ops_mod.nodeDisp(node_0idx + 1, 1)


# ══════════════════════════════════════════════════════════════════════════════
# Case 1 — Portal frame, lateral point load
# ══════════════════════════════════════════════════════════════════════════════

def case1_portal_lateral() -> bool:
    """h=L=4m, H=10kN at top-left joint, pinned bases, E=200GPa, I=50e-6 m⁴."""
    print_case("Case 1 — Portal frame, lateral point load H at top-left joint")
    h, L = 4.0, 4.0
    E, A, I = 200e9, 10e-3, 50e-6
    H = 10_000.0

    #  node 1 ──────── node 2   (y = h)
    #     |                |
    #  node 0           node 3   (y = 0)  PIN at 0 and 3
    coords = [(0.0, 0.0), (0.0, h), (L, h), (L, 0.0)]
    support_map = {0: _PIN, 3: _PIN}
    conn = [(0, 1), (1, 2), (2, 3)]

    # ── StructLab ─────────────────────────────────────────────────────────────
    sl_model = _sl_make_frame(coords, support_map, conn, E, A, I,
                               point_loads=[(1, H, 0.0, 0.0)])
    sl_res, _ = _sl_run(sl_model)
    sl_R0x  = _sl_reaction(sl_res, 0, 0)
    sl_R3x  = _sl_reaction(sl_res, 3, 0)
    sl_R0y  = _sl_reaction(sl_res, 0, 1)
    sl_R3y  = _sl_reaction(sl_res, 3, 1)
    sl_sway = _sl_disp(sl_res, 1, 0)

    # ── OpenSeesPy ────────────────────────────────────────────────────────────
    ops = _ops_build_frame(coords, support_map, conn, E, A, I,
                           point_loads=[(1, H, 0.0, 0.0)])
    ops_R0x  = _ops_Rx(ops, 0)
    ops_R3x  = _ops_Rx(ops, 3)
    ops_R0y  = _ops_Ry(ops, 0)
    ops_R3y  = _ops_Ry(ops, 3)
    ops_sway = _ops_dx(ops, 1)

    # ── Analytical (slope-deflection, pinned bases, h=L, same EI) ─────────────
    ref_Rx   = -H / 2                    # −5 000 N (each base resists half)
    ref_R0y  = -H * h / L               # −10 000 N (uplift at windward base)
    ref_R3y  =  H * h / L               # +10 000 N (compression at leeward base)
    ref_sway =  H * L**3 / (4 * E * I)  # lateral displacement at top joint

    print(f"    Analytical: R_0x={ref_Rx:.0f}  R_0y={ref_R0y:.0f}  R_3y={ref_R3y:.0f}  sway={ref_sway*1e3:.4f} mm")
    print(f"    StructLab:  R_0x={sl_R0x:.0f}  R_0y={sl_R0y:.0f}  R_3y={sl_R3y:.0f}  sway={sl_sway*1e3:.4f} mm")
    print(f"    OpenSeesPy: R_0x={ops_R0x:.0f}  R_0y={ops_R0y:.0f}  R_3y={ops_R3y:.0f}  sway={ops_sway*1e3:.4f} mm")

    # Reactions vs analytical: strict 0.1 % tolerance
    ok_reactions = compare_table([
        ("R_0x (StructLab vs Analytical)", sl_R0x, ref_Rx,  "N"),
        ("R_3x (StructLab vs Analytical)", sl_R3x, ref_Rx,  "N"),
        ("R_0y (StructLab vs Analytical)", sl_R0y, ref_R0y, "N"),
        ("R_3y (StructLab vs Analytical)", sl_R3y, ref_R3y, "N"),
    ])
    # Sway vs analytical: 0.5 % — formula ignores axial shortening in columns (~0.28 % error)
    ok_sway_an = compare("sway (StructLab vs Analytical)", sl_sway, ref_sway, "m", tol=0.005)
    ok_ops = compare_table([
        ("R_0x (StructLab vs OpenSeesPy)", sl_R0x,  ops_R0x,  "N"),
        ("R_0y (StructLab vs OpenSeesPy)", sl_R0y,  ops_R0y,  "N"),
        ("R_3y (StructLab vs OpenSeesPy)", sl_R3y,  ops_R3y,  "N"),
        ("sway (StructLab vs OpenSeesPy)", sl_sway, ops_sway, "m"),
    ])
    return ok_reactions and ok_sway_an and ok_ops


# ══════════════════════════════════════════════════════════════════════════════
# Case 2 — Portal frame, gravity UDL on beam
# ══════════════════════════════════════════════════════════════════════════════

def case2_portal_gravity() -> bool:
    """h=L=4m, w=10kN/m UDL on beam, pinned bases, E=200GPa, I=50e-6 m⁴."""
    print_case("Case 2 — Portal frame, gravity UDL on beam (pinned bases)")
    h, L = 4.0, 4.0
    E, A, I = 200e9, 10e-3, 50e-6
    w = 10_000.0  # N/m downward

    coords = [(0.0, 0.0), (0.0, h), (L, h), (L, 0.0)]
    support_map = {0: _PIN, 3: _PIN}
    conn = [(0, 1), (1, 2), (2, 3)]  # element 1 = horizontal beam

    # ── StructLab ─────────────────────────────────────────────────────────────
    sl_model = _sl_make_frame(coords, support_map, conn, E, A, I,
                               udl_elements=[(1, w)])
    sl_res, _ = _sl_run(sl_model)
    sl_R0y = _sl_reaction(sl_res, 0, 1)
    sl_R3y = _sl_reaction(sl_res, 3, 1)
    sl_R0x = _sl_reaction(sl_res, 0, 0)

    # ── OpenSeesPy ────────────────────────────────────────────────────────────
    # wy = -w for downward load on horizontal member (local-y = global-y upward)
    ops = _ops_build_frame(coords, support_map, conn, E, A, I,
                           udl_map={1: -w})
    ops_R0y = _ops_Ry(ops, 0)
    ops_R3y = _ops_Ry(ops, 3)
    ops_R0x = _ops_Rx(ops, 0)

    # ── Analytical (symmetric beam, pinned columns carry no horizontal reaction) ─
    ref_Ry = w * L / 2   # 20 000 N

    print(f"    Analytical: R_0y=R_3y={ref_Ry:.0f} N,  R_0x~0")
    print(f"    StructLab:  R_0y={sl_R0y:.0f}  R_3y={sl_R3y:.0f}  R_0x={sl_R0x:.1f}")
    print(f"    OpenSeesPy: R_0y={ops_R0y:.0f}  R_3y={ops_R3y:.0f}  R_0x={ops_R0x:.1f}")

    return compare_table([
        ("R_0y (StructLab vs Analytical)", sl_R0y, ref_Ry, "N"),
        ("R_3y (StructLab vs Analytical)", sl_R3y, ref_Ry, "N"),
        ("R_0y (StructLab vs OpenSeesPy)", sl_R0y, ops_R0y, "N"),
        ("R_3y (StructLab vs OpenSeesPy)", sl_R3y, ops_R3y, "N"),
    ])


# ══════════════════════════════════════════════════════════════════════════════
# Case 3 — Two-story frame, dual lateral loads
# ══════════════════════════════════════════════════════════════════════════════

def case3_two_story_lateral() -> bool:
    """h=L=4m, H1=8kN at floor 1, H2=4kN at roof, pinned bases, E=200GPa, I=50e-6 m⁴."""
    print_case("Case 3 — Two-story frame, dual lateral loads (pinned bases)")
    h, L = 4.0, 4.0
    E, A, I = 200e9, 10e-3, 50e-6
    H1, H2 = 8_000.0, 4_000.0

    #  4 ──[el 5]── 5   (y = 2h, roof)
    #  |            |
    # [el 3]      [el 4]
    #  |            |
    #  2 ──[el 2]── 3   (y = h,  floor 1)
    #  |            |
    # [el 0]      [el 1]
    #  |            |
    #  0            1   (y = 0,  ground)  PIN at 0 and 1
    coords = [
        (0.0, 0.0), (L,   0.0),
        (0.0, h),   (L,   h),
        (0.0, 2*h), (L, 2*h),
    ]
    support_map = {0: _PIN, 1: _PIN}
    conn = [(0, 2), (1, 3), (2, 3), (2, 4), (3, 5), (4, 5)]

    # ── StructLab ─────────────────────────────────────────────────────────────
    sl_model = _sl_make_frame(
        coords, support_map, conn, E, A, I,
        point_loads=[(2, H1, 0.0, 0.0), (4, H2, 0.0, 0.0)],
    )
    sl_res, _ = _sl_run(sl_model)
    sl_R0x = _sl_reaction(sl_res, 0, 0)
    sl_R1x = _sl_reaction(sl_res, 1, 0)
    sl_R0y = _sl_reaction(sl_res, 0, 1)
    sl_R1y = _sl_reaction(sl_res, 1, 1)

    # ── OpenSeesPy ────────────────────────────────────────────────────────────
    ops = _ops_build_frame(
        coords, support_map, conn, E, A, I,
        point_loads=[(2, H1, 0.0, 0.0), (4, H2, 0.0, 0.0)],
    )
    ops_R0x = _ops_Rx(ops, 0)
    ops_R1x = _ops_Rx(ops, 1)
    ops_R0y = _ops_Ry(ops, 0)
    ops_R1y = _ops_Ry(ops, 1)

    # ── Analytical (pure statics — no slope-deflection needed) ─────────────────
    # ΣFx = 0: R_0x + R_1x = -(H1+H2); anti-symmetry → R_0x = R_1x = -(H1+H2)/2
    # ΣM about node 0: R_1y×L = H1×h + H2×2h
    ref_Rx  = -(H1 + H2) / 2           # −6 000 N
    ref_R1y =  h * (H1 + 2 * H2) / L  # +16 000 N
    ref_R0y = -ref_R1y                  # −16 000 N

    print(f"    Analytical: R_0x={ref_Rx:.0f}  R_0y={ref_R0y:.0f}  R_1y={ref_R1y:.0f}")
    print(f"    StructLab:  R_0x={sl_R0x:.0f}  R_0y={sl_R0y:.0f}  R_1y={sl_R1y:.0f}")
    print(f"    OpenSeesPy: R_0x={ops_R0x:.0f}  R_0y={ops_R0y:.0f}  R_1y={ops_R1y:.0f}")

    return compare_table([
        ("R_0x (StructLab vs Analytical)", sl_R0x, ref_Rx,  "N"),
        ("R_1x (StructLab vs Analytical)", sl_R1x, ref_Rx,  "N"),
        ("R_0y (StructLab vs Analytical)", sl_R0y, ref_R0y, "N"),
        ("R_1y (StructLab vs Analytical)", sl_R1y, ref_R1y, "N"),
        ("R_0x (StructLab vs OpenSeesPy)", sl_R0x, ops_R0x, "N"),
        ("R_0y (StructLab vs OpenSeesPy)", sl_R0y, ops_R0y, "N"),
        ("R_1y (StructLab vs OpenSeesPy)", sl_R1y, ops_R1y, "N"),
    ])


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print_header("StructLab Phase 7 — Frame Benchmarks (StructLab vs OpenSeesPy)")

    results = [
        case1_portal_lateral(),
        case2_portal_gravity(),
        case3_two_story_lateral(),
    ]

    n_pass  = sum(results)
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
