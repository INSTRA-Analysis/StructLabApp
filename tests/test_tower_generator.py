"""The parametric tower generator (examples/generate_l8_tower.py).

Every preset must build a clean, stable, solvable model whose overall dimensions match
the published envelope; D30 additionally follows its drawing (asymmetric arms).
"""

import importlib.util
import sys
import math
import warnings
from pathlib import Path

import numpy as np
import pytest

import sdk as sl
from ui_qt.model_state import NodeLoad

_PATH = Path(__file__).resolve().parents[1] / "examples" / "generate_l8_tower.py"
_spec = importlib.util.spec_from_file_location("generate_l8_tower", _PATH)
gen = importlib.util.module_from_spec(_spec)
sys.modules["generate_l8_tower"] = gen          # dataclasses needs the module registered
_spec.loader.exec_module(gen)

pytestmark = pytest.mark.filterwarnings("ignore")


@pytest.fixture(scope="module", params=sorted(gen.TOWERS))
def tower(request):
    spec = gen.TOWERS[request.param]
    return spec, gen.build(spec)


def _length(state, m):
    a, b = state.get_node(m.node_i), state.get_node(m.node_j)
    return math.dist((a.x, a.y, a.z), (b.x, b.y, b.z))


def test_envelope_matches_published_dimensions(tower):
    spec, state = tower
    zs = [n.z for n in state.nodes]
    assert max(zs) == pytest.approx(spec.height)
    base = [n for n in state.nodes if n.z == 0.0]
    assert len(base) == 4
    assert max(n.x for n in base) - min(n.x for n in base) == pytest.approx(
        spec.leg_spacing[0][1], abs=1e-3)
    widest = max(a.reach_minus + a.reach_plus for a in spec.arms)
    assert max(n.x for n in state.nodes) - min(n.x for n in state.nodes) == pytest.approx(
        widest, abs=1e-3)


def test_no_degenerate_or_duplicate_members(tower):
    _, state = tower
    seen = set()
    for m in state.members:
        assert _length(state, m) > 0.05, f"member {m.id} is (nearly) zero length"
        key = (min(m.node_i, m.node_j), max(m.node_i, m.node_j))
        assert key not in seen, f"duplicate member between nodes {key}"
        seen.add(key)
    used = {n for m in state.members for n in (m.node_i, m.node_j)}
    assert used == {n.id for n in state.nodes}, "floating nodes"


def test_stable_and_balanced_under_self_weight_and_lateral_load(tower):
    """Solving must not raise a mechanism error; reactions must balance the loads."""
    spec, state = tower
    state = gen.build(spec)                       # fresh copy: we add loads to it
    tips = [n for lst in gen.ATTACH.values() for n in lst]
    for nid in tips:
        state.load_cases[0].set_node_load(nid, NodeLoad(fx=3e3, fy=4e3, fz=-5e3))
    result = sl.Model.from_state(state).solve()   # raises UnstableStructureError if a mechanism
    reactions = result._cache["reactions"].reshape(-1, 6)
    weight = sum(m.density * m.A * 9.81 * _length(state, m) for m in state.members)
    assert reactions[:, 0].sum() == pytest.approx(-3e3 * len(tips), rel=1e-9)
    assert reactions[:, 1].sum() == pytest.approx(-4e3 * len(tips), rel=1e-9)
    assert reactions[:, 2].sum() == pytest.approx(weight + 5e3 * len(tips), rel=1e-9)
    moves = np.linalg.norm(result._cache["displacements"].reshape(-1, 6)[:len(state.nodes), :3],
                           axis=1)
    worst = state.nodes[int(moves.argmax())]
    assert moves.max() < 0.25, f"{spec.name}: {moves.max():.2f} m under a modest load - too soft"
    # The most flexible point must be the top of the shaft, never a loose interior node
    # (a floppy face-centre node once showed up as 1 m of movement in D90).
    assert worst.z > 0.9 * spec.height, f"{spec.name}: softest node is at z={worst.z:.1f}"


def test_d30_arms_are_asymmetric_with_long_side_toward_minus_x():
    state = gen.build(gen.D30)
    for arm in gen.D30.arms:
        tip_x = [state.get_node(n).x for lst in (gen.ATTACH[f"{arm.name} L"],
                                                  gen.ATTACH[f"{arm.name} R"]) for n in lst]
        assert min(tip_x) == pytest.approx(-arm.reach_minus, abs=1e-3)
        assert max(tip_x) == pytest.approx(arm.reach_plus, abs=1e-3)
        assert arm.reach_minus > arm.reach_plus


def test_every_group_has_a_section_and_is_used():
    state = gen.build(gen.D30)
    assert {m.group for m in state.members} == set(gen.GROUPS)


