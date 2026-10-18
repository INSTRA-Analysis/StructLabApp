"""Steel angle checks (EN 1993-1-1 §6.3.1 buckling, §6.2.3 tension) and the material dispatcher.

Expected values are worked by hand from the tabulated section data and the code formulas, not
taken from the implementation: the buckling reduction is anchored on the published value
chi(lambda_bar = 1.0, curve b) = 0.5970.
"""

import math
from types import SimpleNamespace

import pytest

from ui_qt import design_checks as dc
from ui_qt.angle_sections import ANGLE_SECTIONS, angle_properties
from ui_qt.model_state import ElementType, MemberData

E = 210e9


# ── the reduction factor ──────────────────────────────────────────────────────

def test_reduction_curve_b_matches_the_published_value():
    assert dc.buckling_reduction(1.0, "b") == pytest.approx(0.5970, abs=1e-4)


def test_reduction_curve_a_and_c_at_lambda_one():
    # Phi = 0.5 [1 + alpha (1 - 0.2) + 1]; chi = 1 / (Phi + sqrt(Phi^2 - 1))
    for curve, alpha in (("a", 0.21), ("c", 0.49)):
        phi = 0.5 * (1 + alpha * 0.8 + 1)
        assert dc.buckling_reduction(1.0, curve) == pytest.approx(1 / (phi + math.sqrt(phi * phi - 1)))


def test_reduction_is_one_below_the_plateau_and_decreases_after():
    assert dc.buckling_reduction(0.2) == 1.0 and dc.buckling_reduction(0.1) == 1.0
    values = [dc.buckling_reduction(x / 10) for x in range(3, 40)]
    assert all(a > b for a, b in zip(values, values[1:])) and 0 < values[-1] < 0.2


# ── hand-worked resistance: L 100x10, S355, L = 2.0 m ─────────────────────────

def test_buckling_resistance_of_an_equal_angle_by_hand():
    # tabulated: A = 19.2 cm2, i_v = 1.95 cm
    A, i_v, L, fy = 19.2e-4, 1.95e-2, 2.0, 355e6
    lam1 = math.pi * math.sqrt(E / fy)                       # 76.41
    lam_bar = (L / i_v) / lam1                               # 1.342
    phi = 0.5 * (1 + 0.34 * (lam_bar - 0.2) + lam_bar ** 2)
    chi = 1 / (phi + math.sqrt(phi ** 2 - lam_bar ** 2))
    expected = chi * A * fy
    sec = angle_properties("L 100×10")
    got = dc.flexural_buckling_resistance(sec.A, sec.I_v, L, fy, E)
    assert got["lambda_bar"] == pytest.approx(lam_bar, rel=0.005)
    assert got["N_b_Rd"] == pytest.approx(expected, rel=0.01)         # table vs computed section data
    assert got["N_b_Rd"] / 1e3 == pytest.approx(277, abs=3)          # kN, worked value


def test_critical_load_is_euler():
    sec = angle_properties("L 60×6")
    r = dc.flexural_buckling_resistance(sec.A, sec.I_v, 3.0, 275e6, E)
    assert r["N_cr"] == pytest.approx(math.pi ** 2 * E * sec.I_v / 9.0)


# ── class 4 handling ─────────────────────────────────────────────────────────

def test_outstand_reduction_is_one_up_to_the_limit_and_below_one_after():
    # lambda_p = (b/t) / (28.4 eps sqrt(0.43)); S355: eps = 0.814 -> limit b/t = 0.748 * 15.16 = 11.3
    assert dc.outstand_reduction(10, 355e6) == 1.0
    assert dc.outstand_reduction(11.2, 355e6) == 1.0
    rho = dc.outstand_reduction(20, 355e6)
    lam_p = 20 / (28.4 * math.sqrt(235 / 355) * math.sqrt(0.43))
    assert rho == pytest.approx((lam_p - 0.188) / lam_p ** 2) and rho < 1


def test_class_3_limit_for_angles():
    assert dc.angle_is_class_3_or_better(0.100, 0.010, 275e6)        # b/t 10 <= 11.5*0.924 = 10.6
    assert not dc.angle_is_class_3_or_better(0.100, 0.010, 355e6)    # 10 > 11.5*0.814 = 9.36


def test_class_4_angle_with_full_effective_area_is_still_checked():
    r = dc.check_angle(angle_properties("L 100×10"), 100e3, 0.0, 2.0, 355e6, E, False)
    assert r.checked and any("class 4 limit exceeded but" in n for n in r.notes)


