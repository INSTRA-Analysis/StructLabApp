"""Transparency guard (finding F1): out-of-plane loads on a planar (2D) model.

A model whose nodes all lie at z == 0 is solved in 2D (3 DOF/node) regardless of
the ``mode_3d`` flag (see core.model.Model.dofs_per_node). Nodal Fz/Mx/My and
'qz' member loads are then dropped by the assembler. validate_model must WARN
(not silently drop, and not block) so the user knows these loads are ignored.
"""
import warnings

import pytest

import sdk as sl
from ui_qt.solve_actions import validate_model

E, A, I = 210e9, 6.64e-3, 8.36e-5


def _planar_cantilever(mode_3d):
    m = sl.Model(mode_3d=mode_3d)
    n0 = m.add_node(0, 0, 0)
    n1 = m.add_node(4, 0, 0)          # horizontal member, all z == 0 → planar
    m.fixed(n0)
    m.add_member(n0, n1, E=E, A=A, I=I, I_y=I, J=1e-5)
    return m, n0, n1


def _has_oop(msgs):
    return any("out-of-plane" in s.lower() for s in msgs)


def test_planar_fz_load_is_warned_not_blocked():
    m, _, n1 = _planar_cantilever(mode_3d=True)
    m.add_point_load(n1, Fz=-8e3)
    errors, warns = validate_model(m._state)
    assert not _has_oop(errors)          # not a blocking error
    assert _has_oop(warns)               # surfaced as a warning
    # solve proceeds and emits the warning (transparency), does not raise.
    with pytest.warns(UserWarning, match="out-of-plane"):
        m.solve()


def test_planar_moment_x_load_is_warned():
    m, _, n1 = _planar_cantilever(mode_3d=False)
    m.add_point_load(n1, Mx=5e3)
    _, warns = validate_model(m._state)
    assert _has_oop(warns)


def test_planar_qz_member_load_is_warned():
    m, _, _ = _planar_cantilever(mode_3d=True)
    m.add_udl(0, w=10e3, direction="qz")
    _, warns = validate_model(m._state)
    assert _has_oop(warns)


def test_inplane_planar_load_is_clean():
    """No false positive: an ordinary 2D load must not warn."""
    m, n0, n1 = _planar_cantilever(mode_3d=False)
    m.add_point_load(n1, Fy=-8e3)
    errors, warns = validate_model(m._state)
    assert not _has_oop(errors) and not _has_oop(warns)
    with warnings.catch_warnings():
        warnings.simplefilter("error")   # any out-of-plane warning would fail here
        r = m.solve()
    assert abs(r.reactions(n0)[1] - 8e3) / 8e3 < 1e-6


def test_genuine_3d_fz_load_is_clean():
    """The same out-of-plane action on real 3D geometry (z != 0) must not warn."""
    m = sl.Model(mode_3d=True)
    n0 = m.add_node(0, 0, 0)
    n1 = m.add_node(0, 0, 4)          # vertical column → genuine 3D
    m.fixed(n0)
    m.add_member(n0, n1, E=E, A=A, I=I, I_y=I, J=1e-5)
    m.add_point_load(n1, Fx=8e3)
    errors, warns = validate_model(m._state)
    assert not _has_oop(errors) and not _has_oop(warns)
    r = m.solve()
    exp = 8e3 * 4**3 / (3 * E * I)    # PL^3/3EI tip deflection
    assert abs(abs(r.displacement(n1)[0]) - exp) / exp < 1e-3
