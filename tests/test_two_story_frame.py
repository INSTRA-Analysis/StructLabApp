"""Test: two-story single-bay portal frame under lateral loads at each floor.

Geometry (pinned bases, rigid joints, h = L = 4 m, all members same EI):

  node 4 --[el 5]-- node 5   ← roof level  (y = 2h)
     |                  |
   [el 3]             [el 4]
     |                  |
  node 2 --[el 2]-- node 3   ← first floor (y = h)
     |                  |
   [el 0]             [el 1]
     |                  |
  node 0              node 1  ← ground (y = 0), both PINNED

Loads:
  H1 = 8 000 N rightward at node 2 (first floor, left joint)
  H2 = 4 000 N rightward at node 4 (roof, left joint)

Analytical (statics only — no slope-deflection needed):
  ΣFx = 0  →  R_0x + R_1x = -(H1 + H2)
  By anti-symmetry of horizontal loads on symmetric frame:
             R_0x = R_1x = -(H1 + H2) / 2 = -6 000 N

  ΣM about node 0 (CCW positive, r × F):
    R_1y × L  =  H1 × h  +  H2 × 2h
    R_1y      =  h(H1 + 2·H2) / L  =  4·(8000 + 8000)/4  =  16 000 N  (↑)
    R_0y      = -16 000 N  (↓, uplift)

  ΣFy = 0  →  R_0y + R_1y = 0  ✓
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


def _build_model():
    h  = 4.0
    L  = 4.0
    E  = 200e9
    I  = 50e-6
    A  = 10e-3
    H1 = 8_000.0   # N at first floor
    H2 = 4_000.0   # N at roof

    nodes = [
        Node(0, 0.0, 0.0),      # left  base
        Node(1, L,   0.0),      # right base
        Node(2, 0.0, h),        # left  first floor
        Node(3, L,   h),        # right first floor
        Node(4, 0.0, 2 * h),    # left  roof
        Node(5, L,   2 * h),    # right roof
    ]
    mat = Material("Steel", E)
    sec = Section("Generic", A, I)

    elements = [
        FrameElement(0, nodes[0], nodes[2], mat, sec),   # left  ground column
        FrameElement(1, nodes[1], nodes[3], mat, sec),   # right ground column
        FrameElement(2, nodes[2], nodes[3], mat, sec),   # first floor beam
        FrameElement(3, nodes[2], nodes[4], mat, sec),   # left  upper column
        FrameElement(4, nodes[3], nodes[5], mat, sec),   # right upper column
        FrameElement(5, nodes[4], nodes[5], mat, sec),   # roof beam
    ]

    supports = [
        Support(0, SupportType.PINNED),
        Support(1, SupportType.PINNED),
    ]

    nodal_loads = [
        NodalLoad(node_id=2, fx=H1, fy=0.0, moment=0.0),
        NodalLoad(node_id=4, fx=H2, fy=0.0, moment=0.0),
    ]

    model = Model(
        nodes=nodes,
        elements=elements,
        supports=supports,
        nodal_loads=nodal_loads,
    )
    return model, elements, h, L, H1, H2


def _solve(model, elements):
    asm = Assembler(model)
    K = asm.global_stiffness_matrix(elements)
    F = asm.global_force_vector(elements)
    return LinearSolver(model).solve(K, F)


def test_horizontal_base_reactions():
    """Both pinned bases carry (H1+H2)/2 leftward by frame anti-symmetry."""
    model, elements, h, L, H1, H2 = _build_model()
    result = _solve(model, elements)

    R_0x = result.reactions[0]   # node 0, dx DOF
    R_1x = result.reactions[3]   # node 1, dx DOF

    analytical = -(H1 + H2) / 2   # -6 000 N
    tol = 0.001                    # 0.1 % relative

    assert abs(R_0x - analytical) / abs(analytical) < tol, (
        f"R_0x = {R_0x:.1f} N, expected {analytical:.1f} N"
    )
    assert abs(R_1x - analytical) / abs(analytical) < tol, (
        f"R_1x = {R_1x:.1f} N, expected {analytical:.1f} N"
    )


def test_vertical_base_reactions():
    """Overturning moment sets vertical reactions: R_1y = h(H1+2·H2)/L (compression side)."""
    model, elements, h, L, H1, H2 = _build_model()
    result = _solve(model, elements)

    R_0y = result.reactions[1]   # node 0, dy DOF
    R_1y = result.reactions[4]   # node 1, dy DOF

    R_1y_analytic =  h * (H1 + 2 * H2) / L   # +16 000 N
    R_0y_analytic = -h * (H1 + 2 * H2) / L   # -16 000 N
    tol = 0.001

    assert abs(R_0y - R_0y_analytic) / abs(R_0y_analytic) < tol, (
        f"R_0y = {R_0y:.1f} N, expected {R_0y_analytic:.1f} N"
    )
    assert abs(R_1y - R_1y_analytic) / abs(R_1y_analytic) < tol, (
        f"R_1y = {R_1y:.1f} N, expected {R_1y_analytic:.1f} N"
    )


def test_global_equilibrium():
    """Sum of all reactions plus applied loads must vanish in x and y."""
    model, elements, h, L, H1, H2 = _build_model()
    result = _solve(model, elements)

    R = result.reactions
    total_H = H1 + H2
    tol = 1e-6 * total_H

    assert abs(R[0] + R[3] + total_H) < tol, (
        f"SFx = {R[0] + R[3] + total_H:.2e} N (expected 0)"
    )
    assert abs(R[1] + R[4]) < tol, (
        f"SFy = {R[1] + R[4]:.2e} N (expected 0)"
    )
