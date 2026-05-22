"""Test: simple symmetric 3-node truss validated against method of joints.

Geometry (3-4-5 right triangles, h=4m, half-span=3m):

  node 2 (3, 4)
    /   \\
 [0]     [1]       ← rafters (length 5m each)
  /         \\
node 0 --- node 1   ← bottom chord [2] (length 6m)
(0,0)      (6,0)
PINNED    ROLLER_X

Load: P = 10 000 N downward at apex (node 2).

Method of joints (sin θ = 4/5, cos θ = 3/5):

  Reactions by symmetry:
    R_0y = R_1y = P/2 = 5 000 N  (upward)
    R_0x = R_1x = 0               (no horizontal loads)

  At apex (node 2) — ΣFy:
    2 · F_rafter · sin θ = P
    F_rafter = P / (2 sin θ) = 10 000 × 5/8 = 6 250 N  (COMPRESSION)

  At node 0 — ΣFx:
    F_chord = F_rafter · cos θ = 6 250 × 3/5 = 3 750 N  (TENSION)

Implementation note:
  TrussElement is a Phase 4 stub.  This test uses FrameElement directly with
  I = 1e-12 m⁴ (near-zero bending stiffness, ratio EI/EA·L² ≈ 10⁻¹³).
  Bending moments are negligible; axial forces match method of joints.
"""

import numpy as np

from core.node import Node
from core.material import Material
from core.section import Section
from core.support import Support, SupportType
from core.load import NodalLoad
from core.model import Model
from elements.frame_element import FrameElement
from solver.assembler import Assembler
from solver.linear_solver import LinearSolver
from solver.postprocessor import Postprocessor


P = 10_000.0   # N, downward at apex


def _build_model():
    E = 200e9
    A = 10e-3
    I = 1e-12   # near-zero: makes bending stiffness negligible vs axial

    nodes = [
        Node(0, 0.0, 0.0),   # left  support (pinned)
        Node(1, 6.0, 0.0),   # right support (roller, allows horizontal movement)
        Node(2, 3.0, 4.0),   # apex  (free, carries vertical load)
    ]
    mat = Material("Steel", E)
    sec = Section("Truss", A, I)

    elements = [
        FrameElement(0, nodes[0], nodes[2], mat, sec),   # left  rafter (length 5m)
        FrameElement(1, nodes[2], nodes[1], mat, sec),   # right rafter (length 5m)
        FrameElement(2, nodes[0], nodes[1], mat, sec),   # bottom chord  (length 6m)
    ]

    supports = [
        Support(0, SupportType.PINNED),     # left  base: restrains dx and dy
        Support(1, SupportType.ROLLER_X),   # right base: restrains dy only
    ]

    nodal_loads = [NodalLoad(node_id=2, fx=0.0, fy=-P, moment=0.0)]

    model = Model(
        nodes=nodes,
        elements=elements,
        supports=supports,
        nodal_loads=nodal_loads,
    )
    return model, elements


def _solve(model, elements):
    asm = Assembler(model)
    K = asm.global_stiffness_matrix(elements)
    F = asm.global_force_vector(elements)
    return LinearSolver(model).solve(K, F)


def test_support_reactions():
    """Symmetric load gives equal vertical reactions P/2 at each base."""
    model, elements = _build_model()
    result = _solve(model, elements)

    # node 0 PINNED → reactions[0]=Rx, reactions[1]=Ry
    # node 1 ROLLER_X → reactions[4]=Ry  (node 1, DOF base+1 = 3+1 = 4)
    R_0y = result.reactions[1]
    R_1y = result.reactions[4]
    analytical = P / 2   # 5 000 N

    tol = 0.001
    assert abs(R_0y - analytical) / analytical < tol, (
        f"R_0y = {R_0y:.1f} N, expected {analytical:.1f} N"
    )
    assert abs(R_1y - analytical) / analytical < tol, (
        f"R_1y = {R_1y:.1f} N, expected {analytical:.1f} N"
    )


def test_rafter_axial_force():
    """Each rafter carries 6 250 N compression (method of joints)."""
    model, elements = _build_model()
    result = _solve(model, elements)

    post = Postprocessor(elements, [], result.displacements)
    el_results = post.compute()

    F_rafter_left  = el_results[0].N_i   # element 0: left rafter
    F_rafter_right = el_results[1].N_i   # element 1: right rafter

    analytical = P / (2 * 4/5)   # 6 250 N compression → expect negative value
    tol = 0.001

    assert abs(abs(F_rafter_left)  - analytical) / analytical < tol, (
        f"Left rafter  |N| = {abs(F_rafter_left):.1f} N, expected {analytical:.1f} N"
    )
    assert abs(abs(F_rafter_right) - analytical) / analytical < tol, (
        f"Right rafter |N| = {abs(F_rafter_right):.1f} N, expected {analytical:.1f} N"
    )
    # Sign note: in the FEM element-force convention, N_i > 0 = compression
    # (the structure pushes the element end inward); this is opposite to the
    # structural convention (positive = tension) — a known postprocessor TODO.
    assert F_rafter_left  > 0, f"Left rafter should be compression (N_i > 0), got {F_rafter_left:.1f}"
    assert F_rafter_right > 0, f"Right rafter should be compression (N_i > 0), got {F_rafter_right:.1f}"


def test_bottom_chord_axial_force():
    """Bottom chord carries 3 750 N tension (method of joints)."""
    model, elements = _build_model()
    result = _solve(model, elements)

    post = Postprocessor(elements, [], result.displacements)
    el_results = post.compute()

    F_chord = el_results[2].N_i   # element 2: bottom chord
    analytical = P * 3 / (2 * 4)  # 3 750 N tension → N_i < 0 in FEM convention
    tol = 0.001

    assert abs(abs(F_chord) - analytical) / analytical < tol, (
        f"Chord |N| = {abs(F_chord):.1f} N, expected {analytical:.1f} N"
    )
    # FEM convention: N_i = EA/L × (u_i_local − u_j_local); tension gives N_i < 0
    assert F_chord < 0, f"Bottom chord should be tension (N_i < 0 in FEM convention), got {F_chord:.1f}"
