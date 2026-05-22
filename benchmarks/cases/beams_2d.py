"""2D Beam benchmark cases B1–B7.

Each run_bN() function builds and solves the model in both StructLab and
OpenSeesPy (+ analytical where available), then returns a BenchResult.

Sign convention:
  - Deflection: positive = downward (sagging)
  - Moment:     positive = sagging
  - Reaction:   positive = upward
"""
from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import math

from core.model import Model
from core.node import Node
from core.support import Support, SupportType as ST
from core.material import Material
from core.section import Section
from core.load import NodalLoad, ElementLoad, LoadType
from elements.frame_element import FrameElement
from solver.assembler import Assembler
from solver.linear_solver import LinearSolver
from solver.postprocessor import Postprocessor

from benchmarks.result import BenchResult, QuantityResult
from benchmarks.sketch import (
    sketch_b1, sketch_b2, sketch_b3, sketch_b4, sketch_b5, sketch_b6, sketch_b7,
)

_PIN    = ST.PINNED
_ROLLER = ST.ROLLER_X
_FIXED  = ST.FIXED
_FREE   = ST.FREE


# ── StructLab helpers ─────────────────────────────────────────────────────────

def _sl_beam(xs, supports, E, A, I, point_loads=None, udl_elements=None) -> Model:
    model = Model()
    mat = Material(name="m", elastic_modulus=E, poisson_ratio=0.3)
    sec = Section(name="s", area=A, moment_of_inertia=I)
    for i, (x, sup) in enumerate(zip(xs, supports)):
        n = Node(id=i, x=x, y=0.0)
        model.nodes.append(n)
        if sup != _FREE:
            model.supports.append(Support(node_id=i, support_type=sup))
    for k in range(len(xs) - 1):
        el = FrameElement(id=k, node_i=model.nodes[k], node_j=model.nodes[k + 1],
                          material=mat, section=sec)
        model.elements.append(el)
    if point_loads:
        for nid, fx, fy, mz in point_loads:
            model.nodal_loads.append(NodalLoad(node_id=nid, fx=fx, fy=fy, moment=mz))
    if udl_elements:
        for eid, w in udl_elements:
            model.element_loads.append(
                ElementLoad(element_id=eid, load_type=LoadType.UDL, magnitude=w))
    return model


def _sl_solve(model):
    asm = Assembler(model)
    K = asm.global_stiffness_matrix(model.elements)
    F = asm.global_force_vector(model.elements)
    res = LinearSolver(model).solve(K, F)
    post = Postprocessor(model.elements, model.element_loads, res.displacements)
    return res, post.compute()


def _sl_dy(res, nid):  return  res.displacements[nid * 3 + 1]
def _sl_ry(res, nid):  return  res.reactions[nid * 3 + 1]
def _sl_mz(res, nid):  return  res.reactions[nid * 3 + 2]
def _sl_mi(el_res, eid): return next(e for e in el_res if e.element_id == eid).M_i
def _sl_mj(el_res, eid): return next(e for e in el_res if e.element_id == eid).M_j


# ── OpenSeesPy helpers ────────────────────────────────────────────────────────

def _ops_beam(xs, supports, E, A, I, point_loads=None, udl_map=None):
    import openseespy.opensees as ops
    _FIX = {_FIXED: (1,1,1), _PIN: (1,1,0), _ROLLER: (0,1,0), ST.ROLLER_Y: (1,0,0), _FREE: None}
    ops.wipe()
    ops.model("basic", "-ndm", 2, "-ndf", 3)
    for i, x in enumerate(xs):
        ops.node(i+1, x, 0.0)
    for i, sup in enumerate(supports):
        fix = _FIX.get(sup)
        if fix:
            ops.fix(i+1, *fix)
    ops.geomTransf("Linear", 1)
    for k in range(len(xs)-1):
        ops.element("elasticBeamColumn", k+1, k+1, k+2, A, E, I, 1)
    ops.timeSeries("Constant", 1); ops.pattern("Plain", 1, 1)
    if point_loads:
        for nid, fx, fy, mz in point_loads:
            ops.load(nid+1, fx, fy, mz)
    if udl_map:
        for eid, wy in udl_map.items():
            ops.eleLoad("-ele", eid+1, "-type", "-beamUniform", wy, 0.0)
    ops.system("BandGeneral"); ops.numberer("Plain"); ops.constraints("Plain")
    ops.integrator("LoadControl", 1.0); ops.algorithm("Linear"); ops.analysis("Static")
    ops.analyze(1); ops.reactions()
    return ops


