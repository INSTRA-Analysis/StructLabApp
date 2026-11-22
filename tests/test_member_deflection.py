"""Deflection along members: a beam's mid-span (no node there) reaches the summaries and the
PDF serviceability check, which used to look at free nodes only."""

import matplotlib
import pytest

from ui_qt.model_builder import build_model
from ui_qt.model_state import DistLoad, MemberLoad, ModelState, NodeLoad, SupportType
from ui_qt.solve_actions import largest_vertical_deflection, solve_engine

E, I, SPAN, W = 210e9, 2e-4, 6.0, 10e3


def _beam(supports=(SupportType.PIN, SupportType.ROLLER), load=True) -> ModelState:
    s = ModelState()
    s.analysis_type = "plane_xz"
    a, b = s.add_node(0, 0, 0), s.add_node(SPAN, 0, 0)
    a.support_type, b.support_type = supports
    m = s.add_member(a.id, b.id)
    m.E, m.A, m.I, m.I_y, m.J = E, 8e-3, I, I, 1e-5
    if load:
        s.active_case.member_loads[m.id] = MemberLoad(dist_loads=[DistLoad("w", W, W)])
    return s


def _solve(s):
    return solve_engine(*build_model(s, s.active_case), s)


def test_simply_supported_midspan_deflection_relative_to_the_chord():
    r = _solve(_beam())["member_results"][0]
    exact = 5 * W * SPAN ** 4 / (384 * E * I)
    assert r.deflection.span == pytest.approx(exact, rel=1e-6)
    assert r.deflection.span_at == pytest.approx(0.5)
    assert r.deflection.vertical == pytest.approx(-exact, rel=1e-6)          # downward


def test_cantilever_tip_is_the_largest_vertical_displacement():
    s = _beam((SupportType.FIXED, SupportType.FREE), load=False)
    s.active_case.set_node_load(1, NodeLoad(fz=-5e3))
    cache = _solve(s)
    value, member, at = largest_vertical_deflection(cache)
    assert value == pytest.approx(5e3 * SPAN ** 3 / (3 * E * I), rel=1e-6) and at == 1.0


def test_pdf_checks_a_simply_supported_beam_at_midspan(tmp_path):
    pypdf = pytest.importorskip("pypdf")
    from ui_qt.pdf_report import generate_report
    s = _beam()
    out = tmp_path / "r.pdf"
    with matplotlib.rc_context({"pdf.fonttype": 42}):
        generate_report(str(out), s, None, _solve(s), "LC0")
    text = "\n".join(p.extract_text() for p in pypdf.PdfReader(str(out)).pages)
    assert "No free nodes" not in text or "every node is supported" in text
    delta = 5 * W * SPAN ** 4 / (384 * E * I)
    assert f"{delta * 1e3:.2f} mm" in text and "member 0 at 0.50 L" in text
