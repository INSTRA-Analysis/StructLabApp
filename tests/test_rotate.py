"""Rotate tool: geometry, section orientation, in-place vs copies, dialog and wiring."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import itertools
import math

import numpy as np
import pytest

from ui_qt.transform import rotate_point, rotated_beta, rotation_matrix


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication([])


# ── pure geometry ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("axis, start, end", [
    ("Z", (1, 0, 0), (0, 1, 0)),     # right-hand rule: +90 about Z turns X into Y
    ("X", (0, 1, 0), (0, 0, 1)),
    ("Y", (0, 0, 1), (1, 0, 0)),
])
def test_plus_90_follows_the_right_hand_rule(axis, start, end):
    assert rotate_point(start, (0, 0, 0), rotation_matrix(axis, 90.0)) == pytest.approx(end)


def test_rotation_is_proper_and_pivot_is_respected():
    r = rotation_matrix("Z", 37.5)
    assert r @ r.T == pytest.approx(np.eye(3)) and np.linalg.det(r) == pytest.approx(1.0)
    assert rotate_point((3, 1, 2), (2, 1, 0), rotation_matrix("Z", 180.0)) == pytest.approx((1, 1, 2))
    with pytest.raises(ValueError):
        rotation_matrix("W", 10.0)


MEMBERS = [((0, 0, 0), (4, 0, 0)), ((0, 0, 0), (0, 0, 3)), ((1, 2, 0), (3, 5, 4)), ((0, 0, 5), (0, 0, 0))]


@pytest.mark.parametrize("member, axis, angle, beta",
                         list(itertools.product(MEMBERS, "XYZ", (30.0, 90.0, -135.0), (0.0, 0.4))))
def test_section_turns_with_the_member(member, axis, angle, beta):
    """After rotating, the member's local y-axis is the old one rotated: the section moved rigidly."""
    from ui_qt.canvas_items import _compute_local_axes
    rot = rotation_matrix(axis, angle)
    start, end = member
    new_start, new_end = rotate_point(start, (0, 0, 0), rot), rotate_point(end, (0, 0, 0), rot)
    new_beta = rotated_beta(start, end, beta, rot, new_start, new_end)
    old_y = _compute_local_axes(*start, *end, beta)[1]
    new_x, new_y, _ = _compute_local_axes(*new_start, *new_end, new_beta)
    assert new_y == pytest.approx(rot @ old_y, abs=1e-9)
    assert new_x == pytest.approx(rot @ _compute_local_axes(*start, *end, beta)[0], abs=1e-9)


def test_horizontal_member_about_z_keeps_its_roll_angle():
    rot = rotation_matrix("Z", 90.0)
    assert rotated_beta((0, 0, 0), (4, 0, 0), 0.4, rot, (0, 0, 0), (0, 4, 0)) == pytest.approx(0.4)


# ── on the canvas ─────────────────────────────────────────────────────────────

def _scene(qapp):
    from ui_qt.canvas import StructCanvas
    from ui_qt.model_state import ElementType, ModelState, SupportType
    s = ModelState()
    base, top = s.add_node(1, 0, 0), s.add_node(1, 0, 3)
    base.support_type = SupportType.FIXED
    col = s.add_member(base.id, top.id)
    col.group, col.A, col.fy, col.W_pl, col.beta_angle = "Leg", 0.01, 355e6, 4e-4, 0.25
    col.element_type = ElementType.BEAM
    sc = StructCanvas()
    sc.load_state(s)
    return sc, base, top, col


def _select_all(sc):
    for it in list(sc._member_items.values()) + list(sc._node_items.values()):
        it.setSelected(True)


def test_rotate_in_place_moves_the_selection_and_undo_restores_it(qapp):
    sc, base, top, col = _scene(qapp)
    _select_all(sc)
    assert sc.rotate_selection("Z", 90.0, pivot=(0, 0, 0))
    ms = sc.model_state
    assert (ms.get_node(base.id).x, ms.get_node(base.id).y) == pytest.approx((0, 1))
    assert (ms.get_node(top.id).x, ms.get_node(top.id).y, ms.get_node(top.id).z) == pytest.approx((0, 1, 3))
    assert len(ms.nodes) == 2 and len(ms.members) == 1
    sc.undo()
    assert (sc.model_state.get_node(base.id).x, sc.model_state.get_node(base.id).y) == pytest.approx((1, 0))


def test_rotate_about_the_selection_centre_by_default(qapp):
    sc, base, top, col = _scene(qapp)
    _select_all(sc)
    sc.rotate_selection("Y", 90.0)                         # centre is (1, 0, 1.5): column lies down
    a, b = sc.model_state.get_node(base.id), sc.model_state.get_node(top.id)
    assert (a.x, a.z) == pytest.approx((-0.5, 1.5)) and (b.x, b.z) == pytest.approx((2.5, 1.5))


