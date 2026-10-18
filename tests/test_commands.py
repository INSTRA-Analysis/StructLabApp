"""The command table: every action resolves, shortcuts are unique, groups are exclusive."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication([])


@pytest.fixture()
def win(qapp, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    from ui_qt.main_window import MainWindow
    monkeypatch.setattr(MainWindow, "_show_welcome", lambda self: None)
    monkeypatch.setattr(MainWindow, "_check_autosave_recovery", lambda self: False)
    for name in ("question", "warning", "information", "critical"):
        monkeypatch.setattr(QMessageBox, name,
                            lambda *a, _n=name, **k: pytest.fail(f"unexpected {_n} dialog: {a[1:3]}"))
    w = MainWindow()
    yield w
    w._scene.clearSelection()
    qapp.processEvents()
    w._is_dirty = False
    w.close()


def test_every_named_handler_and_icon_exists():
    from ui_qt.commands import COMMANDS
    from ui_qt.icons import icon_path
    from ui_qt.main_window import MainWindow
    for c in COMMANDS:
        if isinstance(c.handler, str):
            assert callable(getattr(MainWindow, c.handler, None)), f"{c.key}: no MainWindow.{c.handler}"
        if c.icon:
            assert icon_path(c.icon) is not None, f"{c.key}: missing icon {c.icon}"
    keys = [c.key for c in COMMANDS]
    assert len(keys) == len(set(keys))


def test_no_two_actions_share_a_shortcut(win):
    seen = {}
    for act in win.actions():
        key = act.shortcut().toString()
        if key:
            assert key not in seen, f"{key}: {seen[key]} and {act.text()}"
            seen[key] = act.text()
    for expected in ("Ctrl+S", "F5", "Ctrl+Z", "S", "N", "M", "R", "L", "Ctrl+G", "Ctrl+T"):
        assert expected in seen, expected


def test_mode_actions_are_exclusive_and_drive_the_canvas(win):
    from ui_qt.canvas import CanvasMode
    a = win._act
    assert a["mode_select"].isChecked()
    a["mode_node"].trigger()
    assert a["mode_node"].isChecked() and not a["mode_select"].isChecked()
    assert win._scene._mode == CanvasMode.ADD_NODE
    a["mode_select"].trigger()
    assert win._scene._mode == CanvasMode.SELECT


def test_plane_actions_are_exclusive(win):
    from ui_qt.canvas import WorkingPlane
    win._act["plane_xz"].trigger()
    assert win._plane_btns[WorkingPlane.XZ].isChecked() and not win._plane_btns[WorkingPlane.XY].isChecked()
    assert win._active_plane == WorkingPlane.XZ


def test_overlay_and_toggle_actions_reach_the_scene(win):
    win._act["ov_sfd"].setEnabled(True)
    win._act["ov_sfd"].setChecked(True)
    assert win._scene._overlay_visible.get("SFD") is True
    win._act["thickness"].setChecked(True)
    assert win._scene._thickness_by_section
    win._act["thickness"].setChecked(False)


def test_solve_action_solves_a_valid_model(win):
    from ui_qt.model_state import ModelState, NodeLoad, SupportType
    s = ModelState()
    a, b = s.add_node(0, 0, 0), s.add_node(4, 0, 0)
    a.support_type = SupportType.FIXED
    s.add_member(a.id, b.id)
    s.load_cases[0].set_node_load(b.id, NodeLoad(fy=-1e3))
    win._apply_model_state(s, "test")
    win._act["solve"].trigger()
    assert win._solve_cache is not None
    assert win._act["ov_bmd"].isEnabled()                     # overlay controls unlocked


def test_interface_preference_reads_the_environment_override(monkeypatch):
    from ui_qt.main_window import MainWindow
    monkeypatch.setenv("STRUCTLAB_UI", "classic")
    assert MainWindow._interface_preference() == "classic"
    monkeypatch.setenv("STRUCTLAB_UI", "ribbon")
    assert MainWindow._interface_preference() == "ribbon"


def test_version_is_shown_consistently(win):
    from ui_qt.version import APP_VERSION, VERSION_LABEL
    assert APP_VERSION == "2.0" and VERSION_LABEL == "V2.0"
    assert "StructLab V2.0" in win.windowTitle()
