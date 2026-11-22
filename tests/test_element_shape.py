"""transverse_deflection: the exact displaced shape inside one element, from the end
displacements and the curvature M/EI — no end rotations, no fine subdivision needed."""

import numpy as np
import pytest

from solver.postprocessor import transverse_deflection
from ui_qt.model_builder import build_model
from ui_qt.model_state import (
    DistLoad, ElementType, MemberLoad, ModelState, PartialDistLoad, PointLoadData, SupportType,
)
from ui_qt.solve_actions import solve_engine

E, I, IY, L = 210e9, 2e-4, 5e-5, 6.0


def _beam(analysis_type, n_sub, loads: MemberLoad, kind=ElementType.BEAM, right=SupportType.ROLLER):
    s = ModelState()
    s.analysis_type = analysis_type
    a, b = s.add_node(0, 0, 0), s.add_node(L, 0, 0)
    a.set_restraints((True, True, True, True, False, False))       # pin, twist held
    b.support_type = right
    if right is SupportType.ROLLER:
        b.set_restraints((False, True, True, True, False, False))
    m = s.add_member(a.id, b.id)
    m.E, m.I, m.I_y, m.J, m.n_sub, m.element_type = E, I, IY, 1e-5, n_sub, kind
    s.active_case.member_loads[m.id] = loads
    model, mm = build_model(s, s.active_case)
    return model, solve_engine(model, mm, s)


def _shape(model, cache, el_index, plane, x):
    el = model.elements[el_index]
    res = cache["sub_results"][el_index]
    loads = [ld for ld in model.element_loads if ld.element_id == el.id]
    d = cache["displacements"]
    li = el._R3.T @ d[el.node_i.id * 6:el.node_i.id * 6 + 3]
    lj = el._R3.T @ d[el.node_j.id * 6:el.node_j.id * 6 + 3]
    k = 1 if plane == "z" else 2
    EI = E * (I if plane == "z" else IY)
    return transverse_deflection(res.end_forces, loads, el.length, EI, li[k], lj[k], x, plane)


def test_vertical_udl_midspan_on_one_element():
    w = 10e3
    model, cache = _beam("plane_xz", 1, MemberLoad(dist_loads=[DistLoad("w", w, w)]))
    v = _shape(model, cache, 0, "z", np.array([L / 2]))[0]          # local y = up
    assert v == pytest.approx(-5 * w * L ** 4 / (384 * E * I), rel=1e-9)


def test_sideways_udl_bends_about_the_weak_axis():
    q = 4e3                                                          # along +Y
    model, cache = _beam("space", 1, MemberLoad(dist_loads=[DistLoad("qy", q, q)]))
    w_local = _shape(model, cache, 0, "y", np.array([L / 2]))[0]
    uy = -w_local                                                    # local z = −Y here
    assert uy == pytest.approx(5 * q * L ** 4 / (384 * E * IY), rel=1e-9)


@pytest.mark.parametrize("kind, right", [(ElementType.BEAM, SupportType.ROLLER),
                                         (ElementType.PIN_RIGHT, SupportType.FIXED)])
def test_one_element_reproduces_a_fine_mesh(kind, right):
    """Point moment, partial and triangular loads (and a released end): the one-element shape
    at the fine mesh's interior nodes equals that mesh's nodal displacements."""
    loads = MemberLoad(dist_loads=[DistLoad("w", 0.0, 9e3)],
                       point_loads=[PointLoadData("MOMENT", 0.3, 7e3), PointLoadData("FORCE", 0.55, 5e3)],
                       partial_loads=[PartialDistLoad(0.6, 0.9, 6e3, 2e3)])
    coarse_model, coarse = _beam("plane_xz", 1, loads, kind, right)
    fine_model, fine = _beam("plane_xz", 8, loads, kind, right)
    xs = np.arange(1, 8) * L / 8
    v = _shape(coarse_model, coarse, 0, "z", xs)
    uz_fine = fine["displacements"][[n * 6 + 2 for n in range(2, 9)]]   # sub-nodes 2..8, Z up
    assert v == pytest.approx(uz_fine, rel=1e-8, abs=1e-12)
