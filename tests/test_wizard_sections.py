"""Tests that wizard- and CSV-generated members carry real capacity-check
data (W_pl/W_el, fy, b_sec/h_sec), not just stiffness (E/A/I).

Previously beam_wizard/portal_wizard/truss_wizard and CSV import only set
E/A/I, so the Design tab's bending/axial checks always read "N/A" until the
user re-picked a section through the section picker dialog — the only code
path that touched W_pl/W_el/fy. Also fixes a latent typo ("IPE_400" instead
of "IPE 400" in wizards.py's rafter dropdown) that would have silently broken
the name-based section lookup this fix relies on.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
from pathlib import Path

import pytest

from ui_qt.model_state import ElementType
from ui_qt.section_library import steel_capacity_by_name, steel_profile_by_name
from ui_qt.presets import beam_wizard, portal_wizard, truss_wizard, frame_wizard
from ui_qt.csv_import import parse_structlab_csv

# Test fixture profiles: (E, A, I), matching the EN section library exactly
# (frame_wizard()/beam_wizard() etc. just consume plain (E,A,I) tuples — the
# wizard *dialogs* now resolve these via section_library, not hardcoded
# tuples, so tests build their own small fixtures here instead).
_E_STEEL = 210e9
IPE_300 = (_E_STEEL, *steel_profile_by_name("IPE 300")[:2])
IPE_400 = (_E_STEEL, *steel_profile_by_name("IPE 400")[:2])
HEB_260 = (_E_STEEL, *steel_profile_by_name("HEB 260")[:2])


# ── steel_capacity_by_name ───────────────────────────────────────────────────

def test_steel_capacity_by_name_known_profile():
    cap = steel_capacity_by_name("IPE 300")
    assert cap is not None
    W_pl, W_el = cap
    assert W_pl == pytest.approx(628e-6)
    assert W_el == pytest.approx(557e-6)


def test_steel_capacity_by_name_unknown_profile_returns_none():
    assert steel_capacity_by_name("SHS 150x8") is None
    assert steel_capacity_by_name("not a real section") is None


# ── beam_wizard ───────────────────────────────────────────────────────────────

def test_beam_wizard_steel_sets_capacity_fields():
    E, A, I = IPE_400
    W_pl, W_el = steel_capacity_by_name("IPE 400")
    s = beam_wizard(
        spans=[6.0], support_types=["PIN", "ROLLER"], E=E, A=A, I=I,
        udl_g=10e3, fy=355e6, W_pl=W_pl, W_el=W_el,
    )
    m = s.members[0]
    assert m.fy == pytest.approx(355e6)
    assert m.W_pl == pytest.approx(W_pl)
    assert m.W_el == pytest.approx(W_el)


def test_beam_wizard_concrete_sets_section_geometry():
    s = beam_wizard(
        spans=[6.0], support_types=["PIN", "ROLLER"], E=32e9, A=0.15, I=0.003125,
        fy=30e6, b_sec=0.3, h_sec=0.5,
    )
    m = s.members[0]
    assert m.fy == pytest.approx(30e6)          # fck for concrete
    assert m.b_sec == pytest.approx(0.3)
    assert m.h_sec == pytest.approx(0.5)
    assert m.d_eff == pytest.approx(0.45)        # h - 50mm assumed cover


def test_beam_wizard_defaults_are_unchanged_when_capacity_args_omitted():
    """Backward compatible: a caller that doesn't pass the new kwargs gets
    the same MemberData defaults as before this fix."""
    s = beam_wizard(spans=[6.0], support_types=["PIN", "ROLLER"], E=210e9, A=0.005381, I=8.356e-5)
    m = s.members[0]
    assert m.W_pl == 0.0 and m.W_el == 0.0
    assert m.b_sec == 0.0 and m.h_sec == 0.0


# ── portal_wizard ─────────────────────────────────────────────────────────────

def test_portal_wizard_columns_and_rafter_get_independent_capacities():
    E_col, A_col, I_col = HEB_260
    E_raf, A_raf, I_raf = IPE_400
    col_W_pl, col_W_el = steel_capacity_by_name("HEB 260")
    raf_W_pl, raf_W_el = steel_capacity_by_name("IPE 400")

    s = portal_wizard(
        span=10.0, height=5.0, fixed_base=True,
        E_col=E_col, A_col=A_col, I_col=I_col,
        E_raf=E_raf, A_raf=A_raf, I_raf=I_raf,
        col_fy=355e6, col_W_pl=col_W_pl, col_W_el=col_W_el,
        raf_fy=355e6, raf_W_pl=raf_W_pl, raf_W_el=raf_W_el,
    )
    columns = [m for m in s.members if m.I == pytest.approx(I_col)]
    rafters = [m for m in s.members if m.I == pytest.approx(I_raf)]
    assert len(columns) == 2 and len(rafters) == 1
    assert all(c.W_pl == pytest.approx(col_W_pl) for c in columns)
    assert rafters[0].W_pl == pytest.approx(raf_W_pl)
    # columns and rafter must not have swapped capacities
    assert columns[0].W_pl != pytest.approx(rafters[0].W_pl)


# ── truss_wizard ──────────────────────────────────────────────────────────────

def test_truss_wizard_bars_get_fy():
    s = truss_wizard(
        truss_type="Pratt", n_panels=4, span=12.0, depth=1.5,
        chord_section=IPE_300, web_section=IPE_300, chord_fy=355e6, web_fy=355e6,
    )
    assert s.members
    assert all(m.element_type is ElementType.BAR for m in s.members)
    assert all(m.fy == pytest.approx(355e6) for m in s.members)


def test_truss_wizard_chord_and_web_can_have_independent_fy():
    s = truss_wizard(
        truss_type="Warren", n_panels=4, span=12.0, depth=1.5,
        chord_section=IPE_300, web_section=IPE_300, chord_fy=355e6, web_fy=235e6,
    )
    chords = [m for m in s.members if m.fy == pytest.approx(355e6)]
    webs = [m for m in s.members if m.fy == pytest.approx(235e6)]
    assert chords and webs
    assert len(chords) + len(webs) == len(s.members)


# ── CSV import ────────────────────────────────────────────────────────────────

def test_csv_import_reads_w_pl_w_el_columns():
    csv_text = (
        "#NODES\n"
        "id,x,y,z\n"
        "1,0,0,0\n"
        "2,6,0,0\n"
        "#MEMBERS\n"
        "id,node_i,node_j,etype,e,a,i,fy,w_pl,w_el\n"
        "1,1,2,beam,2.1e11,0.008446,2.313e-4,3.55e8,1.307e-3,1.157e-3\n"
    )
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "beam.csv"
        path.write_text(csv_text)
        state, warnings = parse_structlab_csv(path)

    assert warnings == []
    m = state.members[0]
    assert m.W_pl == pytest.approx(1.307e-3)
    assert m.W_el == pytest.approx(1.157e-3)


# ── wizard DIALOGS end-to-end (exercises the exact _on_accept wiring, not
# just the presets.py functions the dialogs call) ────────────────────────────

@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def test_beam_wizard_dialog_default_steel_profile_gets_real_capacity(qapp):
    from ui_qt.wizards import BeamWizardDialog
    dlg = BeamWizardDialog()
    assert dlg._rb_steel.isChecked()            # default: steel
    dlg._on_accept()
    m = dlg.result().members[0]
    assert m.fy == pytest.approx(355e6)
    assert m.W_pl > 0.0                          # default profile is IPE 400


def test_portal_wizard_dialog_default_profiles_get_real_capacity(qapp):
    """Also guards the 'IPE_400' -> 'IPE 400' rafter-dropdown typo: a broken
    name lookup would silently leave W_pl at 0 instead of raising."""
    from ui_qt.wizards import PortalWizardDialog
    dlg = PortalWizardDialog()
    dlg._on_accept()
    state = dlg.result()
    assert all(m.W_pl > 0.0 for m in state.members)
    assert all(m.fy == pytest.approx(355e6) for m in state.members)


def test_truss_wizard_dialog_default_profiles_get_fy(qapp):
    from ui_qt.wizards import TrussWizardDialog
    dlg = TrussWizardDialog()
    dlg._on_accept()
    state = dlg.result()
    assert state.members
    assert all(m.fy == pytest.approx(355e6) for m in state.members)


def test_truss_wizard_dialog_bars_get_fy_even_when_profile_not_in_library(qapp):
    """A profile the picker returns with no library match (e.g. a fully
    custom entry) must still leave fy set — bars only need axial capacity,
    not W_pl/W_el, so a missing section-modulus match shouldn't matter."""
    from ui_qt.wizards import TrussWizardDialog
    dlg = TrussWizardDialog()
    # Simulate picking something the library can't resolve a name for.
    dlg._chord_sec.result = (200e9, 0.01, 1e-5, 0.0, 0.0, 0.0, 0.0, 7850.0, 235e6, "steel")
    dlg._on_accept()
    state = dlg.result()
    assert state.members
    chords = [m for m in state.members if m.fy == pytest.approx(235e6)]
    assert chords


