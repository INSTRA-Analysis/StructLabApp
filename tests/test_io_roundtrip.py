"""Serialization roundtrip tests for .slab v2 format.

Verifies that saving and reloading a model preserves all data
including load cases, combinations, member loads (with lateral qx),
and produces identical solve results.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest

from ui_qt.model_state import (
    ModelState, NodeData, MemberData,
    SupportType, ElementType, PointLoadData,
    LoadCase, NodeLoad, MemberLoad, LoadCombination,
)
from ui_qt.io import save_model, load_model
from ui_qt.solve_actions import validate_model, solve_engine


def _make_test_model() -> ModelState:
    """Build a simple model with 2 load cases + 1 combination."""
    s = ModelState()
    s.load_cases[0].name = "Dead (G)"
    lc_g = s.load_cases[0]
    lc_q = s.add_load_case("Live (Q)", category="Q")

    n0 = s.add_node(0.0, 0.0)
    n0.support_type = SupportType.PIN
    n1 = s.add_node(4.0, 0.0)
    n2 = s.add_node(8.0, 0.0)
    n2.support_type = SupportType.ROLLER
    n2.spring_ky = 0.0  # explicit zero (not default)

    m1 = s.add_member(n0.id, n1.id)
    m1.element_type = ElementType.BEAM
    m1.E, m1.A, m1.I = 210e9, 0.005, 1e-4

    m2 = s.add_member(n1.id, n2.id)
    m2.element_type = ElementType.BEAM
    m2.E, m2.A, m2.I = 210e9, 0.005, 1e-4

    lc_g.set_member_load(m1.id, MemberLoad(w_start=-10_000, w_end=-10_000))
    lc_g.set_member_load(m2.id, MemberLoad(w_start=-10_000, w_end=-10_000))
    lc_q.set_member_load(m1.id, MemberLoad(w_start=-5_000, w_end=-5_000))
    lc_q.set_member_load(m2.id, MemberLoad(w_start=-5_000, w_end=-5_000))

    c = LoadCombination(
        id=1, name="ULS 1", limit_state="ULS",
        factors={0: 1.35, 1: 1.5},
    )
    s.combinations.append(c)

    return s


def _solve_for_lc(state, lc) -> dict:
    """Build and solve the model for a single load case."""
    from ui_qt.model_builder import build_model
    model, member_el_map = build_model(state, lc)
    return solve_engine(model, member_el_map, state)


def test_roundtrip_model_structure():
    """Save and reload a model; verify node/member counts and properties survive."""
    original = _make_test_model()
    path = Path(tempfile.mktemp(suffix=".slab"))
    try:
        save_model(original, path)
        reloaded = load_model(path)

        assert len(reloaded.nodes) == len(original.nodes)
        assert len(reloaded.members) == len(original.members)
        assert len(reloaded.load_cases) == len(original.load_cases)
        assert len(reloaded.combinations) == len(original.combinations)

        # Check node geometry
        for on, rn in zip(original.nodes, reloaded.nodes):
            assert rn.x == pytest.approx(on.x)
            assert rn.y == pytest.approx(on.y)
            assert rn.support_type == on.support_type
            assert rn.spring_ky == pytest.approx(on.spring_ky)

        # Check member properties
        for om, rm in zip(original.members, reloaded.members):
            assert rm.E == pytest.approx(om.E)
            assert rm.A == pytest.approx(om.A)
            assert rm.I == pytest.approx(om.I)
            assert rm.element_type == om.element_type
            assert rm.node_i == om.node_i
            assert rm.node_j == om.node_j

        # Check load cases
        for olc, rlc in zip(original.load_cases, reloaded.load_cases):
            assert rlc.name == olc.name
            assert rlc.category == olc.category
            assert list(rlc.member_loads.keys()) == list(olc.member_loads.keys())
            for mid in olc.member_loads:
                oml = olc.member_loads[mid]
                rml = rlc.member_loads[mid]
                assert rml.w_start == pytest.approx(oml.w_start)
                assert rml.w_end == pytest.approx(oml.w_end)

        # Check combinations
        for oc, rc in zip(original.combinations, reloaded.combinations):
            assert rc.name == oc.name
            assert rc.limit_state == oc.limit_state
            assert rc.factors == oc.factors

    finally:
        path.unlink(missing_ok=True)


def test_roundtrip_solve_results():
    """Save → reload → solve both; verify identical displacements and reactions."""
    original = _make_test_model()
    path = Path(tempfile.mktemp(suffix=".slab"))
    try:
        save_model(original, path)
        reloaded = load_model(path)

        def _solve(state):
            lc = state.load_cases[0]  # Dead (G)
            return _solve_for_lc(state, lc)

        orig_cache = _solve(original)
        reload_cache = _solve(reloaded)

        np.testing.assert_allclose(
            orig_cache['displacements'],
            reload_cache['displacements'],
            atol=1e-10,
        )
        np.testing.assert_allclose(
            orig_cache['reactions'],
            reload_cache['reactions'],
            atol=1e-10,
        )

        # Compare member results
        for omr, rmr in zip(orig_cache['member_results'],
                            reload_cache['member_results']):
            np.testing.assert_allclose(omr.end_forces, rmr.end_forces, atol=1e-10)

    finally:
        path.unlink(missing_ok=True)


def test_roundtrip_combination_solve():
    """Save → reload → solve combination; verify identical results."""
    original = _make_test_model()
    path = Path(tempfile.mktemp(suffix=".slab"))
    try:
        save_model(original, path)
        reloaded = load_model(path)

        from ui_qt.model_builder import build_model_combined

        combo = original.combinations[0]  # ULS 1
        om, om_el_map = build_model_combined(original, combo)
        orig_cache = solve_engine(om, om_el_map, original)

        rcombo = reloaded.combinations[0]
        rm, rm_el_map = build_model_combined(reloaded, rcombo)
        reload_cache = solve_engine(rm, rm_el_map, reloaded)

        np.testing.assert_allclose(
            orig_cache['displacements'],
            reload_cache['displacements'],
            atol=1e-10,
        )
        np.testing.assert_allclose(
            orig_cache['reactions'],
            reload_cache['reactions'],
            atol=1e-10,
        )
    finally:
        path.unlink(missing_ok=True)


def test_roundtrip_with_lateral_qx():
    """Save → reload model with distributed lateral qx loads."""
    s = ModelState()
    s.load_cases[0].name = "Wind (W)"
    lc_w = s.load_cases[0]

    n0 = s.add_node(0.0, 0.0)
    n0.support_type = SupportType.FIXED
    n1 = s.add_node(0.0, 5.0)

    m = s.add_member(n0.id, n1.id)
    m.element_type = ElementType.BEAM
    m.E, m.A, m.I = 210e9, 0.01, 2e-4

    lc_w.set_member_load(m.id, MemberLoad(
        qx_start=2_000.0,
        qx_end=3_500.0,
    ))

    path = Path(tempfile.mktemp(suffix=".slab"))
    try:
        save_model(s, path)
        reloaded = load_model(path)

        rlc = reloaded.load_cases[0]
        rml = rlc.member_loads[m.id]
        assert rml.qx_start == pytest.approx(2_000.0)
        assert rml.qx_end == pytest.approx(3_500.0)

        # Solve both and compare
        lc_orig = s.load_cases[0]
        oc = _solve_for_lc(s, lc_orig)

        rlc2 = reloaded.load_cases[0]
        rc = _solve_for_lc(reloaded, rlc2)

        np.testing.assert_allclose(
            oc['displacements'], rc['displacements'], atol=1e-10)
    finally:
        path.unlink(missing_ok=True)


def test_validate_model_detects_floating_nodes():
    """validate_model (extracted to solve_actions) detects floating nodes."""
    s = ModelState()
    s.add_node(0.0, 0.0)
    s.add_node(5.0, 0.0)
    s.add_node(10.0, 0.0)  # floating — no members
    m = s.add_member(0, 1)
    m.element_type = ElementType.BEAM
    m.E, m.A, m.I = 210e9, 0.01, 1e-4

    errors, _warnings = validate_model(s)
    assert any("Floating" in e for e in errors)


def test_validate_model_detects_no_supports():
    """validate_model detects missing supports."""
    s = ModelState()
    n0 = s.add_node(0.0, 0.0)
    n1 = s.add_node(5.0, 0.0)
    m = s.add_member(n0.id, n1.id)
    m.element_type = ElementType.BEAM
    m.E, m.A, m.I = 210e9, 0.01, 1e-4

    errors, _warnings = validate_model(s)
    assert any("unsupported" in e.lower() for e in errors)


def test_validate_model_detects_only_rollers():
    """validate_model warns when only ROLLER supports exist (no PIN/FIXED)."""
    s = ModelState()
    n0 = s.add_node(0.0, 0.0)
    n0.support_type = SupportType.ROLLER
    n1 = s.add_node(5.0, 0.0)
    n1.support_type = SupportType.ROLLER
    m = s.add_member(n0.id, n1.id)
    m.element_type = ElementType.BEAM
    m.E, m.A, m.I = 210e9, 0.01, 1e-4

    errors, _warnings = validate_model(s)
    assert any("only ROLLER" in e for e in errors)


def test_validate_model_detects_zero_length():
    """validate_model detects zero-length members."""
    s = ModelState()
    n0 = s.add_node(0.0, 0.0)
    n0.support_type = SupportType.PIN
    n1 = s.add_node(0.0, 0.0)  # same point as n0
    n1.support_type = SupportType.ROLLER
    m = s.add_member(n0.id, n1.id)
    m.element_type = ElementType.BEAM
    m.E, m.A, m.I = 210e9, 0.01, 1e-4

    errors, _warnings = validate_model(s)
    assert any("zero length" in e for e in errors)
