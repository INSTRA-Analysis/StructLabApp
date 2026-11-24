"""Turning the view of a large model must stay fast and leave every item where it belongs.

An orbit used to rebuild every node's hinge ring and load arrows, each of which scanned the
whole model, and refreshed every member twice: 7.6 s per step for a 2,092-member frame. A camera
move now only moves things, with whole-model figures worked out once per pass (RedrawPass).
"""

import time

import pytest

import ui_qt.projection as _proj
from ui_qt.model_state import (ElementType, MemberLoad, DistLoad, ModelState, NodeLoad,
                               SupportType)
from ui_qt.projection import isometric


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication([])


def _grid(n: int) -> ModelState:
    """An n x n x 2 space grid: 2n² nodes, about 6n² members, every top node loaded."""
    s = ModelState()
    ids = {}
    for k in range(2):
        for i in range(n):
            for j in range(n):
                ids[i, j, k] = s.add_node(i * 2.0, j * 2.0, k * 2.0).id
    for k in range(2):
        for i in range(n):
            for j in range(n):
                if i + 1 < n:
                    s.add_member(ids[i, j, k], ids[i + 1, j, k])
                if j + 1 < n:
                    s.add_member(ids[i, j, k], ids[i, j + 1, k])
                if k == 0:
                    s.add_member(ids[i, j, 0], ids[i, j, 1])
                    if i + 1 < n:
                        s.add_member(ids[i, j, 0], ids[i + 1, j, 1])
    for i in (0, n - 1):
        for j in (0, n - 1):
            s.get_node(ids[i, j, 0]).support_type = SupportType.PIN
    for i in range(n):
        for j in range(n):
            s.active_case.set_node_load(ids[i, j, 1], NodeLoad(fz=-10e3))
    return s


def _canvas(state):
    from ui_qt.canvas import StructCanvas
    sc = StructCanvas()
    sc.load_state(state)
    return sc


def _turn(sc, azimuth, elevation=30.0):
    _proj.ISO_AZIMUTH, _proj.ISO_ELEVATION = azimuth, elevation
    sc.reproject()


def test_orbit_of_a_large_model_is_fast(qapp):
    state = _grid(19)                                  # 722 nodes, about 2,100 members
    sc = _canvas(state)
    assert len(sc._member_items) > 2000
    _turn(sc, -40)
    start = time.perf_counter()
    for k in range(5):
        _turn(sc, -45 + 3 * k)
    per_step = (time.perf_counter() - start) / 5
    # about 0.08 s today; it was 7.6 s. The limit leaves room for a slow test machine.
    assert per_step < 1.0, f"{per_step:.2f} s per orbit step"
    sc.clearSelection()


def test_after_an_orbit_every_member_and_ring_follows_its_nodes(qapp):
    state = _grid(4)
    pinned = state.members[0]
    pinned.element_type = ElementType.PIN_RIGHT
    sc = _canvas(state)
    _turn(sc, 70, 15)
    for mitem in sc._member_items.values():
        ni, nj = state.get_node(mitem.member.node_i), state.get_node(mitem.member.node_j)
        line = mitem.line()
        assert (line.x1(), line.y1()) == pytest.approx(isometric(ni.x, ni.y, ni.z))
        assert (line.x2(), line.y2()) == pytest.approx(isometric(nj.x, nj.y, nj.z))
    ring = sc._node_items[pinned.node_j]._hinge_item
    assert ring is not None
    hinge_node = state.get_node(pinned.node_j)
    assert (ring.pos().x(), ring.pos().y()) == pytest.approx(isometric(hinge_node.x, hinge_node.y,
                                                                       hinge_node.z))
    assert sc._pass is None                            # nothing cached after the pass
    sc.clearSelection()


def test_load_arrows_survive_an_orbit_in_every_case_mode(qapp):
    state = _grid(3)
    loaded = state.members[0]
    state.active_case.set_member_load(loaded.id, MemberLoad(dist_loads=[DistLoad("w", 5e3, 5e3)]))
    windward = state.nodes[0].id                       # a base node: no other load
    wind = state.add_load_case("Wind", "W")
    wind.set_node_load(windward, NodeLoad(fx=3e3))
    sc = _canvas(state)
    sc._show_all_cases = True                          # every case drawn at once
    sc.refresh_all_loads()
    assert sum(n.has_load_symbols() for n in sc._node_items.values()) == 10   # 9 top + wind
    _turn(sc, 20, 45)
    assert sum(n.has_load_symbols() for n in sc._node_items.values()) == 10
    assert sc._member_items[loaded.id].has_load_symbols()
    sc._show_all_cases = False
    sc.refresh_all_loads()                             # back to the active case only
    assert not sc._node_items[windward].has_load_symbols()
    assert sum(n.has_load_symbols() for n in sc._node_items.values()) == 9
    sc.clearSelection()


def test_a_load_edit_after_a_pass_uses_fresh_maxima(qapp):
    state = _grid(3)
    sc = _canvas(state)
    _turn(sc, 10)
    small, big = state.nodes[-2], state.nodes[-1]
    arrow_before = sc._node_items[small.id]._load_items[0].path().boundingRect().height()
    state.active_case.set_node_load(big.id, NodeLoad(fz=-1e6))       # 100 x the other loads
    sc.refresh_all_loads()
    arrow_after = sc._node_items[small.id]._load_items[0].path().boundingRect().height()
    assert arrow_after < arrow_before                  # rescaled to the new largest load
    assert sc.pass_value("x", lambda: -1.0) == -1.0    # outside a pass: computed every call
    sc.clearSelection()
