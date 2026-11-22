"""Linearly varying load (UVL): textbook fixed-end moments and cantilever root moment.

The UVL fixed-end moments carried the opposite sign to the UDL's (w1 = w2 did not reproduce
the UDL), which went unnoticed because 2D and 3D shared the error. Checked here against
closed forms, one element per member (no sub-division to hide it)."""

import pytest

from core.load import ElementLoad, LoadDirection, LoadType
from core.support import SupportType
from solver.fem_loads import fixed_end_forces
from tests.test_bending_profile import L, _solve

W1, W2 = 2e3, 9e3


@pytest.mark.parametrize("is_3d, direction", [(False, LoadDirection.LOCAL_Y),
                                              (True, LoadDirection.LOCAL_Y),
                                              (True, LoadDirection.LOCAL_Z)])
def test_equal_ends_reproduce_the_udl(is_3d, direction):
    uvl = fixed_end_forces(ElementLoad(0, LoadType.UVL, 5e3, position=5e3, direction=direction),
                           L, is_3d=is_3d)
    udl = fixed_end_forces(ElementLoad(0, LoadType.UDL, 5e3, direction=direction), L, is_3d=is_3d)
    assert uvl == pytest.approx(udl)


@pytest.mark.parametrize("dim", [2, 3])
def test_fixed_fixed_end_moments(dim):
    er = _solve(dim, [ElementLoad(0, LoadType.UVL, W1, position=W2)])
    m_i, m_j = (er.end_forces[2], er.end_forces[5]) if dim == 2 else (er.end_forces[5], er.end_forces[11])
    assert m_i == pytest.approx(-L ** 2 * (3 * W1 + 2 * W2) / 60)      # hogging at both ends
    assert m_j == pytest.approx(-L ** 2 * (2 * W1 + 3 * W2) / 60)


@pytest.mark.parametrize("dim", [2, 3])
@pytest.mark.parametrize("load, m_root", [
    # propped cantilever (fixed at i, pinned at j), textbook root moments
    (ElementLoad(0, LoadType.UDL, 7e3), -7e3 * L ** 2 / 8),
    (ElementLoad(0, LoadType.POINT_FORCE, 11e3, position=1.7),
     -11e3 * 1.7 * (L - 1.7) * (2 * L - 1.7) / (2 * L ** 2)),
])
def test_propped_cantilever_with_a_released_end(dim, load, m_root):
    """Member hinged (moment-released) at j on a pin: the released end's shear must follow."""
    er = _solve(dim, [load], SupportType.PINNED, pin_j=True)
    root = er.end_forces[2] if dim == 2 else er.end_forces[5]
    assert root == pytest.approx(m_root)


@pytest.mark.parametrize("is_3d, direction, v_i, v_j", [
    (False, LoadDirection.LOCAL_Y, 1, 4), (True, LoadDirection.LOCAL_Y, 1, 7),
    (True, LoadDirection.LOCAL_Z, 2, 8)])
def test_both_ends_released_is_a_simple_span(is_3d, direction, v_i, v_j):
    """Released at both ends: no end moments, statically determinate end shears."""
    P, a = 11e3, 1.7
    f = fixed_end_forces(ElementLoad(0, LoadType.POINT_FORCE, P, position=a, direction=direction),
                         L, pin_i=True, pin_j=True, is_3d=is_3d)
    assert f[v_i] == pytest.approx(P * (L - a) / L) and f[v_j] == pytest.approx(P * a / L)
    moments = (2, 5) if not is_3d else (4, 5, 10, 11)
    assert all(f[k] == pytest.approx(0.0, abs=1e-9) for k in moments)


def test_weak_plane_released_end_matches_the_strong_plane():
    """Same propped cantilever loaded in local z: the weak-plane root moment has the same size."""
    load_y = ElementLoad(0, LoadType.POINT_FORCE, 11e3, position=1.7)
    load_z = ElementLoad(0, LoadType.POINT_FORCE, 11e3, position=1.7, direction=LoadDirection.LOCAL_Z)
    m_z = _solve(3, [load_y], SupportType.PINNED, pin_j=True).end_forces[5]
    m_y = _solve(3, [load_z], SupportType.PINNED, pin_j=True).end_forces[4]
    assert abs(m_y) == pytest.approx(abs(m_z))


@pytest.mark.parametrize("dim", [2, 3])
def test_cantilever_root_moment_is_the_load_resultant_times_its_lever_arm(dim):
    er = _solve(dim, [ElementLoad(0, LoadType.UVL, W1, position=W2)], SupportType.FREE)
    m_root = er.end_forces[2] if dim == 2 else er.end_forces[5]
    assert m_root == pytest.approx(-(W1 * L ** 2 / 2 + (W2 - W1) * L ** 2 / 3))
