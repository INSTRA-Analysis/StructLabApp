"""Navigation gizmo: each axis ball snaps to the view along that axis; home returns home."""

from PyQt6.QtCore import QPointF

import ui_qt.projection as proj
from ui_qt.nav_gizmo import NavGizmo


def _click(gizmo: NavGizmo, key: str) -> tuple[float, float] | None:
    bx, by, _ = gizmo._balls(0.0, 0.0, 1.0)[key]
    return gizmo.hit_test(QPointF(bx, by), 0.0, 0.0, 1.0, proj.ISO_AZIMUTH)


def test_axis_balls_snap_to_the_matching_views(monkeypatch):
    monkeypatch.setattr(proj, "ISO_AZIMUTH", -45.0)
    monkeypatch.setattr(proj, "ISO_ELEVATION", 30.0)
    g = NavGizmo()
    assert _click(g, "+X") == (90.0, 0.0)      # Right
    assert _click(g, "-Y") == (0.0, 0.0)       # Front
    assert _click(g, "+Z") == (-45.0, 90.0)    # Top keeps the azimuth
    # -X, +Y and -Z sit behind at this view; they are still clickable where not covered
    assert _click(g, "-X") == (-90.0, 0.0)


def test_home_button_and_empty_disc(monkeypatch):
    monkeypatch.setattr(proj, "ISO_AZIMUTH", 30.0)
    monkeypatch.setattr(proj, "ISO_ELEVATION", 10.0)
    g = NavGizmo()
    g.home_az, g.home_el = -45.0, 30.0
    hx, hy = g._home_center(0.0, 0.0, 1.0)
    assert g.hit_test(QPointF(hx, hy), 0.0, 0.0, 1.0, 30.0) == (-45.0, 30.0)
    # The disc itself is not a view target, but it counts as "over the gizmo" (menu)
    edge = QPointF(0.0, NavGizmo.HALF - 2.0)
    assert g.hit_test(edge, 0.0, 0.0, 1.0, 30.0) is None
    assert g.contains(edge, 0.0, 0.0, 1.0)
    assert not g.contains(QPointF(NavGizmo.HALF * 2, 0.0), 0.0, 0.0, 1.0)
