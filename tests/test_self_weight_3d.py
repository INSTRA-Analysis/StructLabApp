"""Self-weight in 3D (Z-up) models: gravity acts along -Z for bars and beams.

Regression for the bug where the 2D-only code applied gravity along global Y.
"""

import math

import numpy as np
import pytest

import sdk as sl

pytestmark = pytest.mark.filterwarnings("ignore:No loads applied")

E = 210e9
RHO = 7850.0
G = 9.81


def _solve(model: sl.Model):
    model._state.set_self_weight_case(model._state.load_cases[0].id)
    result = model.solve()
    reactions = result._cache["reactions"].reshape(-1, 6)
    return result, reactions


def _member(model: sl.Model, i: int, j: int, A: float, I: float, kind: str,
            I_y: float | None = None, beta: float = 0.0) -> int:
    mid = model.add_member(i, j, E=E, A=A, I=I, I_y=I_y, J=1e-6,
                           n_sub=10, element_type=kind)
    md = model._state.get_member(mid)
    md.density, md.beta_angle = RHO, beta
    return mid


@pytest.mark.parametrize("beta, I_bend", [(0.0, 2e-5), (math.pi / 2, 5e-6)])
def test_horizontal_cantilever_deflection_uses_correct_axis(beta, I_bend):
    """Tip sag = wL⁴/(8EI) about the axis that actually resists gravity."""
    L, A = 4.0, 0.01
    m = sl.Model(mode_3d=True)
    a, b = m.add_node(0, 0, 10), m.add_node(L, 0, 10)   # z != 0 -> 3D engine
    m.fixed(a)
    _member(m, a, b, A, I=2e-5, kind="BEAM", I_y=5e-6, beta=beta)
    result, _ = _solve(m)
    w = RHO * A * G
    assert result.displacement(b)[2] == pytest.approx(-w * L**4 / (8 * E * I_bend), rel=1e-3)
    assert abs(result.displacement(b)[1]) < 1e-9


def test_vertical_column_carries_its_weight_axially():
    H, A = 3.0, 0.02
    m = sl.Model(mode_3d=True)
    a, b = m.add_node(0, 0, 0), m.add_node(0, 0, H)
    m.fixed(a)
    _member(m, a, b, A, I=1e-4, kind="BEAM")
    _, reactions = _solve(m)
    assert reactions[a][2] == pytest.approx(RHO * A * G * H, rel=1e-9)
    assert abs(reactions[a][0]) < 1e-6 and abs(reactions[a][1]) < 1e-6


def test_bar_weight_goes_to_joints_vertically():
    """Inclined bar: no sideways reaction from self-weight, total = weight."""
    A = 0.005
    m = sl.Model(mode_3d=True)
    a, b = m.add_node(0, 0, 0), m.add_node(3, 4, 5)
    m.pin(a)
    m.pin(b)
    _member(m, a, b, A, I=1e-6, kind="BAR")
    _, reactions = _solve(m)
    weight = RHO * A * G * math.sqrt(9 + 16 + 25)
    assert reactions[:, 2].sum() == pytest.approx(weight, rel=1e-9)


def test_mixed_inclined_frame_force_and_moment_equilibrium():
    """Arbitrarily oriented beams + bars: reactions balance weight and its moment."""
    pts = [(0, 0, 0), (6, 0, 0), (6, 5, 0), (0, 5, 0),
           (1, 1, 4), (5, 1, 4.5), (5, 4, 5), (1, 4, 4)]
    m = sl.Model(mode_3d=True)
    ids = [m.add_node(*p) for p in pts]
    for i in ids[:4]:
        m.fixed(i)
    members = [(0, 4, "BEAM"), (1, 5, "BEAM"), (2, 6, "BEAM"), (3, 7, "BEAM"),
               (4, 5, "BEAM"), (5, 6, "BEAM"), (6, 7, "BEAM"), (7, 4, "BEAM"),
               (4, 6, "BAR"), (5, 7, "BAR")]
    weights = []
    for i, j, kind in members:
        A = 0.004 if kind == "BAR" else 0.012
        _member(m, ids[i], ids[j], A, I=4e-5, kind=kind, I_y=2e-5)
        p, q = np.array(pts[i], float), np.array(pts[j], float)
        weights.append((RHO * A * G * np.linalg.norm(q - p), (p + q) / 2))

    _, reactions = _solve(m)
    total = sum(w for w, _ in weights)
    assert reactions[:, 0].sum() == pytest.approx(0.0, abs=1e-6)
    assert reactions[:, 1].sum() == pytest.approx(0.0, abs=1e-6)
    assert reactions[:, 2].sum() == pytest.approx(total, rel=1e-9)

    resisting = np.zeros(3)
    for i, p in zip(ids[:4], pts[:4]):
        resisting += reactions[i][3:] + np.cross(p, reactions[i][:3])
    applied = sum(np.cross(c, [0.0, 0.0, -w]) for w, c in weights)
    assert resisting + applied == pytest.approx(np.zeros(3), abs=1e-3)
