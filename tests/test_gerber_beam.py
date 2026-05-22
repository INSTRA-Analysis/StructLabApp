"""Test: Gerber beam (internal hinge) validated against statics.

Structure: fixed support → element 0 (pin_j) → internal hinge → element 1 → roller
           |←────── L ──────→|                              |←── L ──→|
           Node 0 (fixed)    Node 1 (hinge, load P↓)       Node 2 (roller)

With the hinge at node 1:
  - element 0 has pin_j=True → M_j(el0) = 0
  - equilibrium at θ_1 forces M_i(el1) = 0 automatically
  - right span (el1) carries zero internal forces (no load, M=0 at both ends)
  - structure reduces to: cantilever (el0) with tip load P

Analytical results (cantilever, L=1, EI=1, P=1):
  v_1       = -PL³ / (3EI) = -1/3 m
  R_0y      = +P            = +1 N  (upward)
  R_0_moment= +PL           = +1 N·m (CCW reaction, stored in reactions[2])
  R_2y      = 0             (roller carries nothing)
  M_i(el0)  = -PL           = -1 N·m (hogging, negative in sagging-positive convention)
  M_j(el0)  = 0             (pin release)
  M_i(el1)  = 0             (Gerber hinge condition, enforced by equilibrium)
"""

import pytest
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


def _build_model():
    L = 1.0   # m  (each span)
    E = 1.0   # N/m² (normalised)
    A = 1.0   # m²
    I = 1.0   # m⁴
    P = 1.0   # N

    nodes = [Node(0, 0.0, 0.0), Node(1, L, 0.0), Node(2, 2 * L, 0.0)]
    material = Material("unit", E)
    section = Section("unit", A, I)

    elements = [
        FrameElement(0, nodes[0], nodes[1], material, section, pin_j=True),
        FrameElement(1, nodes[1], nodes[2], material, section),
    ]

    supports = [
        Support(0, SupportType.FIXED),
        Support(2, SupportType.ROLLER_X),
    ]

    nodal_loads = [NodalLoad(node_id=1, fx=0.0, fy=-P, moment=0.0)]

    model = Model(
        nodes=nodes,
        elements=elements,
        supports=supports,
        nodal_loads=nodal_loads,
    )
    return model, elements, L, P


def _solve(model, elements):
    assembler = Assembler(model)
    K = assembler.global_stiffness_matrix(elements)
    F = assembler.global_force_vector(elements)
    result = LinearSolver(model).solve(K, F)
    post = Postprocessor(elements, model.element_loads, result.displacements)
    el_results = post.compute()
    return result, el_results


def test_hinge_deflection():
    """Vertical displacement at hinge equals cantilever tip deflection PL³/3EI."""
    model, elements, L, P = _build_model()
    result, _ = _solve(model, elements)

    v1 = result.displacements[1 * 3 + 1]  # node 1, dy DOF
    analytical = -P * L**3 / (3 * 1.0)    # E=I=1

    assert v1 == pytest.approx(analytical, rel=1e-6)


def test_fixed_support_reactions():
    """Fixed support carries full vertical load P and moment PL (CCW)."""
    model, elements, L, P = _build_model()
    result, _ = _solve(model, elements)

    R_0y = result.reactions[0 * 3 + 1]
    R_0m = result.reactions[0 * 3 + 2]

    assert R_0y == pytest.approx(P, rel=1e-6)
    assert R_0m == pytest.approx(P * L, rel=1e-6)


def test_roller_carries_zero():
    """Roller at node 2 has zero vertical reaction (right span is unloaded)."""
    model, elements, L, P = _build_model()
    result, _ = _solve(model, elements)

    R_2y = result.reactions[2 * 3 + 1]
    assert R_2y == pytest.approx(0.0, abs=1e-10)


def test_pin_release_moment_zero():
    """M_j of element 0 is zero — the pin release is working."""
    model, elements, L, P = _build_model()
    _, el_results = _solve(model, elements)

    assert el_results[0].M_j == pytest.approx(0.0, abs=1e-10)


def test_gerber_hinge_condition():
    """M_i of element 1 is zero — moment equilibrium at the hinge is satisfied."""
    model, elements, L, P = _build_model()
    _, el_results = _solve(model, elements)

    assert el_results[1].M_i == pytest.approx(0.0, abs=1e-10)


def test_fixed_end_moment_hogging():
    """M_i of element 0 equals -PL (hogging, negative in sagging-positive convention)."""
    model, elements, L, P = _build_model()
    _, el_results = _solve(model, elements)

    assert el_results[0].M_i == pytest.approx(-P * L, rel=1e-6)
