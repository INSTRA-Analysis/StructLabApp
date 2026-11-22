"""The drawn BMD / SFD are exact where a point load falls between sub-nodes.

Before: the per-sub-element profile ignored point forces and point moments, so a load at
1/3 span drew a notch 5.6 % off the true moment and a point moment drew no step at all."""

import numpy as np
import pytest

from ui_qt import canvas_overlay as co
from ui_qt.model_builder import build_model
from ui_qt.model_state import MemberLoad, ModelState, PointLoadData, SupportType
from ui_qt.solve_actions import solve_engine

SPAN, A = 10.0, 3.33          # 0.333 L: inside a sub-element (n_sub = 20)


def _profiles(kind, magnitude):
    s = ModelState()
    s.analysis_type = "plane_xz"
    a, b = s.add_node(0, 0, 0), s.add_node(SPAN, 0, 0)
    a.support_type, b.support_type = SupportType.PIN, SupportType.ROLLER
    m = s.add_member(a.id, b.id)
    m.I_y, m.J = m.I, 1e-5
    s.active_case.member_loads[m.id] = MemberLoad(point_loads=[PointLoadData(kind, A / SPAN, magnitude)])
    model, mm = build_model(s, s.active_case)
    cache = solve_engine(model, mm, s)
    res = {r.element_id: r for r in cache["sub_results"]}
    els = {e.id: e for e in model.elements}
    loads = co.build_load_map(model)
    t_m, M = co._stitch_M(mm[0], res, els, loads)
    t_v, V = co._stitch_V(mm[0], res, els, loads)
    return t_m * SPAN, M, t_v * SPAN, V


def test_point_force_moment_and_shear_are_exact():
    P = 10e3
    x, M, xv, V = _profiles("FORCE", P)
    exact_m = P * np.where(x < A, (SPAN - A) / SPAN * x, A / SPAN * (SPAN - x))
    assert np.abs(M).max() == pytest.approx(P * A * (SPAN - A) / SPAN, rel=1e-9)
    assert np.allclose(np.abs(M), exact_m, atol=1e-6 * P)
    assert set(np.round(np.abs(V) / P, 6)) == {round((SPAN - A) / SPAN, 6), round(A / SPAN, 6)}


def test_diagram_scale_does_not_depend_on_subdivision():
    """The auto-scale follows the member length, not the sub-element length (with the new
    default of 4 sub-elements the diagrams were drawn 5× too large)."""
    scales = []
    for n_sub in (4, 20):
        s = ModelState()
        s.analysis_type = "plane_xz"
        a, b = s.add_node(0, 0, 0), s.add_node(SPAN, 0, 0)
        a.support_type, b.support_type = SupportType.PIN, SupportType.ROLLER
        m = s.add_member(a.id, b.id)
        m.I_y, m.J, m.n_sub = m.I, 1e-5, n_sub
        s.active_case.member_loads[m.id] = MemberLoad(point_loads=[PointLoadData("FORCE", 0.5, 1e4)])
        model, mm = build_model(s, s.active_case)
        cache = solve_engine(model, mm, s)
        scales.append(co.compute_auto_scales(model, cache["sub_results"], cache["displacements"], mm))
    assert scales[0] == pytest.approx(scales[1], rel=1e-9)


def test_point_moment_draws_its_step_at_the_load():
    M0 = 10e3
    x, M, _, _ = _profiles("MOMENT", M0)
    exact = M0 * np.where(x < A, -x / SPAN, 1 - x / SPAN)
    assert np.allclose(np.abs(M), np.abs(exact), atol=1e-6 * M0)
    i = np.searchsorted(x, A)                       # the two samples either side of the load
    assert abs(M[i] - M[i - 1]) == pytest.approx(M0, rel=1e-6)
