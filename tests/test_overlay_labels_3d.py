"""Diagram labels on 3D models: the deformed shape's peak-δ label (it was computed for 2D
elements only, so plane frames and space frames showed none)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from ui_qt.model_builder import build_model
from ui_qt.model_state import ModelState, NodeLoad, SupportType
from ui_qt.solve_actions import solve_engine


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def _labels(analysis_type, load):
    from ui_qt.canvas_overlay import draw_labels
    s = ModelState()
    s.analysis_type = analysis_type
    a, b = s.add_node(0, 0, 0), s.add_node(4, 0, 0)
    a.support_type = SupportType.FIXED
    m = s.add_member(a.id, b.id)
    m.E, m.A, m.I, m.I_y, m.J = 210e9, 0.01, 1e-4, 1e-4, 1e-5
    s.active_case.set_node_load(b.id, load)
    model, emap = build_model(s, s.active_case)
    c = solve_engine(model, emap, s)
    items = draw_labels(model, c["sub_results"], {}, 1e-4, emap,
                        displacements=c["displacements"], def_scale=50.0)
    return {it.data(1): it.text() for it in items}


@pytest.mark.parametrize("analysis_type", ["plane_xz", "space"])
def test_deformed_shape_labels_its_peak_deflection(qapp, analysis_type):
    labels = _labels(analysis_type, NodeLoad(fz=-10e3))
    tip_mm = 10e3 * 4 ** 3 / (3 * 210e9 * 1e-4) * 1e3             # PL³/3EI = 10.16 mm
    assert labels["Deformed"] == f"{-tip_mm:.2f} mm"
    assert "40.00" in labels["BMD"]                                 # PL = 40 kN·m at the root