def test_slender_angle_is_not_checked_rather_than_guessed():
    slender = SimpleNamespace(name="slender", a=0.2, t=0.01, A=39e-4, I_v=1e-6, W_u=1e-5, W_v=1e-5)
    r = dc.check_angle(slender, 50e3, 0.0, 2.0, 355e6, E, False)
    assert not r.checked and "class 4" in r.notes[0]


# ── tension, bending, interaction note ───────────────────────────────────────

def test_tension_is_gross_section_yield():
    sec = angle_properties("L 100×10")
    r = dc.check_angle(sec, -150e3, 0.0, 2.0, 355e6, E, False)
    assert r.governing == "Tension"
    assert r.eta == pytest.approx(150e3 / (sec.A * 355e6))


def test_compression_governed_by_buckling_not_squash_load():
    sec = angle_properties("L 100×10")
    r = dc.check_angle(sec, 150e3, 0.0, 2.0, 355e6, E, False)
    squash = 150e3 / (sec.A * 355e6)
    assert r.governing == "Buckling" and r.eta > 1.5 * squash


def test_bending_ratio_is_added_and_reported_separately():
    sec = angle_properties("L 100×10")
    r = dc.check_angle(sec, 100e3, 1.0e3, 2.0, 355e6, E, True)
    m_rd = min(sec.W_u, sec.W_v) * 355e6
    rows = {row["check"]: row for row in r.rows}
    assert rows["Bending M (elastic)"]["capacity"] == pytest.approx(m_rd)
    assert r.eta == pytest.approx(rows["Axial N (buckling)"]["eta"] / 100 + 1.0e3 / m_rd)
    assert any("§6.3.3" in n for n in r.notes)


def test_bar_members_carry_no_bending_term():
    sec = angle_properties("L 80×8")
    m = _member(sec, ElementType.BAR)
    r = dc.check_member(m, 50e3, 99e3, 3.0)
    assert [row["check"] for row in r.rows] == ["Axial N (buckling)"]


# ── recognising the section ──────────────────────────────────────────────────

def _member(sec, etype=ElementType.BEAM, fy=275e6):
    m = MemberData(id=1, node_i=0, node_j=1, element_type=etype)
    m.E, m.fy, m.A, m.I, m.I_y = E, fy, sec.A, sec.I_v, sec.I_u
    return m


def test_every_library_angle_is_recognised_as_itself():
    for sec in ANGLE_SECTIONS.values():
        if sec.kind != "equal":
            continue
        assert dc.identify_angle(sec.A, sec.I_v, sec.I_u).name == sec.name


def test_strong_and_weak_axis_order_does_not_matter():
    sec = angle_properties("L 120×12")
    assert dc.identify_angle(sec.A, sec.I_v, sec.I_u) is dc.identify_angle(sec.A, sec.I_u, sec.I_v)


def test_unknown_section_is_not_an_angle():
    assert dc.identify_angle(0.005381, 8.356e-5, 6.04e-6) is None      # an IPE 300-like section


# ── the dispatcher ───────────────────────────────────────────────────────────

def test_dispatcher_uses_the_angle_check_for_steel_angles():
    m = _member(angle_properties("L 100×10"), fy=355e6)
    r = dc.check_member(m, 150e3, 0.0, 2.0)
    assert r.governing == "Buckling" and r.rows[0]["check"] == "Axial N (buckling)"


def test_other_steel_gets_cross_section_only_and_says_so():
    m = MemberData(id=1, node_i=0, node_j=1)
    m.E, m.fy, m.A, m.I, m.W_pl = E, 355e6, 0.005381, 8.356e-5, 628e-6
    r = dc.check_member(m, 100e3, 0.0, 5.0)
    assert r.checked and any("buckling is not checked" in n for n in r.notes)


def test_concrete_keeps_its_en1992_resistance_and_says_slenderness_is_open():
    m = MemberData(id=1, node_i=0, node_j=1)
    m.E, m.fy, m.A, m.As_tension, m.fyk = 33e9, 30e6, 0.09, 0.0012, 500e6
    r = dc.check_member(m, 500e3, 0.0, 3.0)
    n_rd = 0.09 * 30e6 / 1.5 + 0.0012 * 500e6 / 1.15
    assert r.eta == pytest.approx(500e3 / n_rd)
    assert any("§5.8" in n for n in r.notes)


def test_member_without_capacity_data_is_not_checked():
    m = MemberData(id=1, node_i=0, node_j=1)
    m.E, m.A = 10e9, 0.01                                  # timber: no axial check
    assert not dc.check_member(m, 1e3, 0.0, 2.0).checked


def test_zero_length_is_not_checked():
    assert not dc.check_angle(angle_properties("L 50×5"), 1e3, 0.0, 0.0, 275e6, E, False).checked
