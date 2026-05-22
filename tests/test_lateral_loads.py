"""Tests: distributed lateral loads (global X direction, qx_start / qx_end).

Geometry for all cases
----------------------
  Vertical cantilever column: node 0 at (0, 0) FIXED, node 1 at (0, H) FREE.
  Column has elastic modulus E, second moment of area I, cross-section area A.

Case A — uniform lateral UDL (qx_start = qx_end = w)
  Exact analytical (standard cantilever UDL):
    tip deflection  δ = w·H⁴ / (8EI)
    base reaction   Rx_base = −w·H
    base moment     M_base  = +w·H² / 2  (CCW, positive)

Case B — linearly varying load, maximum at base, zero at tip
  (qx_start = w, qx_end = 0)
  Exact analytical (triangular load decreasing from base):
    tip deflection  δ = w·H⁴ / (30EI)
    total X force   = w·H / 2

Case C — linearly varying load, zero at base, maximum at tip
  (qx_start = 0, qx_end = w)
  Exact analytical (load increasing toward tip — realistic wind profile):
    tip deflection  δ = 11·w·H⁴ / (120EI)
    total X force   = w·H / 2

Convergence property
---------------------
The nodal-lumping method (trapezoidal tributary areas) converges monotonically
to the exact solution as n_sub increases.  Tests verify that the discretisation
error shrinks as n_sub is increased from 1 → 5 → 20 → 50.
"""

import math
import pytest

from ui_qt.model_state import (
    ModelState, SupportType, ElementType, MemberLoad,
)
from ui_qt.model_builder import build_model
from solver.assembler import Assembler
from solver.linear_solver import LinearSolver

# ── shared geometry ────────────────────────────────────────────────────────────

H   = 4.0       # m  — column height
E   = 200e9     # Pa — elastic modulus
I   = 50e-6     # m⁴ — second moment of area
A   = 10e-3     # m²
w   = 10_000.0  # N/m — lateral load magnitude


def _build_cantilever(qx_start: float, qx_end: float, n_sub: int) -> tuple:
    """Return (displacements, reactions) for the cantilever column."""
    state = ModelState()

    n0 = state.add_node(0.0, 0.0)
    n1 = state.add_node(0.0, H)

    n0.support_type = SupportType.FIXED

    m = state.add_member(n0.id, n1.id)
    m.E     = E
    m.A     = A
    m.I     = I
    m.n_sub = n_sub

    lc = state.active_case
    lc.set_member_load(m.id, MemberLoad(
        qx_start=qx_start,
        qx_end=qx_end,
    ))

    model, _ = build_model(state, lc)
    asm = Assembler(model)
    K = asm.global_stiffness_matrix(model.elements)
    F = asm.global_force_vector(model.elements)
    result = LinearSolver(model).solve(K, F)
    return result.displacements, result.reactions


# ── Case A: uniform qx ────────────────────────────────────────────────────────

class TestUniformLateralUDL:

    def test_global_equilibrium_x(self):
        """Sum of all X reactions must equal -total applied load, exactly."""
        disps, reactions = _build_cantilever(w, w, n_sub=1)
        # Reaction at node 0: reactions[0] = Rx
        total_applied = w * H
        assert abs(reactions[0] + total_applied) < 1e-6 * total_applied, (
            f"ΣFx not zero: Rx={reactions[0]:.2f} N, applied={total_applied:.2f} N"
        )

    def test_global_equilibrium_y(self):
        """No vertical load → Ry at base is zero."""
        disps, reactions = _build_cantilever(w, w, n_sub=5)
        assert abs(reactions[1]) < 1.0, f"Ry={reactions[1]:.2e} N (expected 0)"

    def test_tip_deflection_convergence(self):
        """Tip deflection converges to wH⁴/(8EI) as n_sub increases."""
        exact = w * H**4 / (8 * E * I)
        errors = {}
        for n_sub in (1, 5, 20, 50):
            disps, _ = _build_cantilever(w, w, n_sub=n_sub)
            # Node 1 = index 1 in the original node list → DOF 3 (dx), 4 (dy), 5 (θ)
            # But with sub-division, node 1 keeps its original id.
            dx_tip = disps[1 * 3]   # node id=1, dx component
            errors[n_sub] = abs(dx_tip - exact) / exact

        # Error must decrease with refinement
        assert errors[5]  < errors[1],  f"No improvement 1→5: {errors}"
        assert errors[20] < errors[5],  f"No improvement 5→20: {errors}"
        assert errors[50] < errors[20], f"No improvement 20→50: {errors}"

        # n_sub=50 must be within 0.5% of exact
        assert errors[50] < 0.005, (
            f"n_sub=50 error={errors[50]*100:.3f}% > 0.5%  "
            f"(got {disps[3]:.6f} m, exact {exact:.6f} m)"
        )

    def test_base_moment_converges(self):
        """Fixed-end moment at base converges to wH²/2 (CCW positive)."""
        exact_M = w * H**2 / 2
        disps, reactions = _build_cantilever(w, w, n_sub=50)
        M_base = reactions[2]   # node 0, moment DOF
        assert abs(abs(M_base) - exact_M) / exact_M < 0.01, (
            f"|M_base|={abs(M_base):.1f} N·m, exact={exact_M:.1f} N·m"
        )


