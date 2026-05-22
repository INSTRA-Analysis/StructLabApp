"""Test: BarElement validated against TrussElement and analytical results.

Structure: symmetric 3-node roof truss (same as test_simple_truss but using
BarElement instead of FrameElement with I≈0).

    Node 0 (pinned)         Node 1 (roller)
      (0,0)  ─────────────── (5,0)
                    ╲   ╱
                     ╲ ╱
                  Node 2 (free, apex)
                    (2.5, 2)

Members:
  bar 0: node 0 → node 2   (left rafter)
  bar 1: node 1 → node 2   (right rafter)
  bar 2: node 0 → node 1   (bottom chord)

Loads: P = 10 000 N downward at node 2 (apex).

Analytical (method of joints, P=10 kN, span 5 m, height 2 m):
  Member lengths: rafter L_r = √(2.5²+2²) = √10.25 ≈ 3.2016 m
                  chord  L_c = 5 m
  cos α = 2.5/L_r,  sin α = 2/L_r

  Reactions: R_0y = R_1y = P/2 = 5 000 N  (by symmetry)
             R_0x = 0,  R_1x ≠ 0 (roller free in x)

  Joint 2 equilibrium:
    ΣFy = 0: 2 * F_rafter * sin α = P → F_rafter = P/(2 sin α)
    F_rafter = 10000 / (2 * 2/L_r) = 5000*L_r/2 = 2500*L_r ≈ 8 003.9 N (compression)

  Joint 0 equilibrium (ΣFx = 0):
    F_chord = F_rafter * cos α = 2500*L_r * 2.5/L_r = 6 250 N (tension)

Note on sign convention (from test_simple_truss):
  N_i > 0 = compression in FrameElement convention for bar members.
  The bottom chord is in tension  → N_i < 0 in the recovered force vector.
  The rafter is in compression    → N_i > 0.
"""

import numpy as np
import pytest

from core.node import Node
from core.material import Material
from core.section import Section
from core.support import Support, SupportType
from core.load import NodalLoad
from core.model import Model
from elements.bar_element import BarElement
from solver.assembler import Assembler
from solver.linear_solver import LinearSolver
from solver.postprocessor import Postprocessor


# ── geometry constants ──────────────────────────────────────────────────────

L_SPAN = 5.0
H = 2.0
L_RAFTER = np.sqrt((L_SPAN / 2) ** 2 + H ** 2)   # ≈ 3.2016 m
P = 10_000.0
E = 200e9
A = 1e-3    # 1 000 mm²


# ── helpers ─────────────────────────────────────────────────────────────────

def _build_model():
    nodes = [
        Node(0, 0.0, 0.0),
        Node(1, L_SPAN, 0.0),
        Node(2, L_SPAN / 2, H),
    ]
    mat = Material("Steel", E)
    elements = [
        BarElement(0, nodes[0], nodes[2], mat, A),   # left rafter
        BarElement(1, nodes[1], nodes[2], mat, A),   # right rafter
        BarElement(2, nodes[0], nodes[1], mat, A),   # bottom chord
    ]
    supports = [
        Support(0, SupportType.PINNED),
        Support(1, SupportType.ROLLER_X),
    ]
    model = Model(
        nodes=nodes,
        elements=elements,
        supports=supports,
        nodal_loads=[NodalLoad(node_id=2, fx=0.0, fy=-P, moment=0.0)],
    )
    return model, elements


def _solve(model, elements):
    assembler = Assembler(model)
    K = assembler.global_stiffness_matrix(elements)
    F = assembler.global_force_vector(elements)
    result = LinearSolver(model).solve(K, F)
    post = Postprocessor(elements, model.element_loads, result.displacements)
    el_results = post.compute()
    return result, el_results


# ── tests ────────────────────────────────────────────────────────────────────

def test_bar_support_reactions():
    """Vertical reactions at pinned and roller nodes equal P/2 = 5 000 N each."""
    model, elements = _build_model()
    result, _ = _solve(model, elements)

    R_0y = result.reactions[0 * 3 + 1]
    R_1y = result.reactions[1 * 3 + 1]

    assert R_0y == pytest.approx(P / 2, rel=1e-4)
    assert R_1y == pytest.approx(P / 2, rel=1e-4)


def test_bar_rafter_compression():
    """Left rafter carries compression ≈ 2500 * L_rafter N (N_i > 0 = compression)."""
    model, elements = _build_model()
    _, el_results = _solve(model, elements)

    F_analytical = 2500.0 * L_RAFTER   # P * L_r / (2*H) = P*L_r/(2H)
    N_rafter = el_results[0].N_i

    assert N_rafter == pytest.approx(F_analytical, rel=1e-4)


def test_bar_chord_tension():
    """Bottom chord carries tension = 6 250 N (N_i < 0 = tension convention)."""
    model, elements = _build_model()
    _, el_results = _solve(model, elements)

    N_chord = el_results[2].N_i
    assert N_chord == pytest.approx(-6250.0, rel=1e-4)


def test_bar_zero_moments():
    """Bar elements carry no bending — M_i and M_j are zero for all members."""
    model, elements = _build_model()
    _, el_results = _solve(model, elements)

    for er in el_results:
        assert er.M_i == pytest.approx(0.0, abs=1e-6)
        assert er.M_j == pytest.approx(0.0, abs=1e-6)


def test_bar_theta_dofs_zero():
    """θ DOFs at all nodes are zero — bar-only nodes have no rotational stiffness."""
    model, elements = _build_model()
    result, _ = _solve(model, elements)

    for node_id in range(3):
        theta = result.displacements[node_id * 3 + 2]
        assert theta == pytest.approx(0.0, abs=1e-12)
