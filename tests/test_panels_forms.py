"""Headless smoke tests for ui_qt/panels.py's member/node property forms.

_MemberForm/_MultiMemberForm and _NodeForm/_MultiNodeForm used to duplicate a
good deal of logic (Design-tab visibility, M_Rd display, distributed-load
table population, section-picker application) under an "_m"-suffixed copy.
That was pulled into shared helpers operating on small widget bundles
(_DesignWidgets, _DLTableWidgets) — these tests exercise both the single- and
multi-member forms through that shared code path to lock in behavioural
parity, since nothing previously enforced it beyond the duplication itself.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from ui_qt.model_state import (
    ModelState, MemberData, NodeData, LoadCase, DistLoad, MemberLoad,
)
from ui_qt.panels import _MemberForm, _MultiMemberForm


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def _steel_state() -> ModelState:
    lc = LoadCase(id=0, name="Dead load", category="G")
    member = MemberData(id=0, node_i=0, node_j=1, E=210e9)  # steel: E outside concrete/timber ranges
    lc.member_loads[0] = MemberLoad(dist_loads=[DistLoad("w", 5e3, 5e3)])
    return ModelState(
        nodes=[NodeData(id=0, x=0.0, y=0.0), NodeData(id=1, x=4.0, y=0.0)],
        members=[member], load_cases=[lc],
    )


def _concrete_state() -> ModelState:
    lc = LoadCase(id=0, name="Dead load", category="G")
    member = MemberData(id=0, node_i=0, node_j=1, E=30e9,   # concrete range
                         b_sec=0.3, h_sec=0.5, d_eff=0.45, As_tension=1500e-6)
    return ModelState(
        nodes=[NodeData(id=0, x=0.0, y=0.0), NodeData(id=1, x=4.0, y=0.0)],
        members=[member], load_cases=[lc],
    )


# ── _MemberForm ───────────────────────────────────────────────────────────

def test_member_form_steel_shows_wpl_wel_not_concrete_fields(qapp):
    state = _steel_state()
    form = _MemberForm(state.members[0], state, on_apply=lambda: None)
    assert form._design_form.isRowVisible(form._Wpl)
    assert not form._design_form.isRowVisible(form._b_sec)


def test_member_form_concrete_shows_section_fields_and_computes_mrd(qapp):
    state = _concrete_state()
    form = _MemberForm(state.members[0], state, on_apply=lambda: None)
    assert form._design_form.isRowVisible(form._b_sec)
    assert not form._design_form.isRowVisible(form._Wpl)
    # fy defaults to member.fy (275 MPa) — with b/h/As/d already set, M_Rd must compute.
    assert form._mrd_lbl.text() != "—"
    assert "kN" in form._mrd_lbl.text()


def test_member_form_dl_table_populated_from_load_case(qapp):
    state = _steel_state()
    form = _MemberForm(state.members[0], state, on_apply=lambda: None)
    assert form._dl_table.rowCount() == 1
    assert form._dl_table.cellWidget(0, 2).value() == pytest.approx(5.0)  # kN/m


def test_member_form_dl_add_and_remove_row(qapp):
    state = _steel_state()
    form = _MemberForm(state.members[0], state, on_apply=lambda: None)
    form._dl_add_entry("qx")
    assert form._dl_table.rowCount() == 2
    form._dl_table.selectRow(1)
    form._dl_remove_row()
    assert form._dl_table.rowCount() == 1


# ── _MultiMemberForm ──────────────────────────────────────────────────────

def test_multi_member_form_mirrors_single_form_design_behaviour(qapp):
    state = _concrete_state()
    state.members.append(MemberData(id=1, node_i=1, node_j=2, E=30e9,
                                     b_sec=0.3, h_sec=0.5, d_eff=0.45, As_tension=1500e-6))
    form = _MultiMemberForm(state.members, state, on_apply=lambda: None)
    assert form._design_form_m.isRowVisible(form._b_sec_m)
    assert not form._design_form_m.isRowVisible(form._Wpl_m)
    # Concrete M_Rd must be computed immediately on open, same as _MemberForm
    # (previously the multi-form only auto-computed the steel/timber M_Rd).
    assert form._mrd_lbl_m.text() != "—"
    assert "kN" in form._mrd_lbl_m.text()


def test_multi_member_form_apply_updates_all_selected_members(qapp):
    state = _steel_state()
    state.members.append(MemberData(id=1, node_i=1, node_j=2, E=210e9))
    form = _MultiMemberForm(state.members, state, on_apply=lambda: None)
    form._E.setValue(200.0)   # GPa
    form._apply()
    assert state.members[0].E == pytest.approx(200e9)
    assert state.members[1].E == pytest.approx(200e9)


def test_multi_member_form_dl_table_uses_first_member_only(qapp):
    state = _steel_state()
    state.members.append(MemberData(id=1, node_i=1, node_j=2, E=210e9))  # no loads on member 1
    form = _MultiMemberForm(state.members, state, on_apply=lambda: None)
    assert form._dl_table_m.rowCount() == 1   # from member 0's load, per _dl_populate_m contract


def test_multi_member_form_dl_add_and_remove_row(qapp):
    state = _steel_state()
    state.members.append(MemberData(id=1, node_i=1, node_j=2, E=210e9))
    form = _MultiMemberForm(state.members, state, on_apply=lambda: None)
    form._dl_add_entry_m("qy")
    assert form._dl_table_m.rowCount() == 2
    form._dl_table_m.selectRow(1)
    form._dl_remove_row_m()
    assert form._dl_table_m.rowCount() == 1


def test_member_form_apply_clears_estimated_reinforcement_flag(qapp):
    """Applying from the properties panel means the user has reviewed the
    value — the wizard-placed 'estimated minimum' flag must not survive."""
    state = _concrete_state()
    state.members[0].reinforcement_estimated = True
    form = _MemberForm(state.members[0], state, on_apply=lambda: None)
    form._apply()
    assert state.members[0].reinforcement_estimated is False


def test_multi_member_form_apply_clears_estimated_reinforcement_flag(qapp):
    state = _concrete_state()
    state.members.append(MemberData(id=1, node_i=1, node_j=2, E=30e9,
                                    b_sec=0.3, h_sec=0.5, d_eff=0.45, As_tension=1500e-6))
    for m in state.members:
        m.reinforcement_estimated = True
    form = _MultiMemberForm(state.members, state, on_apply=lambda: None)
    form._apply()
    assert all(m.reinforcement_estimated is False for m in state.members)


# ── member group assignment ──────────────────────────────────────────────────

def test_member_form_group_field_prefilled_from_member(qapp):
    state = _steel_state()
    state.members[0].group = "Rafter"
    form = _MemberForm(state.members[0], state, on_apply=lambda: None)
    assert form._group.text() == "Rafter"


def test_member_form_apply_sets_group(qapp):
    state = _steel_state()
    form = _MemberForm(state.members[0], state, on_apply=lambda: None)
    form._group.setText("  Column  ")
    form._apply()
    assert state.members[0].group == "Column"   # stripped of surrounding whitespace


def test_multi_member_form_group_prefilled_from_first_member(qapp):
    state = _steel_state()
    state.members[0].group = "Leg"
    state.members.append(MemberData(id=1, node_i=1, node_j=2, E=210e9, group="Diagonal"))
    form = _MultiMemberForm(state.members, state, on_apply=lambda: None)
    assert form._group_m.text() == "Leg"   # first member's value, mirroring _type_combo's pattern


def test_multi_member_form_apply_sets_group_on_every_member(qapp):
    state = _steel_state()
    state.members.append(MemberData(id=1, node_i=1, node_j=2, E=210e9))
    form = _MultiMemberForm(state.members, state, on_apply=lambda: None)
    form._group_m.setText("Bracing")
    form._apply()
    assert all(m.group == "Bracing" for m in state.members)
