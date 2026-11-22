"""Plane frame (XZ) = the 2D engine, case by case.

Every 2D benchmark (B1–B7, F1–F3, T1–T2) and every 2D golden model is turned into a plane
frame in the XZ plane (3D engine, uy/θx/θz locked) and solved; the results must equal the
native 2D solve to 1e-9:

  displacements   ux = ux,  uz = uy(2D),  θy = -θz(2D),  locked DOFs exactly zero
  reactions       Rx = Rx,  Rz = Ry(2D),  My = -Mz(2D),  lock forces nil
  member forces   N equal; V and M equal, or opposite where the member's local y is
                  reversed between the 2D (90° anticlockwise) and 3D (upward) conventions
                  (its loads in member axes are flipped to the same physical direction)
  diagrams        V(x), M(x) sampled along every element, same rule

The benchmark models are captured from the benchmark modules themselves (their own builders,
stopped before OpenSees runs), so this suite tracks exactly what the benchmarks solve.
"""

from __future__ import annotations

import copy

import numpy as np
import pytest

from core.load import ElementLoad, LoadDirection, NodalLoad
from core.model import Model
from core.node import Node
from core.support import Support, SupportType as CoreType
from elements.bar_element import BarElement
from elements.frame_element import FrameElement
from elements.truss_element import TrussElement
from solver.assembler import Assembler
from solver.linear_solver import LinearSolver
from solver.postprocessor import Postprocessor

PLANE_XZ = (1, 3, 5)
TOL = 1e-9


# ── core-level: 2D model -> plane frame in XZ ────────────────────────────────

def _reversed_local_y(ni: Node, nj: Node) -> bool:
    dx, dz = nj.x - ni.x, nj.z - ni.z
    length = np.hypot(dx, dz)
    y_2d = np.array([-dz / length, 0.0, dx / length])
    return float(y_2d @ FrameElement.local_axes_3d(dx, nj.y - ni.y, dz)[:, 1]) < 0.0


def to_plane_frame(m2: Model) -> tuple[Model, dict[int, float]]:
    """The same structure as a plane frame in XZ; also each element's local-sign (+1 / -1)."""
    nodes = {n.id: Node(n.id, n.x, 0.0, n.y) for n in m2.nodes}       # (x, y, 0) -> (x, 0, y)
    elements, sign = [], {}
    for el in m2.elements:
        ni, nj = nodes[el.node_i.id], nodes[el.node_j.id]
        if isinstance(el, BarElement):
            new = BarElement(el.id, ni, nj, el.material, area=el.section.area, dimension=3)
        elif isinstance(el, TrussElement):
            new = TrussElement(el.id, ni, nj, el.material, area=el.section.area, dimension=3)
        else:
            new = FrameElement(el.id, ni, nj, el.material, el.section,
                               pin_i=el.pin_i, pin_j=el.pin_j, dimension=3)
        elements.append(new)
        sign[el.id] = -1.0 if _reversed_local_y(ni, nj) else 1.0
    supports = []
    for sp in m2.supports:
        held_2d = {d - sp.node_id * 3 for d in sp.restrained_dofs(3)}      # 0 ux, 1 uy, 2 θz
        held_3d = {{0: 0, 1: 2, 2: 4}[k] for k in held_2d}                # -> ux, uz, θy
        flags = tuple(k in held_3d for k in range(6))
        supports.append(Support(sp.node_id, CoreType.FREE,
                                spring_stiffness_x=sp.spring_stiffness_x,
                                spring_stiffness_z=sp.spring_stiffness_y,
                                spring_stiffness_ry=sp.spring_stiffness_theta,
                                restrained=flags))
    nodal = [NodalLoad(node_id=nl.node_id, fx=nl.fx, fz=nl.fy, moment_y=-nl.moment)
             for nl in m2.nodal_loads]
    element_loads = []
    for el in m2.element_loads:
        assert el.direction is LoadDirection.LOCAL_Y
        s = sign[el.element_id]
        uvl = el.load_type.name == "UVL"                 # position holds w at the end
        element_loads.append(ElementLoad(el.element_id, el.load_type, s * el.magnitude,
                                         s * el.position if uvl else el.position))
    m3 = Model(nodes=list(nodes.values()), elements=elements, supports=supports,
               nodal_loads=nodal, element_loads=element_loads, dimension=3,
               locked_dofs=PLANE_XZ)
    return m3, sign


