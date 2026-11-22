"""Phase 3, step 8: nothing in the app makes a 2D model.  The canvas refuses a switch to 2D
(a 2D model it holds goes to 3D as a plane frame), and a console script that sets the model
to 2D gets a plane frame back."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from ui_qt.model_state import ModelState, NodeLoad


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def test_canvas_refuses_to_switch_to_2d(qapp):
    from ui_qt.canvas import StructCanvas
    sc = StructCanvas()
    assert sc.set_analysis_mode("2D") is False
    assert sc.model_state.analysis_mode == "3D"


def test_canvas_takes_a_2d_model_to_a_plane_frame(qapp):
    from ui_qt.canvas import StructCanvas
    s = ModelState()
    s.analysis_mode = "2D"
    a, b = s.add_node(0, 0, 0), s.add_node(0, 3, 0)
    s.add_member(a.id, b.id)
    s.active_case.set_node_load(b.id, NodeLoad(fy=-5e3))
    sc = StructCanvas()
    sc.load_state(s)
    assert sc.set_analysis_mode("3D") is True
    assert (s.analysis_mode, s.analysis_type) == ("3D", "plane_xz")
    assert (b.z, s.active_case.get_node_load(b.id).fz) == (3.0, -5e3)


def test_a_console_edit_to_2d_comes_back_as_a_plane_frame(qapp, monkeypatch):
    from ui_qt.main_window import MainWindow
    monkeypatch.setattr(MainWindow, "_show_welcome", lambda self: None)
    monkeypatch.setattr(MainWindow, "_check_autosave_recovery", lambda self: False)
    win = MainWindow()
    try:
        state = win._scene.model_state
        state.add_member(state.add_node(0, 0, 0).id, state.add_node(4, 2, 0).id)
        state.analysis_mode = "2D"                       # what a console script might do
        win._refresh_after_console_edit()
        assert (state.analysis_mode, state.analysis_type) == ("3D", "plane_xz")
        assert "plane frame" in win._sb.currentMessage()
        assert win._sb_analysis.text() == "Plane frame (XZ)"
    finally:
        win._is_dirty = False
        win.close()
