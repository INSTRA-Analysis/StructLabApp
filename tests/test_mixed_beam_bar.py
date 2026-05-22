"""Test: mixed FrameElement (beam) + BarElement in one model.

Structure: simply supported beam with a vertical bar prop at midspan.

    Node 0 (pinned)    Node 1 (midspan, free)    Node 2 (roller_x)
      (0,0) ── FrameEl 0 ── (L/2, 0) ── FrameEl 1 ── (L, 0)
                                  |
                             BarElement 2 (vertical prop, length h)
                                  |
                              Node 3 (pinned)
                              (L/2, -h)

Unit values: L=4, h=1, E=I=A=P=1.

Force-method (flexibility):
  f_beam = L³ / (48EI) = 64/48 = 4/3   midspan flexibility of simply supported beam
  f_bar  = h / (EA) = 1                 bar axial flexibility

  Bar redundant R (upward on beam, compression in bar):
    R = P * f_beam / (f_beam + f_bar) = (4/3) / (4/3 + 1) = 4/7 N

  Midspan deflection:
    v_mid = -R / k_bar = -R * f_bar = -4/7 m    (downward, negative in FEM)

  Support reactions:
    R_0y = R_2y = (P - R) / 2 = (3/7) / 2 = 3/14 N
    R_3y = R = 4/7 N        (upward, pin at bar anchor)
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
from elements.bar_element import BarElement
from solver.assembler import Assembler
from solver.linear_solver import LinearSolver
from solver.postprocessor import Postprocessor


# ── problem parameters ───────────────────────────────────────────────────────

L = 4.0
h = 1.0
E = 1.0; I_beam = 1.0; A = 1.0; P = 1.0

f_beam = L**3 / (48 * E * I_beam)    # 4/3
f_bar  = h / (E * A)                  # 1.0
R_BAR  = P * f_beam / (f_beam + f_bar)   # 4/7  bar force (compression)
V_MID  = -(R_BAR * f_bar)             # -4/7  midspan deflection (downward)
R_ENDS = (P - R_BAR) / 2              # 3/14  each beam support


# ── helpers ──────────────────────────────────────────────────────────────────

def _build():
    nodes = [
        Node(0, 0.0,   0.0),
        Node(1, L / 2, 0.0),
        Node(2, L,     0.0),
        Node(3, L / 2, -h),
    ]
    mat = Material("unit", E)
    sec = Section("unit", A, I_beam)
    elements = [
        FrameElement(0, nodes[0], nodes[1], mat, sec),   # left half-beam
        FrameElement(1, nodes[1], nodes[2], mat, sec),   # right half-beam
        BarElement(  2, nodes[1], nodes[3], mat, A),     # vertical prop
    ]
    supports = [
        Support(0, SupportType.PINNED),
        Support(2, SupportType.ROLLER_X),
        Support(3, SupportType.PINNED),
    ]
    model = Model(
        nodes=nodes,
        elements=elements,
        supports=supports,
        nodal_loads=[NodalLoad(node_id=1, fx=0.0, fy=-P, moment=0.0)],
    )
    return model, elements


def _solve(model, elements):
    assembler = Assembler(model)
    K = assembler.global_stiffness_matrix(elements)
    F = assembler.global_force_vector(elements)
    result = LinearSolver(model).solve(K, F)
    post = Postprocessor(elements, model.element_loads, result.displacements)
    return result, post.compute()


# ── tests ─────────────────────────────────────────────────────────────────────

def test_mixed_midspan_deflection():
    """Midspan deflection equals -R_bar·f_bar = -4/7 m."""
    model, elements = _build()
    result, _ = _solve(model, elements)

    v_mid = result.displacements[1 * 3 + 1]
    assert v_mid == pytest.approx(V_MID, rel=1e-5)


def test_mixed_beam_support_reactions():
    """Each beam support carries (P - R_bar)/2 = 3/14 N upward."""
    model, elements = _build()
    result, _ = _solve(model, elements)

    assert result.reactions[0 * 3 + 1] == pytest.approx(R_ENDS, rel=1e-5)
    assert result.reactions[2 * 3 + 1] == pytest.approx(R_ENDS, rel=1e-5)


def test_mixed_bar_anchor_reaction():
    """Bar anchor (node 3) carries upward reaction equal to bar force R_bar = 4/7 N."""
    model, elements = _build()
    result, _ = _solve(model, elements)

    R_3y = result.reactions[3 * 3 + 1]
    assert R_3y == pytest.approx(R_BAR, rel=1e-5)


def test_mixed_global_equilibrium():
    """Sum of all vertical support reactions equals applied load P."""
    model, elements = _build()
    result, _ = _solve(model, elements)

    total = (result.reactions[0 * 3 + 1]
             + result.reactions[2 * 3 + 1]
             + result.reactions[3 * 3 + 1])
    assert total == pytest.approx(P, rel=1e-5)


def test_mixed_bar_zero_moment():
    """Bar element carries no bending (M_i = M_j = 0)."""
    model, elements = _build()
    _, el_results = _solve(model, elements)

    bar = el_results[2]
    assert bar.M_i == pytest.approx(0.0, abs=1e-8)
    assert bar.M_j == pytest.approx(0.0, abs=1e-8)


def test_mixed_stiffer_than_simple_beam():
    """Bar prop reduces midspan deflection vs a plain simply supported beam."""
    model, elements = _build()
    result, _ = _solve(model, elements)

    v_mid  = result.displacements[1 * 3 + 1]
    v_bare = -P * L**3 / (48 * E * I_beam)   # -4/3 without prop
    assert v_mid > v_bare   # less negative → stiffer


def test_mixed_bar_node_theta_zero():
    """θ at bar-only anchor node 3 is zero (auto-eliminated DOF stays zero)."""
    model, elements = _build()
    result, _ = _solve(model, elements)

    theta_3 = result.displacements[3 * 3 + 2]
    assert theta_3 == pytest.approx(0.0, abs=1e-12)
