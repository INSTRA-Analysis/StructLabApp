"""Selection to Bars / Beams: only the element type changes."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication, QMessageBox

from ui_qt.model_state import ElementType, ModelState

_app = QApplication.instance() or QApplication([])


def _frame():
    s = ModelState()
    n = [s.add_node(0, 0, 0), s.add_node(0, 0, 3), s.add_node(4, 0, 3), s.add_node(4, 0, 0)]
    a = s.add_member(n[0].id, n[1].id)           # column: heavy section, group "col"
    b = s.add_member(n[1].id, n[2].id)           # beam: lighter section, group "bm"
    c = s.add_member(n[2].id, n[3].id)
    a.group, a.A, a.I, a.density, a.fy = "col", 0.01, 4e-4, 7850.0, 355e6
    b.group, b.A, b.I, b.density, b.fy = "bm", 0.004, 8e-5, 7850.0, 275e6
    c.group, c.A, c.I = "col", 0.02, 9e-4
    return s, a, b, c


def test_only_the_element_type_changes_and_undo_restores_it():
    from ui_qt.canvas import StructCanvas
    s, a, b, c = _frame()
    sc = StructCanvas()
    sc.load_state(s)
    before = {m.id: (m.group, m.A, m.I, m.density, m.fy) for m in s.members}
    assert sc.set_element_type([a.id, b.id, c.id], ElementType.BAR) == 3
    for m in sc.model_state.members:
        assert m.element_type == ElementType.BAR
        assert (m.group, m.A, m.I, m.density, m.fy) == before[m.id]      # sections and groups kept
    sc.undo()
    assert all(m.element_type == ElementType.BEAM for m in sc.model_state.members)
    sc.clearSelection()


def test_members_already_of_that_type_are_not_counted_and_leave_no_undo_step():
    from ui_qt.canvas import StructCanvas
    s, a, b, c = _frame()
    sc = StructCanvas()
    sc.load_state(s)
    assert sc.set_element_type([a.id], ElementType.BEAM) == 0
    assert not sc._undo_stack
    assert sc.set_element_type([999], ElementType.BAR) == 0
    sc.clearSelection()


def test_window_commands_act_on_the_selection(monkeypatch):
    from ui_qt.main_window import MainWindow
    monkeypatch.setattr(MainWindow, "_show_welcome", lambda self: None)
    monkeypatch.setattr(MainWindow, "_check_autosave_recovery", lambda self: False)
    for name in ("question", "warning", "information", "critical"):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    win = MainWindow()
    s, a, b, c = _frame()
    win._scene.load_state(s)
    win._act["set_bars"].trigger()                                   # nothing selected: a hint, no change
    assert all(m.element_type == ElementType.BEAM for m in win._scene.model_state.members)
    for mid in (a.id, c.id):
        win._scene._member_items[mid].setSelected(True)
    win._act["set_bars"].trigger()
    ms = win._scene.model_state
    assert [m.element_type for m in ms.members] == [ElementType.BAR, ElementType.BEAM, ElementType.BAR]
    assert ms.get_member(a.id).A == 0.01 and ms.get_member(c.id).group == "col"
    win._scene.clearSelection()
    win._scene._member_items[a.id].setSelected(True)
    win._act["set_beams"].trigger()
    assert ms.get_member(a.id).element_type == ElementType.BEAM
    win._is_dirty = False
    win._scene.clearSelection()
    win.close()


def test_all_bar_frame_with_a_diagonal_still_solves_after_the_switch():
    """A braced frame converted to bars keeps working; the beams' bending drops out."""
    import numpy as np
    from ui_qt.model_builder import build_model
    from ui_qt.model_state import NodeLoad, SupportType
    from ui_qt.solve_actions import solve_engine
    s, a, b, c = _frame()
    for m in s.members:
        m.E = 210e9
    s.add_member(s.nodes[0].id, s.nodes[2].id)                        # diagonal makes it a truss
    s.members[-1].A, s.members[-1].I, s.members[-1].E = 0.002, 1e-5, 210e9
    s.nodes[0].support_type = SupportType.PIN
    s.nodes[3].support_type = SupportType.ROLLER
    s.load_cases[0].set_node_load(s.nodes[1].id, NodeLoad(fx=10e3))
    from ui_qt.canvas import StructCanvas
    sc = StructCanvas()
    sc.load_state(s)
    sc.set_element_type([m.id for m in s.members], ElementType.BAR)
    model, emap = build_model(sc.model_state, sc.model_state.load_cases[0])
    cache = solve_engine(model, emap, sc.model_state)
    assert np.all(np.isfinite(cache["displacements"]))
    for r in cache["member_results"]:
        assert abs(r.M_i) < 1e-6 and abs(r.M_j) < 1e-6                # a bar carries no moment
    sc.clearSelection()
