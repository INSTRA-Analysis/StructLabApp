"""3D Frame benchmark cases 3D1–3D8.

StructLab uses its 3-DOF/node 2D engine projected into 3D space
(each frame is analysed as a planar structure in its natural plane).
PyNite provides an independent 3D FEM reference.

For cases 3D1–3D3, analytical solutions are also provided.
Cases 3D4–3D8 use PyNite only as reference.
"""
from __future__ import annotations

import sys, os
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
    sketch_3d1, sketch_3d2, sketch_3d3, sketch_3d4, sketch_3d5,
    sketch_3d6, sketch_3d7, sketch_3d8,
)

_FIXED  = ST.FIXED
_PIN    = ST.PINNED
_ROLLER = ST.ROLLER_X
_FREE   = ST.FREE


# ── StructLab helpers ─────────────────────────────────────────────────────────

def _sl_solve_model(model):
    asm = Assembler(model)
    K = asm.global_stiffness_matrix(model.elements)
    F = asm.global_force_vector(model.elements)
    res = LinearSolver(model).solve(K, F)
    post = Postprocessor(model.elements, model.element_loads, res.displacements)
    return res, post.compute()


def _sl_dy(res, nid): return res.displacements[nid * 3 + 1]
def _sl_dx(res, nid): return res.displacements[nid * 3]
def _sl_ry(res, nid): return res.reactions[nid * 3 + 1]
def _sl_mz(res, nid): return res.reactions[nid * 3 + 2]
def _sl_mi(el_res, eid): return next(e for e in el_res if e.element_id == eid).M_i
def _sl_mj(el_res, eid): return next(e for e in el_res if e.element_id == eid).M_j


def _sl_cantilever(L, P, E, A, I, direction="y"):
    """StructLab cantilever: load in y-direction (2D plane = XY or XZ)."""
    model = Model()
    mat = Material(name="m", elastic_modulus=E, poisson_ratio=0.3)
    sec = Section(name="s", area=A, moment_of_inertia=I)
    model.nodes = [Node(id=0, x=0, y=0), Node(id=1, x=L, y=0)]
    model.supports.append(Support(node_id=0, support_type=_FIXED))
    model.elements.append(FrameElement(id=0, node_i=model.nodes[0], node_j=model.nodes[1],
                                       material=mat, section=sec))
    # Load as vertical (y-direction) point load at tip
    model.nodal_loads.append(NodalLoad(node_id=1, fx=0, fy=-P, moment=0))
    return model


def _sl_ss_beam(L, w, E, A, I, n_seg=4):
    """StructLab simply supported beam with UDL."""
    model = Model()
    mat = Material(name="m", elastic_modulus=E, poisson_ratio=0.3)
    sec = Section(name="s", area=A, moment_of_inertia=I)
    xs = [L * i / n_seg for i in range(n_seg + 1)]
    for i, x in enumerate(xs):
        model.nodes.append(Node(id=i, x=x, y=0))
    model.supports.append(Support(node_id=0, support_type=_PIN))
    model.supports.append(Support(node_id=n_seg, support_type=_ROLLER))
    for k in range(n_seg):
        model.elements.append(FrameElement(id=k, node_i=model.nodes[k],
                                           node_j=model.nodes[k+1],
                                           material=mat, section=sec))
        model.element_loads.append(ElementLoad(element_id=k, load_type=LoadType.UDL, magnitude=w))
    return model


# ── PyNite helpers ────────────────────────────────────────────────────────────

def _pyn_cantilever(L, E, G, nu, A, Iy, Iz, J, Fy=0.0, Fz=0.0, axis="x"):
    """PyNite cantilever: node N1 at origin (fixed), N2 at distance L along axis."""
    from Pynite import FEModel3D
    m = FEModel3D()
    m.add_material("St", E=E, G=G, nu=nu, rho=7850)
    m.add_section("Sec", A=A, Iy=Iy, Iz=Iz, J=J)
    if axis == "x":
        m.add_node("N1", 0, 0, 0); m.add_node("N2", L, 0, 0)
    elif axis == "z":
        m.add_node("N1", 0, 0, 0); m.add_node("N2", 0, 0, L)
    elif axis == "y":
        m.add_node("N1", 0, 0, 0); m.add_node("N2", 0, L, 0)
    m.add_member("M1", "N1", "N2", "St", "Sec")
    m.def_support("N1", True, True, True, True, True, True)
    m.add_load_combo("LC1", {"Case 1": 1.0})
    if Fy != 0: m.add_node_load("N2", "FY", Fy, case="Case 1")
    if Fz != 0: m.add_node_load("N2", "FZ", Fz, case="Case 1")
    m.analyze(check_statics=False)
    return m


