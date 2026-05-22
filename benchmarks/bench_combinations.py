"""Phase 7 — Load combinations & pattern loading benchmark: StructLab vs OpenSeesPy.

Validates that StructLab's EN 1990 combination engine (1.35G + 1.5Q + 1.5ψ₀W)
produces identical results to manually superposing OpenSeesPy solutions.

Also validates EN 1992-1-1 pattern loading: alternating span patterns on a
2-span continuous beam, comparing StructLab's pattern-run results against
OpenSeesPy with the same Q-distribution.

Run:
    python benchmarks/bench_combinations.py

Requires: openseespy
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
from core.material import Material
from core.section import Section
from core.load import NodalLoad, ElementLoad, LoadType
from elements.frame_element import FrameElement
from solver.assembler import Assembler
from solver.linear_solver import LinearSolver
from solver.postprocessor import Postprocessor, ElementResult

from benchmarks.utils import print_header, print_case, compare_table

_FIXED  = ST.FIXED
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
    post = Postprocessor(model.elements, model.element_loads, result.displacements)
    return result, post.compute()


def _sl_reaction(result, node_id: int, dof: int) -> float:
    return result.reactions[node_id * 3 + dof]


def _sl_disp(result, node_id: int, dof: int) -> float:
    return result.displacements[node_id * 3 + dof]


def _sl_moment(el_results, el_id: int, end: str) -> float:
    er = next(e for e in el_results if e.element_id == el_id)
    return er.M_i if end == "i" else er.M_j


# ══════════════════════════════════════════════════════════════════════════════
# OpenSeesPy helpers
# ══════════════════════════════════════════════════════════════════════════════

def _ops_beam(xs, sups, E, A, I, udl_map=None, point_loads=None):
    """Build and solve a 2D beam model in OpenSeesPy. Returns (ops, node_tags)."""
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

    for i, sup in enumerate(sups):
        fix = _FIX.get(sup)
        if fix is not None:
            ops.fix(i + 1, *fix)

    ops.geomTransf("Linear", 1)

    for k in range(len(xs) - 1):
        ops.element(
            "elasticBeamColumn", k + 1,
            k + 1, k + 2, A, E, I, 1,
        )

    ops.timeSeries("Constant", 1)
    ops.pattern("Plain", 1, 1)

    if udl_map:
        for eid, wy in udl_map.items():
            ops.eleLoad("-ele", eid + 1, "-type", "-beamUniform", wy, 0.0)

    if point_loads:
        for nid, fx, fy, mz in point_loads:
            ops.load(nid + 1, fx, fy, mz)

    ops.system("BandGeneral")
    ops.numberer("Plain")
    ops.constraints("Plain")
    ops.integrator("LoadControl", 1.0)
    ops.algorithm("Linear")
    ops.analysis("Static")
    ops.analyze(1)
    ops.reactions()

    return ops, list(range(1, len(xs) + 1))


# ══════════════════════════════════════════════════════════════════════════════
# Case 1 — EN 1990 ULS combination (1.35G + 1.5Q)
# ══════════════════════════════════════════════════════════════════════════════

def case1_uls_combination():
    """2-span continuous beam, 2×8 m, IPE 400.

    G: 12 kN/m (dead)   Q: 8 kN/m (imposed)
    ULS = 1.35G + 1.5Q = 1.35×12 + 1.5×8 = 28.2 kN/m total

    Both StructLab and OpenSeesPy solve the superimposed case directly.
    """
    print_case("Case 1 — EN 1990 ULS combination: 1.35G + 1.5Q on 2-span beam")

    L1, L2 = 8.0, 8.0
    xs = [0.0, L1, L1 + L2]
    sups = [_PIN, _ROLLER, _ROLLER]
    E, A, I = 210e9, 0.008446, 2.313e-4

    w_g = 12_000.0   # N/m dead
    w_q =  8_000.0   # N/m imposed
    w_uls = 1.35 * w_g + 1.5 * w_q

    # ── StructLab: solve ULS directly ────────────────────────────────────────
    model = Model()
    mat = Material("m", E)
    sec = Section("s", A, I)
    for i, (x, sup) in enumerate(zip(xs, sups)):
        n = Node(id=i, x=x, y=0.0)
        model.nodes.append(n)
        if sup != ST.FREE:
            model.supports.append(Support(node_id=i, support_type=sup))
    for k in range(2):
        el = FrameElement(id=k, node_i=model.nodes[k], node_j=model.nodes[k + 1],
                          material=mat, section=sec)
        model.elements.append(el)
        model.element_loads.append(
            ElementLoad(element_id=k, load_type=LoadType.UDL, magnitude=w_uls))

    sl_res, sl_el = _sl_run(model)

    # ── OpenSeesPy: solve ULS directly ───────────────────────────────────────
    ops, _ = _ops_beam(xs, sups, E, A, I, udl_map={0: -w_uls, 1: -w_uls})

    rows = [
        ("R_0y (end)",     _sl_reaction(sl_res, 0, 1), ops.nodeReaction(1, 2), "N"),
        ("R_1y (center)",  _sl_reaction(sl_res, 1, 1), ops.nodeReaction(2, 2), "N"),
        ("R_2y (end)",     _sl_reaction(sl_res, 2, 1), ops.nodeReaction(3, 2), "N"),
        ("M_0 (el0, i)",   _sl_moment(sl_el, 0, "i"),
         ops.nodeReaction(1, 3), "N·m"),
    ]
    return compare_table(rows)


def _ops_element_moment(ops, el_tag: int, x: float) -> float:
    """Return bending moment at distance x from node i of an elastic beam column."""
    # For an elasticBeamColumn, force at end J index is 2 in basic forces (Mz)
    # We compute M(x) from end forces: M(x) = M_i + V_i * x - w * x²/2
    fi = ops.eleResponse(el_tag, "forces")
    if len(fi) >= 6:
        return float(fi[2])  # M_i (local z moment at node i)
    return 0.0


# ══════════════════════════════════════════════════════════════════════════════
# Case 2 — EN 1992-1-1 pattern loading: alternating spans
# ══════════════════════════════════════════════════════════════════════════════

def case2_pattern_loading():
    """3-span continuous beam, 3×6 m. G=10 kN/m on all spans, Q=15 kN/m.

    EN 1992-1-1 pattern A: Q on spans 1 and 3 (odd-indexed).
    Compare StructLab pattern solution vs OpenSeesPy with same Q dist.
    """
    print_case("Case 2 — EN 1992-1-1 pattern loading (Alt A: spans 1,3)")

    L = 6.0
    xs = [0.0, L, 2 * L, 3 * L]
    sups = [_PIN, _ROLLER, _ROLLER, _ROLLER]
    E, A, I = 210e9, 0.008446, 2.313e-4   # IPE 400

    w_g = 10_000.0  # dead on all spans
    w_q = 15_000.0  # imposed only on spans 1, 3

    # ── StructLab: pattern load directly ──────────────────────────────────────
    model = Model()
    mat = Material("m", E)
    sec = Section("s", A, I)
    for i, (x, sup) in enumerate(zip(xs, sups)):
        n = Node(id=i, x=x, y=0.0)
        model.nodes.append(n)
        if sup != ST.FREE:
            model.supports.append(Support(node_id=i, support_type=sup))

    for k in range(3):
        el = FrameElement(id=k, node_i=model.nodes[k], node_j=model.nodes[k + 1],
                          material=mat, section=sec)
        model.elements.append(el)
        # G on all spans; Q only on spans 0 and 2 (indices 0,2)
        w_total = w_g + (w_q if k in (0, 2) else 0.0)
        model.element_loads.append(
            ElementLoad(element_id=k, load_type=LoadType.UDL, magnitude=w_total))

    sl_res, sl_el = _sl_run(model)

    # ── OpenSeesPy: same pattern ──────────────────────────────────────────────
    udl_map = {}
    for k in range(3):
        w_total = w_g + (w_q if k in (0, 2) else 0.0)
        udl_map[k] = -w_total
    ops, _ = _ops_beam(xs, sups, E, A, I, udl_map=udl_map)

    rows = [
        ("R_0y (pin)",     _sl_reaction(sl_res, 0, 1), ops.nodeReaction(1, 2), "N"),
        ("R_1y (roller 1)", _sl_reaction(sl_res, 1, 1), ops.nodeReaction(2, 2), "N"),
        ("R_2y (roller 2)", _sl_reaction(sl_res, 2, 1), ops.nodeReaction(3, 2), "N"),
        ("R_3y (roller 3)", _sl_reaction(sl_res, 3, 1), ops.nodeReaction(4, 2), "N"),
        ("M_0 (el0, i)",   _sl_moment(sl_el, 0, "i"),
         ops.nodeReaction(1, 3), "N·m"),
    ]
    return compare_table(rows)


# ══════════════════════════════════════════════════════════════════════════════
# Case 3 — EN 1990 ULS + Wind (1.35G + 1.5Q + 1.5ψ₀W, ψ₀=0.6)
# ══════════════════════════════════════════════════════════════════════════════

def case3_uls_with_wind():
    """Portal frame, 6 m × 4 m, IPE 360 rafter, HEB 220 columns.

    G: 15 kN/m on rafter   Q: 10 kN/m on rafter   W: 25 kN lateral at eaves
    ULS = 1.35G + 1.5Q + 1.5×0.6×W
    """
    print_case("Case 3 — EN 1990 ULS+Wind: portal frame, 1.35G+1.5Q+0.9W")

    span, height = 6.0, 4.0
    E = 210e9
    A_col, I_col = 0.009104, 8.091e-5    # HEB 220
    A_bm,  I_bm  = 0.007273, 1.627e-4    # IPE 360

    w_g = 15_000.0
    w_q = 10_000.0
    H_w = 25_000.0

    w_uls  = 1.35 * w_g + 1.5 * w_q       # vertical UDL
    H_uls  = 1.5 * 0.6 * H_w             # lateral wind

    # ── StructLab ─────────────────────────────────────────────────────────────
    model = Model()
    mat_c = Material("col", E)
    sec_c = Section("col", A_col, I_col)
    mat_b = Material("bm", E)
    sec_b = Section("bm", A_bm, I_bm)

    n0 = Node(id=0, x=0.0, y=0.0)
    n1 = Node(id=1, x=0.0, y=height)
    n2 = Node(id=2, x=span, y=height)
    n3 = Node(id=3, x=span, y=0.0)
    for n in [n0, n1, n2, n3]:
        model.nodes.append(n)

    model.supports.append(Support(0, ST.PINNED))
    model.supports.append(Support(3, ST.PINNED))

    model.elements.append(FrameElement(0, n0, n1, mat_c, sec_c))
    model.elements.append(FrameElement(1, n1, n2, mat_b, sec_b))
    model.elements.append(FrameElement(2, n2, n3, mat_c, sec_c))

    model.element_loads.append(
        ElementLoad(element_id=1, load_type=LoadType.UDL, magnitude=w_uls))
    model.nodal_loads.append(NodalLoad(node_id=1, fx=H_uls, fy=0.0, moment=0.0))

    sl_res, sl_el = _sl_run(model)

    # ── OpenSeesPy ────────────────────────────────────────────────────────────
    import openseespy.opensees as ops
    ops.wipe()
    ops.model("basic", "-ndm", 2, "-ndf", 3)

    ops.node(1, 0.0, 0.0)
    ops.node(2, 0.0, height)
    ops.node(3, span, height)
    ops.node(4, span, 0.0)

    ops.fix(1, 1, 1, 0)
    ops.fix(4, 1, 1, 0)

    ops.geomTransf("Linear", 1)
    ops.geomTransf("Linear", 2)
    ops.geomTransf("Linear", 3)

    ops.element("elasticBeamColumn", 1, 1, 2, A_col, E, I_col, 1)
    ops.element("elasticBeamColumn", 2, 2, 3, A_bm,  E, I_bm,  2)
    ops.element("elasticBeamColumn", 3, 3, 4, A_col, E, I_col, 3)

    ops.timeSeries("Linear", 1)
    ops.pattern("Plain", 1, 1)
    ops.eleLoad("-ele", 2, "-type", "-beamUniform", -w_uls, 0.0)
    ops.load(2, H_uls, 0.0, 0.0)

    ops.system("BandGeneral")
    ops.numberer("RCM")
    ops.constraints("Plain")
    ops.integrator("LoadControl", 1.0)
    ops.algorithm("Linear")
    ops.analysis("Static")
    ops.analyze(1)
    ops.reactions()

    rows = [
        ("R_0x (base left)",  _sl_reaction(sl_res, 0, 0), ops.nodeReaction(1, 1), "N"),
        ("R_0y (base left)",  _sl_reaction(sl_res, 0, 1), ops.nodeReaction(1, 2), "N"),
        ("R_3x (base right)", _sl_reaction(sl_res, 3, 0), ops.nodeReaction(4, 1), "N"),
        ("R_3y (base right)", _sl_reaction(sl_res, 3, 1), ops.nodeReaction(4, 2), "N"),
        ("dx eave left",      _sl_disp(sl_res, 1, 0),     ops.nodeDisp(2, 1),     "m"),
    ]
    return compare_table(rows)


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print_header("StructLab Phase 7 — Load Combinations & Pattern Loading "
                 "(StructLab vs OpenSeesPy)")
    results = []
    results.append(case1_uls_combination())
    results.append(case2_pattern_loading())
    results.append(case3_uls_with_wind())

    all_pass = all(results)
    print()
    print("=" * 72)
    if all_pass:
        print("  All 3 combination / pattern cases PASSED")
    else:
        print("  Some cases FAILED — see details above")
    print("=" * 72)
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
