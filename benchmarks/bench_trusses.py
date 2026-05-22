"""Phase 7 — Truss benchmarks: StructLab vs OpenSeesPy.

Two cases, all linear-elastic static:
  1. Simple symmetric 3-node truss — vertical load P at apex (3-4-5 geometry)
  2. Pratt truss — asymmetric load at one top joint (6 nodes, 9 members)

StructLab uses TrussElement (pin_i=pin_j=True, I=0).
OpenSeesPy uses Truss elements (uniaxial elastic material, ndf=2 model).

Sign-convention note
  StructLab: N_i > 0 = compression, N_i < 0 = tension  (FEM element-force convention)
  OpenSeesPy Truss: eleForce gives global end-node forces; axial force is projected
  onto the element axis and converted to StructLab sign convention for comparison.

Run:
    python benchmarks/bench_trusses.py

Requires: pip install openseespy
"""
from __future__ import annotations

import math
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.model import Model
from core.node import Node
from core.support import Support
from core.support import SupportType as ST
from core.material import Material
from core.load import NodalLoad
from elements.truss_element import TrussElement
from solver.assembler import Assembler
from solver.linear_solver import LinearSolver
from solver.postprocessor import Postprocessor

from benchmarks.utils import print_header, print_case, compare_table

_PIN    = ST.PINNED
_ROLLER = ST.ROLLER_X


# ══════════════════════════════════════════════════════════════════════════════
# StructLab helpers
# ══════════════════════════════════════════════════════════════════════════════

def _sl_run(model: Model):
    asm = Assembler(model)
    K = asm.global_stiffness_matrix(model.elements)
    F = asm.global_force_vector(model.elements)
    result = LinearSolver(model).solve(K, F)
    post = Postprocessor(model.elements, [], result.displacements)
    return result, post.compute()


def _sl_reaction(result, node_id: int, dof: int) -> float:
    """Reaction at node_id, dof 0=Rx, 1=Ry."""
    return result.reactions[node_id * 3 + dof]


def _sl_axial(el_results, el_id: int) -> float:
    """Axial force N_i for element el_id (positive = compression)."""
    return next(e for e in el_results if e.element_id == el_id).N_i


def _sl_make_truss(
    coords: list[tuple[float, float]],
    support_map: dict[int, ST],
    connectivity: list[tuple[int, int]],
    E: float,
    A: float,
    point_loads: list[tuple[int, float, float, float]],
) -> Model:
    model = Model()
    mat = Material("m", E)

    for i, (x, y) in enumerate(coords):
        model.nodes.append(Node(i, x, y))

    for nid, sup in support_map.items():
        model.supports.append(Support(nid, sup))

    for k, (ni, nj) in enumerate(connectivity):
        model.elements.append(
            TrussElement(k, model.nodes[ni], model.nodes[nj], mat, A)
        )

    for nid, fx, fy, mz in point_loads:
        model.nodal_loads.append(NodalLoad(nid, fx, fy, mz))

    return model


# ══════════════════════════════════════════════════════════════════════════════
# OpenSeesPy helpers
# ══════════════════════════════════════════════════════════════════════════════

def _ops_build_truss(
    coords: list[tuple[float, float]],
    support_map: dict[int, ST],
    connectivity: list[tuple[int, int]],
    E: float,
    A: float,
    point_loads: list[tuple[int, float, float, float]],
):
    """Set up and solve a 2-D pin-jointed truss in OpenSeesPy (ndf=2).

    Returns the ops module after analysis.
    """
    import openseespy.opensees as ops

    _FIX2 = {
        ST.PINNED:   (1, 1),
        ST.ROLLER_X: (0, 1),
        ST.ROLLER_Y: (1, 0),
    }

    ops.wipe()
    ops.model("basic", "-ndm", 2, "-ndf", 2)

    for i, (x, y) in enumerate(coords):
        ops.node(i + 1, x, y)

    for nid, sup in support_map.items():
        ops.fix(nid + 1, *_FIX2[sup])

    ops.uniaxialMaterial("Elastic", 1, E)
    for k, (ni, nj) in enumerate(connectivity):
        ops.element("Truss", k + 1, ni + 1, nj + 1, A, 1)

    ops.timeSeries("Constant", 1)
    ops.pattern("Plain", 1, 1)
    for nid, fx, fy, _mz in point_loads:
        ops.load(nid + 1, fx, fy)

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
    """Vertical reaction at 0-indexed node (ndf=2 model)."""
    return ops_mod.nodeReaction(node_0idx + 1, 2)