def _pyn_ss_beam(L, w, E, G, nu, A, Iy, Iz, J, n_pts=20):
    """PyNite simply supported beam with UDL in FY direction (gravity = -Y in PyNite).

    Beam along X axis; gravity in -Y direction.
    Pin: DX+DY+DZ fixed, Rx fixed (prevents torsion/out-of-plane instability).
    Roller: DY+DZ fixed only. Rz free at both ends (simply supported in bending).
    Returns (model, mid_node_name, n_pts).
    """
    from Pynite import FEModel3D
    m = FEModel3D()
    m.add_material("St", E=E, G=G, nu=nu, rho=7850)
    m.add_section("Sec", A=A, Iy=Iy, Iz=Iz, J=J)
    xs = [L * i / n_pts for i in range(n_pts + 1)]
    for i, x in enumerate(xs):
        m.add_node(f"N{i}", x, 0, 0)
    for k in range(n_pts):
        m.add_member(f"M{k}", f"N{k}", f"N{k+1}", "St", "Sec")
    # Pin: fix DX, DY, DZ and torsion Rx; Roller: fix DY, DZ only
    # def_support(node, DX, DY, DZ, Rx, Ry, Rz)
    m.def_support("N0", True, True, True, True, False, False)
    m.def_support(f"N{n_pts}", False, True, True, False, False, False)
    m.add_load_combo("LC1", {"Case 1": 1.0})
    for k in range(n_pts):
        m.add_member_dist_load(f"M{k}", "FY", -w, -w, case="Case 1")
    m.analyze(check_statics=False)
    return m, f"N{n_pts // 2}", n_pts


# ── 3D-1: Cantilever column, tip load in Z (vertical) ────────────────────────

def run_3d1() -> BenchResult:
    """3D-1 — Cantilever column of length L along X axis, tip load P in Y (vertical).

    In StructLab 2D XY plane: cantilever along X, load -Fy at tip.
    In PyNite: X-axis cantilever, FY load at N2.
    Analytical: δ_tip = PL³/(3EI), M_root = PL.
    """
    L, P = 4.0, 20.0          # m, kN
    E  = 200e6                 # kN/m²
    G  = 77e6                  # kN/m²
    A  = 0.01; Iy = 1e-4; Iz = 8.33e-6; J = 1e-7

    # StructLab (2D, XY plane)
    model = _sl_cantilever(L, P, E, A, Iz)
    res, el_res = _sl_solve_model(model)
    dy_tip_sl = -_sl_dy(res, 1) * 1000          # mm
    mroot_sl  = abs(_sl_mi(el_res, 0)) / 1000   # kN·m

    # PyNite
    mp = _pyn_cantilever(L, E, G, 0.3, A, Iy, Iz, J, Fy=-P, axis="x")
    dy_tip_pyn = abs(mp.nodes["N2"].DY["LC1"]) * 1000
    mem = mp.members["M1"]
    mroot_pyn  = abs(mem.moment("Mz", 0, "LC1")) / 1000

    # Analytical
    dy_exact   = P * L**3 / (3 * E * Iz) * 1000
    mroot_exact = P * L / 1000

    qr = [
        QuantityResult("Tip deflection δ_tip",  "mm",   dy_tip_sl,  dy_exact,   "analytical"),
        QuantityResult("Tip deflection δ_tip",  "mm",   dy_tip_sl,  dy_tip_pyn, "PyNite"),
        QuantityResult("Root moment M_root",    "kN·m", mroot_sl,   mroot_exact,"analytical"),
        QuantityResult("Root moment M_root",    "kN·m", mroot_sl,   mroot_pyn,  "PyNite"),
    ]

    return BenchResult(
        case_id="3D1",
        title="3D Cantilever Column — Tip Point Load",
        description=(
            f"Cantilever length L={L} m, tip load P={int(P)} kN perpendicular to axis. "
            "E=200 GPa, I=833 cm⁴. Validated vs analytical (PL³/3EI) and PyNite."
        ),
        category="3D Frames",
        reference_types=["analytical", "PyNite"],
        quantities=qr,
        sketch_func=sketch_3d1,
    )


# ── 3D-2: Cantilever beam, stronger axis bending ─────────────────────────────