def _ops_ry(ops, nid): return ops.nodeReaction(nid+1, 2)
def _ops_mz(ops, nid): return ops.nodeReaction(nid+1, 3)
def _ops_dy(ops, nid): return ops.nodeDisp(nid+1, 2)


# ── B1: Simply supported beam, mid-span point load ────────────────────────────

def run_b1() -> BenchResult:
    """B1 — SS beam, mid-span point load P.

    Analytical: δ_max = PL³/48EI  (at mid-span)
                R_A = R_B = P/2
                M_max = PL/4       (at mid-span)
    """
    L, P = 6.0, 50.0  # m, kN
    E, A, I = 210e6, 0.02, 4e-4   # kN/m², m², m⁴

    xs = [0.0, L/2, L]
    sups = [_PIN, _FREE, _ROLLER]
    pl = [(1, 0.0, -P, 0.0)]

    model = _sl_beam(xs, sups, E, A, I, point_loads=pl)
    res, el_res = _sl_solve(model)

    dy_mid_sl = -_sl_dy(res, 1) * 1000          # mm (downward +)
    ry_a_sl   =  _sl_ry(res, 0) / 1000          # kN
    ry_b_sl   =  _sl_ry(res, 2) / 1000          # kN
    mmax_sl   =  abs(_sl_mi(el_res, 1)) / 1000  # kN·m

    ops = _ops_beam(xs, sups, E, A, I, point_loads=pl)
    dy_mid_ops = -_ops_dy(ops, 1) * 1000
    ry_a_ops   = _ops_ry(ops, 0) / 1000
    ry_b_ops   = _ops_ry(ops, 2) / 1000

    dy_exact  = P * L**3 / (48 * E * I) * 1000  # mm
    ry_exact  = P / 2 / 1000                     # kN
    mmax_exact = P * L / 4 / 1000               # kN·m

    qr = [
        QuantityResult("Mid-span deflection",  "mm",   dy_mid_sl,  dy_exact,  "analytical"),
        QuantityResult("Mid-span deflection",  "mm",   dy_mid_sl,  dy_mid_ops,"OpenSeesPy"),
        QuantityResult("Reaction R_A",         "kN",   ry_a_sl,    ry_exact,  "analytical"),
        QuantityResult("Reaction R_B",         "kN",   ry_b_sl,    ry_exact,  "analytical"),
        QuantityResult("Max moment M_max",     "kN·m", mmax_sl,    mmax_exact,"analytical"),
    ]

    return BenchResult(
        case_id="B1",
        title="Simply Supported Beam — Mid-span Point Load",
        description=(
            f"Span L={L} m, point load P={int(P)} kN at mid-span. "
            "E=210 GPa, I=400 cm⁴. Validated against analytical DSM solution and OpenSeesPy."
        ),
        category="2D Beams",
        reference_types=["analytical", "OpenSeesPy"],
        quantities=qr,
        sketch_func=sketch_b1,
    )


# ── B2: Simply supported beam, UDL ───────────────────────────────────────────

def run_b2() -> BenchResult:
    """B2 — SS beam, UDL w.

    Analytical: δ_max = 5wL⁴/384EI  (at mid-span)
                R_A = R_B = wL/2
                M_max = wL²/8
    """
    L, w = 6.0, 20.0   # m, kN/m
    E, A, I = 210e6, 0.02, 4e-4

    xs   = [0.0, L/2, L]
    sups = [_PIN, _FREE, _ROLLER]

    model = _sl_beam(xs, sups, E, A, I, udl_elements=[(0, w), (1, w)])
    res, el_res = _sl_solve(model)

    dy_mid_sl  = -_sl_dy(res, 1) * 1000
    ry_a_sl    =  _sl_ry(res, 0) / 1000
    mmax_sl    =  max(abs(_sl_mj(el_res, 0)), abs(_sl_mi(el_res, 1))) / 1000

    ops = _ops_beam(xs, sups, E, A, I, udl_map={0: -w, 1: -w})
    dy_mid_ops = -_ops_dy(ops, 1) * 1000
    ry_a_ops   = _ops_ry(ops, 0) / 1000

    dy_exact   = 5 * w * L**4 / (384 * E * I) * 1000
    ry_exact   = w * L / 2 / 1000
    mmax_exact = w * L**2 / 8 / 1000

    qr = [
        QuantityResult("Mid-span deflection", "mm",   dy_mid_sl, dy_exact,   "analytical"),
        QuantityResult("Mid-span deflection", "mm",   dy_mid_sl, dy_mid_ops, "OpenSeesPy"),
        QuantityResult("Reaction R_A",        "kN",   ry_a_sl,   ry_exact,   "analytical"),
        QuantityResult("Reaction R_A",        "kN",   ry_a_sl,   ry_a_ops,   "OpenSeesPy"),
        QuantityResult("Max moment M_max",    "kN·m", mmax_sl,   mmax_exact, "analytical"),
    ]

    return BenchResult(
        case_id="B2",
        title="Simply Supported Beam — UDL",
        description=(
            f"Span L={L} m, UDL w={int(w)} kN/m. "
            "E=210 GPa, I=400 cm⁴. Validated against analytical and OpenSeesPy."
        ),
        category="2D Beams",
        reference_types=["analytical", "OpenSeesPy"],
        quantities=qr,
        sketch_func=sketch_b2,
    )


