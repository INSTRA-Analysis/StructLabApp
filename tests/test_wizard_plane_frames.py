"""Wizards build plane frames in the XZ plane.  Their loads all act in the plane, so the
plane-frame results equal what the same model gave as a space frame before."""

import numpy as np
import pytest

from ui_qt import presets
from ui_qt.model_builder import build_model
from ui_qt.solve_actions import lock_force_note, solve_engine, validate_model

IPE = (210e9, 5.38e-3, 8.356e-5)

WIZARDS = {
    "beam": lambda: presets.beam_wizard([5.0, 6.0, 5.0], ["PIN", "ROLLER", "ROLLER", "ROLLER"],
                                        *IPE, udl_g=8e3, udl_q=5e3, point_q=20e3),
    "portal pinned": lambda: presets.portal_wizard(12.0, 5.0, False, *IPE, *IPE,
                                                   udl_g=6e3, udl_q=4e3, wind_h=10e3),
    "portal fixed": lambda: presets.portal_wizard(12.0, 5.0, True, *IPE, *IPE, udl_g=6e3, wind_h=10e3),
    "truss": lambda: presets.truss_wizard("Pratt", 6, 18.0, 2.0, IPE, (210e9, 2e-3, 1e-6),
                                          panel_load=15e3),
    "frame": lambda: _loaded(presets.frame_wizard(2, 3, 6.0, 3.5, fixed_base=True)),
}


def _loaded(s):
    """The frame wizard adds no loads: give it wind at each floor and gravity on every node."""
    from ui_qt.model_state import NodeLoad
    for n in s.nodes:
        if n.z > 0:
            s.active_case.set_node_load(n.id, NodeLoad(fx=5e3 if n.x == 0 else 0.0, fz=-20e3))
    return s


@pytest.mark.parametrize("name", list(WIZARDS))
def test_wizard_builds_a_valid_plane_frame(name):
    s = WIZARDS[name]()
    assert (s.analysis_mode, s.analysis_type) == ("3D", "plane_xz")
    assert all(n.y == 0.0 for n in s.nodes)
    errors, warns = validate_model(s)
    assert not errors and not any("Plane frame" in w for w in warns)


@pytest.mark.parametrize("name", list(WIZARDS))
def test_plane_frame_results_equal_the_space_frame_ones(name):
    s = WIZARDS[name]()
    loaded = [lc for lc in s.load_cases if lc.node_loads or lc.member_loads]
    assert loaded                                                      # something to compare
    for lc in loaded:
        plane = solve_engine(*build_model(s, lc), s)
        assert lock_force_note(plane) is None                          # nothing out of plane
        s.analysis_type = "space"
        space = solve_engine(*build_model(s, lc), s)
        s.analysis_type = "plane_xz"
        scale_u = max(np.abs(space["displacements"]).max(), 1e-12)
        scale_r = max(np.abs(space["reactions"]).max(), 1.0)
        np.testing.assert_allclose(plane["displacements"], space["displacements"],
                                   atol=1e-8 * scale_u, rtol=0)
        np.testing.assert_allclose(plane["reactions"], space["reactions"], atol=1e-8 * scale_r, rtol=0)
