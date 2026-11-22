"""Dragging nodes of a plane frame in the Front view: they move in the frame's XZ plane,
snapped to 0.25 m, y unchanged; orbited, a drag is refused; space frames stay locked."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsItem

import ui_qt.projection as proj
from ui_qt.model_state import ModelState, SupportType


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def _scene(analysis_type="plane_xz", y=1.5):
    from ui_qt.canvas import CanvasMode, StructCanvas
    s = ModelState()
    s.analysis_type = analysis_type
    a, b = s.add_node(0, y, 0), s.add_node(4, y, 3)
    a.support_type = SupportType.PIN
    s.add_member(a.id, b.id)
    sc = StructCanvas()
    sc.load_state(s)
    sc.set_mode(CanvasMode.SELECT)
    return sc, s, b


def _movable(item):
    return bool(item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable)


def _drag(item, pos):
    """Move the item as a mouse drag does (between press and release)."""
    item._dragging = True
    item._drag_from = (item.node.x, item.node.y, item.node.z)
    try:
        item.setPos(pos)
    finally:
        item._dragging = False
        item._finish_drag()


def test_a_drag_that_moves_a_node_marks_the_model_changed(qapp):
    proj.ISO_AZIMUTH, proj.ISO_ELEVATION = 0.0, 2.0
    sc, s, b = _scene()
    seen = []
    sc.model_changed.connect(lambda: seen.append(1))
    item = sc.get_node_item(b.id)
    _drag(item, item.pos())                                      # press and release in place
    assert not seen
    _drag(item, QPointF(*proj.isometric(1.0, b.y, 1.0)))
    assert seen == [1]


def test_a_plane_frame_node_drags_in_its_plane_with_snapping(qapp):
    proj.ISO_AZIMUTH, proj.ISO_ELEVATION = 0.0, 2.0               # Front view
    sc, s, b = _scene()
    item = sc.get_node_item(b.id)
    assert _movable(item)
    _drag(item, QPointF(*proj.isometric(2.1, b.y, 3.3)))
    assert (b.x, b.y, b.z) == (2.0, 1.5, 3.25)                    # snapped, y kept
    assert (item.pos().x(), item.pos().y()) == pytest.approx(proj.isometric(2.0, 1.5, 3.25))


def test_the_member_follows_the_dragged_node(qapp):
    proj.ISO_AZIMUTH, proj.ISO_ELEVATION = 0.0, 2.0
    sc, s, b = _scene()
    item = sc.get_node_item(b.id)
    _drag(item, QPointF(*proj.isometric(5.0, b.y, 2.0)))
    line = sc._member_items[s.members[0].id].line()
    assert (line.x2(), line.y2()) == pytest.approx(proj.isometric(5.0, 1.5, 2.0))


def test_back_view_drag_also_works(qapp):
    proj.ISO_AZIMUTH, proj.ISO_ELEVATION = 180.0, 2.0
    sc, s, b = _scene()
    _drag(sc.get_node_item(b.id), QPointF(*proj.isometric(-1.0, b.y, 2.5)))
    assert (b.x, b.z) == (-1.0, 2.5)


def test_orbited_a_drag_is_refused(qapp):
    proj.ISO_AZIMUTH, proj.ISO_ELEVATION = -45.0, 30.0
    sc, s, b = _scene()
    item = sc.get_node_item(b.id)
    before = (item.pos().x(), item.pos().y())
    _drag(item, QPointF(before[0] + 50, before[1] + 30))
    assert (b.x, b.y, b.z) == (4.0, 1.5, 3.0)
    assert (item.pos().x(), item.pos().y()) == pytest.approx(before)


def test_space_frame_nodes_stay_locked(qapp):
    proj.ISO_AZIMUTH, proj.ISO_ELEVATION = 0.0, 2.0
    sc, s, b = _scene("space")
    assert not _movable(sc.get_node_item(b.id))


@pytest.mark.parametrize("az, el", [(3.0, 2.0), (0.0, 8.0), (180.0, 2.0), (-45.0, 30.0)])
def test_changing_the_view_never_moves_an_off_grid_node(qapp, az, el):
    """Regression: re-projection also calls setPos, and the drag snapping used to move a node
    at (1.37, 2.11) to (1.25, 2.00) when the view was nudged."""
    from ui_qt.canvas import CanvasMode, StructCanvas
    proj.ISO_AZIMUTH, proj.ISO_ELEVATION = 0.0, 2.0
    s = ModelState()
    s.analysis_type = "plane_xz"
    a, b = s.add_node(0, 0, 0), s.add_node(1.37, 0, 2.11)
    s.add_member(a.id, b.id)
    sc = StructCanvas()
    sc.load_state(s)
    sc.set_mode(CanvasMode.SELECT)
    sc.set_view(az, el)
    assert (b.x, b.y, b.z) == (1.37, 0, 2.11)
