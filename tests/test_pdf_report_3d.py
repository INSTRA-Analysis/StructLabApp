"""PDF report on a 3D model: 6-DOF strides, Z columns, true equilibrium verdict."""

import matplotlib
import pytest

from ui_qt.model_builder import build_model
from ui_qt.model_state import ModelState, NodeLoad, SupportType
from ui_qt.pdf_report import generate_report
from ui_qt.solve_actions import solve_engine

pypdf = pytest.importorskip("pypdf")


def _frame_3d() -> ModelState:
    """Two columns + a beam in the XZ plane, wind in Y, gravity on the beam."""
    s = ModelState()
    base_a, base_b = s.add_node(0, 0, 0), s.add_node(6, 0, 0)
    top_a, top_b = s.add_node(0, 0, 4), s.add_node(6, 0, 4)
    base_a.support_type = base_b.support_type = SupportType.FIXED
    for a, b in ((base_a, top_a), (base_b, top_b), (top_a, top_b)):
        m = s.add_member(a.id, b.id)
        m.density, m.A, m.I, m.I_y, m.J = 7850.0, 0.01, 4e-5, 2e-5, 1e-6
    s.load_cases[0].include_self_weight = True
    s.load_cases[0].set_node_load(top_a.id, NodeLoad(fy=8000.0, fz=-20000.0))
    return s


def _report_text(tmp_path, state: ModelState) -> str:
    model, member_map = build_model(state, state.active_case)
    cache = solve_engine(model, member_map, state)
    out = tmp_path / "report.pdf"
    with matplotlib.rc_context({"pdf.fonttype": 42}):
        generate_report(str(out), state, None, cache, "LC0")
    return "\n".join(page.extract_text() for page in pypdf.PdfReader(str(out)).pages)


def test_3d_report_has_z_columns_and_true_equilibrium(tmp_path):
    text = _report_text(tmp_path, _frame_3d())
    assert "3D Structural Analysis" in text      # cover page
    assert "Z (m)" in text                       # node table
    assert "Fz (kN)" in text and "Mx (kN" in text  # node-load table
    assert "Rz (kN)" in text and "ΣRz" in text     # reactions page
    assert "Global equilibrium satisfied" in text
    assert "Equilibrium residual exceeds tolerance" not in text
    assert "dz (mm)" in text                     # displacement table
    assert "Vz_i" in text and "Mz_j" in text     # full 3D member end forces


def test_2d_report_is_unchanged_in_shape(tmp_path):
    """2D keeps its 3-DOF columns and still reports equilibrium."""
    s = ModelState()
    s.analysis_mode = "2D"
    a, b = s.add_node(0, 0), s.add_node(6, 0)
    a.support_type, b.support_type = SupportType.PIN, SupportType.ROLLER
    m = s.add_member(a.id, b.id)
    m.A, m.I = 0.01, 4e-5
    s.load_cases[0].set_node_load(a.id, NodeLoad(fy=-1000.0))
    text = _report_text(tmp_path, s)
    assert "2D Structural Analysis" in text
    assert "Rz (kN)" not in text and "Z (m)" not in text
    assert "Ry (kN)" in text and "M (kN·m)" in text
    assert "Global equilibrium satisfied" in text


def _long_beam(n_members: int) -> ModelState:
    s = ModelState()
    nodes = [s.add_node(2.0 * k, 0) for k in range(n_members + 1)]
    nodes[0].support_type, nodes[-1].support_type = SupportType.PIN, SupportType.ROLLER
    for a, b in zip(nodes, nodes[1:]):
        m = s.add_member(a.id, b.id)
        m.A, m.I = 0.01, 4e-5
    s.load_cases[0].set_node_load(nodes[n_members // 2].id, NodeLoad(fy=-5000.0))
    return s


def test_long_tables_say_how_many_rows_were_cut(tmp_path):
    """A table that cannot fit on the page must say so, never drop rows silently."""
    text = _report_text(tmp_path, _long_beam(45))
    assert "more rows not shown" in text


def test_short_tables_have_no_truncation_notice(tmp_path):
    assert "not shown" not in _report_text(tmp_path, _long_beam(5))


def test_member_diagram_pages_are_capped_and_labelled(tmp_path):
    from ui_qt.pdf_report import MAX_DIAGRAM_PAGES
    text = _report_text(tmp_path, _long_beam(MAX_DIAGRAM_PAGES + 6))
    assert f"{MAX_DIAGRAM_PAGES} of {MAX_DIAGRAM_PAGES + 6} members shown" in text
