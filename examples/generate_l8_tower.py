"""Generate a representative UK L8 'D STD' 400 kV double-circuit suspension tower.

Writes examples/l8_tower_3d.slab (StructLab v3 model, Z up).

Published envelope (drawing 35/8744, via telcontar.net/Power/pylons/L8):
    height 46.4 m, base width 7.5 m, widest crossarm span 17.1 m.
Everything else (panel levels, waist width, arm geometry, bracing pattern,
sections) is a REPRESENTATIVE design, not the real drawing.

Modelling choices
-----------------
* Legs, arm top/bottom chords: continuous BEAM members. All bracing: BAR.
* Angle sections use I = I_y = moment of inertia about the axis parallel to the
  legs (no beta_angle); principal-axis values are used in the member checks.
* Each section family is its own `group`, so sections can be re-assigned per group.
* Phase and earth-wire attachment nodes are returned in ATTACH for the load step.
* Self-weight uses the app's own option (on in the "Self weight" case): bars are lumped
  to their joints, legs and arm chords are distributed along their length.

Run:  python examples/generate_l8_tower.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui_qt.io import save_model
from ui_qt.model_state import ElementType, MemberData, ModelState, SupportType

# ── Equal-angle sections (EN 10056-1): name -> (A cm², I_yy cm⁴, t mm, b mm) ────
ANGLES: dict[str, tuple[float, float, float, float]] = {
    "L200x20": (76.3, 2850.0, 20.0, 200.0),
    "L150x15": (43.0, 898.0, 15.0, 150.0),
    "L120x12": (27.5, 368.0, 12.0, 120.0),
    "L100x10": (19.2, 177.0, 10.0, 100.0),
    "L80x8":   (12.3, 72.3, 8.0, 80.0),
    "L70x7":   (9.40, 42.4, 7.0, 70.0),
    "L60x6":   (6.91, 22.8, 6.0, 60.0),
    "L50x5":   (4.80, 11.0, 5.0, 50.0),
}

E_STEEL, RHO = 210e9, 7850.0

# group -> (section, element type, fy [Pa])
GROUPS: dict[str, tuple[str, ElementType, float]] = {
    "Leg 1 (0-14.5m)":   ("L200x20", ElementType.BEAM, 355e6),
    "Leg 2 (14.5-26m)":  ("L150x15", ElementType.BEAM, 355e6),
    "Leg 3 (26-37m)":    ("L120x12", ElementType.BEAM, 355e6),
    "Leg 4 (37m-top)":   ("L100x10", ElementType.BEAM, 355e6),
    "Diagonal lower":    ("L80x8",   ElementType.BAR, 275e6),
    "Diagonal upper":    ("L60x6",   ElementType.BAR, 275e6),
    "Horizontal":        ("L70x7",   ElementType.BAR, 275e6),
    "Plan bracing":      ("L50x5",   ElementType.BAR, 275e6),
    "Arm chord":         ("L100x10", ElementType.BEAM, 355e6),
    "Arm web":           ("L60x6",   ElementType.BAR, 275e6),
    "Arm plan bracing":  ("L50x5",   ElementType.BAR, 275e6),
    "Peak":              ("L70x7",   ElementType.BAR, 275e6),
}

# ── Geometry ─────────────────────────────────────────────────────────────────
HEIGHT = 46.4
HALF_BASE, HALF_WAIST, HALF_TOP = 3.75, 1.25, 0.60      # leg half-spacing
Z_WAIST, Z_TOP = 28.0, 44.0
ARMS = [  # (name, z of bottom chord, half-span, rise at body, rise at tip)
    ("Lower",  28.0, 8.55, 2.0, 0.8),
    ("Middle", 35.0, 7.80, 2.0, 0.8),
    ("Upper",  42.0, 6.30, 2.0, 0.8),
]
LEVELS = [0, 5, 10, 14.5, 18.5, 22.5, 26, 28, 30, 33, 35, 37, 39.5, 42, 44]
PLAN_BRACED = {26.0, 28.0, 35.0, 42.0, 44.0}
ARM_PANELS = 3

ATTACH: dict[str, list[int]] = {}   # label -> node ids (filled by build())


def half_width(z: float) -> float:
    if z <= Z_WAIST:
        return HALF_BASE + (HALF_WAIST - HALF_BASE) * z / Z_WAIST
    return HALF_WAIST + (HALF_TOP - HALF_WAIST) * (z - Z_WAIST) / (Z_TOP - Z_WAIST)


def leg_group(z_mid: float) -> str:
    return ("Leg 1 (0-14.5m)" if z_mid < 14.5 else "Leg 2 (14.5-26m)" if z_mid < 26
            else "Leg 3 (26-37m)" if z_mid < 37 else "Leg 4 (37m-top)")


def build() -> ModelState:
    s = ModelState()
    s.mode_3d = True
    s.metadata.title = "L8 D STD 400 kV suspension tower (representative)"
    s.load_cases[0].name = "Self weight"
    s.load_cases[0].include_self_weight = True

    keys: dict[tuple[float, float, float], int] = {}

    def node(x: float, y: float, z: float) -> int:
        k = (round(x, 4), round(y, 4), round(z, 4))
        if k not in keys:
            keys[k] = s.add_node(*k).id
        return keys[k]

    def member(a: int, b: int, group: str) -> None:
        sec, etype, fy = GROUPS[group]
        area_cm2, iyy_cm4, t, b_mm = ANGLES[sec]
        m: MemberData = s.add_member(a, b)
        m.group, m.element_type, m.E, m.fy, m.density = group, etype, E_STEEL, fy, RHO
        m.A, m.I, m.I_y = area_cm2 * 1e-4, iyy_cm4 * 1e-8, iyy_cm4 * 1e-8
        m.J = (2 * b_mm - t) * t ** 3 / 3.0 * 1e-12      # thin-walled angle, m⁴
        m.n_sub = 10 if etype == ElementType.BEAM else 2

    corners = [(-1, -1), (1, -1), (1, 1), (-1, 1)]

    def ring(z: float) -> list[int]:
        h = half_width(z)
        return [node(sx * h, sy * h, z) for sx, sy in corners]

    rings = {z: ring(z) for z in LEVELS}
    for z in LEVELS:                       # horizontals + plan bracing
        r = rings[z]
        if z > 0:
            for i in range(4):
                member(r[i], r[(i + 1) % 4], "Horizontal")
        if z in PLAN_BRACED:
            member(r[0], r[2], "Plan bracing")   # crossing diagonals, no centre node
            member(r[1], r[3], "Plan bracing")   # (a coplanar-bar-only node is a mechanism)

    for lo, hi in zip(LEVELS, LEVELS[1:]):  # legs + X-braced faces
        a, b = rings[lo], rings[hi]
        grp = "Diagonal lower" if hi <= Z_WAIST else "Diagonal upper"
        for i in range(4):
            member(a[i], b[i], leg_group((lo + hi) / 2))
            j = (i + 1) % 4
            member(a[i], b[j], grp)             # X-bracing: two crossing bars per
            member(a[j], b[i], grp)             # face, no node at the crossing

    # Peak (earth-wire attachment) above the top ring
    apex = node(0.0, 0.0, HEIGHT)
    for n in rings[Z_TOP]:
        member(apex, n, "Peak")
    ATTACH["Earth wire"] = [apex]

    # Crossarms: two parallel trusses (one per leg pair) on each side
    for name, z0, span, rise0, rise_tip in ARMS:
        for side, label in ((1, "R"), (-1, "L")):
            planes = []
            for sy in (-1, 1):
                hb = half_width(z0)
                ht = half_width(z0 + rise0)
                y0, yt = sy * hb, sy * ht
                bot = [node(side * hb, y0, z0)]
                top = [node(side * ht, yt, z0 + rise0)]
                for k in range(1, ARM_PANELS + 1):
                    f = k / ARM_PANELS
                    x = hb + (span - hb) * f
                    bot.append(node(side * x, y0, z0))
                    top.append(node(side * x, y0, z0 + rise0 + (rise_tip - rise0) * f))
                for k in range(ARM_PANELS):
                    member(bot[k], bot[k + 1], "Arm chord")
                    member(top[k], top[k + 1], "Arm chord")
                    member(bot[k], top[k + 1], "Arm web")
                for k in range(1, ARM_PANELS + 1):
                    member(bot[k], top[k], "Arm web")
                planes.append((bot, top))
            for pl in (0, 1):                           # plan bracing, bottom and top
                for k in range(1, ARM_PANELS + 1):
                    p0, p1 = planes[0][pl], planes[1][pl]
                    member(p0[k], p1[k], "Arm plan bracing")
                    member(p0[k - 1], p1[k], "Arm plan bracing")
            ATTACH[f"{name} {label}"] = [planes[0][0][-1], planes[1][0][-1]]

    for n in rings[0]:
        s.get_node(n).support_type = SupportType.PIN
    return s


if __name__ == "__main__":
    state = build()
    out = Path(__file__).resolve().parents[1] / "examples" / "l8_tower_3d.slab"
    save_model(state, out)
    mass = {}
    for m in state.members:
        a, b = state.get_node(m.node_i), state.get_node(m.node_j)
        L = math.dist((a.x, a.y, a.z), (b.x, b.y, b.z))
        c = mass.setdefault(m.group, [0, 0.0, 0.0])
        c[0] += 1; c[1] += L; c[2] += L * m.A * RHO
    print(f"Wrote {out}\n{len(state.nodes)} nodes, {len(state.members)} members\n")
    print(f"{'group':20s}{'section':9s}{'n':>5s}{'length m':>10s}{'mass kg':>10s}")
    for g, (n, L, M) in mass.items():
        print(f"{g:20s}{GROUPS[g][0]:9s}{n:5d}{L:10.1f}{M:10.0f}")
    print(f"{'TOTAL':34s}{sum(v[2] for v in mass.values()):10.0f}")
