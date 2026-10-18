"""Crossing bracing: finding the crossings and shortening the buckling length at them.

The design assumption (ModelState.crossing_braces): bracing that crosses is connected there, so
a compression member is held at the crossing while the member crossing it is in tension. The
analysis model is not changed.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PyQt6.QtWidgets import QApplication

from ui_qt import design_checks as dc
from ui_qt.angle_sections import angle_properties
from ui_qt.model_checks import crossing_restraints, find_crossings
from ui_qt.model_state import ElementType, LoadCombination, ModelState, NodeLoad, SupportType
from ui_qt.optimise import apply_section, optimise_groups

_app = QApplication.instance() or QApplication([])


def _panel(z: float = 0.0):
    """A 4 x 3 m braced panel in the XZ plane: four corners, two diagonals that cross."""
    s = ModelState()
    c = [s.add_node(0, 0, z), s.add_node(4, 0, z), s.add_node(4, 0, z + 3), s.add_node(0, 0, z + 3)]
    for a, b in ((0, 1), (1, 2), (2, 3), (3, 0)):
        s.add_member(c[a].id, c[b].id)
    d1, d2 = s.add_member(c[0].id, c[2].id), s.add_member(c[1].id, c[3].id)
    return s, c, d1, d2


# ── finding crossings ────────────────────────────────────────────────────────

def test_an_x_without_a_node_is_found_at_its_centre():
    s, c, d1, d2 = _panel()
    found = find_crossings(s)
    assert len(found) == 1
    x = found[0]
    assert {x.member_a, x.member_b} == {d1.id, d2.id}
    assert x.point == pytest.approx((2.0, 0.0, 1.5)) and x.param_a == pytest.approx(0.5)


def test_restraints_list_each_crossing_from_both_members():
    s, c, d1, d2 = _panel()
    r = crossing_restraints(s)
    assert r[d1.id] == [(pytest.approx(0.5), d2.id)] and r[d2.id] == [(pytest.approx(0.5), d1.id)]
    assert set(r) == {d1.id, d2.id}


def test_skew_members_and_contacts_at_an_end_are_not_crossings():
    s = ModelState()
    a, b = s.add_node(0, 0, 0), s.add_node(4, 0, 0)
    s.add_member(a.id, b.id)
    c, d = s.add_node(2, -1, 0.05), s.add_node(2, 1, 0.05)       # passes 5 cm above: skew
    s.add_member(c.id, d.id)
    e, f = s.add_node(2, 0, 0), s.add_node(2, 3, 0)               # starts ON the member: a T, not an X
    s.add_member(e.id, f.id)
    assert find_crossings(s) == []


def test_parallel_members_and_shared_nodes_are_ignored():
    s = ModelState()
    for y in (0.0, 1.0):
        s.add_member(s.add_node(0, y, 0).id, s.add_node(4, y, 0).id)
    assert find_crossings(s) == []
    s2, c, d1, d2 = _panel()
    s2.add_member(c[0].id, c[2].id)                               # another member on the same two nodes
    assert all({x.member_a, x.member_b} != {d1.id, s2.members[-1].id} for x in find_crossings(s2))


def test_member_ids_limits_the_search():
    s, c, d1, d2 = _panel()
    assert find_crossings(s, member_ids={d1.id}) == []
    assert len(find_crossings(s, member_ids={d1.id, d2.id})) == 1


# ── the buckling length ──────────────────────────────────────────────────────

def test_tension_partner_holds_the_member_at_the_crossing():
    assert dc.buckling_length(5.0, [(0.5, 7)], lambda pid: -10e3) == pytest.approx(2.5)


def test_compressed_unloaded_or_unknown_partner_gives_no_support():
    for n in (+10e3, 0.0, None):
        assert dc.buckling_length(5.0, [(0.5, 7)], lambda pid, n=n: n) == pytest.approx(5.0)


def test_off_centre_crossing_leaves_the_longer_stretch():
    assert dc.buckling_length(10.0, [(0.3, 7)], lambda pid: -1.0) == pytest.approx(7.0)


def test_two_holding_crossings_leave_the_longest_gap():
    got = dc.buckling_length(10.0, [(0.2, 1), (0.5, 2)], lambda pid: -1.0)
    assert got == pytest.approx(5.0)                                  # gaps 2, 3, 5
    only_second = dc.buckling_length(10.0, [(0.2, 1), (0.5, 2)], lambda pid: -1.0 if pid == 2 else +1.0)
    assert only_second == pytest.approx(5.0)
    only_first = dc.buckling_length(10.0, [(0.2, 1), (0.5, 2)], lambda pid: -1.0 if pid == 1 else +1.0)
    assert only_first == pytest.approx(8.0)


# ── the model flag and the canvas ────────────────────────────────────────────

def _angle_panel(flag: bool):
    s, c, d1, d2 = _panel()
    sec = angle_properties("L 80×8")
    for m in s.members:
        m.element_type, m.E, m.fy, m.density = ElementType.BAR, 210e9, 275e6, 7850.0
        apply_section(m, sec)
        m.group = "diag" if m in (d1, d2) else "frame"
    c[0].support_type = SupportType.PIN
    c[1].support_type = SupportType.PIN
    s.load_cases[0].set_node_load(c[3].id, NodeLoad(fx=10e3))        # racking: c0-c2 stretches, c1-c3 shortens
    s.crossing_braces = flag
    combo = LoadCombination(id=1, name="ULS", limit_state="ULS", factors={s.load_cases[0].id: 1.0})
    s.combinations.append(combo)
    return s, c, d1, d2, combo


def _solved(s):
    from ui_qt.model_builder import build_model
    from ui_qt.solve_actions import solve_engine
    model, emap = build_model(s, s.load_cases[0])
    return solve_engine(model, emap, s)


def test_flag_off_leaves_every_buckling_length_at_the_member_length():
    from ui_qt.canvas import StructCanvas
    s, c, d1, d2, _ = _angle_panel(False)
    sc = StructCanvas()
    sc.load_state(s)
    lengths = sc.buckling_lengths(_solved(s)["member_results"])
    assert lengths[d1.id] == pytest.approx(5.0) and lengths[d2.id] == pytest.approx(5.0)
    sc.clearSelection()


def test_flag_on_holds_only_the_compressed_diagonal():
    from ui_qt.canvas import StructCanvas
    s, c, d1, d2, _ = _angle_panel(True)
    cache = _solved(s)
    forces = {r.element_id: dc.member_forces(r)[0] for r in cache["member_results"]}
    assert forces[d1.id] < 0 < forces[d2.id]                          # c0-c2 in tension, c1-c3 compressed
    sc = StructCanvas()
    sc.load_state(s)
    lengths = sc.buckling_lengths(cache["member_results"])
    assert lengths[d2.id] == pytest.approx(2.5)                       # compressed, partner pulls: held
    assert lengths[d1.id] == pytest.approx(5.0)                       # in tension: nothing to hold
    assert lengths[s.members[0].id] == pytest.approx(4.0)             # not crossed: member length
    sc.clearSelection()


def test_tooltip_reports_the_shortened_buckling_length():
    from ui_qt.canvas import StructCanvas
    s, c, d1, d2, _ = _angle_panel(True)
    cache = _solved(s)
    sc = StructCanvas()
    sc.load_state(s)
    sc.results_provider = lambda: cache
    text = sc._member_items[d2.id].tooltip_text()
    assert "Lcr = 2.50 m (held at crossing)" in text and "buckling, EN 1993-1-1" in text
    assert "held at crossing" not in sc._member_items[d1.id].tooltip_text()
    sc.clearSelection()


def test_colour_uses_the_shorter_length():
    from ui_qt.canvas import StructCanvas
    results = {}
    for flag in (False, True):
        s, c, d1, d2, _ = _angle_panel(flag)
        cache = _solved(s)
        sc = StructCanvas()
        sc.load_state(s)
        lengths = sc.buckling_lengths(cache["member_results"])
        r = next(r for r in cache["member_results"] if r.element_id == d2.id)
        results[flag] = dc.display_utilisation(s.get_member(d2.id), r, lengths[d2.id])[0]
        sc.update_member_util_colours(cache["member_results"], s.members)
        sc.clearSelection()
    assert results[True] < results[False]


def test_flag_survives_save_and_load_and_defaults_off():
    s = ModelState()
    assert ModelState.from_dict(s.to_dict()).crossing_braces is False and "crossing_braces" not in s.to_dict()
    s.crossing_braces = True
    assert ModelState.from_dict(s.to_dict()).crossing_braces is True


def test_optimiser_picks_a_lighter_diagonal_when_the_crossing_holds_it():
    s0, c, d1, d2, combo0 = _angle_panel(False)
    s1, c, d1, d2, combo1 = _angle_panel(True)
    r0 = optimise_groups(s0, [combo0], target=0.85)
    r1 = optimise_groups(s1, [combo1], target=0.85)
    a0 = angle_properties(next(g.after for g in r0.groups if g.group == "diag")).A
    a1 = angle_properties(next(g.after for g in r1.groups if g.group == "diag")).A
    assert a1 < a0
    assert all(g.eta_after <= 0.85 + 1e-9 for g in r1.groups)


def test_window_toggle_sets_the_flag_and_follows_the_loaded_model(monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    from ui_qt.main_window import MainWindow
    monkeypatch.setattr(MainWindow, "_show_welcome", lambda self: None)
    monkeypatch.setattr(MainWindow, "_check_autosave_recovery", lambda self: False)
    for name in ("question", "warning", "information", "critical"):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    win = MainWindow()
    act = win._act["crossing_braces"]
    assert not act.isChecked()
    act.trigger()
    assert win._scene.model_state.crossing_braces is True
    s, *_ = _panel()
    s.crossing_braces = False
    win._scene.load_state(s)
    win._scene.model_changed.emit()                                  # as after undo/open: the action follows
    assert not act.isChecked()
    win._is_dirty = False
    win._scene.clearSelection()
    win.close()
