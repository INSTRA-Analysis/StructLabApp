"""G-grab 'along member' (A): slide a node along a connected member, typed or dragged."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import math

import pytest
from PyQt6.QtCore import QPointF, Qt


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication([])


def _scene(qapp):
    """A sloped member a–b (3, 0, 4 → length 5) divided at m, plus a horizontal brace m–c."""
    from ui_qt.canvas import StructCanvas
    from ui_qt.model_state import ModelState
    s = ModelState()
    a, m, b = s.add_node(0, 0, 0), s.add_node(1.5, 0, 2), s.add_node(3, 0, 4)
    c = s.add_node(4, 0, 2)
    lower, upper, brace = s.add_member(a.id, m.id), s.add_member(m.id, b.id), s.add_member(m.id, c.id)
    sc = StructCanvas()
    sc.load_state(s)
    return sc, dict(a=a, m=m, b=b, c=c, lower=lower, upper=upper, brace=brace)


def _grab(sc, node):
    sc._begin_grab([node], QPointF(0, 0))


def _xyz(sc, nid):
    n = sc.model_state.get_node(nid)
    return n.x, n.y, n.z


def test_a_cycles_through_the_connected_members_then_releases(qapp):
    sc, x = _scene(qapp)
    _grab(sc, x["m"])
    assert sc.cycle_grab_member() == x["lower"].id
    assert sc.cycle_grab_member() == x["upper"].id
    assert sc.cycle_grab_member() == x["brace"].id
    assert sc.cycle_grab_member() is None and sc._grab_dir is None


def test_typed_distance_moves_exactly_along_the_member_and_is_not_grid_snapped(qapp):
    sc, x = _scene(qapp)
    _grab(sc, x["m"])
    sc.cycle_grab_member()                         # lower member: direction m -> a
    sc._handle_grab_key(Qt.Key.Key_1, "1")
    sc._handle_grab_key(Qt.Key.Key_Period, ".")
    sc._handle_grab_key(Qt.Key.Key_1, "1")         # 1.1 m towards a
    sc._handle_grab_key(Qt.Key.Key_Return, "")
    px, py, pz = _xyz(sc, x["m"].id)
    assert (px, py, pz) == pytest.approx((1.5 - 0.66, 0, 2 - 0.88))   # 1.1 × (0.6, 0, 0.8)
    assert not sc._grab_active


def test_slide_stays_between_collinear_neighbours(qapp):
    sc, x = _scene(qapp)
    _grab(sc, x["m"])
    sc.cycle_grab_member()                         # along the a–b line
    sc._move_along_member(100.0)                   # far past a
    px, py, pz = _xyz(sc, x["m"].id)
    assert math.dist((px, py, pz), (0, 0, 0)) == pytest.approx(sc._ALONG_MARGIN)
    sc._move_along_member(-100.0)                  # far past b, the other collinear neighbour
    assert math.dist(_xyz(sc, x["m"].id), (3, 0, 4)) == pytest.approx(sc._ALONG_MARGIN)


def test_end_node_can_extend_its_member_but_not_collapse_it(qapp):
    sc, x = _scene(qapp)
    _grab(sc, x["b"])
    sc.cycle_grab_member()                         # upper member, + towards m
    sc._move_along_member(-1.0)                    # extend beyond b
    assert _xyz(sc, x["b"].id) == pytest.approx((3.6, 0, 4.8))
    sc._move_along_member(50.0)
    assert math.dist(_xyz(sc, x["b"].id), (1.5, 0, 2)) == pytest.approx(sc._ALONG_MARGIN)


def test_mouse_drag_projects_onto_the_members_screen_direction(qapp):
    import ui_qt.projection as proj
    sc, x = _scene(qapp)
    _grab(sc, x["m"])
    sc.cycle_grab_member()
    sc.cycle_grab_member()                         # upper: m -> b, unit (0.6, 0, 0.8)
    ex, ey = proj.isometric(0.6, 0.0, 0.8)         # screen pixels per metre along the member
    sc._apply_grab(QPointF(0.5 * ex, 0.5 * ey))    # drag half a metre's worth on screen
    assert _xyz(sc, x["m"].id) == pytest.approx((1.8, 0, 2.4))
    sc._apply_grab(QPointF(0.5 * ex - 40 * ey, 0.5 * ey + 40 * ex))   # sideways motion is ignored
    assert _xyz(sc, x["m"].id) == pytest.approx((1.8, 0, 2.4))


def test_axis_key_releases_the_member_lock_and_free_drag_still_snaps(qapp):
    sc, x = _scene(qapp)
    _grab(sc, x["c"])
    sc.cycle_grab_member()
    sc._handle_grab_key(Qt.Key.Key_X, "x")
    assert sc._grab_member_id is None and sc._grab_axis == "X"
    sc._apply_delta_to_grabbed(0.1, 0, 0)
    sc._confirm_grab()
    assert sc.model_state.get_node(x["c"].id).x == 4.0          # free drag: 4.1 snaps to 4.0


def test_escape_restores_the_node(qapp):
    sc, x = _scene(qapp)
    _grab(sc, x["m"])
    sc.cycle_grab_member()
    sc._move_along_member(0.5)
    sc._handle_grab_key(Qt.Key.Key_Escape, "")
    assert _xyz(sc, x["m"].id) == pytest.approx((1.5, 0, 2))
    assert sc._grab_member_id is None
