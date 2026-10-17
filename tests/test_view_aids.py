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
