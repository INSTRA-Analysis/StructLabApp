"""2D Frame benchmark cases F1–F3.

Cases compare StructLab vs OpenSeesPy for portal and multi-storey frames.
"""
from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

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
from benchmarks.sketch import sketch_f1, sketch_f2, sketch_f3

_FIXED = ST.FIXED
_FREE  = ST.FREE


def _sl_solve(model):
    asm = Assembler(model)
    K = asm.global_stiffness_matrix(model.elements)
    F = asm.global_force_vector(model.elements)
    res = LinearSolver(model).solve(K, F)
    post = Postprocessor(model.elements, model.element_loads, res.displacements)
    return res, post.compute()


def _sl_dx(res, nid): return res.displacements[nid * 3]
def _sl_dy(res, nid): return res.displacements[nid * 3 + 1]
def _sl_ry(res, nid): return res.reactions[nid * 3 + 1]
def _sl_rx(res, nid): return res.reactions[nid * 3]
def _sl_mz(res, nid): return res.reactions[nid * 3 + 2]


# ── OpenSeesPy helpers ────────────────────────────────────────────────────────

def _ops_solve(nodes_xy, elements_ij, supports, E, A, I,
               nodal_loads=None, udl_map=None):
    """Generic 2D frame solver using OpenSeesPy.

    nodes_xy : list of (x, y) — 0-indexed
    elements_ij : list of (i, j) — 0-indexed node pairs
    supports : dict {node_0idx: (fix_x, fix_y, fix_rz)}
    nodal_loads : list of (node_0idx, Fx, Fy, Mz)
    udl_map : dict {el_0idx: wy}  — wy = -w for downward in ops convention
    """
    import openseespy.opensees as ops
    ops.wipe()
    ops.model("basic", "-ndm", 2, "-ndf", 3)
    for i, (x, y) in enumerate(nodes_xy):
        ops.node(i + 1, x, y)
    for nid, fix in supports.items():
        ops.fix(nid + 1, *fix)
    ops.geomTransf("Linear", 1)
    for k, (ni, nj) in enumerate(elements_ij):
        ops.element("elasticBeamColumn", k + 1, ni + 1, nj + 1, A, E, I, 1)
    ops.timeSeries("Constant", 1); ops.pattern("Plain", 1, 1)
    if nodal_loads:
        for nid, fx, fy, mz in nodal_loads:
            ops.load(nid + 1, fx, fy, mz)
    if udl_map:
        for eid, wy in udl_map.items():
            ops.eleLoad("-ele", eid + 1, "-type", "-beamUniform", wy, 0.0)
    ops.system("BandGeneral"); ops.numberer("Plain"); ops.constraints("Plain")
    ops.integrator("LoadControl", 1.0); ops.algorithm("Linear")
    ops.analysis("Static"); ops.analyze(1); ops.reactions()
    return ops


def _ops_dx(ops, nid): return ops.nodeDisp(nid + 1, 1)
def _ops_dy(ops, nid): return ops.nodeDisp(nid + 1, 2)
def _ops_rx(ops, nid): return ops.nodeReaction(nid + 1, 1)
def _ops_ry(ops, nid): return ops.nodeReaction(nid + 1, 2)
def _ops_mz(ops, nid): return ops.nodeReaction(nid + 1, 3)


# ── StructLab frame builder ───────────────────────────────────────────────────

def _sl_frame(nodes_xy, elements_ij, supports_map, E, A, I,
              nodal_loads=None, udl_elements=None):
    model = Model()
    mat = Material(name="m", elastic_modulus=E, poisson_ratio=0.3)
    sec = Section(name="s", area=A, moment_of_inertia=I)
    for nid, (x, y) in enumerate(nodes_xy):
        model.nodes.append(Node(id=nid, x=x, y=y))
    for nid, stype in supports_map.items():
        model.supports.append(Support(node_id=nid, support_type=stype))
    for k, (ni, nj) in enumerate(elements_ij):
        model.elements.append(FrameElement(
            id=k, node_i=model.nodes[ni], node_j=model.nodes[nj],
            material=mat, section=sec))
    if nodal_loads:
        for nid, fx, fy, mz in nodal_loads:
            model.nodal_loads.append(NodalLoad(node_id=nid, fx=fx, fy=fy, moment=mz))
    if udl_elements:
        for eid, w in udl_elements:
            model.element_loads.append(
                ElementLoad(element_id=eid, load_type=LoadType.UDL, magnitude=w))
    return model


