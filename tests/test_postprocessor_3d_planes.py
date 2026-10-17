"""3D member results use ONE bending plane per element, and diagrams close to zero."""

import math

import numpy as np
import pytest

import sdk as sl
from solver.postprocessor import ElementResult, Postprocessor

pytestmark = pytest.mark.filterwarnings("ignore:No loads applied")

RHO, G, L, A = 7850.0, 9.81, 4.0, 0.01


def test_both_ends_report_the_same_plane():
    """My dominates at end i, Mz at end j: M_i and M_j must still share a plane."""
    f = np.zeros(12)
    f[4], f[5] = 9.0, 1.0       # end i: My 9, Mz 1
    f[10], f[11] = 2.0, 5.0     # end j: My 2, Mz 5   (Mz is larger at j)
    f[2], f[8] = 3.0, 4.0       # Vz_i, Vz_j
    f[1], f[7] = 0.5, 0.6       # Vy_i, Vy_j
    r = ElementResult(element_id=0, end_forces=f)
    # Largest bending anywhere is My (9 > 5): both ends must come from My / Vz.
    assert (r.M_i, r.M_j) == (9.0, 2.0)
    assert (r.V_i, r.V_j) == (3.0, 4.0)


def test_ties_go_to_the_strong_plane():
    f = np.zeros(12)
    f[4], f[5], f[10], f[11] = 3.0, 3.0, 3.0, 3.0
    f[1], f[2] = 7.0, 8.0
    r = ElementResult(element_id=0, end_forces=f)
    assert r.V_i == 7.0   # Vy, not Vz


@pytest.mark.parametrize("beta", [0.0, math.pi / 2])
def test_cantilever_diagram_closes_in_either_bending_plane(beta):
    """Self-weight on a cantilever: M(root) = -wL²/2 and M = V = 0 at the free tip,
    whether gravity bends the member about its strong (beta=0) or weak axis."""
    m = sl.Model(mode_3d=True)
    a, b = m.add_node(0, 0, 10), m.add_node(L, 0, 10)
    m.fixed(a)
    mid = m.add_member(a, b, E=210e9, A=A, I=2e-5, I_y=5e-6, J=1e-6, n_sub=8)
    md = m._state.get_member(mid)
    md.density, md.beta_angle = RHO, beta
    m._state.set_self_weight_case(m._state.load_cases[0].id)
    result = m.solve()
    pp = Postprocessor(result._cache["model"].elements,
                       result._cache["model"].element_loads,
                       result._cache["displacements"])
    pieces = pp.sfd_bmd(10)
    moments = np.concatenate([p.M for p in pieces])
    shears = np.concatenate([p.V for p in pieces])
    w = RHO * A * G
    assert abs(moments[0]) == pytest.approx(w * L**2 / 2, rel=1e-6)
    assert moments[-1] == pytest.approx(0.0, abs=1e-6)
    assert shears[-1] == pytest.approx(0.0, abs=1e-6)
