"""Support symbols: what the canvas draws at a supported node, in 2D and in 3D.

Two styles share one colour (``theme.SUPPORT``), the type being told by the shape:

* 2D "drawing office": textbook symbols in screen pixels, outlined with a light tint on a
  hatched ground line (fixed, pinned, rollers, springs with a spiral for k_theta).
* 3D "solid bearings": shaded solids on a base plate, built in glyph units and projected with
  the canvas camera (footing block, pyramid, pyramid on cylinders, collar on rails, coils).

The optional *restraint markers* view draws exactly what the solver restrains instead: a cone
into the node per blocked translation, a disc per blocked rotation (a ring around the node in
2D), and a coil or spiral per spring, in the axis colours. The restrained DOFs come from
``core.Support.restrained_dofs`` so the markers can never disagree with the analysis.

Everything here returns ``DrawOp`` lists (a painter path, fill, pen); the canvas item only
paints them. No widgets, so it is testable without a window.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor, QPainterPath, QPolygonF

from ui_qt import theme

# ── colours and sizes ────────────────────────────────────────────────────────

SUPPORT = theme.SUPPORT                 # one colour for every support
SUPPORT_LIGHT = "#a6e8ae"
SUPPORT_DARK = "#245c2e"
SUPPORT_TINT = QColor(92, 201, 107, 41)  # 16 % fill behind 2D outlines
AXIS = (theme.AXIS_X, theme.AXIS_Y, theme.AXIS_Z)
GLYPH_PX = 56.0                          # 3D: pixels per glyph unit at zoom 1

Tone = tuple[str, str, str]              # (dark, mid, light)


def _hex_rgb(colour: str) -> tuple[int, int, int]:
    c = QColor(colour)
    return c.red(), c.green(), c.blue()


def mix(a: str, b: str, t: float) -> str:
    """Linear mix of two colours, t = 0 → a, t = 1 → b, as #rrggbb."""
    t = min(1.0, max(0.0, t))
    ra, rb = _hex_rgb(a), _hex_rgb(b)
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(ra, rb))


SUPPORT_TONE: Tone = (SUPPORT_DARK, SUPPORT, SUPPORT_LIGHT)


def axis_tone(axis: int) -> Tone:
    c = AXIS[axis]
    return mix(c, "#000000", 0.55), c, mix(c, "#ffffff", 0.45)


@dataclass
class DrawOp:
    """One painter primitive: fill (or None) and pen colour (or None) with width."""
    path: QPainterPath
    fill: QColor | None
    pen: QColor | None
    width: float = 1.0


# ── which DOFs a node's support restrains (from the solver's own table) ─────

def restraint_flags(support_name: str, three_d: bool) -> tuple[bool, ...]:
    """(ux, uy, uz, θx, θy, θz) restrained by a UI support type, as the solver applies it.

    In 2D only ux, uy and θz exist; uz, θx, θy are reported False.
    """
    from core.support import Support
    from ui_qt.model_builder import _RIGID_MAP
    from ui_qt.model_state import SupportType
    core_type = _RIGID_MAP[SupportType[support_name]]
    dpn = 6 if three_d else 3
    dofs = set(Support(node_id=0, support_type=core_type).restrained_dofs(dpn))
    if three_d:
        return tuple(i in dofs for i in range(6))
    return (0 in dofs, 1 in dofs, False, False, False, 2 in dofs)


def node_springs(node) -> tuple[float, ...]:
    """(kx, ky, kz, krx, kry, krz) of a SPRING node; θz uses k_theta (what the solver reads)."""
    if node.support_type.name != "SPRING":
        return (0.0,) * 6
    return (node.spring_kx, node.spring_ky, node.spring_kz,
            node.spring_krx, node.spring_kry, node.spring_ktheta or node.spring_krz)


# ── camera ───────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Camera:
    """The canvas's orthographic az/el camera (same formulas as projection.isometric)."""
    right: np.ndarray
    up: np.ndarray
    toward: np.ndarray
    light: np.ndarray

    @classmethod
    def from_angles(cls, azimuth_deg: float, elevation_deg: float) -> "Camera":
        az, el = math.radians(azimuth_deg), math.radians(elevation_deg)
        c, s, se, ce = math.cos(az), math.sin(az), math.sin(el), math.cos(el)
        right = np.array([c, s, 0.0])
        up = np.array([s * se, -c * se, ce])
        toward = np.array([-s * ce, c * ce, se])
        light = -0.45 * right + 0.7 * up + 0.75 * toward
        return cls(right, up, toward, light / np.linalg.norm(light))

    def project(self, p: np.ndarray, scale: float) -> QPointF:
        return QPointF(float(p @ self.right) * scale, -float(p @ self.up) * scale)


