"""Tests for the true-3D support-glyph geometry in ui_qt/canvas_items.py.

Support glyphs (FIXED/PIN/ROLLER/ROLLER_Y/ROLLER_Z/SPRING) used to be drawn as
hand-faked pseudo-3D shapes directly in screen space. They were rewritten to
build real 3D vertices (world-metre offsets from the node) and project each
one through isometric(), the same technique already used by the axis triads,
ground grid, and ViewCube elsewhere in this codebase. These tests cover the
new pure geometry helpers directly, plus a headless smoke pass per
SupportType through the real NodeItem drawing pipeline.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import math

import numpy as np
import pytest

import ui_qt.projection as _proj
from ui_qt.projection import isometric
from ui_qt.model_state import ModelState, NodeData, SupportType
from ui_qt.canvas_items import (
    NodeItem,
    _support_bar_axis_world,
    _face_towards_camera,
    _circle_poly_points,
    _helix_points,
    _spiral_points,
    _perp_basis,
    _project_path_3d,
    _project_poly_3d,
    _project_polyline_3d,
    _node_local_pt,
)


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _restore_orbit():
    """Every test may mutate the live ISO_AZIMUTH/ISO_ELEVATION globals that
    isometric() reads by default — restore them so tests don't leak state."""
    az0, el0 = _proj.ISO_AZIMUTH, _proj.ISO_ELEVATION
    yield
    _proj.ISO_AZIMUTH, _proj.ISO_ELEVATION = az0, el0


# ── pure geometry helpers ─────────────────────────────────────────────────────

def test_support_bar_axis_world_picks_wider_screen_axis():
    _proj.ISO_AZIMUTH = 0.0
    assert _support_bar_axis_world() == (1.0, 0.0, 0.0)   # world X reads fully horizontal
    _proj.ISO_AZIMUTH = 90.0
    assert _support_bar_axis_world() == (0.0, 1.0, 0.0)   # world Y reads fully horizontal


def test_face_towards_camera_top_down():
    _proj.ISO_AZIMUTH, _proj.ISO_ELEVATION = 0.0, 90.0   # camera looks straight down +Z
    up_face = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]     # normal = +Z
    down_face = [(0.0, 0.0, 0.0), (0.0, 1.0, 0.0), (1.0, 0.0, 0.0)]   # normal = -Z
    assert _face_towards_camera(up_face) is True
    assert _face_towards_camera(down_face) is False


def test_circle_poly_points_all_at_radius():
    pts = _circle_poly_points((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), 0.5, n=12)
    assert len(pts) == 12
    for p in pts:
        assert math.hypot(p[0], p[1]) == pytest.approx(0.5)
        assert p[2] == pytest.approx(0.0)


def test_helix_points_span_standoff_to_standoff_plus_length():
    pts = _helix_points((0.0, 0.0, 1.0), turns=3, n_per_turn=8, length_m=1.2, radius_m=0.1, standoff=0.3)
    assert pts[0][2] == pytest.approx(0.3)          # starts at standoff
    assert pts[-1][2] == pytest.approx(0.3 + 1.2)    # ends at standoff + length
    for p in pts:
        assert math.hypot(p[0], p[1]) == pytest.approx(0.1)   # stays on the helix radius


def test_spiral_points_radius_grows_monotonically():
    pts = _spiral_points((0.0, 0.0, 1.0), wraps=2.0, n_per_wrap=8,
                         r_start_m=0.1, r_end_m=0.4, standoff=0.0)
    radii = [math.hypot(p[0], p[1]) for p in pts]
    assert radii[0] == pytest.approx(0.1)
    assert radii[-1] == pytest.approx(0.4)
    assert all(b >= a - 1e-9 for a, b in zip(radii, radii[1:]))   # monotonically non-decreasing


@pytest.mark.parametrize("axis", [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), (0.0, 0.0, -1.0)])
def test_perp_basis_is_orthonormal_to_axis(axis):
    u, v = _perp_basis(axis)
    ax = np.array(axis); u_ = np.array(u); v_ = np.array(v)
    assert np.dot(ax, u_) == pytest.approx(0.0, abs=1e-9)
    assert np.dot(ax, v_) == pytest.approx(0.0, abs=1e-9)
    assert np.dot(u_, v_) == pytest.approx(0.0, abs=1e-9)
    assert np.linalg.norm(u_) == pytest.approx(1.0)
    assert np.linalg.norm(v_) == pytest.approx(1.0)


