"""Load combinations keep self-weight and the 3D node-load components."""

import math

import pytest

from ui_qt.model_builder import build_model_combined
from ui_qt.model_state import ModelState, NodeLoad, SupportType

RHO, G, A, L = 7850.0, 9.81, 0.01, 4.0


def _cantilever(z: float) -> ModelState:
    s = ModelState()
    a, b = s.add_node(0, 0, z), s.add_node(L, 0, z)
    a.support_type = SupportType.FIXED
    m = s.add_member(a.id, b.id)
    m.density, m.A = RHO, A
    s.load_cases[0].include_self_weight = True
    s.load_cases[0].set_node_load(b.id, NodeLoad(fz=-5000.0, moment_y=100.0))
    return s


def _total(model, attr: str) -> float:
    return sum(getattr(n, attr) for n in model.nodal_loads)


def test_combination_scales_3d_node_loads():
    s = _cantilever(z=10.0)
    combo = s.add_combination("ULS")
    combo.factors = {0: 1.35}
    model, _ = build_model_combined(s, combo)
    weight = RHO * A * G * L
    # Self-weight (UDL elements + axial lumps) and the factored point load.
    assert _total(model, "fz") == pytest.approx(1.35 * -5000.0)
    assert _total(model, "moment_y") == pytest.approx(1.35 * 100.0)
    sw_uniform = sum(el.magnitude * model.elements[el.element_id].length
                     for el in model.element_loads)
    assert sw_uniform == pytest.approx(1.35 * weight, rel=1e-9)


def test_combination_scales_self_weight_in_2d():
    s = _cantilever(z=0.0)
    combo = s.add_combination("ULS")
    combo.factors = {0: 1.35}
    model, _ = build_model_combined(s, combo)
    plain, _ = build_model_combined(s, _unit_combo(s))
    ratio = sum(el.magnitude for el in model.element_loads) / sum(
        el.magnitude for el in plain.element_loads)
    assert ratio == pytest.approx(1.35)
    assert not math.isclose(sum(el.magnitude for el in model.element_loads), 0.0)


def _unit_combo(s: ModelState):
    combo = s.add_combination("SLS", limit_state="SLS")
    combo.factors = {0: 1.0}
    return combo
