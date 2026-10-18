"""Duplicate checks: coincident nodes, duplicate / zero-length members, merging and the UI."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from ui_qt.model_checks import check_duplicates, merge_duplicates
from ui_qt.model_state import DistLoad, MemberLoad, ModelState, NodeLoad, SupportType


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication([])


def _messy() -> tuple[ModelState, dict]:
    """a—b beam; c sits on b (0.4 mm away); a second a—b member; a reversed b—a member;
    a zero-length member b—c; d is a lone far node."""
    s = ModelState()
    a, b = s.add_node(0, 0, 0), s.add_node(4, 0, 0)
    c = s.add_node(4.0004, 0, 0)
    d = s.add_node(10, 0, 0)
    m1 = s.add_member(a.id, b.id)
    m2 = s.add_member(a.id, b.id)          # exact duplicate
    m3 = s.add_member(c.id, a.id)          # duplicate through the coincident node, reversed
    m4 = s.add_member(b.id, c.id)          # zero length once b and c are the same point
    return s, dict(a=a, b=b, c=c, d=d, m1=m1, m2=m2, m3=m3, m4=m4)


def test_check_finds_each_kind():
    s, x = _messy()
    r = check_duplicates(s)
    assert r.node_clusters == [[x["b"].id, x["c"].id]]
    assert r.member_groups == [[x["m1"].id, x["m2"].id, x["m3"].id]]
    assert r.zero_length == [x["m4"].id]
    assert (r.extra_nodes, r.extra_members, r.is_clean) == (1, 2, False)


def test_tolerance_controls_what_counts_as_the_same_point():
    s, x = _messy()
    r = check_duplicates(s, tol=1e-4)                       # 0.1 mm: b and c are now distinct
    assert r.node_clusters == [] and r.zero_length == []
    assert r.member_groups == [[x["m1"].id, x["m2"].id]]


def test_clean_model_reports_clean():
    s = ModelState()
    a, b = s.add_node(0, 0, 0), s.add_node(1, 0, 0)
    s.add_member(a.id, b.id)
    assert check_duplicates(s).is_clean


def test_merge_repairs_the_model_and_carries_loads_and_supports():
    s, x = _messy()
    x["c"].support_type = SupportType.PIN                   # support on the node that disappears
    lc = s.load_cases[0]
    lc.set_node_load(x["b"].id, NodeLoad(fy=-1000.0))
    lc.set_node_load(x["c"].id, NodeLoad(fy=-500.0, fx=200.0))
    lc.member_loads[x["m2"].id] = MemberLoad(dist_loads=[DistLoad("w", 3.0, 3.0)])
    summary = merge_duplicates(s)
    assert summary.nodes_merged == 1 and summary.zero_length_removed == 1
    assert summary.members_removed == 2                     # m2 (load moved) and m3 (no loads)
    assert [m.id for m in s.members] == [x["m1"].id]
    assert {n.id for n in s.nodes} == {x["a"].id, x["b"].id, x["d"].id}
    assert s.get_node(x["b"].id).support_type == SupportType.PIN
    merged = lc.get_node_load(x["b"].id)
    assert (merged.fx, merged.fy) == (200.0, -1500.0)
    assert lc.get_member_load(x["m1"].id).net("w") == (3.0, 3.0)
    assert check_duplicates(s).is_clean


def test_reversed_duplicate_with_loads_is_kept_and_reported():
    s = ModelState()
    a, b = s.add_node(0, 0, 0), s.add_node(4, 0, 0)
    m1, m2 = s.add_member(a.id, b.id), s.add_member(b.id, a.id)
    s.load_cases[0].member_loads[m2.id] = MemberLoad(dist_loads=[DistLoad("w", 1.0, 2.0)])
    summary = merge_duplicates(s)
    assert summary.kept_reversed_with_loads == [m2.id] and summary.members_removed == 0
    assert len(s.members) == 2


def test_conflicting_supports_are_reported():
    s = ModelState()
    a, b = s.add_node(0, 0, 0), s.add_node(0, 0, 0)
    a.support_type, b.support_type = SupportType.FIXED, SupportType.ROLLER
    other = s.add_node(3, 0, 0)
    s.add_member(b.id, other.id)
    summary = merge_duplicates(s)
    assert summary.support_conflicts == [a.id]
    assert s.get_node(a.id).support_type == SupportType.FIXED      # the kept node's own support wins
    assert s.members[0].node_i == a.id                              # member re-pointed to the kept node


def test_rotating_a_symmetric_tower_face_four_times_leaves_no_duplicates(qapp):
    """The user's question: rotation copies must not leave replicated nodes or members."""
    from ui_qt.canvas import StructCanvas
    s = ModelState()
    # one face of a square tower, corners at (±1, -1): two legs and a diagonal
    p = [s.add_node(-1, -1, 0), s.add_node(1, -1, 0), s.add_node(-1, -1, 3), s.add_node(1, -1, 3)]
    for i, j in ((0, 2), (1, 3), (0, 3), (2, 3)):
        s.add_member(p[i].id, p[j].id)
    sc = StructCanvas()
    sc.load_state(s)
    for it in list(sc._member_items.values()) + list(sc._node_items.values()):
        it.setSelected(True)
    sc.rotate_selection("Z", 90.0, pivot=(0, 0, 0), copies=3)
    r = check_duplicates(sc.model_state)
    assert r.is_clean, r
    assert len(sc.model_state.nodes) == 8                    # 4 corners × 2 levels, legs shared
    assert len(sc.model_state.members) == 12                 # 4 legs + 4 diagonals + 4 top ties
    legs = [m for m in sc.model_state.members
            if sc.model_state.get_node(m.node_i).x == sc.model_state.get_node(m.node_j).x
            and sc.model_state.get_node(m.node_i).y == sc.model_state.get_node(m.node_j).y]
    assert len(legs) == 4                                    # each corner leg exists exactly once


