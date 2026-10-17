"""Parametric lattice transmission-tower generator (UK L8 family).

Writes a StructLab v3 model (Z up) from a ``TowerSpec``. The default is the
**L8(c) D30** 400 kV double-circuit angle tower, reproduced from the published
elevation drawing (drawing 35/8744 via telcontar.net/Power/pylons/L8): arm levels,
arm reaches (the arms are NOT symmetric), shaft taper, panel levels and the K-type
bracing of the lower body were measured from that drawing. Member sections are a
representative first design, not the real schedule.

Other towers are other specs:
    python examples/generate_l8_tower.py                  # L8c_D30 -> examples/l8c_d30_tower_3d.slab
    python examples/generate_l8_tower.py L8c_D90 --plot   # scaled variant + front-elevation PNG
    python examples/generate_l8_tower.py --list

``L8c_D``, ``L8c_D60`` and ``L8c_D90`` are the D30 template scaled to those towers'
published height / base width / crossarm width. Only D30 follows its drawing in detail.

Modelling choices
-----------------
* Legs and arm chords: continuous BEAM members. All bracing: BAR.
* Sections come from the app's angle library (ui_qt/angle_sections.py, EN 10056-1). A corner
  leg uses its principal axes (I_v about the tangential axis, I_u about the radial axis,
  beta = 0); other beams use the minor axis I_v on both axes (safe side, orientation unknown).
* Bracing patterns per band: ``X`` (two crossing bars per face), ``V`` (corners of the
  upper level to the centre of the lower one) and ``LAMBDA`` (centre of the upper level
  to the corners of the lower one). V/LAMBDA use a node at the centre of a horizontal;
  a node held only by bars in one plane is a mechanism, so every such level gets a plan
  diaphragm: a diamond ring through the four face-centre nodes plus two crossing bars.
  (Crossing bars alone are not enough: the opposite pair can still translate together.)
* Each section family is its own ``group`` so sections can be reassigned per group.
* Self-weight uses the app's own option (Self weight case).
* Load attachment points are returned in ATTACH (arm tips, earth-wire nodes).
* Cable loads (docs/L8_tower_cable_loads.pdf) are added as separate load cases at those
  points: Conductor weight, Ice, Wind +X, Wind -X. They are CHARACTERISTIC loads on a
  SUSPENSION basis from the assumptions in ``CableAssumptions``; they carry no partial
  factors and no wind on the tower body, broken-wire or line-angle (tension) loads.
"""

from __future__ import annotations

import dataclasses
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui_qt.angle_sections import angle_properties
from ui_qt.io import save_model
from ui_qt.model_state import ElementType, ModelState, NodeLoad, SupportType

E_STEEL, RHO = 210e9, 7850.0

# group -> (section, element type, fy [Pa])
GROUPS: dict[str, tuple[str, ElementType, float]] = {
    "Leg 1 (base)":      ("L 200×20", ElementType.BEAM, 355e6),
    "Leg 2":             ("L 150×15", ElementType.BEAM, 355e6),
    "Leg 3":             ("L 120×12", ElementType.BEAM, 355e6),
    "Leg 4 (top)":       ("L 100×10", ElementType.BEAM, 355e6),
    "K-brace":           ("L 120×12", ElementType.BAR, 275e6),
    "Diagonal lower":    ("L 80×8",   ElementType.BAR, 275e6),
    "Diagonal upper":    ("L 60×6",   ElementType.BAR, 275e6),
    "Horizontal":        ("L 70×7",   ElementType.BAR, 275e6),
    "Horizontal (K level)": ("L 90×9", ElementType.BAR, 275e6),
    "Plan bracing":      ("L 50×5",   ElementType.BAR, 275e6),
    "Arm chord":         ("L 100×10", ElementType.BEAM, 355e6),
    "Arm web":           ("L 60×6",   ElementType.BAR, 275e6),
    "Arm plan bracing":  ("L 50×5",   ElementType.BAR, 275e6),
}
LEG_GROUPS = [(12.2, "Leg 1 (base)"), (19.7, "Leg 2"), (29.2, "Leg 3"), (1e9, "Leg 4 (top)")]
X_LOWER_LIMIT = 29.2          # X-bracing below this height uses the heavier diagonal


