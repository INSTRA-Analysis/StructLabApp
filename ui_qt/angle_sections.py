"""Hot-rolled angle (L) sections to EN 10056-1: equal and unequal.

Properties are COMPUTED from the nominal section geometry (leg lengths, thickness,
root radius r1, toe radius r2 = r1/2) by numerical integration of the outline, not
copied from a table. For the sizes checked against published tables the result agrees
to well under 1 %. Root radii are the EN 10056-1 values for the equal angles; those of the
unequal angles are best-effort. Use mill / supplier tables for the final design check.

Geometry and axes (x to the right, y up, origin at the heel = outside corner):

        y
        |  short leg b (vertical)
        |
        |_____ x           long leg a (horizontal)

* ``I_y``, ``I_z`` — second moment about the centroidal axes PARALLEL to the long leg (y)
  and to the short leg (z). For equal angles I_y = I_z.
* ``I_u`` >= ``I_v`` — principal second moments (u = major axis, v = minor axis).
  For an equal angle the u axis is the axis of symmetry (through the heel).
* ``i_v`` is the minimum radius of gyration: the one that governs flexural buckling of a
  single angle (EN 1993-1-1 §6.3.1, buckling curve b for hot-rolled angles).
* ``J`` — St-Venant torsion constant, thin-walled: (a + b - t)·t³/3.
* ``cx``, ``cy`` — centroid distance from the outside face of the vertical leg (x) and of
  the horizontal leg (y).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

RHO_STEEL = 7850.0          # kg/m³
_ARC_STEPS = 48

# Equal angles: leg -> root radius r1 [mm] (EN 10056-1 Table 1); r2 = r1 / 2.
_EQUAL_R1 = {20: 3.5, 25: 3.5, 30: 5, 35: 5, 40: 6, 45: 7, 50: 7, 55: 8, 60: 8, 65: 9,
             70: 9, 75: 9, 80: 10, 90: 11, 100: 12, 120: 13, 130: 14, 150: 16, 160: 17,
             180: 18, 200: 18, 250: 24}
# leg -> available thicknesses [mm]
_EQUAL_SIZES = {
    20: (3,), 25: (3, 4), 30: (3, 4), 35: (4,), 40: (4, 5), 45: (4.5,), 50: (4, 5, 6),
    55: (5, 6), 60: (5, 6, 8), 65: (7,), 70: (6, 7), 75: (6, 8), 80: (6, 8, 10),
    90: (7, 8, 9, 10), 100: (8, 10, 12), 120: (10, 12, 15), 130: (12,),
    150: (10, 12, 14, 15, 18), 160: (15, 16), 180: (16, 18), 200: (16, 18, 20, 24),
    250: (25, 28, 35),
}
# (long leg, short leg, thickness, r1) — best-effort root radii
_UNEQUAL = [
    (60, 40, 6, 6), (80, 60, 7, 8), (100, 50, 8, 10), (100, 65, 8, 10),
    (100, 75, 10, 10), (120, 80, 10, 11), (150, 75, 10, 11), (150, 90, 12, 12),
    (150, 100, 12, 12), (200, 100, 12, 15), (200, 150, 15, 15),
]


@dataclass(frozen=True)
class AngleSection:
    name: str
    kind: str               # "equal" | "unequal"
    a: float                # long leg [m]
    b: float                # short leg [m]
    t: float                # thickness [m]
    r1: float               # root radius [m]
    r2: float               # toe radius [m]
    A: float                # area [m²]
    cx: float               # centroid from outside face of the vertical leg [m]
    cy: float               # centroid from outside face of the horizontal leg [m]
    I_y: float              # about the centroidal axis parallel to the long leg [m⁴]
    I_z: float              # about the centroidal axis parallel to the short leg [m⁴]
    I_u: float              # major principal [m⁴]
    I_v: float              # minor principal [m⁴]
    theta: float            # direction of the major (u) axis, from the long-leg direction (+x) [rad]
    J: float                # torsion constant [m⁴]
    W_u: float              # elastic modulus about u [m³]
    W_v: float              # elastic modulus about v [m³]

    @property
    def mass_per_m(self) -> float:
        return self.A * RHO_STEEL

    @property
    def i_u(self) -> float:
        return math.sqrt(self.I_u / self.A)

    @property
    def i_v(self) -> float:
        return math.sqrt(self.I_v / self.A)


def _outline(a: float, b: float, t: float, r1: float, r2: float) -> np.ndarray:
    """Counter-clockwise outline with the root fillet and one toe radius per leg."""
    def arc(cx: float, cy: float, r: float, a0: float, a1: float) -> list[tuple[float, float]]:
        ts = np.linspace(a0, a1, _ARC_STEPS)
        return [(cx + r * math.cos(s), cy + r * math.sin(s)) for s in ts]

    pts: list[tuple[float, float]] = [(0.0, 0.0), (a, 0.0)]
    pts += arc(a - r2, t - r2, r2, 0.0, math.pi / 2)            # toe of the long leg
    pts += arc(t + r1, t + r1, r1, -math.pi / 2, -math.pi)       # root fillet (concave)
    pts += arc(t - r2, b - r2, r2, 0.0, math.pi / 2)             # toe of the short leg
    pts.append((0.0, b))
    return np.array(pts)


def _section_from_outline(name: str, kind: str, a: float, b: float, t: float,
                          r1: float, r2: float) -> AngleSection:
    p = _outline(a, b, t, r1, r2)
    x, y = p[:, 0], p[:, 1]
    x1, y1 = np.roll(x, -1), np.roll(y, -1)
    cross = x * y1 - x1 * y
    area = cross.sum() / 2
    cx = ((x + x1) * cross).sum() / (6 * area)
    cy = ((y + y1) * cross).sum() / (6 * area)
    ixx = ((y**2 + y * y1 + y1**2) * cross).sum() / 12           # ∫y² dA about the origin
    iyy = ((x**2 + x * x1 + x1**2) * cross).sum() / 12
    ixy = ((x * y1 + 2 * x * y + 2 * x1 * y1 + x1 * y) * cross).sum() / 24
    ixx -= area * cy**2
    iyy -= area * cx**2
    ixy -= area * cx * cy
    tensor = np.array([[ixx, -ixy], [-ixy, iyy]])
    values, vectors = np.linalg.eigh(tensor)
    i_v, i_u = float(values[0]), float(values[1])
    u_dir = vectors[:, 1]
    theta = math.atan2(u_dir[1], u_dir[0])
    rel = np.column_stack((x - cx, y - cy))
    along_u = rel @ u_dir
    along_v = rel @ np.array([-u_dir[1], u_dir[0]])
    return AngleSection(
        name=name, kind=kind, a=a, b=b, t=t, r1=r1, r2=r2, A=float(area),
        cx=float(cx), cy=float(cy), I_y=float(ixx), I_z=float(iyy), I_u=i_u, I_v=i_v,
        theta=theta, J=(a + b - t) * t**3 / 3.0,
        W_u=i_u / float(np.abs(along_v).max()), W_v=i_v / float(np.abs(along_u).max()),
    )


def _fmt(v: float) -> str:
    return f"{v:g}"


def _build() -> dict[str, AngleSection]:
    out: dict[str, AngleSection] = {}
    for leg, thicknesses in _EQUAL_SIZES.items():
        for t in thicknesses:
            r1 = _EQUAL_R1[leg]
            name = f"L {_fmt(leg)}×{_fmt(t)}"
            out[name] = _section_from_outline(name, "equal", leg / 1e3, leg / 1e3,
                                              t / 1e3, r1 / 1e3, r1 / 2e3)
    for a, b, t, r1 in _UNEQUAL:
        name = f"L {a}×{b}×{_fmt(t)}"
        out[name] = _section_from_outline(name, "unequal", a / 1e3, b / 1e3,
                                          t / 1e3, r1 / 1e3, r1 / 2e3)
    return out


ANGLE_SECTIONS: dict[str, AngleSection] = _build()


def angle_properties(name: str) -> AngleSection | None:
    """The AngleSection called ``name`` (e.g. "L 100×10", "L 100×65×8"), or None."""
    return ANGLE_SECTIONS.get(name)


def angle_names(kind: str) -> list[str]:
    """Names of the "equal" or "unequal" angles, smallest first."""
    return [n for n, s in ANGLE_SECTIONS.items() if s.kind == kind]
