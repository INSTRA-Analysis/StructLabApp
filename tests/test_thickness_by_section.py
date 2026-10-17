"""'Thickness by Section' view: member line width follows sqrt(area)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import math

import pytest


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication([])


def _scene(qapp, areas):
    from ui_qt.canvas import StructCanvas
    from ui_qt.model_state import ModelState
    state = ModelState()
    prev = state.add_node(0, 0, 0)
    for i, a in enumerate(areas):
        nxt = state.add_node(i + 1, 0, 0)
        state.add_member(prev.id, nxt.id).A = a
        prev = nxt
    sc = StructCanvas()
    sc.load_state(state)
    return sc


def _width(sc, member):
    from ui_qt.canvas_items import MemberItem
    item = sc._member_items.get(member.id)
    if item is None:
        item = MemberItem(member, sc.model_state.get_node(member.node_i),
                          sc.model_state.get_node(member.node_j), sc)
    return item._base_colour_pen(3.0).widthF()


def test_off_by_default_and_all_members_equal(qapp):
    sc = _scene(qapp, [0.001, 0.01])
    assert not sc._thickness_by_section
    assert [sc.section_width_factor(m) for m in sc.model_state.members] == [1.0, 1.0]


def test_width_follows_square_root_of_area(qapp):
    sc = _scene(qapp, [0.0004, 0.0016, 0.0064])          # sqrt: 0.02, 0.04, 0.08
    sc.set_thickness_by_section(True)
    f = [sc.section_width_factor(m) for m in sc.model_state.members]
    assert f[0] == pytest.approx(sc._THICKNESS_MIN) and f[2] == pytest.approx(sc._THICKNESS_MAX)
    t = (0.04 - 0.02) / (0.08 - 0.02)
    assert f[1] == pytest.approx(sc._THICKNESS_MIN + (sc._THICKNESS_MAX - sc._THICKNESS_MIN) * t)
    assert f[0] < f[1] < f[2]


def test_pen_width_scales_and_switching_off_restores_it(qapp):
    sc = _scene(qapp, [0.0004, 0.0064])
    small, big = sc.model_state.members
    sc.set_thickness_by_section(True)
    assert _width(sc, big) / _width(sc, small) == pytest.approx(
        sc._THICKNESS_MAX / sc._THICKNESS_MIN)
    sc.set_thickness_by_section(False)
    assert _width(sc, small) == _width(sc, big) == pytest.approx(3.0)


def test_unknown_or_uniform_sizes_keep_default_width(qapp):
    sc = _scene(qapp, [0.0, 0.01, 0.01])
    sc.set_thickness_by_section(True)
    assert [sc.section_width_factor(m) for m in sc.model_state.members] == [1.0, 1.0, 1.0]


def test_refresh_after_a_section_edit(qapp):
    sc = _scene(qapp, [0.0004, 0.0004])
    sc.set_thickness_by_section(True)
    a, b = sc.model_state.members
    assert sc.section_width_factor(b) == 1.0              # uniform -> no variation
    b.A = 0.0064
    sc.refresh_section_widths()
    assert sc.section_width_factor(b) > sc.section_width_factor(a)


def test_menu_action_toggles_the_scene(qapp, monkeypatch):
    from PyQt6.QtWidgets import QApplication
    from ui_qt.main_window import MainWindow
    monkeypatch.setattr(MainWindow, "_show_welcome", lambda self: None)
    monkeypatch.setattr(MainWindow, "_check_autosave_recovery", lambda self: False)
    win = MainWindow()
    try:
        win._thickness_act.setChecked(True)
        assert win._scene._thickness_by_section
        win._thickness_act.setChecked(False)
        assert not win._scene._thickness_by_section
    finally:
        win.close()


# ── hover tooltip ─────────────────────────────────────────────────────────────

def test_member_tooltip_gives_group_profile_length_and_mass(qapp):
    from ui_qt.angle_sections import angle_properties
    from ui_qt.canvas import StructCanvas
    from ui_qt.model_state import ModelState
    s = angle_properties("L 100×10")
    state = ModelState()
    a, b = state.add_node(0, 0, 0), state.add_node(3, 0, 4)
    m = state.add_member(a.id, b.id)
    m.A, m.I, m.group, m.density = s.A, s.I_u, "Leg", 7850.0
    sc = StructCanvas()
    sc.load_state(state)
    tip = sc._member_items[m.id].tooltip_text()
    assert "Leg" in tip and "L 100×10" in tip
    assert "L = 5.000 m" in tip and f"{s.A * 5 * 7850:.1f} kg" in tip


def test_tooltip_handles_missing_section_and_group(qapp):
    from ui_qt.canvas import StructCanvas
    from ui_qt.model_state import ModelState
    state = ModelState()
    a, b = state.add_node(0, 0, 0), state.add_node(2, 0, 0)
    m = state.add_member(a.id, b.id)
    m.A = 0.0
    sc = StructCanvas()
    sc.load_state(state)
    tip = sc._member_items[m.id].tooltip_text()
    assert "no group" in tip and "no section set" in tip and "kg" not in tip
