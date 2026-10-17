"""Mechanisms raise UnstableStructureError (a LinAlgError) with a helpful hint."""

import numpy as np
import pytest

import sdk as sl
from core.model import Model
from core.node import Node
from solver.linear_solver import LinearSolver, UnstableStructureError

pytestmark = pytest.mark.filterwarnings("ignore")


def test_unsupported_beam_raises_friendly_singular_error():
    m = sl.Model(mode_3d=False)
    a, b = m.add_node(0, 0), m.add_node(4, 0)
    m.add_member(a, b, E=210e9, A=0.01, I=1e-4)
    m.add_point_load(b, Fy=-1000.0)
    m.pin(a)                      # one pin only: rigid-body rotation about it
    with pytest.raises(UnstableStructureError, match="Singular matrix"):
        m.solve()


def test_error_is_still_a_linalg_error():
    assert issubclass(UnstableStructureError, np.linalg.LinAlgError)


def test_out_of_plane_coplanar_bars_node_is_reported():
    """A node held only by bars in one plane has no out-of-plane stiffness."""
    m = sl.Model(mode_3d=True)
    corners = [m.add_node(x, y, 5.0) for x, y in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    centre = m.add_node(0, 0, 5.0)
    for c in corners:
        m.pin(c)
        m.add_member(c, centre, E=210e9, A=0.001, I=1e-8, element_type="BAR")
    m.add_point_load(centre, Fz=-1000.0)
    with pytest.raises(UnstableStructureError):
        m.solve()


def _two_node_solver() -> LinearSolver:
    model = Model()
    model.nodes = [Node(id=0, x=0.0, y=0.0, z=0.0), Node(id=1, x=10.0, y=0.0, z=0.0)]
    return LinearSolver(model)


def test_absurd_displacement_flags_a_mechanism_and_names_the_node():
    solver = _two_node_solver()
    d = np.zeros(solver.num_dofs)
    d[solver._dpn + 1] = 1e6                      # node 1 moves a million metres
    with pytest.raises(UnstableStructureError) as info:
        solver._check_for_mechanism(d)
    assert "node(s) 1" in info.value.hint


def test_non_finite_displacement_is_a_mechanism():
    solver = _two_node_solver()
    d = np.zeros(solver.num_dofs)
    d[0] = np.nan
    with pytest.raises(UnstableStructureError):
        solver._check_for_mechanism(d)


def test_ordinary_displacements_pass():
    solver = _two_node_solver()
    d = np.zeros(solver.num_dofs)
    d[solver._dpn + 1] = 0.05                     # 5 cm on a 10 m span
    solver._check_for_mechanism(d)                # must not raise
