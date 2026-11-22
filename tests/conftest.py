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
