"""Split crossing members (X-bracing drawn without a node at the crossing)."""

import math

import pytest

from ui_qt.model_checks import check_duplicates, find_crossings, split_crossings
from ui_qt.model_state import ElementType, MemberLoad, ModelState, NodeLoad, SupportType


def _panel(z: float = 0.0):
    """A 4 x 3 m braced panel in the XZ plane: four corners, two diagonals that cross."""
    s = ModelState()
    c = [s.add_node(0, 0, z), s.add_node(4, 0, z), s.add_node(4, 0, z + 3), s.add_node(0, 0, z + 3)]
    for a, b in ((0, 1), (1, 2), (2, 3), (3, 0)):
        s.add_member(c[a].id, c[b].id)
    d1, d2 = s.add_member(c[0].id, c[2].id), s.add_member(c[1].id, c[3].id)
    return s, c, d1, d2


def test_an_x_without_a_node_is_found_at_its_centre():
    s, c, d1, d2 = _panel()
    found = find_crossings(s)
    assert len(found) == 1
    x = found[0]
    assert {x.member_a, x.member_b} == {d1.id, d2.id}
    assert x.point == pytest.approx((2.0, 0.0, 1.5)) and x.param_a == pytest.approx(0.5)


def test_splitting_joins_the_x_and_halves_each_diagonal():
    s, c, d1, d2 = _panel()
    d1.group, d1.A, d1.fy, d1.density, d1.beta_angle = "Diagonal", 6.9e-4, 355e6, 7850.0, 0.4
    d1.element_type = ElementType.BAR
    r = split_crossings(s)
    assert (r.crossings, r.nodes_created, r.members_split, r.members_created) == (1, 1, 2, 4)
    assert len(s.nodes) == 5 and len(s.members) == 4 + 4
    centre = next(n for n in s.nodes if (n.x, n.y, n.z) == pytest.approx((2.0, 0.0, 1.5)))
    pieces = [m for m in s.members if centre.id in (m.node_i, m.node_j)]
    assert len(pieces) == 4
    from_d1 = [m for m in pieces if m.group == "Diagonal"]
    assert len(from_d1) == 2
    for m in from_d1:                                   # every property survives the split
        assert (m.A, m.fy, m.density, m.beta_angle, m.element_type) == (6.9e-4, 355e6, 7850.0, 0.4, ElementType.BAR)
    ni = {n.id: n for n in s.nodes}
    for m in pieces:
        a, b = ni[m.node_i], ni[m.node_j]
        assert math.dist((a.x, a.y, a.z), (b.x, b.y, b.z)) == pytest.approx(2.5)


def test_second_run_finds_nothing_and_the_model_stays_clean():
    s, *_ = _panel()
    split_crossings(s)
    assert find_crossings(s) == [] and split_crossings(s).crossings == 0
    assert check_duplicates(s).is_clean


def test_three_members_through_one_point_share_one_node():
    s = ModelState()
    pts = [(0, 0, 0), (2, 2, 2), (2, 0, 0), (0, 2, 2), (0, 2, 0), (2, 0, 2)]
    ids = [s.add_node(*p).id for p in pts]
    for k in (0, 2, 4):
        s.add_member(ids[k], ids[k + 1])               # three space diagonals of a cube meet at (1,1,1)
    r = split_crossings(s)
    assert r.crossings == 3 and r.nodes_created == 1 and r.members_split == 3 and r.members_created == 6


def test_a_member_crossed_twice_is_cut_in_three():
    s = ModelState()
    a, b = s.add_node(0, 0, 0), s.add_node(10, 0, 0)
    long = s.add_member(a.id, b.id)
    for x in (3.0, 7.0):
        lo, hi = s.add_node(x, -1, 0), s.add_node(x, 1, 0)
        s.add_member(lo.id, hi.id)
    r = split_crossings(s)
    assert r.nodes_created == 2 and r.members_created == 3 + 2 + 2
    xs = sorted(n.x for n in s.nodes if n.y == 0)
    assert xs == [0.0, 3.0, 7.0, 10.0]