# ── B3: Propped cantilever, mid-span point load ───────────────────────────────

def run_b3() -> BenchResult:
    """B3 — Propped cantilever, mid-span point load P.

    Analytical (Superposition):
      R_B (roller) = 5P/16
      R_A (fixed), M_A by statics
      δ_max ≈ PL³/(48EI)·(1 - 5/8) ... derivation gives 0.00932 PL³/EI at x≈0.447L
    """
    L, P = 5.0, 40.0
    E, A, I = 200e6, 0.02, 3e-4

    xs   = [0.0, L/2, L]
    sups = [_FIXED, _FREE, _ROLLER]
    pl   = [(1, 0.0, -P, 0.0)]

    model = _sl_beam(xs, sups, E, A, I, point_loads=pl)
    res, el_res = _sl_solve(model)

    dy_mid_sl = -_sl_dy(res, 1) * 1000
    ry_b_sl   =  _sl_ry(res, 2) / 1000
    ma_sl     =  abs(_sl_mz(res, 0)) / 1000  # magnitude of root moment

    ops = _ops_beam(xs, sups, E, A, I, point_loads=pl)
    dy_mid_ops = -_ops_dy(ops, 1) * 1000
    ry_b_ops   = _ops_ry(ops, 2) / 1000
    ma_ops     = abs(_ops_mz(ops, 0)) / 1000

    # Analytical (3-moment or force method)
    # R_B = 5P/16  (standard result)
    ry_b_exact = 5 * P / 16 / 1000
    # M_A = -PL(3/16) hogging
    ma_exact   = P * L * 3 / 16 / 1000
    # δ_mid = 7PL³/(768EI)  (standard result for propped cantilever, load at mid-span)
    dy_mid_exact = 7 * P * L**3 / (768 * E * I) * 1000

    qr = [
        QuantityResult("Mid-span deflection",  "mm",   dy_mid_sl,  dy_mid_exact, "analytical"),
        QuantityResult("Mid-span deflection",  "mm",   dy_mid_sl,  dy_mid_ops,   "OpenSeesPy"),
        QuantityResult("Roller reaction R_B",  "kN",   ry_b_sl,    ry_b_exact,   "analytical"),
        QuantityResult("Root moment |M_A|",     "kN·m", ma_sl,      ma_exact,     "analytical"),
        QuantityResult("Root moment |M_A|",     "kN·m", ma_sl,      ma_ops,       "OpenSeesPy"),
    ]

    return BenchResult(
        case_id="B3",
        title="Propped Cantilever — Mid-span Point Load",
        description=(
            f"L={L} m, fixed at A, roller at B, point load P={int(P)} kN at mid-span. "
            "Validated against force-method analytical solution and OpenSeesPy."
        ),
        category="2D Beams",
        reference_types=["analytical", "OpenSeesPy"],
        quantities=qr,
        sketch_func=sketch_b3,
    )


# ── B4: Propped cantilever, UDL ───────────────────────────────────────────────

