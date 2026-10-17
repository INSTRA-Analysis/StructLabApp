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
