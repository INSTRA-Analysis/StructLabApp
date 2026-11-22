"""Plane Frame (XZ) in the window: the toggle, the status badge, undo, files, the PDF line,
and the deflection read-out using the vertical DOF."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from ui_qt.model_state import ModelState, NodeLoad, SupportType, analysis_label


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def win(qapp, monkeypatch):
    from ui_qt.main_window import MainWindow
    monkeypatch.setattr(MainWindow, "_show_welcome", lambda self: None)
    monkeypatch.setattr(MainWindow, "_check_autosave_recovery", lambda self: False)
    w = MainWindow()
    yield w
    w._is_dirty = False
    w.close()


def _portal(mode="3D") -> ModelState:
    s = ModelState()
    s.analysis_mode = mode
    up = (lambda x, h: (x, 0, h)) if mode == "3D" else (lambda x, h: (x, h, 0))
    n = [s.add_node(*up(0, 0)), s.add_node(*up(0, 4)), s.add_node(*up(6, 4)), s.add_node(*up(6, 0))]
    n[0].support_type = n[3].support_type = SupportType.PIN
    for a, b in ((0, 1), (1, 2), (3, 2)):
        m = s.add_member(n[a].id, n[b].id)
        m.E, m.A, m.I, m.I_y, m.J = 210e9, 8e-3, 2e-4, 2e-4, 1e-5
    vertical = NodeLoad(fz=-20e3) if mode == "3D" else NodeLoad(fy=-20e3)
    s.active_case.set_node_load(n[2].id, vertical)
    return s


def test_analysis_labels():
    s = ModelState()
    assert analysis_label(s)[0] == "Space frame"
    s.analysis_type = "plane_xz"
    assert analysis_label(s)[0] == "Plane frame (XZ)" and "uy, θx, θz" in analysis_label(s)[1]
    s.analysis_mode = "2D"
    assert analysis_label(s)[0] == "2D frame"


def test_toggle_sets_the_type_updates_the_badge_and_undoes(win):
    win._scene.load_state(_portal())
    win._update_status_stats()
    act = win._act["plane_frame"]
    assert act.isEnabled() and not act.isChecked()
    assert win._sb_analysis.text() == "Space frame"
    act.setChecked(True)
    assert win._scene.model_state.analysis_type == "plane_xz"
    assert win._sb_analysis.text() == "Plane frame (XZ)" and win._is_dirty
    win._scene.undo()
    win._update_status_stats()
    assert win._scene.model_state.analysis_type == "space" and not act.isChecked()


def test_switching_plane_frame_on_faces_the_front_in_the_frames_plane(win):
    import ui_qt.projection as proj
    s = _portal()
    for n in s.nodes:
        n.y = 2.5                                              # the frame's plane is y = 2.5
    win._scene.load_state(s)
    win._act["plane_frame"].setChecked(True)
    assert (proj.ISO_AZIMUTH, proj.ISO_ELEVATION) == (0.0, 2.0)
    assert win._scene._working_plane.name == "XZ" and win._scene._plane_offset == 2.5


def test_a_wizard_frame_opens_on_the_front_view(win):
    import ui_qt.projection as proj
    from ui_qt import presets
    ipe = (210e9, 5.38e-3, 8.356e-5)
    win._apply_model_state(presets.portal_wizard(12.0, 5.0, False, *ipe, *ipe, udl_g=6e3), "Portal")
    assert (proj.ISO_AZIMUTH, proj.ISO_ELEVATION) == (0.0, 2.0)
    assert win._act["plane_frame"].isChecked()


def test_a_saved_plane_frame_reopens_as_one(win, tmp_path):
    from ui_qt.io import save_model
    s = _portal()
    s.analysis_type = "plane_xz"
    path = tmp_path / "portal.slab"
    save_model(s, str(path))
    import ui_qt.recent_files as rf
    original = rf.push
    rf.push = lambda p: None                                   # keep the user's recent list
    try:
        win._open_file(str(path))
    finally:
        rf.push = original
    assert win._scene.model_state.analysis_type == "plane_xz"
    assert win._act["plane_frame"].isChecked() and win._sb_analysis.text() == "Plane frame (XZ)"


def test_solve_reports_the_vertical_deflection_of_a_plane_frame(win):
    """Simply supported 6 m beam, 20 kN at midspan: δ = PL³/48EI = 2.14 mm, read from uz
    (the locked uy is always zero in a plane frame)."""
    s = ModelState()
    s.analysis_type = "plane_xz"
    a, b, c = s.add_node(0, 0, 0), s.add_node(3, 0, 0), s.add_node(6, 0, 0)
    a.support_type, c.support_type = SupportType.PIN, SupportType.ROLLER
    for p, q in ((a, b), (b, c)):
        m = s.add_member(p.id, q.id)
        m.E, m.A, m.I, m.I_y, m.J = 210e9, 8e-3, 2e-4, 2e-4, 1e-5
    s.active_case.set_node_load(b.id, NodeLoad(fz=-20e3))
    win._scene.load_state(s)
    win._on_solve()
    assert win._solve_cache is not None
    assert "δ max: 2.14 mm" in win._sb_stats.text()
    assert "Max deflection: 2.14 mm (member 0, end j)" in win._sb.currentMessage()


def test_solve_reports_a_beams_midspan_deflection(win):
    """One member, simply supported, UDL: the deflection is mid-span, where there is no node.
    δ = 5wL⁴/384EI; the node-only summary used to report 0."""
    s = ModelState()
    s.analysis_type = "plane_xz"
    a, b = s.add_node(0, 0, 0), s.add_node(6, 0, 0)
    a.support_type, b.support_type = SupportType.PIN, SupportType.ROLLER
    m = s.add_member(a.id, b.id)
    m.E, m.A, m.I, m.I_y, m.J = 210e9, 8e-3, 2e-4, 2e-4, 1e-5
    from ui_qt.model_state import DistLoad, MemberLoad
    s.active_case.member_loads[m.id] = MemberLoad(dist_loads=[DistLoad("w", 10e3, 10e3)])
    win._scene.load_state(s)
    win._on_solve()
    delta = 5 * 10e3 * 6 ** 4 / (384 * 210e9 * 2e-4)
    assert f"Max deflection: {delta * 1e3:.2f} mm (member 0 at 0.50 L)" in win._sb.currentMessage()


def test_pdf_title_page_states_the_analysis(tmp_path):
    from tests.test_pdf_report_3d import _report_text
    s = _portal()
    s.analysis_type = "plane_xz"
    text = _report_text(tmp_path, s)
    assert "Plane frame (XZ)" in text and "Structural Analysis" in text