# ── 3D solids (glyph units, node at the origin) ──────────────────────────────

@dataclass
class Solid:
    faces: list[np.ndarray]
    tone: Tone
    smooth: bool = False                 # curved surface: no edge lines between facets
    centre: np.ndarray = field(init=False)

    def __post_init__(self) -> None:
        self.centre = np.vstack(self.faces).mean(axis=0)


@dataclass
class Glyph:
    solids: list[Solid] = field(default_factory=list)
    lines: list[tuple[np.ndarray, str, float]] = field(default_factory=list)   # points, colour, width


_E = np.eye(3)


def _box(centre, half, tone: Tone) -> Solid:
    c, h = np.asarray(centre, float), np.asarray(half, float)
    v = lambda i, j, k: c + h * np.array([i, j, k], float)
    quads = [((-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)), ((-1, -1, -1), (-1, 1, -1), (1, 1, -1), (1, -1, -1)),
             ((-1, -1, -1), (1, -1, -1), (1, -1, 1), (-1, -1, 1)), ((-1, 1, -1), (-1, 1, 1), (1, 1, 1), (1, 1, -1)),
             ((-1, -1, -1), (-1, -1, 1), (-1, 1, 1), (-1, 1, -1)), ((1, -1, -1), (1, 1, -1), (1, 1, 1), (1, -1, 1))]
    return Solid([np.array([v(*q) for q in quad]) for quad in quads], tone)


def _pyramid(apex_z: float, base_z: float, half: float, tone: Tone) -> Solid:
    apex = np.array([0.0, 0.0, apex_z])
    base = [np.array([x, y, base_z]) for x, y in ((-half, -half), (half, -half), (half, half), (-half, half))]
    faces = [np.array(base[::-1])] + [np.array([apex, base[i], base[(i + 1) % 4]]) for i in range(4)]
    return Solid(faces, tone)


