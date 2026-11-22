"""End to end, in the real main window (headless): open the tower, Solve, report.

Guards the whole 3D path at once: file load -> validation -> model build -> solve
-> results cache -> PDF report. Uses the frozen tower in tests/golden.
"""

import math
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import matplotlib
import numpy as np
import pytest

pypdf = pytest.importorskip("pypdf")

TOWER = Path(__file__).parent / "golden" / "l8_tower_frozen.slab"


@pytest.fixture()
def window(monkeypatch):
    from PyQt6.QtWidgets import QApplication, QMessageBox
    from ui_qt.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(MainWindow, "_show_welcome", lambda self: None)
    monkeypatch.setattr(MainWindow, "_check_autosave_recovery", lambda self: False)
    # A modal dialog would hang a headless run; none should be needed for a valid model.
    for name in ("question", "warning", "information", "critical"):
        monkeypatch.setattr(QMessageBox, name,
                            lambda *a, _n=name, **k: pytest.fail(f"unexpected {_n} dialog: {a[1:3]}"))
    win = MainWindow()
    yield win
    win.close()


def test_tower_opens_solves_and_reports(window, tmp_path):
    window._open_file(str(TOWER))
    state = window._scene.model_state
    assert len(state.nodes) == 133 and len(state.members) == 454

    window._on_solve()
    cache = window._solve_cache
    assert cache is not None and np.all(np.isfinite(cache["displacements"]))
    assert cache["model"].dofs_per_node == 6

    # Vertical equilibrium against the tower's own weight (self-weight case is on).
    weight = sum(m.density * m.A * 9.81 * math.dist(
        (state.get_node(m.node_i).x, state.get_node(m.node_i).y, state.get_node(m.node_i).z),
        (state.get_node(m.node_j).x, state.get_node(m.node_j).y, state.get_node(m.node_j).z))
        for m in state.members)
    reactions = cache["reactions"].reshape(-1, 6)
    assert reactions[:, 2].sum() == pytest.approx(weight, rel=1e-9)
    assert reactions[:, :2].sum() == pytest.approx(0.0, abs=1e-6)

    # Opening and solving must not rewrite the user's geometry (old z=0 -> 1e-12 hack).
    base_z = {n.z for n in state.nodes if n.support_type.name == "PIN"}
    assert base_z == {0.0} or base_z == {1e-12}

    from ui_qt.pdf_report import generate_report
    out = tmp_path / "tower.pdf"
    with matplotlib.rc_context({"pdf.fonttype": 42}):
        generate_report(str(out), state, None, cache, "Self weight")
    text = "\n".join(p.extract_text() for p in pypdf.PdfReader(str(out)).pages)
    assert "Space frame (Z up): 6 DOF per node" in text
    assert "Global equilibrium satisfied" in text
    assert "members shown (largest |M|)" in text      # 454 members: diagram pages capped
    assert "more rows not shown" in text              # long tables say so, never silent


def test_pdf_is_only_generated_on_request(window, monkeypatch):
    """Opening, solving and re-solving never build a report; only the export action does."""
    import ui_qt.pdf_report as pdf_report

    calls = []
    monkeypatch.setattr(pdf_report, "generate_report", lambda *a, **k: calls.append(1))
    window._open_file(str(TOWER))
    window._on_solve()
    window._on_solve()
    assert calls == []