# ── Beam Wizard: per-span/per-node tables ────────────────────────────────────

def test_beam_wizard_default_tables_match_default_span_count(qapp):
    from ui_qt.wizards import BeamWizardDialog
    dlg = BeamWizardDialog()
    assert dlg._n_spans.value() == 1
    assert dlg._spans_table.rowCount() == 1
    assert dlg._supports_table.rowCount() == 2   # spans + 1 nodes


def test_beam_wizard_changing_span_count_rebuilds_tables(qapp):
    from ui_qt.wizards import BeamWizardDialog
    dlg = BeamWizardDialog()
    dlg._n_spans.setValue(4)
    assert dlg._spans_table.rowCount() == 4
    assert dlg._supports_table.rowCount() == 5
    dlg._n_spans.setValue(2)
    assert dlg._spans_table.rowCount() == 2
    assert dlg._supports_table.rowCount() == 3


def test_beam_wizard_rebuild_preserves_existing_values(qapp):
    from ui_qt.wizards import BeamWizardDialog
    dlg = BeamWizardDialog()
    dlg._n_spans.setValue(3)
    dlg._spans_table.cellWidget(0, 0).setValue(8.0)
    dlg._supports_table.cellWidget(0, 0).setCurrentText("FIXED")
    dlg._n_spans.setValue(4)   # grow by one — existing rows must keep their values
    assert dlg._spans_table.cellWidget(0, 0).value() == pytest.approx(8.0)
    assert dlg._supports_table.cellWidget(0, 0).currentText() == "FIXED"


