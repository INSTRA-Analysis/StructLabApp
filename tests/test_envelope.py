"""Tests for ui_qt/envelope.py — max/min envelope across load combinations.

Covers the pure-numpy point-wise sampling (`_sample_member`) without Qt, and
the max/min-tracking table logic (`EnvelopeDialog._node_tab` / `_member_tab`)
under a headless (offscreen) QApplication. Previously zero test coverage,
despite deciding the governing combination shown to the user per node/member.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest

from ui_qt.model_state import ModelState, NodeData, MemberData, LoadCombination
from ui_qt.envelope import _sample_member, _draw_envelope_on_ax, EnvelopeDialog
from solver.postprocessor import ElementResult


def _result(eid, N_i, V_i, M_i, N_j, V_j, M_j) -> ElementResult:
    return ElementResult(element_id=eid,
                          end_forces=np.array([N_i, V_i, M_i, N_j, V_j, M_j], dtype=float))


# ── _sample_member ───────────────────────────────────────────────────────────

def test_sample_member_single_subelement_endpoints_match():
    sub = [_result(0, N_i=0, V_i=10.0, M_i=100.0, N_j=0, V_j=-10.0, M_j=200.0)]
    x, M, V = _sample_member(sub, el_ids=[0], n_per_sub=4)
    assert x[0] == pytest.approx(0.0)
    assert x[-1] == pytest.approx(1.0)
    assert M[0] == pytest.approx(100.0)
    assert M[-1] == pytest.approx(200.0)
    # V(x) = (1-t)*V_i - t*V_j  →  at x=0: V_i;  at x=1: -V_j
    assert V[0] == pytest.approx(10.0)
    assert V[-1] == pytest.approx(10.0)


def test_sample_member_midpoint_is_linear_average():
    sub = [_result(0, 0, 0.0, 100.0, 0, 0.0, 300.0)]
    x, M, V = _sample_member(sub, el_ids=[0], n_per_sub=2)
    mid_idx = len(x) // 2
    assert x[mid_idx] == pytest.approx(0.5)
    assert M[mid_idx] == pytest.approx(200.0)


def test_sample_member_two_subelements_are_continuous_at_boundary():
    sub = [
        _result(11, 0, 0.0, 50.0,  0, 0.0, 150.0),
        _result(12, 0, 0.0, 150.0, 0, 0.0, -20.0),
    ]
    x, M, V = _sample_member(sub, el_ids=[11, 12], n_per_sub=4)
    n_per_sub = 4
    # boundary between sub-elements sits at x_norm == 0.5 (index n_per_sub)
    boundary_idx = n_per_sub
    assert x[boundary_idx] == pytest.approx(0.5)
    assert M[boundary_idx] == pytest.approx(150.0)   # sub0.M_j == sub1.M_i
    assert M[0] == pytest.approx(50.0)
    assert M[-1] == pytest.approx(-20.0)


# ── _draw_envelope_on_ax (pure matplotlib, no Qt) ────────────────────────────

def _single_member_state() -> ModelState:
    return ModelState(
        nodes=[NodeData(id=0, x=0.0, y=0.0), NodeData(id=1, x=4.0, y=0.0)],
        members=[MemberData(id=0, node_i=0, node_j=1)],
        load_cases=[],
    )


def test_draw_envelope_all_zero_shows_placeholder_text():
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib.figure import Figure

    state = _single_member_state()
    run = {
        'combo': LoadCombination(id=0, name="C1"),
        'sub_results': [_result(0, 0, 0, 0, 0, 0, 0)],
        'member_el_map': [[0]],
    }
    fig = Figure()
    ax = fig.add_subplot(111)
    _draw_envelope_on_ax(ax, [run], state, kind='M')
    texts = [t.get_text() for t in ax.texts]
    assert any("All results" in t for t in texts)


def test_draw_envelope_nonzero_draws_fill_patches_no_placeholder():
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib.figure import Figure

    state = _single_member_state()
    run = {
        'combo': LoadCombination(id=0, name="C1"),
        'sub_results': [_result(0, 0, 0, 50_000.0, 0, 0, -20_000.0)],
        'member_el_map': [[0]],
    }
    fig = Figure()
    ax = fig.add_subplot(111)
    _draw_envelope_on_ax(ax, [run], state, kind='M')
    texts = [t.get_text() for t in ax.texts]
    assert not any("All results" in t for t in texts)
    assert len(ax.patches) >= 2   # max-fill + min-fill polygons


# ── EnvelopeDialog table max/min tracking (headless Qt) ─────────────────────

@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def _cell_text(tbl, row, col) -> str:
    return tbl.item(row, col).text()


def test_node_tab_tracks_max_min_displacement_and_combo(qapp):
    state = ModelState(
        nodes=[NodeData(id=0, x=0.0, y=0.0), NodeData(id=1, x=4.0, y=0.0)],
        members=[], load_cases=[],
    )
    # displacements indexed [node.id*3 + dof]; dof1 = dy, in metres.
    disp_a = np.zeros(6); disp_a[0 * 3 + 1] = -0.010; disp_a[1 * 3 + 1] = 0.002
    disp_b = np.zeros(6); disp_b[0 * 3 + 1] = 0.004;  disp_b[1 * 3 + 1] = -0.030
    runs = [
        {'combo': LoadCombination(id=0, name="COMBO-A"), 'displacements': disp_a},
        {'combo': LoadCombination(id=1, name="COMBO-B"), 'displacements': disp_b},
    ]

    tbl = EnvelopeDialog._node_tab(None, runs, state)

    # Node 0: max dy = +4mm (COMBO-B), min dy = -10mm (COMBO-A)
    assert _cell_text(tbl, 0, 1) == "+4.000"
    assert _cell_text(tbl, 0, 2) == "COMBO-B"
    assert _cell_text(tbl, 0, 3) == "-10.000"
    assert _cell_text(tbl, 0, 4) == "COMBO-A"

    # Node 1: max dy = +2mm (COMBO-A), min dy = -30mm (COMBO-B)
    assert _cell_text(tbl, 1, 1) == "+2.000"
    assert _cell_text(tbl, 1, 2) == "COMBO-A"
    assert _cell_text(tbl, 1, 3) == "-30.000"
    assert _cell_text(tbl, 1, 4) == "COMBO-B"


def test_member_tab_tracks_max_min_moment_shear_and_axial(qapp):
    state = ModelState(
        nodes=[NodeData(id=0, x=0.0, y=0.0), NodeData(id=1, x=4.0, y=0.0)],
        members=[MemberData(id=0, node_i=0, node_j=1)],
        load_cases=[],
    )
    # Combo A: sagging (+M), moderate shear, member in compression (N positive).
    res_a = _result(0, N_i=8_000.0, V_i=5_000.0, M_i=30_000.0,
                        N_j=8_000.0, V_j=-5_000.0, M_j=-10_000.0)
    # Combo B: hogging governs (more negative M), larger |V|, member in tension.
    res_b = _result(0, N_i=-12_000.0, V_i=9_000.0, M_i=-40_000.0,
                        N_j=-12_000.0, V_j=-9_000.0, M_j=15_000.0)
    runs = [
        {'combo': LoadCombination(id=0, name="A"), 'member_results': [res_a]},
        {'combo': LoadCombination(id=1, name="B"), 'member_results': [res_b]},
    ]

    tbl = EnvelopeDialog._member_tab(None, runs, state)

    assert _cell_text(tbl, 0, 1) == "+30.000"   # Max M+  (from combo A, M_i)
    assert _cell_text(tbl, 0, 2) == "A"
    assert _cell_text(tbl, 0, 3) == "-40.000"   # Max M-  (from combo B, M_i)
    assert _cell_text(tbl, 0, 4) == "B"
    assert _cell_text(tbl, 0, 5) == "9.000"     # Max |V| (from combo B)
    assert _cell_text(tbl, 0, 6) == "B"
    assert _cell_text(tbl, 0, 7) == "8.000"     # Max N compression (N > 0), combo A
    assert _cell_text(tbl, 0, 8) == "A"
    assert _cell_text(tbl, 0, 9) == "12.000"    # Max N tension (N < 0), combo B
    assert _cell_text(tbl, 0, 10) == "B"
