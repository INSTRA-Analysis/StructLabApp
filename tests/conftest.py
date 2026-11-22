"""Shared test fixtures."""

import pytest


@pytest.fixture(autouse=True)
def _restore_camera():
    """The canvas camera is module-level state (ui_qt.projection ISO_AZIMUTH / ISO_ELEVATION).
    Opening a plane frame turns it to the Front view, so restore it after every test: no
    test may leak its view into the next one."""
    import ui_qt.projection as proj
    az, el = proj.ISO_AZIMUTH, proj.ISO_ELEVATION
    yield
    proj.ISO_AZIMUTH, proj.ISO_ELEVATION = az, el


@pytest.fixture(autouse=True)
def _private_autosave(tmp_path, monkeypatch):
    """Keep tests away from the user's real autosave (~/.structlab/autosave.slab): closing a
    window, opening a file or clearing a model deletes it, autosave writes it."""
    import ui_qt.main_window as mw
    monkeypatch.setattr(mw, "_AUTOSAVE_PATH", tmp_path / "autosave.slab")


@pytest.fixture(autouse=True)
def _private_preferences(tmp_path, monkeypatch):
    """Keep tests away from the user's real interface preferences (registry on Windows)."""
    from PyQt6.QtCore import QSettings
    import ui_qt.main_window as mw
    path = str(tmp_path / "preferences.ini")
    monkeypatch.setattr(mw, "_preferences", lambda: QSettings(path, QSettings.Format.IniFormat))
