"""Result colours (utilisation, axial force) stay on the members when the view zooms.

Every zoom rebuilds each member's pen for the new scale; it used to rebuild it from the
plain member colour, so fit, wheel zoom or a view preset silently removed the colours."""

import pytest
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def canvas(qapp):
    from ui_qt.canvas import StructCanvas, StructView
    from ui_qt.model_state import ModelState
    s = ModelState()
    a, b, c = s.add_node(0, 0, 0), s.add_node(5, 0, 0), s.add_node(5, 0, 4)
    s.add_member(a.id, b.id); s.add_member(b.id, c.id)
    sc = StructCanvas()
    sc.load_state(s)
    view = StructView(sc)
    view.resize(800, 600)
    yield sc, view
    view.deleteLater()


def _colours(sc):
    return [item.pen().color().name() for item in sc._member_items.values()]


def _zoom(view):
    view._fit_now()
    view.scale(1.3, 1.3)
    view._notify_zoom()


def test_utilisation_colour_survives_zoom(canvas):
    sc, view = canvas
    plain = _colours(sc)
    for item in sc._member_items.values():
        item.set_util_colour(0.5)
    coloured = _colours(sc)
    assert coloured != plain
    _zoom(view)
    assert _colours(sc) == coloured


def test_force_colour_survives_zoom_and_clearing_restores_plain(canvas):
    sc, view = canvas
    plain = _colours(sc)
    for item in sc._member_items.values():
        item.set_force_colour(-10.0, 10.0)
    coloured = _colours(sc)
    assert coloured != plain
    _zoom(view)
    assert _colours(sc) == coloured
    sc.clear_member_colours()
    _zoom(view)
    assert _colours(sc) == plain
