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
        qapp.processEvents()                   # run queued zoom/fit calls while the window still exists
        win._is_dirty = False                  # no "save changes?" prompt on close
        win.close()


# ── results in the tooltips ───────────────────────────────────────────────────

def _solved_cantilever():
    from ui_qt.canvas import StructCanvas
    from ui_qt.model_builder import build_model
    from ui_qt.model_state import ModelState, NodeLoad, SupportType
    from ui_qt.solve_actions import solve_engine
    state = ModelState()
    a, b = state.add_node(0, 0, 0), state.add_node(4, 0, 0)
    a.support_type = SupportType.FIXED
    m = state.add_member(a.id, b.id)
    m.E, m.A, m.I, m.W_pl, m.fy = 210e9, 0.01, 1e-4, 4e-4, 275e6
    state.load_cases[0].set_node_load(b.id, NodeLoad(fy=-10e3))     # 10 kN down at the tip
    sc = StructCanvas()
    sc.load_state(state)
    model, emap = build_model(state, state.load_cases[0])
    return sc, state, solve_engine(model, emap, state), m, a, b


def test_tooltips_show_results_only_when_a_solve_is_current(qapp):
    sc, state, cache, m, a, b = _solved_cantilever()
    mt, nt = sc._member_items[m.id].tooltip_text, sc._node_items[b.id].tooltip_text
    assert "current results" not in mt() and "current results" not in nt()      # nothing solved
    sc.results_provider = lambda: cache
    text = mt()
    assert "M max = 40.00 kN·m" in text and "N = 0.0 kN" in text
    assert "utilisation = 0.36" in text                                          # 40 kN·m / (4e-4·275e6)
    tip = nt()
    assert "u = (0.00, -" in tip and "mm" in tip                                 # tip deflects down
    assert "R =" not in tip                                                      # free node: no reaction
    assert "R = (0.0, 10.0" in sc._node_items[a.id].tooltip_text()               # fixed support reaction
    sc.results_provider = lambda: None                                           # edit invalidated the cache
    assert "current results" not in mt()


def test_tooltip_deflection_matches_the_closed_form(qapp):
    sc, state, cache, m, a, b = _solved_cantilever()
    sc.results_provider = lambda: cache
    want_mm = 10e3 * 4 ** 3 / (3 * 210e9 * 1e-4) * 1e3                           # PL^3 / 3EI
    assert f"-{want_mm:.2f}" in sc._node_items[b.id].tooltip_text()


def test_window_feeds_the_canvas_its_solve_cache(qapp, monkeypatch):
    from ui_qt.main_window import MainWindow
    monkeypatch.setattr(MainWindow, "_show_welcome", lambda self: None)
    monkeypatch.setattr(MainWindow, "_check_autosave_recovery", lambda self: False)
    win = MainWindow()
    try:
        assert win._scene.current_results() is None
        win._solve_cache = {"marker": 1}
        assert win._scene.current_results() == {"marker": 1}
        win._solve_cache = None
        assert win._scene.current_results() is None
    finally:
        win.close()


# ── section cut ───────────────────────────────────────────────────────────────

def _column_scene():
    """A 2-storey column: nodes at z = 0, 3, 6; one beam off the middle node."""
    from ui_qt.canvas import StructCanvas
    from ui_qt.model_state import ModelState
    state = ModelState()
    n = [state.add_node(0, 0, 0), state.add_node(0, 0, 3), state.add_node(0, 0, 6), state.add_node(4, 0, 3)]
    ms = [state.add_member(n[0].id, n[1].id), state.add_member(n[1].id, n[2].id),
          state.add_member(n[1].id, n[3].id)]
    sc = StructCanvas()
    sc.load_state(state)
    return sc, n, ms


