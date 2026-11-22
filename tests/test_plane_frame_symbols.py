"""A plane frame seen in its XZ plane (Front view) draws the 2D drawing-office symbols;
orbited, the 3D bearings return.  Its (ux, uz, θy) are the 2D (ux, uy, θz) on screen."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from ui_qt import support_glyphs as sg
from ui_qt.model_state import ModelState, NodeData, SupportType


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.mark.parametrize("az, el, side", [(0, 2, 1), (3, -4, 1), (180, 2, -1), (-178, 0, -1),
                                          (-45, 30, 0), (0, 30, 0), (90, 2, 0), (20, 2, 0)])
def test_elevation_side(az, el, side):
    assert sg.elevation_side(az, el) == side


def _rects(ops):
    return [op.path.boundingRect() for op in ops]


@pytest.mark.parametrize("preset, kind_2d", [
    (SupportType.FIXED, "FIXED"), (SupportType.PIN, "PIN"),
    (SupportType.ROLLER, "ROLLER"),                 # free in X: wheels under the node
    (SupportType.ROLLER_Z, "ROLLER_Y"),             # free vertically: the 2D wall roller
])
def test_front_view_draws_the_2d_symbol(qapp, preset, kind_2d):
    node = NodeData(id=0, x=0, y=0)
    node.support_type = preset
    cam = sg.Camera.from_angles(0.0, 2.0)
    ops = sg.support_ops(node, cam, False, elevation=1)
    assert _rects(ops) == _rects(sg.drawing_ops_2d(kind_2d))


def test_back_view_is_the_mirror_image(qapp):
    node = NodeData(id=0, x=0, y=0)
    node.support_type = SupportType.ROLLER_Z            # wall roller: drawn to one side
    cam = sg.Camera.from_angles(180.0, 2.0)
    front = _rects(sg.support_ops(node, cam, False, elevation=1))
    back = _rects(sg.support_ops(node, cam, False, elevation=-1))
    assert [(-r.right(), r.top()) for r in front] == pytest.approx([(r.left(), r.top()) for r in back])


def test_springs_and_restraint_view_map_to_the_plane(qapp):
    node = NodeData(id=0, x=0, y=0)
    node.support_type = SupportType.SPRING
    node.spring_kz, node.spring_kry = 2e6, 5e5            # vertical + rotation in the plane
    cam = sg.Camera.from_angles(0.0, 2.0)
    ops = sg.support_ops(node, cam, False, elevation=1)
    assert _rects(ops) == _rects(sg.drawing_ops_2d("SPRING", (0, 2e6, 0, 0, 0, 5e5)))
    pin = NodeData(id=1, x=0, y=0)
    pin.support_type = SupportType.PIN
    markers = sg.support_ops(pin, cam, True, elevation=1)
    assert _rects(markers) == _rects(sg.restraint_ops_2d((True, True, False, False, False, False)))


def test_node_item_uses_2d_symbols_only_for_a_plane_frame_in_elevation(qapp):
    import ui_qt.projection as proj
    from ui_qt.canvas_items import NodeItem

    class Scene:
        def __init__(self, ms):
            self.model_state = ms

        def removeItem(self, item):
            pass

    def ops(analysis_type, az, el):
        proj.ISO_AZIMUTH, proj.ISO_ELEVATION = az, el
        ms = ModelState(nodes=[NodeData(id=0, x=0, y=0, z=0)])
        ms.analysis_type = analysis_type
        ms.nodes[0].support_type = SupportType.PIN
        return _rects(NodeItem(ms.nodes[0], Scene(ms))._support_items[0].ops)

    flat = _rects(sg.drawing_ops_2d("PIN"))
    assert ops("plane_xz", 0.0, 2.0) == flat
    assert ops("plane_xz", -45.0, 30.0) != flat          # orbited: the 3D bearing
    assert ops("space", 0.0, 2.0) != flat                # a space frame keeps its bearings
