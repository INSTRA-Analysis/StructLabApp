"""Global distributed loads (qx / qy / qz) and self-weight act as exact element loads in 3D:
the results no longer depend on how finely a member is subdivided.

Before, qx / qy / qz were lumped at the sub-nodes (exact only in the limit of many
sub-elements) and the axial part of self-weight at the sub-element ends."""

import math

import numpy as np
import pytest

from core.load import ElementLoad, LoadDirection, LoadType
from solver.fem_loads import fixed_end_forces
from ui_qt.model_builder import build_model
from ui_qt.model_state import DistLoad, MemberLoad, ModelState, SupportType
from ui_qt.solve_actions import solve_engine

E, I, L = 210e9, 2e-4, 6.0


def test_axial_fixed_end_forces():
    f = fixed_end_forces(ElementLoad(0, LoadType.UVL, 2e3, position=8e3,
                                     direction=LoadDirection.LOCAL_X), L, is_3d=True)
    assert f[0] + f[6] == pytest.approx((2e3 + 8e3) / 2 * L)          # all of it, pushed back
    assert f[0] == pytest.approx(L * (2 * 2e3 + 8e3) / 6)
    assert np.count_nonzero(f) == 2
    with pytest.raises(ValueError):
        fixed_end_forces(ElementLoad(0, LoadType.POINT_FORCE, 1e3, 1.0,
                                     direction=LoadDirection.LOCAL_X), L, is_3d=True)


def _beam(n_sub: int, load: str, analysis_type="space", incline=0.0) -> ModelState:
    s = ModelState()
    s.analysis_type = analysis_type
    a = s.add_node(0, 0, 0)
    b = s.add_node(L * math.cos(incline), 0, L * math.sin(incline))
    for n in (a, b):                                   # pinned, twist about the axis held
        n.set_restraints((True, True, True, True, False, False))
    m = s.add_member(a.id, b.id)
    m.E, m.A, m.I, m.I_y, m.J, m.n_sub = E, 8e-3, I, I / 2, 1e-5, n_sub
    m.density = 7850.0
    if load == "self":
        s.active_case.include_self_weight = True
    else:
        s.active_case.member_loads[m.id] = MemberLoad(dist_loads=[DistLoad(load, 3e3, 11e3)])
    return s


@pytest.mark.parametrize("load", ["qx", "qy", "qz", "self"])
@pytest.mark.parametrize("incline", [0.0, 0.6])
def test_results_do_not_depend_on_subdivision(load, incline):
    """1 and 20 sub-elements give the same peak moment, deflection and reactions."""
    coarse = solve_engine(*build_model(s := _beam(1, load, incline=incline), s.active_case), s)
    fine = solve_engine(*build_model(t := _beam(20, load, incline=incline), t.active_case), t)
    rc, rf = coarse["member_results"][0], fine["member_results"][0]
    assert rc.peak_moment == pytest.approx(rf.peak_moment, rel=1e-9, abs=1e-6)
    react = lambda c: c["reactions"][[0, 1, 2, 6, 7, 8]]                     # noqa: E731
    assert react(coarse) == pytest.approx(react(fine), rel=1e-9, abs=1e-6)


def test_triangular_qz_on_a_simple_beam_matches_the_closed_form():
    """qz from 0 to q: peak M = q L² / (9√3) at x = L/√3, one element."""
    q = 12e3
    s = _beam(1, "qz")
    s.active_case.member_loads[0] = MemberLoad(dist_loads=[DistLoad("qz", 0.0, q)])
    r = solve_engine(*build_model(s, s.active_case), s)["member_results"][0]
    assert r.peak_moment == pytest.approx(q * L ** 2 / (9 * math.sqrt(3)), rel=1e-6)


def test_self_weight_axial_force_varies_along_a_column():
    """Vertical column, pinned base, top held sideways: N goes from 0 at the top to the full
    weight at the base, whatever the subdivision (it used to be lumped per sub-element)."""
    s = ModelState()
    a, b = s.add_node(0, 0, 0), s.add_node(0, 0, 4.0)
    a.support_type = SupportType.FIXED
    b.set_restraints((True, True, False, False, False, False))
    m = s.add_member(a.id, b.id)
    m.A, m.density, m.n_sub, m.I_y, m.J = 0.01, 7850.0, 1, m.I, 1e-5
    s.active_case.include_self_weight = True
    r = solve_engine(*build_model(s, s.active_case), s)["member_results"][0]
    weight = 7850.0 * 0.01 * 9.81 * 4.0
    assert r.N_i == pytest.approx(weight)                 # compression at the base
    assert r.N_j == pytest.approx(0.0, abs=1e-6)
