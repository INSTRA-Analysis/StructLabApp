"""3D validation tests: cantilever beam with tip load, torsion, and frame."""

import numpy as np
import pytest

from core.node import Node
from core.material import Material
from core.section import Section
from core.support import Support, SupportType
from core.load import NodalLoad, ElementLoad, LoadType, LoadDirection
from core.model import Model
from elements.frame_element import FrameElement
from solver.assembler import Assembler
from solver.linear_solver import LinearSolver
from solver.postprocessor import Postprocessor


# ── shared material ─────────────────────────────────────────────────────────

@pytest.fixture
def steel() -> Material:
    return Material(name="S355", elastic_modulus=210e9, poisson_ratio=0.3)


@pytest.fixture
def section() -> Section:
    # IPE 300 equivalent: strong axis I_z for bending in xy-plane,
    # weak axis I_y for bending in xz-plane.
    return Section(name="IPE300", area=5.38e-3,
                   moment_of_inertia=83.6e-6,  # I_z (strong)
                   I_y=6.04e-6,                # I_y (weak)
                   J=0.20e-6)                  # torsion


# ═══════════════════════════════════════════════════════════════════════════════
#  Cantilever: tip load in Z  (weak-axis bending)
# ═══════════════════════════════════════════════════════════════════════════════

def test_cantilever_tip_load_z(steel: Material, section: Section) -> None:
    """Cantilever (along X) with tip force in +Z → bending about Y in XZ plane.

    Analytical: δ_z = P L³ / (3 E I_z)   (strong-axis, vertical)
    """
    L = 4.0
    P = 1000.0  # N

    n0 = Node(id=0, x=0, y=0, z=0)
    n1 = Node(id=1, x=L, y=0, z=0)
    n0.z = 1e-12  # force 3D mode

    model = Model(
        nodes=[n0, n1],
        supports=[Support(node_id=0, support_type=SupportType.FIXED)],
        nodal_loads=[NodalLoad(node_id=1, fz=P)],
    )
    assert model.is_3d

    el = FrameElement(id=0, node_i=n0, node_j=n1, material=steel, section=section)
    model.elements = [el]

    assembler = Assembler(model)
    K = assembler.global_stiffness_matrix([el])
    F = assembler.global_force_vector([el])

    solver = LinearSolver(model)
    result = solver.solve(K, F)

    E = steel.elastic_modulus
    Iz = section.I_z
    delta_expected = P * L ** 3 / (3 * E * Iz)

    # Node 1, DOF 2 = dz  (dofs_per_node=6: base=6, +2 = 8)
    dz_idx = n1.dof_indices(dofs_per_node=6)[2]
    delta_computed = result.displacements[dz_idx]

    assert delta_computed == pytest.approx(delta_expected, rel=0.001)


# ═══════════════════════════════════════════════════════════════════════════════
#  Cantilever: tip load in Y  (horizontal, weak-axis bending in XY plane)
# ═══════════════════════════════════════════════════════════════════════════════

def test_cantilever_tip_load_y_3d(steel: Material, section: Section) -> None:
    """Cantilever with tip force in Y, solved with 6-DOF 3D engine.

    Analytical: δ_y = P L³ / (3 E I_z)
    """
    L = 3.0
    P = -5000.0  # N downward

    n0 = Node(id=0, x=0, y=0, z=0)
    n1 = Node(id=1, x=L, y=0, z=0)
    n0.z = 1e-12  # force 3D mode

    model = Model(
        nodes=[n0, n1],
        supports=[Support(node_id=0, support_type=SupportType.FIXED)],
        nodal_loads=[NodalLoad(node_id=1, fy=P)],
    )
    assert model.is_3d

    el = FrameElement(id=0, node_i=n0, node_j=n1, material=steel, section=section)
    model.elements = [el]

    assembler = Assembler(model)
    K = assembler.global_stiffness_matrix([el])
    F = assembler.global_force_vector([el])

    solver = LinearSolver(model)
    result = solver.solve(K, F)

    E = steel.elastic_modulus
    Iy = section.I_y
    delta_expected = abs(P) * L ** 3 / (3 * E * Iy)

    dy_idx = n1.dof_indices(dofs_per_node=6)[1]  # dy at node 1
    delta_computed = abs(result.displacements[dy_idx])
    assert delta_computed == pytest.approx(delta_expected, rel=0.001)


# ═══════════════════════════════════════════════════════════════════════════════
#  Cantilever: torsion
# ═══════════════════════════════════════════════════════════════════════════════

def test_cantilever_torsion(steel: Material, section: Section) -> None:
    """Cantilever with torque at tip → twist about X axis.

    Analytical: θ_x = T L / (G J)
    """
    L = 2.0
    T = 100.0  # N·m

    n0 = Node(id=0, x=0, y=0, z=0)
    n1 = Node(id=1, x=L, y=0, z=1e-12)  # tiny z to force 3D mode

    model = Model(
        nodes=[n0, n1],
        supports=[Support(node_id=0, support_type=SupportType.FIXED)],
        nodal_loads=[NodalLoad(node_id=1, moment_x=T)],
    )

    el = FrameElement(id=0, node_i=n0, node_j=n1, material=steel, section=section)
    model.elements = [el]

    assembler = Assembler(model)
    K = assembler.global_stiffness_matrix([el])
    F = assembler.global_force_vector([el])

    solver = LinearSolver(model)
    result = solver.solve(K, F)

    G = steel.shear_modulus
    J = section.J
    twist_expected = T * L / (G * J)

    rx_idx = n1.dof_indices(dofs_per_node=6)[3]  # θ_x at node 1 = 9
    twist_computed = result.displacements[rx_idx]

    assert twist_computed == pytest.approx(twist_expected, rel=0.001)
    assert model.is_3d


