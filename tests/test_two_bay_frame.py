"""Test: single-story two-bay portal frame under gravity UDL on both beams.

Geometry (pinned bases, rigid joints, h = L = 4 m, all members same EI):

  node 1 --[el 1]-- node 2 --[el 2]-- node 3   ← top (y = h)
     |                  |                  |
   [el 0]            [el 3]             [el 4]
     |                  |                  |
  node 0              node 4            node 5   ← ground (y = 0), all PINNED

UDL w on both beams (elements 1 and 2).

Analytical (slope-deflection, h = L, same EI throughout):

  By symmetry: θ₂ = 0, θ₁ = -θ₃, no sway (δ = 0).

  Modified slope-deflection for left column (pinned base, near end = joint 1):
    M₁_col = (3EI/L) θ₁

  Left beam (UDL w, span L):
    M₁_beam = (4EI/L) θ₁ − wL²/12

  Joint 1 equilibrium → 7EI θ₁/L = wL²/12 → θ₁ = wL³/(84EI)

  End moments:
    M₁_col  = wL²/28     (column top)
    M₁_beam = −wL²/28    (beam left end)
    M₂_beam = +3wL²/28   (beam right end)

  Beam shear (ΣM about center joint, using r×F cross-product):
    V₁ = 3wL/7    (shear at outer joint, = R_outer)
    V₂ = 4wL/7    (shear at center joint, per beam)

  Vertical base reactions:
    R_0y = R_5y = 3wL/7          (outer supports)
    R_4y         = 2·V₂ = 8wL/7  (centre support, both beams contribute)

  Horizontal base reactions (ΣM about base for each column):
    R_0x = +wL/28  (rightward),  R_5x = −wL/28  (leftward),  R_4x = 0

  Note: ~0.35 % deviation from FEM due to column axial shortening (ignored
  in slope-deflection); tolerance is set to 0.5 %.
"""

import numpy as np

from core.node import Node
from core.material import Material
from core.section import Section
from core.support import Support, SupportType
from core.load import ElementLoad, LoadType
from core.model import Model
from elements.frame_element import FrameElement
from solver.assembler import Assembler
from solver.linear_solver import LinearSolver


def _build_model():
    h  = 4.0
    L  = 4.0
    E  = 200e9
    I  = 50e-6
    A  = 10e-3
    w  = 10_000.0   # N/m downward on both beams

    nodes = [
        Node(0, 0.0, 0.0),      # left  base  (pinned)
        Node(1, 0.0, h),        # left  top
        Node(2, L,   h),        # centre top
        Node(3, 2*L, h),        # right top
        Node(4, L,   0.0),      # centre base (pinned)
        Node(5, 2*L, 0.0),      # right  base (pinned)
    ]
    mat = Material("Steel", E)
    sec = Section("Generic", A, I)

    elements = [
        FrameElement(0, nodes[0], nodes[1], mat, sec),   # left  column
        FrameElement(1, nodes[1], nodes[2], mat, sec),   # left  beam
        FrameElement(2, nodes[2], nodes[3], mat, sec),   # right beam
        FrameElement(3, nodes[4], nodes[2], mat, sec),   # centre column
        FrameElement(4, nodes[5], nodes[3], mat, sec),   # right  column
    ]

    supports = [
        Support(0, SupportType.PINNED),
        Support(4, SupportType.PINNED),
        Support(5, SupportType.PINNED),
    ]

    element_loads = [
        ElementLoad(element_id=1, load_type=LoadType.UDL, magnitude=w),
        ElementLoad(element_id=2, load_type=LoadType.UDL, magnitude=w),
    ]

    model = Model(
        nodes=nodes,
        elements=elements,
        supports=supports,
        element_loads=element_loads,
    )
    return model, elements, h, L, w


def _solve(model, elements):
    asm = Assembler(model)
    K = asm.global_stiffness_matrix(elements)
    F = asm.global_force_vector(elements)
    return LinearSolver(model).solve(K, F)


def test_outer_vertical_reactions():
    """Outer bases each carry 3wL/7 (slope-deflection, h=L, same EI)."""
    model, elements, h, L, w = _build_model()
    result = _solve(model, elements)

    # node 0 → DOF 1 (dy);  node 5 → DOF 16 (dy)
    R_0y = result.reactions[1]
    R_5y = result.reactions[16]

    analytical = 3 * w * L / 7
    tol = 0.005   # 0.5 % — column axial shortening causes ~0.35 % deviation

    assert abs(R_0y - analytical) / analytical < tol, (
        f"R_0y = {R_0y:.1f} N, expected {analytical:.1f} N"
    )
    assert abs(R_5y - analytical) / analytical < tol, (
        f"R_5y = {R_5y:.1f} N, expected {analytical:.1f} N"
    )


def test_center_vertical_reaction():
    """Centre base carries 8wL/7 — larger than the two outer supports combined."""
    model, elements, h, L, w = _build_model()
    result = _solve(model, elements)

    # node 4 → DOF 13 (dy)
    R_4y = result.reactions[13]

    analytical = 8 * w * L / 7
    tol = 0.005   # 0.5 % — column axial shortening causes ~0.26 % deviation

    assert abs(R_4y - analytical) / analytical < tol, (
        f"R_4y = {R_4y:.1f} N, expected {analytical:.1f} N"
    )


def test_vertical_equilibrium():
    """Sum of all vertical reactions equals total applied load 2wL."""
    model, elements, h, L, w = _build_model()
    result = _solve(model, elements)

    R_0y = result.reactions[1]
    R_4y = result.reactions[13]
    R_5y = result.reactions[16]

    total_load = 2 * w * L
    tol = 1e-6 * total_load

    assert abs(R_0y + R_4y + R_5y - total_load) < tol, (
        f"SFy = {R_0y + R_4y + R_5y:.1f} N, expected {total_load:.1f} N"
    )


def test_horizontal_equilibrium():
    """No net horizontal force: outer column bases carry equal-and-opposite reactions."""
    model, elements, h, L, w = _build_model()
    result = _solve(model, elements)

    # node 0 → DOF 0;  node 4 → DOF 12;  node 5 → DOF 15
    R_0x = result.reactions[0]
    R_4x = result.reactions[12]
    R_5x = result.reactions[15]

    tol = 1e-6 * w * L

    assert abs(R_0x + R_4x + R_5x) < tol, (
        f"SFx = {R_0x + R_4x + R_5x:.2e} N (expected 0)"
    )
