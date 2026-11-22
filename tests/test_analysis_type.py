"""Analysis type on the model: Space frame or Plane frame (XZ), saved in the file, passed to
the solver as locked DOFs, and checked before solving (one plane, in-plane sections and loads)."""

import math

import pytest

from ui_qt.model_builder import build_model
from ui_qt.model_state import ANALYSIS_TYPES, MemberLoad, DistLoad, ModelState, NodeLoad, SupportType
from ui_qt.solve_actions import lock_force_note, solve_engine, validate_model, validate_model_issues


def _portal(analysis_type="plane_xz") -> ModelState:
    """Pinned portal in the XZ plane (3D axes, Z up)."""
    s = ModelState()
    s.analysis_type = analysis_type
    n = [s.add_node(0, 0, 0), s.add_node(0, 0, 4), s.add_node(6, 0, 4), s.add_node(6, 0, 0)]
    n[0].support_type = n[3].support_type = SupportType.PIN
    for a, b in ((0, 1), (1, 2), (3, 2)):
        m = s.add_member(n[a].id, n[b].id)
        m.E, m.A, m.I, m.I_y, m.J = 210e9, 8e-3, 2e-4, 2e-4, 1e-5
    s.active_case.set_node_load(n[1].id, NodeLoad(fx=10e3, fz=-20e3))
    return s


def test_defaults_to_space_and_round_trips_through_the_file():
    assert ModelState().analysis_type == "space"
    s = _portal()
    assert ModelState.from_dict(s.to_dict()).analysis_type == "plane_xz"
    old = s.to_dict()
    old.pop("analysis_type")
    assert ModelState.from_dict(old).analysis_type == "space"      # files from before
    old["analysis_type"] = "nonsense"
    assert ModelState.from_dict(old).analysis_type == "space"


def test_builder_passes_the_locks_in_3d_only():
    model, _ = build_model(_portal(), None)
    assert model.locked_dofs == ANALYSIS_TYPES["plane_xz"] == (1, 3, 5)
    model, _ = build_model(_portal("space"), None)
    assert model.locked_dofs == ()
    s = ModelState()
    s.analysis_mode, s.analysis_type = "2D", "plane_xz"              # 2D is already planar
    s.add_member(s.add_node(0, 0, 0).id, s.add_node(3, 0, 0).id)
    assert build_model(s, None)[0].locked_dofs == ()


def test_a_clean_plane_frame_validates_and_solves_with_no_note():
    s = _portal()
    errors, warns = validate_model(s)
    assert not errors and not any("Plane frame" in w for w in warns)
    cache = solve_engine(*build_model(s, None), s)
    assert lock_force_note(cache) is None
    assert cache["reactions"][2::6].sum() == pytest.approx(20e3, rel=1e-9)


def test_a_node_off_the_plane_is_an_error_naming_it():
    s = _portal()
    s.nodes[2].y = 0.5
    issue = next(i for i in validate_model_issues(s) if "outside the frame's plane" in i.text)
    assert issue.severity == "error" and issue.node_ids == (s.nodes[2].id,)


def test_a_rolled_section_is_a_warning():
    s = _portal()
    s.members[1].beta_angle = math.radians(90)
    issue = next(i for i in validate_model_issues(s) if "section rotation" in i.text)
    assert issue.severity == "warning" and issue.member_ids == (s.members[1].id,)
    s.members[1].beta_angle = math.pi                                 # 180° is still in plane
    assert not any("section rotation" in i.text for i in validate_model_issues(s))


def test_out_of_plane_loads_are_warned_and_reported_after_the_solve():
    s = _portal()
    s.active_case.set_node_load(s.nodes[2].id, NodeLoad(fy=3e3))
    s.active_case.set_member_load(s.members[1].id, MemberLoad(dist_loads=[DistLoad("qy", 1e3, 1e3)]))
    issue = next(i for i in validate_model_issues(s) if "out-of-plane load" in i.text)
    assert issue.severity == "warning"
    assert issue.node_ids == (s.nodes[2].id,) and issue.member_ids == (s.members[1].id,)
    cache = solve_engine(*build_model(s, None), s)
    note = lock_force_note(cache)
    assert note and "not in the results" in note