def run_b4() -> BenchResult:
    """B4 — Propped cantilever, UDL w.

    Analytical: R_B = 3wL/8, M_A = wL²/8, δ_max = wL⁴/185EI at x≈0.4215L
    """
    L, w = 6.0, 15.0
    E, A, I = 200e6, 0.02, 3e-4

    xs   = [0.0, L/3, 2*L/3, L]
    sups = [_FIXED, _FREE, _FREE, _ROLLER]

    model = _sl_beam(xs, sups, E, A, I, udl_elements=[(0, w), (1, w), (2, w)])
    res, el_res = _sl_solve(model)

    ry_b_sl = _sl_ry(res, 3) / 1000
    ma_sl   = abs(_sl_mz(res, 0)) / 1000

    ops = _ops_beam(xs, sups, E, A, I, udl_map={0: -w, 1: -w, 2: -w})
    ry_b_ops = _ops_ry(ops, 3) / 1000
    ma_ops   = abs(_ops_mz(ops, 0)) / 1000

    ry_b_exact = 3 * w * L / 8 / 1000
    ma_exact   = w * L**2 / 8 / 1000

    qr = [
        QuantityResult("Roller reaction R_B", "kN",   ry_b_sl, ry_b_exact, "analytical"),
        QuantityResult("Roller reaction R_B", "kN",   ry_b_sl, ry_b_ops,   "OpenSeesPy"),
        QuantityResult("Root moment M_A",     "kN·m", ma_sl,   ma_exact,   "analytical"),
        QuantityResult("Root moment M_A",     "kN·m", ma_sl,   ma_ops,     "OpenSeesPy"),
    ]

    return BenchResult(
        case_id="B4",
        title="Propped Cantilever — UDL",
        description=(
            f"L={L} m, fixed at A, roller at B, UDL w={int(w)} kN/m. "
            "Standard force-method result: R_B=3wL/8, M_A=wL²/8."
        ),
        category="2D Beams",
        reference_types=["analytical", "OpenSeesPy"],
        quantities=qr,
        sketch_func=sketch_b4,
    )


# ── B5: 2-span continuous beam ────────────────────────────────────────────────

def run_b5() -> BenchResult:
    """B5 — 2-span continuous beam, equal spans, UDL on both.

    3-moment theorem: R_mid = 5wL/4 (by symmetry), R_end = 3wL/8
    """
    L, w = 5.0, 20.0
    E, A, I = 210e6, 0.02, 5e-4

    xs   = [0.0, L/2, L, 3*L/2, 2*L]
    sups = [_PIN, _FREE, _ROLLER, _FREE, _ROLLER]

    model = _sl_beam(xs, sups, E, A, I,
                     udl_elements=[(0, w), (1, w), (2, w), (3, w)])
    res, el_res = _sl_solve(model)

    ry_a_sl   = _sl_ry(res, 0) / 1000
    ry_mid_sl = _sl_ry(res, 2) / 1000
    ry_b_sl   = _sl_ry(res, 4) / 1000

    ops = _ops_beam(xs, sups, E, A, I, udl_map={0: -w, 1: -w, 2: -w, 3: -w})
    ry_a_ops   = _ops_ry(ops, 0) / 1000
    ry_mid_ops = _ops_ry(ops, 2) / 1000

    ry_end_exact = 3 * w * L / 8 / 1000    # R_A = R_B = 3wL/8
    ry_mid_exact = 5 * w * L / 4 / 1000    # R_mid = 10wL/8 = 5wL/4

    qr = [
        QuantityResult("Reaction R_A (end)",  "kN", ry_a_sl,   ry_end_exact, "analytical"),
        QuantityResult("Reaction R_A (end)",  "kN", ry_a_sl,   ry_a_ops,     "OpenSeesPy"),
        QuantityResult("Reaction R_mid",      "kN", ry_mid_sl, ry_mid_exact, "analytical"),
        QuantityResult("Reaction R_mid",      "kN", ry_mid_sl, ry_mid_ops,   "OpenSeesPy"),
        QuantityResult("Reaction R_B (end)",  "kN", ry_b_sl,   ry_end_exact, "analytical"),
    ]

    return BenchResult(
        case_id="B5",
        title="2-span Continuous Beam — UDL",
        description=(
            f"Two equal spans L={L} m, UDL w={int(w)} kN/m on both. "
            "3-moment theorem: end reactions = 3wL/8, centre reaction = 5wL/4."
        ),
        category="2D Beams",
        reference_types=["analytical", "OpenSeesPy"],
        quantities=qr,
        sketch_func=sketch_b5,
    )


# ── B6: 3-span continuous beam ────────────────────────────────────────────────

