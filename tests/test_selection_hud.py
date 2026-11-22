"""View > Selection Shortcuts: the reminder drawn over the view while something is selected
can be switched off, and the choice is remembered (tests use a private preferences file)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _window(monkeypatch):
    from ui_qt.main_window import MainWindow
    monkeypatch.setattr(MainWindow, "_show_welcome", lambda self: None)
    monkeypatch.setattr(MainWindow, "_check_autosave_recovery", lambda self: False)
    return MainWindow()


def _close(win):
    win._is_dirty = False
    win.close()


def test_on_by_default_and_remembered_when_switched_off(qapp, monkeypatch):
    import ui_qt.main_window as mw
    win = _window(monkeypatch)
    act = win._act["selection_hud"]
    assert act.isCheckable() and act.isChecked() and win._view.show_selection_hud
    act.setChecked(False)
    assert win._view.show_selection_hud is False
    assert str(mw._preferences().value("ui/selection_hud")).lower() == "false"
    _close(win)

    again = _window(monkeypatch)                       # a new session reads the preference
    assert not again._act["selection_hud"].isChecked()
    assert again._view.show_selection_hud is False
    _close(again)