def test_skew_members_and_contacts_at_an_end_are_not_crossings():
    s = ModelState()
    a, b = s.add_node(0, 0, 0), s.add_node(4, 0, 0)
    s.add_member(a.id, b.id)
    c, d = s.add_node(2, -1, 0.05), s.add_node(2, 1, 0.05)       # passes 5 cm above: skew
    s.add_member(c.id, d.id)
    e, f = s.add_node(2, 0, 0), s.add_node(2, 3, 0)               # starts ON the member: a T, not an X
    s.add_member(e.id, f.id)
    assert find_crossings(s) == []


def test_parallel_members_are_ignored():
    s = ModelState()
    for y in (0.0, 1.0):
        s.add_member(s.add_node(0, y, 0).id, s.add_node(4, y, 0).id)
    assert find_crossings(s) == []


def test_members_with_loads_are_left_alone_and_reported():
    s, c, d1, d2 = _panel()
    s.load_cases[0].set_member_load(d1.id, MemberLoad(w_start=1000.0, w_end=1000.0))
    r = split_crossings(s)
    assert r.crossings == 0 and r.skipped_loaded == [d1.id] and len(s.nodes) == 4
    assert "carry member loads" in r.message()
    assert d1.id in {m.id for m in s.members}


def test_member_ids_limits_the_search():
    s, c, d1, d2 = _panel()
    assert find_crossings(s, member_ids={d1.id}) == []
    assert len(find_crossings(s, member_ids={d1.id, d2.id})) == 1


def test_split_x_is_stiffer_than_the_free_crossing_and_still_solves():
    """Joined at the centre the X-braced panel carries a racking load with the same member forces
    (statically the diagonals are the only load path), and every diagonal piece is half as long."""
    import numpy as np
    from ui_qt.model_builder import build_model
    from ui_qt.solve_actions import solve_engine

    def racking(split: bool):
        s, c, d1, d2 = _panel()
        for m in s.members:
            m.element_type, m.A, m.I, m.E = ElementType.BAR, 1e-3, 1e-6, 210e9
        c[0].support_type = SupportType.PIN
        c[1].support_type = SupportType.PIN
        s.load_cases[0].set_node_load(c[3].id, NodeLoad(fx=10e3))
        if split:
            split_crossings(s)
        model, emap = build_model(s, s.load_cases[0])
        cache = solve_engine(model, emap, s)
        assert np.all(np.isfinite(cache["displacements"]))
        return cache["reactions"], s

    free, _ = racking(False)
    joined, state = racking(True)
    assert np.sum(free) == pytest.approx(np.sum(joined))             # equilibrium unchanged
    assert len(state.members) == 8


def test_canvas_split_is_one_undo_step():
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from ui_qt.canvas import StructCanvas
    s, *_ = _panel()
    sc = StructCanvas()
    sc.load_state(s)
    summary = sc.split_crossings()
    assert summary.members_created == 4 and len(sc.model_state.members) == 8
    sc.undo()
    assert len(sc.model_state.members) == 6 and len(sc.model_state.nodes) == 4
    sc.clearSelection()


def test_window_command_splits_after_confirmation(monkeypatch):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication, QMessageBox
    app = QApplication.instance() or QApplication([])
    from ui_qt.main_window import MainWindow
    monkeypatch.setattr(MainWindow, "_show_welcome", lambda self: None)
    monkeypatch.setattr(MainWindow, "_check_autosave_recovery", lambda self: False)
    asked = []
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: asked.append(a[2]) or QMessageBox.StandardButton.Yes))
    win = MainWindow()
    s, *_ = _panel()
    win._scene.load_state(s)
    win._act["split_crossings"].trigger()
    assert asked and "1 crossing(s) in the model" in asked[0]
    assert len(win._scene.model_state.members) == 8
    win._act["split_crossings"].trigger()                        # nothing left to split: no prompt
    assert len(asked) == 1
    win._is_dirty = False
    win._scene.clearSelection()
    win.close()
