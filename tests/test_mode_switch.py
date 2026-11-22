"""2D <-> 3D switch: the model is rotated (+90° about X), never mirrored, so every load,
support and spring keeps its physical meaning.  A 2D solve and the 3D solve of the switched
model must describe the same deformation:  ux = ux,  uz(3D) = uy(2D),  θy(3D) = -θz(2D).

Regression: the switch used to swap Y and Z (a mirror), which reversed nodal moments and
'qy' distributed loads.
"""

import pytest

from ui_qt.model_builder import build_model
from ui_qt.model_state import DistLoad, MemberLoad, ModelState, NodeLoad, SupportType
from ui_qt.solve_actions import solve_engine

E, A, I = 210e9, 8e-3, 2e-4


def _l_frame(load) -> tuple[ModelState, list]:
    """Fixed column (Y up) with a beam on top ending on a vertical spring support."""
    s = ModelState()
    s.analysis_mode = "2D"
    base, knee, tip = s.add_node(0, 0, 0), s.add_node(0, 3, 0), s.add_node(4, 3, 0)
    base.support_type = SupportType.FIXED
    tip.support_type = SupportType.SPRING
    tip.spring_ky, tip.spring_ktheta = 4e6, 2e6
    for a, b in ((base, knee), (knee, tip)):
        m = s.add_member(a.id, b.id)
        m.E, m.A, m.I, m.I_y, m.J = E, A, I, I, 1e-5
    load(s, knee, tip, s.members[1])
    return s, [base, knee, tip]


def _solve(s):
    model, mm = build_model(s, s.active_case)
    return model.dofs_per_node, solve_engine(model, mm, s)


LOADS = {
    "tip moment": lambda s, k, t, m: s.active_case.set_node_load(t.id, NodeLoad(moment=10e3)),
    "knee moment and Fx": lambda s, k, t, m: s.active_case.set_node_load(k.id, NodeLoad(fx=8e3, moment=-6e3)),
    "qy upward on the beam": lambda s, k, t, m: s.active_case.set_member_load(
        m.id, MemberLoad(dist_loads=[DistLoad("qy", 5e3, 5e3)])),
    "qx on the beam": lambda s, k, t, m: s.active_case.set_member_load(
        m.id, MemberLoad(dist_loads=[DistLoad("qx", 2e3, 3e3)])),
    "w and Fy": lambda s, k, t, m: (
        s.active_case.set_member_load(m.id, MemberLoad(w_start=4e3, w_end=4e3)),
        s.active_case.set_node_load(t.id, NodeLoad(fy=-3e3))),
}


@pytest.mark.parametrize("name", list(LOADS))
def test_the_switched_model_deforms_the_same_way(name):
    s, nodes = _l_frame(LOADS[name])
    dpn2, c2 = _solve(s)
    s.rotate_axes("3D")
    s.analysis_mode = "3D"
    dpn3, c3 = _solve(s)
    assert (dpn2, dpn3) == (3, 6)
    d2, d3, r2, r3 = c2["displacements"], c3["displacements"], c2["reactions"], c3["reactions"]
    scale = max(abs(d2).max(), 1e-12)
    for n in nodes:
        ux, uy, thz = d2[n.id * 3: n.id * 3 + 3]
        assert d3[n.id * 6 + 0] == pytest.approx(ux, abs=1e-9 * scale)
        assert d3[n.id * 6 + 2] == pytest.approx(uy, abs=1e-9 * scale)
        assert d3[n.id * 6 + 4] == pytest.approx(-thz, abs=1e-9 * scale)
    base = nodes[0].id
    rscale = max(abs(r2).max(), 1.0)
    assert r3[base * 6 + 0] == pytest.approx(r2[base * 3 + 0], abs=1e-8 * rscale)
    assert r3[base * 6 + 2] == pytest.approx(r2[base * 3 + 1], abs=1e-8 * rscale)
    assert r3[base * 6 + 4] == pytest.approx(-r2[base * 3 + 2], abs=1e-8 * rscale)


@pytest.mark.parametrize("name", list(LOADS))
def test_a_round_trip_returns_the_identical_model(name):
    s, _ = _l_frame(LOADS[name])
    before = s.to_dict()
    s.rotate_axes("3D")
    s.rotate_axes("2D")
    assert s.to_dict() == before


def test_qy_upward_load_still_acts_upward_after_the_switch():
    s, (_b, _k, tip) = _l_frame(LOADS["qy upward on the beam"])
    _, c2 = _solve(s)
    assert c2["displacements"][tip.id * 3 + 1] > 0                     # lifts the tip in 2D
    s.rotate_axes("3D")
    s.analysis_mode = "3D"
    dl = s.active_case.get_member_load(s.members[1].id).dist_loads[0]
    assert (dl.direction, dl.w_start) == ("qz", -5e3)                  # qz is positive down
    _, c3 = _solve(s)
    assert c3["displacements"][tip.id * 6 + 2] > 0                     # and lifts it in 3D


def test_rotate_axes_rejects_an_unknown_mode():
    with pytest.raises(ValueError):
        ModelState().rotate_axes("4D")
