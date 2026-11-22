"""Support symbols (ui_qt/support_glyphs.py): restraints match the solver, 3D solids are shaded
and culled correctly, every type draws in 2D, 3D and as restraint markers."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest

import ui_qt.projection as _proj
from ui_qt import support_glyphs as sg
from ui_qt.model_state import ModelState, NodeData, SupportType


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _restore_view_state():
    """Tests change the live orbit and the restraint view: restore them."""
    import ui_qt.canvas_items as ci
    az0, el0, rs0 = _proj.ISO_AZIMUTH, _proj.ISO_ELEVATION, ci._SHOW_RESTRAINTS
    yield
    _proj.ISO_AZIMUTH, _proj.ISO_ELEVATION = az0, el0
    ci.set_show_restraints(rs0)


ALL = ["FIXED", "PIN", "ROLLER", "ROLLER_Y", "ROLLER_Z", "SPRING"]


# ── restraints come from the solver's own table ─────────────────────────────

def test_restraint_flags_in_3d():
    f = sg.restraint_flags
    assert f("FIXED", True) == (True,) * 6
    assert f("PIN", True) == (True, True, True, False, False, False)
    assert f("ROLLER", True) == (False, True, True, False, False, False)      # free in X
    assert f("ROLLER_Y", True) == (True, False, True, False, False, False)    # free in Y
    assert f("ROLLER_Z", True) == (True, True, False, False, False, False)    # free in Z
    assert f("SPRING", True) == (False,) * 6


def test_restraint_flags_in_2d_and_roller_z_is_a_pin():
    f = sg.restraint_flags
    assert f("FIXED", False) == (True, True, False, False, False, True)
    assert f("ROLLER", False) == (False, True, False, False, False, False)
    assert f("ROLLER_Y", False) == (True, False, False, False, False, False)
    assert f("ROLLER_Z", False) == f("PIN", False)          # the solver restrains X and Y
    pin_ops = sg.drawing_ops_2d("PIN")
    rz_ops = sg.drawing_ops_2d("ROLLER_Z")
    assert [op.path.boundingRect() for op in rz_ops] == [op.path.boundingRect() for op in pin_ops]


def test_node_springs_reads_k_theta_for_rotation_about_z():
    n = NodeData(id=0, x=0, y=0)
    n.support_type = SupportType.SPRING
    n.spring_kx, n.spring_ktheta = 5.0, 7.0
    assert sg.node_springs(n) == (5.0, 0.0, 0.0, 0.0, 0.0, 7.0)
    n.support_type = SupportType.PIN                         # springs ignored by the solver
    assert sg.node_springs(n) == (0.0,) * 6


# ── camera, shading, culling ────────────────────────────────────────────────

@pytest.mark.parametrize("az,el", [(-45, 30), (20, 60), (135, 10)])
def test_camera_projects_like_the_canvas(az, el):
    cam = sg.Camera.from_angles(az, el)
    p = np.array([0.3, -0.7, 0.4])
    q = cam.project(p, 80.0)
    assert (q.x(), q.y()) == pytest.approx(_proj.isometric(*p, azimuth_deg=az, elevation_deg=el))
    assert cam.toward == pytest.approx(_proj.camera_dir(az, el))


def test_top_view_shows_only_the_tops_of_a_box(qapp):
    cam = sg.Camera.from_angles(0.0, 90.0)
    ops = sg.glyph_ops(sg.Glyph([sg._box([0, 0, 0], [1, 1, 1], sg.SUPPORT_TONE)]), cam, 10.0)
    assert len(ops) == 1                                     # five faces culled
    assert ops[0].path.boundingRect().width() == pytest.approx(20.0)


def test_faces_lit_towards_the_light_are_lighter():
    cam = sg.Camera.from_angles(-45, 30)
    lit = sg.shade(sg.SUPPORT_TONE, cam.light, cam)
    dark = sg.shade(sg.SUPPORT_TONE, -cam.light, cam)
    assert sum(sg._hex_rgb(lit)) > sum(sg._hex_rgb(dark))


def test_roller_cylinders_lie_across_the_free_direction():
    cam = sg.Camera.from_angles(-45, 30)
    for kind, across in (("ROLLER", 1), ("ROLLER_Y", 0)):
        cylinders = [s for s in sg.bearing_glyph(kind, cam).solids if s.smooth]
        assert len(cylinders) == 2
        for cyl in cylinders:
            extent = np.ptp(np.vstack(cyl.faces), axis=0)
            assert np.argmax(extent) == across, kind


def test_bearings_sit_below_the_node():
    cam = sg.Camera.from_angles(-45, 30)
    for kind in ("FIXED", "PIN", "ROLLER", "ROLLER_Y"):
        top = max(np.vstack(s.faces)[:, 2].max() for s in sg.bearing_glyph(kind, cam).solids)
        assert top <= 1e-9, kind


def test_restraint_markers_count_cones_discs_and_springs():
    fixed = sg.restraint_glyph((True,) * 6)
    assert len(fixed.solids) == 6 and not fixed.lines
    springs = sg.restraint_glyph((False,) * 6, (1.0, 0, 1.0, 0, 0, 1.0))
    assert not springs.solids and len(springs.lines) == 3
    assert {c for _pts, c, _w in springs.lines} == {sg.AXIS[0], sg.AXIS[2]}


def test_spring_without_stiffness_still_shows_a_coil():
    cam = sg.Camera.from_angles(-45, 30)
    assert sg.bearing_glyph("SPRING", cam).lines
    assert sg.drawing_ops_2d("SPRING")


# ── through the real NodeItem ────────────────────────────────────────────────

class _FakeScene:
    def __init__(self, model_state):
        self.model_state = model_state

    def removeItem(self, item):
        pass


def _node_item(kind, three_d):
    from ui_qt.canvas_items import NodeItem
    ms = ModelState(nodes=[NodeData(id=0, x=1.0, y=2.0, z=4.0 if three_d else 0.0)])
    ms.analysis_mode = "3D" if three_d else "2D"
    ms.nodes[0].support_type = SupportType[kind]
    return NodeItem(ms.nodes[0], _FakeScene(ms))


@pytest.mark.parametrize("kind", ALL)
@pytest.mark.parametrize("three_d, az, el", [(False, -45, 30), (True, -45, 30), (True, -15, 60),
                                             (True, -80, 10), (True, 120, -20)])
@pytest.mark.parametrize("restraints", [False, True])
def test_every_support_draws_one_glyph_item(qapp, kind, three_d, az, el, restraints):
    from ui_qt.canvas_items import SupportGlyphItem, set_show_restraints
    _proj.ISO_AZIMUTH, _proj.ISO_ELEVATION = az, el
    set_show_restraints(restraints)
    item = _node_item(kind, three_d)
    assert len(item._support_items) == 1
    glyph = item._support_items[0]
    assert isinstance(glyph, SupportGlyphItem) and glyph.parentItem() is item
    if not (restraints and kind == "SPRING"):            # an unset spring has no restraint
        assert glyph.ops and not glyph.boundingRect().isEmpty()


def test_show_restraints_action_redraws_the_supports(qapp, monkeypatch):
    from ui_qt.main_window import MainWindow
    monkeypatch.setattr(MainWindow, "_show_welcome", lambda self: None)
    monkeypatch.setattr(MainWindow, "_check_autosave_recovery", lambda self: False)
    win = MainWindow()
    try:
        scene = win._scene
        node = scene.model_state.add_node(0.0, 0.0, 0.0)
        node.support_type = SupportType.FIXED
        scene._rebuild_items()
        item = scene.get_node_item(node.id)
        fills = lambda: {op.fill.name() for op in item._support_items[0].ops if op.fill is not None}
        bearings = fills()
        win._act["show_restraints"].setChecked(True)
        markers = fills()
        assert markers and not markers & bearings            # axis colours replace the support green
        win._act["show_restraints"].setChecked(False)
        assert fills() == bearings
    finally:
        win._act["show_restraints"].setChecked(False)
        win._is_dirty = False
        win.close()


def test_free_node_has_no_symbol(qapp):
    item = _node_item("FREE", True)
    assert item._support_items == []


def test_bearings_use_the_support_colour_only(qapp):
    from PyQt6.QtGui import QColor
    allowed = {QColor(c).rgb() for c in (sg.SUPPORT, sg.SUPPORT_LIGHT, sg.SUPPORT_DARK)}
    for kind in ("FIXED", "PIN", "ROLLER", "ROLLER_Y", "ROLLER_Z"):
        for op in sg.drawing_ops_2d(kind):
            assert op.pen is None or QColor(op.pen.rgb()).rgb() in allowed, kind
