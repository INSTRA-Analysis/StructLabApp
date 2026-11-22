"""Properties panel for a plane frame (XZ, Z up): x and z, Fx / Fz / My, supports ux / uz / θy,
the plane-frame presets, and no 'qy' member load."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from ui_qt.model_state import SUPPORT_PRESETS, LoadCase, ModelState, NodeData, NodeLoad, SupportType
from ui_qt.support_editor import (
    SupportEditor, menu_presets, plane_frame_restraints, support_layout,
)


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def _state(kind):
    s = ModelState()
    if kind == "2d":
        s.analysis_mode = "2D"
    elif kind == "plane":
        s.analysis_type = "plane_xz"
    return s


@pytest.mark.parametrize("kind", ["plane", "space"])
def test_support_layout_of_a_model(kind):
    assert support_layout(_state(kind)) == kind
    assert support_layout(None) == "space"


@pytest.mark.parametrize("preset, ticks", [
    (SupportType.FIXED, (True, True, True)), (SupportType.PIN, (True, True, False)),
    (SupportType.ROLLER, (False, True, False)), (SupportType.ROLLER_Z, (True, False, False))])
def test_plane_frame_ticks_reproduce_the_presets(preset, ticks):
    assert plane_frame_restraints(*ticks) == SUPPORT_PRESETS[preset]


def test_plane_frame_menus_offer_the_in_plane_rollers():
    presets = [p for _, p in menu_presets("plane")]
    assert SupportType.ROLLER_Z in presets and SupportType.ROLLER_Y not in presets
    names = dict((p, t) for t, p in menu_presets("plane"))
    assert "vertical" in names[SupportType.ROLLER_Z]


def test_support_editor_shows_ux_uz_thy_for_a_plane_frame(qapp):
    node = NodeData(id=0, x=0, y=0)
    ed = SupportEditor([node], "plane")
    assert sorted(ed.boxes) == [0, 2, 4]
    assert [ed.boxes[d].text() for d in (0, 2, 4)] == ["ux →", "uz ↑", "θy"]
    ed.combo.setCurrentIndex(ed.combo.findData(SupportType.ROLLER_Z))
    ed.apply_to(node)
    assert node.support_type is SupportType.ROLLER_Z               # free vertically
    ed2 = SupportEditor([node], "plane")
    ed2.boxes[4].setChecked(True)                                   # ux + θy held
    ed2.springs[2].setValue(3e6)                                    # vertical spring
    ed2.apply_to(node)
    assert node.restraints[0] and node.restraints[4] and not node.restraints[2]
    assert node.spring_kz == 3e6 and node.support_type is SupportType.CUSTOM


def test_node_form_shows_x_z_and_in_plane_loads(qapp):
    from PyQt6.QtWidgets import QFormLayout, QGroupBox, QLabel
    from ui_qt.panels import _NodeForm
    node = NodeData(id=3, x=2.0, y=0.0, z=4.0)
    lc = LoadCase(id=0, name="G", category="G")
    lc.set_node_load(3, NodeLoad(fy=7.0, fz=-5e3))
    form = _NodeForm(node, lc, on_apply=lambda: None, layout="plane")

    def labels(title):
        box = next(b for b in form.findChildren(QGroupBox) if b.title().startswith(title))
        lay = box.layout()
        return [lay.itemAt(i, QFormLayout.ItemRole.LabelRole).widget().text()
                for i in range(lay.rowCount())]
    assert labels("Coordinates") == ["x (m):", "z (m) ↑:", "y (m), frame plane:"]
    assert not form._y.isEnabled()
    assert labels("Applied load") == ["Fx (kN) →:", "Fz (kN) ↑:", "My (kN·m):"]
    form._fz.setValue(-8.0)
    form._apply()
    nl = lc.get_node_load(3)
    assert nl.fz == -8e3 and nl.fy == 7.0                          # hidden Fy kept


def test_multi_node_form_uses_the_plane_layout(qapp):
    from ui_qt.panels import _MultiNodeForm
    a, b = NodeData(id=0, x=0, y=0), NodeData(id=1, x=3, y=0)
    form = _MultiNodeForm([a, b], LoadCase(id=0, name="G", category="G"), lambda: None, layout="plane")
    assert sorted(form.support_editor.boxes) == [0, 2, 4]


def test_plane_frame_has_no_qy_member_load_button():
    from ui_qt.panels import _dist_load_buttons
    assert [k for k, _ in _dist_load_buttons(_state("plane"))] == ["w", "qx"]
    assert [k for k, _ in _dist_load_buttons(_state("space"))] == ["w", "qx", "qy"]