def test_beam_wizard_unequal_spans_and_cantilever_tip(qapp):
    """The whole point of the table UI: unequal span lengths and a FREE end
    (cantilever tip) — both already supported by beam_wizard()'s backend,
    previously unreachable from the dialog."""
    from ui_qt.wizards import BeamWizardDialog
    dlg = BeamWizardDialog()
    dlg._n_spans.setValue(2)
    dlg._spans_table.cellWidget(0, 0).setValue(6.0)
    dlg._spans_table.cellWidget(1, 0).setValue(2.0)     # short cantilever span
    dlg._supports_table.cellWidget(0, 0).setCurrentText("FIXED")
    dlg._supports_table.cellWidget(1, 0).setCurrentText("PIN")
    dlg._supports_table.cellWidget(2, 0).setCurrentText("FREE")   # cantilever tip
    dlg._on_accept()
    state = dlg.result()

    assert len(state.nodes) == 3
    assert len(state.members) == 2
    xs = sorted(n.x for n in state.nodes)
    assert xs == pytest.approx([0.0, 6.0, 8.0])
    from ui_qt.model_state import SupportType
    supports = {n.x: n.support_type for n in state.nodes}
    assert supports[0.0] == SupportType.FIXED
    assert supports[6.0] == SupportType.PIN
    assert supports[8.0] == SupportType.FREE


# ── Frame Wizard ──────────────────────────────────────────────────────────────

