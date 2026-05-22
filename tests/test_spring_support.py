"""Test: elastic spring support validated against analytical stiffness superposition.

Structure: fixed cantilever with vertical spring at free end.

          Fixed ──────────────── Node 1 (spring k_s, load P↓)
          Node 0        L=1m

Analytical (tip stiffness of cantilever = 3EI/L³):

  v_1       = -P / (3EI/L³ + k_s)
  R_0y      = K[v_0, v_1] * v_1 = -3EI/L³ * v_1

With E=I=L=P=1, k_s = 3 (= 3EI/L³, doubles effective stiffness):
  v_1       = -1 / (3 + 3) = -1/6 m
  R_0y      = -(-3) * (-1/6) = ... let me use equilibrium instead
  Spring F  = k_s * |v_1| = 3 * 1/6 = 1/2 N  (upward)
  R_0y      = P - spring_F = 1 - 1/2 = 1/2 N  (upward)

Additional check: rotational spring on a propped cantilever.
A fixed-roller beam with a rotational spring k_r at the roller end stiffens the
structure.  With no rotational spring the roller reaction is 3EI/L³ * v_roller = 0
(roller is pinned so v=0).  Adding k_r at the roller changes the moment at the
roller end: M_roller = k_r * theta_roller.  This lets us verify that the spring
adds stiffness to the theta DOF correctly.
"""

import pytest

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


# ── helpers ────────────────────────────────────────────────────────────────

def _cantilever_with_spring(k_s: float):
    """Cantilever (fixed at 0, free at 1) with vertical spring k_s at tip."""
    L = 1.0; E = 1.0; A = 1.0; I = 1.0; P = 1.0
    nodes = [Node(0, 0.0, 0.0), Node(1, L, 0.0)]
    mat = Material("unit", E)
    sec = Section("unit", A, I)
    elements = [FrameElement(0, nodes[0], nodes[1], mat, sec)]
    supports = [
        Support(0, SupportType.FIXED),
        Support(1, SupportType.FREE, spring_stiffness_y=k_s),
    ]
    model = Model(
        nodes=nodes,
        elements=elements,
        supports=supports,
        nodal_loads=[NodalLoad(1, fx=0.0, fy=-P, moment=0.0)],
    )
    return model, elements, L, E, I, P, k_s


def _solve(model, elements):
    assembler = Assembler(model)
    K = assembler.global_stiffness_matrix(elements)
    F = assembler.global_force_vector(elements)
    return LinearSolver(model).solve(K, F)


# ── tests ───────────────────────────────────────────────────────────────────

def test_spring_tip_deflection():
    """Tip deflection equals -P / (3EI/L³ + k_s)."""
    k_s = 3.0
    model, elements, L, E, I, P, k_s = _cantilever_with_spring(k_s)
    result = _solve(model, elements)

    v_tip = result.displacements[1 * 3 + 1]
    tip_stiffness = 3 * E * I / L**3
    analytical = -P / (tip_stiffness + k_s)

    assert v_tip == pytest.approx(analytical, rel=1e-6)


def test_no_spring_matches_cantilever():
    """With k_s=0 spring has no effect: deflection equals -PL³/3EI."""
    model, elements, L, E, I, P, _ = _cantilever_with_spring(k_s=0.0)
    result = _solve(model, elements)

    v_tip = result.displacements[1 * 3 + 1]
    assert v_tip == pytest.approx(-P * L**3 / (3 * E * I), rel=1e-6)


def test_spring_global_equilibrium():
    """R_0y + spring force = applied load P (global vertical equilibrium)."""
    k_s = 3.0
    model, elements, L, E, I, P, k_s = _cantilever_with_spring(k_s)
    result = _solve(model, elements)

    v_tip = result.displacements[1 * 3 + 1]
    R_0y = result.reactions[0 * 3 + 1]
    spring_force = k_s * (-v_tip)    # upward force exerted by spring

    assert R_0y + spring_force == pytest.approx(P, rel=1e-6)


def test_rotational_spring_stiffens_roller():
    """Rotational spring at roller end increases the moment there and reduces tip deflection.

    Propped cantilever (fixed at 0, roller at 1) + rotational spring k_r at roller.
    Without spring: M at roller = 0, roller reaction = 3EI/L³ * ... (standard propped cantilever).
    With spring: roller develops moment M_roller = k_r * theta_1; structure is stiffer.
    We verify that adding k_r > 0 reduces the midspan deflection versus k_r = 0.
    """
    L = 2.0; E = 200e9; A = 6.65e-3; I = 60e-6; P = 50_000.0

    def _build(k_r: float):
        nodes = [Node(0, 0.0, 0.0), Node(1, L / 2, 0.0), Node(2, L, 0.0)]
        mat = Material("Steel", E)
        sec = Section("W", A, I)
        elems = [
            FrameElement(0, nodes[0], nodes[1], mat, sec),
            FrameElement(1, nodes[1], nodes[2], mat, sec),
        ]
        supports = [
            Support(0, SupportType.FIXED),
            Support(2, SupportType.ROLLER_X, spring_stiffness_theta=k_r),
        ]
        m = Model(
            nodes=nodes, elements=elems, supports=supports,
            nodal_loads=[NodalLoad(1, fx=0.0, fy=-P, moment=0.0)],
        )
        return m, elems

    model_no_spring, elems_no = _build(k_r=0.0)
    model_sprung, elems_sp = _build(k_r=1e9)

    res_no = _solve(model_no_spring, elems_no)
    res_sp = _solve(model_sprung, elems_sp)

    v_mid_no = res_no.displacements[1 * 3 + 1]
    v_mid_sp = res_sp.displacements[1 * 3 + 1]

    # Stiffer support → smaller (less negative) midspan deflection
    assert v_mid_sp > v_mid_no