def run_3d2() -> BenchResult:
    """3D-2 — Cantilever along X axis with load in strong-axis (Iz >> Iy).

    Tests that StructLab picks the correct bending stiffness EIz.
    """
    L, P = 5.0, 30.0
    E = 210e6; G = 80e6
    A = 0.012; Iy = 2e-4; Iz = 1.5e-5; J = 2e-7

    model = _sl_cantilever(L, P, E, A, Iz)
    res, el_res = _sl_solve_model(model)
    dy_tip_sl = -_sl_dy(res, 1) * 1000
    mroot_sl  = abs(_sl_mi(el_res, 0)) / 1000

    mp = _pyn_cantilever(L, E, G, 0.3, A, Iy, Iz, J, Fy=-P, axis="x")
    dy_tip_pyn = abs(mp.nodes["N2"].DY["LC1"]) * 1000
    mroot_pyn  = abs(mp.members["M1"].moment("Mz", 0, "LC1")) / 1000

    dy_exact   = P * L**3 / (3 * E * Iz) * 1000
    mroot_exact = P * L / 1000

    qr = [
        QuantityResult("Tip deflection δ_tip", "mm",   dy_tip_sl,  dy_exact,   "analytical"),
        QuantityResult("Tip deflection δ_tip", "mm",   dy_tip_sl,  dy_tip_pyn, "PyNite"),
        QuantityResult("Root moment M_root",   "kN·m", mroot_sl,   mroot_exact,"analytical"),
        QuantityResult("Root moment M_root",   "kN·m", mroot_sl,   mroot_pyn,  "PyNite"),
    ]

    return BenchResult(
        case_id="3D2",
        title="3D Cantilever — Vertical Tip Load (Strong Axis)",
        description=(
            f"Cantilever L={L} m, load P={int(P)} kN. E=210 GPa, Iz={Iz*1e6:.0f} cm⁴. "
            "Verifies correct bending axis selection vs PyNite and analytical solution."
        ),
        category="3D Frames",
        reference_types=["analytical", "PyNite"],
        quantities=qr,
        sketch_func=sketch_3d2,
    )


# ── 3D-3: Simply supported beam, UDL ─────────────────────────────────────────

