"""Start page: choices it returns, recent-model thumbnails, and how the window acts on them."""

import pytest
from PyQt6.QtCore import QSize


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication([])


def _saved_model(tmp_path, name="frame.slab"):
    from ui_qt.io import save_model
    from ui_qt.model_state import ModelState
    state = ModelState()
    a, b, c = state.add_node(0, 0, 0), state.add_node(0, 0, 3), state.add_node(4, 0, 3)
    state.add_member(a.id, b.id)
    state.add_member(b.id, c.id)
    path = tmp_path / name
    save_model(state, str(path))
    return str(path)


def test_new_model_choices_set_the_mode(qapp):
    from ui_qt.welcome_dialog import WelcomeDialog
    dlg = WelcomeDialog(None, recent_files=[])
    dlg._choose("blank:plane")
    assert (dlg.choice, dlg.start_mode) == ("blank", "plane")
    dlg = WelcomeDialog(None, recent_files=[])
    dlg._choose("wizard:truss")
    assert dlg.choice == "wizard:truss"


def test_recent_models_get_a_card_and_a_wireframe(qapp, tmp_path):
    from ui_qt.welcome_dialog import WelcomeDialog, model_segments
    path = _saved_model(tmp_path)
    segs, is_3d = model_segments(path)
    assert len(segs) == 2 and is_3d
    dlg = WelcomeDialog(None, recent_files=[path])
    assert len(dlg.recent_cards) == 1
    hits = []
    dlg.recent_cards[0].clicked.connect(lambda: hits.append(dlg.choice))
    dlg.recent_cards[0].clicked.emit()
    assert dlg.choice == f"file:{path}"


def test_an_unreadable_recent_file_still_gets_a_card(qapp, tmp_path):
    from ui_qt.welcome_dialog import WelcomeDialog, model_segments
    bad = tmp_path / "broken.slab"
    bad.write_text("not json", encoding="utf-8")
    assert model_segments(str(bad)) is None
    dlg = WelcomeDialog(None, recent_files=[str(bad)])
    assert len(dlg.recent_cards) == 1


def test_wireframe_handles_empty_and_degenerate_input(qapp):
    from ui_qt.welcome_dialog import render_wireframe
    assert not render_wireframe([], QSize(80, 50), True).isNull()
    one_point = [((1.0, 1.0, 1.0), (1.0, 1.0, 1.0))]          # zero-size model
    assert not render_wireframe(one_point, QSize(80, 50), True).isNull()


@pytest.mark.parametrize("start_mode, analysis_type, plane_name", [
    ("plane", "plane_xz", "XZ"), ("3D", "space", None)])
def test_new_model_from_the_start_page(qapp, monkeypatch, tmp_path, start_mode, analysis_type, plane_name):
    """New plane frame: a 3D model with Plane Frame on, shown from the front in its XZ plane.
    New 3D model: a space frame.  The start page never creates a 2D model."""
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QDialog
    import ui_qt.banner_themes as bt
    import ui_qt.projection as proj
    import ui_qt.welcome_dialog as wd
    from ui_qt.main_window import MainWindow
    store = QSettings(str(tmp_path / "structlab.ini"), QSettings.Format.IniFormat)
    monkeypatch.setattr(bt, "settings", lambda: store)
    show_welcome = MainWindow._show_welcome
    monkeypatch.setattr(MainWindow, "_show_welcome", lambda self: None)
    monkeypatch.setattr(MainWindow, "_check_autosave_recovery", lambda self: False)

    class FakeStart:
        def __init__(self, *a, **k):
            self.choice, self.start_mode = "blank", start_mode

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(wd, "WelcomeDialog", FakeStart)
    az, el = proj.ISO_AZIMUTH, proj.ISO_ELEVATION
    win = MainWindow()
    try:
        show_welcome(win)
        state = win._scene.model_state
        assert state.analysis_mode == "3D" and state.analysis_type == analysis_type
        if plane_name:
            assert (proj.ISO_AZIMUTH, proj.ISO_ELEVATION) == (0.0, 2.0)          # Front view
            assert win._scene._working_plane.name == plane_name
    finally:
        proj.ISO_AZIMUTH, proj.ISO_ELEVATION = az, el
        win._is_dirty = False
        win.close()


def test_a_2d_state_put_in_the_window_becomes_a_plane_frame(qapp, monkeypatch):
    from ui_qt.main_window import MainWindow
    from ui_qt.model_state import ModelState
    import ui_qt.projection as proj
    monkeypatch.setattr(MainWindow, "_show_welcome", lambda self: None)
    monkeypatch.setattr(MainWindow, "_check_autosave_recovery", lambda self: False)
    s = ModelState()
    s.analysis_mode = "2D"
    s.add_member(s.add_node(0, 0, 0).id, s.add_node(0, 3, 0).id)
    az, el = proj.ISO_AZIMUTH, proj.ISO_ELEVATION
    win = MainWindow()
    try:
        win._apply_model_state(s, "console")
        state = win._scene.model_state
        assert (state.analysis_mode, state.analysis_type) == ("3D", "plane_xz")
        assert max(n.z for n in state.nodes) == 3.0                          # height is Z
    finally:
        proj.ISO_AZIMUTH, proj.ISO_ELEVATION = az, el
        win._is_dirty = False
        win.close()


@pytest.mark.parametrize("choice, handler", [
    ("wizard:portal", "_on_portal_wizard"),
    ("help:shortcuts", "_on_keyboard_shortcuts"),
])
def test_window_acts_on_the_start_page_choice(qapp, monkeypatch, tmp_path, choice, handler):
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QDialog
    import ui_qt.banner_themes as bt
    import ui_qt.welcome_dialog as wd
    from ui_qt.main_window import MainWindow
    store = QSettings(str(tmp_path / "structlab.ini"), QSettings.Format.IniFormat)
    monkeypatch.setattr(bt, "settings", lambda: store)    # never touch the real preferences
    show_welcome = MainWindow._show_welcome            # the real one, called below
    monkeypatch.setattr(MainWindow, "_show_welcome", lambda self: None)
    monkeypatch.setattr(MainWindow, "_check_autosave_recovery", lambda self: False)

    class FakeStart:
        def __init__(self, *a, **k):
            self.choice, self.start_mode = choice, "3D"

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(wd, "WelcomeDialog", FakeStart)
    win = MainWindow()
    try:
        calls = []
        monkeypatch.setattr(win, handler, lambda: calls.append(handler))
        show_welcome(win)
        assert calls == [handler]
    finally:
        win._is_dirty = False
        win.close()
