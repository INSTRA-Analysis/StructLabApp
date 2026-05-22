"""Phase 7 — Braced frame benchmark: StructLab vs OpenSeesPy.

2-story 4-bay braced frame from "braced frame.slab":
  - 15 nodes  (5 FIXED bases, 5 floor-1, 5 floor-2)
  - 18 BEAM members  (columns + floor beams, FrameElement / elasticBeamColumn)
  - 2 BAR diagonal braces  (BarElement / elasticBeamColumn -release 3)
  - Lateral loads: 20 kN at floor-1 left node, 25 kN at floor-2 left node

Checks:
  - Global horizontal & vertical equilibrium (StructLab and OpenSeesPy)
  - Floor-1 and floor-2 lateral sway: StructLab vs OpenSeesPy
  - Axial force in each diagonal brace: StructLab vs OpenSeesPy

Run:
    python benchmarks/bench_braced_frame.py

Requires: pip install openseespy  (version with -release support)
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
from core.section import Section
from core.load import NodalLoad
from elements.frame_element import FrameElement
from elements.bar_element import BarElement
from solver.assembler import Assembler
from solver.linear_solver import LinearSolver
from solver.postprocessor import Postprocessor

from benchmarks.utils import print_header, print_case, compare, compare_table

_FIXED = ST.FIXED

# ══════════════════════════════════════════════════════════════════════════════
# Model geometry — mirrors "braced frame.slab" exactly
# ══════════════════════════════════════════════════════════════════════════════

COORDS = [
    # base nodes (IDs 0-4, y = -4 m)
    (-2.0, -4.0), (2.0, -4.0), (6.0, -4.0), (10.0, -4.0), (14.0, -4.0),
    # floor-1 nodes (IDs 5-9, y = -1 m)
    (-2.0, -1.0), (2.0, -1.0), (6.0, -1.0), (10.0, -1.0), (14.0, -1.0),
    # floor-2 nodes (IDs 10-14, y = 2 m)
    (-2.0,  2.0), (2.0,  2.0), (6.0,  2.0), (10.0,  2.0), (14.0,  2.0),
]

SUPPORT_MAP = {0: _FIXED, 1: _FIXED, 2: _FIXED, 3: _FIXED, 4: _FIXED}

# (node_i, node_j, is_bar) — IDs 0-19 match .slab member IDs
MEMBERS: list[tuple[int, int, bool]] = [
    (0,  5,  False),  # 0  column A base→floor1
    (5,  10, False),  # 1  column A floor1→floor2
    (10, 11, False),  # 2  beam floor-2 bay 1
    (1,  6,  False),  # 3  column B base→floor1
    (6,  11, False),  # 4  column B floor1→floor2
    (11, 12, False),  # 5  beam floor-2 bay 2
    (2,  7,  False),  # 6  column C base→floor1
    (7,  12, False),  # 7  column C floor1→floor2
    (12, 13, False),  # 8  beam floor-2 bay 3
    (3,  8,  False),  # 9  column D base→floor1
    (8,  13, False),  # 10 column D floor1→floor2
    (13, 14, False),  # 11 beam floor-2 bay 4
    (4,  9,  False),  # 12 column E base→floor1
    (9,  14, False),  # 13 column E floor1→floor2
    (5,  6,  False),  # 14 beam floor-1 bay 1
    (6,  7,  False),  # 15 beam floor-1 bay 2
    (7,  8,  False),  # 16 beam floor-1 bay 3
    (8,  9,  False),  # 17 beam floor-1 bay 4
    (1,  7,  True),   # 18 BAR brace A  (node 1 base → node 7 floor-1)
    (6,  12, True),   # 19 BAR brace B  (node 6 floor-1 → node 12 floor-2)
]

POINT_LOADS = [
    (5,  20_000.0, 0.0, 0.0),   # 20 kN lateral at floor-1 left
    (10, 25_000.0, 0.0, 0.0),   # 25 kN lateral at floor-2 left
]

E = 200e9   # Pa
A = 0.03    # m²
I = 3e-4    # m⁴


# ══════════════════════════════════════════════════════════════════════════════
# StructLab
# ══════════════════════════════════════════════════════════════════════════════

def _sl_build() -> Model:
    model = Model()
    mat = Material("steel", E)
    sec = Section("s", A, I)

    for i, (x, y) in enumerate(COORDS):
        model.nodes.append(Node(i, x, y))

    for nid, sup in SUPPORT_MAP.items():
        model.supports.append(Support(nid, sup))

    for k, (ni, nj, is_bar) in enumerate(MEMBERS):
        if is_bar:
            el = BarElement(k, model.nodes[ni], model.nodes[nj], mat, A)
        else:
            el = FrameElement(k, model.nodes[ni], model.nodes[nj], mat, sec)
        model.elements.append(el)

    for nid, fx, fy, mz in POINT_LOADS:
        model.nodal_loads.append(NodalLoad(nid, fx, fy, mz))

    return model


def _sl_run(model: Model):
    asm = Assembler(model)
    K = asm.global_stiffness_matrix(model.elements)
    F = asm.global_force_vector(model.elements)
    result = LinearSolver(model).solve(K, F)
    post = Postprocessor(model.elements, [], result.displacements)
    return result, post.compute()


def _sl_reaction(result, node_id: int, dof: int) -> float:
    return result.reactions[node_id * 3 + dof]


def _sl_disp(result, node_id: int, dof: int) -> float:
    return result.displacements[node_id * 3 + dof]


def _sl_axial(el_results, el_id: int) -> float:
    return next(e for e in el_results if e.element_id == el_id).N_i


# ══════════════════════════════════════════════════════════════════════════════
# OpenSeesPy
# ══════════════════════════════════════════════════════════════════════════════

def _ops_build():
    import openseespy.opensees as ops

    ops.wipe()
    ops.model("basic", "-ndm", 2, "-ndf", 3)

    for i, (x, y) in enumerate(COORDS):
        ops.node(i + 1, x, y)

    for nid in SUPPORT_MAP:
        ops.fix(nid + 1, 1, 1, 1)

    ops.geomTransf("Linear", 1)

    for k, (ni, nj, is_bar) in enumerate(MEMBERS):
        if is_bar:
            # Pin releases at both ends → axial-only (matches BarElement)
            ops.element("elasticBeamColumn",
                        k + 1, ni + 1, nj + 1, A, E, I, 1,
                        "-release", 3)
        else:
            ops.element("elasticBeamColumn",
                        k + 1, ni + 1, nj + 1, A, E, I, 1)

    ops.timeSeries("Constant", 1)
    ops.pattern("Plain", 1, 1)
    for nid, fx, fy, mz in POINT_LOADS:
        ops.load(nid + 1, fx, fy, mz)

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


def _ops_axial(ops_mod, el_0idx: int, ni_0idx: int, nj_0idx: int) -> float:
    """Axial force in StructLab sign convention (positive = compression)."""
    f = ops_mod.eleForce(el_0idx + 1)   # [Fx_i, Fy_i, Mz_i, Fx_j, Fy_j, Mz_j]
    xi, yi = ops_mod.nodeCoord(ni_0idx + 1)
    xj, yj = ops_mod.nodeCoord(nj_0idx + 1)
    L_el = math.sqrt((xj - xi) ** 2 + (yj - yi) ** 2)
    cos_th = (xj - xi) / L_el
    sin_th = (yj - yi) / L_el
    return f[0] * cos_th + f[1] * sin_th


# ══════════════════════════════════════════════════════════════════════════════
# Benchmark case
# ══════════════════════════════════════════════════════════════════════════════

def case_braced_frame() -> bool:
    """2-story 4-bay braced frame — lateral 20 kN + 25 kN, fixed bases."""
    print_case(
        "2-story 4-bay braced frame  |  F_floor1=20 kN  F_floor2=25 kN  |  fixed bases"
    )

    total_H = sum(pl[1] for pl in POINT_LOADS)   # 45 000 N

    # ── StructLab ─────────────────────────────────────────────────────────────
    sl_model = _sl_build()
    sl_res, sl_el = _sl_run(sl_model)

    sl_dx5   = _sl_disp(sl_res, 5, 0)    # floor-1 sway at loaded node
    sl_dx10  = _sl_disp(sl_res, 10, 0)   # floor-2 sway at loaded node
    sl_sum_Rx = sum(_sl_reaction(sl_res, n, 0) for n in range(5))
    sl_sum_Ry = sum(_sl_reaction(sl_res, n, 1) for n in range(5))
    sl_N_A   = _sl_axial(sl_el, 18)      # brace 18: node 1 → node 7
    sl_N_B   = _sl_axial(sl_el, 19)      # brace 19: node 6 → node 12

    # ── OpenSeesPy ────────────────────────────────────────────────────────────
    ops = _ops_build()

    ops_dx5   = _ops_dx(ops, 5)
    ops_dx10  = _ops_dx(ops, 10)
    ops_sum_Rx = sum(_ops_Rx(ops, n) for n in range(5))
    ops_sum_Ry = sum(_ops_Ry(ops, n) for n in range(5))
    ops_N_A   = _ops_axial(ops, 18, MEMBERS[18][0], MEMBERS[18][1])
    ops_N_B   = _ops_axial(ops, 19, MEMBERS[19][0], MEMBERS[19][1])

    # ── Print summary ──────────────────────────────────────────────────────────
    print()
    print(f"    {'Quantity':<28s}  {'StructLab':>14s}  {'OpenSeesPy':>14s}")
    print(f"    {'-'*60}")
    print(f"    {'dx floor-1 (node 5)':<28s}  {sl_dx5*1e3:>13.4f} mm  {ops_dx5*1e3:>13.4f} mm")
    print(f"    {'dx floor-2 (node 10)':<28s}  {sl_dx10*1e3:>13.4f} mm  {ops_dx10*1e3:>13.4f} mm")
    print(f"    {'Sum_Rx at base':<28s}  {sl_sum_Rx:>13.1f} N   {ops_sum_Rx:>13.1f} N")
    print(f"    {'Sum_Ry at base':<28s}  {sl_sum_Ry:>13.4f} N   {ops_sum_Ry:>13.4f} N")
    print(f"    {'N brace A (1->7)':<28s}  {sl_N_A:>13.1f} N   {ops_N_A:>13.1f} N")
    print(f"    {'N brace B (6->12)':<28s}  {sl_N_B:>13.1f} N   {ops_N_B:>13.1f} N")
    print(f"    (Statics: Sum_Rx should = {-total_H:.0f} N,  Sum_Ry should = 0 N)")
    print()

    # Global equilibrium — both solvers vs statics
    ok_eq = compare_table([
        ("Sum_Rx (SL vs -Sum_F_ext)",    sl_sum_Rx,  -total_H, "N"),
        ("Sum_Rx (OPS vs -Sum_F_ext)",   ops_sum_Rx, -total_H, "N"),
        ("Sum_Ry (SL vs 0)",             sl_sum_Ry,   0.0,     "N"),
        ("Sum_Ry (OPS vs 0)",            ops_sum_Ry,  0.0,     "N"),
    ])

    # StructLab vs OpenSeesPy
    ok_vs = compare_table([
        ("dx floor-1 (SL vs OPS)",  sl_dx5,   ops_dx5,   "m"),
        ("dx floor-2 (SL vs OPS)",  sl_dx10,  ops_dx10,  "m"),
        ("N brace A  (SL vs OPS)",  sl_N_A,   ops_N_A,   "N"),
        ("N brace B  (SL vs OPS)",  sl_N_B,   ops_N_B,   "N"),
    ])

    return ok_eq and ok_vs


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print_header(
        "StructLab Phase 7 — Braced Frame Benchmark (StructLab vs OpenSeesPy)"
    )
    passed = case_braced_frame()
    print()
    print("=" * 72)
    if passed:
        print("  \033[1m\033[32mAll checks PASSED\033[0m")
    else:
        print("  \033[1m\033[31mSome checks FAILED\033[0m")
    print("=" * 72)
    print()


if __name__ == "__main__":
    main()