def test_k_levels_are_restrained_out_of_plane():
    """Face-centre nodes (apex of V / LAMBDA) are tied across the tower by plan bars."""
    state = gen.build(gen.D30)
    plan = [m for m in state.members if m.group == "Plan bracing"]
    k_levels = {round(n.z, 3) for n in state.nodes
                if abs(n.x) < 1e-6 and abs(n.y) > 1e-6 and 0 < n.z < 20}
    through = {round(state.get_node(m.node_i).z, 3) for m in plan
               if abs(state.get_node(m.node_i).x) < 1e-6 or abs(state.get_node(m.node_i).y) < 1e-6}
    assert k_levels <= through


# ── cable load cases ──────────────────────────────────────────────────────────

def _case(state, name):
    return next(lc for lc in state.load_cases if lc.name == name)


def _total(case, comp: str) -> float:
    return sum(getattr(nl, comp) for nl in case.node_loads.values())


def test_cable_cases_exist_with_the_right_categories():
    state = gen.build(gen.D30)
    names = [(lc.name, lc.category) for lc in state.load_cases]
    assert names == [("Self weight", "G"), ("Conductor weight", "G"), ("Ice", "Q"),
                     ("Wind +X", "W"), ("Wind -X", "W")]
    assert [lc.name for lc in state.load_cases if lc.include_self_weight] == ["Self weight"]


def test_no_cable_cases_when_switched_off():
    state = gen.build(gen.D30, cable=None)
    assert [lc.name for lc in state.load_cases] == ["Self weight"]


def test_cable_load_totals_match_the_assumptions():
    a = gen.CableAssumptions()
    ld = gen.cable_loads(a)
    state = gen.build(gen.D30, a)
    n_phase = 6                                       # 3 arm levels x 2 sides
    weight = _case(state, "Conductor weight")
    ice, wind_p, wind_m = (_case(state, n) for n in ("Ice", "Wind +X", "Wind -X"))
    assert _total(weight, "fz") == pytest.approx(
        -(n_phase * ld["phase"]["vertical"] + ld["earth"]["vertical"]) * 1e3, rel=1e-9)
    assert _total(ice, "fz") == pytest.approx(
        -(n_phase * ld["phase"]["ice"] + ld["earth"]["ice"]) * 1e3, rel=1e-9)
    assert _total(wind_p, "fx") == pytest.approx(
        (n_phase * ld["phase"]["wind"] + ld["earth"]["wind"]) * 1e3, rel=1e-9)
    assert _total(wind_m, "fx") == pytest.approx(-_total(wind_p, "fx"), rel=1e-12)
    for case, comp in ((weight, "fx"), (ice, "fx"), (wind_p, "fz"), (wind_m, "fz")):
        assert _total(case, comp) == 0.0              # wind is horizontal, weight is vertical
    for case in (weight, ice, wind_p, wind_m):
        assert _total(case, "fy") == 0.0 and not any(
            nl.moment_x or nl.moment_y or nl.moment for nl in case.node_loads.values())


def test_loads_sit_only_on_the_attachment_nodes_and_are_shared_equally():
    a = gen.CableAssumptions()
    ld = gen.cable_loads(a)
    state = gen.build(gen.D30, a)
    attach = {n for ids in gen.ATTACH.values() for n in ids}
    weight = _case(state, "Conductor weight")
    assert set(weight.node_loads) == attach and len(attach) == 6 * 2 + 4
    for label, ids in gen.ATTACH.items():
        kind = "earth" if label == "Earth wire" else "phase"
        for nid in ids:
            assert weight.node_loads[nid].fz == pytest.approx(
                -ld[kind]["vertical"] * 1e3 / len(ids), rel=1e-9)


def test_phase_attachments_are_the_arm_tips():
    state = gen.build(gen.D30)
    for arm in gen.D30.arms:
        for side, reach in (("L", arm.reach_minus), ("R", arm.reach_plus)):
            for nid in gen.ATTACH[f"{arm.name} {side}"]:
                n = state.get_node(nid)
                assert abs(n.x) == pytest.approx(reach, abs=1e-3)
                assert n.z == pytest.approx(arm.z_bottom, abs=1e-3)


@pytest.mark.parametrize("case_name", ["Conductor weight", "Ice", "Wind +X", "Wind -X"])
def test_each_cable_case_solves_with_balanced_reactions(case_name):
    state = gen.build(gen.D30)
    case = _case(state, case_name)
    result = sl.Model.from_state(state).solve(lc=case_name)
    reactions = result._cache["reactions"].reshape(-1, 6)
    for comp, idx in (("fx", 0), ("fy", 1), ("fz", 2)):
        assert reactions[:, idx].sum() == pytest.approx(-_total(case, comp), abs=1e-3)
    moves = np.linalg.norm(result._cache["displacements"].reshape(-1, 6)[:len(state.nodes), :3], axis=1)
    assert moves.max() < 0.25


def test_opposite_wind_cases_give_exactly_opposite_results():
    """Linear analysis: Wind -X is the mirror load set of Wind +X, so results negate."""
    state = gen.build(gen.D30)
    model = sl.Model.from_state(state)
    plus = model.solve(lc="Wind +X")._cache["displacements"]
    minus = model.solve(lc="Wind -X")._cache["displacements"]
    assert minus == pytest.approx(-plus, abs=1e-12)