# ── Specification ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Arm:
    """One crossarm level: a triangular truss on each side of the shaft.

    The bottom boom is horizontal at ``z_bottom``; the top boom runs from the shaft at
    ``z_top`` down to the tip at ``z_bottom``. Reaches are measured from the shaft axis.
    """
    name: str
    z_bottom: float
    z_top: float
    reach_minus: float      # towards -X
    reach_plus: float       # towards +X


@dataclass(frozen=True)
class Band:
    """A run of equal panels between two levels with one bracing pattern."""
    z_bottom: float
    z_top: float
    panels: int
    pattern: str            # "X" | "V" | "LAMBDA"


@dataclass(frozen=True)
class TowerSpec:
    name: str
    height: float
    leg_spacing: tuple[tuple[float, float], ...]    # (z, centre-to-centre leg spacing)
    arms: tuple[Arm, ...]
    bands: tuple[Band, ...]
    arm_panel_length: float = 2.2                   # target bay length along an arm [m]

    def half_width(self, z: float) -> float:
        zs, ws = zip(*sorted(self.leg_spacing))
        return float(np.interp(z, zs, ws)) / 2.0


D30 = TowerSpec(
    name="L8c_D30",
    height=43.8,
    leg_spacing=((0.0, 9.60), (4.5, 8.21), (9.4, 6.51), (14.3, 4.97), (19.2, 3.89),
                 (22.2, 3.27), (26.1, 2.50), (30.1, 2.19), (35.1, 1.88),
                 (36.9, 1.73), (43.8, 1.575)),
    arms=(
        Arm("Lower",  19.7, 21.5, 8.59, 4.80),
        Arm("Middle", 26.7, 29.2, 10.61, 6.90),
        Arm("Upper",  35.1, 36.9, 7.14, 4.80),
    ),
    bands=(
        Band(0.0, 7.3, 1, "LAMBDA"), Band(7.3, 12.2, 1, "LAMBDA"),
        Band(12.2, 16.6, 1, "LAMBDA"), Band(16.6, 19.7, 1, "V"),
        Band(19.7, 21.5, 1, "X"), Band(21.5, 26.7, 2, "X"),
        Band(26.7, 29.2, 1, "X"), Band(29.2, 35.1, 3, "X"),
        Band(35.1, 36.9, 1, "X"), Band(36.9, 43.8, 4, "X"),
    ),
)


def scaled_variant(base: TowerSpec, name: str, height: float,
                   base_width: float, crossarm_width: float) -> TowerSpec:
    """Scale a template to another tower's published height / base width / crossarm width.

    Heights scale uniformly; only the flare below the lowest arm follows the base width
    (the shaft above it keeps its width); arm reaches scale with the crossarm width.
    """
    kz = height / base.height
    waist_z = min(a.z_bottom for a in base.arms)
    waist_w = base.half_width(waist_z) * 2
    k_flare = (base_width - waist_w) / (base.leg_spacing[0][1] - waist_w)
    spacing = tuple(
        (z * kz, w if z >= waist_z else waist_w + (w - waist_w) * k_flare)
        for z, w in base.leg_spacing)
    widest = max(a.reach_minus + a.reach_plus for a in base.arms)
    kx = crossarm_width / widest
    arms = tuple(dataclasses.replace(
        a, z_bottom=a.z_bottom * kz, z_top=a.z_top * kz,
        reach_minus=a.reach_minus * kx, reach_plus=a.reach_plus * kx) for a in base.arms)
    bands = tuple(dataclasses.replace(b, z_bottom=b.z_bottom * kz, z_top=b.z_top * kz)
                  for b in base.bands)
    return dataclasses.replace(base, name=name, height=height, leg_spacing=spacing,
                               arms=arms, bands=bands)


TOWERS: dict[str, TowerSpec] = {
    "L8c_D30": D30,
    "L8c_D":   scaled_variant(D30, "L8c_D",   46.4, 7.5, 17.1),
    "L8c_D60": scaled_variant(D30, "L8c_D60", 44.5, 10.8, 18.2),
    "L8c_D90": scaled_variant(D30, "L8c_D90", 49.4, 16.2, 21.8),
}

ATTACH: dict[str, list[int]] = {}      # label -> node ids (filled by build())


# ── Cable loads ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Conductor:
    name: str
    diameter: float         # m
    mass_per_m: float       # kg/m
    uts_kn: float           # breaking load [kN]


ZEBRA = Conductor("ACSR Zebra", 0.02862, 1.621, 131.9)    # APAR ACSR catalogue
LYNX = Conductor("ACSR Lynx", 0.01953, 0.842, 79.8)


