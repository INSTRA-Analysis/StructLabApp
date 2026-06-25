"""Tests for the 2D analysis mode.

2D is the engine's native XY plane: nodes have z == 0 and Y is vertical, so the
builder needs no remap. The only mode-specific transform is ModelState.swap_yz(),
applied when toggling 2D⇄3D so a planar model keeps standing (height moves Y↔Z).
"""

from __future__ import annotations

import numpy as np

from ui_qt.model_state import ModelState, SupportType, NodeLoad, MemberLoad
from ui_qt.model_builder import build_model
from ui_qt.solve_actions import solve_engine

E, A, I = 210e9, 8.446e-3, 2.313e-4   # IPE 400


def _portal_2d() -> ModelState:
    """Single-bay portal in the native 2D XY plane (Y vertical, z=0)."""
    s = ModelState(); s.analysis_mode = "2D"
    H, L = 4.0, 6.0
    n0 = s.add_node(0, 0, 0); n0.support_type = SupportType.PIN
    n1 = s.add_node(0, H, 0)
    n2 = s.add_node(L, H, 0)
    n3 = s.add_node(L, 0, 0); n3.support_type = SupportType.PIN
    for a, b in [(n0, n1), (n1, n2), (n3, n2)]:
        m = s.add_member(a.id, b.id); m.E, m.A, m.I = E, A, I
    s.active_case.set_member_load(s.members[1].id, MemberLoad(w_start=8000, w_end=8000))
    s.active_case.set_node_load(n1.id, NodeLoad(fx=15000, fy=-20000))
    s.active_case.set_node_load(n2.id, NodeLoad(fy=-20000, moment=12000))
    return s


def test_2d_builds_native_3dof():
    """A 2D model (all z==0) builds as a clean 3-DOF model and solves."""
    s = _portal_2d()
    model, mm = build_model(s, s.active_case)
    assert model.dofs_per_node == 3
    cache = solve_engine(model, mm, s)
    assert np.all(np.isfinite(cache["displacements"]))


def test_2d_vertical_equilibrium():
    s = _portal_2d()
    cache = solve_engine(*build_model(s, s.active_case), s)
    R = cache["reactions"]
    react_y = sum(R[d] for d in range(1, len(R), 3))   # vertical = Y = index 1
    applied = 2 * 20_000 + 8_000 * 6.0
    assert abs(react_y - applied) < 1.0


def test_overhang_beam_2d():
    """User's case: simply-supported beam with two overhangs, point load shifted
    toward the first support — native 2D (XY)."""
    s = ModelState(); s.analysis_mode = "2D"
    xs = [(0, None), (1.5, SupportType.PIN), (3.0, None),
          (6.5, SupportType.ROLLER), (8.0, None)]
    nodes = []
    for x, sup in xs:
        n = s.add_node(x, 0.0, 0.0)
        if sup:
            n.support_type = sup
        nodes.append(n)
    for i in range(4):
        m = s.add_member(nodes[i].id, nodes[i + 1].id); m.E, m.A, m.I = E, A, I
        s.active_case.set_member_load(m.id, MemberLoad(w_start=20_000, w_end=20_000))
    s.active_case.set_node_load(nodes[2].id, NodeLoad(fy=-30_000))   # vertical, shifted
    cache = solve_engine(*build_model(s, s.active_case), s)
    assert np.all(np.isfinite(cache["displacements"]))
    react_y = sum(cache["reactions"][d] for d in range(1, len(cache["reactions"]), 3))
    assert abs(react_y - (20_000 * 8.0 + 30_000)) < 1.0


def test_swap_yz_is_involution_and_moves_height():
    """swap_yz moves the vertical Y→Z (and fy→fz); applying it twice is identity."""
    s = ModelState(); s.analysis_mode = "2D"
    n = s.add_node(2.0, 3.0, 0.0)
    s.active_case.set_node_load(n.id, NodeLoad(fx=5.0, fy=-7.0, moment=9.0))
    s.swap_yz()
    assert (n.x, n.y, n.z) == (2.0, 0.0, 3.0)              # height Y → Z
    nl = s.active_case.get_node_load(n.id)
    assert (nl.fy, nl.fz) == (0.0, -7.0)                   # vertical Fy → Fz
    assert (nl.moment, nl.moment_y) == (0.0, 9.0)
    s.swap_yz()                                            # back again
    assert (n.x, n.y, n.z) == (2.0, 3.0, 0.0)
    nl = s.active_case.get_node_load(n.id)
    assert (nl.fy, nl.fz) == (-7.0, 0.0)


def test_analysis_mode_roundtrip_and_backcompat():
    s = ModelState(); s.analysis_mode = "2D"
    assert s.mode_3d is False and s.is_2d is True
    s2 = ModelState.from_dict(s.to_dict())
    assert s2.analysis_mode == "2D" and s2.mode_3d is False
    legacy = s.to_dict(); legacy.pop("analysis_mode"); legacy["mode_3d"] = True
    assert ModelState.from_dict(legacy).analysis_mode == "3D"
