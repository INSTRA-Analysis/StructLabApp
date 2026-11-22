"""Characterization models for the golden-value tests.

Each builder returns a fully loaded ``sdk.Model``. They are deliberately plain and
frozen: change one only together with a deliberate regeneration of ``golden.json``
(``python tests/golden/generate.py``) and say why in the commit message.

Together they cover: plane-frame beam / frame / truss / spring support (XZ, Z up), and 3D cantilever
(torsion, rotated section), space frame (node loads, qz/qx/'w' UDL, partial and
point member loads, self-weight, bar braces), pin releases, and the L8 tower.
"""

from __future__ import annotations

import math
from pathlib import Path

import sdk as sl
from ui_qt.io import load_model
from ui_qt.model_state import NodeLoad, SupportType

E, G = 210e9, 80.77e9
A, I = 8.446e-3, 2.313e-4            # IPE 400
RHO = 7850.0
HERE = Path(__file__).parent


def _member(m: sl.Model, i, j, kind="BEAM", n_sub=10, **kw) -> int:
    props = dict(E=E, A=A, I=I)
    props.update(kw)
    return m.add_member(i, j, n_sub=n_sub, element_type=kind, **props)


def continuous_beam_plane() -> sl.Model:
    """Three equal 6 m spans, UDL on all spans plus a nodal load mid-span-2 (plane frame, XZ)."""
    m = sl.Model()
    n = [m.add_node(x, 0, 0) for x in (0, 6, 9, 12, 18)]
    m.pin(n[0])
    for k in (1, 3, 4):
        m.roller(n[k])
    members = [_member(m, n[0], n[1]), _member(m, n[1], n[2]),
               _member(m, n[2], n[3]), _member(m, n[3], n[4])]
    for mid in members:
        m.add_udl(mid, 20e3)
    m.add_point_load(n[2], Fz=-50e3)
    return m


def portal_frame_plane() -> sl.Model:
    m = sl.Model()
    n0, n1, n2, n3 = (m.add_node(0, 0, 0), m.add_node(0, 0, 4),
                      m.add_node(6, 0, 4), m.add_node(6, 0, 0))
    m.pin(n0), m.pin(n3)
    cols = [_member(m, n0, n1), _member(m, n3, n2)]
    beam = _member(m, n1, n2)
    m.add_udl(beam, 8e3)
    m.add_point_load(n1, Fx=15e3, Fz=-20e3)
    m.add_point_load(n2, Fz=-20e3, My=-12e3)      # the former 2D anticlockwise 12 kN·m
    return m


def warren_truss_plane() -> sl.Model:
    m = sl.Model()
    bottom = [m.add_node(4.0 * k, 0, 0) for k in range(5)]
    top = [m.add_node(2.0 + 4.0 * k, 0, 3.0) for k in range(4)]
    m.pin(bottom[0]), m.roller(bottom[4])
    bar = dict(kind="BAR", n_sub=1, A=0.004, I=1e-9)
    for k in range(4):
        _member(m, bottom[k], bottom[k + 1], **bar)
        _member(m, bottom[k], top[k], **bar)
        _member(m, top[k], bottom[k + 1], **bar)
    for k in range(3):
        _member(m, top[k], top[k + 1], **bar)
    for k in (1, 2, 3):
        m.add_point_load(bottom[k], Fz=-10e3)
    return m


def spring_supported_beam_plane() -> sl.Model:
    m = sl.Model()
    a, b, c = m.add_node(0, 0, 0), m.add_node(5, 0, 0), m.add_node(10, 0, 0)
    m.pin(a)
    m._state.get_node(c).support_type = SupportType.SPRING
    m._state.get_node(c).spring_kz = 5e6           # vertical spring
    p = _member(m, a, b)
    q = _member(m, b, c)
    m.add_udl(p, 12e3)
    m.add_udl(q, 12e3)
    m.add_point_load(b, Fz=-30e3)
    return m


def cantilever_3d_torsion() -> sl.Model:
    """Elevated cantilever, rotated section, biaxial tip load plus torque."""
    m = sl.Model(mode_3d=True)
    a, b = m.add_node(0, 0, 5), m.add_node(4, 0, 5)
    m.fixed(a)
    _member(m, a, b, I=2.0e-5, I_y=5.0e-6, J=3.0e-6, A=0.01)
    m._state.get_member(0).beta_angle = 0.3
    m.add_point_load(b, Fy=2e3, Fz=-3e3, Mx=1e3)
    return m


