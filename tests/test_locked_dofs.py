"""Locked DOFs: a plane frame solved by the 3D engine with uy, θx, θz held at every node
gives exactly the 2D engine's results, and stays stable where a plain 3D solve does not."""

import numpy as np
import pytest

from solver.linear_solver import UnstableStructureError
from ui_qt.model_builder import build_model
from ui_qt.model_state import MemberLoad, ModelState, NodeLoad, SupportType
from ui_qt.solve_actions import solve_engine

PLANE_XZ = (1, 3, 5)
E, A, I = 210e9, 8e-3, 2e-4


def _pinned_portal() -> ModelState:
    """Pinned-base portal in 2D (Y up): sway in plane, but a mechanism out of plane in 3D."""
    s = ModelState()
    s.analysis_mode = "2D"
    n = [s.add_node(0, 0, 0), s.add_node(0, 4, 0), s.add_node(6, 4, 0), s.add_node(6, 0, 0)]
    n[0].support_type = n[3].support_type = SupportType.PIN
    for a, b in ((0, 1), (1, 2), (3, 2)):
        m = s.add_member(n[a].id, n[b].id)
        m.E, m.A, m.I, m.I_y, m.J = E, A, I, I, 1e-5
    s.active_case.set_node_load(n[1].id, NodeLoad(fx=15e3, moment=-4e3))
    s.active_case.set_member_load(s.members[1].id, MemberLoad(w_start=8e3, w_end=8e3))
    return s


def _plane_frame(s: ModelState):
    """Rotate the 2D model into XZ and solve it with the plane-frame locks."""
    s.rotate_axes("3D")
    s.analysis_mode = "3D"
    model, mm = build_model(s, s.active_case)
    model.locked_dofs = PLANE_XZ
    return solve_engine(model, mm, s)


def test_plane_frame_equals_the_2d_engine():
    s = _pinned_portal()
    c2 = solve_engine(*build_model(s, s.active_case), s)
    c3 = _plane_frame(s)
    d2, r2 = c2["displacements"], c2["reactions"]
    d3, r3 = c3["displacements"], c3["reactions"]
    n2 = len(d2) // 3
    d2n, d3n = d2.reshape(n2, 3), d3.reshape(-1, 6)[:n2]
    r2n, r3n = r2.reshape(n2, 3), r3.reshape(-1, 6)[:n2]
    sd, sr = abs(d2).max(), abs(r2).max()
    assert d3n[:, 0] == pytest.approx(d2n[:, 0], abs=1e-9 * sd)        # ux
    assert d3n[:, 2] == pytest.approx(d2n[:, 1], abs=1e-9 * sd)        # uz = uy(2D)
    assert d3n[:, 4] == pytest.approx(-d2n[:, 2], abs=1e-9 * sd)       # θy = -θz(2D)
    assert np.abs(d3n[:, [1, 3, 5]]).max() == 0.0                      # locked: exactly zero
    assert r3n[:, 0] == pytest.approx(r2n[:, 0], abs=1e-9 * sr)
    assert r3n[:, 2] == pytest.approx(r2n[:, 1], abs=1e-9 * sr)
    assert np.abs(c3["lock_forces"]).max() < 1e-9 * sr                 # nothing out of plane
    for m2, m3 in zip(c2["member_results"], c3["member_results"]):     # axial force too
        assert m3.N_i == pytest.approx(m2.N_i, abs=1e-9 * sr)


def test_without_the_locks_the_out_of_plane_mechanism_is_one_newton_away():
    """In-plane loads happen to solve (the mechanism is not excited), but the pinned portal
    has no out-of-plane stiffness: 1 N out of plane makes the plain 3D solve fail, while the
    plane frame takes it on a lock."""
    s = _pinned_portal()
    s.rotate_axes("3D")
    s.analysis_mode = "3D"
    s.active_case.set_node_load(s.nodes[1].id, NodeLoad(fy=1.0))
    model, mm = build_model(s, s.active_case)
    with pytest.raises(UnstableStructureError):
        solve_engine(model, mm, s)
    model.locked_dofs = PLANE_XZ
    c = solve_engine(model, mm, s)
    assert c["lock_forces"][s.nodes[1].id * 6 + 1] == pytest.approx(-1.0)


def test_an_out_of_plane_load_shows_up_as_a_lock_force_not_a_reaction():
    s = _pinned_portal()
    s.rotate_axes("3D")
    s.analysis_mode = "3D"
    knee = s.nodes[1]
    s.active_case.set_node_load(knee.id, NodeLoad(fy=2e3))            # out of the XZ plane
    model, mm = build_model(s, s.active_case)
    model.locked_dofs = PLANE_XZ
    c = solve_engine(model, mm, s)
    assert c["lock_forces"][knee.id * 6 + 1] == pytest.approx(-2e3)
    assert c["reactions"][1::6] == pytest.approx(0.0, abs=1e-9)


def test_locked_dofs_outside_the_node_size_are_refused():
    s = _pinned_portal()
    model, mm = build_model(s, s.active_case)                         # 2D: 3 DOF per node
    model.locked_dofs = (5,)
    with pytest.raises(ValueError):
        solve_engine(model, mm, s)
