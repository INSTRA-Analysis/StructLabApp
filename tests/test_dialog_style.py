"""Wizard and combinations dialogs carry the shared dialog look (header, primary button)."""

import pytest


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication([])


def _check(dlg, title: str):
    from PyQt6.QtWidgets import QDialogButtonBox, QFrame, QLabel
    assert dlg.objectName() == "themed_dialog"
    header = dlg.layout().itemAt(0).widget()
    assert isinstance(header, QFrame) and header.objectName() == "dialog_header"
    assert header.findChild(QLabel, "dialog_header_title").text() == title
    for box in dlg.findChildren(QDialogButtonBox):
        ok = box.button(QDialogButtonBox.StandardButton.Ok)
        if ok is not None:
            assert ok.property("role") == "primary"


@pytest.mark.parametrize("cls, title", [
    ("BeamWizardDialog", "Continuous beam"),
    ("PortalWizardDialog", "Portal frame"),
    ("TrussWizardDialog", "Truss"),
    ("FrameWizardDialog", "Multi-storey frame"),
])
def test_wizards_are_themed(qapp, cls, title):
    import ui_qt.wizards as wz
    dlg = getattr(wz, cls)()
    _check(dlg, title)


def test_combinations_dialog_has_one_primary_action(qapp):
    from PyQt6.QtWidgets import QPushButton
    from ui_qt.combinations import CombinationsDialog
    from ui_qt.model_state import ModelState
    dlg = CombinationsDialog(ModelState(), lambda *a: None, lambda *a: None)
    _check(dlg, "Load combinations — EN 1990")
    primary = [b for b in dlg.findChildren(QPushButton) if b.property("role") == "primary"]
    assert [b.text() for b in primary] == ["Solve Selected"]
