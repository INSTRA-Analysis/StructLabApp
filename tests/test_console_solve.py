"""The console's solve() runs the app's own Solve, and sdk_examples/example_frame.py uses it.

The example builds a portal frame on the LIVE canvas model from the embedded
console, then calls refresh() + solve(). These tests open the real main window
headlessly, run the example's code in the console kernel, and check that the
app itself ends up holding a solved 2D frame (results cache + equilibrium).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest

EXAMPLE = os.path.join(os.path.dirname(__file__), "..", "sdk_examples", "example_frame.py")


@pytest.fixture()
def window(monkeypatch):
    from PyQt6.QtWidgets import QApplication, QMessageBox
    from ui_qt.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(MainWindow, "_show_welcome", lambda self: None)
    monkeypatch.setattr(MainWindow, "_check_autosave_recovery", lambda self: False)
    # a modal dialog would hang a headless run
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: pytest.fail("solve blocked"))
    win = MainWindow()
    yield win
    if getattr(win, "_console_dialog", None) is not None:
        win._console_dialog.close()
    win.close()


def _console_shell(win):
    win._open_console()
    return win._console_dialog._widget.kernel_manager.kernel.shell


def _seed_2d_template(win) -> None:
    """A leftover 2D model the example has to replace."""
    state = win._scene.model_state
    state.analysis_mode = "2D"
    a, b = state.add_node(0, 0), state.add_node(3, 0)
    state.add_member(a.id, b.id)


def test_console_exposes_solve(window):
    shell = _console_shell(window)
    assert callable(shell.user_ns["solve"])


def test_example_frame_builds_and_solves_in_the_app(window):
    _seed_2d_template(window)
    shell = _console_shell(window)
    with open(EXAMPLE, encoding="utf-8") as fh:
        result = shell.run_cell(fh.read())
    assert result.error_in_exec is None and result.error_before_exec is None

    state = window._scene.model_state
    assert state.is_2d
    assert len(state.nodes) == 4 and len(state.members) == 3   # template was replaced

    cache = window._solve_cache
    assert cache is not None
    assert cache["model"].dofs_per_node == 3
    reactions = np.asarray(cache["reactions"])
    assert reactions[0::3].sum() == pytest.approx(-20e3, abs=1.0)   # wind balanced
    assert reactions[1::3].sum() == pytest.approx(90e3, abs=1.0)    # 15 kN/m x 6 m


def test_example_frame_refuses_3d_project(window):
    shell = _console_shell(window)
    window._scene.model_state.analysis_mode = "3D"
    with open(EXAMPLE, encoding="utf-8") as fh:
        result = shell.run_cell(fh.read())
    assert isinstance(result.error_in_exec, RuntimeError)
    assert window._solve_cache is None