def _solve(model: Model):
    asm = Assembler(model)
    res = LinearSolver(model).solve(asm.global_stiffness_matrix(model.elements),
                                    asm.global_force_vector(model.elements))
    post = Postprocessor(model.elements, model.element_loads, res.displacements)
    return res, post.compute(), post.sfd_bmd(11)


def assert_plane_frame_equals_2d(m2: Model) -> None:
    m3, sign = to_plane_frame(m2)
    r2, e2, d2 = _solve(m2)
    r3, e3, d3 = _solve(m3)
    ids = [n.id for n in m2.nodes]
    u2 = np.array([r2.displacements[i * 3: i * 3 + 3] for i in ids])
    u3 = np.array([r3.displacements[i * 6: i * 6 + 6] for i in ids])
    su = max(np.abs(u2).max(), 1e-30)
    np.testing.assert_allclose(u3[:, [0, 2, 4]], u2 * [1, 1, -1], atol=TOL * su, rtol=0)
    assert np.abs(u3[:, PLANE_XZ]).max() == 0.0
    f2 = np.array([r2.reactions[i * 3: i * 3 + 3] for i in ids])
    f3 = np.array([r3.reactions[i * 6: i * 6 + 6] for i in ids])
    sf = max(np.abs(f2).max(), 1.0)
    np.testing.assert_allclose(f3[:, [0, 2, 4]], f2 * [1, 1, -1], atol=TOL * sf, rtol=0)
    assert np.abs(r3.lock_forces).max() <= TOL * sf
    for a, b in zip(e2, e3):
        s = sign[a.element_id]
        assert (b.N_i, b.N_j) == pytest.approx((a.N_i, a.N_j), abs=TOL * sf)
        assert (b.V_i, b.V_j) == pytest.approx((s * a.V_i, s * a.V_j), abs=TOL * sf)
        assert (b.M_i, b.M_j) == pytest.approx((s * a.M_i, s * a.M_j), abs=TOL * sf)
    for a, b in zip(d2, d3):
        s = sign[a.element_id]
        np.testing.assert_allclose(b.V, s * a.V, atol=TOL * sf, rtol=0)
        np.testing.assert_allclose(b.M, s * a.M, atol=TOL * sf, rtol=0)


# ── the benchmark models, captured from the benchmark modules ────────────────

class _Captured(Exception):
    pass


def _benchmark_models() -> dict[str, Model]:
    from benchmarks.cases import beams_2d, frames_2d, trusses_2d
    models: dict[str, Model] = {}
    for module, names in ((beams_2d, [f"b{k}" for k in range(1, 8)]),
                          (frames_2d, ["f1", "f2", "f3"]),
                          (trusses_2d, ["t1", "t2"])):
        original = module._sl_solve
        for name in names:
            def capture(model, _name=name):
                models[_name.upper()] = copy.deepcopy(model)
                raise _Captured
            module._sl_solve = capture
            try:
                getattr(module, f"run_{name}")()
            except _Captured:
                pass
            finally:
                module._sl_solve = original
    return models


def _synthetic_frame() -> Model:
    """What the benchmarks leave out: nodal and member point moments, a varying load (UVL),
    a point load on a column, a member drawn right to left, springs and a pin release."""
    from core.load import LoadType
    from core.material import Material
    from core.section import Section
    mat = Material(name="S355", elastic_modulus=210e9, poisson_ratio=0.3)
    sec = Section(name="IPE300", area=5.38e-3, moment_of_inertia=8.356e-5)
    n = [Node(0, 0, 0, 0), Node(1, 0, 4, 0), Node(2, 5, 5, 0), Node(3, 9, 4, 0), Node(4, 9, 0, 0)]
    els = [FrameElement(0, n[0], n[1], mat, sec),
           FrameElement(1, n[2], n[1], mat, sec, pin_i=True),          # drawn right to left
           FrameElement(2, n[2], n[3], mat, sec),
           FrameElement(3, n[4], n[3], mat, sec),
           BarElement(4, n[0], n[2], mat, area=1e-3)]
    sup = [Support(0, CoreType.FIXED),
           Support(4, CoreType.ROLLER_X, spring_stiffness_x=2e6, spring_stiffness_theta=5e5)]
    nodal = [NodalLoad(node_id=1, fx=12e3, moment=-7e3), NodalLoad(node_id=3, fy=-9e3, moment=4e3)]
    loads = [ElementLoad(1, LoadType.UDL, 6e3),
             ElementLoad(2, LoadType.UVL, 2e3, position=8e3),
             ElementLoad(0, LoadType.POINT_FORCE, 5e3, position=1.5),
             ElementLoad(3, LoadType.POINT_MOMENT, 3e3, position=2.0),
             ElementLoad(2, LoadType.POINT_MOMENT, -2e3, position=1.0)]
    return Model(nodes=n, elements=els, supports=sup, nodal_loads=nodal, element_loads=loads)