def _perp_basis(axis: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    ref = _E[0] if abs(axis[2]) > 0.9 else _E[2]
    u = np.cross(axis, ref)
    u /= np.linalg.norm(u)
    return u, np.cross(axis, u)


def _ring(centre: np.ndarray, axis: np.ndarray, radius: float, n: int) -> list[np.ndarray]:
    u, v = _perp_basis(axis)
    return [centre + radius * (math.cos(2 * math.pi * i / n) * u + math.sin(2 * math.pi * i / n) * v)
            for i in range(n)]


def _cylinder(centre, axis, radius: float, length: float, tone: Tone, n: int = 16) -> Solid:
    c, a = np.asarray(centre, float), np.asarray(axis, float)
    A, B = _ring(c - a * length / 2, a, radius, n), _ring(c + a * length / 2, a, radius, n)
    sides = [np.array([A[i], A[(i + 1) % n], B[(i + 1) % n], B[i]]) for i in range(n)]
    return Solid([np.array(A[::-1]), np.array(B)] + sides, tone, smooth=True)


def _cone(apex, axis, height: float, radius: float, tone: Tone, n: int = 16) -> Solid:
    apex, a = np.asarray(apex, float), np.asarray(axis, float)
    base = _ring(apex + a * height, a, radius, n)
    faces = [np.array(base[::-1])] + [np.array([apex, base[(i + 1) % n], base[i]]) for i in range(n)]
    return Solid(faces, tone, smooth=True)


def _helix(axis: np.ndarray, start: float, end: float, radius: float, turns: float) -> np.ndarray:
    """Coil along ``axis`` from ``start`` to ``end`` (glyph units), tapering in and out."""
    u, v = _perp_basis(axis)
    n = int(turns * 16)
    pts = [axis * start * 0.6]
    for i in range(n + 1):
        t = i / n
        r = radius * min(1.0, min(t, 1 - t) * 10)
        ang = 2 * math.pi * turns * t
        pts.append(axis * (start + (end - start) * t) + r * (math.cos(ang) * u + math.sin(ang) * v))
    pts.append(axis * end)
    return np.array(pts)


def _spiral(axis: np.ndarray, r0: float, r1: float, turns: float = 1.3) -> np.ndarray:
    u, v = _perp_basis(axis)
    n = int(turns * 24)
    return np.array([(r0 + (r1 - r0) * i / n) * (math.cos(2 * math.pi * turns * i / n) * u
                                                 + math.sin(2 * math.pi * turns * i / n) * v)
                     for i in range(n + 1)])


def _double_arrow(a: np.ndarray, b: np.ndarray, side: np.ndarray, head: float = 0.07) -> list[np.ndarray]:
    d = (b - a) / np.linalg.norm(b - a)
    wing = lambda tip, direction, sg: tip - direction * head + side * sg * head * 0.6
    return [np.array([a, b]),
            np.array([wing(a, -d, 1), a, wing(a, -d, -1)]),
            np.array([wing(b, d, 1), b, wing(b, d, -1)])]


def _side_towards(axis: np.ndarray, cam: Camera) -> float:
    return 1.0 if float(axis @ cam.toward) >= 0 else -1.0


def bearing_glyph(kind: str, cam: Camera, springs: tuple[float, ...] = (0.0,) * 6) -> Glyph:
    """3D "solid bearings" for a UI support type name (FIXED, PIN, ROLLER, ROLLER_Y, ROLLER_Z, SPRING)."""
    T = SUPPORT_TONE

    def plate(z: float, half: float = 0.42) -> Solid:
        return _box([0, 0, z], [half, half, 0.035], T)

    if kind == "FIXED":
        return Glyph([_box([0, 0, -0.13], [0.33, 0.33, 0.13], T), plate(-0.295, 0.47)])
    if kind == "PIN":
        return Glyph([_pyramid(-0.03, -0.42, 0.26, T), plate(-0.455)])
    if kind in ("ROLLER", "ROLLER_Y"):
        free = _E[0] if kind == "ROLLER" else _E[1]
        across = _E[1] if kind == "ROLLER" else _E[0]
        solids = [_pyramid(-0.03, -0.33, 0.23, T), _box([0, 0, -0.36], [0.31, 0.31, 0.03], T),
                  *(_cylinder(free * k + np.array([0, 0, -0.455]), across, 0.065, 0.56, T) for k in (-0.15, 0.15)),
                  plate(-0.555)]
        off = across * 0.56 * _side_towards(across, cam) + np.array([0, 0, -0.555])
        lines = [(seg, SUPPORT_LIGHT, 1.6) for seg in _double_arrow(off - free * 0.36, off + free * 0.36, _E[2])]
        return Glyph(solids, lines)
    if kind == "ROLLER_Z":
        along_x = abs(cam.right[0]) >= abs(cam.right[1])     # rails side by side across the screen
        rail_axis, other = (_E[0], _E[1]) if along_x else (_E[1], _E[0])
        rail = lambda k: _box(rail_axis * k + np.array([0, 0, -0.2]),
                              rail_axis * 0.035 + other * 0.07 + np.array([0, 0, 0.38]), T)
        collar = _box([0, 0, 0], rail_axis * 0.19 + other * 0.09 + np.array([0, 0, 0.07]), T)
        off = other * 0.36 * _side_towards(other, cam)
        lines = [(seg, SUPPORT_LIGHT, 1.6)
                 for seg in _double_arrow(off + np.array([0, 0, -0.32]), off + np.array([0, 0, 0.18]), rail_axis)]
        return Glyph([rail(-0.235), rail(0.235), collar, plate(-0.615)], lines)
    if kind == "SPRING":
        return _spring_glyph(springs, coloured=False)
    return Glyph()


def _spring_glyph(springs: tuple[float, ...], coloured: bool) -> Glyph:
    """Coils for translational springs (with anchor plates unless coloured) and spirals for rotational."""
    glyph = Glyph()
    kt, kr = springs[:3], springs[3:]
    if not any(springs):
        kt = (0.0, 0.0, 1.0)                     # assigned but no stiffness yet: show one coil
    anchors = {0: ([-0.535, 0, 0], [0.03, 0.2, 0.2]), 1: ([0, -0.535, 0], [0.2, 0.03, 0.2]),
               2: ([0, 0, -0.535], [0.2, 0.2, 0.03])}
    for i, k in enumerate(kt):
        if k:
            colour = AXIS[i] if coloured else SUPPORT
            glyph.lines.append((_helix(-_E[i], 0.08, 0.5, 0.085, 5), colour, 1.7))
            if not coloured:
                glyph.solids.append(_box(*anchors[i], SUPPORT_TONE))
    for i, k in enumerate(kr):
        if k:
            colour = AXIS[i] if coloured else SUPPORT
            pts = _spiral(_E[i], 0.13, 0.27) + _E[i] * (0.18 if i == 2 else 0.0)
            glyph.lines.append((pts, colour, 1.6))
    return glyph


def restraint_glyph(flags: tuple[bool, ...], springs: tuple[float, ...] = (0.0,) * 6) -> Glyph:
    """3D restraint markers: cone per blocked translation, disc per blocked rotation, coloured by axis."""
    glyph = Glyph()
    for i in range(3):
        a = -_E[i]
        if flags[i]:
            glyph.solids.append(_cone(a * 0.1, a, 0.32, 0.12, axis_tone(i)))
        if flags[i + 3]:
            glyph.solids.append(_cylinder(a * 0.58, a, 0.2, 0.06, axis_tone(i)))   # wider than the cone
    if any(springs):
        spring = _spring_glyph(springs, coloured=True)
        glyph.lines += spring.lines
    return glyph


# ── projection to paint operations ───────────────────────────────────────────

def shade(tone: Tone, normal: np.ndarray, cam: Camera) -> str:
    """Face colour: dark → mid → light with the light that follows the camera."""
    lum = 0.18 + 0.82 * max(0.0, float(normal @ cam.light))
    dark, mid, light = tone
    return mix(dark, mid, lum / 0.55) if lum < 0.55 else mix(mid, light, (lum - 0.55) / 0.45)


def glyph_ops(glyph: Glyph, cam: Camera, scale: float = GLYPH_PX) -> list[DrawOp]:
    """Visible faces far → near (back faces culled), then the line work."""
    faces = []
    for solid in glyph.solids:
        for f in solid.faces:
            n = np.cross(f[1] - f[0], f[2] - f[0])
            length = np.linalg.norm(n)
            if length < 1e-12:
                continue
            n = n / length
            if float(n @ (f.mean(axis=0) - solid.centre)) < 0:
                n = -n                                         # outward
            if float(n @ cam.toward) <= 1e-6:
                continue                                       # faces away from the camera
            faces.append((float(f.mean(axis=0) @ cam.toward), f, n, solid))
    faces.sort(key=lambda item: item[0])
    ops = []
    for _depth, f, n, solid in faces:
        path = QPainterPath()
        path.addPolygon(QPolygonF([cam.project(p, scale) for p in f]))
        path.closeSubpath()
        fill = QColor(shade(solid.tone, n, cam))
        edge = fill if solid.smooth else QColor(solid.tone[0])
        ops.append(DrawOp(path, fill, edge, 0.6 if solid.smooth else 0.9))
    for pts, colour, width in glyph.lines:
        path = QPainterPath(cam.project(pts[0], scale))
        for p in pts[1:]:
            path.lineTo(cam.project(p, scale))
        ops.append(DrawOp(path, None, QColor(colour), width))
    return ops


# ── 2D drawing-office symbols (screen px, node at the origin, y down) ───────

def _ground(y: float, half: float) -> list[DrawOp]:
    line = QPainterPath(QPointF(-half, y))
    line.lineTo(half, y)
    hatch = QPainterPath()
    x = -half + 4
    while x <= half + 0.1:
        hatch.moveTo(x, y)
        hatch.lineTo(x - 5, y + 6)
        x += 5.5
    faint = QColor(SUPPORT)
    faint.setAlphaF(0.75)
    return [DrawOp(line, None, QColor(SUPPORT), 2.0), DrawOp(hatch, None, faint, 1.2)]


def _triangle(height: float, half: float) -> DrawOp:
    path = QPainterPath(QPointF(0, 0))
    path.lineTo(-half, height)
    path.lineTo(half, height)
    path.closeSubpath()
    return DrawOp(path, SUPPORT_TINT, QColor(SUPPORT), 1.8)


def _rotated(ops: list[DrawOp], degrees: float) -> list[DrawOp]:
    from PyQt6.QtGui import QTransform
    t = QTransform().rotate(degrees)
    return [DrawOp(t.map(op.path), op.fill, op.pen, op.width) for op in ops]


def _zigzag(direction: tuple[float, float], start: float, end: float, amp: float = 6.0) -> QPainterPath:
    dx, dy = direction
    px, py = -dy, dx
    path = QPainterPath(QPointF(dx * (start - 3), dy * (start - 3)))
    path.lineTo(dx * start, dy * start)
    n = 6
    for i in range(n):
        along = start + (end - start) * (i + 0.5) / n
        side = amp if i % 2 == 0 else -amp
        path.lineTo(dx * along + px * side, dy * along + py * side)
    path.lineTo(dx * end, dy * end)
    path.lineTo(dx * (end + 2), dy * (end + 2))
    return path


def _spiral_2d(r0: float = 10.0, r1: float = 16.0) -> QPainterPath:
    path = QPainterPath()
    for i in range(51):
        t = i / 50
        a = math.pi * 1.15 - t * math.pi * 2.3
        r = r0 + (r1 - r0) * t
        p = QPointF(r * math.cos(a), -r * math.sin(a))
        path.moveTo(p) if i == 0 else path.lineTo(p)
    return path


def roller_2d() -> list[DrawOp]:
    wheels = QPainterPath()
    for x in (-5.5, 5.5):
        wheels.addEllipse(QPointF(x, 17.4), 3.2, 3.2)
    return [_triangle(14, 10), DrawOp(wheels, SUPPORT_TINT, QColor(SUPPORT), 1.5)] + _ground(20.8, 17)


def drawing_ops_2d(kind: str, springs: tuple[float, ...] = (0.0,) * 6) -> list[DrawOp]:
    """2D drawing-office symbol for a UI support type name."""
    if kind == "FIXED":
        return _ground(0, 18)
    if kind in ("PIN", "ROLLER_Z"):                  # ROLLER_Z is solved as a pin in 2D
        return [_triangle(18, 11)] + _ground(18, 17)
    if kind == "ROLLER":
        return roller_2d()
    if kind == "ROLLER_Y":
        return _rotated(roller_2d(), 90)
    if kind == "SPRING":
        kx, ky, ktheta = springs[0], springs[1], springs[5]
        if not (kx or ky or ktheta):
            ky = 1.0
        ops: list[DrawOp] = []
        pen = QColor(SUPPORT)
        if ky:
            ops.append(DrawOp(_zigzag((0, 1), 9, 29), None, pen, 1.8))
            ops += _ground(31, 14)
        if kx:
            ops.append(DrawOp(_zigzag((-1, 0), 9, 29), None, pen, 1.8))
            ops += _rotated(_ground(31, 14), 90)
        if ktheta:
            ops.append(DrawOp(_spiral_2d(), None, pen, 1.8))
        return ops
    return []


def restraint_ops_2d(flags: tuple[bool, ...], springs: tuple[float, ...] = (0.0,) * 6) -> list[DrawOp]:
    """2D restraint markers: arrowheads into the node for ux (red) and uy (green), a ring for θz (blue)."""
    ops = []

    def head(points: list[tuple[float, float]], colour: str) -> DrawOp:
        path = QPainterPath()
        path.addPolygon(QPolygonF([QPointF(*p) for p in points]))
        path.closeSubpath()
        return DrawOp(path, QColor(colour), QColor(mix(colour, "#000000", 0.45)), 1.0)

    if flags[0]:
        ops.append(head([(-11, 0), (-24, -6), (-24, 6)], AXIS[0]))
    if flags[1]:
        ops.append(head([(0, 11), (-6, 24), (6, 24)], AXIS[1]))
    if flags[5]:
        ring = QPainterPath()
        ring.addEllipse(QRectF(-8.5, -8.5, 17, 17))
        ops.append(DrawOp(ring, None, QColor(AXIS[2]), 2.2))
    if springs[0]:
        ops.append(DrawOp(_zigzag((-1, 0), 11, 31), None, QColor(AXIS[0]), 1.8))
    if springs[1]:
        ops.append(DrawOp(_zigzag((0, 1), 11, 31), None, QColor(AXIS[1]), 1.8))
    if springs[5]:
        ops.append(DrawOp(_spiral_2d(), None, QColor(AXIS[2]), 1.8))
    return ops
