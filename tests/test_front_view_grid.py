"""The 3D grid seen edge-on (the Front view of a plane frame): the XY ground grid fades out
instead of collapsing into a dense band, and the working-plane grid takes over, centred on
what is in view."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QFont

import ui_qt.projection as proj
from ui_qt.canvas import floor_visibility


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.mark.parametrize("el, f", [(30, 1.0), (12, 1.0), (9, 0.5), (6, 0.0), (2, 0.0), (-2, 0.0), (-30, 1.0)])
def test_floor_visibility(el, f):
    assert floor_visibility(el) == pytest.approx(f)


class _Recorder:
    """Stands in for QPainter: records the lines drawn, ignores everything else."""

    def __init__(self):
        self.lines = []

    def drawLine(self, line):
        self.lines.append((line.x1(), line.y1(), line.x2(), line.y2()))

    def font(self):
        return QFont()

    def __getattr__(self, name):
        return lambda *a, **k: None


def _grid_lines(az, el, plane_name="XZ"):
    from ui_qt.canvas import StructCanvas, StructView, WorkingPlane
    proj.ISO_AZIMUTH, proj.ISO_ELEVATION = az, el
    sc = StructCanvas()
    sc.set_working_plane(WorkingPlane[plane_name])
    view = StructView(sc)
    view.resize(900, 600)
    rec = _Recorder()
    view._draw_iso_grid(rec, QRectF(-2000, -2000, 4000, 4000))
    return rec.lines, view


def test_front_view_has_no_dense_band_of_lines(qapp):
    lines, view = _grid_lines(0.0, 2.0)
    horizontal = sorted({round(y1, 3) for x1, y1, x2, y2 in lines if abs(y2 - y1) < 1e-6})
    gaps = [b - a for a, b in zip(horizontal, horizontal[1:])]
    assert len(horizontal) > 5
    assert min(gaps) > 0.9 * 0.25 * 80 * 0.99                 # at least one grid step apart
    vertical = [l for l in lines if abs(l[0] - l[2]) < 1e-6]
    assert len(vertical) > 5                                  # the XZ grid's verticals


def test_iso_view_still_draws_the_ground_floor(qapp):
    lines, _ = _grid_lines(-45.0, 30.0, "XY")
    assert len(lines) > 20


def test_front_view_grid_is_centred_on_what_is_in_view(qapp):
    """Scrolled up to z ~ 20 m, the grid's vertical lines must reach that height."""
    from PyQt6.QtCore import QPointF
    proj.ISO_AZIMUTH, proj.ISO_ELEVATION = 0.0, 2.0
    from ui_qt.canvas import StructCanvas, StructView, WorkingPlane
    sc = StructCanvas()
    sc.set_working_plane(WorkingPlane.XZ)
    view = StructView(sc)
    view.resize(900, 600)
    view.centerOn(QPointF(*proj.isometric(0.0, 0.0, 20.0)))
    rec = _Recorder()
    view._draw_iso_grid(rec, QRectF(-4000, -4000, 8000, 8000))
    top = min(min(y1, y2) for _, y1, _, y2 in rec.lines)
    assert top < proj.isometric(0.0, 0.0, 20.0)[1]           # grid extends above z = 20 m
