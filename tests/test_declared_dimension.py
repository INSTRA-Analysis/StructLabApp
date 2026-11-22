"""Declared analysis dimension: the engine solves what the model declares, never a guess
from the z coordinates (a 3D model may lie entirely at z = 0)."""

import pytest

from core.material import Material
from core.model import Model
from core.node import Node
from core.section import Section
from elements.bar_element import BarElement
from elements.frame_element import FrameElement
from solver.assembler import Assembler
from ui_qt.model_builder import build_model
from ui_qt.model_state import MemberLoad, ModelState, NodeLoad, SupportType
from ui_qt.solve_actions import solve_engine

E, A, I = 210e9, 8e-3, 2.313e-4
MAT = Material(name="S", elastic_modulus=E, poisson_ratio=0.3)
SEC = Section(name="s", area=A, moment_of_inertia=I)


def test_model_dimension_overrides_the_coordinates():
    flat = [Node(0, 0, 0, 0), Node(1, 3, 0, 0)]
    assert Model(nodes=flat).dofs_per_node == 3                    # legacy detection
    assert Model(nodes=flat, dimension=3).dofs_per_node == 6
    assert Model(nodes=[Node(0, 0, 0, 1)], dimension=2).dofs_per_node == 3


def test_element_dimension_is_declared_or_bound_by_the_model():
    a, b = Node(0, 0, 0, 0), Node(1, 3, 0, 0)
    assert FrameElement(0, a, b, MAT, SEC, dimension=3).is_3d     # 3D at z = 0
    auto = FrameElement(1, a, b, MAT, SEC)
    assert not auto.is_3d
    auto.bind_dimension(6)
    assert auto.is_3d and auto.global_stiffness_matrix(6).shape == (12, 12)
    with pytest.raises(ValueError):
        FrameElement(2, a, Node(2, 0, 0, 1), MAT, SEC, dimension=2)   # off the plane
    with pytest.raises(ValueError):
        FrameElement(3, a, b, MAT, SEC, dimension=2).bind_dimension(6)
    assert BarElement(4, a, b, MAT, area=A, dimension=3).is_3d


def test_assembler_binds_every_element_to_the_model():
    a, b = Node(0, 0, 0, 0), Node(1, 0, 3, 0)
    el = FrameElement(0, a, b, MAT, SEC)
    model = Model(nodes=[a, b], elements=[el], dimension=3)
    Assembler(model)
    assert el.is_3d


def _flat_3d_beam(load) -> tuple:
    s = ModelState()
    s.analysis_mode = "3D"
    a, b, c = s.add_node(0, 0, 0), s.add_node(3, 0, 0), s.add_node(6, 0, 0)
    a.support_type = c.support_type = SupportType.PIN
    for p, q in ((a, b), (b, c)):
        m = s.add_member(p.id, q.id)
        m.E, m.A, m.I, m.I_y, m.J = E, A, I, I, 1e-5
    load(s, b)
    model, mm = build_model(s, s.active_case)
    return s, model, solve_engine(model, mm, s), b


def test_flat_3d_beam_carries_a_vertical_point_load():
    s, model, cache, b = _flat_3d_beam(lambda s, b: s.active_case.set_node_load(b.id, NodeLoad(fz=-1e4)))
    assert model.dofs_per_node == 6
    assert cache["displacements"][b.id * 6 + 2] == pytest.approx(-1e4 * 6.0 ** 3 / (48 * E * I), rel=1e-9)
    assert cache["reactions"][2::6].sum() == pytest.approx(1e4, rel=1e-9)
    assert all(n.z == 0.0 for n in s.nodes)                       # the model is not touched


def test_flat_3d_beam_udl_acts_downward_not_sideways():
    w = 5e3
    _s, _m, cache, b = _flat_3d_beam(
        lambda s, b: [s.active_case.set_member_load(m.id, MemberLoad(w_start=w, w_end=w)) for m in s.members])
    d = cache["displacements"]
    assert d[b.id * 6 + 2] == pytest.approx(-5 * w * 6.0 ** 4 / (384 * E * I), rel=1e-9)
    assert d[b.id * 6 + 1] == pytest.approx(0.0, abs=1e-15)


def test_a_2d_model_off_the_plane_is_refused():
    s = ModelState()
    s.analysis_mode = "2D"
    a, b = s.add_node(0, 0, 0), s.add_node(3, 0, 1.0)
    s.add_member(a.id, b.id)
    with pytest.raises(ValueError, match="XY plane"):
        build_model(s, s.active_case)
