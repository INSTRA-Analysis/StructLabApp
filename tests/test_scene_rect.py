"""The canvas scene rectangle must grow with the model.

Pan and orbit drive the view's scroll bars, which Qt clamps to the scene
rectangle. It used to be a fixed +/-50 m square, so a model reaching past that
(e.g. examples/space_frame_lecture37_3d.csv, 78 m long) could not be scrolled
fully into view, and orbiting swung its far corner out of reach.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest

from ui_qt.csv_import import parse_structlab_csv
from ui_qt.model_state import ModelState

BIG = Path(__file__).resolve().parent.parent / "examples" / "space_frame_lecture37_3d.csv"
DEFAULT_HALF = 4000.0


def _long_model() -> ModelState:
    """A 13-node chain ~140 m long — well past the old +/-50 m rectangle, but cheap."""
    state = ModelState()
    ids = [state.add_node(10.0 * i, 4.0 * i, 1.5 * i).id for i in range(13)]
    for a, b in zip(ids, ids[1:]):
        state.add_member(a, b)
    return state


@pytest.fixture()
def canvas(monkeypatch):
    from PyQt6.QtWidgets import QApplication
    import ui_qt.projection as proj
    from ui_qt.canvas import StructCanvas, StructView

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(proj, "ISO_AZIMUTH", proj.ISO_AZIMUTH)      # restored after the test
    monkeypatch.setattr(proj, "ISO_ELEVATION", proj.ISO_ELEVATION)
    scene = StructCanvas()
    view = StructView(scene)
    view.resize(1000, 700)
    view.show()
    app.processEvents()
    yield app, scene, view
    view.close()


def test_small_model_keeps_default_rect(canvas):
    _, scene, _ = canvas
    state = ModelState()
    a, b = state.add_node(0, 0, 0), state.add_node(6, 0, 0)
    state.add_member(a.id, b.id)
    scene.load_state(state)
    assert scene.sceneRect().right() == DEFAULT_HALF


def test_lecture37_example_fits_in_scene_rect(canvas):
    _, scene, _ = canvas
    state, _w = parse_structlab_csv(BIG)
    scene.load_state(state)
    assert scene.sceneRect().contains(scene.itemsBoundingRect())
    assert scene.sceneRect().right() > DEFAULT_HALF


def test_big_model_grows_rect_and_clear_resets_it(canvas):
    _, scene, _ = canvas
    scene.load_state(_long_model())
    assert scene.sceneRect().contains(scene.itemsBoundingRect())
    assert scene.sceneRect().right() > DEFAULT_HALF
    scene.clear_model()
    assert scene.sceneRect().right() == DEFAULT_HALF


@pytest.mark.parametrize("azimuth,elevation", [(-45, 30), (90, 60), (200, 85)])
def test_every_edge_reachable_at_any_orbit_angle(canvas, azimuth, elevation):
    import ui_qt.projection as proj
    app, scene, view = canvas
    scene.load_state(_long_model())
    proj.ISO_AZIMUTH, proj.ISO_ELEVATION = azimuth, elevation
    scene.reproject()
    view.resetTransform()
    view.scale(0.4, 0.4)             # zoomed in, so scrolling is needed to see the ends
    app.processEvents()
    items = scene.itemsBoundingRect()
    assert scene.sceneRect().contains(items)

    def visible():
        return view.mapToScene(view.viewport().rect()).boundingRect()

    hbar, vbar = view.horizontalScrollBar(), view.verticalScrollBar()
    hbar.setValue(hbar.maximum()); app.processEvents()
    assert visible().right() >= items.right()
    hbar.setValue(hbar.minimum()); app.processEvents()
    assert visible().left() <= items.left()
    vbar.setValue(vbar.maximum()); app.processEvents()
    assert visible().bottom() >= items.bottom()
    vbar.setValue(vbar.minimum()); app.processEvents()
    assert visible().top() <= items.top()