def test_node_local_pt_matches_isometric():
    _proj.ISO_AZIMUTH, _proj.ISO_ELEVATION = -45.0, 30.0
    pt = _node_local_pt(0.3, -0.1, 0.2)
    sx, sy = isometric(0.3, -0.1, 0.2)
    assert (pt.x(), pt.y()) == pytest.approx((sx, sy))


def test_project_path_3d_closes_and_projects_every_vertex():
    offsets = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]
    path = _project_path_3d(offsets, closed=True)
    # 3 vertices + 1 implicit closing point back to the start
    assert path.elementCount() == 4
    first = path.elementAt(0)
    last = path.elementAt(3)
    assert (first.x, first.y) == pytest.approx((last.x, last.y))


def test_project_polyline_3d_keeps_strokes_disjoint():
    strokes = [[(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)], [(0.0, 1.0, 0.0), (0.0, 2.0, 0.0)]]
    path = _project_polyline_3d(strokes)
    # 2 strokes x (1 moveTo + 1 lineTo) = 4 elements, no implicit join between them
    assert path.elementCount() == 4


# ── headless smoke pass: every SupportType must draw without crashing ───────

class _FakeScene:
    """Minimal stand-in for StructCanvas: NodeItem only needs .model_state and
    a no-op removeItem() (called when _draw_support_symbol redraws)."""
    def __init__(self, model_state):
        self.model_state = model_state

    def removeItem(self, item):
        pass


def _make_node_item(support_type, mode_3d=True, z=4.0):
    ms = ModelState(nodes=[NodeData(id=0, x=1.0, y=2.0, z=z)])
    ms.analysis_mode = "3D" if mode_3d else "2D"
    ms.nodes[0].support_type = support_type
    return NodeItem(ms.nodes[0], _FakeScene(ms))


ALL_SUPPORTS = [SupportType.FIXED, SupportType.PIN, SupportType.ROLLER,
                SupportType.ROLLER_Y, SupportType.ROLLER_Z, SupportType.SPRING]


@pytest.mark.parametrize("support_type", ALL_SUPPORTS)
@pytest.mark.parametrize("az,el", [(-45.0, 30.0), (-15.0, 60.0), (-80.0, 10.0)])
def test_support_glyph_3d_draws_without_crashing(qapp, support_type, az, el):
    _proj.ISO_AZIMUTH, _proj.ISO_ELEVATION = az, el
    item = _make_node_item(support_type, mode_3d=True)
    assert len(item._support_items) > 0


@pytest.mark.parametrize("support_type", ALL_SUPPORTS)
def test_support_glyph_2d_draws_without_crashing(qapp, support_type):
    item = _make_node_item(support_type, mode_3d=False, z=0.0)
    assert len(item._support_items) > 0


def test_roller_z_2d_is_a_faded_disabled_badge_not_a_triangle(qapp):
    """ROLLER_Z has no 2D meaning; it must render a distinct disabled-looking
    badge rather than the old meaningless downward triangle (same shape PIN
    uses), so it doesn't look like an active support type in 2D."""
    item = _make_node_item(SupportType.ROLLER_Z, mode_3d=False, z=0.0)
    opacities = {round(it.opacity(), 2) for it in item._support_items}
    assert opacities and max(opacities) < 1.0   # faded, unlike every active glyph


def test_spring_with_no_constants_set_still_draws_placeholder(qapp):
    item = _make_node_item(SupportType.SPRING, mode_3d=True)
    assert len(item._support_items) > 0


def test_spring_multi_axis_draws_more_than_single_axis(qapp):
    ms = ModelState(nodes=[NodeData(id=0, x=0.0, y=0.0, z=3.0)])
    ms.analysis_mode = "3D"
    node = ms.nodes[0]
    node.support_type = SupportType.SPRING
    node.spring_kz = 1e6
    single = NodeItem(node, _FakeScene(ms))
    n_single = len(single._support_items)

    node.spring_kx = 1e6
    node.spring_krx = 1e5   # translational + rotational sharing the X axis
    multi = NodeItem(node, _FakeScene(ms))
    assert len(multi._support_items) > n_single
