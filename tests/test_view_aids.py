"""View aids: cursor coordinates, select by group/profile, hide by group, ..."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QPointF


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication([])


def _scene(z_top=0.0):
    from ui_qt.canvas import StructCanvas
    from ui_qt.model_state import ModelState
    state = ModelState()
    a, b, c = state.add_node(0, 0, 0), state.add_node(4, 0, 0), state.add_node(4, 3, z_top)
    state.add_member(a.id, b.id)
    state.add_member(b.id, c.id)
    sc = StructCanvas()
    sc.load_state(state)
    return sc


def test_cursor_text_2d_reads_model_coordinates(qapp):
    from ui_qt.canvas_items import PX_PER_M
    sc = _scene()
    sc.model_state.analysis_mode = "2D"
    assert sc.cursor_text(QPointF(2 * PX_PER_M, -1.5 * PX_PER_M)) == "x = 2.00   y = 1.50 m"


def test_cursor_text_3d_inverts_the_projection_on_the_working_plane(qapp):
    import ui_qt.projection as proj
    from ui_qt.canvas_items import PX_PER_M
    sc = _scene(z_top=3.0)
    sc._working_plane = type(sc._working_plane).XY
    sc._plane_offset = 3.0
    sx, sy = proj.isometric(1.0, 2.0, 3.0)
    assert sc.cursor_text(QPointF(sx, sy)).startswith("x = 1.00   y = 2.00   z = 3.00 m")


def test_cursor_signal_fires_on_mouse_move(qapp):
    class Ev:                                   # QGraphicsSceneMouseEvent cannot be built in Python
        def scenePos(self): return QPointF(0, 0)
        def __getattr__(self, name): return lambda *a, **k: None
    sc = _scene()
    seen = []
    sc.cursor_coords.connect(seen.append)
    try:
        sc.mouseMoveEvent(Ev())
    except TypeError:
        pass                                    # the base-class call rejects the stub; the signal is already out
    assert seen and seen[-1].startswith("x = ")


# ── select same group / section ───────────────────────────────────────────────

def _grouped_scene():
    from ui_qt.canvas import StructCanvas
    from ui_qt.model_state import ModelState
    state = ModelState()
    n = [state.add_node(i, 0, 0) for i in range(5)]
    ms = [state.add_member(n[i].id, n[i + 1].id) for i in range(4)]
    for m, g, a in zip(ms, ("Leg", "Leg", "Brace", ""), (0.01, 0.02, 0.01, 0.01)):
        m.group, m.A = g, a
    sc = StructCanvas()
    sc.load_state(state)
    return sc, ms


def test_member_ids_like_group_and_section(qapp):
    sc, ms = _grouped_scene()
    assert sc.member_ids_like(ms[0], "group") == [ms[0].id, ms[1].id]
    assert sc.member_ids_like(ms[3], "group") == [ms[3].id]          # no group: only itself
    assert sc.member_ids_like(ms[0], "section") == [ms[0].id, ms[2].id, ms[3].id]


def test_select_members_replaces_selection_and_skips_hidden(qapp):
    sc, ms = _grouped_scene()
    sc._member_items[ms[3].id].setSelected(True)
    sc._member_items[ms[1].id].setVisible(False)
    sc.select_members([ms[0].id, ms[1].id])
    selected = {it.member.id for it in sc.selectedItems() if hasattr(it, "member")}
    assert selected == {ms[0].id}


def test_window_shows_cursor_coordinates_in_the_status_bar(qapp, monkeypatch):
    from ui_qt.main_window import MainWindow
    monkeypatch.setattr(MainWindow, "_show_welcome", lambda self: None)
    monkeypatch.setattr(MainWindow, "_check_autosave_recovery", lambda self: False)
    win = MainWindow()
    try:
        win._scene.cursor_coords.emit("x = 1.00   y = 2.00 m")
        assert win._sb_cursor.text() == "x = 1.00   y = 2.00 m"
    finally:
        win.close()


# ── Groups panel ──────────────────────────────────────────────────────────────

def test_group_rows_quantities_and_profile_names(qapp):
    from ui_qt.angle_sections import angle_properties
    from ui_qt.groups_panel import group_rows
    sc, ms = _grouped_scene()                       # Leg, Leg, Brace, (none); each 1 m long
    s = angle_properties("L 100×10")
    for m in ms[:2]:
        m.A, m.I, m.density = s.A, s.I_u, 7850.0
    rows = {r.name: r for r in group_rows(sc.model_state)}
    assert list(rows) == ["Leg", "Brace", ""]       # first-seen order, ungrouped last
    leg = rows["Leg"]
    assert leg.member_ids == (ms[0].id, ms[1].id) and leg.length == pytest.approx(2.0)
    assert leg.mass == pytest.approx(2 * s.A * 7850.0) and leg.profile == "L 100×10"
    assert rows["Brace"].mass == 0.0 and rows[""].label == "(no group)"
    ms[1].A = 0.005
    assert group_rows(sc.model_state)[0].profile.startswith("mixed")


def test_apply_section_sets_every_member_and_keeps_unset_extras(qapp):
    from ui_qt.angle_sections import angle_properties
    from ui_qt.groups_panel import apply_section
    from ui_qt.section_library import angle_section_extras as extras
    sc, ms = _grouped_scene()
    ms[0].W_pl = 7e-4
    s = angle_properties("L 100×10")
    apply_section(ms[:2], (210e9, s.A, s.I_u, 0.0, s.W_u, 0.0, 0.0, 7850.0, 355e6, "steel"),
                  extras("L 100×10"))
    for m in ms[:2]:
        assert (m.A, m.I, m.I_y, m.J, m.density, m.fy) == (s.A, s.I_u, s.I_v, s.J, 7850.0, 355e6)
        assert m.W_el == s.W_u
    assert ms[0].W_pl == 7e-4                       # picker gave 0 -> untouched
    assert ms[2].A == 0.01                          # other groups untouched


def test_hiding_a_group_hides_members_nodes_and_restores(qapp):
    sc, ms = _grouped_scene()                       # chain of 5 nodes; Leg = members 0,1
    sc.set_group_hidden("Leg", True)
    vis = {m.id: sc._member_items[m.id].isVisible() for m in ms}
    assert vis == {ms[0].id: False, ms[1].id: False, ms[2].id: True, ms[3].id: True}
    nodes = {n: it.isVisible() for n, it in sc._node_items.items()}
    n = [m.node_i for m in ms] + [ms[-1].node_j]
    assert not nodes[n[0]] and not nodes[n[1]]      # only touch hidden members
    assert nodes[n[2]] and nodes[n[3]] and nodes[n[4]]   # shared / visible-member nodes stay
    sc.show_all_groups()
    assert all(it.isVisible() for it in list(sc._member_items.values()) + list(sc._node_items.values()))


def test_hidden_groups_survive_isolate_and_restore(qapp):
    sc, ms = _grouped_scene()
    sc.set_group_hidden("Brace", True)
    sc._member_items[ms[0].id].setSelected(True)
    sc.toggle_isolate()                              # isolate member 0 ...
    assert sc._member_items[ms[0].id].isVisible() and not sc._member_items[ms[1].id].isVisible()
    sc.toggle_isolate()                              # ... and restore everything
    assert sc._member_items[ms[1].id].isVisible()
    assert not sc._member_items[ms[2].id].isVisible()           # Brace is still hidden


def test_panel_checkbox_toggles_visibility_and_profile_button_assigns(qapp, monkeypatch):
    from PyQt6.QtCore import Qt
    import ui_qt.section_picker as picker
    from ui_qt.angle_sections import angle_properties
    from ui_qt.groups_panel import GroupsPanel
    from ui_qt.section_library import angle_section_extras
    sc, ms = _grouped_scene()
    panel = GroupsPanel(sc)
    panel.refresh()
    assert panel._table.rowCount() == 3
    panel._table.item(0, 0).setCheckState(Qt.CheckState.Unchecked)       # hide "Leg"
    assert "Leg" in sc._hidden_groups and not sc._member_items[ms[0].id].isVisible()

    s = angle_properties("L 80×8")

    class Stub:
        def __init__(self, *a, **k): pass
        def exec(self): return True
        def get_result(self): return (210e9, s.A, s.I_u, s.W_u, s.W_u, 0.0, 0.0, 7850.0, 355e6, "steel")
        def get_extra(self): return angle_section_extras("L 80×8")

    monkeypatch.setattr(picker, "SectionPickerDialog", Stub)
    panel._table.selectRow(1)                                            # "Brace"
    panel._assign_profile()
    assert ms[2].A == s.A and ms[2].I_y == s.I_v
    assert ms[0].A == 0.01                                               # Leg untouched
    assert panel._table.item(1, 5).text() == "L 80×8"


def test_window_has_a_groups_dock_in_the_view_menu(qapp, monkeypatch):
    from ui_qt.main_window import MainWindow
    monkeypatch.setattr(MainWindow, "_show_welcome", lambda self: None)
    monkeypatch.setattr(MainWindow, "_check_autosave_recovery", lambda self: False)
    win = MainWindow()
    try:
        assert win._groups_dock.windowTitle() == "Groups"
        win._groups_panel.refresh()
        win._reset_dock_layout()
    finally:
        win.close()


# ── validation findings point at the offending items ─────────────────────────

def test_validation_issues_name_the_nodes_and_members(qapp):
    from ui_qt.model_state import ModelState, SupportType
    from ui_qt.solve_actions import validate_model, validate_model_issues
    state = ModelState()
    a, b, c = state.add_node(0, 0, 0), state.add_node(3, 0, 0), state.add_node(9, 9, 0)
    state.add_member(a.id, b.id)
    z = state.add_node(3, 0, 0)
    state.add_member(b.id, z.id)                       # zero-length member
    a.support_type = SupportType.ROLLER
    issues = validate_model_issues(state)
    by_text = {i.text.split(":")[0].split(" has")[0]: i for i in issues}
    floating = next(i for i in issues if i.text.startswith("Floating"))
    assert floating.node_ids == (c.id,)
    zero = next(i for i in issues if "zero length" in i.text)
    assert zero.member_ids == (state.members[1].id,) and set(zero.node_ids) == {b.id, z.id}
    rollers = next(i for i in issues if i.text.startswith("No PIN or FIXED"))
    assert rollers.node_ids == (a.id,)
    errors, _ = validate_model(state)                  # the string API is unchanged
    assert [i.text for i in issues if i.severity == "error"] == errors


def test_focus_on_selects_and_ignores_missing_ids(qapp):
    sc, ms = _grouped_scene()
    sc.views()  # no view attached in the test: selection only
    n = sc.focus_on(node_ids=[ms[0].node_i], member_ids=[ms[1].id, 9999])
    assert n == 2
    sel = sc.selectedItems()
    assert {type(i).__name__ for i in sel} == {"NodeItem", "MemberItem"}
    assert sc.focus_on([12345]) == 0 and not sc.selectedItems()


def test_mechanism_error_carries_the_node_ids():
    from solver.linear_solver import UnstableStructureError
    err = UnstableStructureError("mechanism", hint="h", node_ids=(4, 7))
    assert err.node_ids == (4, 7) and "Singular matrix" in str(err)


def test_window_selects_the_problem_items_after_a_blocked_solve(qapp, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    from ui_qt.main_window import MainWindow
    from ui_qt.model_state import ModelState, SupportType
    monkeypatch.setattr(MainWindow, "_show_welcome", lambda self: None)
    monkeypatch.setattr(MainWindow, "_check_autosave_recovery", lambda self: False)
    shown = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: shown.append(a[1]))
    for name in ("question", "warning", "information"):     # a stray modal would hang the run
        monkeypatch.setattr(QMessageBox, name,
                            lambda *a, _n=name, **k: pytest.fail(f"unexpected {_n} dialog: {a[1:3]}"))
    state = ModelState()
    a, b, c = state.add_node(0, 0, 0), state.add_node(3, 0, 0), state.add_node(9, 9, 0)
    state.add_member(a.id, b.id)
    a.support_type = SupportType.PIN
    win = MainWindow()
    try:
        win._scene.load_state(state)
        win._on_solve() if hasattr(win, "_on_solve") else win._solve()
        assert shown and "validation" in shown[0].lower()
        sel = win._scene.selectedItems()
        assert [getattr(i, "node", None).id for i in sel] == [c.id]
    finally:
        win._is_dirty = False                  # no "save changes?" prompt on close
        win.close()
