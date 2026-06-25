"""Tests for ui_qt.csv_import — sectioned CSV → ModelState."""

from __future__ import annotations

from pathlib import Path

import pytest

from ui_qt.csv_import import parse_structlab_csv
from ui_qt.model_state import ElementType, SupportType

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
TOWER_CSV = EXAMPLES / "transmission_tower_3d.csv"


# ── the worked example ────────────────────────────────────────────────────────

def test_tower_counts_and_properties():
    state, warnings = parse_structlab_csv(TOWER_CSV)
    assert warnings == []
    assert len(state.nodes) == 85
    assert len(state.members) == 318
    assert state.mode_3d is True

    # every member is a pin-jointed bar with the toolbox section
    assert all(m.element_type is ElementType.BAR for m in state.members)
    assert all(m.A == pytest.approx(0.005) for m in state.members)
    assert all(m.E == pytest.approx(2e11) for m in state.members)
    # self-weight gamma 78000 N/m3 -> density kg/m3 (within rounding)
    assert all(7900 < m.density < 8000 for m in state.members)

    # group labels survived the round-trip from the generator
    groups = {m.group for m in state.members}
    assert {"Leg", "Diagonal", "Horizontal"} <= groups


def test_tower_supports_and_loads():
    state, _ = parse_structlab_csv(TOWER_CSV)
    fixed = [n for n in state.nodes if n.support_type is SupportType.FIXED]
    assert len(fixed) == 4
    loaded = state.active_case.node_loads
    assert len(loaded) == 12
    # all applied loads are vertical-down in StructLab Z (toolbox Y-up was remapped)
    for load in loaded.values():
        assert load.fz < 0
        assert load.fx == 0 and load.fy == 0


def test_tower_solves_without_singularity():
    """End-to-end: build -> solve. Confirms axis mapping + BAR DOF handling."""
    import numpy as np
    from ui_qt.model_builder import build_model
    from ui_qt.solve_actions import solve_engine

    state, _ = parse_structlab_csv(TOWER_CSV)
    model, member_el_map = build_model(state, state.active_case)
    cache = solve_engine(model, member_el_map, state)

    disp = cache["displacements"]
    assert np.all(np.isfinite(disp))  # no singularity

    # Global vertical equilibrium: sum of Z reactions balances the applied downward
    # load. 3D layout is 6 DOF/node -> Z-translation is every dof with dof % 6 == 2.
    reactions = cache["reactions"]
    react_fz = sum(reactions[d] for d in range(2, len(reactions), 6))
    applied_fz = sum(l.fz for l in state.active_case.node_loads.values())
    assert react_fz == pytest.approx(-applied_fz, rel=1e-6, abs=1.0)


# ── malformed input is tolerated, not fatal ──────────────────────────────────

def _write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "model.csv"
    p.write_text(text, encoding="utf-8")
    return p


def test_unknown_etype_defaults_to_bar_with_warning(tmp_path):
    csv = _write(tmp_path, """\
#NODES
id,x,y,z
1,0,0,0
2,1,0,0
#MEMBERS
id,node_i,node_j,etype,group,E,A,fy,density
1,1,2,wibble,Chord,2e11,0.005,2.75e8,7850
""")
    state, warnings = parse_structlab_csv(csv)
    assert len(state.members) == 1
    assert state.members[0].element_type is ElementType.BAR
    assert any("unknown etype" in w for w in warnings)


def test_member_with_missing_node_is_skipped(tmp_path):
    csv = _write(tmp_path, """\
#NODES
id,x,y,z
1,0,0,0
2,1,0,0
#MEMBERS
id,node_i,node_j,etype,group,E,A,fy,density
1,1,2,bar,Chord,2e11,0.005,2.75e8,7850
2,1,99,bar,Chord,2e11,0.005,2.75e8,7850
""")
    state, warnings = parse_structlab_csv(csv)
    assert len(state.members) == 1
    assert any("missing node" in w for w in warnings)


def test_arbitrary_ids_are_remapped(tmp_path):
    """Non-contiguous CSV ids must still resolve member/support/force references."""
    csv = _write(tmp_path, """\
#NODES
id,x,y,z
100,0,0,0
200,2,0,0
300,1,0,2
#MEMBERS
id,node_i,node_j,etype,group,E,A,fy,density
1,100,300,bar,Diagonal,2e11,0.005,2.75e8,7850
2,300,200,bar,Diagonal,2e11,0.005,2.75e8,7850
#SUPPORTS
node,rx,ry,rz
100,1,1,1
200,1,1,1
#FORCES
node,Fx,Fy,Fz
300,0,0,-5000
""")
    state, warnings = parse_structlab_csv(csv)
    assert warnings == []
    assert len(state.members) == 2
    assert sum(1 for n in state.nodes if n.support_type is SupportType.FIXED) == 2
    assert len(state.active_case.node_loads) == 1


# ── optional beam columns (I / Iy / J) ────────────────────────────────────────

def test_beam_bending_columns_are_read(tmp_path):
    csv = _write(tmp_path, """\
#NODES
id,x,y,z
1,0,0,0
2,6,0,0
#MEMBERS
id,node_i,node_j,etype,group,E,A,I,Iy,J,fy,density
1,1,2,beam,Beam,2.1e11,0.009104,8.091e-5,2.843e-5,9.1e-7,355e6,7850
""")
    state, warnings = parse_structlab_csv(csv)
    assert warnings == []
    m = state.members[0]
    assert m.element_type is ElementType.BEAM
    assert m.I == pytest.approx(8.091e-5)
    assert m.I_y == pytest.approx(2.843e-5)
    assert m.J == pytest.approx(9.1e-7)


def test_truss_without_bending_columns_keeps_defaults(tmp_path):
    """A pure-truss CSV (no I/Iy/J columns) must still parse without error."""
    csv = _write(tmp_path, """\
#NODES
id,x,y,z
1,0,0,0
2,2,0,0
#MEMBERS
id,node_i,node_j,etype,group,E,A,fy,density
1,1,2,bar,Chord,2.1e11,0.005,355e6,7850
""")
    state, warnings = parse_structlab_csv(csv)
    assert warnings == []
    assert state.members[0].element_type is ElementType.BAR


# ── every shipped example parses cleanly and solves ───────────────────────────

@pytest.mark.parametrize("filename", [
    "transmission_tower_3d.csv",
    "pratt_truss_2d.csv",
    "space_frame_roof_3d.csv",
    "portal_frame_3d.csv",
    "multibay_frame_2d.csv",
])
def test_example_parses_and_solves(filename):
    import numpy as np
    from ui_qt.model_builder import build_model
    from ui_qt.solve_actions import solve_engine, validate_model

    state, warnings = parse_structlab_csv(EXAMPLES / filename)
    assert warnings == [], f"{filename}: {warnings}"
    errors, _ = validate_model(state)
    assert errors == [], f"{filename}: {errors}"
    model, member_el_map = build_model(state, state.active_case)
    cache = solve_engine(model, member_el_map, state)
    assert np.all(np.isfinite(cache["displacements"])), f"{filename}: singular"
