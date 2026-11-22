"""Out-of-plane loads and the declared dimension.

A 3D model is solved in 3D (6 DOF/node) even when every node lies at z = 0 (a grillage, a
floor, a beam drawn on the ground plane): its vertical loads act and match hand results.
A plane frame holds its out-of-plane freedoms, so loads out of its plane (Fy, Mx, Mz, 'qy')
are WARNED (not blocked); so are Fz/Mx/My and 'qz' on a 2D model (an old file read as stored).
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


@pytest.mark.parametrize("load", [{"Fy": 3e3}, {"Mx": 5e3}, {"Mz": 2e3}])
def test_out_of_plane_nodal_load_on_a_plane_frame_is_warned(load):
    m, _, n1 = _flat_cantilever(mode_3d=False)                 # a plane frame in XZ
    m.add_point_load(n1, **load)
    errors, warns = validate_model(m._state)
    assert not _has_oop(errors) and _has_oop(warns)


def test_qy_member_load_on_a_plane_frame_is_warned():
    m, _, _ = _flat_cantilever(mode_3d=False)
    m.add_udl(0, w=10e3, direction="qy")
    _, warns = validate_model(m._state)
    assert _has_oop(warns)


def test_inplane_loads_on_a_plane_frame_are_clean():
    """No false positive: Fx, Fz and My act in a plane frame's plane."""
    m, n0, n1 = _flat_cantilever(mode_3d=False)
    m.add_point_load(n1, Fx=1e3, Fz=-8e3, My=2e3)
    errors, warns = validate_model(m._state)
    assert not _has_oop(errors) and not _has_oop(warns)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        r = m.solve()
    assert abs(r.reactions(n0)[2] - 8e3) / 8e3 < 1e-6


def _model_2d(load):
    """A 2D model (as read from an old file with keep_2d=True)."""
    from ui_qt.model_state import ModelState, NodeLoad, SupportType
    s = ModelState()
    s.analysis_mode = "2D"
    a, b = s.add_node(0, 0, 0), s.add_node(L, 0, 0)
    a.support_type = SupportType.FIXED
    s.add_member(a.id, b.id)
    s.active_case.set_node_load(b.id, NodeLoad(**load))
    return s


@pytest.mark.parametrize("load", [{"fz": -8e3}, {"moment_x": 5e3}])
def test_out_of_plane_load_on_a_2d_model_is_warned(load):
    errors, warns = validate_model(_model_2d(load))
    assert not _has_oop(errors) and _has_oop(warns)


def test_inplane_load_on_a_2d_model_is_clean():
    _, warns = validate_model(_model_2d({"fy": -8e3}))
    assert not _has_oop(warns)


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
