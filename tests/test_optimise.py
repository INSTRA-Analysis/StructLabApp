"""Optimise-by-group: lightest equal angle per group within a utilisation target."""

import pytest

from ui_qt import design_checks as dc
from ui_qt.angle_sections import angle_properties
from ui_qt.model_state import ElementType, LoadCombination, ModelState, NodeLoad, SupportType
from ui_qt.optimise import apply_section, equal_angles, optimise_groups

E, FY = 210e9, 275e6


def _bars():
    """Two independent determinate bars: 'comp' pushed by 80 kN over 3 m, 'tens' pulled by 40 kN over 2 m."""
    s = ModelState()
    a, b = s.add_node(0, 0, 0), s.add_node(3, 0, 0)
    c, d = s.add_node(0, 5, 0), s.add_node(2, 5, 0)
    for n in (a, c):
        n.support_type = SupportType.PIN
    for n in (b, d):
        n.support_type = SupportType.ROLLER
    big = angle_properties("L 200×20")
    for (i, j, grp) in ((a, b, "comp"), (c, d, "tens")):
        m = s.add_member(i.id, j.id)
        m.group, m.element_type, m.E, m.fy, m.density = grp, ElementType.BAR, E, FY, 7850.0
        apply_section(m, big)
    case = s.load_cases[0]
    case.set_node_load(b.id, NodeLoad(fx=-80e3))
    case.set_node_load(d.id, NodeLoad(fx=+40e3))
    combo = LoadCombination(id=1, name="ULS", limit_state="ULS", factors={case.id: 1.0})
    s.combinations.append(combo)
    return s, [combo]


def _lightest(n_ed, length, target, floor_area=0.0, min_i=0.0):
    """Independent search: first library angle (by area) passing the check."""
    for sec in equal_angles():
        if sec.A < floor_area or (sec.I_v / sec.A) ** 0.5 < min_i:
            continue
        c = dc.check_angle(sec, n_ed, 0.0, length, FY, E, False)
        if c.eta is not None and c.eta <= target:
            return sec
    raise AssertionError("nothing passes")


def test_each_group_gets_the_lightest_passing_angle_and_it_converges():
    s, combos = _bars()
    r = optimise_groups(s, combos, target=0.85)
    want = {"comp": _lightest(80e3, 3.0, 0.85), "tens": _lightest(-40e3, 2.0, 0.85)}
    got = {g.group: g for g in r.groups}
    assert got["comp"].after == want["comp"].name and got["tens"].after == want["tens"].name
    assert r.converged and r.iterations <= 3
    assert r.mass_after < r.mass_before / 5                          # started from L 200x20 everywhere
    for g in got.values():
        assert g.eta_after <= 0.85 + 1e-9 and g.eta_before < g.eta_after


def test_the_next_smaller_section_would_not_pass():
    s, combos = _bars()
    optimise_groups(s, combos, target=0.85)
    chosen = dc.identify_angle(*[s.members[0].A, s.members[0].I, s.members[0].I])
    smaller = [x for x in equal_angles() if x.A < chosen.A][-1]
    assert dc.check_angle(smaller, 80e3, 0.0, 3.0, FY, E, False).eta > 0.85


def test_buckling_not_squash_load_decides_the_compression_bar():
    s, combos = _bars()
    optimise_groups(s, combos, target=0.85)
    comp = next(m for m in s.members if m.group == "comp")
    squash = 80e3 / FY / 0.85
    assert comp.A > 1.5 * squash                                     # a section sized on N/(A fy) alone would buckle


def test_minimum_section_is_respected():
    s, combos = _bars()
    optimise_groups(s, combos, target=0.85, min_section="L 100×10")
    assert all(m.A >= angle_properties("L 100×10").A - 1e-12 for m in s.members)


def test_slenderness_limit_forces_a_larger_section():
    s, combos = _bars()
    free = optimise_groups(s, combos, target=0.85)
    s2, combos2 = _bars()
    limited = optimise_groups(s2, combos2, target=0.85, max_slenderness=100)
    tens_free = next(g for g in free.groups if g.group == "tens")
    tens_lim = next(g for g in limited.groups if g.group == "tens")
    assert tens_lim.slenderness <= 100 + 1e-9
    assert angle_properties(tens_lim.after).A > angle_properties(tens_free.after).A


def test_ordered_groups_never_get_smaller_down_the_chain():
    s, combos = _bars()
    # 'comp' needs the bigger section; ask for tens >= comp
    r = optimise_groups(s, combos, target=0.85, ordered=[["tens", "comp"]])
    a = {g.group: angle_properties(g.after).A for g in r.groups}
    assert a["tens"] >= a["comp"]


def test_groups_that_are_not_library_angles_are_left_alone():
    s, combos = _bars()
    odd = s.members[1]
    odd.A, odd.I, odd.I_y = 0.005381, 8.356e-5, 8.356e-5            # an IPE-like section
    r = optimise_groups(s, combos, target=0.85)
    tens = next(g for g in r.groups if g.group == "tens")
    assert "left alone" in tens.note and odd.A == 0.005381


def test_only_uls_combinations_count():
    s, combos = _bars()
    with pytest.raises(ValueError):
        optimise_groups(s, [LoadCombination(id=2, name="S", limit_state="SLS", factors={0: 1.0})])


def test_apply_section_keeps_principal_axis_assignment():
    from ui_qt.model_state import MemberData
    sec = angle_properties("L 150×15")
    leg = MemberData(id=0, node_i=0, node_j=1)
    leg.I, leg.I_y = 1.0, 2.0                                        # a corner leg on principal axes
    apply_section(leg, sec)
    assert (leg.I, leg.I_y) == (sec.I_v, sec.I_u)
    brace = MemberData(id=1, node_i=0, node_j=1)
    brace.I = brace.I_y = 1.0
    apply_section(brace, sec)
    assert brace.I == brace.I_y == sec.I_v
