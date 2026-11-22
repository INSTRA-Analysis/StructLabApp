"""bending_profile: exact V(x), M(x) along an element for every element-load type.

M(L) must reproduce the solver's own j-end moment (the profile and the stiffness solution
agree), in 2D and in both 3D bending planes; textbook peaks for point loads off the nodes.
"""

import numpy as np
import pytest

from core.load import ElementLoad, LoadDirection, LoadType
from core.material import Material
from core.model import Model
from core.node import Node
from core.section import Section
from core.support import Support, SupportType
from elements.frame_element import FrameElement
from solver.assembler import Assembler
from solver.linear_solver import LinearSolver
from solver.postprocessor import Postprocessor, bending_profile

L = 5.0


def _solve(dim, loads, end_j=SupportType.FIXED, pin_j=False):
    a, b = Node(0, 0, 0, 0), Node(1, L, 0, 0)
    el = FrameElement(0, a, b, Material("s", 210e9, 0.3),
                      Section("s", 0.01, 1e-4, I_y=4e-5, J=1e-6), pin_j=pin_j, dimension=dim)
    model = Model(nodes=[a, b], elements=[el], dimension=dim,
                  supports=[Support(0, SupportType.FIXED), Support(1, end_j)])
    model.element_loads = loads
    asm = Assembler(model)
    res = LinearSolver(model).solve(asm.global_stiffness_matrix(model.elements),
                                    asm.global_force_vector(model.elements))
    return Postprocessor(model.elements, loads, res.displacements).compute()[0]


def _loads(direction):
    return [ElementLoad(0, LoadType.UDL, 7e3, direction=direction),
            ElementLoad(0, LoadType.UVL, 2e3, position=9e3, direction=direction),
            ElementLoad(0, LoadType.POINT_FORCE, 11e3, position=1.7, direction=direction),
            ElementLoad(0, LoadType.POINT_MOMENT, 6e3, position=3.1, direction=direction)]


@pytest.mark.parametrize("dim, direction, plane, j", [
    (2, LoadDirection.LOCAL_Y, "z", 5),
    (3, LoadDirection.LOCAL_Y, "z", 11),
    (3, LoadDirection.LOCAL_Z, "y", 10),
])
@pytest.mark.parametrize("end_j, pin_j", [(SupportType.FIXED, False), (SupportType.PINNED, True),
                                          (SupportType.FREE, False)])
def test_profile_ends_on_the_solvers_j_moment(dim, direction, plane, j, end_j, pin_j):
    loads = _loads(direction)
    er = _solve(dim, loads, end_j, pin_j)
    V, M = bending_profile(er.end_forces, loads, L, np.array([0.0, L]), plane)
    scale = np.abs(er.end_forces).max()
    assert M[0] == pytest.approx(er.end_forces[{5: 2, 11: 5, 10: 4}[j]], abs=1e-9 * scale)
    assert M[1] == pytest.approx(er.end_forces[j], abs=1e-9 * scale)


def test_simply_supported_point_load_peak_is_pab_over_l():
    P, a = 10e3, 1.7
    loads = [ElementLoad(0, LoadType.POINT_FORCE, P, position=a)]
    er = _solve(3, loads, SupportType.PINNED, pin_j=False)      # propped cantilever: check shape
    x = np.array([a])
    _, M = bending_profile(er.end_forces, loads, L, x)
    # independent statics on the propped cantilever: M(a) = M_i + V_i * a
    assert M[0] == pytest.approx(er.end_forces[5] + er.end_forces[1] * a)


def test_point_moment_steps_by_its_magnitude():
    loads = [ElementLoad(0, LoadType.POINT_MOMENT, 6e3, position=2.0)]
    er = _solve(3, loads)
    _, M = bending_profile(er.end_forces, loads, L, np.array([2.0 - 1e-9, 2.0]))
    assert abs(M[1] - M[0]) == pytest.approx(6e3)


def test_loads_in_the_other_plane_are_ignored():
    loads = [ElementLoad(0, LoadType.UDL, 5e3, direction=LoadDirection.LOCAL_Z)]
    er = _solve(3, loads)
    _, Mz = bending_profile(er.end_forces, loads, L, np.linspace(0, L, 9), "z")
    assert np.allclose(Mz, 0.0, atol=1e-6)
