"""Out-of-plane loads and the declared dimension.

A 3D model is solved in 3D (6 DOF/node) even when every node lies at z = 0 (a grillage, a
floor, a beam drawn on the ground plane): its vertical loads act and match hand results.
Only a 2D model has no out-of-plane freedoms; there nodal Fz/Mx/My and 'qz' member loads
cannot act, and validate_model WARNS (does not block) so they are never dropped silently.
"""
import warnings

import pytest

import sdk as sl
from ui_qt.solve_actions import validate_model

E, A, I = 210e9, 6.64e-3, 8.36e-5
L = 4.0


def _flat_cantilever(mode_3d):
    m = sl.Model(mode_3d=mode_3d)
    n0 = m.add_node(0, 0, 0)
    n1 = m.add_node(L, 0, 0)          # horizontal member, all z == 0
    m.fixed(n0)
    m.add_member(n0, n1, E=E, A=A, I=I, I_y=I, J=1e-5)
    return m, n0, n1


def _has_oop(msgs):
    return any("out-of-plane" in s.lower() for s in msgs)


def test_flat_3d_model_carries_a_vertical_nodal_load():
    m, n0, n1 = _flat_cantilever(mode_3d=True)
    m.add_point_load(n1, Fz=-8e3)
    errors, warns = validate_model(m._state)
    assert not _has_oop(errors) and not _has_oop(warns)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        r = m.solve()
    assert r.displacement(n1)[2] == pytest.approx(-8e3 * L ** 3 / (3 * E * I), rel=1e-6)
    assert r.reactions(n0)[2] == pytest.approx(8e3, rel=1e-9)


def test_flat_3d_model_carries_a_qz_member_load():
    m, _, n1 = _flat_cantilever(mode_3d=True)
    m.add_udl(0, w=10e3, direction="qz")
    _, warns = validate_model(m._state)
    assert not _has_oop(warns)
    r = m.solve()
    # qz is lumped onto the sub-element nodes (converges with n_sub; ~0.3 % at the default)
    assert r.displacement(n1)[2] == pytest.approx(-10e3 * L ** 4 / (8 * E * I), rel=1e-2)


@pytest.mark.parametrize("load", [{"Fz": -8e3}, {"Mx": 5e3}])
def test_out_of_plane_nodal_load_on_a_2d_model_is_warned(load):
    m, _, n1 = _flat_cantilever(mode_3d=False)
    m.add_point_load(n1, **load)
    errors, warns = validate_model(m._state)
    assert not _has_oop(errors) and _has_oop(warns)


def test_qz_member_load_on_a_2d_model_is_warned():
    m, _, _ = _flat_cantilever(mode_3d=False)
    m.add_udl(0, w=10e3, direction="qz")
    _, warns = validate_model(m._state)
    assert _has_oop(warns)


def test_inplane_load_on_a_2d_model_is_clean():
    """No false positive: an ordinary 2D load must not warn."""
    m, n0, n1 = _flat_cantilever(mode_3d=False)
    m.add_point_load(n1, Fy=-8e3)
    errors, warns = validate_model(m._state)
    assert not _has_oop(errors) and not _has_oop(warns)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        r = m.solve()
    assert abs(r.reactions(n0)[1] - 8e3) / 8e3 < 1e-6


def test_genuine_3d_column_is_clean():
    m = sl.Model(mode_3d=True)
    n0 = m.add_node(0, 0, 0)
    n1 = m.add_node(0, 0, L)          # vertical column
    m.fixed(n0)
    m.add_member(n0, n1, E=E, A=A, I=I, I_y=I, J=1e-5)
    m.add_point_load(n1, Fx=8e3)
    errors, warns = validate_model(m._state)
    assert not _has_oop(errors) and not _has_oop(warns)
    r = m.solve()
    exp = 8e3 * L ** 3 / (3 * E * I)
    assert abs(abs(r.displacement(n1)[0]) - exp) / exp < 1e-3
