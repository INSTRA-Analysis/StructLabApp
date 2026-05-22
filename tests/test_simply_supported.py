"""Test: simply supported beam with center point load → δ = PL³/48EI."""

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


def test_midspan_deflection():
    """DSM result must match PL³/48EI within 0.1%."""
    L = 10.0          # m  (total span)
    E = 200e9         # Pa (steel)
    I = 60e-6         # m⁴
    A = 6.65e-3       # m²
    P = 10_000.0      # N  (downward)

    # Three nodes: left support, midspan, right support
    nodes = [
        Node(0, 0.0,   0.0),
        Node(1, L / 2, 0.0),
        Node(2, L,     0.0),
    ]
    material = Material("Steel", E)
    section = Section("Generic", A, I)

    elements = [
        FrameElement(0, nodes[0], nodes[1], material, section),
        FrameElement(1, nodes[1], nodes[2], material, section),
    ]

    supports = [
        Support(0, SupportType.PINNED),    # restrains dx, dy at node 0
        Support(2, SupportType.ROLLER_X),  # restrains dy at node 2 (free to move in x)
    ]

    nodal_loads = [
        NodalLoad(node_id=1, fx=0.0, fy=-P, moment=0.0),
    ]

    model = Model(
        nodes=nodes,
        elements=elements,
        supports=supports,
        nodal_loads=nodal_loads,
    )

    assembler = Assembler(model)
    K = assembler.global_stiffness_matrix(elements)
    F = assembler.global_force_vector(elements)

    solver = LinearSolver(model)
    result = solver.solve(K, F)

    midspan_dy = result.displacements[1 * 3 + 1]  # node 1, dy DOF

    analytical = -P * L**3 / (48 * E * I)

    assert abs(midspan_dy - analytical) / abs(analytical) < 0.001, (
        f"Midspan deflection {midspan_dy:.6e} m differs from analytical "
        f"{analytical:.6e} m by more than 0.1%"
    )
