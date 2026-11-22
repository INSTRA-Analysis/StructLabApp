"""Space frames: members without a real weak-axis I_y / torsion constant J are flagged, and
assigning a library profile that has none clears the previous section's values (an angle's
weak axis must not survive on an IPE)."""

from ui_qt.groups_panel import apply_section
from ui_qt.model_state import ElementType, ModelState, SupportType
from ui_qt.solve_actions import solve_notes, validate_model, validate_model_issues


def _frame(analysis_type: str) -> ModelState:
    s = ModelState()
    s.analysis_type = analysis_type
    a, b = s.add_node(0, 0, 0), s.add_node(0, 0, 4)
    a.support_type = SupportType.FIXED
    s.add_member(a.id, b.id)
    return s


def _flagged(s) -> bool:
    return any(i.severity == "note" and "weak-axis I_y" in i.text for i in validate_model_issues(s))


def test_it_is_a_note_after_the_solve_not_a_question_before_it():
    s = _frame("space")
    errors, warnings = validate_model(s)
    assert not any("weak-axis" in w for w in warnings)       # no "Solve anyway?" for this
    assert "weak-axis I_y" in solve_notes(validate_model_issues(s))


def test_space_frame_member_without_iy_or_j_is_flagged():
    s = _frame("space")
    assert _flagged(s)                                   # default member: I_y None, J = 0
    m = s.members[0]
    m.I_y, m.J = 6.04e-6, 2.01e-7
    assert not _flagged(s)
    m.J = 0.0
    assert _flagged(s)


def test_bars_and_plane_frames_are_not_flagged():
    s = _frame("space")
    s.members[0].element_type = ElementType.BAR
    assert not _flagged(s)
    assert not _flagged(_frame("plane_xz"))              # in-plane bending uses I only


def test_assigning_a_profile_without_weak_axis_data_clears_it():
    s = _frame("space")
    m = s.members[0]
    m.I_y, m.J = 1.2e-6, 3e-8                           # e.g. left by an angle
    result = (210e9, 5.38e-3, 8.356e-5, 6.28e-4, 5.57e-4, 0.15, 0.3, 7850, 355e6, "steel")
    apply_section([m], result, extra={})                 # IPE 300: no I_y / J in the library
    assert m.I_y is None and m.J == 0.0
    apply_section([m], result, extra={"I_y": 2e-6, "J": 4e-8})
    assert (m.I_y, m.J) == (2e-6, 4e-8)
