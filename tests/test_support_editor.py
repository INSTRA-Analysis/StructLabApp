"""Properties panel support editor: presets tick the boxes, ticks pick the preset (or Custom),
springs sit on free DOFs, and a selection's supports change only when the support is edited."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from ui_qt.model_state import SUPPORT_PRESETS, LoadCase, NodeData, SupportType


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def _editor(nodes, is_2d=False):
    from ui_qt.support_editor import SupportEditor
    return SupportEditor(nodes, is_2d)


def _choose(ed, preset):
    ed.combo.setCurrentIndex(ed.combo.findData(preset))


def test_3d_shows_six_boxes_and_a_preset_ticks_them(qapp):
    node = NodeData(id=0, x=0, y=0)
    ed = _editor([node])
    assert sorted(ed.boxes) == [0, 1, 2, 3, 4, 5]
    _choose(ed, SupportType.PIN)
    assert ed.flags() == SUPPORT_PRESETS[SupportType.PIN]
    ed.apply_to(node)
    assert node.support_type is SupportType.PIN


def test_ticking_a_box_selects_the_matching_preset_or_custom(qapp):
    node = NodeData(id=0, x=0, y=0)
    node.support_type = SupportType.PIN
    ed = _editor([node])
    ed.boxes[5].setChecked(True)                               # pin + theta_z
    assert ed.preset() is SupportType.CUSTOM
    for dof in (3, 4):
        ed.boxes[dof].setChecked(True)
    assert ed.preset() is SupportType.FIXED
    ed.apply_to(node)
    assert node.restraints == (True,) * 6


def test_2d_shows_the_in_plane_freedoms_and_keeps_out_of_plane_restraints(qapp):
    node = NodeData(id=0, x=0, y=0)
    ed = _editor([node], is_2d=True)
    assert sorted(ed.boxes) == [0, 1, 5]
    assert ed.combo.findData(SupportType.ROLLER_Z) == -1         # not a distinct preset in 2D
    _choose(ed, SupportType.ROLLER_Y)                            # wall roller, free vertically
    ed.apply_to(node)
    assert node.restraints == SUPPORT_PRESETS[SupportType.ROLLER_Y]
    ed2 = _editor([node], is_2d=True)
    ed2.boxes[0].setChecked(False)
    ed2.boxes[5].setChecked(True)                               # only theta_z
    ed2.apply_to(node)
    assert node.restraints == (False, False, False, False, False, True)
    assert node.support_type is SupportType.CUSTOM


def test_pin_with_a_rotational_spring_is_custom_and_reaches_the_solver(qapp):
    from ui_qt.model_builder import build_model
    from ui_qt.model_state import ModelState
    s = ModelState()
    node = s.add_node(0, 0, 0)
    s.add_node(0, 0, 3)
    s.add_member(0, 1)
    node.support_type = SupportType.PIN
    ed = _editor([node])
    assert not ed.springs[0].isEnabled() and ed.springs[5].isEnabled()   # only free DOFs
    ed.springs[5].setValue(4e5)
    assert ed.preset() is SupportType.CUSTOM and not ed.spring_group.isHidden()
    ed.apply_to(node)
    assert node.restraints == SUPPORT_PRESETS[SupportType.PIN] and node.spring_ktheta == 4e5
    assert node.support_type is SupportType.CUSTOM
    model, _ = build_model(s, s.active_case)
    sup = next(sp for sp in model.supports if sp.node_id == node.id)
    assert sup.spring_stiffness_theta == 4e5 and sup.restrained == SUPPORT_PRESETS[SupportType.PIN]


def test_spring_preset_without_stiffness_stays_a_spring(qapp):
    node = NodeData(id=0, x=0, y=0)
    ed = _editor([node])
    _choose(ed, SupportType.SPRING)
    ed.apply_to(node)
    assert node.support_type is SupportType.SPRING


def test_untouched_editor_writes_nothing(qapp):
    node = NodeData(id=0, x=0, y=0)
    node.set_restraints((True, False, False, False, False, True))
    ed = _editor([node])
    ed.apply_to(node)
    assert node.restraints == (True, False, False, False, False, True)


def test_editing_a_selections_loads_keeps_their_different_supports(qapp):
    from ui_qt.panels import _MultiNodeForm
    a, b = NodeData(id=0, x=0, y=0), NodeData(id=1, x=1, y=0)
    a.support_type, b.support_type = SupportType.FIXED, SupportType.ROLLER
    lc = LoadCase(id=0, name="G", category="G")
    form = _MultiNodeForm([a, b], lc, on_apply=lambda: None)
    form._fx.setValue(5.0)
    form._apply()
    assert (a.support_type, b.support_type) == (SupportType.FIXED, SupportType.ROLLER)
    assert lc.get_node_load(1).fx == 5000.0
    _choose(form.support_editor, SupportType.PIN)
    form._apply()
    assert (a.support_type, b.support_type) == (SupportType.PIN, SupportType.PIN)