def _ops_axial(
    ops_mod,
    tag_0idx: int,
    ni_0idx: int,
    nj_0idx: int,
) -> float:
    """Axial force in StructLab convention (positive = compression).

    OpenSeesPy eleForce returns the forces APPLIED TO the element ends by the
    structure.  For a compressed member the applied forces push the ends toward
    each other, so the force at node-i points in the (i→j) direction:
      F_along = F_ix·cos θ + F_iy·sin θ > 0  for compression
    This is already the compression-positive convention StructLab uses.
    """
    f = ops_mod.eleForce(tag_0idx + 1)  # [Fx_i, Fy_i, Fx_j, Fy_j]
    xi, yi = ops_mod.nodeCoord(ni_0idx + 1)
    xj, yj = ops_mod.nodeCoord(nj_0idx + 1)
    L_el = math.sqrt((xj - xi) ** 2 + (yj - yi) ** 2)
    cos_th = (xj - xi) / L_el
    sin_th = (yj - yi) / L_el
    return f[0] * cos_th + f[1] * sin_th


# ══════════════════════════════════════════════════════════════════════════════
# Case 1 — Simple symmetric 3-node truss
# ══════════════════════════════════════════════════════════════════════════════

def case1_simple_truss() -> bool:
    """3-4-5 right-triangle truss, P=10kN at apex, E=200GPa, A=10e-3 m²."""
    print_case("Case 1 — Simple symmetric 3-node truss, apex point load")
    P = 10_000.0
    E, A = 200e9, 10e-3

    #  node 2 (3, 4)   ← apex, load P downward
    #    /     \\
    # [el 0] [el 1]
    #  /         \\
    # node 0 --[el 2]-- node 1
    # (0,0)PINNED       (6,0)ROLLER_X
    coords = [(0.0, 0.0), (6.0, 0.0), (3.0, 4.0)]
    support_map = {0: _PIN, 1: _ROLLER}
    conn = [(0, 2), (2, 1), (0, 1)]  # left rafter, right rafter, bottom chord

    # ── StructLab ─────────────────────────────────────────────────────────────
    sl_model = _sl_make_truss(coords, support_map, conn, E, A,
                               point_loads=[(2, 0.0, -P, 0.0)])
    sl_res, sl_el = _sl_run(sl_model)
    sl_R0y = _sl_reaction(sl_res, 0, 1)
    sl_R1y = _sl_reaction(sl_res, 1, 1)
    sl_N_rafter_l = _sl_axial(sl_el, 0)   # el 0: left rafter  (compression)
    sl_N_rafter_r = _sl_axial(sl_el, 1)   # el 1: right rafter (compression)
    sl_N_chord    = _sl_axial(sl_el, 2)   # el 2: bottom chord (tension)

    # ── OpenSeesPy ────────────────────────────────────────────────────────────
    ops = _ops_build_truss(coords, support_map, conn, E, A,
                           point_loads=[(2, 0.0, -P, 0.0)])
    ops_R0y = _ops_Ry(ops, 0)
    ops_R1y = _ops_Ry(ops, 1)
    ops_N_rafter_l = _ops_axial(ops, 0, conn[0][0], conn[0][1])
    ops_N_rafter_r = _ops_axial(ops, 1, conn[1][0], conn[1][1])
    ops_N_chord    = _ops_axial(ops, 2, conn[2][0], conn[2][1])

    # ── Analytical (method of joints, sin=4/5, cos=3/5) ───────────────────────
    ref_Ry       =  P / 2               # 5 000 N (symmetric)
    ref_N_rafter =  P / (2 * 4 / 5)    # 6 250 N compression (N > 0)
    ref_N_chord  = -P * 3 / (2 * 4)    # −3 750 N tension    (N < 0)

    print(f"    Analytical: R_y={ref_Ry:.0f}  N_rafter={ref_N_rafter:.0f}  N_chord={ref_N_chord:.0f}")
    print(f"    StructLab:  R_0y={sl_R0y:.0f}  N_rafter_l={sl_N_rafter_l:.0f}  N_chord={sl_N_chord:.0f}")
    print(f"    OpenSeesPy: R_0y={ops_R0y:.0f}  N_rafter_l={ops_N_rafter_l:.0f}  N_chord={ops_N_chord:.0f}")

    return compare_table([
        ("R_0y (StructLab vs Analytical)",      sl_R0y,       ref_Ry,       "N"),
        ("R_1y (StructLab vs Analytical)",      sl_R1y,       ref_Ry,       "N"),
        ("N_rafter_l (SL vs Analytical)",       sl_N_rafter_l, ref_N_rafter, "N"),
        ("N_rafter_r (SL vs Analytical)",       sl_N_rafter_r, ref_N_rafter, "N"),
        ("N_chord (SL vs Analytical)",          sl_N_chord,   ref_N_chord,  "N"),
        ("R_0y (StructLab vs OpenSeesPy)",      sl_R0y,       ops_R0y,      "N"),
        ("N_rafter_l (SL vs OpenSeesPy)",       sl_N_rafter_l, ops_N_rafter_l, "N"),
        ("N_chord (SL vs OpenSeesPy)",          sl_N_chord,   ops_N_chord,  "N"),
    ])


# ══════════════════════════════════════════════════════════════════════════════
# Case 2 — Pratt truss (6 nodes, 9 members)
# ══════════════════════════════════════════════════════════════════════════════

