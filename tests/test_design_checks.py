"""Tests for ui_qt/panels.py's element-type-aware Design-tab capacity checks.

The Design tab used to always report a bending (M_Ed/M_Rd) check, even for
truss bars (which carry no bending by construction). _compute_member_design_rows
now branches per element_type: BAR -> axial only; BEAM-family -> bending only,
or axial + bending + a linear N+M interaction row once a member carries real
combined axial force (e.g. a column). These are pure functions (no Qt), so
they're tested directly without a live ResultsPanel.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from ui_qt.model_state import (
    ModelState, NodeData, MemberData, ElementType, SupportType,
)
from ui_qt.panels import (
    _compute_member_design_rows,
    _design_axial_row,
    _design_bending_row,
    _DESIGN_N_THRESHOLD_N,
    ResultsPanel,
)

STEEL_FY = 355e6   # Pa, S355
A_SECTION = 0.005381        # m^2 (~IPE 300)
W_PL = 628e-6                # m^3


# ── BAR (truss member): axial only ──────────────────────────────────────────

def test_bar_gets_only_an_axial_row():
    rows = _compute_member_design_rows(
        ElementType.BAR, "steel", STEEL_FY, A_SECTION, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
        M_Ed=0.0, N_Ed=100e3,
    )
    assert [r["check"] for r in rows] == ["Axial N"]


def test_bar_axial_capacity_matches_ec3_yield_formula():
    N_Ed = 500e3   # 500 kN
    rows = _compute_member_design_rows(
        ElementType.BAR, "steel", STEEL_FY, A_SECTION, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
        M_Ed=0.0, N_Ed=N_Ed,
    )
    row = rows[0]
    N_Rd_expected = A_SECTION * STEEL_FY   # gamma_M0 = 1.0
    assert row["capacity"] == pytest.approx(N_Rd_expected)
    assert row["eta"] == pytest.approx(N_Ed / N_Rd_expected * 100)
    assert row["status"] == "PASS ✓"


def test_bar_axial_overstressed_fails():
    N_Rd = A_SECTION * STEEL_FY
    row = _design_axial_row("steel", STEEL_FY, A_SECTION, As=0.0, fyk_v=0.0, N_Ed=N_Rd * 1.5)
    assert row["eta"] > 100.0
    assert row["status"] == "FAIL ✗"


def test_bar_timber_axial_is_explicitly_not_implemented():
    """No silently-wrong number for timber axial — must say N/A."""
    row = _design_axial_row("timber", 24e6, 0.09, As=0.0, fyk_v=0.0, N_Ed=50e3)
    assert row["capacity"] is None
    assert row["eta"] is None
    assert "N/A" in row["status"]


# ── Concrete axial: compression (concrete + steel) vs tension (steel only) ──
# N_Ed sign follows the solver's convention: positive = compression.

_FCK = 30e6    # C30/37
_FYK = 500e6   # B500 reinforcement
_AC  = 0.3 * 0.4   # 300x400 column, m^2
_AS  = 2000e-6     # total longitudinal steel, m^2


def test_concrete_axial_compression_uses_concrete_plus_steel():
    N_Rd_expected = _AC * (_FCK / 1.5) + _AS * (_FYK / 1.15)
    row = _design_axial_row("concrete", _FCK, _AC, _AS, _FYK, N_Ed=N_Rd_expected * 0.5)
    assert row["check"] == "Axial N (compression)"
    assert row["capacity"] == pytest.approx(N_Rd_expected)
    assert row["status"] == "PASS ✓"


def test_concrete_axial_tension_uses_steel_only():
    N_Rd_expected = _AS * (_FYK / 1.15)   # no concrete contribution
    row = _design_axial_row("concrete", _FCK, _AC, _AS, _FYK, N_Ed=-N_Rd_expected * 0.5)
    assert row["check"] == "Axial N (tension)"
    assert row["capacity"] == pytest.approx(N_Rd_expected)
    assert row["status"] == "PASS ✓"


def test_concrete_axial_tension_capacity_is_far_below_compression_capacity():
    """The whole point of the sign split: the same column is much weaker in
    tension (steel only) than in compression (concrete + steel)."""
    comp = _design_axial_row("concrete", _FCK, _AC, _AS, _FYK, N_Ed=1.0)
    tens = _design_axial_row("concrete", _FCK, _AC, _AS, _FYK, N_Ed=-1.0)
    assert tens["capacity"] < comp["capacity"]


def test_concrete_axial_tension_can_fail_while_compression_would_pass():
    N_Rd_tension = _AS * (_FYK / 1.15)
    N_Ed = -N_Rd_tension * 1.2   # tension, 20% over the steel-only capacity
    row = _design_axial_row("concrete", _FCK, _AC, _AS, _FYK, N_Ed=N_Ed)
    assert row["status"] == "FAIL ✗"


def test_concrete_axial_tension_without_reinforcement_is_na():
    """Tension relies entirely on the reinforcement — with none, there's
    nothing to check (concrete alone still resists compression, so this
    only bites in tension)."""
    row = _design_axial_row("concrete", _FCK, _AC, As=0.0, fyk_v=_FYK, N_Ed=-100e3)
    assert row["capacity"] is None
    assert "N/A" in row["status"]


# ── BEAM-family, negligible axial: bending only (today's behaviour) ─────────

def test_beam_with_no_axial_gets_only_a_bending_row():
    rows = _compute_member_design_rows(
        ElementType.BEAM, "steel", STEEL_FY, A_SECTION, W_PL, 0.0, 0.0, 0.0, 0.0, 0.0,
        M_Ed=50e3, N_Ed=0.0,
    )
    assert [r["check"] for r in rows] == ["Bending M"]


@pytest.mark.parametrize("etype", [ElementType.PIN_LEFT, ElementType.PIN_RIGHT])
def test_pin_released_beam_ends_are_treated_as_beam_family(etype):
    rows = _compute_member_design_rows(
        etype, "steel", STEEL_FY, A_SECTION, W_PL, 0.0, 0.0, 0.0, 0.0, 0.0,
        M_Ed=10e3, N_Ed=0.0,
    )
    assert [r["check"] for r in rows] == ["Bending M"]


def test_beam_bending_capacity_prefers_plastic_over_elastic():
    row = _design_bending_row("steel", STEEL_FY, W_PL, W_el=400e-6, b=0, d=0, As=0, fyk_v=0, M_Ed=50e3)
    assert row["capacity"] == pytest.approx(STEEL_FY * W_PL)


def test_small_axial_noise_does_not_trigger_combined_check():
    rows = _compute_member_design_rows(
        ElementType.BEAM, "steel", STEEL_FY, A_SECTION, W_PL, 0.0, 0.0, 0.0, 0.0, 0.0,
        M_Ed=50e3, N_Ed=_DESIGN_N_THRESHOLD_N * 0.5,   # below threshold
    )
    assert [r["check"] for r in rows] == ["Bending M"]


# ── BEAM-family with real combined axial (a column) ─────────────────────────
# No combined N+M interaction row: a linear N/N_Rd + M/M_Rd sum is too crude
# to present as a real check (it ignores buckling entirely, EC3 §6.3), so the
# two checks are shown separately and the reader draws their own conclusion
# rather than trusting a combined PASS/FAIL that isn't code-compliant.

def test_column_gets_axial_and_bending_rows_only():
    rows = _compute_member_design_rows(
        ElementType.BEAM, "steel", STEEL_FY, A_SECTION, W_PL, 0.0, 0.0, 0.0, 0.0, 0.0,
        M_Ed=20e3, N_Ed=200e3,   # well above the noise threshold
    )
    assert [r["check"] for r in rows] == ["Axial N", "Bending M"]


# ── Design tab grouping: a member's rows must visually read as one group ────

@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def test_populate_preserves_axial_sign_through_the_full_solve_path(qapp):
    """Regression guard for the exact bug: ResultsPanel.populate() used to
    abs() the axial force before it reached the Design tab, which would have
    silently collapsed every concrete member onto the compression formula
    even when actually in tension. Drives the real solve-path entry point
    (populate), not just _populate_design_table directly."""
    import numpy as np
    from solver.postprocessor import ElementResult

    ms = ModelState(
        nodes=[NodeData(id=0, x=0.0, y=0.0), NodeData(id=1, x=4.0, y=0.0)],
        members=[MemberData(id=0, node_i=0, node_j=1, element_type=ElementType.BEAM,
                            E=32e9, A=_AC, fy=_FCK, density=2500.0,
                            b_sec=0.3, h_sec=0.4, d_eff=0.35,
                            As_tension=_AS, fyk=_FYK)],
    )
    ms.nodes[0].support_type = SupportType.PIN
    ms.nodes[1].support_type = SupportType.ROLLER

    N_tension = -_AS * (_FYK / 1.15) * 1.2   # 20% over the steel-only tension capacity
    res = ElementResult(element_id=0, end_forces=np.array(
        [N_tension, 0.0, 5e3, N_tension, 0.0, -5e3]))

    panel = ResultsPanel()
    panel.populate(
        displacements=np.zeros(len(ms.nodes) * 3),
        reactions=np.zeros(len(ms.nodes) * 3),
        member_results=[res],
        model_state=ms,
        dpn=3,
    )
    tbl = panel._design_table
    checks = [tbl.item(r, 1).text() for r in range(tbl.rowCount())]
    statuses = [tbl.item(r, 5).text() for r in range(tbl.rowCount())]
    assert "Axial N (tension)" in checks
    assert statuses[checks.index("Axial N (tension)")] == "FAIL ✗"


def test_design_table_spans_member_cell_across_its_rows(qapp):
    ms = ModelState(
        nodes=[NodeData(id=0, x=0.0, y=0.0), NodeData(id=1, x=4.0, y=0.0),
               NodeData(id=2, x=4.0, y=3.0)],
        members=[
            MemberData(id=0, node_i=0, node_j=1, element_type=ElementType.BAR,
                      E=210e9, A=A_SECTION, fy=STEEL_FY),
            MemberData(id=1, node_i=1, node_j=2, element_type=ElementType.BEAM,
                      E=210e9, A=A_SECTION, W_pl=W_PL, fy=STEEL_FY),
        ],
    )
    panel = ResultsPanel()
    # member 0: BAR -> 1 row.  member 1: BEAM with real combined N+M -> 2 rows.
    panel._populate_design_table([(0, 0.0, 100e3), (1, 20e3, 200e3)], ms)

    tbl = panel._design_table
    assert tbl.rowCount() == 1 + 2
    assert tbl.rowSpan(0, 0) == 1        # member 0's single row: no span needed
    # member 1's group: Qt reports the full span for every row inside it
    assert tbl.rowSpan(1, 0) == 2
    assert tbl.rowSpan(2, 0) == 2


def test_design_table_regroups_cleanly_across_repeated_populate_calls(qapp):
    """A stale span from a previous solve must not linger after re-solving
    with a different row layout (clearSpans() on each populate)."""
    ms = ModelState(
        nodes=[NodeData(id=0, x=0.0, y=0.0), NodeData(id=1, x=4.0, y=0.0)],
        members=[MemberData(id=0, node_i=0, node_j=1, element_type=ElementType.BEAM,
                            E=210e9, A=A_SECTION, W_pl=W_PL, fy=STEEL_FY)],
    )
    panel = ResultsPanel()
    panel._populate_design_table([(0, 20e3, 200e3)], ms)   # combined -> 2 rows
    assert panel._design_table.rowSpan(0, 0) == 2

    panel._populate_design_table([(0, 20e3, 0.0)], ms)     # re-solve: bending only -> 1 row
    assert panel._design_table.rowCount() == 1
    assert panel._design_table.rowSpan(0, 0) == 1


# ── estimated-reinforcement flag in the Design tab ───────────────────────────

def test_estimated_reinforcement_is_flagged_in_the_status_text(qapp):
    ms = ModelState(
        nodes=[NodeData(id=0, x=0.0, y=0.0), NodeData(id=1, x=4.0, y=0.0)],
        members=[MemberData(id=0, node_i=0, node_j=1, element_type=ElementType.BEAM,
                            E=32e9, A=_AC, fy=_FCK, density=2500.0,
                            b_sec=0.3, h_sec=0.4, d_eff=0.35,
                            As_tension=_AS, fyk=_FYK,
                            reinforcement_estimated=True)],
    )
    panel = ResultsPanel()
    panel._populate_design_table([(0, 50e3, 0.0)], ms)
    status = panel._design_table.item(0, 5).text()
    assert status.startswith(("PASS", "FAIL"))
    assert "min. reinf." in status


def test_reviewed_reinforcement_is_not_flagged(qapp):
    """Same member, but reinforcement_estimated=False (as if the user had
    already reviewed/applied it via the properties panel) — no flag."""
    ms = ModelState(
        nodes=[NodeData(id=0, x=0.0, y=0.0), NodeData(id=1, x=4.0, y=0.0)],
        members=[MemberData(id=0, node_i=0, node_j=1, element_type=ElementType.BEAM,
                            E=32e9, A=_AC, fy=_FCK, density=2500.0,
                            b_sec=0.3, h_sec=0.4, d_eff=0.35,
                            As_tension=_AS, fyk=_FYK,
                            reinforcement_estimated=False)],
    )
    panel = ResultsPanel()
    panel._populate_design_table([(0, 50e3, 0.0)], ms)
    status = panel._design_table.item(0, 5).text()
    assert status in ("PASS ✓", "FAIL ✗")
    assert "min. reinf." not in status


def test_na_rows_are_not_flagged_even_when_estimated(qapp):
    """No real verdict (e.g. As still 0) -> nothing to flag."""
    ms = ModelState(
        nodes=[NodeData(id=0, x=0.0, y=0.0), NodeData(id=1, x=4.0, y=0.0)],
        members=[MemberData(id=0, node_i=0, node_j=1, element_type=ElementType.BEAM,
                            E=32e9, A=_AC, fy=_FCK, density=2500.0,
                            b_sec=0.3, h_sec=0.4, d_eff=0.35,
                            As_tension=0.0, fyk=_FYK,
                            reinforcement_estimated=True)],
    )
    panel = ResultsPanel()
    panel._populate_design_table([(0, 50e3, 0.0)], ms)
    status = panel._design_table.item(0, 5).text()
    assert status == "Set b/d/As"   # no real verdict yet
    assert "min. reinf." not in status