def space_frame_3d() -> sl.Model:
    """4 columns, a beam grid at z=4 with every load type, a bar brace, self-weight."""
    m = sl.Model(mode_3d=True)
    base = [m.add_node(x, y, 0) for x, y in ((0, 0), (6, 0), (6, 5), (0, 5))]
    top = [m.add_node(x, y, 4) for x, y in ((0, 0), (6, 0), (6, 5), (0, 5))]
    for k, b in enumerate(base):
        m.fixed(b) if k % 2 == 0 else m.pin(b)
    sec = dict(A=0.012, I=4e-5, I_y=2e-5, J=1e-5)
    for b, t in zip(base, top):
        _member(m, b, t, **sec)
    ring = [_member(m, top[k], top[(k + 1) % 4], **sec) for k in range(4)]
    brace = _member(m, base[0], top[2], kind="BAR", n_sub=1, A=0.003, I=1e-9)
    for mid in range(len(m._state.members)):
        m._state.get_member(mid).density = RHO
    m._state.set_self_weight_case(m._state.load_cases[0].id)
    m.add_udl(ring[0], 15e3, direction="qz")
    m.add_udl(ring[1], 6e3, direction="qx")
    m.add_partial_load(ring[2], 10e3, 0.25, 0.75)
    m.add_point_force_on_member(ring[3], 25e3, 0.4)
    m.add_point_load(top[1], Fx=10e3, Fy=-6e3, Fz=-30e3, Mz=4e3)
    m.add_point_load(top[3], Fy=12e3, Mx=2e3, My=-1.5e3)
    return m


def pin_release_frame_3d() -> sl.Model:
    """Portal in the XZ plane with a released rafter (PIN_LEFT / PIN_RIGHT) and UDL."""
    m = sl.Model(mode_3d=True)
    n0, n1, n2, n3 = (m.add_node(0, 0, 0), m.add_node(0, 0, 4),
                      m.add_node(6, 0, 4), m.add_node(6, 0, 0))
    m.fixed(n0), m.fixed(n3)
    _member(m, n0, n1, A=0.01, I=4e-5, I_y=4e-5, J=1e-5)
    _member(m, n3, n2, A=0.01, I=4e-5, I_y=4e-5, J=1e-5)
    rafter = _member(m, n1, n2, kind="PIN_RIGHT", A=0.01, I=4e-5, I_y=4e-5, J=1e-5)
    m.add_udl(rafter, 9e3)
    m.add_point_load(n1, Fx=7e3)
    return m


def l8_tower() -> sl.Model:
    """Frozen copy of the generated L8 tower: self-weight + lateral load on every arm tip."""
    state = load_model(HERE / "l8_tower_frozen.slab")
    tips = [n for n in state.nodes if abs(abs(n.x) - 8.55) < 1e-6 or abs(abs(n.x) - 7.8) < 1e-6
            or abs(abs(n.x) - 6.3) < 1e-6]
    case = state.load_cases[0]
    for n in tips:
        case.set_node_load(n.id, NodeLoad(fy=4e3, fz=-6e3))
    return sl.Model.from_state(state)


def as_2d(model: sl.Model):
    """A plane-frame model as the equivalent 2D model (XY, Y up): the native 2D engine's input,
    used by the tests that check a plane frame equals the 2D engine.  The SDK itself no longer
    builds 2D models."""
    import copy
    state = copy.deepcopy(model._state)
    state.rotate_axes("2D")
    state.analysis_mode, state.analysis_type = "2D", "space"
    return state


PLANE_MODELS = ["continuous_beam_plane", "portal_frame_plane", "warren_truss_plane",
                "spring_supported_beam_plane"]


MODELS = {
    "continuous_beam_plane": continuous_beam_plane,
    "portal_frame_plane": portal_frame_plane,
    "warren_truss_plane": warren_truss_plane,
    "spring_supported_beam_plane": spring_supported_beam_plane,
    "cantilever_3d_torsion": cantilever_3d_torsion,
    "space_frame_3d": space_frame_3d,
    "pin_release_frame_3d": pin_release_frame_3d,
    "l8_tower": l8_tower,
}