def case2_pratt_truss() -> bool:
    """6-node 9-member Pratt truss, P=10kN at node 4 (top-left joint).

    Panel width = height = 2 m.  Nodes:
        N4(2,2)─[el 3]─N5(4,2)
       / |                  \\
    [4]  [6]   [8]     [7]   [5]
     /   |     ╲              \\
    N0  N1(2,0) N2(4,0)      N3(6,0)
   PIN                       ROLLER_X
    """
    print_case("Case 2 — Pratt truss (6 nodes, 9 members), asymmetric load at N4")
    P = 10_000.0
    E, A = 200e9, 10e-3

    coords = [
        (0.0, 0.0), (2.0, 0.0), (4.0, 0.0), (6.0, 0.0),
        (2.0, 2.0), (4.0, 2.0),
    ]
    support_map = {0: _PIN, 3: _ROLLER}
    conn = [
        (0, 1), (1, 2), (2, 3),   # bottom chord: el 0, 1, 2
        (4, 5),                    # top chord:    el 3
        (0, 4), (3, 5),            # end posts:    el 4, 5
        (1, 4), (2, 5),            # verticals:    el 6, 7
        (1, 5),                    # Pratt diag:   el 8
    ]

    # ── StructLab ─────────────────────────────────────────────────────────────
    sl_model = _sl_make_truss(coords, support_map, conn, E, A,
                               point_loads=[(4, 0.0, -P, 0.0)])
    sl_res, sl_el = _sl_run(sl_model)
    sl_R0y  = _sl_reaction(sl_res, 0, 1)
    sl_R3y  = _sl_reaction(sl_res, 3, 1)
    sl_N_bc = _sl_axial(sl_el, 0)   # bottom chord N0-N1 (tension)
    sl_N_v  = _sl_axial(sl_el, 6)   # Pratt vertical N1-N4 (compression)
    sl_N_d  = _sl_axial(sl_el, 8)   # Pratt diagonal N1-N5 (tension)

    # ── OpenSeesPy ────────────────────────────────────────────────────────────
    ops = _ops_build_truss(coords, support_map, conn, E, A,
                           point_loads=[(4, 0.0, -P, 0.0)])
    ops_R0y  = _ops_Ry(ops, 0)
    ops_R3y  = _ops_Ry(ops, 3)
    ops_N_bc = _ops_axial(ops, 0, conn[0][0], conn[0][1])
    ops_N_v  = _ops_axial(ops, 6, conn[6][0], conn[6][1])
    ops_N_d  = _ops_axial(ops, 8, conn[8][0], conn[8][1])

    # ── Analytical (method of joints) ─────────────────────────────────────────
    # ΣM about N0: R_3y = P×2/6 = P/3;  R_0y = 2P/3
    ref_R0y  =  2 * P / 3
    ref_R3y  =  P / 3
    ref_N_bc = -2 * P / 3              # tension  (N < 0)
    ref_N_v  =  P / 3                  # compression (N > 0, Pratt vertical)
    ref_N_d  = -P * math.sqrt(2) / 3  # tension  (N < 0, Pratt diagonal)

    print(f"    Analytical: R_0y={ref_R0y:.1f}  R_3y={ref_R3y:.1f}")
    print(f"                N_bc={ref_N_bc:.1f}  N_v={ref_N_v:.1f}  N_d={ref_N_d:.1f}")
    print(f"    StructLab:  R_0y={sl_R0y:.1f}  R_3y={sl_R3y:.1f}")
    print(f"                N_bc={sl_N_bc:.1f}  N_v={sl_N_v:.1f}  N_d={sl_N_d:.1f}")
    print(f"    OpenSeesPy: R_0y={ops_R0y:.1f}  R_3y={ops_R3y:.1f}")
    print(f"                N_bc={ops_N_bc:.1f}  N_v={ops_N_v:.1f}  N_d={ops_N_d:.1f}")

    return compare_table([
        ("R_0y (StructLab vs Analytical)", sl_R0y,  ref_R0y,  "N"),
        ("R_3y (StructLab vs Analytical)", sl_R3y,  ref_R3y,  "N"),
        ("N_bc (SL vs Analytical)",        sl_N_bc, ref_N_bc, "N"),
        ("N_v  (SL vs Analytical)",        sl_N_v,  ref_N_v,  "N"),
        ("N_d  (SL vs Analytical)",        sl_N_d,  ref_N_d,  "N"),
        ("R_0y (StructLab vs OpenSeesPy)", sl_R0y,  ops_R0y,  "N"),
        ("R_3y (StructLab vs OpenSeesPy)", sl_R3y,  ops_R3y,  "N"),
        ("N_bc (SL vs OpenSeesPy)",        sl_N_bc, ops_N_bc, "N"),
        ("N_v  (SL vs OpenSeesPy)",        sl_N_v,  ops_N_v,  "N"),
        ("N_d  (SL vs OpenSeesPy)",        sl_N_d,  ops_N_d,  "N"),
    ])


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print_header("StructLab Phase 7 — Truss Benchmarks (StructLab vs OpenSeesPy)")

    results = [
        case1_simple_truss(),
        case2_pratt_truss(),
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
