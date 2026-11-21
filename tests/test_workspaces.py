"""Workspaces: each one sets panels, results strip, load arrows and ribbon tab; tabs alone don't."""

import pytest


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication([])


@pytest.fixture()
def win(qapp, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    from ui_qt.main_window import MainWindow
    monkeypatch.setenv("STRUCTLAB_UI", "ribbon")
    monkeypatch.setattr(MainWindow, "_show_welcome", lambda self: None)
    monkeypatch.setattr(MainWindow, "_check_autosave_recovery", lambda self: False)
    for name in ("question", "warning", "information", "critical"):
        monkeypatch.setattr(QMessageBox, name,
                            staticmethod(lambda *a, **k: QMessageBox.StandardButton.No))
    w = MainWindow()
    w.resize(1500, 850)
    w.show()
    qapp.processEvents()
    yield w
    w._scene.clearSelection()
    qapp.processEvents()
    w._is_dirty = False
    w.close()


def _current_tab(win) -> str:
    return win._ribbon.tabs.tabText(win._ribbon.tabs.currentIndex())


def test_results_workspace_shows_results_and_hides_loads(win, qapp):
    win._act["ws_results"].trigger()
    qapp.processEvents()
    assert win._right_dock.isVisible() and win._strips.right.isVisible()
    assert not win._act["show_loads"].isChecked()
    assert _current_tab(win) == "Results"
    assert win._act["ws_results"].isChecked()


def test_model_and_loads_workspaces(win, qapp):
    win._act["ws_model"].trigger()
    qapp.processEvents()
    assert not win._right_dock.isVisible() and not win._strips.right.isVisible()
    assert win._left_dock.isVisible() and win._act["show_loads"].isChecked()
    assert _current_tab(win) == "Model"
    win._act["ws_loads"].trigger()
    qapp.processEvents()
    assert _current_tab(win) == "Loads" and win._act["show_loads"].isChecked()
    assert not win._act["ws_model"].isChecked()       # exclusive


def test_clicking_a_ribbon_tab_does_not_switch_workspace(win, qapp):
    win._act["ws_model"].trigger()
    qapp.processEvents()
    win._ribbon.set_current_tab("Results")
    qapp.processEvents()
    assert not win._right_dock.isVisible()
    assert win._act["ws_model"].isChecked()


def test_a_successful_solve_opens_the_results_workspace(win, qapp):
    from ui_qt.model_state import ModelState, NodeLoad, SupportType
    state = ModelState()
    a, b = state.add_node(0, 0, 0), state.add_node(4, 0, 0)
    a.support_type = SupportType.FIXED
    m = state.add_member(a.id, b.id)
    m.E, m.A, m.I = 210e9, 0.01, 1e-4
    state.load_cases[0].set_node_load(b.id, NodeLoad(fy=-10e3))
    win._scene.load_state(state)
    win._act["ws_model"].trigger()
    qapp.processEvents()
    win._on_solve()
    qapp.processEvents()
    assert win._solve_cache is not None
    assert win._act["ws_results"].isChecked() and win._right_dock.isVisible()


def test_a_failed_solve_keeps_the_workspace(win, qapp):
    win._act["ws_model"].trigger()
    qapp.processEvents()
    win._on_solve()                    # empty model: warns, nothing solved
    assert win._act["ws_model"].isChecked() and not win._right_dock.isVisible()


def test_switcher_sits_in_the_ribbon_tab_row(win):
    buttons = win._ribbon.workspace_switcher.findChildren(type(win._ribbon.collapse_button))
    assert [b.defaultAction() for b in buttons] == [
        win._act["ws_model"], win._act["ws_loads"], win._act["ws_results"]]