BENCHMARKS = _benchmark_models()
CASES = {**BENCHMARKS, "SYNTHETIC": _synthetic_frame()}


def test_all_twelve_2d_benchmarks_were_captured():
    assert sorted(BENCHMARKS) == sorted([f"B{k}" for k in range(1, 8)] + ["F1", "F2", "F3", "T1", "T2"])
    assert all(m.dofs_per_node == 3 for m in BENCHMARKS.values())


@pytest.mark.parametrize("name", sorted(CASES))
def test_case_as_a_plane_frame_equals_the_2d_engine(name):
    assert_plane_frame_equals_2d(copy.deepcopy(CASES[name]))


def test_the_comparison_catches_a_wrong_moment_sign(monkeypatch):
    """Guard on the guard: map nodal moments with the wrong sign and the check must fail."""
    import tests.test_plane_frame_equivalence as me
    real = me.to_plane_frame

    def wrong(m2):
        m3, sign = real(m2)
        m3.nodal_loads = [NodalLoad(node_id=n.node_id, fx=n.fx, fz=n.fz, moment_y=-n.moment_y)
                          for n in m3.nodal_loads]
        return m3, sign
    monkeypatch.setattr(me, "to_plane_frame", wrong)
    with pytest.raises(AssertionError):
        me.assert_plane_frame_equals_2d(copy.deepcopy(CASES["SYNTHETIC"]))


# ── the 2D golden models, through the app's own path ─────────────────────────

from tests.golden.models import PLANE_MODELS as GOLDEN_2D        # rebuilt as 2D by as_2d


@pytest.mark.parametrize("name", GOLDEN_2D)
def test_golden_model_switched_to_a_plane_frame_equals_2d(name):
    from tests.golden import models as golden
    from ui_qt.model_builder import build_model
    from ui_qt.solve_actions import solve_engine
    s = golden.as_2d(getattr(golden, name)())
    assert s.is_2d
    c2 = solve_engine(*build_model(s, s.active_case), s)
    s.rotate_axes("3D")
    s.analysis_mode, s.analysis_type = "3D", "plane_xz"
    flipped = s._members_with_reversed_local_y()
    c3 = solve_engine(*build_model(s, s.active_case), s)
    ids = [n.id for n in s.nodes]
    u2 = np.array([c2["displacements"][i * 3: i * 3 + 3] for i in ids])
    u3 = np.array([c3["displacements"][i * 6: i * 6 + 6] for i in ids])
    np.testing.assert_allclose(u3[:, [0, 2, 4]], u2 * [1, 1, -1], atol=TOL * np.abs(u2).max(), rtol=0)
    f2 = np.array([c2["reactions"][i * 3: i * 3 + 3] for i in ids])
    f3 = np.array([c3["reactions"][i * 6: i * 6 + 6] for i in ids])
    sf = max(np.abs(f2).max(), 1.0)
    np.testing.assert_allclose(f3[:, [0, 2, 4]], f2 * [1, 1, -1], atol=TOL * sf, rtol=0)
    for md, a, b in zip(s.members, c2["member_results"], c3["member_results"]):
        k = -1.0 if md.id in flipped else 1.0
        assert (b.N_i, b.N_j) == pytest.approx((a.N_i, a.N_j), abs=TOL * sf)
        assert (b.M_i, b.M_j, b.V_i, b.V_j) == pytest.approx(
            (k * a.M_i, k * a.M_j, k * a.V_i, k * a.V_j), abs=TOL * sf)
