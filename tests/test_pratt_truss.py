"""Test: Pratt truss validated against method of joints.

6-node, 9-member simply supported Pratt truss.  An asymmetric single-joint
load exercises non-zero forces in the Pratt diagonal (tension) and the Pratt
vertical (compression), confirming the Pratt-truss characteristic.

Geometry  (panel width L = 2 m, height H = 2 m, 45-degree end posts):

    N4(2,2)----N5(4,2)        top chord
   /  |                  \
  /   |                   \
N0   N1(2,0)   N2(4,0)   N3(6,0)
(0,0)                      (6,0)
PINNED                  ROLLER_X

Members  (9 - statically determinate: 2x6 - 3 reactions = 9 free DOF):
  el 0: N0->N1   bottom chord left    (tension  under this load)
  el 1: N1->N2   bottom chord middle  (tension)
  el 2: N2->N3   bottom chord right   (tension)
  el 3: N4->N5   top chord            (compression)
  el 4: N0->N4   left end post  45    (compression)
  el 5: N3->N5   right end post 45    (compression)
  el 6: N1->N4   left vertical        (compression - Pratt)
  el 7: N2->N5   right vertical       (zero-force)
  el 8: N1->N5   Pratt diagonal       (tension - Pratt)

Load: P = 10 000 N downward at N4 only (asymmetric, to force non-zero diagonal/vertical).

Method of joints (lengths: end posts = 2*sqrt(2) m, chords/verticals = 2 m):

  Global equilibrium (moment about N0):
    R_3y = P * 2 / 6 = P/3
    R_0y = P - P/3  = 2P/3

  Member forces:
    el 0  N0-N1 tension      |N| = 2P/3
    el 6  N1-N4 compression  |N| = P/3   <- Pratt vertical
    el 8  N1-N5 tension      |N| = P*sqrt(2)/3  <- Pratt diagonal

FEM sign convention (N_i > 0 = compression, N_i < 0 = tension).
"""

import math

import numpy as np

from core.load import NodalLoad
from core.material import Material
from core.model import Model
from core.node import Node
from core.support import Support, SupportType
from elements.truss_element import TrussElement
from solver.assembler import Assembler
from solver.linear_solver import LinearSolver
from solver.postprocessor import Postprocessor


P = 10_000.0   # N, applied downward at N4


def _build_model():
    E = 200e9
    A = 10e-3

    nodes = [
        Node(0, 0.0, 0.0),
        Node(1, 2.0, 0.0),
        Node(2, 4.0, 0.0),
        Node(3, 6.0, 0.0),
        Node(4, 2.0, 2.0),
        Node(5, 4.0, 2.0),
    ]
    mat = Material("Steel", E)

    elements = [
        TrussElement(0, nodes[0], nodes[1], mat, A),
        TrussElement(1, nodes[1], nodes[2], mat, A),
        TrussElement(2, nodes[2], nodes[3], mat, A),
        TrussElement(3, nodes[4], nodes[5], mat, A),
        TrussElement(4, nodes[0], nodes[4], mat, A),
        TrussElement(5, nodes[3], nodes[5], mat, A),
        TrussElement(6, nodes[1], nodes[4], mat, A),
        TrussElement(7, nodes[2], nodes[5], mat, A),
        TrussElement(8, nodes[1], nodes[5], mat, A),
    ]

    supports = [
        Support(0, SupportType.PINNED),
        Support(3, SupportType.ROLLER_X),
    ]

    nodal_loads = [NodalLoad(node_id=4, fx=0.0, fy=-P, moment=0.0)]

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


def _element_results(model, elements):
    result = _solve(model, elements)
    post = Postprocessor(elements, [], result.displacements)
    return result, post.compute()


def test_support_reactions():
    """R_0y = 2P/3 and R_3y = P/3 by moment equilibrium."""
    model, elements = _build_model()
    result = _solve(model, elements)

    R_0y = result.reactions[1]       # node 0, DOF 0*3+1 = 1
    R_3y = result.reactions[10]      # node 3, DOF 3*3+1 = 10

    tol = 0.001
    assert abs(R_0y - 2 * P / 3) / (2 * P / 3) < tol, (
        f"R_0y = {R_0y:.1f} N, expected {2*P/3:.1f} N"
    )
    assert abs(R_3y - P / 3) / (P / 3) < tol, (
        f"R_3y = {R_3y:.1f} N, expected {P/3:.1f} N"
    )


def test_bottom_chord_tension():
    """el 0 (N0-N1) tension, magnitude 2P/3 (N_i < 0 in FEM convention)."""
    model, elements = _build_model()
    _, er = _element_results(model, elements)

    N_01 = er[0].N_i
    expected = 2 * P / 3

    tol = 0.001
    assert N_01 < 0, f"N0-N1 should be tension (N_i < 0), got {N_01:.1f}"
    assert abs(abs(N_01) - expected) / expected < tol, (
        f"|N_01| = {abs(N_01):.1f} N, expected {expected:.1f} N"
    )


def test_pratt_vertical_compression():
    """el 6 (N1-N4) compression P/3 - Pratt characteristic: verticals in compression."""
    model, elements = _build_model()
    _, er = _element_results(model, elements)

    N_14 = er[6].N_i
    expected = P / 3

    tol = 0.001
    assert N_14 > 0, f"N1-N4 should be compression (N_i > 0), got {N_14:.1f}"
    assert abs(N_14 - expected) / expected < tol, (
        f"N_14 = {N_14:.1f} N, expected {expected:.1f} N"
    )


def test_pratt_diagonal_tension():
    """el 8 (N1-N5) tension P*sqrt(2)/3 - Pratt characteristic: diagonals in tension."""
    model, elements = _build_model()
    _, er = _element_results(model, elements)

    N_15 = er[8].N_i
    expected = P * math.sqrt(2) / 3

    tol = 0.001
    assert N_15 < 0, f"N1-N5 should be tension (N_i < 0), got {N_15:.1f}"
    assert abs(abs(N_15) - expected) / expected < tol, (
        f"|N_15| = {abs(N_15):.1f} N, expected {expected:.1f} N"
    )
