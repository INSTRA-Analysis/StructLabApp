"""Auto-generated combinations against an independent statement of EN 1990 6.10 / Table A1.2(B).

The oracle below does not share code with ui_qt.combinations: it enumerates every assignment of
a factor to every variable action and keeps the ones EN 1990 asks for, then compares them with
what the generator produced.

Factors (EN 1990 Table A1.1 / A1.2(B), recommended values): gamma_G,sup = 1.35, gamma_G,inf =
1.00, gamma_Q = 1.50; psi0 imposed 0.7, wind 0.6, snow 0.5; psi2 imposed 0.3, wind 0, snow 0.2.
"""

import itertools

import pytest

from ui_qt.combinations import auto_generate_en1990
from ui_qt.model_state import ModelState

PSI0 = {"Q": 0.7, "W": 0.6, "S": 0.5}
PSI2 = {"Q": 0.3, "W": 0.0, "S": 0.2}
GAMMA_SUP, GAMMA_INF, GAMMA_Q = 1.35, 1.00, 1.50


def _state(cases):
    """cases: (name, category, exclusive_group)."""
    s = ModelState()
    s.load_cases.clear()
    s._next_case_id = 0
    for name, cat, grp in cases:
        s.add_load_case(name, cat).exclusive_group = grp
    s.add_node(0, 0, 0); s.add_node(1, 0, 0); s.add_member(0, 1)
    return s


def _freeze(factors):
    return frozenset((cid, round(f, 9)) for cid, f in factors.items() if abs(f) > 1e-12)


def _oracle(state, limit_state):
    perm = [c for c in state.load_cases if c.category == "G"]
    var = [c for c in state.load_cases if c.category != "G"]
    out = set()

    def valid_alternatives(assign):
        groups = {}
        for i, f in enumerate(assign):
            if f > 0 and var[i].exclusive_group:
                groups[var[i].exclusive_group] = groups.get(var[i].exclusive_group, 0) + 1
        return all(n == 1 for n in groups.values())

    if limit_state == "ULS":
        if perm:                                  # every variable action favourable: absent
            out.add(_freeze({c.id: GAMMA_SUP for c in perm}))
        for g in (GAMMA_SUP, GAMMA_INF):
            for assign in itertools.product(*[(0.0, GAMMA_Q * PSI0[c.category], GAMMA_Q) for c in var]):
                # a companion is present only where unfavourable (6.4.3.2): any subset
                if sum(1 for f in assign if f == GAMMA_Q) != 1 or not valid_alternatives(assign):
                    continue
                out.add(_freeze({**{c.id: g for c in perm}, **{c.id: f for c, f in zip(var, assign)}}))
    else:                                         # SLS characteristic
        for assign in itertools.product(*[(0.0, PSI0[c.category], 1.0) for c in var]):
            if sum(1 for f in assign if f == 1.0) != 1 or not valid_alternatives(assign):
                continue
            out.add(_freeze({**{c.id: 1.0 for c in perm}, **{c.id: f for c, f in zip(var, assign)}}))
    return out


CASE_SETS = {
    "tower": [("Self weight", "G", ""), ("Conductor weight", "G", ""), ("Ice", "Q", ""),
              ("Wind +X", "W", "Wind"), ("Wind -X", "W", "Wind")],
    "building": [("Dead", "G", ""), ("Imposed", "Q", ""), ("Wind", "W", ""), ("Snow", "S", "")],
    "one permanent, one variable": [("G", "G", ""), ("Q", "Q", "")],
    "alternatives of two kinds": [("G", "G", ""), ("W+", "W", "w"), ("W-", "W", "w"),
                                  ("S+", "S", "s"), ("S-", "S", "s")],
    "variable actions only": [("Q", "Q", ""), ("W", "W", "")],
}


@pytest.mark.parametrize("name", CASE_SETS)
def test_uls_combinations_are_exactly_en1990_6_10(name):
    s = _state(CASE_SETS[name])
    got = [c for c in auto_generate_en1990(s) if c.limit_state == "ULS"]
    assert {_freeze(c.factors) for c in got} == _oracle(s, "ULS")
    assert len({_freeze(c.factors) for c in got}) == len(got)          # no duplicates


@pytest.mark.parametrize("name", CASE_SETS)
def test_sls_characteristic_combinations_match_en1990_6_14(name):
    s = _state(CASE_SETS[name])
    generated = auto_generate_en1990(s)
    char = [c for c in generated if c.limit_state == "SLS" and c.name.startswith("SLS Char")]
    assert {_freeze(c.factors) for c in char} == _oracle(s, "SLS")


@pytest.mark.parametrize("name", CASE_SETS)
def test_quasi_permanent_uses_psi2(name):
    s = _state(CASE_SETS[name])
    qp = [c for c in auto_generate_en1990(s) if c.name.startswith("SLS Quasi")]
    assert len(qp) == 1
    by_name = {c.id: c for c in s.load_cases}
    for cid, f in qp[0].factors.items():
        c = by_name[cid]
        assert f == pytest.approx(1.0 if c.category == "G" else PSI2[c.category])
    for c in s.load_cases:                       # psi2 = 0 actions are absent
        if c.category != "G" and PSI2[c.category] == 0:
            assert c.id not in qp[0].factors


