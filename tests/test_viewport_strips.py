"""Floating viewport strips: bound to the shared actions and kept inside the canvas."""

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
                            staticmethod(lambda *a, **k: QMessageBox.StandardButton.No))
    w = MainWindow()
    w.resize(1400, 850)
    w.show()
    qapp.processEvents()
    yield w
    w._scene.clearSelection()
    qapp.processEvents()
    w._is_dirty = False
    w.close()


def test_strip_buttons_are_the_shared_actions(win):
    strips = win._strips
    left = [b.defaultAction() for b in strips.left.buttons]
    right = [b.defaultAction() for b in strips.right.buttons]
    assert win._act["mode_member"] in left and win._act["zoom_fit"] in left
    assert win._act["ov_bmd"] in right and win._act["util_colours"] in right
    # Checking the action anywhere checks the strip button too (one shared state)
    btn = next(b for b in strips.right.buttons if b.defaultAction() is win._act["ov_sfd"])
    win._act["ov_sfd"].setChecked(True)
    assert btn.isChecked()
    win._act["ov_sfd"].setChecked(False)


@pytest.mark.parametrize("width", [1900, 1300, 1100, 900])
def test_strips_stay_inside_the_viewport_and_clear_of_each_other(win, qapp, width):
    from ui_qt.viewport_overlay import GIZMO_SPACE
    win.resize(width, 760)
    qapp.processEvents()
    strips = win._strips
    vp = win._view.viewport().geometry()
    for strip in (strips.left, strips.top, strips.right):
        if strip.isVisible():
            assert vp.contains(strip.geometry()), (width, strip.accessibleName())
    if strips.top.isVisible():
        top = strips.top.geometry()
        assert top.left() > strips.left.geometry().right()          # clear of the tools
        assert top.right() < vp.right() - GIZMO_SPACE + 2            # clear of the gizmo


def test_view_presets_drop_out_before_the_view_strip_hides(win, qapp):
    win.resize(1900, 760)
    qapp.processEvents()
    presets = win._strips.top.groups[0]
    assert win._strips.top.isVisible() and all(b.isVisible() for b in presets)
    win.resize(1000, 760)
    qapp.processEvents()
    if win._strips.top.isVisible():                       # narrow: planes kept, presets gone
        assert not any(b.isVisible() for b in presets)