# ── Case B: triangular load, max at base, zero at tip ─────────────────────────

class TestTriangularLoadBaseToTip:

    def test_global_equilibrium_x(self):
        """Total X force = w·H/2."""
        disps, reactions = _build_cantilever(w, 0.0, n_sub=1)
        total_applied = w * H / 2
        assert abs(reactions[0] + total_applied) < 1e-6 * total_applied, (
            f"ΣFx: Rx={reactions[0]:.2f}, applied={total_applied:.2f}"
        )

    def test_tip_deflection_converges(self):
        """Tip deflection converges to wH⁴/(30EI)."""
        exact = w * H**4 / (30 * E * I)
        errors = {}
        for n_sub in (5, 20, 50):
            disps, _ = _build_cantilever(w, 0.0, n_sub=n_sub)
            dx_tip = disps[1 * 3]
            errors[n_sub] = abs(dx_tip - exact) / exact

        assert errors[20] < errors[5],  f"No improvement 5→20: {errors}"
        assert errors[50] < errors[20], f"No improvement 20→50: {errors}"
        assert errors[50] < 0.01, (
            f"n_sub=50 error={errors[50]*100:.3f}% > 1%"
        )


# ── Case C: triangular load, zero at base, max at tip ─────────────────────────

class TestTriangularLoadTipLoaded:

    def test_global_equilibrium_x(self):
        """Total X force = w·H/2."""
        disps, reactions = _build_cantilever(0.0, w, n_sub=1)
        total_applied = w * H / 2
        assert abs(reactions[0] + total_applied) < 1e-6 * total_applied

    def test_tip_deflection_converges(self):
        """Tip deflection converges to 11wH⁴/(120EI)."""
        exact = 11 * w * H**4 / (120 * E * I)
        errors = {}
        for n_sub in (5, 20, 50):
            disps, _ = _build_cantilever(0.0, w, n_sub=n_sub)
            dx_tip = disps[1 * 3]
            errors[n_sub] = abs(dx_tip - exact) / exact

        assert errors[20] < errors[5],  f"No improvement 5→20: {errors}"
        assert errors[50] < errors[20], f"No improvement 20→50: {errors}"
        assert errors[50] < 0.01, (
            f"n_sub=50 error={errors[50]*100:.3f}% > 1%"
        )


# ── Serialisation round-trip ───────────────────────────────────────────────────

