"""Golden-value (characterization) tests.

``tests/golden/golden.json`` freezes displacements, reactions and member end forces
of 8 models solved through the app's own pipeline. Any engine refactor (sparse
solver, DOF handling, element interface...) must leave these numbers unchanged.

Every model is also checked against an independent closed-form / equilibrium
answer, so the frozen numbers are known-good, not merely known.
"""

import json
import math
from pathlib import Path

import numpy as np
import pytest

from tests.golden.fingerprint import fingerprint
from tests.golden.models import MODELS, RHO

GOLDEN = json.loads((Path(__file__).parent / "golden" / "golden.json").read_text("utf-8"))
G_ACC = 9.81


@pytest.fixture(scope="module")
def solved() -> dict:
    return {name: fingerprint(build()) for name, build in MODELS.items()}


@pytest.mark.parametrize("name", sorted(MODELS))
def test_matches_frozen_numbers(solved, name):
    for key in ("displacements", "reactions", "member_end_forces"):
        actual, frozen = np.array(solved[name][key]), np.array(GOLDEN[name][key])
        assert actual.shape == frozen.shape, f"{name}.{key} changed shape"
        scale = max(float(np.abs(frozen).max()), 1e-12)
        np.testing.assert_allclose(actual, frozen, rtol=1e-6, atol=1e-8 * scale,
                                   err_msg=f"{name}.{key} drifted from golden")


# ── independent checks that the frozen numbers are physically right ───────────

def _sum(solved, name, comp) -> float:
    return float(np.array(solved[name]["reactions"])[:, comp].sum())


def test_continuous_beam_equilibrium(solved):
    assert _sum(solved, "continuous_beam_plane", 2) == pytest.approx(20e3 * 18 + 50e3, rel=1e-9)
    assert _sum(solved, "continuous_beam_plane", 0) == pytest.approx(0.0, abs=1e-6)


def test_portal_frame_equilibrium(solved):
    assert _sum(solved, "portal_frame_plane", 0) == pytest.approx(-15e3, rel=1e-9)
    assert _sum(solved, "portal_frame_plane", 2) == pytest.approx(8e3 * 6 + 40e3, rel=1e-9)


def test_warren_truss_reactions_and_joint_equilibrium(solved):
    r = np.array(solved["warren_truss_plane"]["reactions"])
    assert r[0, 2] == pytest.approx(15e3, rel=1e-9) and r[4, 2] == pytest.approx(15e3, rel=1e-9)
    # Bar forces are axial only: shear, torsion and bending at both ends must be zero.
    f = np.array(solved["warren_truss_plane"]["member_end_forces"])
    assert np.abs(f[:, [1, 2, 3, 4, 5, 7, 8, 9, 10, 11]]).max() < 1e-3


def test_spring_beam_total_reaction(solved):
    assert _sum(solved, "spring_supported_beam_plane", 2) == pytest.approx(12e3 * 10 + 30e3, rel=1e-9)


def test_3d_cantilever_reactions_and_torsion(solved):
    s = solved["cantilever_3d_torsion"]
    root = np.array(s["reactions"])[0]
    assert root[:3] == pytest.approx([0.0, -2e3, 3e3], abs=1e-6)
    # Moment about the root: r × F + applied Mx, with r = (4, 0, 0), F = (0, 2e3, -3e3)
    assert root[3:] == pytest.approx([-1e3, -12e3, -8e3], abs=1e-3)
    twist = np.array(s["displacements"])[1][3]                 # θx at the tip
    assert twist == pytest.approx(1e3 * 4 / ((210e9 / 2.6) * 3e-6), rel=1e-3)


def test_space_frame_force_equilibrium(solved):
    length = 4 * 4.0 * 0.012 + (6 + 5 + 6 + 5) * 0.012 + math.sqrt(36 + 25 + 16) * 0.003
    self_weight = RHO * G_ACC * length
    applied_down = 15e3 * 6 + 30e3 + 25e3 + 30e3               # qz UDL, partial, point, nodal Fz
    assert _sum(solved, "space_frame_3d", 0) == pytest.approx(-(6e3 * 5 + 10e3), rel=1e-9)
    assert _sum(solved, "space_frame_3d", 1) == pytest.approx(-(-6e3 + 12e3), rel=1e-9)
    assert _sum(solved, "space_frame_3d", 2) == pytest.approx(
        applied_down + self_weight, rel=1e-9)


def test_released_rafter_end_carries_no_moment(solved):
    f = np.array(solved["pin_release_frame_3d"]["member_end_forces"])[2]   # the rafter
    assert abs(f[10]) < 1e-3 and abs(f[11]) < 1e-3              # M_y_j, M_z_j at the pin
    r = solved["pin_release_frame_3d"]["reactions"]
    assert sum(row[0] for row in r) == pytest.approx(-7e3, rel=1e-9)
    assert sum(row[2] for row in r) == pytest.approx(9e3 * 6, rel=1e-9)


def test_tower_reactions_balance_weight_and_loads(solved):
    state = MODELS["l8_tower"]()._state
    weight = sum(m.density * m.A * G_ACC * math.dist(
        (state.get_node(m.node_i).x, state.get_node(m.node_i).y, state.get_node(m.node_i).z),
        (state.get_node(m.node_j).x, state.get_node(m.node_j).y, state.get_node(m.node_j).z))
        for m in state.members)
    n_tips = sum(1 for nl in state.load_cases[0].node_loads.values() if nl.fy == 4e3)
    assert n_tips == 24            # top- and bottom-chord end of 3 arms x 2 sides x 2 planes
    assert _sum(solved, "l8_tower", 0) == pytest.approx(0.0, abs=1e-3)
    assert _sum(solved, "l8_tower", 1) == pytest.approx(-4e3 * n_tips, rel=1e-9)
    assert _sum(solved, "l8_tower", 2) == pytest.approx(weight + 6e3 * n_tips, rel=1e-9)
