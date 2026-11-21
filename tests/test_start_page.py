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
    dlg._choose("blank:2D")
    assert (dlg.choice, dlg.start_mode) == ("blank", "2D")
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


@pytest.mark.parametrize("choice, handler", [
    ("wizard:portal", "_on_portal_wizard"),
    ("help:shortcuts", "_on_keyboard_shortcuts"),
])
def test_window_acts_on_the_start_page_choice(qapp, monkeypatch, choice, handler):
    from PyQt6.QtWidgets import QDialog
    import ui_qt.welcome_dialog as wd
    from ui_qt.main_window import MainWindow
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