def run_b6() -> BenchResult:
    """B6 — 3-span continuous beam, equal spans, UDL. Validated vs OpenSeesPy."""
    L, w = 4.0, 25.0
    E, A, I = 210e6, 0.02, 5e-4

    n_segs = 2   # sub-segments per span for accuracy
    xs   = [i * L / n_segs for span in range(3) for i in range(n_segs)] + [3 * L]
    sups = [_PIN if x == 0 else (_ROLLER if abs(x - L) < 1e-6 or abs(x - 2*L) < 1e-6
            or abs(x - 3*L) < 1e-6 else _FREE) for x in xs]

    udl_els = list(range(len(xs) - 1))

    model = _sl_beam(xs, sups, E, A, I, udl_elements=[(k, w) for k in udl_els])
    res, _ = _sl_solve(model)

    # Support indices: 0, n_segs, 2*n_segs, 3*n_segs
    s0 = 0; s1 = n_segs; s2 = 2*n_segs; s3 = 3*n_segs
    ry_0_sl = _sl_ry(res, s0) / 1000
    ry_1_sl = _sl_ry(res, s1) / 1000
    ry_2_sl = _sl_ry(res, s2) / 1000
    ry_3_sl = _sl_ry(res, s3) / 1000

    ops = _ops_beam(xs, sups, E, A, I, udl_map={k: -w for k in udl_els})
    ry_0_ops = _ops_ry(ops, s0) / 1000
    ry_1_ops = _ops_ry(ops, s1) / 1000
    ry_2_ops = _ops_ry(ops, s2) / 1000
    ry_3_ops = _ops_ry(ops, s3) / 1000

    qr = [
        QuantityResult("Reaction R₀",  "kN", ry_0_sl, ry_0_ops, "OpenSeesPy"),
        QuantityResult("Reaction R₁",  "kN", ry_1_sl, ry_1_ops, "OpenSeesPy"),
        QuantityResult("Reaction R₂",  "kN", ry_2_sl, ry_2_ops, "OpenSeesPy"),
        QuantityResult("Reaction R₃",  "kN", ry_3_sl, ry_3_ops, "OpenSeesPy"),
    ]

    return BenchResult(
        case_id="B6",
        title="3-span Continuous Beam — UDL",
        description=(
            f"Three equal spans L={L} m, UDL w={int(w)} kN/m. "
            "Statically indeterminate to 2nd degree. Reactions validated vs OpenSeesPy."
        ),
        category="2D Beams",
        reference_types=["OpenSeesPy"],
        quantities=qr,
        sketch_func=sketch_b6,
    )


# ── B7: Fixed-fixed beam, UDL ─────────────────────────────────────────────────

def run_b7() -> BenchResult:
    """B7 — Fixed-fixed beam, UDL w.

    Analytical: M_end = wL²/12, M_mid = wL²/24, δ_max = wL⁴/384EI
    """
    L, w = 5.0, 30.0
    E, A, I = 210e6, 0.02, 4e-4

    xs   = [0.0, L/2, L]
    sups = [_FIXED, _FREE, _FIXED]

    model = _sl_beam(xs, sups, E, A, I, udl_elements=[(0, w), (1, w)])
    res, el_res = _sl_solve(model)

    ma_sl     = abs(_sl_mz(res, 0)) / 1000
    dy_mid_sl = -_sl_dy(res, 1) * 1000

    ops = _ops_beam(xs, sups, E, A, I, udl_map={0: -w, 1: -w})
    ma_ops     = abs(_ops_mz(ops, 0)) / 1000
    dy_mid_ops = -_ops_dy(ops, 1) * 1000

    ma_exact     = w * L**2 / 12 / 1000
    dy_mid_exact = w * L**4 / (384 * E * I) * 1000
    mmid_exact   = w * L**2 / 24 / 1000

    mmid_sl = max(abs(_sl_mi(el_res, 1)), abs(_sl_mj(el_res, 0))) / 1000

    qr = [
        QuantityResult("Fixed-end moment M_A",  "kN·m", ma_sl,     ma_exact,     "analytical"),
        QuantityResult("Fixed-end moment M_A",  "kN·m", ma_sl,     ma_ops,       "OpenSeesPy"),
        QuantityResult("Mid-span moment",       "kN·m", mmid_sl,   mmid_exact,   "analytical"),
        QuantityResult("Mid-span deflection",   "mm",   dy_mid_sl, dy_mid_exact, "analytical"),
        QuantityResult("Mid-span deflection",   "mm",   dy_mid_sl, dy_mid_ops,   "OpenSeesPy"),
    ]

    return BenchResult(
        case_id="B7",
        title="Fixed-Fixed Beam — UDL",
        description=(
            f"Span L={L} m, both ends fully fixed, UDL w={int(w)} kN/m. "
            "Analytical: M_ends=wL²/12, M_mid=wL²/24, δ_max=wL⁴/384EI."
        ),
        category="2D Beams",
        reference_types=["analytical", "OpenSeesPy"],
        quantities=qr,
        sketch_func=sketch_b7,
    )


def run_all() -> list[BenchResult]:
    return [run_b1(), run_b2(), run_b3(), run_b4(), run_b5(), run_b6(), run_b7()]
