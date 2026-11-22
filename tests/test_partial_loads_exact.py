"""Partial-span loads are exact element loads: fixed-end forces, diagrams and results no longer
depend on where the sub-element boundaries fall (they used to be a point force at the
centroid of the covered stretch)."""

import numpy as np
import pytest

from core.load import ElementLoad, LoadDirection, LoadType
from solver.fem_loads import fixed_end_forces
from solver.postprocessor import bending_profile
from ui_qt.model_builder import build_model
from ui_qt.model_state import MemberLoad, ModelState, PartialDistLoad, SupportType
from ui_qt.solve_actions import solve_engine

L = 6.0


def _partial(a, b, w1, w2, direction=LoadDirection.LOCAL_Y):
    return ElementLoad(0, LoadType.PARTIAL, w1, position=a, end_position=b, magnitude_end=w2,
                       direction=direction)


@pytest.mark.parametrize("is_3d, direction", [(False, LoadDirection.LOCAL_Y), (True, LoadDirection.LOCAL_Y),
                                              (True, LoadDirection.LOCAL_Z)])
def test_full_length_partial_equals_the_uvl(is_3d, direction):
    part = fixed_end_forces(_partial(0.0, L, 2e3, 9e3, direction), L, is_3d=is_3d)
    uvl = fixed_end_forces(ElementLoad(0, LoadType.UVL, 2e3, position=9e3, direction=direction),
                           L, is_3d=is_3d)
    assert part == pytest.approx(uvl)


def test_partial_fixed_end_moments_by_direct_integration():
    """Fixed-fixed beam, linear load over [a, b]: M_A = ∫ w(s) s (L − s)² / L² ds and
    M_B = ∫ w(s) s² (L − s) / L² ds, integrated here on a fine grid (independent of Gauss)."""
    w1, w2, a, b = 5e3, 8e3, 1.5, 4.0
    f = fixed_end_forces(_partial(a, b, w1, w2), L)
    s = np.linspace(a, b, 200001)
    w = w1 + (s - a) / (b - a) * (w2 - w1)
    assert f[2] == pytest.approx(np.trapezoid(w * s * (L - s) ** 2 / L ** 2, s), rel=1e-8)
    assert -f[5] == pytest.approx(np.trapezoid(w * s ** 2 * (L - s) / L ** 2, s), rel=1e-8)
    assert f[1] + f[4] == pytest.approx((w1 + w2) / 2 * (b - a))


def test_profile_of_a_partial_load_on_a_simple_span():
    """Simply supported (zero end moments), UDL over [a, b]: V and M from statics."""
    w, a, b = 5e3, 1.5, 4.0
    R_a = w * (b - a) * (L - (a + b) / 2) / L
    ends = np.array([0.0, R_a, 0.0, 0.0, 0.0, 0.0])                    # 2D [N, V, M, ...]
    x = np.linspace(0, L, 61)
    V, M = bending_profile(ends, [_partial(a, b, w, w)], L, x)
    covered = np.clip(x, a, b) - a
    assert V == pytest.approx(R_a - w * covered)
    assert M == pytest.approx(R_a * x - w * covered * (x - (a + np.clip(x, a, b)) / 2))


def _beam(n_sub: int) -> ModelState:
    s = ModelState()
    s.analysis_type = "plane_xz"
    p, q = s.add_node(0, 0, 0), s.add_node(L, 0, 0)
    p.support_type, q.support_type = SupportType.PIN, SupportType.ROLLER
    m = s.add_member(p.id, q.id)
    m.I_y, m.J, m.n_sub = m.I, 1e-5, n_sub
    s.active_case.member_loads[m.id] = MemberLoad(
        partial_loads=[PartialDistLoad(0.23, 0.71, 4e3, 10e3)])
    return s


def test_results_do_not_depend_on_subdivision():
    one, many = (solve_engine(*build_model(s, s.active_case), s)
                 for s in (_beam(1), _beam(7)))
    assert one["member_results"][0].peak_moment == pytest.approx(
        many["member_results"][0].peak_moment, rel=1e-9)
    assert one["reactions"][:12] == pytest.approx(many["reactions"][:12], abs=1e-6)   # the 2 nodes
