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
