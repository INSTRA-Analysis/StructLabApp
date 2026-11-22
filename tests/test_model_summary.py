"""With nothing selected, the Properties panel shows the model at a glance instead of a
single line."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from ui_qt.model_state import ElementType, ModelState, SupportType
from ui_qt.panels import model_summary_html


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _portal() -> ModelState:
    s = ModelState()
    s.analysis_type = "plane_xz"
    n = [s.add_node(0, 0, 0), s.add_node(0, 0, 4), s.add_node(6, 0, 4), s.add_node(6, 0, 0)]
    n[0].support_type = n[3].support_type = SupportType.FIXED
    for i in range(3):
        m = s.add_member(n[i].id, n[i + 1].id)
        m.A, m.density = 0.01, 7850.0
    s.add_member(n[0].id, n[2].id).element_type = ElementType.BAR
    return s


def test_summary_lists_the_model():
    html = model_summary_html(_portal())
    for text in ("Plane frame (XZ)", "4  (2 supported)", "4  (1 bars)", "Total length",
                 "Mass", "Load cases", "Click a node or member"):
        assert text in html, text
    assert "Total length</td><td><b>21.21 m" in html                    # 4 + 6 + 4 + √52


def test_no_model_shows_just_the_hint():
    assert model_summary_html(None) == model_summary_html(ModelState()) == \
        "Click a node or member to inspect it."


def test_panel_shows_the_summary_and_keeps_it_current(qapp):
    from ui_qt.panels import PropertiesPanel
    panel = PropertiesPanel()
    s = _portal()
    panel.set_model_state(s)
    panel.show_empty()
    assert "4  (2 supported)" in panel._placeholder.text()
    s.add_node(9, 0, 0)
    panel.set_model_state(s)                                  # what a model change calls
    assert "5  (2 supported)" in panel._placeholder.text()