def test_members_beyond_cuts_only_members_entirely_on_the_removed_side(qapp):
    from ui_qt.section_cut import SectionCut, members_beyond
    sc, n, ms = _column_scene()
    state = sc.model_state
    assert members_beyond(state, SectionCut("Z", 4.0, True)) == {ms[0].id, ms[2].id}   # keep z >= 4
    assert members_beyond(state, SectionCut("Z", 2.0, True)) == set()                  # nothing wholly below z=2
    assert members_beyond(state, SectionCut("Z", 3.0, False)) == set()                 # touching the plane stays
    assert members_beyond(state, SectionCut("Z", 2.9, False)) == {ms[1].id, ms[2].id}  # keep z <= 2.9
    assert members_beyond(state, SectionCut("X", 1.0, False)) == set()                 # beam crosses x=1
    assert members_beyond(state, SectionCut("X", 1.0, True)) == {ms[0].id, ms[1].id}   # both columns at x=0


def test_scene_hides_the_cut_members_and_orphaned_nodes_then_restores(qapp):
    from ui_qt.section_cut import SectionCut
    sc, n, ms = _column_scene()
    sc.set_section_cut(SectionCut("Z", 4.0, True))
    assert [sc._member_items[m.id].isVisible() for m in ms] == [False, True, False]
    assert not sc._node_items[n[0].id].isVisible() and not sc._node_items[n[3].id].isVisible()
    assert sc._node_items[n[1].id].isVisible() and sc._node_items[n[2].id].isVisible()
    sc.clear_section_cut()
    assert all(it.isVisible() for it in list(sc._member_items.values()) + list(sc._node_items.values()))


def test_section_cut_and_hidden_groups_combine(qapp):
    from ui_qt.section_cut import SectionCut
    sc, n, ms = _column_scene()
    ms[1].group = "Upper"
    sc.set_group_hidden("Upper", True)
    sc.set_section_cut(SectionCut("Z", 4.0, True))           # also cuts members 0 and 2
    assert not any(sc._member_items[m.id].isVisible() for m in ms)
    sc.clear_section_cut()
    assert [sc._member_items[m.id].isVisible() for m in ms] == [True, False, True]   # group stays hidden


def test_section_cut_dialog_drives_the_scene_live(qapp):
    from ui_qt.section_cut import SectionCutDialog
    sc, n, ms = _column_scene()
    dlg = SectionCutDialog(sc)
    assert dlg._axis.currentText() == "Z"
    dlg._pos.setValue(4.5)
    assert sc._section_cut.axis == "Z" and sc._section_cut.position == 4.5
    assert not sc._member_items[ms[0].id].isVisible() and sc._member_items[ms[1].id].isVisible()
    assert "2 of 3" in dlg._info.text()
    dlg._keep.setCurrentIndex(1)                              # keep below instead: nothing wholly above 4.5
    assert all(it.isVisible() for it in sc._member_items.values())
    dlg._pos.setValue(2.0)                                    # wholly above z=2: the upper column and the beam
    assert sc._member_items[ms[0].id].isVisible() and not sc._member_items[ms[1].id].isVisible()
    assert not sc._member_items[ms[2].id].isVisible()
    dlg._slider.setValue(0)                                   # slider moves the plane to the model bottom
    assert dlg._pos.value() == 0.0
    dlg.close()                                               # closing restores the full model
    assert sc._section_cut is None
    assert all(it.isVisible() for it in sc._member_items.values())


# ── named views ───────────────────────────────────────────────────────────────

def test_named_views_roundtrip_through_the_project_file(qapp, tmp_path):
    from ui_qt.io import load_model, save_model
    from ui_qt.model_state import ModelState
    s = ModelState()
    s.add_node(0, 0, 0)
    assert "named_views" not in s.to_dict()                    # empty: file format unchanged
    s.named_views["Front"] = {"az": 0.0, "el": 0.0, "cx": 12.5, "cy": -40.0, "scale": 1.75}
    path = tmp_path / "v.slab"
    save_model(s, path)
    loaded = load_model(path)
    assert loaded.named_views == s.named_views
    s.clear()
    assert s.named_views == {}


