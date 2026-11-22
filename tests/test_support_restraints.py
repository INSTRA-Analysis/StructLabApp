"""Per-axis support restraints: six flags per node, one table for 2D and 3D.

The presets must reproduce the solver's former per-mode tables exactly (old models solve as
before), the flags must follow the axes through a 2D <-> 3D switch, and the file format must
carry them (old files load from the preset name).
"""

import numpy as np
import pytest

from core.support import Support, SupportType as CoreType
from ui_qt.model_builder import _RIGID_MAP, build_model
from ui_qt.model_state import (
    SUPPORT_PRESETS, ModelState, NodeData, NodeLoad, SupportType, classify_support, node_from_dict,
)
from ui_qt.solve_actions import solve_engine

PRESETS = [p for p in SUPPORT_PRESETS]


@pytest.mark.parametrize("preset", PRESETS)
@pytest.mark.parametrize("dpn", [3, 6])
def test_presets_reproduce_the_former_solver_tables(preset, dpn):
    old = Support(node_id=4, support_type=_RIGID_MAP[preset]).restrained_dofs(dpn)
    new = Support(node_id=4, support_type=CoreType.FREE,
                  restrained=SUPPORT_PRESETS[preset]).restrained_dofs(dpn)
    assert new == old


@pytest.mark.parametrize("preset", [p for p in PRESETS if p is not SupportType.FREE])
def test_assigning_a_preset_reads_back_the_same_preset(preset):
    n = NodeData(id=0, x=0, y=0)
    n.support_type = preset
    assert n.support_type is preset
    assert n.restraints == SUPPORT_PRESETS[preset]


def test_any_other_combination_is_custom():
    n = NodeData(id=0, x=0, y=0)
    n.set_restraints((False, True, False, False, False, True))
    assert n.support_type is SupportType.CUSTOM
    n.support_type = SupportType.CUSTOM                     # keeps the flags
    assert n.restraints == (False, True, False, False, False, True)
    with pytest.raises(ValueError):
        n.set_restraints((True, True))


def test_rigid_presets_clear_springs_spring_preset_keeps_them():
    n = NodeData(id=0, x=0, y=0)
    n.support_type = SupportType.SPRING
    assert n.support_type is SupportType.SPRING              # still a spring before any k is typed
    n.spring_ky = 2e6
    n.support_type = SupportType.PIN
    assert n.spring_ky == 0.0 and n.support_type is SupportType.PIN
    assert classify_support((False,) * 6, has_springs=True) is SupportType.SPRING


# ── the 2D <-> 3D switch ─────────────────────────────────────────────────────

@pytest.mark.parametrize("before, after", [
    (SupportType.ROLLER_Y, SupportType.ROLLER_Z),     # 2D wall roller stays free vertically
    (SupportType.ROLLER_Z, SupportType.ROLLER_Y),
    (SupportType.ROLLER, SupportType.ROLLER),
    (SupportType.PIN, SupportType.PIN),
    (SupportType.FIXED, SupportType.FIXED),
])
def test_supports_keep_their_meaning_through_swap_yz(before, after):
    s = ModelState()
    n = s.add_node(1.0, 2.0, 0.0)
    n.support_type = before
    s.swap_yz()
    assert n.support_type is after
    s.swap_yz()
    assert n.support_type is before                    # the swap is its own inverse


def test_custom_rotation_follows_the_axes():
    s = ModelState()
    n = s.add_node(0, 0, 0)
    n.set_restraints((False, False, False, False, False, True))   # 2D: theta_z only
    s.swap_yz()
    assert n.restraints == (False, False, False, False, True, False)   # 3D: theta_y


def test_wall_roller_frame_deflects_the_same_in_2d_and_after_switching_to_3d():
    """L-frame: fixed column, beam ending on a wall roller (holds X, free vertically), tip load.
    Before per-axis restraints the switch to 3D turned the roller into a vertical prop."""
    E, A, I, P = 210e9, 8.446e-3, 2.313e-4, 10_000.0
    s = ModelState()
    s.analysis_mode = "2D"
    base, knee, tip = s.add_node(0, 0, 0), s.add_node(0, 3, 0), s.add_node(6, 3, 0)
    base.support_type, tip.support_type = SupportType.FIXED, SupportType.ROLLER_Y
    for a, b in ((base, knee), (knee, tip)):
        m = s.add_member(a.id, b.id)
        m.E, m.A, m.I, m.I_y, m.J = E, A, I, I, 1e-5
    s.active_case.set_node_load(tip.id, NodeLoad(fy=-P))

    cache = solve_engine(*build_model(s, s.active_case), s)
    v2d = cache["displacements"][tip.id * 3 + 1]
    assert v2d < -1e-4                                   # free vertically: it deflects

    s.swap_yz()
    s.analysis_mode = "3D"
    model, mm = build_model(s, s.active_case)
    assert model.dofs_per_node == 6
    cache = solve_engine(model, mm, s)
    assert cache["displacements"][tip.id * 6 + 2] == pytest.approx(v2d, rel=1e-6)


# ── files ────────────────────────────────────────────────────────────────────

def test_custom_restraints_round_trip_through_the_file_format():
    s = ModelState()
    n = s.add_node(0, 0, 0)
    n.set_restraints((True, False, True, False, True, False))
    n.spring_ky = 5e5                                   # a spring on a free DOF of a custom support
    back = ModelState.from_dict(s.to_dict()).nodes[0]
    assert back.restraints == n.restraints and back.spring_ky == 5e5
    assert back.support_type is SupportType.CUSTOM


def test_old_files_load_from_the_preset_and_drop_springs_the_solver_ignored():
    old = {"id": 0, "x": 0, "y": 0, "support": "PIN", "spring_ktheta": 3e5}
    n = node_from_dict(old)
    assert n.restraints == SUPPORT_PRESETS[SupportType.PIN]
    assert n.spring_ktheta == 0.0 and n.support_type is SupportType.PIN
    spring = node_from_dict({"id": 1, "x": 0, "y": 0, "support": "SPRING", "spring_ky": 2e6})
    assert spring.support_type is SupportType.SPRING and spring.spring_ky == 2e6