def test_copies_make_a_polar_array_with_all_properties(qapp):
    from ui_qt.model_state import SupportType
    sc, base, top, col = _scene(qapp)
    _select_all(sc)
    assert sc.rotate_selection("Z", 90.0, pivot=(0, 0, 0), copies=3)
    ms = sc.model_state
    assert len(ms.members) == 4 and len(ms.nodes) == 8
    bases = sorted((round(n.x, 6), round(n.y, 6)) for n in ms.nodes if n.z == 0)
    assert bases == [(-1, 0), (0, -1), (0, 1), (1, 0)]
    assert all(n.support_type == SupportType.FIXED for n in ms.nodes if n.z == 0)
    for m in ms.members:
        assert (m.group, m.A, m.fy, m.W_pl) == ("Leg", 0.01, 355e6, 4e-4)
    assert ms.get_member(col.id).beta_angle == 0.25        # the original is untouched
    assert len(sc._member_items) == 4 and len(sc._node_items) == 8


def test_copies_that_land_on_existing_members_are_skipped(qapp):
    sc, base, top, col = _scene(qapp)
    _select_all(sc)
    sc.rotate_selection("Z", 90.0, pivot=(0, 0, 0), copies=4)    # the 4th copy is the original again
    assert len(sc.model_state.members) == 4 and len(sc.model_state.nodes) == 8


def test_nothing_selected_does_nothing(qapp):
    sc, base, top, col = _scene(qapp)
    assert not sc.rotate_selection("Z", 45.0)
    assert sc.model_state.get_node(base.id).x == 1


# ── dialog and window ─────────────────────────────────────────────────────────

def test_dialog_defaults_and_values(qapp):
    from ui_qt.dialogs import RotateDialog
    dlg = RotateDialog(is_3d=True, centroid=(1.0, 2.0, 3.0))
    assert dlg.axis == "Z" and dlg.angle == 90.0 and dlg.pivot is None and dlg.copies == 0
    dlg._axis_btns["X"].setChecked(True)
    dlg._angle.setValue(-22.5)
    dlg._pivot_point.setChecked(True)
    dlg._pivot_spins[2].setValue(7.0)
    dlg._duplicate.setChecked(True)
    dlg._copies.setValue(3)
    assert (dlg.axis, dlg.angle, dlg.pivot, dlg.copies) == ("X", -22.5, (1.0, 2.0, 7.0), 3)
    flat = RotateDialog(is_3d=False)
    assert list(flat._axis_btns) == ["Z"] and flat._pivot_spins[2].isHidden()


def test_window_command_runs_the_rotation(qapp, monkeypatch):
    import ui_qt.dialogs as dialogs
    from ui_qt.main_window import MainWindow
    monkeypatch.setattr(MainWindow, "_show_welcome", lambda self: None)
    monkeypatch.setattr(MainWindow, "_check_autosave_recovery", lambda self: False)

    class Stub:
        DialogCode = dialogs.RotateDialog.DialogCode
        def __init__(self, *a, **k): pass
        def exec(self): return self.DialogCode.Accepted
        axis, angle, pivot, copies = "Z", 180.0, (0.0, 0.0, 0.0), 1

    monkeypatch.setattr(dialogs, "RotateDialog", Stub)
    sc0, base, top, col = _scene(qapp)
    win = MainWindow()
    try:
        win._apply_model_state(sc0.model_state, "t")
        _select_all(win._scene)
        win._act["rotate_selection"].trigger()
        assert len(win._scene.model_state.members) == 2
        xs = sorted(round(n.x, 6) for n in win._scene.model_state.nodes if n.z == 0)
        assert xs == [-1, 1]
    finally:
        win._scene.clearSelection()
        qapp.processEvents()
        win._is_dirty = False
        win.close()


# ── rotation feedback on the real tower (four-fold symmetric about its axis) ──

def _tower_with(member_ids):
    from pathlib import Path
    from ui_qt.canvas import StructCanvas
    from ui_qt.io import load_model
    sc = StructCanvas()
    sc.load_state(load_model(Path(__file__).resolve().parents[1] / "examples" / "l8c_d30_tower_3d.slab"))
    for mid in member_ids:
        sc._member_items[mid].setSelected(True)
    return sc


def test_copy_onto_an_existing_symmetric_leg_is_skipped_and_reported(qapp):
    sc = _tower_with([108])                                  # front corner leg
    n0, m0 = len(sc.model_state.nodes), len(sc.model_state.members)
    result = sc.rotate_selection("Z", 90.0, (0, 0, 0), copies=3)
    assert (len(sc.model_state.nodes), len(sc.model_state.members)) == (n0, m0)
    assert result.members_created == 0 and result.members_skipped == 3 and result.nodes_reused == 6
    assert result.needs_attention
    assert "skipped" in result.message(90.0, "Z", 3) and "0 new member" in result.message(90.0, "Z", 3)


def test_in_place_rotation_onto_existing_geometry_is_reported(qapp):
    sc = _tower_with([108])
    result = sc.rotate_selection("Z", 90.0, (0, 0, 0), copies=0)
    assert result.coincident_nodes == 2 and result.duplicate_members >= 1 and result.needs_attention
    assert "Check Duplicates" in result.message(90.0, "Z", 0)


def test_a_genuinely_new_copy_needs_no_attention(qapp):
    sc = _tower_with([108])
    result = sc.rotate_selection("Z", 45.0, (0, 0, 0), copies=1)
    assert (result.members_created, result.nodes_created, result.members_skipped) == (1, 2, 0)
    assert not result.needs_attention
    assert result.message(45.0, "Z", 1).startswith("1 rotated copy at 45° about Z: 1 new member(s), 2 new node(s).")