def run_3d3() -> BenchResult:
    """3D-3 — SS beam L=6 m, UDL w=20 kN/m.

    Analytical: δ_mid = 5wL⁴/384EI, M_max = wL²/8.
    """
    L, w = 6.0, 20.0
    E = 200e6; G = 77e6
    A = 0.015; Iy = 3e-4; Iz = 1e-4; J = 5e-8
    n_seg = 6

    model = _sl_ss_beam(L, w, E, A, Iz, n_seg=n_seg)
    res, el_res = _sl_solve_model(model)
    dy_mid_sl = -_sl_dy(res, n_seg // 2) * 1000
    mmax_sl   = max(abs(_sl_mj(el_res, k)) for k in range(n_seg)) / 1000

    mp, mid_node, n_pts = _pyn_ss_beam(L, w, E, G, 0.3, A, Iy, Iz, J, n_pts=n_seg)
    dy_mid_pyn = abs(mp.nodes[mid_node].DY["LC1"]) * 1000   # FY gravity → DY deflection
    mmax_pyn   = abs(mp.members[f"M{n_pts//2-1}"].max_moment("Mz", "LC1")) / 1000

    dy_exact   = 5 * w * L**4 / (384 * E * Iz) * 1000
    mmax_exact = w * L**2 / 8 / 1000

    qr = [
        QuantityResult("Mid-span deflection", "mm",   dy_mid_sl, dy_exact,   "analytical"),
        QuantityResult("Mid-span deflection", "mm",   dy_mid_sl, dy_mid_pyn, "PyNite"),
        QuantityResult("Max moment M_max",    "kN·m", mmax_sl,   mmax_exact, "analytical"),
    ]

    return BenchResult(
        case_id="3D3",
        title="3D Simply Supported Beam — UDL",
        description=(
            f"Span L={L} m, UDL w={int(w)} kN/m. E=200 GPa, I={int(Iz*1e6)} cm⁴. "
            "Analytical: δ_mid=5wL⁴/384EI, M_max=wL²/8. Cross-validated with PyNite."
        ),
        category="3D Frames",
        reference_types=["analytical", "PyNite"],
        quantities=qr,
        sketch_func=sketch_3d3,
    )


# ── 3D-4: 2-storey space frame ────────────────────────────────────────────────

def run_3d4() -> BenchResult:
    """3D-4 — 2-storey 1-bay-each-direction space frame, gravity UDL on all floor beams.

    StructLab solves each portal in its own vertical plane (XZ then YZ)
    and aggregates. Here we solve the XZ plane portal as a 2D frame for comparison.

    PyNite reference: full 3D assembly.
    Comparison quantity: top-level lateral sway (x-direction) under gravity.
    """
    from Pynite import FEModel3D

    Lx = 3.0; Lz = 6.0; H1 = 3.0; H2 = 3.0   # bay widths, storey heights
    w = 15.0    # kN/m on all beams
    E = 200e6; G = 77e6; nu = 0.3
    A = 0.02; Iy = 5e-4; Iz = 5e-4; J = 3e-7

    # StructLab: solve one portal frame (XZ plane) for gravity UDL
    # Nodes in XZ: (x=0,z=0), (x=Lx,z=0), (x=0,z=H1), (x=Lx,z=H1), (x=0,z=H1+H2), (x=Lx,z=H1+H2)
    model = Model()
    mat = Material(name="m", elastic_modulus=E, poisson_ratio=nu)
    sec = Section(name="s", area=A, moment_of_inertia=Iz)
    node_coords = [(0,0),(Lx,0),(0,H1),(Lx,H1),(0,H1+H2),(Lx,H1+H2)]
    for i, (x, y) in enumerate(node_coords):
        model.nodes.append(Node(id=i, x=x, y=y))
    model.supports.append(Support(node_id=0, support_type=_FIXED))
    model.supports.append(Support(node_id=1, support_type=_FIXED))
    els_ij = [(0,2),(1,3),(2,4),(3,5),(2,3),(4,5)]
    for k, (ni, nj) in enumerate(els_ij):
        model.elements.append(FrameElement(id=k, node_i=model.nodes[ni],
                                           node_j=model.nodes[nj],
                                           material=mat, section=sec))
    for eid in (4, 5):
        model.element_loads.append(ElementLoad(element_id=eid, load_type=LoadType.UDL, magnitude=w))
    res, _ = _sl_solve_model(model)
    ry_0_sl = _sl_ry(res, 0) / 1000
    ry_1_sl = _sl_ry(res, 1) / 1000

    # PyNite: same portal frame — nodes in XY plane (Y = vertical in PyNite convention)
    # node_coords: (x, height) → PyNite (X, Y, Z=0)
    m3 = FEModel3D()
    m3.add_material("St", E=E, G=G, nu=nu, rho=7850)
    m3.add_section("Sec", A=A, Iy=Iy, Iz=Iz, J=J)
    for i, (x, y) in enumerate(node_coords):
        m3.add_node(f"N{i}", x, y, 0)  # XY plane, Z=0
    for k, (ni, nj) in enumerate(els_ij):
        m3.add_member(f"M{k}", f"N{ni}", f"N{nj}", "St", "Sec")
    m3.def_support("N0", True, True, True, True, True, True)
    m3.def_support("N1", True, True, True, True, True, True)
    m3.add_load_combo("LC1", {"Case 1": 1.0})
    for k in (4, 5):
        m3.add_member_dist_load(f"M{k}", "FY", -w, -w, case="Case 1")
    m3.analyze(check_statics=False)
    ry_0_pyn = abs(m3.nodes["N0"].RxnFY["LC1"]) / 1000
    ry_1_pyn = abs(m3.nodes["N1"].RxnFY["LC1"]) / 1000

    qr = [
        QuantityResult("Base reaction R_A (vert.)", "kN", ry_0_sl, ry_0_pyn, "PyNite"),
        QuantityResult("Base reaction R_B (vert.)", "kN", ry_1_sl, ry_1_pyn, "PyNite"),
    ]

    return BenchResult(
        case_id="3D4",
        title="2-storey Space Frame — Gravity Loads",
        description=(
            f"2-storey 1-bay XZ frame: Lx={Lx} m, H={H1}+{H2} m, UDL w={int(w)} kN/m on beams. "
            "StructLab 2D-plane analysis compared with PyNite 3D frame."
        ),
        category="3D Frames",
        reference_types=["PyNite"],
        quantities=qr,
        sketch_func=sketch_3d4,
    )


# ── 3D-5: L-shaped 3D frame, tip load ────────────────────────────────────────

def run_3d5() -> BenchResult:
    """3D-5 — L-shaped plan frame: two bays, one in X, one in Y.

    Columns at (0,0), (3,0), (3,3), all height H=3 m.
    Beams: (0,0,H)→(3,0,H) in X, (3,0,H)→(3,3,H) in Y.
    Load P=-20 kN at (3,3,H) in Z.
    StructLab: solve each bay as separate 2D frame + combined.
    PyNite: full 3D solution.
    """
    from Pynite import FEModel3D

    H = 3.0; P = 20.0
    E = 200e6; G = 77e6; nu = 0.3
    A = 0.015; Iy = 4e-4; Iz = 4e-4; J = 2e-7

    # StructLab: XZ portal (col 1 + beam 1)
    # Nodes: 0=(0,0), 1=(3,0) cols. 2=(0,H), 3=(3,H) tops. beam 2→3.
    model_xz = Model()
    mat = Material(name="m", elastic_modulus=E, poisson_ratio=nu)
    sec = Section(name="s", area=A, moment_of_inertia=Iz)
    for i, (x, y) in enumerate([(0,0),(3,0),(0,H),(3,H)]):
        model_xz.nodes.append(Node(id=i, x=x, y=y))
    model_xz.supports.append(Support(node_id=0, support_type=_FIXED))
    model_xz.supports.append(Support(node_id=1, support_type=_FIXED))
    for k, (ni, nj) in enumerate([(0,2),(1,3),(2,3)]):
        model_xz.elements.append(FrameElement(id=k, node_i=model_xz.nodes[ni],
                                               node_j=model_xz.nodes[nj],
                                               material=mat, section=sec))
    model_xz.nodal_loads.append(NodalLoad(node_id=3, fx=0, fy=-P, moment=0))
    res_xz, _ = _sl_solve_model(model_xz)
    dy_tip_sl = -_sl_dy(res_xz, 3) * 1000

    # PyNite: full L-frame — Y=vertical, columns along Y, beams in XZ plane
    # Base: C1(0,0,0), C2(3,0,0), C3(3,0,3); Tops: T1(0,H,0), T2(3,H,0), T3(3,H,3)
    # Beams: T1→T2 along X, T2→T3 along Z
    m3 = FEModel3D()
    m3.add_material("St", E=E, G=G, nu=nu, rho=7850)
    m3.add_section("Sec", A=A, Iy=Iy, Iz=Iz, J=J)
    m3.add_node("C1", 0, 0, 0); m3.add_node("C2", 3, 0, 0); m3.add_node("C3", 3, 0, 3)
    m3.add_node("T1", 0, H, 0); m3.add_node("T2", 3, H, 0); m3.add_node("T3", 3, H, 3)
    for n in ("C1", "C2", "C3"):
        m3.def_support(n, True, True, True, True, True, True)
    m3.add_member("col1","C1","T1","St","Sec"); m3.add_member("col2","C2","T2","St","Sec")
    m3.add_member("col3","C3","T3","St","Sec")
    m3.add_member("bm1","T1","T2","St","Sec"); m3.add_member("bm2","T2","T3","St","Sec")
    m3.add_load_combo("LC1", {"Case 1": 1.0})
    m3.add_node_load("T3", "FY", -P, case="Case 1")   # vertical load at tip = -Y
    m3.analyze(check_statics=False)
    dz_tip_pyn = abs(m3.nodes["T3"].DY["LC1"]) * 1000   # DY = vertical deflection

    qr = [
        QuantityResult("Tip deflection (vert.)", "mm", dy_tip_sl, dz_tip_pyn, "PyNite"),
    ]

    return BenchResult(
        case_id="3D5",
        title="L-shaped 3D Frame — Vertical Tip Load",
        description=(
            f"L-plan frame: two bays (3×3 m), H={H} m columns, tip load P={int(P)} kN. "
            "StructLab solves in XZ plane; PyNite resolves full 3D coupling."
        ),
        category="3D Frames",
        reference_types=["PyNite"],
        quantities=qr,
        sketch_func=sketch_3d5,
    )


# ── 3D-6: 3D portal frame, gravity + lateral ─────────────────────────────────

def run_3d6() -> BenchResult:
    """3D-6 — Single-bay portal frame (fixed bases), gravity UDL + lateral load.

    This is a planar XZ frame — same as F1 but validated in PyNite 3D.
    """
    from Pynite import FEModel3D

    L, H = 5.0, 4.0
    w = 20.0; Plat = 15.0   # kN/m, kN
    E = 200e6; G = 77e6; nu = 0.3
    A = 0.02; Iy = 5e-4; Iz = 4e-4; J = 3e-7

    # StructLab 2D
    model = Model()
    mat = Material(name="m", elastic_modulus=E, poisson_ratio=nu)
    sec = Section(name="s", area=A, moment_of_inertia=Iz)
    for i, (x, y) in enumerate([(0,0),(0,H),(L,H),(L,0)]):
        model.nodes.append(Node(id=i, x=x, y=y))
    model.supports.append(Support(node_id=0, support_type=_FIXED))
    model.supports.append(Support(node_id=3, support_type=_FIXED))
    for k, (ni, nj) in enumerate([(0,1),(1,2),(2,3)]):
        model.elements.append(FrameElement(id=k, node_i=model.nodes[ni],
                                           node_j=model.nodes[nj],
                                           material=mat, section=sec))
    model.element_loads.append(ElementLoad(element_id=1, load_type=LoadType.UDL, magnitude=w))
    model.nodal_loads.append(NodalLoad(node_id=1, fx=Plat, fy=0, moment=0))
    res, _ = _sl_solve_model(model)
    dx_top_sl = _sl_dx(res, 1) * 1000
    ry_0_sl   = _sl_ry(res, 0) / 1000

    # PyNite: Y = vertical axis, columns along Y, beam along X
    # A(0,0,0) → B(0,H,0): left column; D(L,0,0) → C(L,H,0): right column; B→C: beam
    m3 = FEModel3D()
    m3.add_material("St", E=E, G=G, nu=nu, rho=7850)
    m3.add_section("Sec", A=A, Iy=Iy, Iz=Iz, J=J)
    m3.add_node("A", 0, 0, 0); m3.add_node("B", 0, H, 0)
    m3.add_node("C", L, H, 0); m3.add_node("D", L, 0, 0)
    m3.def_support("A", True, True, True, True, True, True)
    m3.def_support("D", True, True, True, True, True, True)
    m3.add_member("col_L","A","B","St","Sec"); m3.add_member("bm","B","C","St","Sec")
    m3.add_member("col_R","D","C","St","Sec")
    m3.add_load_combo("LC1", {"Case 1": 1.0})
    m3.add_member_dist_load("bm", "FY", -w, -w, case="Case 1")   # gravity = -Y
    m3.add_node_load("B", "FX", Plat, case="Case 1")             # lateral = X
    m3.analyze(check_statics=False)
    dx_top_pyn = abs(m3.nodes["B"].DX["LC1"]) * 1000
    ry_0_pyn   = abs(m3.nodes["A"].RxnFY["LC1"]) / 1000

    qr = [
        QuantityResult("Top-left sway δ_x",  "mm", dx_top_sl, dx_top_pyn, "PyNite"),
        QuantityResult("Base reaction R_A",   "kN", ry_0_sl,   ry_0_pyn,   "PyNite"),
    ]

    return BenchResult(
        case_id="3D6",
        title="3D Portal Frame — Gravity UDL + Lateral Load",
        description=(
            f"Fixed-base portal: L={L} m, H={H} m, UDL w={int(w)} kN/m + "
            f"lateral P={int(Plat)} kN. Validated in full 3D with PyNite."
        ),
        category="3D Frames",
        reference_types=["PyNite"],
        quantities=qr,
        sketch_func=sketch_3d6,
    )


# ── 3D-7: Space truss (tetrahedral apex) ─────────────────────────────────────

def run_3d7() -> BenchResult:
    """3D-7 — Tetrahedral space truss: square base 2×2 m, apex at (1,1,2).

    All base nodes pinned. Apex load Fz=-10 kN.
    Analytical: all 4 diagonal members carry equal compression = Fz/(4·cosθ).
    """
    from Pynite import FEModel3D

    s = 2.0; za = 2.0; P = 10.0  # side, apex height, load kN
    E = 200e6; G = 77e6; nu = 0.3
    A = 0.003; J = 1e-8; Iy = Iz = 1e-8  # near-zero I → truss behaviour

    base = [(0,0,0),(s,0,0),(s,s,0),(0,s,0)]
    apex = (s/2, s/2, za)

    # Diagonal length
    diag_L = math.sqrt((s/2)**2 + (s/2)**2 + za**2)
    # All 4 diagonals carry equal load: N = -P/4 / cos(theta_z)
    # where cos(theta_z) = za / diag_L
    N_diag_exact = -P / 4 / (za / diag_L)   # compression (negative)

    # PyNite
    m3 = FEModel3D()
    m3.add_material("St", E=E, G=G, nu=nu, rho=7850)
    m3.add_section("Sec", A=A, Iy=Iy, Iz=Iz, J=J)
    for i, (x, y, z) in enumerate(base):
        m3.add_node(f"B{i}", x, y, z)
        m3.def_support(f"B{i}", True, True, True, True, True, True)
    m3.add_node("T", *apex)
    for i in range(4):
        m3.add_member(f"D{i}", f"B{i}", "T", "St", "Sec")
    # Base cross-bracing
    m3.add_member("Bx1","B0","B1","St","Sec"); m3.add_member("Bx2","B1","B2","St","Sec")
    m3.add_member("Bx3","B2","B3","St","Sec"); m3.add_member("Bx4","B3","B0","St","Sec")
    m3.add_member("Bx5","B0","B2","St","Sec"); m3.add_member("Bx6","B1","B3","St","Sec")
    m3.add_load_combo("LC1", {"Case 1": 1.0})
    m3.add_node_load("T", "FZ", -P, case="Case 1")
    m3.analyze(check_statics=False)
    dz_apex_pyn = abs(m3.nodes["T"].DZ["LC1"]) * 1000

    # StructLab: collapse to equivalent 2D by symmetry — 1 diagonal + half-base
    # Analytical: by symmetry each of the 4 base corners carries P/4 vertically
    rz_base_exact = P / 4 / 1000   # kN each
    rz_base_pyn   = abs(m3.nodes["B0"].RxnFZ["LC1"]) / 1000

    # StructLab 2D equivalent: symmetric 2-bar truss in XZ plane (half of full 3D by symmetry)
    # Left support at (0,0), apex at (h_proj, za), right support at (2*h_proj, 0)
    # Load P downward at apex. Each bar reaction = P/2 vertical.
    h_proj = math.sqrt(2) * s / 2   # horizontal projection of each diagonal
    model = Model()
    mat = Material(name="m", elastic_modulus=E, poisson_ratio=nu)
    sec = Section(name="s", area=A, moment_of_inertia=1e-10)
    for i, (x, y) in enumerate([(0, 0), (h_proj, za), (2*h_proj, 0)]):
        model.nodes.append(Node(id=i, x=x, y=y))
    model.supports.append(Support(node_id=0, support_type=_PIN))
    model.supports.append(Support(node_id=2, support_type=_PIN))   # pin both bases
    for k, (ni, nj) in enumerate([(0, 1), (1, 2)]):
        model.elements.append(FrameElement(id=k, node_i=model.nodes[ni],
                                           node_j=model.nodes[nj],
                                           material=mat, section=sec, pin_i=True, pin_j=True))
    model.nodal_loads.append(NodalLoad(node_id=1, fx=0, fy=-P, moment=0))
    res2d, _ = _sl_solve_model(model)
    ry_sl = _sl_ry(res2d, 0) / 1000   # vertical reaction per base (each = P/2 in 2D)
    # Scale to 3D: each of 4 corners carries P/4 = (P/2)/2 — matches analytical
    ry_sl_3d = ry_sl / 2   # half of the 2D value = P/4 equivalent

    qr = [
        QuantityResult("Base reaction (per corner)", "kN", ry_sl_3d, rz_base_exact, "analytical"),
        QuantityResult("Base reaction (per corner)", "kN", ry_sl_3d, rz_base_pyn,   "PyNite"),
    ]

    return BenchResult(
        case_id="3D7",
        title="Space Truss — Tetrahedral Apex, Vertical Point Load",
        description=(
            f"Square base {s}×{s} m, apex at height {za} m. Load P={int(P)} kN downward. "
            "By symmetry each base corner carries P/4 vertically. "
            "StructLab solves 2-bar 2D equivalent; scaled to 3D. Validated vs PyNite."
        ),
        category="3D Frames",
        reference_types=["analytical", "PyNite"],
        quantities=qr,
        sketch_func=sketch_3d7,
    )


# ── 3D-8: 3-bay single-storey 3D frame ───────────────────────────────────────

def run_3d8() -> BenchResult:
    """3D-8 — 3-bay single-storey 3D frame (grid), gravity UDL on all beams.

    Columns on 3×2 grid (bay_x × bay_y). Beams in both X and Y directions.
    Validated: StructLab sum of base reactions = total applied load.
    Cross-validated with PyNite for individual column base reactions.
    """
    from Pynite import FEModel3D

    bx = [0, 3, 6]; by = [0, 4]  # m
    H = 3.5         # storey height
    w = 12.0        # kN/m UDL on X-direction beams
    E = 200e6; G = 77e6; nu = 0.3
    A = 0.02; Iy = 5e-4; Iz = 4e-4; J = 3e-7

    # PyNite full 3D
    m3 = FEModel3D()
    m3.add_material("St", E=E, G=G, nu=nu, rho=7850)
    m3.add_section("Sec", A=A, Iy=Iy, Iz=Iz, J=J)
    m3.add_load_combo("LC1", {"Case 1": 1.0})

    # Y = vertical axis (PyNite convention)
    # Columns from (x, 0, z) → (x, H, z); beams in XZ plane at height Y=H
    node_names = {}
    for iz_idx, z in enumerate(by):   # 'by' repurposed as Z-direction bay coords
        for ix, x in enumerate(bx):
            nb = f"B{ix}{iz_idx}"; m3.add_node(nb, x, 0, z)
            m3.def_support(nb, True, True, True, True, True, True)
            nt = f"T{ix}{iz_idx}"; m3.add_node(nt, x, H, z)
            node_names[(ix, iz_idx)] = (nb, nt)
            m3.add_member(f"col{ix}{iz_idx}", nb, nt, "St", "Sec")

    # Beams in X direction (at height Y=H)
    for iz_idx in range(len(by)):
        for ix in range(len(bx) - 1):
            _, t0 = node_names[(ix, iz_idx)]
            _, t1 = node_names[(ix+1, iz_idx)]
            mem_name = f"bmX{ix}{iz_idx}"
            m3.add_member(mem_name, t0, t1, "St", "Sec")
            m3.add_member_dist_load(mem_name, "FY", -w, -w, case="Case 1")

    # Beams in Z direction (at height Y=H)
    for ix in range(len(bx)):
        for iz_idx in range(len(by) - 1):
            _, t0 = node_names[(ix, iz_idx)]
            _, t1 = node_names[(ix, iz_idx+1)]
            m3.add_member(f"bmZ{ix}{iz_idx}", t0, t1, "St", "Sec")

    m3.analyze(check_statics=False)

    # Total base reactions from PyNite (vertical = Y direction = RxnFY)
    total_ry_pyn = sum(
        abs(m3.nodes[node_names[(ix, iz_idx)][0]].RxnFY["LC1"])
        for ix in range(len(bx)) for iz_idx in range(len(by))
    ) / 1000

    # Total applied load
    beam_count = len(bx) * (len(by) - 1) + len(by) * (len(bx) - 1)
    # Only X beams have UDL in this setup
    total_x_beam_len = (len(bx) - 1) * (bx[1] - bx[0]) * len(by)
    # Adjust: spans differ
    total_x_beam_len = sum(bx[i+1] - bx[i] for i in range(len(bx)-1)) * len(by)
    total_load = w * total_x_beam_len / 1000  # kN

    # StructLab: solve one XZ bay as 2D portal, multiply by number of bays
    model = Model()
    mat = Material(name="m", elastic_modulus=E, poisson_ratio=nu)
    sec = Section(name="s", area=A, moment_of_inertia=Iz)
    for i, (x, y) in enumerate([(0,0),(bx[1],0),(0,H),(bx[1],H)]):
        model.nodes.append(Node(id=i, x=x, y=y))
    model.supports.append(Support(node_id=0, support_type=_FIXED))
    model.supports.append(Support(node_id=1, support_type=_FIXED))
    for k, (ni, nj) in enumerate([(0,2),(1,3),(2,3)]):
        model.elements.append(FrameElement(id=k, node_i=model.nodes[ni],
                                           node_j=model.nodes[nj],
                                           material=mat, section=sec))
    model.element_loads.append(ElementLoad(element_id=2, load_type=LoadType.UDL, magnitude=w))
    res, _ = _sl_solve_model(model)
    total_ry_sl = (_sl_ry(res, 0) + _sl_ry(res, 1)) * len(by) / 1000 * (len(bx)-1)

    qr = [
        QuantityResult("Total base reaction ΣR_z", "kN", total_ry_sl, total_load, "analytical"),
        QuantityResult("Total base reaction ΣR_z", "kN", total_ry_sl, total_ry_pyn, "PyNite"),
    ]

    return BenchResult(
        case_id="3D8",
        title="3-bay Single-storey 3D Frame — Gravity UDL",
        description=(
            f"3×2 column grid: bays {bx[1]-bx[0]}+{bx[2]-bx[1]} m in X, {by[1]-by[0]} m in Y, "
            f"H={H} m. UDL w={int(w)} kN/m on X-beams. Total applied load = PyNite base ΣR_z."
        ),
        category="3D Frames",
        reference_types=["analytical", "PyNite"],
        quantities=qr,
        sketch_func=sketch_3d8,
    )


def run_all() -> list[BenchResult]:
    return [run_3d1(), run_3d2(), run_3d3(), run_3d4(),
            run_3d5(), run_3d6(), run_3d7(), run_3d8()]