def test_frame_wizard_dialog_defaults_to_pinned_base_with_real_section(qapp):
    from ui_qt.wizards import FrameWizardDialog
    from ui_qt.model_state import SupportType
    dlg = FrameWizardDialog()
    assert dlg._rb_pin.isChecked()
    dlg._on_accept()
    state = dlg.result()
    assert state.members
    assert all(m.E > 0 and m.A > 0 and m.I > 0 for m in state.members)
    assert all(m.W_pl > 0.0 for m in state.members)   # default profile is IPE 300
    ground = [n for n in state.nodes if n.support_type != SupportType.FREE]
    assert ground and all(n.support_type == SupportType.PIN for n in ground)


def test_frame_wizard_dialog_fixed_base(qapp):
    from ui_qt.wizards import FrameWizardDialog
    from ui_qt.model_state import SupportType
    dlg = FrameWizardDialog()
    dlg._rb_fixed.setChecked(True)
    dlg._on_accept()
    state = dlg.result()
    ground = [n for n in state.nodes if n.support_type != SupportType.FREE]
    assert ground and all(n.support_type == SupportType.FIXED for n in ground)


def test_frame_wizard_backend_sets_real_properties_not_placeholder():
    """Previously frame_wizard() never touched E/A/I on created members, so
    they kept MemberData's generic placeholder defaults."""
    s = frame_wizard(2, 2, 6.0, 3.0, fixed_base=True,
                     E=210e9, A=0.008446, I=2.313e-4, fy=355e6, W_pl=1.307e-3, W_el=1.157e-3)
    assert s.members
    assert all(m.E == pytest.approx(210e9) for m in s.members)
    assert all(m.W_pl == pytest.approx(1.307e-3) for m in s.members)
    from ui_qt.model_state import SupportType
    base_nodes = [n for n in s.nodes if n.support_type != SupportType.FREE]
    assert base_nodes and all(n.support_type == SupportType.FIXED for n in base_nodes)


def test_frame_wizard_backend_concrete_params():
    s = frame_wizard(2, 2, 6.0, 3.0, fixed_base=True,
                     E=32e9, A=0.16, I=0.16 * 0.4 ** 3 / 12,
                     fy=30e6, b_sec=0.4, h_sec=0.4, density=2500.0)
    assert s.members
    assert all(m.b_sec == pytest.approx(0.4) for m in s.members)
    assert all(m.d_eff == pytest.approx(0.35) for m in s.members)   # h - 50mm cover
    assert all(m.density == pytest.approx(2500.0) for m in s.members)
    assert all(m.W_pl == 0.0 for m in s.members)   # concrete: no steel section modulus


def test_frame_wizard_dialog_concrete_pick_propagates_to_every_member(qapp):
    """The section picker already lets you choose a concrete rectangular
    section — _on_accept must actually forward b/h/density instead of
    discarding them (previously done via a `*_` unpack)."""
    from ui_qt.wizards import FrameWizardDialog
    dlg = FrameWizardDialog()
    # Simulate picking a 400x400 C30/37 concrete section via the full picker.
    dlg._sec.result = (32e9, 0.16, 0.16 * 0.4 ** 3 / 12, 0.0064, 0.00427,
                       0.4, 0.4, 2500.0, 30e6, "concrete")
    dlg._on_accept()
    state = dlg.result()
    assert state.members
    assert all(m.b_sec == pytest.approx(0.4) for m in state.members)
    assert all(m.h_sec == pytest.approx(0.4) for m in state.members)
    assert all(2000 <= m.density <= 3000 for m in state.members)
    assert all(m.fy == pytest.approx(30e6) for m in state.members)


def test_frame_wizard_dialog_steel_pick_has_no_concrete_geometry_or_density(qapp):
    from ui_qt.wizards import FrameWizardDialog
    dlg = FrameWizardDialog()   # default profile is steel (IPE 300)
    dlg._on_accept()
    state = dlg.result()
    assert all(m.b_sec == 0.0 and m.h_sec == 0.0 for m in state.members)
    assert all(m.density == 0.0 for m in state.members)


