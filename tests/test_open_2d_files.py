"""Phase 2: a 2D file opens as the same structure in 3D, a plane frame in the XZ plane.

Every kind of 2D file (current, older v2/v3 without a stored mode, legacy v1) opens as a 3D
plane frame with Z up, and solves to exactly the results the 2D engine gives the file.
3D files open untouched; ``keep_2d=True`` reads a file as stored.
"""

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest

from ui_qt.io import load_model, save_model
from ui_qt.model_builder import build_model
from ui_qt.model_state import ModelState, NodeLoad, SupportType
from ui_qt.solve_actions import solve_engine

TOL = 1e-9
GOLDEN_2D = ["continuous_beam_2d", "portal_frame_2d", "warren_truss_2d", "spring_supported_beam_2d"]


def _same_results(two_d: ModelState, plane: ModelState, axial_ends: bool = True) -> None:
    """The plane frame's results equal the 2D ones (ux, uz = uy, θy = -θz; reactions;
    member N, and V/M with the local-axis sign).  ``axial_ends=False`` compares the mean
    axial force instead of each end (self-weight: see the test below)."""
    c2 = solve_engine(*build_model(two_d, two_d.active_case), two_d)
    c3 = solve_engine(*build_model(plane, plane.active_case), plane)
    ids = [n.id for n in two_d.nodes]
    u2 = np.array([c2["displacements"][i * 3: i * 3 + 3] for i in ids])
    u3 = np.array([c3["displacements"][i * 6: i * 6 + 6] for i in ids])
    np.testing.assert_allclose(u3[:, [0, 2, 4]], u2 * [1, 1, -1], atol=TOL * np.abs(u2).max(), rtol=0)
    r2 = np.array([c2["reactions"][i * 3: i * 3 + 3] for i in ids])
    r3 = np.array([c3["reactions"][i * 6: i * 6 + 6] for i in ids])
    sf = max(np.abs(r2).max(), 1.0)
    np.testing.assert_allclose(r3[:, [0, 2, 4]], r2 * [1, 1, -1], atol=TOL * sf, rtol=0)
    flipped = plane._members_with_reversed_local_y()
    for md, a, b in zip(plane.members, c2["member_results"], c3["member_results"]):
        k = -1.0 if md.id in flipped else 1.0
        if axial_ends:
            assert (b.N_i, b.N_j) == pytest.approx((a.N_i, a.N_j), abs=TOL * sf)
        else:
            assert (b.N_i - b.N_j) / 2 == pytest.approx((a.N_i - a.N_j) / 2, abs=TOL * sf)
        assert (b.M_i, b.M_j) == pytest.approx((k * a.M_i, k * a.M_j), abs=TOL * sf)


@pytest.mark.parametrize("name", GOLDEN_2D)
def test_a_2d_file_opens_as_a_plane_frame_with_the_same_results(name, tmp_path):
    from tests.golden import models as golden
    two_d = getattr(golden, name)()._state
    path = tmp_path / f"{name}.slab"
    save_model(two_d, path)
    opened = load_model(path)
    assert opened.converted_from_2d
    assert (opened.analysis_mode, opened.analysis_type) == ("3D", "plane_xz")
    assert all(n.y == 0.0 for n in opened.nodes)                    # one XZ plane
    assert max(n.z for n in opened.nodes) == max(n.y for n in two_d.nodes)   # height -> Z
    _same_results(load_model(path, keep_2d=True), opened)


def test_self_weight_still_acts_downward(tmp_path):
    """Displacements, reactions and moments are identical.  Axial forces agree on average
    but not end by end: 2D lumps a member's axial self-weight at its two end nodes (N constant
    along a column), 3D at every sub-element node (N grows towards the base, as it should)."""
    s = ModelState()
    s.analysis_mode = "2D"
    a, b, c = s.add_node(0, 0, 0), s.add_node(0, 3, 0), s.add_node(5, 3, 0)
    a.support_type, c.support_type = SupportType.FIXED, SupportType.ROLLER
    for p, q in ((a, b), (b, c)):
        m = s.add_member(p.id, q.id)
        m.E, m.A, m.I, m.I_y, m.J, m.density = 210e9, 8e-3, 2e-4, 2e-4, 1e-5, 7850
    s.active_case.include_self_weight = True
    path = tmp_path / "sw.slab"
    save_model(s, path)
    opened = load_model(path)
    _same_results(load_model(path, keep_2d=True), opened, axial_ends=False)
    col = solve_engine(*build_model(opened, opened.active_case), opened)["member_results"][0]
    weight = 7850 * 8e-3 * 9.81 * 3.0
    n_sub = opened.members[0].n_sub
    assert col.N_i - (-col.N_j) == pytest.approx(weight * (n_sub - 1) / n_sub, rel=1e-6)


def test_older_v2_file_without_a_stored_mode_is_converted(tmp_path):
    s = ModelState()
    s.analysis_mode = "2D"
    a, b = s.add_node(0, 0, 0), s.add_node(4, 0, 0)
    a.support_type = SupportType.FIXED
    s.add_member(a.id, b.id)
    s.active_case.set_node_load(b.id, NodeLoad(fy=-5e3, moment=2e3))
    data = s.to_dict()
    data.pop("analysis_mode")
    data.pop("mode_3d")
    data["version"] = 2
    path = tmp_path / "old.slab"
    path.write_text(json.dumps(data), encoding="utf-8")
    opened = load_model(path)
    assert opened.converted_from_2d and opened.analysis_type == "plane_xz"
    nl = opened.active_case.get_node_load(b.id)
    assert (nl.fz, nl.moment_y) == (-5e3, -2e3)                       # down, same sense


def test_legacy_v1_file_is_2d_and_converted(tmp_path):
    v1 = {"nodes": [{"id": 0, "x": 0, "y": 0, "support": "FIXED"},
                    {"id": 1, "x": 3, "y": 0, "support": "FREE", "fy": -1000.0}],
          "members": [{"id": 0, "ni": 0, "nj": 1, "type": "BEAM"}]}
    path = tmp_path / "v1.slab"
    path.write_text(json.dumps(v1), encoding="utf-8")
    assert load_model(path, keep_2d=True).is_2d                      # was read as 3D before
    opened = load_model(path)
    assert opened.converted_from_2d
    assert opened.active_case.get_node_load(1).fz == -1000.0


def test_a_3d_file_opens_untouched(tmp_path):
    s = ModelState()
    a, b = s.add_node(0, 0, 0), s.add_node(0, 0, 3)
    s.add_member(a.id, b.id)
    path = tmp_path / "three.slab"
    save_model(s, path)
    opened = load_model(path)
    assert not opened.converted_from_2d and opened.analysis_type == "space"
    assert opened.to_dict() == s.to_dict()


def test_the_window_says_the_model_was_converted(tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QApplication
    from tests.golden import models as golden
    from ui_qt.main_window import MainWindow
    import ui_qt.recent_files as rf
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(MainWindow, "_show_welcome", lambda self: None)
    monkeypatch.setattr(MainWindow, "_check_autosave_recovery", lambda self: False)
    monkeypatch.setattr(rf, "push", lambda p: None)                 # keep the user's recent list
    path = tmp_path / "portal.slab"
    save_model(golden.portal_frame_2d()._state, path)
    win = MainWindow()
    try:
        win._open_file(str(path))
        assert "plane frame in the XZ plane" in win._sb.currentMessage()
        assert win._scene.model_state.analysis_type == "plane_xz"
        assert win._act["plane_frame"].isChecked() and not win._is_dirty
    finally:
        win._is_dirty = False
        win.close()
