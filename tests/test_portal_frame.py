"""Test: symmetric single-bay portal frame under lateral load.

Geometry: pinned bases, rigid beam-column joints, h = L = 4 m, all members same EI.
Load: horizontal H = 10 000 N (rightward) at top-left joint (node 1) only.

Analytical results (slope-deflection + statics):
  R_0x = R_3x = -H/2          horizontal reactions (leftward)
  R_0y = -H*h/L = -H           left base (uplift)
  R_3y = +H*h/L = +H           right base (compression)
  Sway  delta = H*L^3 / (4*EI)  (single-joint load, pinned bases, h=L, same EI)
"""

import numpy as np

from core.node import Node
from core.material import Material
from core.section import Section
from core.support import Support, SupportType
from core.load import ElementLoad, LoadType, NodalLoad
from core.model import Model
from elements.frame_element import FrameElement
from solver.assembler import Assembler
from solver.linear_solver import LinearSolver


def _build_model():
    h = 4.0
    L = 4.0
    E = 200e9
    I = 50e-6
    A = 10e-3
    H = 10_000.0

    nodes = [
        Node(0, 0.0, 0.0),
        Node(1, 0.0, h),
        Node(2, L,   h),
        Node(3, L,   0.0),
    ]
    material = Material("Steel", E)
    section  = Section("Generic", A, I)

    elements = [
        FrameElement(0, nodes[0], nodes[1], material, section),
        FrameElement(1, nodes[1], nodes[2], material, section),
        FrameElement(2, nodes[2], nodes[3], material, section),
    ]

    supports = [
        Support(0, SupportType.PINNED),
        Support(3, SupportType.PINNED),
    ]

    nodal_loads = [NodalLoad(node_id=1, fx=H, fy=0.0, moment=0.0)]

    model = Model(
        nodes=nodes,
        elements=elements,
        supports=supports,
        nodal_loads=nodal_loads,
    )
    return model, elements, h, L, H, E * I


def _solve(model, elements):
    assembler = Assembler(model)
    K = assembler.global_stiffness_matrix(elements)
    F = assembler.global_force_vector(elements)
    return LinearSolver(model).solve(K, F)


def test_horizontal_reactions():
    """Both bases carry H/2 leftward by anti-symmetry."""
    model, elements, h, L, H, EI = _build_model()
    result = _solve(model, elements)
    R_0x = result.reactions[0]
    R_3x = result.reactions[9]
    assert abs(R_0x - (-H / 2)) / H < 0.001, f"R_0x={R_0x:.1f} expected {-H/2:.1f}"
    assert abs(R_3x - (-H / 2)) / H < 0.001, f"R_3x={R_3x:.1f} expected {-H/2:.1f}"


def test_vertical_reactions():
    """Overturning: uplift at windward base, compression at leeward base."""
    model, elements, h, L, H, EI = _build_model()
    result = _solve(model, elements)
    R_0y = result.reactions[1]
    R_3y = result.reactions[10]
    analytical = H * h / L
    assert abs(R_0y - (-analytical)) / analytical < 0.001, f"R_0y={R_0y:.1f} expected {-analytical:.1f}"
    assert abs(R_3y -   analytical ) / analytical < 0.001, f"R_3y={R_3y:.1f} expected {analytical:.1f}"


def test_global_equilibrium():
    """Sum of all reactions + applied loads must vanish."""
    model, elements, h, L, H, EI = _build_model()
    result = _solve(model, elements)
    R = result.reactions
    tol = 1e-6 * H
    assert abs(R[0] + R[9] + H) < tol, f"SFx={R[0]+R[9]+H:.2e}"
    assert abs(R[1] + R[10])    < tol, f"SFy={R[1]+R[10]:.2e}"


def test_sway_displacement():
    """Lateral sway matches slope-deflection formula HL^3/(4EI) for single-joint load."""
    model, elements, h, L, H, EI = _build_model()
    result = _solve(model, elements)
    delta_got      = result.displacements[3]
    delta_analytic = H * L**3 / (4 * EI)
    assert abs(delta_got - delta_analytic) / delta_analytic < 0.005, (
        f"Sway={delta_got:.6f} m expected {delta_analytic:.6f} m"
    )


# ---------------------------------------------------------------------------
# Gravity load case: symmetric UDL on beam
# ---------------------------------------------------------------------------

def _build_gravity_model():
    """Same geometry; UDL w on beam only (element 1, horizontal)."""
    h = 4.0
    L = 4.0
    E = 200e9
    I = 50e-6
    A = 10e-3
    w = 10_000.0   # N/m downward

    nodes = [
        Node(0, 0.0, 0.0),
        Node(1, 0.0, h),
        Node(2, L,   h),
        Node(3, L,   0.0),
    ]
    material = Material("Steel", E)
    section  = Section("Generic", A, I)

    elements = [
        FrameElement(0, nodes[0], nodes[1], material, section),
        FrameElement(1, nodes[1], nodes[2], material, section),
        FrameElement(2, nodes[2], nodes[3], material, section),
    ]

    supports = [
        Support(0, SupportType.PINNED),
        Support(3, SupportType.PINNED),
    ]

    element_loads = [ElementLoad(element_id=1, load_type=LoadType.UDL, magnitude=w)]

    model = Model(
        nodes=nodes,
        elements=elements,
        supports=supports,
        element_loads=element_loads,
    )
    return model, elements, L, w


def test_gravity_vertical_reactions():
    """Symmetric UDL: each pinned base carries wL/2 upward."""
    model, elements, L, w = _build_gravity_model()
    result = _solve(model, elements)
    R_0y = result.reactions[1]
    R_3y = result.reactions[10]
    analytical = w * L / 2   # 20 000 N
    for label, R in [("R_0y", R_0y), ("R_3y", R_3y)]:
        assert abs(R - analytical) / analytical < 0.001, (
            f"{label}={R:.1f} N, expected {analytical:.1f} N"
        )


def test_gravity_no_sway():
    """Symmetric gravity load produces negligible horizontal sway (<0.1 mm) at top joints.

    Analytically zero by symmetry; tolerance accommodates floating-point noise from
    the large axial-to-flexural stiffness ratio (EA/EI ~ 200).
    """
    model, elements, L, w = _build_gravity_model()
    result = _solve(model, elements)
    dx_left  = result.displacements[3]   # node 1, dx
    dx_right = result.displacements[6]   # node 2, dx
    tol = 1e-4   # 0.1 mm — zero to engineering precision
    assert abs(dx_left)  < tol, f"dx_left={dx_left:.2e} m (expected ~0)"
    assert abs(dx_right) < tol, f"dx_right={dx_right:.2e} m (expected ~0)"