def test_frame_wizard_dialog_concrete_member_gets_a_real_design_check(qapp):
    """End-to-end: a Frame Wizard concrete member, once reinforced, must
    produce a real bending verdict through the actual Design tab code path —
    same shape of regression as the Portal Wizard density bug."""
    from ui_qt.wizards import FrameWizardDialog
    from ui_qt.panels import ResultsPanel

    dlg = FrameWizardDialog()
    dlg._sec.result = (32e9, 0.16, 0.16 * 0.4 ** 3 / 12, 0.0, 0.0,
                       0.4, 0.4, 2500.0, 30e6, "concrete")
    dlg._on_accept()
    state = dlg.result()
    col = state.members[0]
    col.As_tension = 1500e-6

    panel = ResultsPanel()
    panel._populate_design_table([(col.id, 50e3, 0.0)], state)
    tbl = panel._design_table
    checks   = [tbl.item(r, 1).text() for r in range(tbl.rowCount())]
    statuses = [tbl.item(r, 5).text() for r in range(tbl.rowCount())]
    assert "Bending M" in checks
    assert statuses[checks.index("Bending M")].startswith(("PASS", "FAIL"))


# ── Portal Wizard RC option ───────────────────────────────────────────────────

def test_portal_wizard_dialog_rc_sets_independent_column_and_rafter_geometry(qapp):
    from ui_qt.wizards import PortalWizardDialog
    dlg = PortalWizardDialog()
    dlg._rb_rc.setChecked(True)
    dlg._rc_col_b.setValue(400); dlg._rc_col_h.setValue(400)
    dlg._rc_raf_b.setValue(300); dlg._rc_raf_h.setValue(600)
    dlg._on_accept()
    state = dlg.result()

    columns = [m for m in state.members if m.h_sec == pytest.approx(0.4)]
    rafters = [m for m in state.members if m.h_sec == pytest.approx(0.6)]
    assert len(columns) == 2
    assert len(rafters) == 1
    assert all(c.b_sec == pytest.approx(0.4) for c in columns)
    assert rafters[0].b_sec == pytest.approx(0.3)
    # must not cross-assign column geometry onto the rafter or vice versa
    assert rafters[0].b_sec != pytest.approx(columns[0].b_sec)


def test_portal_wizard_backend_concrete_params():
    s = portal_wizard(
        span=10.0, height=5.0, fixed_base=True,
        E_col=32e9, A_col=0.16, I_col=0.16 * 0.4 ** 3 / 12,
        E_raf=32e9, A_raf=0.18, I_raf=0.18 * 0.6 ** 3 / 12,
        col_fy=30e6, raf_fy=30e6,
        col_b_sec=0.4, col_h_sec=0.4, raf_b_sec=0.3, raf_h_sec=0.6,
        density=2500.0,
    )
    columns = [m for m in s.members if m.h_sec == pytest.approx(0.4)]
    rafters = [m for m in s.members if m.h_sec == pytest.approx(0.6)]
    assert len(columns) == 2 and len(rafters) == 1
    assert all(c.d_eff == pytest.approx(0.35) for c in columns)   # h - 50mm cover
    assert rafters[0].d_eff == pytest.approx(0.55)
    # density must be in the concrete range (2000-3000) or the Design tab's
    # material inference misclassifies the member as steel regardless of
    # b_sec/h_sec being set — this is the exact bug that shipped once.
    assert all(m.density == pytest.approx(2500.0) for m in s.members)


def test_portal_wizard_dialog_rc_sets_concrete_range_density(qapp):
    from ui_qt.wizards import PortalWizardDialog
    dlg = PortalWizardDialog()
    dlg._rb_rc.setChecked(True)
    dlg._on_accept()
    state = dlg.result()
    assert all(2000 <= m.density <= 3000 for m in state.members)


def test_portal_wizard_dialog_steel_has_zero_density(qapp):
    """Steel members must NOT get a concrete-range density (would misclassify
    them as concrete in the Design tab's material inference)."""
    from ui_qt.wizards import PortalWizardDialog
    dlg = PortalWizardDialog()
    assert dlg._rb_steel.isChecked()   # default
    dlg._on_accept()
    state = dlg.result()
    assert all(m.density == 0.0 for m in state.members)


