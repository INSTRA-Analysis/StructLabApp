"""The moment used for design and summaries is the peak ALONG the member, not at its ends.

A simply supported beam carries no end moment; before this fix its utilisation showed 0 %,
the status bar a zero maximum moment, and pattern loading could not see span moments."""

import numpy as np
import pytest

from ui_qt.design_checks import display_utilisation, member_forces
from ui_qt.model_builder import build_model, build_model_combined
from ui_qt.model_state import (
    DistLoad, LoadCase, LoadCombination, MemberLoad, ModelState, PointLoadData, SupportType,
)
from ui_qt.solve_actions import largest_member_moment, solve_engine

SPAN, W = 8.0, 20e3


def _beam(point=None) -> ModelState:
    s = ModelState()
    s.analysis_type = "plane_xz"
    a, b = s.add_node(0, 0, 0), s.add_node(SPAN, 0, 0)
    a.support_type, b.support_type = SupportType.PIN, SupportType.ROLLER
    m = s.add_member(a.id, b.id)
    m.E, m.A, m.I, m.I_y, m.J, m.W_pl, m.fy = 210e9, 5.38e-3, 8.356e-5, 6.04e-6, 2.01e-7, 6.28e-4, 355e6
    ml = MemberLoad(dist_loads=[DistLoad("w", W, W)])
    if point:
        ml.point_loads.append(PointLoadData("FORCE", *point))
    s.active_case.member_loads[m.id] = ml
    return s


def _solve(s):
    return solve_engine(*build_model(s, s.active_case), s)


def test_simply_supported_beam_peak_is_wl2_over_8():
    s = _beam()
    r = _solve(s)["member_results"][0]
    assert r.peak_moment == pytest.approx(W * SPAN ** 2 / 8, rel=1e-9)
    assert member_forces(r)[1] == pytest.approx(W * SPAN ** 2 / 8, rel=1e-9)
    eta, _ = display_utilisation(s.members[0], r, SPAN)
    assert eta == pytest.approx(W * SPAN ** 2 / 8 / (6.28e-4 * 355e6), rel=1e-6)   # was 0


def test_peak_under_a_point_load_between_sub_nodes():
    P, t = 30e3, 0.333
    r = _solve(_beam((t, P)))["member_results"][0]
    a = t * SPAN
    x = np.linspace(0, SPAN, 20001)                       # independent closed form, dense
    m = W * x * (SPAN - x) / 2 + P * np.where(x < a, (SPAN - a) / SPAN * x, a / SPAN * (SPAN - x))
    assert r.peak_moment == pytest.approx(m.max(), rel=1e-6)


def test_summary_reports_the_span_moment():
    cache = _solve(_beam())
    value, member = largest_member_moment(cache["member_results"])
    assert value == pytest.approx(W * SPAN ** 2 / 8) and member == 0


def test_station_moments_superpose_across_cases():
    """Optimise sums case station moments: 1.35 G + 1.5 Q must equal the combined solve."""
    s = _beam()
    q = LoadCase(id=1, name="Q", category="Q")
    q.member_loads[0] = MemberLoad(point_loads=[PointLoadData("FORCE", 0.25, 40e3)])
    s.load_cases.append(q)
    st_g = _solve(s)["member_results"][0].moment_stations
    st_q = solve_engine(*build_model(s, q), s)["member_results"][0].moment_stations
    combo = LoadCombination(id=0, name="ULS", factors={0: 1.35, 1: 1.5})
    r_c = solve_engine(*build_model_combined(s, combo), s)["member_results"][0]
    assert np.allclose(1.35 * st_g + 1.5 * st_q, r_c.moment_stations, atol=1e-6)