def test_validation_warns_about_duplicates_with_ids():
    from ui_qt.solve_actions import validate_model_issues
    s, x = _messy()
    warns = [i for i in validate_model_issues(s) if i.severity == "warning"]
    node_warn = next(i for i in warns if "coincide" in i.text)
    member_warn = next(i for i in warns if "duplicate member" in i.text)
    assert set(node_warn.node_ids) == {x["b"].id, x["c"].id}
    assert set(member_warn.member_ids) == {x["m1"].id, x["m2"].id, x["m3"].id}


def test_scene_merge_is_one_undo_step(qapp):
    from ui_qt.canvas import StructCanvas
    s, x = _messy()
    sc = StructCanvas()
    sc.load_state(s)
    sc.merge_duplicates(1e-3)
    assert len(sc.model_state.members) == 1 and len(sc._member_items) == 1
    sc.undo()
    assert len(sc.model_state.members) == 4 and len(sc.model_state.nodes) == 4


def test_dialog_checks_selects_and_fixes(qapp):
    from ui_qt.canvas import StructCanvas
    from ui_qt.dialogs import DuplicatesDialog
    s, x = _messy()
    sc = StructCanvas()
    sc.load_state(s)
    dlg = DuplicatesDialog(sc)
    assert "coincident" in dlg._result.text() and dlg._btn_fix.isEnabled()
    dlg.select_found()
    selected = {getattr(i, "member", None) and i.member.id for i in sc.selectedItems()} - {None}
    assert {x["m1"].id, x["m2"].id, x["m3"].id, x["m4"].id} <= selected
    dlg.fix()
    assert "No duplicates found" in dlg._result.text() and "Merged 1 node" in dlg._result.text()
    assert not dlg._btn_fix.isEnabled()
    dlg._tol.setValue(0.01)                                   # re-check runs on a tolerance change
    assert dlg.report.is_clean


# ── overlapping collinear members ─────────────────────────────────────────────

def _chain_with_full_member():
    """A member divided into two (a–b–c) plus a member drawn over it end to end (a–c)."""
    s = ModelState()
    a, b, c = s.add_node(0, 0, 0), s.add_node(2, 0, 1.5), s.add_node(4, 0, 3)
    m1, m2, full = s.add_member(a.id, b.id), s.add_member(b.id, c.id), s.add_member(c.id, a.id)
    return s, m1, m2, full


def test_member_drawn_over_a_divided_member_is_found():
    s, m1, m2, full = _chain_with_full_member()
    r = check_duplicates(s)
    assert r.overlaps == [(m1.id, full.id), (m2.id, full.id)]
    assert r.member_groups == [] and not r.is_clean and not r.fixable
    assert full.id in r.member_ids()


def test_segments_that_only_touch_are_not_overlaps():
    s, m1, m2, full = _chain_with_full_member()
    s.remove_member(full.id)
    assert check_duplicates(s).is_clean


def test_partial_overlap_and_parallel_lines():
    s = ModelState()
    n = [s.add_node(0, 0, 0), s.add_node(3, 0, 0), s.add_node(2, 0, 0), s.add_node(5, 0, 0),
         s.add_node(0, 0.5, 0), s.add_node(5, 0.5, 0)]
    a = s.add_member(n[0].id, n[1].id)           # 0..3
    b = s.add_member(n[2].id, n[3].id)           # 2..5 overlaps 2..3 with a
    s.add_member(n[4].id, n[5].id)               # parallel, 0.5 m away: not an overlap
    assert check_duplicates(s).overlaps == [(a.id, b.id)]


def test_overlaps_are_reported_not_merged_and_warned_before_solving():
    from ui_qt.solve_actions import validate_model_issues
    s, m1, m2, full = _chain_with_full_member()
    summary = merge_duplicates(s)
    assert summary.members_removed == 0 and len(s.members) == 3
    warn = next(i for i in validate_model_issues(s) if "overlap" in i.text)
    assert set(warn.member_ids) == {m1.id, m2.id, full.id}


def test_dialog_lists_overlaps_selects_them_and_disables_merge(qapp):
    from ui_qt.canvas import StructCanvas
    from ui_qt.dialogs import DuplicatesDialog
    s, m1, m2, full = _chain_with_full_member()
    sc = StructCanvas()
    sc.load_state(s)
    dlg = DuplicatesDialog(sc)
    assert "overlapping" in dlg._result.text()
    assert dlg._btn_select.isEnabled() and not dlg._btn_fix.isEnabled()
    dlg.select_found()
    selected = {i.member.id for i in sc.selectedItems() if hasattr(i, "member")}
    assert selected == {m1.id, m2.id, full.id}