@dataclass(frozen=True)
class CableAssumptions:
    """Inputs for the characteristic cable loads. Change here; everything follows.

    ``span`` is used as both the wind span and the weight span (UK normal span for
    275/400 kV towers). Wind speed, ice thickness and hardware weights are ILLUSTRATIVE
    assumptions, not code values.
    """
    span: float = 360.0                 # m
    bundle: int = 2                     # sub-conductors per phase (twin)
    wind_speed: float = 35.0            # m/s
    air_density: float = 1.225          # kg/m³
    drag: float = 1.0                   # drag coefficient on the cable
    ice_thickness: float = 0.010        # m radial
    ice_density: float = 900.0          # kg/m³
    hardware_phase_kn: float = 2.0      # insulator string + fittings, per phase
    hardware_earth_kn: float = 0.5      # earth-wire clamp / fittings
    phase: Conductor = ZEBRA
    earth: Conductor = LYNX
    gravity: float = 9.81


def cable_loads(a: CableAssumptions = CableAssumptions()) -> dict:
    """Characteristic load per phase and for the earth wire, in kN (wind as a force on the span)."""
    q = 0.5 * a.air_density * a.wind_speed ** 2          # Pa

    def ice_kg_per_m(d: float) -> float:
        return math.pi * ((d / 2 + a.ice_thickness) ** 2 - (d / 2) ** 2) * a.ice_density

    def one(c: Conductor, n: int, hardware: float) -> dict[str, float]:
        weight = n * c.mass_per_m * a.gravity * a.span / 1e3
        return {"weight": weight, "hardware": hardware,
                "vertical": weight + hardware,
                "ice": n * ice_kg_per_m(c.diameter) * a.gravity * a.span / 1e3,
                "wind": q * a.drag * n * c.diameter * a.span / 1e3}

    return {"q": q, "phase": one(a.phase, a.bundle, a.hardware_phase_kn),
            "earth": one(a.earth, 1, a.hardware_earth_kn)}


# (name, category, vertical component, transverse X component) — each a multiple of the loads
CABLE_CASES = (
    ("Conductor weight", "G", ("vertical", 1.0), None),
    ("Ice", "Q", ("ice", 1.0), None),
    ("Wind +X", "W", None, ("wind", +1.0)),
    ("Wind -X", "W", None, ("wind", -1.0)),
)


def add_cable_load_cases(state: ModelState, a: CableAssumptions = CableAssumptions()) -> None:
    """Add the cable loads as separate load cases at the attachment nodes in ATTACH.

    Each phase attachment has two nodes (front / back plane): each takes half. The earth
    wire is spread over the four top-ring corners: a quarter each. Loads are characteristic
    (unfactored); vertical is downward (-Z); wind acts across the line (±X).
    """
    loads = cable_loads(a)
    for name, category, vertical, transverse in CABLE_CASES:
        case = state.add_load_case(name, category)
        for label, node_ids in ATTACH.items():
            kind = "earth" if label == "Earth wire" else "phase"
            share = 1.0 / len(node_ids)
            fz = fx = 0.0
            if vertical:
                fz = -loads[kind][vertical[0]] * vertical[1] * share * 1e3
            if transverse:
                fx = loads[kind][transverse[0]] * transverse[1] * share * 1e3
            for nid in node_ids:
                case.set_node_load(nid, NodeLoad(fx=fx, fz=fz))


# ── Builder ──────────────────────────────────────────────────────────────────

CORNERS = [(-1, -1), (1, -1), (1, 1), (-1, 1)]       # face i runs corner i -> i+1


