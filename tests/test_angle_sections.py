"""Angle (L) sections: computed properties, library registration, picker and forms."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import math

import pytest

from ui_qt.angle_sections import ANGLE_SECTIONS, angle_names, angle_properties
from ui_qt.section_library import (
    STEEL_PROFILES, angle_section_extras, steel_profile_by_name,
)

# Published EN 10056-1 values: A [cm²], I_y [cm⁴], I_u [cm⁴], I_v [cm⁴]
TABLE = {
    "L 200×20": (76.3, 2850, 4530, 1170), "L 150×15": (43.0, 898, 1430, 370),
    "L 120×12": (27.5, 368, 584, 152), "L 100×10": (19.2, 177, 280, 73.0),
    "L 80×8": (12.3, 72.3, 115, 29.6), "L 60×6": (6.91, 22.8, 36.1, 9.44),
    "L 50×5": (4.80, 11.0, 17.4, 4.55),
}


@pytest.mark.parametrize("name", sorted(TABLE))
def test_computed_properties_match_the_published_tables(name):
    s = ANGLE_SECTIONS[name]
    computed = (s.A * 1e4, s.I_y * 1e8, s.I_u * 1e8, s.I_v * 1e8)
    for got, want in zip(computed, TABLE[name]):
        assert got == pytest.approx(want, rel=0.012), f"{name}: {computed} vs {TABLE[name]}"


def test_mass_and_centroid_of_l100x10():
    s = ANGLE_SECTIONS["L 100×10"]
    assert s.mass_per_m == pytest.approx(15.0, abs=0.1)        # kg/m
    assert s.cx == s.cy == pytest.approx(0.0282, abs=0.0003)   # 28.2 mm
    assert s.i_v == pytest.approx(0.01950, abs=0.0003)         # 19.5 mm minimum radius
    assert s.J == pytest.approx((2 * 0.1 - 0.01) * 0.01**3 / 3)


def test_equal_angle_principal_axes_are_the_diagonals():
    s = ANGLE_SECTIONS["L 120×12"]
    assert s.I_y == pytest.approx(s.I_z, rel=1e-9)             # equal legs
    assert s.I_u > s.I_v
    # I_u + I_v is invariant: = I_y + I_z
    assert s.I_u + s.I_v == pytest.approx(s.I_y + s.I_z, rel=1e-9)
    assert abs(math.degrees(s.theta)) == pytest.approx(45.0, abs=0.01)


def test_geometry_code_handles_unequal_legs_for_future_use():
    """Unequal angles are not catalogued yet, but the machinery must be ready for them."""
    from ui_qt.angle_sections import _section_from_outline
    s = _section_from_outline("probe", "unequal", 0.100, 0.065, 0.008, 0.010, 0.005)
    assert s.I_u + s.I_v == pytest.approx(s.I_y + s.I_z, rel=1e-9)
    assert s.I_z > s.I_y                      # I_z is about the axis parallel to the short leg
    assert s.I_u > s.I_v > 0


def test_every_section_is_physically_sane():
    for name, s in ANGLE_SECTIONS.items():
        assert s.I_u > s.I_v > 0, name
        assert s.A > 0 and s.W_u > 0 and s.W_v > 0, name
        assert s.cx < max(s.a, s.b) / 2 and s.cy < max(s.a, s.b) / 2, name
        assert s.r2 == pytest.approx(s.r1 / 2), name


def test_library_catalogues_equal_angles_only():
    assert "L (equal)" in STEEL_PROFILES and "L (unequal)" not in STEEL_PROFILES
    assert len(STEEL_PROFILES["L (equal)"]) == len(angle_names("equal")) >= 50
    assert all(s.kind == "equal" and s.a == s.b for s in ANGLE_SECTIONS.values())
    assert angle_properties("L 100×65×8") is None
    name, A, I, W_pl, W_el = next(e for e in STEEL_PROFILES["L (equal)"] if e[0] == "L 100×10")
    s = angle_properties(name)
    assert (A, I) == (s.A, s.I_u)             # I is the MAJOR principal moment
    assert W_pl == W_el == s.W_u              # designed elastically
    assert steel_profile_by_name("L 100×10") == (A, I, W_pl, W_el)


def test_existing_series_unchanged():
    assert steel_profile_by_name("IPE 400") is not None
    assert angle_section_extras("IPE 400") is None
    assert [k for k in STEEL_PROFILES][:5] == ["IPE", "HEA", "HEB", "CHS", "RHS"]


def test_extras_give_the_weak_axis_and_torsion():
    ex = angle_section_extras("L 100×10")
    s = angle_properties("L 100×10")
    assert ex["I_y"] == s.I_v and ex["J"] == s.J and ex["i_v"] == s.i_v


# ── picker dialog ─────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication([])


def _dialog(qapp):
    from ui_qt.section_picker import SectionPickerDialog
    return SectionPickerDialog(current_E=210e9, current_A=0.01, current_I=1e-4)


def test_picker_returns_angle_properties_and_extras(qapp):
    dlg = _dialog(qapp)
    dlg._series_combo.setCurrentText("L (equal)")
    dlg._profile_combo.setCurrentIndex(dlg._profile_combo.findText("L 100×10"))
    assert "i_v" in dlg._lbl_extra.text() and "elastically" in dlg._lbl_extra.text()
    dlg._on_accept()
    E, A, I, W_pl, W_el, *_ = dlg.get_result()
    s = angle_properties("L 100×10")
    assert (A, I, W_pl, W_el) == (s.A, s.I_u, s.W_u, s.W_u)
    extra = dlg.get_extra()
    assert extra["I_y"] == s.I_v and extra["J"] == s.J


def test_picker_has_no_extras_for_ordinary_sections(qapp):
    dlg = _dialog(qapp)
    dlg._series_combo.setCurrentText("IPE")
    dlg._on_accept()
    assert dlg.get_extra() == {}
    assert dlg._lbl_extra.text() == ""


# ── property forms apply the extras ───────────────────────────────────────────

class _StubPicker:
    def __init__(self, *a, **k): pass
    def exec(self): return True
    def get_result(self):
        s = angle_properties("L 100×10")
        return (210e9, s.A, s.I_u, s.W_u, s.W_u, 0.0, 0.0, 7850.0, 355e6, "steel")
    def get_extra(self): return angle_section_extras("L 100×10")


def _state(n_members: int):
    from ui_qt.model_state import ModelState, NodeData, MemberData, LoadCase
    members = [MemberData(id=i, node_i=0, node_j=1, E=210e9) for i in range(n_members)]
    return ModelState(nodes=[NodeData(id=0, x=0, y=0), NodeData(id=1, x=4, y=0)],
                      members=members, load_cases=[LoadCase(id=0, name="G", category="G")])


def test_single_member_form_applies_angle_iy_and_j(qapp, monkeypatch):
    import ui_qt.section_picker as picker
    from ui_qt.panels import _MemberForm
    monkeypatch.setattr(picker, "SectionPickerDialog", _StubPicker)
    state = _state(1)
    _MemberForm(state.members[0], state, on_apply=lambda: None)._pick_section()
    s = angle_properties("L 100×10")
    m = state.members[0]
    assert m.I == pytest.approx(s.I_u, rel=1e-3) and m.I_y == pytest.approx(s.I_v, rel=1e-3)
    assert m.J == pytest.approx(s.J, rel=1e-3)
    assert m.A == pytest.approx(s.A, rel=1e-3)


def test_multi_member_form_applies_angle_iy_and_j_to_every_member(qapp, monkeypatch):
    import ui_qt.section_picker as picker
    from ui_qt.panels import _MultiMemberForm
    monkeypatch.setattr(picker, "SectionPickerDialog", _StubPicker)
    state = _state(3)
    _MultiMemberForm(state.members, state, on_apply=lambda: None)._pick_section()
    s = angle_properties("L 100×10")
    for m in state.members:
        assert m.I == pytest.approx(s.I_u, rel=1e-3) and m.I_y == pytest.approx(s.I_v, rel=1e-3)
        assert m.J == pytest.approx(s.J, rel=1e-3)


def test_small_angle_keeps_its_minor_inertia_through_the_form(qapp, monkeypatch):
    """L 50×5 has I_v of only 4.55 cm⁴; the form must not round it away."""
    import ui_qt.section_picker as picker
    from ui_qt.panels import _MemberForm
    s = angle_properties("L 50×5")

    class Small(_StubPicker):
        def get_result(self):
            return (210e9, s.A, s.I_u, s.W_u, s.W_u, 0.0, 0.0, 7850.0, 355e6, "steel")
        def get_extra(self): return angle_section_extras("L 50×5")

    monkeypatch.setattr(picker, "SectionPickerDialog", Small)
    state = _state(1)
    _MemberForm(state.members[0], state, on_apply=lambda: None)._pick_section()
    m = state.members[0]
    assert m.I_y == pytest.approx(s.I_v, rel=0.01)
    assert m.I == pytest.approx(s.I_u, rel=0.01)
    assert m.J == pytest.approx(s.J, rel=0.01)


def test_profile_name_lookup_recognises_angles_by_either_principal_moment():
    from ui_qt.panels import _build_section_lookup
    s = angle_properties("L 120×12")
    lookup = _build_section_lookup()
    assert lookup[(round(s.A, 8), round(s.I_u, 12))] == "L 120×12"
    assert lookup[(round(s.A, 8), round(s.I_v, 12))] == "L 120×12"
    assert lookup[(round(angle_properties("L 60×6").A, 8), round(angle_properties("L 60×6").I_v, 12))] == "L 60×6"