def test_portal_wizard_rc_column_gets_a_real_bending_check_once_reinforced(qapp):
    """End-to-end reproduction of the reported bug, through the actual Design
    tab code path (ResultsPanel._populate_design_table, which infers
    steel-vs-concrete from density): a concrete Portal Wizard column showed
    a computed M_Ed but no capacity check at all, because density stayed 0
    and the material inference silently took the steel branch instead.
    With density fixed, once As is filled in (the one genuinely
    wizard-can't-supply input, same limitation as beam_wizard), the Design
    tab must produce a real M_Rd/eta, not "N/A"."""
    from ui_qt.wizards import PortalWizardDialog
    from ui_qt.panels import ResultsPanel

    dlg = PortalWizardDialog()
    dlg._rb_rc.setChecked(True)
    dlg._on_accept()
    state = dlg.result()

    col = state.members[0]
    assert 2000 <= col.density <= 3000          # the bug: this used to be 0
    col.As_tension = 1500e-6                     # the one input the wizard can't supply

    panel = ResultsPanel()
    panel._populate_design_table([(col.id, 100e3, 0.0)], state)
    tbl = panel._design_table
    checks  = [tbl.item(r, 1).text() for r in range(tbl.rowCount())]
    statuses = [tbl.item(r, 5).text() for r in range(tbl.rowCount())]
    assert "Bending M" in checks
    bending_status = statuses[checks.index("Bending M")]
    assert bending_status.startswith(("PASS", "FAIL"))   # a real verdict, not "N/A"


# ── EC2 minimum reinforcement auto-fill ──────────────────────────────────────

def test_min_reinforcement_area_formula():
    from ui_qt.section_library import min_reinforcement_area
    b, d, fck, fyk = 0.3, 0.35, 30e6, 500e6
    fctm = 0.30 * (fck / 1e6) ** (2.0 / 3.0) * 1e6
    expected = max(0.26 * (fctm / fyk) * b * d, 0.0013 * b * d)
    assert min_reinforcement_area(b, d, fck, fyk) == pytest.approx(expected)


def test_min_reinforcement_area_zero_for_missing_geometry():
    from ui_qt.section_library import min_reinforcement_area
    assert min_reinforcement_area(0.0, 0.35, 30e6, 500e6) == 0.0
    assert min_reinforcement_area(0.3, 0.0, 30e6, 500e6) == 0.0


def test_beam_wizard_concrete_auto_fills_min_reinforcement_and_flags_it():
    s = beam_wizard(
        spans=[6.0], support_types=["PIN", "ROLLER"], E=32e9, A=0.15, I=0.003125,
        fy=30e6, b_sec=0.3, h_sec=0.5,
    )
    m = s.members[0]
    assert m.As_tension > 0.0
    assert m.reinforcement_estimated is True


def test_portal_wizard_concrete_auto_fills_min_reinforcement_for_both_roles():
    s = portal_wizard(
        span=10.0, height=5.0, fixed_base=True,
        E_col=32e9, A_col=0.16, I_col=0.16 * 0.4 ** 3 / 12,
        E_raf=32e9, A_raf=0.18, I_raf=0.18 * 0.6 ** 3 / 12,
        col_fy=30e6, raf_fy=30e6,
        col_b_sec=0.4, col_h_sec=0.4, raf_b_sec=0.3, raf_h_sec=0.6,
        density=2500.0,
    )
    assert all(m.As_tension > 0.0 for m in s.members)
    assert all(m.reinforcement_estimated is True for m in s.members)


def test_frame_wizard_concrete_auto_fills_min_reinforcement():
    s = frame_wizard(2, 2, 6.0, 3.0, fixed_base=True,
                     E=32e9, A=0.16, I=0.16 * 0.4 ** 3 / 12,
                     fy=30e6, b_sec=0.4, h_sec=0.4, density=2500.0)
    assert all(m.As_tension > 0.0 for m in s.members)
    assert all(m.reinforcement_estimated is True for m in s.members)


def test_steel_wizard_members_never_get_reinforcement_flag():
    s = beam_wizard(spans=[6.0], support_types=["PIN", "ROLLER"], E=210e9, A=0.005381, I=8.356e-5)
    assert all(m.As_tension == 0.0 for m in s.members)
    assert all(m.reinforcement_estimated is False for m in s.members)