# ═══════════════════════════════════════════════════════════════════════════════
#  3D portal frame: vertical load on beam
# ═══════════════════════════════════════════════════════════════════════════════

def test_3d_portal_vertical_load(steel: Material) -> None:
    """Simple 3D portal: two columns (0→1, 2→3) + beam (1→2), Fy at midspan.

    Symmetric → each column takes half the vertical load.
    """
    sec = Section(name="HEB200", area=7.81e-3, moment_of_inertia=57.0e-6,
                  I_y=20.0e-6, J=0.59e-6)

    h = 3.0   # column height
    w = 4.0   # beam span
    P = -10000.0  # 10 kN downward at midspan

    n0 = Node(id=0, x=0, y=0, z=1e-12)      # left base
    n1 = Node(id=1, x=0, y=h, z=1e-12)      # left top
    n2 = Node(id=2, x=w/2, y=h, z=1e-12)    # midspan (load point)
    n3 = Node(id=3, x=w, y=h, z=1e-12)      # right top
    n4 = Node(id=4, x=w, y=0, z=1e-12)      # right base

    model = Model(
        nodes=[n0, n1, n2, n3, n4],
        supports=[
            Support(node_id=0, support_type=SupportType.FIXED),
            Support(node_id=4, support_type=SupportType.FIXED),
        ],
        nodal_loads=[NodalLoad(node_id=2, fy=P)],
    )
    assert model.is_3d

    col_l  = FrameElement(id=0, node_i=n0, node_j=n1, material=steel, section=sec)
    beam_l = FrameElement(id=1, node_i=n1, node_j=n2, material=steel, section=sec)
    beam_r = FrameElement(id=2, node_i=n2, node_j=n3, material=steel, section=sec)
    col_r  = FrameElement(id=3, node_i=n4, node_j=n3, material=steel, section=sec)

    elements = [col_l, beam_l, beam_r, col_r]
    model.elements = elements  # type: ignore[assignment]

    assembler = Assembler(model)
    K = assembler.global_stiffness_matrix(elements)
    F = assembler.global_force_vector(elements)

    solver = LinearSolver(model)
    result = solver.solve(K, F)

    # Vertical reaction at each base should be ~P/2 = 5000 N upward
    ry0 = result.reactions[n0.dof_indices(dofs_per_node=6)[1]]  # dy at n0
    ry4 = result.reactions[n4.dof_indices(dofs_per_node=6)[1]]  # dy at n4

    # Reactions oppose applied load → negative of half the load
    assert ry0 == pytest.approx(-P / 2, rel=0.02)
    assert ry4 == pytest.approx(-P / 2, rel=0.02)


# ═══════════════════════════════════════════════════════════════════════════════
#  3D UDL on beam — FEF via element load
# ═══════════════════════════════════════════════════════════════════════════════

def test_3d_udl_beam(steel: Material, section: Section) -> None:
    """Simply supported beam in 3D with UDL in local Y.

    Analytical: δ_mid = 5 w L⁴ / (384 E I_z)
    """
    L = 6.0
    w = 2000.0  # N/m downward

    # Three nodes for midspan deflection measurement
    n0 = Node(id=0, x=0, y=0, z=0)
    n1 = Node(id=1, x=L/2, y=0, z=0)
    n2 = Node(id=2, x=L, y=0, z=0)

    model = Model(
        nodes=[n0, n1, n2],
        supports=[
            Support(node_id=0, support_type=SupportType.PINNED),
            Support(node_id=2, support_type=SupportType.ROLLER_X),
        ],
    )

    el0 = FrameElement(id=0, node_i=n0, node_j=n1, material=steel, section=section)
    el1 = FrameElement(id=1, node_i=n1, node_j=n2, material=steel, section=section)
    elements = [el0, el1]
    model.elements = elements  # type: ignore[assignment]

    for eid in (0, 1):
        model.element_loads.append(
            ElementLoad(element_id=eid, load_type=LoadType.UDL, magnitude=w,
                        direction=LoadDirection.LOCAL_Y),
        )

    assembler = Assembler(model)
    K = assembler.global_stiffness_matrix(elements)
    F = assembler.global_force_vector(elements)

    solver = LinearSolver(model)
    result = solver.solve(K, F)

    assert not model.is_3d  # all z=0

    # Midspan deflection: δ = 5 w L⁴ / (384 E I)
    E = steel.elastic_modulus
    I = section.I_z
    delta_expected = 5 * w * L ** 4 / (384 * E * I)

    dy_mid = result.displacements[n1.dof_indices(dofs_per_node=3)[1]]
    assert abs(dy_mid) == pytest.approx(delta_expected, rel=0.01)