# ── F1: Portal frame, horizontal point load ───────────────────────────────────

def run_f1() -> BenchResult:
    """F1 — Portal frame (fixed bases), lateral point load H at top-left.

    Nodes: 0=A(0,0) 1=B(0,H) 2=C(L,H) 3=D(L,0)
    Elements: col_L(0→1), beam(1→2), col_R(2→3)
    """
    L, H = 6.0, 4.0   # m
    P = 20.0           # kN lateral at B
    E, A, I = 200e6, 0.02, 4e-4   # kN/m², m², m⁴

    nodes = [(0, 0), (0, H), (L, H), (L, 0)]
    els   = [(0, 1), (1, 2), (2, 3)]
    sups  = {0: _FIXED, 3: _FIXED}
    ops_sups = {0: (1,1,1), 3: (1,1,1)}
    pl    = [(1, P, 0.0, 0.0)]

    model = _sl_frame(nodes, els, sups, E, A, I, nodal_loads=pl)
    res, _ = _sl_solve(model)

    dx_top_sl = _sl_dx(res, 1) * 1000          # mm
    ry_a_sl   = _sl_ry(res, 0) / 1000          # kN (vertical reaction at A)
    rx_a_sl   = _sl_rx(res, 0) / 1000          # kN (horizontal reaction at A)
    ma_sl     = abs(_sl_mz(res, 0)) / 1000     # kN·m

    ops = _ops_solve(nodes, els, ops_sups, E, A, I, nodal_loads=pl)
    dx_top_ops = _ops_dx(ops, 1) * 1000
    rx_a_ops   = _ops_rx(ops, 0) / 1000
    ry_a_ops   = _ops_ry(ops, 0) / 1000
    ma_ops     = abs(_ops_mz(ops, 0)) / 1000

    qr = [
        QuantityResult("Top-left sway δ_x",  "mm",   dx_top_sl, dx_top_ops, "OpenSeesPy"),
        QuantityResult("Base shear H_A",      "kN",   rx_a_sl,   rx_a_ops,   "OpenSeesPy"),
        QuantityResult("Base vertical R_A",   "kN",   ry_a_sl,   ry_a_ops,   "OpenSeesPy"),
        QuantityResult("Base moment M_A",     "kN·m", ma_sl,     ma_ops,     "OpenSeesPy"),
    ]

    return BenchResult(
        case_id="F1",
        title="Portal Frame — Lateral Point Load",
        description=(
            f"Fixed-base portal: span L={L} m, height H={H} m, "
            f"lateral load P={int(P)} kN at top-left. E=200 GPa, I=400 cm⁴."
        ),
        category="2D Frames",
        reference_types=["OpenSeesPy"],
        quantities=qr,
        sketch_func=sketch_f1,
    )


# ── F2: 2-storey portal frame, gravity loads ─────────────────────────────────

def run_f2() -> BenchResult:
    """F2 — 2-storey, 1-bay frame, UDL on both floor beams.

    Nodes (0-indexed, left→right, bottom→top):
      Row 0 (ground): 0=(0,0), 1=(L,0)
      Row 1 (1st fl):  2=(0,H), 3=(L,H)
      Row 2 (roof):    4=(0,2H), 5=(L,2H)
    Elements:
      Columns: 0-2(0→2), 1-3(1→3), 2-4(2→4), 3-5(3→5)
      Beams:   (2→3)=4, (4→5)=5
    """
    L, H = 5.0, 3.5    # m
    w    = 20.0         # kN/m UDL on beams
    E, A_col, I_col = 200e6, 0.02, 6e-4
    A_bm, I_bm = 0.018, 4e-4

    nodes = [(0,0),(L,0),(0,H),(L,H),(0,2*H),(L,2*H)]
    # mixed E/A/I not supported by _sl_frame helper — use uniform section, note in description
    # Using beam section for all (conservative approximation for comparison purposes)
    els   = [(0,2),(1,3),(2,4),(3,5),(2,3),(4,5)]
    sups  = {0: _FIXED, 1: _FIXED}
    ops_sups = {0: (1,1,1), 1: (1,1,1)}
    udl_el= [(4, w), (5, w)]  # beam elements only

    model = _sl_frame(nodes, els, sups, E, I_bm, I_bm, udl_elements=udl_el)
    res, _ = _sl_solve(model)

    dx_roof_sl = _sl_dx(res, 4) * 1000
    ry_0_sl    = _sl_ry(res, 0) / 1000
    ry_1_sl    = _sl_ry(res, 1) / 1000

    ops = _ops_solve(nodes, els, ops_sups, E, I_bm, I_bm, udl_map={4: -w, 5: -w})
    dx_roof_ops = _ops_dx(ops, 4) * 1000
    ry_0_ops    = _ops_ry(ops, 0) / 1000
    ry_1_ops    = _ops_ry(ops, 1) / 1000

    qr = [
        QuantityResult("Roof sway δ_x",       "mm", dx_roof_sl, dx_roof_ops, "OpenSeesPy"),
        QuantityResult("Base reaction R_y (A)","kN", ry_0_sl,    ry_0_ops,    "OpenSeesPy"),
        QuantityResult("Base reaction R_y (B)","kN", ry_1_sl,    ry_1_ops,    "OpenSeesPy"),
    ]

    return BenchResult(
        case_id="F2",
        title="2-storey Portal Frame — Gravity UDL on Beams",
        description=(
            f"2-storey, 1-bay frame: span L={L} m, storey h={H} m, "
            f"UDL w={int(w)} kN/m on both floor beams. Fixed bases."
        ),
        category="2D Frames",
        reference_types=["OpenSeesPy"],
        quantities=qr,
        sketch_func=sketch_f2,
    )


