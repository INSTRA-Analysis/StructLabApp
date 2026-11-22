"""Results of a plane frame (results panel and PDF): the in-plane quantities only
(dx, dz, θy; Rx, Rz, My; member N, V, M); the locked uy, θx, θz are always zero."""

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


def _solved(analysis_type="plane_xz"):
    s = ModelState()
    s.analysis_type = analysis_type
    n = [s.add_node(0, 0, 0), s.add_node(0, 0, 4), s.add_node(6, 0, 4), s.add_node(6, 0, 0)]
    n[0].support_type = n[3].support_type = SupportType.FIXED
    for a, b in ((0, 1), (1, 2), (3, 2)):
        m = s.add_member(n[a].id, n[b].id)
        m.E, m.A, m.I, m.I_y, m.J = 210e9, 8e-3, 2e-4, 2e-4, 1e-5
    s.active_case.set_node_load(n[1].id, NodeLoad(fx=12e3, fz=-30e3))
    return s, solve_engine(*build_model(s, s.active_case), s)


def _headers(table):
    return [table.horizontalHeaderItem(c).text() for c in range(table.columnCount())]


@pytest.mark.parametrize("analysis_type, disp, react", [
    ("plane_xz", ["Node", "dx (mm)", "dz (mm)", "θy (mrad)"], ["Node", "Fx (kN)", "Fz (kN)", "My (kN·m)"]),
    ("space", ["Node", "dx (mm)", "dy (mm)", "dz (mm)", "θx (mrad)", "θy (mrad)", "θz (mrad)"],
     ["Node", "Fx (kN)", "Fy (kN)", "Fz (kN)", "Mx (kN·m)", "My (kN·m)", "Mz (kN·m)"]),
])
def test_results_panel_columns_follow_the_analysis(qapp, analysis_type, disp, react):
    from ui_qt.panels import ResultsPanel
    s, c = _solved(analysis_type)
    panel = ResultsPanel()
    panel.populate(c["displacements"], c["reactions"], c["member_results"], s, 6,
                   member_el_map=c["member_el_map"], sub_results=c["sub_results"])
    assert _headers(panel._disp_table) == disp and _headers(panel._react_table) == react


def test_plane_frame_values_are_the_in_plane_ones(qapp):
    from ui_qt.panels import ResultsPanel
    s, c = _solved()
    panel = ResultsPanel()
    panel.populate(c["displacements"], c["reactions"], c["member_results"], s, 6)
    knee = s.nodes[1].id
    row = panel._disp_row_to_node.index(knee)
    shown = [float(panel._disp_table.item(row, col).text()) for col in (1, 2, 3)]
    expected = [c["displacements"][knee * 6 + k] * 1e3 for k in (0, 2, 4)]
    assert shown == pytest.approx(expected, abs=1e-4)
    base = s.nodes[0].id
    row = panel._react_row_to_node.index(base)
    assert float(panel._react_table.item(row, 2).text()) == pytest.approx(
        c["reactions"][base * 6 + 2] / 1e3, abs=1e-3)


def test_envelope_uses_the_same_columns(qapp):
    from ui_qt.panels import ResultsPanel
    s, c = _solved()
    panel = ResultsPanel()
    panel.populate_envelope([c, c], s, 6)
    assert _headers(panel._disp_table) == ["Node", "dx (mm)", "dz (mm)", "θy (mrad)"]


def test_pdf_tables_show_the_in_plane_quantities(tmp_path):
    from tests.test_pdf_report_3d import _report_text
    s, c = _solved()
    text = _report_text(tmp_path, s)
    for present in ("Rz (kN)", "My (kN·m)", "dz (mm)", "θy (°)", "N_i (kN)", "M_j (kN·m)"):
        assert present in text, present
    for absent in ("Ry (kN)", "Mx (kN·m)", "Vz_i", "θx (", "dy (mm)"):    # no locked columns
        assert absent not in text, absent