class TestLateralLoadSerialisation:

    def test_roundtrip_via_model_state_dict(self):
        """qx_start/qx_end survive to_dict() → from_dict() unchanged."""
        from ui_qt.model_state import LoadCase
        state = ModelState()
        n0 = state.add_node(0.0, 0.0)
        n1 = state.add_node(0.0, H)
        m = state.add_member(n0.id, n1.id)
        state.active_case.set_member_load(m.id, MemberLoad(
            w_start=5e3, w_end=5e3,
            qx_start=2e3, qx_end=8e3,
        ))

        d = state.to_dict()
        state2 = ModelState.from_dict(d)

        ml = state2.active_case.get_member_load(m.id)
        assert ml.qx_start == 2e3, f"qx_start={ml.qx_start}"
        assert ml.qx_end   == 8e3, f"qx_end={ml.qx_end}"
        assert ml.w_start  == 5e3, f"w_start (unchanged)={ml.w_start}"

    def test_old_slab_backward_compat(self):
        """Dict without qx_* keys deserialises to qx=0 (old .slab files)."""
        from ui_qt.model_state import LoadCase
        d = {
            "id": 0, "name": "Dead load", "category": "G",
            "include_self_weight": False,
            "node_loads": {},
            "member_loads": {
                "0": {"w_start": 3000.0, "w_end": 3000.0, "point_loads": []}
            },
        }
        lc = LoadCase.from_dict(d)
        ml = lc.get_member_load(0)
        assert ml.qx_start == 0.0
        assert ml.qx_end   == 0.0
        assert ml.w_start  == 3000.0

    def test_is_zero_with_only_qx(self):
        """MemberLoad with only qx set is not considered zero."""
        ml = MemberLoad(qx_start=1e3)
        assert not ml.is_zero()

    def test_is_zero_when_all_zero(self):
        """Default MemberLoad is zero."""
        assert MemberLoad().is_zero()


# ── Combination merge includes qx ─────────────────────────────────────────────

class TestLateralLoadInCombination:

    def test_combination_factors_qx(self):
        """qx is correctly scaled and merged when building a load combination."""
        from ui_qt.model_state import LoadCombination
        from ui_qt.model_builder import build_model_combined

        state = ModelState()
        n0 = state.add_node(0.0, 0.0);  n0.support_type = SupportType.FIXED
        n1 = state.add_node(0.0, H)
        m  = state.add_member(n0.id, n1.id)
        m.E = E;  m.A = A;  m.I = I;  m.n_sub = 20

        # Wind case: qx = w
        wind_lc = state.add_load_case("Wind", category="W")
        wind_lc.set_member_load(m.id, MemberLoad(qx_start=w, qx_end=w))

        combo = LoadCombination(id=0, name="1.0W", limit_state="SLS")
        combo.factors = {wind_lc.id: 1.0}

        model, _ = build_model_combined(state, combo)
        asm = Assembler(model)
        K = asm.global_stiffness_matrix(model.elements)
        F = asm.global_force_vector(model.elements)
        result = LinearSolver(model).solve(K, F)

        # Equilibrium check: Rx = −w·H regardless of factor = 1.0
        total_applied = w * H
        assert abs(result.reactions[0] + total_applied) < 1e-5 * total_applied

    def test_combination_factor_scales_qx(self):
        """Factored combo (1.5W) doubles deflection compared to 1.0W (linearly elastic)."""
        from ui_qt.model_state import LoadCombination
        from ui_qt.model_builder import build_model_combined

        def _solve_combo(factor):
            state = ModelState()
            n0 = state.add_node(0.0, 0.0);  n0.support_type = SupportType.FIXED
            n1 = state.add_node(0.0, H)
            m  = state.add_member(n0.id, n1.id)
            m.E = E;  m.A = A;  m.I = I;  m.n_sub = 20

            wind_lc = state.add_load_case("Wind", category="W")
            wind_lc.set_member_load(m.id, MemberLoad(qx_start=w, qx_end=w))

            combo = LoadCombination(id=0, name=f"{factor}W", limit_state="ULS")
            combo.factors = {wind_lc.id: factor}

            model, _ = build_model_combined(state, combo)
            asm = Assembler(model)
            K = asm.global_stiffness_matrix(model.elements)
            F = asm.global_force_vector(model.elements)
            return LinearSolver(model).solve(K, F).displacements[1 * 3]

        dx_1 = _solve_combo(1.0)
        dx_15 = _solve_combo(1.5)
        assert abs(dx_15 / dx_1 - 1.5) < 0.001, (
            f"Deflection ratio={dx_15/dx_1:.4f}, expected 1.5"
        )
