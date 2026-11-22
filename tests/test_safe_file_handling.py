"""Unsaved work and saved files are never lost silently.

Open / Open Recent / Import CSV / the wizards used to replace a modified model without asking
(and Open deleted the autosave); a failed save used to truncate the existing file."""

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from ui_qt.io import load_model, save_model
from ui_qt.model_state import ModelState


def _state(n_nodes: int) -> ModelState:
    s = ModelState()
    for k in range(n_nodes):
        s.add_node(float(k), 0.0, 0.0)
    return s


def test_failed_save_keeps_the_previous_file(tmp_path, monkeypatch):
    path = tmp_path / "model.slab"
    save_model(_state(2), path)
    before = path.read_text(encoding="utf-8")

    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(json, "dumps", lambda *a, **k: "{ truncated")
    monkeypatch.setattr(os, "fsync", boom)
    with pytest.raises(OSError):
        save_model(_state(5), path)
    assert path.read_text(encoding="utf-8") == before            # untouched
    assert [p.name for p in tmp_path.iterdir()] == ["model.slab"]  # no temp file left


def test_save_round_trips(tmp_path):
    path = tmp_path / "m.slab"
    save_model(_state(3), path)
    assert len(load_model(path).nodes) == 3


@pytest.fixture
def win(qapp, monkeypatch):
    from ui_qt.main_window import MainWindow
    monkeypatch.setattr(MainWindow, "_show_welcome", lambda self: None)
    monkeypatch.setattr(MainWindow, "_check_autosave_recovery", lambda self: False)
    import ui_qt.recent_files as rf
    monkeypatch.setattr(rf, "push", lambda p: None)
    w = MainWindow()
    yield w
    w._is_dirty = False
    w.close()


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("answer, replaced", [("Cancel", False), ("Discard", True)])
def test_open_asks_before_replacing_unsaved_work(win, tmp_path, monkeypatch, answer, replaced):
    from PyQt6.QtWidgets import QMessageBox
    other = tmp_path / "other.slab"
    save_model(_state(4), other)
    win._scene.load_state(_state(2))
    win._is_dirty = True
    asked = []

    def question(*args, **kwargs):
        asked.append(args[1])
        return getattr(QMessageBox.StandardButton, answer)
    monkeypatch.setattr(QMessageBox, "question", question)
    win._open_file(str(other))
    assert asked == ["Unsaved changes"]
    assert len(win._scene.model_state.nodes) == (4 if replaced else 2)


def test_opening_a_model_shows_the_model_workspace(win, tmp_path):
    """A freshly opened model has no results: leave an empty Results workspace for Model."""
    other = tmp_path / "other.slab"
    save_model(_state(3), other)
    win._show_results_workspace()
    assert win._workspace == "ws_results"
    win._is_dirty = False
    win._open_file(str(other))
    assert win._workspace == "ws_model"


def test_open_does_not_ask_when_nothing_changed(win, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    other = tmp_path / "other.slab"
    save_model(_state(4), other)
    win._scene.load_state(_state(2))
    win._is_dirty = False
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: pytest.fail("asked"))
    win._open_file(str(other))
    assert len(win._scene.model_state.nodes) == 4
