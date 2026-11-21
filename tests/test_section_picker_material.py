"""Section Library: the material's fy / density always match the material shown.

Regression: "Steel S235" is the first list entry, so selecting it on open fired no change
signal and fy kept the 275 MPa placeholder; OK then returned fy = 275 MPa for S235.
"""

import pytest


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication([])


@pytest.fixture()
def picker_cls(qapp):
    from ui_qt.section_picker import SectionPickerDialog
    saved = SectionPickerDialog._last_state
    SectionPickerDialog._last_state = {}
    yield SectionPickerDialog
    SectionPickerDialog._last_state = saved


def test_first_open_on_s235_returns_235_mpa(picker_cls):
    dlg = picker_cls(210e9, 0.01, 1e-4)
    assert dlg._mat_combo.currentText() == "Steel S235"
    assert dlg._fy_spin.value() == pytest.approx(235.0)
    dlg._on_accept()
    fy = dlg.get_result()[8]
    assert fy == pytest.approx(235e6)


def test_reopening_with_s235_remembered_keeps_235_mpa(picker_cls):
    picker_cls._last_state = {"material": "Steel S235", "tab": 0}
    dlg = picker_cls(210e9, 0.01, 1e-4)
    assert dlg._mat_combo.currentText() == "Steel S235"
    assert dlg._fy_spin.value() == pytest.approx(235.0)


@pytest.mark.parametrize("name", ["Steel S275", "Steel S355", "Steel S460"])
def test_every_steel_grade_shows_its_own_fy(picker_cls, name):
    from ui_qt.section_library import MATERIALS
    picker_cls._last_state = {"material": name, "tab": 0}
    dlg = picker_cls(210e9, 0.01, 1e-4)
    assert dlg._fy_spin.value() * 1e6 == pytest.approx(MATERIALS[name][2])


def test_custom_material_keeps_the_typed_values(picker_cls):
    picker_cls._last_state = {"material": "Custom", "tab": 0, "fy": 300.0, "density": 7000.0}
    dlg = picker_cls(200e9, 0.01, 1e-4)
    assert dlg._fy_spin.value() == pytest.approx(300.0)
    assert dlg._density_spin.value() == pytest.approx(7000.0)