def build(spec: TowerSpec = D30, cable: CableAssumptions | None = CableAssumptions()) -> ModelState:
    ATTACH.clear()
    s = ModelState()
    s.mode_3d = True
    s.metadata.title = f"{spec.name} 400 kV tower (representative sections)"
    s.load_cases[0].name = "Self weight"
    s.load_cases[0].include_self_weight = True

    keys: dict[tuple[float, float, float], int] = {}
    pairs: set[tuple[int, int]] = set()

    def node(x: float, y: float, z: float) -> int:
        k = (round(x, 4) + 0.0, round(y, 4) + 0.0, round(z, 4) + 0.0)
        if k not in keys:
            keys[k] = s.add_node(*k).id
        return keys[k]

    def member(a: int, b: int, group: str) -> None:
        if a == b or (min(a, b), max(a, b)) in pairs:
            return
        pairs.add((min(a, b), max(a, b)))
        section, etype, fy = GROUPS[group]
        ang = angle_properties(section)
        m = s.add_member(a, b)
        m.group, m.element_type, m.E, m.fy, m.density = group, etype, E_STEEL, fy, RHO
        m.A, m.J = ang.A, ang.J
        if group.startswith("Leg"):
            # Corner angle, beta = 0: local y is radial = the angle's symmetry axis (u),
            # so bending about local z (tangential, v axis) uses I_v and about y uses I_u.
            m.I, m.I_y = ang.I_v, ang.I_u
        else:
            m.I = m.I_y = ang.I_v        # orientation unknown: use the minor axis (safe side)
        m.n_sub = 10 if etype == ElementType.BEAM else 2

    def coord(n: int) -> tuple[float, float, float]:
        nd = s.get_node(n)
        return nd.x, nd.y, nd.z

    # Levels: every band boundary plus the equal sub-panels inside a band
    levels = sorted({round(z, 4) for b in spec.bands for z in
                     np.linspace(b.z_bottom, b.z_top, b.panels + 1)})
    rings = {}
    for z in levels:
        h = spec.half_width(z)
        rings[z] = [node(sx * h, sy * h, z) for sx, sy in CORNERS]

    # Which levels carry a face-centre node (apex of a V / LAMBDA)
    mid_levels: set[float] = set()
    for b in spec.bands:
        if b.pattern == "V":
            mid_levels.add(round(b.z_bottom, 4))
        elif b.pattern == "LAMBDA":
            mid_levels.add(round(b.z_top, 4))
    mids: dict[tuple[float, int], int] = {}
    for z in mid_levels:
        r = rings[z]
        for i in range(4):
            a, b = coord(r[i]), coord(r[(i + 1) % 4])
            mids[(z, i)] = node((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, z)

    plan_levels = {round(v, 4) for a in spec.arms for v in (a.z_bottom, a.z_top)}
    plan_levels.add(round(spec.height, 4))
    for z in levels:                                    # horizontals + plan bracing
        r = rings[z]
        group = "Horizontal (K level)" if z in mid_levels else "Horizontal"
        for i in range(4):
            if z == levels[0] and z == 0.0:
                continue                                # footing level: supports hold it
            if (z, i) in mids:
                member(r[i], mids[(z, i)], group)
                member(mids[(z, i)], r[(i + 1) % 4], group)
            else:
                member(r[i], r[(i + 1) % 4], group)
        if z in plan_levels:
            member(r[0], r[2], "Plan bracing")
            member(r[1], r[3], "Plan bracing")
        if z in mid_levels:                             # plan diaphragm for the face-centre nodes:
            for i in range(4):                          # diamond ring ...
                member(mids[(z, i)], mids[(z, (i + 1) % 4)], "Plan bracing")
            member(mids[(z, 0)], mids[(z, 2)], "Plan bracing")   # ... plus the two cross bars
            member(mids[(z, 1)], mids[(z, 3)], "Plan bracing")

    for lo, hi in zip(levels, levels[1:]):              # legs
        for i in range(4):
            group = next(g for lim, g in LEG_GROUPS if (lo + hi) / 2 < lim)
            member(rings[lo][i], rings[hi][i], group)

    for band in spec.bands:                             # face bracing
        zs = np.round(np.linspace(band.z_bottom, band.z_top, band.panels + 1), 4)
        for lo, hi in zip(zs, zs[1:]):
            a, b = rings[lo], rings[hi]
            for i in range(4):
                j = (i + 1) % 4
                if band.pattern == "X":
                    grp = "Diagonal lower" if hi <= X_LOWER_LIMIT else "Diagonal upper"
                    member(a[i], b[j], grp)
                    member(a[j], b[i], grp)
                elif band.pattern == "V":               # corners above -> centre below
                    member(b[i], mids[(lo, i)], "K-brace")
                    member(b[j], mids[(lo, i)], "K-brace")
                else:                                   # LAMBDA: centre above -> corners below
                    member(mids[(hi, i)], a[i], "K-brace")
                    member(mids[(hi, i)], a[j], "K-brace")

    top = rings[round(spec.height, 4)]
    ATTACH["Earth wire"] = list(top)

    # Crossarms: a triangular truss on each side, one in each face plane (y = ±h)
    for arm in spec.arms:
        zb, zt = round(arm.z_bottom, 4), round(arm.z_top, 4)
        for side, reach in ((-1, arm.reach_minus), (1, arm.reach_plus)):
            hb = spec.half_width(zb)
            n_bays = max(3, round((reach - hb) / spec.arm_panel_length))
            planes = []
            for sy in (-1, 1):
                bot = [node(side * hb, sy * hb, zb)]
                top_ = [node(side * spec.half_width(zt), sy * spec.half_width(zt), zt)]
                for k in range(1, n_bays + 1):
                    f = k / n_bays
                    x = hb + (reach - hb) * f
                    bot.append(node(side * x, sy * hb, zb))
                    top_.append(node(side * x, sy * hb, zb + (zt - zb) * (1 - f)))
                for k in range(n_bays):
                    member(bot[k], bot[k + 1], "Arm chord")
                    member(top_[k], top_[k + 1], "Arm chord")
                    member(top_[k], bot[k + 1], "Arm web")      # tension diagonal toward the tip
                for k in range(1, n_bays):
                    member(bot[k], top_[k], "Arm web")          # verticals
                planes.append((bot, top_))
            for pl in (0, 1):                                   # plan bracing, bottom and top
                for k in range(1, n_bays + 1):
                    p0, p1 = planes[0][pl], planes[1][pl]
                    member(p0[k], p1[k], "Arm plan bracing")
                    member(p0[k - 1], p1[k], "Arm plan bracing")
            ATTACH[f"{arm.name} {'L' if side < 0 else 'R'}"] = [
                planes[0][0][-1], planes[1][0][-1]]

    for n in rings[levels[0]]:
        s.get_node(n).support_type = SupportType.PIN
    if cable is not None:
        add_cable_load_cases(s, cable)
    return s


# ── Front-elevation preview ──────────────────────────────────────────────────

def plot_front(state: ModelState, path: Path) -> None:
    """Draw the XZ projection (the view of the published drawing) to a PNG."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(4.2, 9.6))
    for m in state.members:
        a, b = state.get_node(m.node_i), state.get_node(m.node_j)
        ax.plot([a.x, b.x], [a.z, b.z], color="black", lw=0.6)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.savefig(path, dpi=110, bbox_inches="tight")
    plt.close(fig)


def summary(state: ModelState) -> str:
    mass: dict[str, list] = {}
    for m in state.members:
        a, b = state.get_node(m.node_i), state.get_node(m.node_j)
        length = math.dist((a.x, a.y, a.z), (b.x, b.y, b.z))
        c = mass.setdefault(m.group, [0, 0.0, 0.0])
        c[0] += 1
        c[1] += length
        c[2] += length * m.A * RHO
    lines = [f"{len(state.nodes)} nodes, {len(state.members)} members\n",
             f"{'group':22s}{'section':9s}{'n':>5s}{'length m':>10s}{'mass kg':>10s}"]
    for g, (n, length, kg) in mass.items():
        lines.append(f"{g:22s}{GROUPS[g][0]:9s}{n:5d}{length:10.1f}{kg:10.0f}")
    lines.append(f"{'TOTAL':36s}{sum(v[2] for v in mass.values()):10.0f}")
    return "\n".join(lines)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--list" in sys.argv:
        for key, sp in TOWERS.items():
            widest = max(a.reach_minus + a.reach_plus for a in sp.arms)
            print(f"{key:8s} height {sp.height:5.1f} m  base {sp.leg_spacing[0][1]:5.2f} m"
                  f"  widest crossarm {widest:5.2f} m")
        raise SystemExit
    chosen = TOWERS[args[0]] if args else D30
    model = build(chosen, None if "--no-cable-loads" in sys.argv else CableAssumptions())
    out = Path(__file__).resolve().parent / f"{chosen.name.lower()}_tower_3d.slab"
    save_model(model, out)
    print(f"Wrote {out}\n{summary(model)}")
    if "--no-cable-loads" not in sys.argv:
        ld = cable_loads()
        print(f"\nCable load cases (characteristic, per phase): vertical {ld['phase']['vertical']:.1f} kN, "
              f"ice +{ld['phase']['ice']:.1f} kN, wind {ld['phase']['wind']:.1f} kN; earth wire "
              f"{ld['earth']['vertical']:.1f} / +{ld['earth']['ice']:.1f} / {ld['earth']['wind']:.1f} kN")
    if "--plot" in sys.argv:
        png = out.with_suffix(".png")
        plot_front(model, png)
        print(f"Preview: {png}")
