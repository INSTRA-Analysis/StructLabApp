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

    def blocked(assign, i):
        grp = var[i].exclusive_group
        return bool(grp) and any(j != i and assign[j] > 0 and var[j].exclusive_group == grp
                                 for j in range(len(var)))

    def valid_alternatives(assign):
        groups = {}
        for i, f in enumerate(assign):
            if f > 0 and var[i].exclusive_group:
                groups[var[i].exclusive_group] = groups.get(var[i].exclusive_group, 0) + 1
        return all(n == 1 for n in groups.values())

    if limit_state == "ULS":
        for g in (GAMMA_SUP, GAMMA_INF):
            for assign in itertools.product(*[(0.0, GAMMA_Q * PSI0[c.category], GAMMA_Q) for c in var]):
                if sum(1 for f in assign if f == GAMMA_Q) != 1 or not valid_alternatives(assign):
                    continue
                if any(f == 0 and not blocked(assign, i) for i, f in enumerate(assign)):
                    continue                      # a companion that could act must act
                out.add(_freeze({**{c.id: g for c in perm}, **{c.id: f for c, f in zip(var, assign)}}))
    else:                                         # SLS characteristic
        for assign in itertools.product(*[(0.0, PSI0[c.category], 1.0) for c in var]):
            if sum(1 for f in assign if f == 1.0) != 1 or not valid_alternatives(assign):
                continue
            if any(f == 0 and not blocked(assign, i) for i, f in enumerate(assign)):
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


def test_tower_has_the_eight_uls_combinations_written_out():
    s = _state(CASE_SETS["tower"])
    ids = {c.name: c.id for c in s.load_cases}
    uls = {_freeze(c.factors) for c in auto_generate_en1990(s) if c.limit_state == "ULS"}
    G, C, I, WP, WM = (ids[n] for n in ("Self weight", "Conductor weight", "Ice", "Wind +X", "Wind -X"))
    expected = set()
    for g in (1.35, 1.0):
        for w in (WP, WM):
            expected.add(_freeze({G: g, C: g, I: 1.5, w: 0.9}))         # ice leading, wind companion
            expected.add(_freeze({G: g, C: g, I: 1.05, w: 1.5}))        # wind leading, ice companion
    assert uls == expected and len(uls) == 8


def test_favourable_permanent_combinations_exist_only_with_variable_actions():
    s = _state([("G", "G", "")])
    names = [c.name for c in auto_generate_en1990(s)]
    assert names == ["ULS: 1.35G", "SLS: 1.0G"]


def test_regeneration_replaces_the_automatic_set_and_keeps_manual_ones():
    s = _state(CASE_SETS["tower"])
    manual = s.add_combination("mine", "ULS")
    first = len(auto_generate_en1990(s))
    second = len(auto_generate_en1990(s))
    assert first == second == 13                 # 8 ULS + 4 SLS characteristic + 1 quasi-permanent
    assert manual in s.combinations
