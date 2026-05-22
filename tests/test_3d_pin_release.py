"""Regression tests for 3D pin-released element transformation.

Issue: the old _transformation_3d used T12[np.ix_(keep,keep)] (square) then
patched the torsion diagonal with 1.0.  For tilted/vertical members this placed
torsion stiffness at the wrong global DOF — e.g. a vertical column pinned at the
top would accumulate torsion stiffness at global θ_x (DOF+3) instead of global
θ_z (DOF+5), making the system singular for a torsion load.

Fix: use T12[keep, :] (non-square, n_reduced × 12) and always return all 12
global DOFs from dof_indices so k_global = T.T @ k_local @ T is 12×12 with
correct mapping.
"""

import math
import numpy as np
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


@pytest.fixture
def steel() -> Material:
    return Material(name="S355", elastic_modulus=210e9, poisson_ratio=0.3)


@pytest.fixture
def box_section() -> Section:
    """Circular tube: A=10e-3, Iy=Iz=50e-6, J=100e-6."""
    return Section(name="BoxTube", area=10e-3,
                   moment_of_inertia=50e-6,
                   I_y=50e-6,
                   J=100e-6)


# ═══════════════════════════════════════════════════════════════════════════════
#  Transformation shape tests
# ═══════════════════════════════════════════════════════════════════════════════

def test_transformation_shape_no_pin(steel: Material, box_section: Section) -> None:
    """Full 3D element (no pins) → T is square 12×12."""
    ni = Node(id=0, x=0.0, y=0.0, z=0.0)
    nj = Node(id=1, x=0.0, y=0.0, z=3.0)
    el = FrameElement(0, ni, nj, steel, box_section)
    T = el.transformation_matrix()
    assert T.shape == (12, 12)
    assert len(el.dof_indices()) == 12


def test_transformation_shape_pin_j(steel: Material, box_section: Section) -> None:
    """Vertical column, pin at top → T is non-square (10×12), dof_indices has 12."""
    ni = Node(id=0, x=0.0, y=0.0, z=0.0)
    nj = Node(id=1, x=0.0, y=0.0, z=3.0)
    el = FrameElement(0, ni, nj, steel, box_section, pin_j=True)
    T = el.transformation_matrix()
    assert T.shape == (10, 12), f"Expected (10, 12), got {T.shape}"
    assert len(el.dof_indices()) == 12


def test_transformation_shape_pin_i(steel: Material, box_section: Section) -> None:
    """Inclined member, pin at start → T is non-square (10×12), dof_indices has 12."""
    ni = Node(id=0, x=0.0, y=0.0, z=0.0)
    nj = Node(id=1, x=4.0, y=0.0, z=3.0)
    el = FrameElement(0, ni, nj, steel, box_section, pin_i=True)
    T = el.transformation_matrix()
    assert T.shape == (10, 12), f"Expected (10, 12), got {T.shape}"
    assert len(el.dof_indices()) == 12


def test_transformation_shape_both_pins(steel: Material, box_section: Section) -> None:
    """Bar element (both pins) → T is non-square (8×12), dof_indices has 12."""
    ni = Node(id=0, x=0.0, y=0.0, z=0.0)
    nj = Node(id=1, x=0.0, y=0.0, z=3.0)
    el = FrameElement(0, ni, nj, steel, box_section, pin_i=True, pin_j=True)
    T = el.transformation_matrix()
    assert T.shape == (8, 12), f"Expected (8, 12), got {T.shape}"
    assert len(el.dof_indices()) == 12


# ═══════════════════════════════════════════════════════════════════════════════
#  Structural: vertical column, pin_j=True, torsion moment at top
# ═══════════════════════════════════════════════════════════════════════════════

def test_vertical_column_pin_top_torsion(steel: Material, box_section: Section) -> None:
    """Vertical column pinned at top subjected to torsion moment M_z at the free end.

    Geometry:  node 0 at (0,0,0) — fixed base
               node 1 at (0,0,L) — pin release (bending free, torsion carried)

    Load: M_z = 10 kN·m at node 1 about global Z (= local x for a vertical member).

    Expected twist at node 1:
        θ_z = M_z * L / (G * J)

    Old buggy code: places torsion stiffness at global θ_x (DOF+3) instead of
    global θ_z (DOF+5) for a vertical column → singular system.
    Fixed code: T is non-square so each local row maps to the correct global col.
    """
    L = 3.0
    G = steel.shear_modulus
    J = box_section.J

    ni = Node(id=0, x=0.0, y=0.0, z=0.0)
    nj = Node(id=1, x=0.0, y=0.0, z=L)

    el = FrameElement(0, ni, nj, steel, box_section, pin_j=True)

    Mz = 10_000.0  # N·m

    model = Model(
        nodes=[ni, nj],
        supports=[Support(node_id=0, support_type=SupportType.FIXED)],
        nodal_loads=[NodalLoad(node_id=1, moment=Mz)],  # moment = moment_z
    )
    model.elements = [el]

    assembler = Assembler(model)
    K = assembler.global_stiffness_matrix([el])
    F = assembler.global_force_vector([el])

    solver = LinearSolver(model)
    result = solver.solve(K, F)

    dpn = model.dofs_per_node  # must be 6
    theta_z_top = result.displacements[nj.id * dpn + 5]  # θ_z at node 1

    expected = Mz * L / (G * J)

    assert abs(theta_z_top - expected) / expected < 1e-6, (
        f"θ_z at top = {theta_z_top:.6e} rad, expected {expected:.6e} rad"
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  Structural: vertical column, pin_j=True, lateral load — checks correct
#  projection of v_y bending stiffness to global X via non-square T
# ═══════════════════════════════════════════════════════════════════════════════

def test_vertical_column_pin_top_lateral_deflection(
    steel: Material, box_section: Section
) -> None:
    """Vertical column, fixed at base, pin at top, lateral force fx = P at top.

    For a cantilever with moment-release at the free end and transverse load P:
        δ_x = P * L³ / (3 * E * Iz)

    This validates that the non-square T correctly maps local v_y bending
    stiffness to the global X DOF for a near-vertical member.
    """
    L = 3.0
    P = 5_000.0
    E = steel.elastic_modulus
    Iz = box_section.moment_of_inertia  # strong-axis, controls v_y bending

    ni = Node(id=0, x=0.0, y=0.0, z=0.0)
    nj = Node(id=1, x=0.0, y=0.0, z=L)

    el = FrameElement(0, ni, nj, steel, box_section, pin_j=True)

    model = Model(
        nodes=[ni, nj],
        supports=[Support(node_id=0, support_type=SupportType.FIXED)],
        nodal_loads=[NodalLoad(node_id=1, fx=P)],
    )
    model.elements = [el]

    assembler = Assembler(model)
    K = assembler.global_stiffness_matrix([el])
    F = assembler.global_force_vector([el])

    solver = LinearSolver(model)
    result = solver.solve(K, F)

    dpn = model.dofs_per_node
    dx_top = result.displacements[nj.id * dpn + 0]  # global dx at node 1

    expected = P * L ** 3 / (3.0 * E * Iz)

    assert abs(dx_top - expected) / expected < 1e-6, (
        f"dx at top = {dx_top:.6e} m, expected {expected:.6e} m"
    )