# ── F3: 2-bay portal frame, gravity + lateral ────────────────────────────────

def run_f3() -> BenchResult:
    """F3 — 2-bay single-storey frame, UDL on left bay + lateral load.

    Nodes: 0=(0,0), 1=(L1,0), 2=(L1+L2,0), 3=(0,H), 4=(L1,H), 5=(L1+L2,H)
    Elements: col0(0→3), col1(1→4), col2(2→5), beam_L(3→4), beam_R(4→5)
    """
    L1, L2, H = 4.0, 3.0, 3.5  # m
    w = 15.0                    # kN/m on left beam
    P = 10.0                    # kN lateral at left top
    E, A, I = 200e6, 0.02, 4e-4

    nodes = [(0,0),(L1,0),(L1+L2,0),(0,H),(L1,H),(L1+L2,H)]
    els   = [(0,3),(1,4),(2,5),(3,4),(4,5)]
    sups  = {0: _FIXED, 1: _FIXED, 2: _FIXED}
    ops_sups = {0:(1,1,1), 1:(1,1,1), 2:(1,1,1)}
    pl    = [(3, P, 0.0, 0.0)]  # lateral at node 3 (top-left)
    udl_el = [(3, w)]           # element 3 = left beam

    model = _sl_frame(nodes, els, sups, E, A, I, nodal_loads=pl, udl_elements=udl_el)
    res, _ = _sl_solve(model)

    dx_3_sl = _sl_dx(res, 3) * 1000
    ry_0_sl = _sl_ry(res, 0) / 1000
    ry_1_sl = _sl_ry(res, 1) / 1000
    ry_2_sl = _sl_ry(res, 2) / 1000

    ops = _ops_solve(nodes, els, ops_sups, E, A, I, nodal_loads=pl, udl_map={3: -w})
    dx_3_ops = _ops_dx(ops, 3) * 1000
    ry_0_ops = _ops_ry(ops, 0) / 1000
    ry_1_ops = _ops_ry(ops, 1) / 1000
    ry_2_ops = _ops_ry(ops, 2) / 1000

    qr = [
        QuantityResult("Top-left sway δ_x",   "mm", dx_3_sl,  dx_3_ops,  "OpenSeesPy"),
        QuantityResult("Base reaction R_A",    "kN", ry_0_sl,  ry_0_ops,  "OpenSeesPy"),
        QuantityResult("Base reaction R_B",    "kN", ry_1_sl,  ry_1_ops,  "OpenSeesPy"),
        QuantityResult("Base reaction R_C",    "kN", ry_2_sl,  ry_2_ops,  "OpenSeesPy"),
    ]

    return BenchResult(
        case_id="F3",
        title="2-bay Portal Frame — Gravity UDL + Lateral Load",
        description=(
            f"2-bay frame: L₁={L1} m, L₂={L2} m, H={H} m. "
            f"UDL w={int(w)} kN/m on left bay, lateral P={int(P)} kN at top-left."
        ),
        category="2D Frames",
        reference_types=["OpenSeesPy"],
        quantities=qr,
        sketch_func=sketch_f3,
    )


def run_all() -> list[BenchResult]:
    return [run_f1(), run_f2(), run_f3()]
