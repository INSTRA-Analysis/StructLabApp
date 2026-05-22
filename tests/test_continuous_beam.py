"""Test: two-span continuous beam with UDL validated against three-moment equation."""

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


def _build_model():
    L = 8.0       # m, each span
    E = 200e9     # Pa
    I = 100e-6    # m⁴
    A = 10e-3     # m²
    w = 20_000.0  # N/m (downward)

    nodes = [Node(0, 0.0, 0.0), Node(1, L, 0.0), Node(2, 2 * L, 0.0)]
    material = Material("Steel", E)
    section = Section("Generic", A, I)

    elements = [
        FrameElement(0, nodes[0], nodes[1], material, section),
        FrameElement(1, nodes[1], nodes[2], material, section),
    ]

    supports = [
        Support(0, SupportType.PINNED),
        Support(1, SupportType.ROLLER_X),
        Support(2, SupportType.ROLLER_X),
    ]

    # magnitude > 0 = downward load intensity; fem_loads returns upward equivalent nodal loads
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


def test_center_support_reaction():
    """Center reaction must equal 1.25*w*L (three-moment equation result)."""
    model, elements, L, w = _build_model()

    assembler = Assembler(model)
    K = assembler.global_stiffness_matrix(elements)
    F = assembler.global_force_vector(elements)

    result = LinearSolver(model).solve(K, F)

    # Node 1 dy DOF = index 4
    R_center = result.reactions[4]
    analytical = 1.25 * w * L  # 200 000 N upward

    assert abs(R_center - analytical) / analytical < 0.001, (
        f"Center reaction {R_center:.1f} N != analytical {analytical:.1f} N"
    )


def test_end_reactions():
    """End reactions must each equal 3*w*L/8."""
    model, elements, L, w = _build_model()

    assembler = Assembler(model)
    K = assembler.global_stiffness_matrix(elements)
    F = assembler.global_force_vector(elements)

    result = LinearSolver(model).solve(K, F)

    R_left  = result.reactions[1]   # node 0, dy
    R_right = result.reactions[7]   # node 2, dy
    analytical = 3 * w * L / 8     # 60 000 N

    for label, R in [("left", R_left), ("right", R_right)]:
        assert abs(R - analytical) / analytical < 0.001, (
            f"{label} reaction {R:.1f} N != analytical {analytical:.1f} N"
        )


def test_internal_moments():
    """Support moment at center node must equal w*L²/8 (hogging)."""
    model, elements, L, w = _build_model()

    assembler = Assembler(model)
    K = assembler.global_stiffness_matrix(elements)
    F = assembler.global_force_vector(elements)

    result = LinearSolver(model).solve(K, F)

    post = Postprocessor(elements, model.element_loads, result.displacements)
    el_results = post.compute()

    # M at right end of element 0 (= center support) should be -wL²/8 (hogging)
    M_center = el_results[0].M_j
    analytical = -w * L**2 / 8   # -160 000 N·m

    assert abs(M_center - analytical) / abs(analytical) < 0.001, (
        f"Center moment {M_center:.1f} N·m != analytical {analytical:.1f} N·m"
    )
