"""Member-load arrows point the way the load acts: the member's local −y as drawn.

They used to point screen-down for every member ('w' on a column was drawn along the column,
where it is invisible) and, for point forces, along the on-screen normal, which flipped with
the direction the member was drawn in."""

import pytest

import ui_qt.projection as proj
from ui_qt.canvas_items import member_load_direction
from ui_qt.model_state import MemberData, NodeData


@pytest.fixture
def front_view():
    proj.ISO_AZIMUTH, proj.ISO_ELEVATION = 0.0, 0.0      # restored by conftest


def _dir(a, b):
    ni, nj = NodeData(id=0, x=a[0], y=a[1], z=a[2]), NodeData(id=1, x=b[0], y=b[1], z=b[2])
    return member_load_direction(MemberData(id=0, node_i=0, node_j=1), ni, nj)


def test_a_beam_is_loaded_downward_whichever_way_it_was_drawn(front_view):
    for a, b in (((0, 0, 4), (6, 0, 4)), ((6, 0, 4), (0, 0, 4))):
        vx, vy = _dir(a, b)
        assert vx == pytest.approx(0.0, abs=1e-9) and vy == pytest.approx(1.0)   # screen y is down


def test_a_column_is_loaded_sideways_not_along_itself(front_view):
    vx, vy = _dir((0, 0, 0), (0, 0, 4))
    assert vy == pytest.approx(0.0, abs=1e-9) and abs(vx) == pytest.approx(1.0)
    right_x, _ = proj.isometric(1.0, 0.0, 0.0)
    origin_x, _ = proj.isometric(0.0, 0.0, 0.0)
    assert vx * (right_x - origin_x) < 0                 # local −y of a column is −X
