"""Regression test: PIN element with UDL load.

Commit 12b173f fixed a crash where pin-release elements (PIN_LEFT / PIN_RIGHT)
carrying distributed loads (UDL/UVL) caused a matmul shape mismatch: the
transformation matrix was 5×5 (condensed for the pin) but fixed_end_forces()
always returns 6 entries.

Fix: full_transformation_matrix() (always 6×6, ignores pin flags) is used for
FEF transformation in the assembler.

This test ensures that pin-release elements with UDL do not crash and produce
statically admissible results.
"""

import pytest
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
from solver.postprocessor import Postprocessor


def _build_gerber_udl():
    """Gerber beam: fixed → pin_j → hinge → roller, UDL on left span.

       w = 1 (UDL on element 0)
       ↓↓↓↓↓↓↓↓↓
    ████████──────────────────────△
    | L=1  | pin   |  L=1          |
    Node 0        Node 1          Node 2
    (fixed)       (hinge)         (roller)
    """
    L = 1.0
    E = 1.0
    A = 1.0
    I = 1.0
    w = 1.0

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

    element_loads = [
        ElementLoad(element_id=0, load_type=LoadType.UDL, magnitude=w),
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
    el_results = post.compute()
    return result, el_results


# ═══════════════════════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════════════════════

def test_pin_udl_no_crash():
    """The solve completes without exception — the original crash is fixed."""
    model, elements, _, _ = _build_gerber_udl()
    result, el_results = _solve(model, elements)
    # If we get here, the assembler didn't crash on matmul shape mismatch
    assert result.displacements is not None
    assert len(el_results) == 2


def test_pin_udl_pin_release_moment_zero():
    """M_j of element 0 is zero — pin release on UDL-carrying element works."""
    model, elements, _, _ = _build_gerber_udl()
    _, el_results = _solve(model, elements)

    assert el_results[0].M_j == pytest.approx(0.0, abs=1e-10)


def test_pin_udl_right_span_internal_equilibrium():
    """Element 1 (right span, no load) has V_i = -V_j (forces on nodes,
    not internal shear).  Moment satisfies M_j = M_i + V_i * L."""
    model, elements, _, _ = _build_gerber_udl()
    _, el_results = _solve(model, elements)

    r1 = el_results[1]
    L  = 1.0

    # For an element with no distributed load:
    # V_i is upward force on node i, V_j is upward force on node j.
    # Vertical equilibrium of the element → V_i + V_j = 0
    assert r1.V_i + r1.V_j == pytest.approx(0.0, abs=1e-14)

    # The internal shear is V_i (upward on left face).
    # Moment at right end = moment at left end + V_i * L
    assert r1.M_j == pytest.approx(r1.M_i + r1.V_i * L, rel=1e-9)


def test_pin_udl_vertical_equilibrium():
    """ΣFy = 0 — total vertical reaction equals total applied UDL load."""
    model, elements, L, w = _build_gerber_udl()
    result, _ = _solve(model, elements)

    R_0y = result.reactions[0 * 3 + 1]  # node 0, dy
    R_2y = result.reactions[2 * 3 + 1]  # node 2, dy
    total_w = w * L  # UDL over left span only

    assert R_0y + R_2y == pytest.approx(total_w, rel=1e-9)


def test_pin_udl_moment_equilibrium():
    """ΣM about node 0 = 0 — moment equilibrium holds."""
    model, elements, L, w = _build_gerber_udl()
    result, _ = _solve(model, elements)

    R_0m = result.reactions[0 * 3 + 2]  # moment reaction at fixed end
    R_2y = result.reactions[2 * 3 + 1]  # roller reaction at node 2

    # UDL moment about node 0: w*L * (L/2) = w*L²/2
    udl_moment = w * L * (L / 2)
    # Roller at distance 2L
    roller_moment = R_2y * (2 * L)
    # Sum of moments about node 0 should be zero
    # R_0m (CCW positive) + roller_moment (CCW positive) - udl_moment (CW) = 0
    total_moment = R_0m + roller_moment - udl_moment

    assert total_moment == pytest.approx(0.0, abs=1e-9)


def test_pin_udl_fixed_end_has_moment():
    """The fixed end carries a non-zero moment (UDL on the pinned span transmits
    moment through the fixed support — the hinge only releases moment at node 1)."""
    model, elements, _, _ = _build_gerber_udl()
    _, el_results = _solve(model, elements)

    # Pin_j releases M at node 1, but the fixed end at node 0 still sees moment
    assert abs(el_results[0].M_i) > 1e-6  # non-zero moment at fixed end
    assert el_results[0].M_i < 0  # hogging at fixed end (negative M)