def test_capture_and_restore_view_returns_to_the_same_camera(qapp):
    import ui_qt.projection as proj
    from ui_qt.canvas import StructView
    sc, n, ms = _column_scene()
    sc.model_state.analysis_mode = "3D"
    view = StructView(sc)
    view.resize(800, 600)
    sc.set_view(-30.0, 20.0)
    view.resetTransform()
    view.scale(1.6, 1.6)
    view.centerOn(40.0, -25.0)
    saved = view.capture_view()
    assert saved["az"] == -30.0 and saved["el"] == 20.0 and saved["scale"] == pytest.approx(1.6)
    sc.set_view(10.0, 70.0)                                    # wander off
    view.resetTransform()
    view.scale(0.4, 0.4)
    view.centerOn(-100.0, 100.0)
    view.restore_view(saved)
    assert (proj.ISO_AZIMUTH, proj.ISO_ELEVATION) == (-30.0, 20.0)
    after = view.capture_view()
    assert after["scale"] == pytest.approx(1.6)
    assert after["cx"] == pytest.approx(saved["cx"], abs=1.0)   # (centerOn is clamped to the scene rect,
    assert after["cy"] == pytest.approx(saved["cy"], abs=1.0)   #  so compare with what was captured)
    sc.set_view(-45.0, 30.0)                                   # leave the module-level default as found


def test_window_saves_restores_and_deletes_named_views(qapp, monkeypatch):
    import ui_qt.projection as proj
    from ui_qt.main_window import MainWindow
    monkeypatch.setattr(MainWindow, "_show_welcome", lambda self: None)
    monkeypatch.setattr(MainWindow, "_check_autosave_recovery", lambda self: False)
    win = MainWindow()
    try:
        win._scene.set_view(-10.0, 25.0)
        win.save_named_view("Detail")
        assert "Detail" in win._scene.model_state.named_views and win._is_dirty
        win._scene.set_view(60.0, 60.0)
        win.restore_named_view("Detail")
        assert (proj.ISO_AZIMUTH, proj.ISO_ELEVATION) == (-10.0, 25.0)
        win._fill_named_views_menu()
        labels = [a.text() for a in win._named_views_menu.actions()]
        assert "Save Current View…" in labels and "Detail" in labels
        win.delete_named_view("Detail")
        assert win._scene.model_state.named_views == {}
    finally:
        win._scene.set_view(-45.0, 30.0)
        qapp.processEvents()
        win._is_dirty = False
        win.close()


# ── deformed-shape animation ──────────────────────────────────────────────────

