"""Test: SFD and BMD for simply supported beam with UDL.

Analytical reference:
  V(x) = w(L/2 - x)       [shear, zero at midspan, +wL/2 at left, -wL/2 at right]
  M(x) = wx(L - x) / 2    [moment, zero at ends, peak wL²/8 at midspan]
"""

import numpy as np
import pytest

from core.node import Node
from core.material import Material
from core.section import Section
from core.support import Support, SupportType
from core.load import ElementLoad, LoadType
from core.model import Model
from elements.frame_element import FrameElement
from solver.assembler import Assembler
from solver.linear_solver import LinearSolver
from solver.postprocessor import Postprocessor


def _build_model():
    L = 10.0       # m, total span
    E = 200e9      # Pa
    I = 60e-6      # m⁴
    A = 6.65e-3    # m²
    w = 10_000.0   # N/m, downward

    nodes = [Node(0, 0.0, 0.0), Node(1, L / 2, 0.0), Node(2, L, 0.0)]
    material = Material("Steel", E)
    section = Section("Generic", A, I)

    elements = [
        FrameElement(0, nodes[0], nodes[1], material, section),
        FrameElement(1, nodes[1], nodes[2], material, section),
    ]

    supports = [
        Support(0, SupportType.PINNED),
        Support(2, SupportType.ROLLER_X),
    ]

    element_loads = [
        ElementLoad(element_id=0, load_type=LoadType.UDL, magnitude=w),
        ElementLoad(element_id=1, load_type=LoadType.UDL, magnitude=w),
    ]

    model = Model(
        nodes=nodes,
        elements=elements,
        supports=supports,
        element_loads=element_loads,
    )
    return model, elements, L, w


def _solve(model, elements):
    assembler = Assembler(model)
    K = assembler.global_stiffness_matrix(elements)
    F = assembler.global_force_vector(elements)
    result = LinearSolver(model).solve(K, F)
    post = Postprocessor(elements, model.element_loads, result.displacements)
    return post.sfd_bmd(n_points=11)


def test_shear_diagram():
    """V(x) = w(L/2 - x) for the full span; check element 0 at 5 interior points."""
    model, elements, L, w = _build_model()
    sfd = _solve(model, elements)

    el0 = sfd[0]   # element 0: local x ∈ [0, L/2]
    tol = 1e-3 * w * L  # 0.1% of total load

    for xi, V_got in zip(el0.x, el0.V):
        x_global = xi                   # element 0 starts at x=0
        V_exact = w * (L / 2 - x_global)
        assert abs(V_got - V_exact) < tol, (
            f"V at x={xi:.2f}: got {V_got:.1f}, expected {V_exact:.1f}"
        )


def test_moment_diagram():
    """M(x) = wx(L-x)/2 for the full span; check element 0 at interior points."""
    model, elements, L, w = _build_model()
    sfd = _solve(model, elements)

    el0 = sfd[0]
    M_ref = w * L**2 / 8  # maximum moment at midspan (reference for tolerance)
    tol = 1e-3 * M_ref    # 0.1% of peak moment

    for xi, M_got in zip(el0.x, el0.M):
        x_global = xi
        M_exact = w * x_global * (L - x_global) / 2
        assert abs(M_got - M_exact) < tol, (
            f"M at x={xi:.2f}: got {M_got:.1f}, expected {M_exact:.1f}"
        )


def test_moment_diagram_element1():
    """Check element 1 (x from L/2 to L): M(ξ) = w(L/2+ξ)(L/2-ξ)/2."""
    model, elements, L, w = _build_model()
    sfd = _solve(model, elements)

    el1 = sfd[1]   # element 1: local ξ ∈ [0, L/2], global x = L/2 + ξ
    M_ref = w * L**2 / 8
    tol = 1e-3 * M_ref

    for xi, M_got in zip(el1.x, el1.M):
        x_global = L / 2 + xi
        M_exact = w * x_global * (L - x_global) / 2
        assert abs(M_got - M_exact) < tol, (
            f"M at global x={x_global:.2f}: got {M_got:.1f}, expected {M_exact:.1f}"
        )


def test_boundary_values():
    """V and M must be exact at the three key points: ends (V=±wL/2, M=0) and midspan (V=0, M=wL²/8)."""
    model, elements, L, w = _build_model()
    sfd = _solve(model, elements)

    tol_V = 1.0   # N
    tol_M = 1.0   # N·m

    # Left end: V = +wL/2, M = 0
    assert abs(sfd[0].V[0] - w * L / 2) < tol_V
    assert abs(sfd[0].M[0]) < tol_M

    # Midspan (right end of element 0 = left end of element 1): V ≈ 0, M = wL²/8
    assert abs(sfd[0].V[-1]) < tol_V
    assert abs(sfd[0].M[-1] - w * L**2 / 8) < tol_M

    # Right end: V = -wL/2, M = 0
    assert abs(sfd[1].V[-1] - (-w * L / 2)) < tol_V
    assert abs(sfd[1].M[-1]) < tol_M
