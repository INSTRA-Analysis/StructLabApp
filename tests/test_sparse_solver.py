"""The sparse path (what the application solves with) equals the dense one, and still reports
mechanisms. Covers springs, moment releases, bars, member loads and plane-frame locks."""

import numpy as np
import pytest
from scipy import sparse

from solver.assembler import Assembler
from solver.linear_solver import LinearSolver, UnstableStructureError
from ui_qt.model_builder import build_model
from ui_qt.model_state import (
    DistLoad, ElementType, MemberLoad, ModelState, NodeLoad, PointLoadData, SupportType,
)


def _model(analysis_type: str) -> ModelState:
    s = ModelState()
    s.analysis_type = analysis_type
    a, b, c, d = (s.add_node(0, 0, 0), s.add_node(0, 0, 4), s.add_node(6, 0, 4), s.add_node(6, 0, 0))
    a.support_type = SupportType.FIXED
    d.support_type = SupportType.SPRING
    d.spring_kx, d.spring_kz, d.spring_kry = 5e6, 8e7, 2e6
    if analysis_type == "space":
        d.spring_ky, d.spring_krx, d.spring_ktheta = 5e6, 1e6, 1e6
    for p, q, kind in ((a, b, ElementType.BEAM), (b, c, ElementType.PIN_RIGHT), (c, d, ElementType.BEAM),
                       (a, c, ElementType.BAR)):
        m = s.add_member(p.id, q.id)
        m.element_type, m.I_y, m.J = kind, m.I / 3, 1e-5
    s.active_case.member_loads[1] = MemberLoad(dist_loads=[DistLoad("w", 4e3, 9e3)],
                                               point_loads=[PointLoadData("FORCE", 0.37, 12e3)])
    s.active_case.set_node_load(b.id, NodeLoad(fx=7e3, fy=2e3 if analysis_type == "space" else 0.0))
    return s


@pytest.mark.parametrize("analysis_type", ["plane_xz", "space"])
def test_sparse_equals_dense(analysis_type):
    s = _model(analysis_type)
    model, _ = build_model(s, s.active_case)
    asm = Assembler(model)
    F = asm.global_force_vector(model.elements)
    K_sparse = asm.global_stiffness_sparse(model.elements)
    assert sparse.issparse(K_sparse)
    assert np.allclose(K_sparse.toarray(), asm.global_stiffness_matrix(model.elements))
    dense = LinearSolver(model).solve(asm.global_stiffness_matrix(model.elements), F)
    sp = LinearSolver(model).solve(K_sparse, F)
    scale = np.abs(dense.displacements).max()
    assert np.abs(sp.displacements - dense.displacements).max() <= 1e-9 * scale
    assert np.abs(sp.reactions - dense.reactions).max() <= 1e-9 * np.abs(dense.reactions).max()
    assert np.allclose(sp.lock_forces, dense.lock_forces, atol=1e-6)
    assert sp.free_dofs == dense.free_dofs


def _pinned_line(torque: float):
    """Straight two-member beam on pins in a SPACE frame: free to twist about its own axis
    (an unloaded rigid-body twist), vertical point load at mid-span, optional torque Mx."""
    s = ModelState()
    a, b, c = s.add_node(0, 0, 0), s.add_node(3, 0, 0), s.add_node(6, 0, 0)
    a.support_type = c.support_type = SupportType.PIN
    for p, q in ((a, b), (b, c)):
        m = s.add_member(p.id, q.id)
        m.I_y, m.J, m.n_sub = m.I, 1e-5, 1
    s.active_case.set_node_load(b.id, NodeLoad(fz=-1e4, moment_x=torque))
    return s, b


@pytest.mark.parametrize("dense", [False, True])
def test_an_unloaded_free_twist_does_not_stop_the_solve(dense):
    s, mid = _pinned_line(0.0)
    model, _ = build_model(s, s.active_case)
    asm = Assembler(model)
    K = asm.global_stiffness_matrix(model.elements) if dense else asm.global_stiffness_sparse(model.elements)
    r = LinearSolver(model).solve(K, asm.global_force_vector(model.elements))
    m = s.members[0]
    assert r.displacements[mid.id * 6 + 2] == pytest.approx(-1e4 * 6 ** 3 / (48 * m.E * m.I), rel=1e-9)


def test_a_loaded_free_twist_is_a_mechanism():
    s, _ = _pinned_line(500.0)
    model, _ = build_model(s, s.active_case)
    asm = Assembler(model)
    with pytest.raises(UnstableStructureError):
        LinearSolver(model).solve(asm.global_stiffness_sparse(model.elements),
                                  asm.global_force_vector(model.elements))


def test_sparse_path_reports_a_mechanism():
    s = ModelState()
    s.analysis_type = "plane_xz"
    a, b, c = s.add_node(0, 0, 0), s.add_node(3, 0, 0), s.add_node(3, 0, 3)
    a.support_type = SupportType.PIN
    for p, q in ((a, b), (b, c)):
        s.add_member(p.id, q.id).element_type = ElementType.BAR      # swings about the pin
    s.active_case.set_node_load(c.id, NodeLoad(fx=1e3))
    model, _ = build_model(s, s.active_case)
    asm = Assembler(model)
    with pytest.raises(UnstableStructureError):
        LinearSolver(model).solve(asm.global_stiffness_sparse(model.elements),
                                  asm.global_force_vector(model.elements))