def test_animation_factor_loops_zero_to_one_to_zero():
    from ui_qt.canvas_overlay import animation_factor
    n = 24
    assert animation_factor(0, n) == pytest.approx(0.0)
    assert animation_factor(n // 2, n) == pytest.approx(1.0)
    assert animation_factor(n, n) == pytest.approx(0.0)                     # wraps
    values = [animation_factor(i, n) for i in range(n)]
    assert all(0.0 <= v <= 1.0 for v in values)
    assert values[:13] == sorted(values[:13]) and values[12:] == sorted(values[12:], reverse=True)


def _deformed_tip_x(items):
    """Screen x of the free end of the deformed polyline(s): the item with the largest extent."""
    return max(i.path().boundingRect().right() for i in items)


def test_update_deformed_layer_redraws_only_that_layer_at_the_given_scale(qapp):
    from ui_qt.canvas_overlay import compute_auto_scales
    sc, state, cache, m, a, b = _solved_cantilever()
    sc.update_overlays(cache["model"], cache["sub_results"], cache["displacements"],
                       cache["member_el_map"])
    bmd_before = list(sc._overlay_items["BMD"])
    _, auto = compute_auto_scales(cache["model"], cache["sub_results"], cache["displacements"])

    def heights(scale):
        sc.update_deformed_layer(cache["model"], cache["displacements"], cache["member_el_map"], scale)
        deformed = [i for i in sc._overlay_items["Deformed"] if i.pen().style().name == "DashLine"]
        return max(i.path().boundingRect().height() for i in deformed)

    small, large = heights(auto), heights(auto * 4)
    assert large > small > 0
    assert sc._overlay_items["BMD"] == bmd_before                       # untouched
    n_items = len(sc._overlay_items["Deformed"])
    heights(auto * 2)
    assert len(sc._overlay_items["Deformed"]) == n_items                # replaced, not accumulated
    uids = [i.data(0) for lst in sc._member_overlay_items.values() for i in lst
            if i in sc._overlay_items["Deformed"]]
    assert len(uids) == n_items                                         # still tagged per member


def test_window_animation_needs_a_solve_and_restores_the_static_overlays(qapp, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    from ui_qt.main_window import MainWindow
    monkeypatch.setattr(MainWindow, "_show_welcome", lambda self: None)
    monkeypatch.setattr(MainWindow, "_check_autosave_recovery", lambda self: False)
    for name in ("question", "warning", "information", "critical"):
        monkeypatch.setattr(QMessageBox, name,
                            lambda *a, _n=name, **k: pytest.fail(f"unexpected {_n} dialog: {a[1:3]}"))
    sc0, state, cache0, m, a, b = _solved_cantilever()
    win = MainWindow()
    try:
        win._animate_act.setChecked(True)                               # nothing solved yet
        assert not win._animate_act.isChecked() and not hasattr(win, "_anim_timer")
        win._scene.load_state(state)
        win._on_solve()
        assert win._solve_cache is not None
        win._animate_act.setChecked(True)
        assert win._anim_timer.isActive()
        shapes = []
        for _ in range(win._ANIM_FRAMES // 2):
            win._anim_tick()
            shapes.append(max(i.path().boundingRect().height()
                              for i in win._scene._overlay_items["Deformed"]
                              if i.pen().style().name == "DashLine"))
        assert shapes[-1] > shapes[0]                                   # grows towards the half-cycle peak
        win._animate_act.setChecked(False)
        assert not win._anim_timer.isActive()
        assert win._scene._overlay_items["BMD"]                         # static overlays are back
    finally:
        if hasattr(win, "_anim_timer"):
            win._anim_timer.stop()
        win._scene.clearSelection()
        qapp.processEvents()
        win._is_dirty = False
        win.close()


# ── colour legends are anchored to the view, not to the repainted area ───────

def test_group_legend_uses_the_whole_view_even_when_only_a_small_area_repaints(qapp):
    from PyQt6.QtCore import QRectF
    from PyQt6.QtGui import QImage, QPainter
    from ui_qt.canvas import StructView
    sc, ms = _grouped_scene()
    sc._colour_by_group = True
    view = StructView(sc)
    view.resize(700, 500)
    seen = []
    view._draw_group_legend = lambda painter, rect: seen.append(QRectF(rect))
    image = QImage(700, 500, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    small = QRectF(100, 100, 40, 30)                       # what a hover repaint exposes
    view.drawBackground(painter, small)
    assert seen == []                                      # the background no longer draws legends
    view.drawForeground(painter, small)
    painter.end()
    assert len(seen) == 1
    whole = view.mapToScene(view.viewport().rect()).boundingRect()
    assert seen[0].width() == pytest.approx(whole.width()) and seen[0].height() == pytest.approx(whole.height())
    assert seen[0].width() > small.width() * 5


def test_show_loads_toggle_runs_without_error(qapp, monkeypatch):
    """Regression: the handler carried two stray lines from a removed 2D/3D toggle (NameError)."""
    from ui_qt.main_window import MainWindow
    monkeypatch.setattr(MainWindow, "_show_welcome", lambda self: None)
    monkeypatch.setattr(MainWindow, "_check_autosave_recovery", lambda self: False)
    win = MainWindow()
    try:
        win._on_show_loads_toggled(False)
        assert win._scene._show_loads is False
        win._on_show_loads_toggled(True)
        assert win._scene._show_loads is True
    finally:
        win._is_dirty = False
        win.close()
