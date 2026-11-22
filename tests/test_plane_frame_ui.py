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


def test_the_toggle_is_disabled_for_a_2d_model(win):
    win._scene.load_state(_portal("2D"))
    win._update_status_stats()
    act = win._act["plane_frame"]
    assert not act.isEnabled() and win._sb_analysis.text() == "2D frame"


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
    assert "δ max: 2.1 mm" in win._sb_stats.text()
    assert "Max deflection: 2.14 mm (node 1)" in win._sb.currentMessage()


def test_pdf_title_page_states_the_analysis(tmp_path):
    from tests.test_pdf_report_3d import _report_text
    s = _portal()
    s.analysis_type = "plane_xz"
    text = _report_text(tmp_path, s)
    assert "Plane frame (XZ)" in text and "3D Structural Analysis" in text
