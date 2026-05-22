"""Test: propped cantilever with midspan point load validated against textbook formulas."""

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
    L = 6.0        # m
    E = 200e9      # Pa
    I = 60e-6      # m⁴
    A = 6.65e-3    # m²
    P = 50_000.0   # N (downward)

    # 3 nodes: fixed end, midspan, roller end
    nodes = [Node(0, 0.0, 0.0), Node(1, L / 2, 0.0), Node(2, L, 0.0)]
    material = Material("Steel", E)
    section = Section("Generic", A, I)

    elements = [
        FrameElement(0, nodes[0], nodes[1], material, section),
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


def test_roller_reaction():
    """Roller (prop) reaction must equal 5P/16."""
    model, elements, L, P = _build_model()

    assembler = Assembler(model)
    K = assembler.global_stiffness_matrix(elements)
    F = assembler.global_force_vector(elements)
    result = LinearSolver(model).solve(K, F)

    R_B = result.reactions[2 * 3 + 1]   # node 2, dy
    analytical = 5 * P / 16              # 15 625 N

    assert abs(R_B - analytical) / analytical < 0.001, (
        f"Prop reaction {R_B:.1f} N != analytical {analytical:.1f} N"
    )


def test_fixed_end_reaction():
    """Fixed-end vertical reaction must equal 11P/16."""
    model, elements, L, P = _build_model()

    assembler = Assembler(model)
    K = assembler.global_stiffness_matrix(elements)
    F = assembler.global_force_vector(elements)
    result = LinearSolver(model).solve(K, F)

    R_A = result.reactions[1]   # node 0, dy
    analytical = 11 * P / 16   # 34 375 N

    assert abs(R_A - analytical) / analytical < 0.001, (
        f"Fixed-end vertical reaction {R_A:.1f} N != analytical {analytical:.1f} N"
    )


def test_fixed_end_moment():
    """Fixed-end moment must equal -3PL/16 (hogging)."""
    model, elements, L, P = _build_model()

    assembler = Assembler(model)
    K = assembler.global_stiffness_matrix(elements)
    F = assembler.global_force_vector(elements)
    result = LinearSolver(model).solve(K, F)

    post = Postprocessor(elements, model.element_loads, result.displacements)
    el_results = post.compute()

    M_A = el_results[0].M_i           # moment at start of element 0
    analytical = -3 * P * L / 16      # -56 250 N·m

    assert abs(M_A - analytical) / abs(analytical) < 0.001, (
        f"Fixed-end moment {M_A:.1f} N·m != analytical {analytical:.1f} N·m"
    )