def test_tower_uls_combinations_written_out():
    s = _state(CASE_SETS["tower"])
    ids = {c.name: c.id for c in s.load_cases}
    uls = {_freeze(c.factors) for c in auto_generate_en1990(s) if c.limit_state == "ULS"}
    G, C, I, WP, WM = (ids[n] for n in ("Self weight", "Conductor weight", "Ice", "Wind +X", "Wind -X"))
    expected = {_freeze({G: 1.35, C: 1.35})}                          # permanent load alone
    for g in (1.35, 1.0):
        expected.add(_freeze({G: g, C: g, I: 1.5}))                     # ice leading, no wind
        for w in (WP, WM):
            expected.add(_freeze({G: g, C: g, I: 1.5, w: 0.9}))         # ice leading, wind companion
            expected.add(_freeze({G: g, C: g, I: 1.05, w: 1.5}))        # wind leading, ice companion
            expected.add(_freeze({G: g, C: g, w: 1.5}))                 # wind leading, no ice
    assert uls == expected and len(uls) == 15


def test_favourable_permanent_combinations_exist_only_with_variable_actions():
    s = _state([("G", "G", "")])
    names = [c.name for c in auto_generate_en1990(s)]
    assert names == ["ULS: 1.35G", "SLS: 1.0G"]


def test_permanent_alone_governs_where_the_wind_relieves_the_member():
    """The portal of guide chapter 9.1: at the windward eave 1.35G gives more moment than
    1.35G + 1.5W, so leaving 1.35G out would under-design that column."""
    import sdk as sl
    m = sl.Model()
    n = [m.add_node(0, 0, 0), m.add_node(0, 0, 4.5), m.add_node(8, 0, 4.5), m.add_node(8, 0, 0)]
    m.fixed(n[0]); m.fixed(n[3])
    mem = [m.add_member(n[i], n[i + 1], E=210e9, A=5381e-6, I=8356e-8) for i in range(3)]
    m.add_udl(mem[1], 10e3, lc="default")            # the model's own permanent (G) case
    m.add_load_case("Wind", "W")
    m.add_point_load(n[1], Fx=15e3, lc="Wind")
    eave = {lc: m.solve(lc).member_forces(mem[0])["M_j"] for lc in ("default", "Wind")}
    ids = {c.name: c.id for c in m._state.load_cases}
    uls = [c.factors for c in auto_generate_en1990(m._state) if c.limit_state == "ULS"]
    assert {ids["default"]: 1.35} in uls
    alone = 1.35 * eave["default"]
    with_wind = 1.35 * eave["default"] + 1.5 * eave["Wind"]
    assert abs(alone) == pytest.approx(56.1e3, rel=1e-3)
    assert abs(with_wind) < abs(alone)


def test_wind_without_ice_governs_the_uplift_of_a_tower_leg():
    """Ice adds weight, so it relieves a leg lifted by the wind: the governing combination is
    1.0G + 1.5W with the ice left out, which the generator used to miss (EN 1990 6.4.3.2)."""
    s = _state(CASE_SETS["tower"])
    ids = {c.name: c.id for c in s.load_cases}
    # Axial force in the windward leg per unit case (kN, tension +): weight compresses it,
    # ice compresses it more, wind lifts it.
    leg = {ids["Self weight"]: -40.0, ids["Conductor weight"]: -20.0, ids["Ice"]: -30.0,
           ids["Wind +X"]: 90.0, ids["Wind -X"]: -90.0}
    uls = [c for c in auto_generate_en1990(s) if c.limit_state == "ULS"]
    tension = {c.name: sum(f * leg[cid] for cid, f in c.factors.items()) for c in uls}
    worst = max(tension, key=tension.get)
    assert ids["Ice"] not in next(c for c in uls if c.name == worst).factors
    assert tension[worst] == pytest.approx(-60.0 + 1.5 * 90.0)               # 75 kN
    with_ice = max(v for n, v in tension.items() if "Ice" in n)
    assert with_ice == pytest.approx(-60.0 + 1.5 * 90.0 - 1.05 * 30.0)       # 43.5 kN: unsafe


def test_regeneration_replaces_the_automatic_set_and_keeps_manual_ones():
    s = _state(CASE_SETS["tower"])
    manual = s.add_combination("mine", "ULS")
    first = len(auto_generate_en1990(s))
    second = len(auto_generate_en1990(s))
    assert first == second == 23                 # 15 ULS + 7 SLS characteristic + 1 quasi-permanent
    assert manual in s.combinations


def test_a_seismic_case_from_an_older_file_is_left_out():
    """StructLab has no seismic design situation yet (EN 1990 6.4.3.4): an "E" case keeps its
    loads but is neither combined automatically nor pattern-loaded, and the window says so."""
    from ui_qt.combinations import cases_left_out
    from ui_qt.model_state import LOAD_CATEGORIES
    from ui_qt.pattern_loading import detect_pattern_loading
    assert "E" not in LOAD_CATEGORIES                  # not offered for new cases
    with_e = _state([("G", "G", ""), ("Q", "Q", ""), ("Quake", "E", "")])
    without_e = _state([("G", "G", ""), ("Q", "Q", "")])
    quake = with_e.load_cases[2]
    got = {(c.name.replace("Quake", ""), _freeze(c.factors)) for c in auto_generate_en1990(with_e)}
    assert all(quake.id not in c.factors for c in with_e.combinations)
    assert got == {(c.name, _freeze(c.factors)) for c in auto_generate_en1990(without_e)}
    assert cases_left_out(with_e) == [quake] and cases_left_out(without_e) == []
    from ui_qt.model_state import DistLoad, MemberLoad
    a, b = with_e.add_node(2, 0, 0).id, with_e.add_node(3, 0, 0).id
    m1, m2 = with_e.add_member(1, a).id, with_e.add_member(a, b).id
    for mid in (m1, m2):
        quake.set_member_load(mid, MemberLoad(dist_loads=[DistLoad("w", 1e3, 1e3)]))
    assert not detect_pattern_loading(with_e).needed
