"""Preset structural models for StructLab.

Each function returns a populated ModelState ready for the canvas.
Loads are stored in LoadCase objects (EN 1990). Academic presets use a
single Dead load (G) case. Showcase presets add a Wind (W) case.
"""

from __future__ import annotations

from ui_qt.model_state import (
    ModelState, NodeData, MemberData,
    SupportType, ElementType,
    LoadCase, NodeLoad, MemberLoad, PointLoadData,
    DEFAULT_E, DEFAULT_A, DEFAULT_I,
)

# ── European steel section properties (EN 10365 / EN 10210, E = 210 GPa) ──────
# Each tuple: (E [Pa], A [m²], I [m⁴])

_E_STEEL = 210_000_000_000.0   # Pa — EN 1993-1-1

IPE_300 = (_E_STEEL, 0.005381, 8.356e-5)
IPE_360 = (_E_STEEL, 0.007273, 1.627e-4)
IPE_400 = (_E_STEEL, 0.008446, 2.313e-4)
IPE_450 = (_E_STEEL, 0.009882, 3.374e-4)
IPE_500 = (_E_STEEL, 0.011600, 4.820e-4)

HEB_220 = (_E_STEEL, 0.009104, 8.091e-5)
HEB_260 = (_E_STEEL, 0.011840, 1.492e-4)
HEB_300 = (_E_STEEL, 0.014910, 2.517e-4)
HEB_340 = (_E_STEEL, 0.017090, 3.666e-4)

SHS_150_8  = (_E_STEEL, 0.004544, 1.532e-5)
SHS_200_10 = (_E_STEEL, 0.007600, 4.585e-5)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mb(state: ModelState, ni: int, nj: int, profile: tuple,
        udl: float = 0.0, etype: ElementType = ElementType.BEAM,
        case: LoadCase | None = None) -> MemberData:
    """Add a member and optionally assign a UDL to a load case."""
    m = state.add_member(ni, nj)
    if m is None:
        raise ValueError(f"Failed to add member {ni}→{nj}: node missing")
    m.element_type = etype
    m.E, m.A, m.I = profile
    if udl != 0.0:
        lc = case if case is not None else state.active_case
        lc.set_member_load(m.id, MemberLoad(w_start=udl, w_end=udl))
    return m


def _nload(state: ModelState, node_id: int, fx: float = 0.0, fy: float = 0.0,
           moment: float = 0.0, fz: float = 0.0,
           case: LoadCase | None = None) -> None:
    """Set a nodal load on a load case (default = active case)."""
    lc = case if case is not None else state.active_case
    lc.set_node_load(node_id, NodeLoad(fx=fx, fy=fy, moment=moment, fz=fz))


# ═══════════════════════════════════════════════════════════════════════════════
#  Academic / validation presets — single Dead load (G) case
# ═══════════════════════════════════════════════════════════════════════════════

def simple_beam() -> ModelState:
    """Simply-supported beam, 4 m span, P=10 kN at midspan."""
    s = ModelState()
    n0 = s.add_node(0, 0); n0.support_type = SupportType.PIN
    n1 = s.add_node(2, 0)
    n2 = s.add_node(4, 0); n2.support_type = SupportType.ROLLER
    _nload(s, n1.id, fy=-10_000.0)
    s.add_member(0, 1)
    s.add_member(1, 2)
    return s


def propped_cantilever() -> ModelState:
    """Propped cantilever, 4 m span, P=10 kN at midspan."""
    s = ModelState()
    n0 = s.add_node(0, 0); n0.support_type = SupportType.FIXED
    n1 = s.add_node(2, 0)
    n2 = s.add_node(4, 0); n2.support_type = SupportType.ROLLER
    _nload(s, n1.id, fy=-10_000.0)
    s.add_member(0, 1)
    s.add_member(1, 2)
    return s


def gerber_beam() -> ModelState:
    """Gerber beam (internal hinge). Fixed at node 0, load at hinge, roller at right."""
    s = ModelState()
    n0 = s.add_node(0, 0); n0.support_type = SupportType.FIXED
    n1 = s.add_node(3, 0)
    n2 = s.add_node(6, 0); n2.support_type = SupportType.ROLLER
    _nload(s, n1.id, fy=-10_000.0)
    m0 = s.add_member(0, 1); m0.element_type = ElementType.PIN_RIGHT
    s.add_member(1, 2)
    return s


def portal_frame() -> ModelState:
    """Single-bay portal frame, 4 m wide × 3 m tall. H=10 kN at beam-column joint."""
    s = ModelState()
    n0 = s.add_node(0, 0); n0.support_type = SupportType.PIN
    n1 = s.add_node(0, 3)
    n2 = s.add_node(4, 3)
    n3 = s.add_node(4, 0); n3.support_type = SupportType.PIN
    _nload(s, n1.id, fx=10_000.0)
    s.add_member(0, 1)
    s.add_member(1, 2)
    s.add_member(3, 2)
    return s


def mixed_beam_bar() -> ModelState:
    """Simply-supported beam with vertical bar prop at midspan (P=1 N)."""
    s = ModelState()
    n0 = s.add_node(0, 0); n0.support_type = SupportType.PIN
    n1 = s.add_node(2, 0)
    n2 = s.add_node(4, 0); n2.support_type = SupportType.ROLLER
    n3 = s.add_node(2, -2); n3.support_type = SupportType.ROLLER
    _nload(s, n1.id, fy=-1.0)
    s.add_member(0, 1)
    s.add_member(1, 2)
    bar = s.add_member(1, 3); bar.element_type = ElementType.BAR
    return s


def continuous_beam_udl() -> ModelState:
    """Two-span continuous beam, 2×8 m, UDL = 20 kN/m."""
    s = ModelState()
    spacing = 2.0
    n_nodes = 9
    nodes = [s.add_node(i * spacing, 0) for i in range(n_nodes)]
    nodes[0].support_type = SupportType.PIN
    nodes[4].support_type = SupportType.ROLLER
    nodes[8].support_type = SupportType.ROLLER
    lc = s.active_case
    for i in range(n_nodes - 1):
        m = s.add_member(nodes[i].id, nodes[i + 1].id)
        lc.set_member_load(m.id, MemberLoad(w_start=20_000.0, w_end=20_000.0))
    return s


def frame_wizard(n_bays: int, n_stories: int,
                 bay_width: float, story_height: float) -> ModelState:
    """Generate a regular multi-story frame (pinned bases, no loads by default)."""
    s = ModelState()
    node_grid: list[list[NodeData]] = []
    for story in range(n_stories + 1):
        row = []
        for bay in range(n_bays + 1):
            nd = s.add_node(bay * bay_width, story * story_height)
            if story == 0:
                nd.support_type = SupportType.PIN
            row.append(nd)
        node_grid.append(row)
    for story in range(n_stories):
        for bay in range(n_bays + 1):
            s.add_member(node_grid[story][bay].id, node_grid[story + 1][bay].id)
    for story in range(1, n_stories + 1):
        for bay in range(n_bays):
            s.add_member(node_grid[story][bay].id, node_grid[story][bay + 1].id)
    return s


# ═══════════════════════════════════════════════════════════════════════════════
#  Showcase presets — real EN 1993-1-1 profiles, separate G + W load cases
# ═══════════════════════════════════════════════════════════════════════════════

def setback_office_frame() -> ModelState:
    """6-story setback office building — S355 steel, EN 1993-1-1.

    Two load cases: Dead + imposed (G) and Wind (W).
    """
    s = ModelState()
    s.load_cases[0].name = "Gravity (G+Q)"
    lc_g = s.load_cases[0]
    lc_w = s.add_load_case("Wind (W)", category="W")

    g  = [s.add_node(x, 0.0)  for x in [0.0, 3.0, 6.0, 9.0, 12.0]]
    s1 = [s.add_node(x, 2.0)  for x in [0.0, 3.0, 6.0, 9.0, 12.0]]
    s2 = [s.add_node(x, 4.0)  for x in [0.0, 3.0, 6.0, 9.0, 12.0]]
    s3 = [s.add_node(x, 7.0)  for x in [1.5, 3.0, 6.0, 9.0, 10.5]]
    s4 = [s.add_node(x, 10.0) for x in [1.5, 3.0, 6.0, 9.0, 10.5]]
    s5 = [s.add_node(x, 13.0) for x in [1.5, 3.0, 6.0, 9.0, 10.5]]
    sr = [s.add_node(x, 16.0) for x in [3.0, 6.0, 9.0]]

    for n in g:
        n.support_type = SupportType.PIN

    # Wind loads on W case
    _nload(s, s3[1].id, fx=9_000.0,  case=lc_w)
    _nload(s, s4[1].id, fx=12_000.0, case=lc_w)
    _nload(s, s5[1].id, fx=15_000.0, case=lc_w)
    _nload(s, sr[0].id, fx=18_000.0, case=lc_w)

    # Floor beams — gravity loads on G case
    for i in range(4):
        _mb(s, g[i].id,  g[i+1].id,  IPE_360, case=lc_g)
    for i in range(4):
        _mb(s, s1[i].id, s1[i+1].id, IPE_450, 12_000.0, case=lc_g)
    for i in range(4):
        _mb(s, s2[i].id, s2[i+1].id, IPE_450, 12_000.0, case=lc_g)
    udl3 = [5_000.0, 8_000.0, 8_000.0, 5_000.0]
    for lvl in (s3, s4, s5):
        for i in range(4):
            _mb(s, lvl[i].id, lvl[i+1].id, IPE_360, udl3[i], case=lc_g)
    _mb(s, sr[0].id, sr[1].id, IPE_300, 5_000.0, case=lc_g)
    _mb(s, sr[1].id, sr[2].id, IPE_300, 5_000.0, case=lc_g)

    # Columns (no gravity UDL)
    for i in range(3):
        _mb(s, sr[i].id, s5[i+1].id, HEB_220)
    for upper, lower in [(s5, s4), (s4, s3)]:
        for k in [1, 2, 3]:
            _mb(s, upper[k].id, lower[k].id, HEB_260)
    for k in [1, 2, 3]:
        _mb(s, s3[k].id, s2[k].id, HEB_300)
    for k in range(5):
        _mb(s, s2[k].id, s1[k].id, HEB_340)
        _mb(s, s1[k].id,  g[k].id, HEB_340)

    return s


def braced_industrial_frame() -> ModelState:
    """2-story 4-bay braced industrial building — S355, K-bracing, G + W cases."""
    s = ModelState()
    s.load_cases[0].name = "Gravity (G+Q)"
    lc_g = s.load_cases[0]
    lc_w = s.add_load_case("Wind (W)", category="W")

    g  = [s.add_node(x, 0.0) for x in [0.0, 3.0, 6.0, 9.0, 12.0]]
    s1 = [s.add_node(x, 3.0) for x in [0.0, 3.0, 6.0, 9.0, 12.0]]
    s2 = [s.add_node(x, 6.0) for x in [0.0, 3.0, 6.0, 9.0, 12.0]]
    for n in g:
        n.support_type = SupportType.PIN

    _nload(s, s1[0].id, fx=55_000.0, case=lc_w)
    _nload(s, s2[0].id, fx=65_000.0, case=lc_w)

    for i in range(4):
        _mb(s, s1[i].id, s1[i+1].id, IPE_500, 15_000.0, case=lc_g)
    for i in range(4):
        _mb(s, s2[i].id, s2[i+1].id, IPE_450, 12_000.0, case=lc_g)
    for k in range(5):
        _mb(s, g[k].id,  s1[k].id, HEB_300)
        _mb(s, s1[k].id, s2[k].id, HEB_300)
    _mb(s, g[1].id,  s1[2].id, SHS_150_8, etype=ElementType.BAR)
    _mb(s, s1[1].id, s2[2].id, SHS_150_8, etype=ElementType.BAR)

    return s


def pratt_truss_bridge() -> ModelState:
    """12 m Pratt truss bridge — S355, panel loads in single G case."""
    s = ModelState()
    lc_g = s.active_case

    bot = [s.add_node(x, 0.0) for x in [0.0, 2.0, 4.0, 6.0, 8.0, 10.0, 12.0]]
    bot[0].support_type = SupportType.PIN
    bot[6].support_type = SupportType.ROLLER

    top = [s.add_node(x, 2.0) for x in [1.0, 3.0, 5.0, 7.0, 9.0, 11.0]]
    for n in top:
        _nload(s, n.id, fy=-40_000.0, case=lc_g)

    for i in range(6):
        _mb(s, bot[i].id, bot[i+1].id, SHS_200_10, etype=ElementType.BAR)
    for i in range(5):
        _mb(s, top[i].id, top[i+1].id, SHS_200_10, etype=ElementType.BAR)
    for i in range(6):
        _mb(s, top[i].id, bot[i].id,   SHS_150_8, etype=ElementType.BAR)
        _mb(s, top[i].id, bot[i+1].id, SHS_150_8, etype=ElementType.BAR)

    return s


def continuous_beam_ms() -> ModelState:
    """3-span continuous IPE 500 beam, UDL = 35 kN/m (G case)."""
    s = ModelState()
    n0 = s.add_node(0.0,  0.0); n0.support_type = SupportType.FIXED
    n1 = s.add_node(4.0,  0.0); n1.support_type = SupportType.ROLLER
    n2 = s.add_node(8.0,  0.0); n2.support_type = SupportType.ROLLER
    n3 = s.add_node(12.0, 0.0); n3.support_type = SupportType.PIN
    _mb(s, n0.id, n1.id, IPE_500, 35_000.0)
    _mb(s, n1.id, n2.id, IPE_500, 35_000.0)
    _mb(s, n2.id, n3.id, IPE_500, 35_000.0)
    return s


# ═══════════════════════════════════════════════════════════════════════════════
#  Concrete section properties (EN 1992-1-1)
# ═══════════════════════════════════════════════════════════════════════════════

_E_C30  = 32_000_000_000.0   # Pa — Ecm for C30/37
_E_C35  = 34_000_000_000.0   # Pa — Ecm for C35/45
_RHO_RC = 2500.0              # kg/m³ — reinforced concrete

# (E [Pa], A [m²], I [m⁴])
RC_COL_400    = (_E_C30, 0.160,  2.133e-3)   # 400×400 mm column
RC_BM_300x600 = (_E_C30, 0.180,  5.400e-3)   # 300×600 mm beam
RC_BRIDGE     = (_E_C35, 0.800,  1.500e-1)   # Bridge box deck (≈1.2×1.1 m equivalent)
RC_TRANSFER   = (_E_C35, 1.080,  2.916e-1)   # 600×1800 mm deep transfer beam


# ═══════════════════════════════════════════════════════════════════════════════
#  New showcase presets — steel + concrete case studies
# ═══════════════════════════════════════════════════════════════════════════════

def steel_industrial_portal() -> ModelState:
    """Single-bay fixed-base steel portal frame — S355, 14 m × 7 m.

    HEB 340 columns, IPE 500 rafter. Classic industrial portal proportions.
    Three load cases: Roof dead G (10 kN/m), Snow Q (5 kN/m),
    Wind W (40 kN lateral at eave + 3 kN/m roof uplift).
    """
    s = ModelState()
    s.load_cases[0].name = "Roof Dead (G)"
    lc_g = s.load_cases[0]
    lc_q = s.add_load_case("Snow (Q)", category="Q")
    lc_w = s.add_load_case("Wind (W)", category="W")

    n0 = s.add_node(0.0,  0.0); n0.support_type = SupportType.FIXED
    n1 = s.add_node(0.0,  7.0)   # left eave
    n2 = s.add_node(14.0, 7.0)   # right eave
    n3 = s.add_node(14.0, 0.0); n3.support_type = SupportType.FIXED

    _mb(s, n0.id, n1.id, HEB_340)                                # left column
    rafter = _mb(s, n1.id, n2.id, IPE_500, udl=10_000.0, case=lc_g)  # rafter
    _mb(s, n2.id, n3.id, HEB_340)                                # right column

    # Snow on rafter
    lc_q.set_member_load(rafter.id, MemberLoad(w_start=5_000.0, w_end=5_000.0))
    # Wind: lateral force at windward eave + uplift on rafter
    _nload(s, n1.id, fx=40_000.0, case=lc_w)
    lc_w.set_member_load(rafter.id, MemberLoad(w_start=-3_000.0, w_end=-3_000.0))

    return s


def steel_cantilevered_canopy() -> ModelState:
    """Steel cantilevered canopy — S355, back-span 6 m + cantilever 5 m.

    Fixed to wall at left end, prop column at 6 m, free tip at 11 m.
    Wind uplift modelled as a linearly varying load (UVL) — zero at the wall,
    increasing to 4 kN/m (upward) at the free tip. Demonstrates UVL input.
    Load cases: Dead G (4 kN/m), Snow Q (3.5 kN/m), Wind uplift W (UVL).
    """
    s = ModelState()
    s.load_cases[0].name = "Dead (G)"
    lc_g = s.load_cases[0]
    lc_q = s.add_load_case("Snow (Q)", category="Q")
    lc_w = s.add_load_case("Wind uplift (W)", category="W")

    n0 = s.add_node(0.0,  0.0); n0.support_type = SupportType.FIXED  # wall
    n1 = s.add_node(6.0,  0.0); n1.support_type = SupportType.ROLLER  # prop
    n2 = s.add_node(11.0, 0.0)                                          # free tip

    back = _mb(s, n0.id, n1.id, IPE_400, udl=4_000.0, case=lc_g)
    cant = _mb(s, n1.id, n2.id, IPE_400, udl=4_000.0, case=lc_g)

    # Snow: uniform across both spans
    lc_q.set_member_load(back.id, MemberLoad(w_start=3_500.0, w_end=3_500.0))
    lc_q.set_member_load(cant.id, MemberLoad(w_start=3_500.0, w_end=3_500.0))

    # Wind uplift: linearly increasing from 0 at wall to −4 kN/m at tip (negative = upward)
    lc_w.set_member_load(back.id, MemberLoad(w_start=0.0,        w_end=-2_000.0))
    lc_w.set_member_load(cant.id, MemberLoad(w_start=-2_000.0,   w_end=-4_000.0))

    return s


def steel_vierendeel_bridge() -> ModelState:
    """Steel Vierendeel pedestrian bridge — S355, 15 m span, 5 panels × 3 m.

    No diagonals: all shear is carried by bending in chords and verticals.
    SHS 200×10 chords, HEB 220 verticals (all BEAM — rigid connections).
    Supported on bottom chord at both ends.
    Load case: Pedestrian load Q (5 kN/m on each bottom chord span).
    """
    s = ModelState()
    s.load_cases[0].name = "Pedestrian Load (Q)"
    s.load_cases[0].category = "Q"
    lc_q = s.load_cases[0]

    pw, ph = 3.0, 2.0   # panel width, height

    bot = [s.add_node(i * pw, 0.0) for i in range(6)]
    top = [s.add_node(i * pw, ph) for i in range(6)]

    bot[0].support_type = SupportType.PIN
    bot[5].support_type = SupportType.ROLLER

    # Bottom chord — pedestrian live load
    for i in range(5):
        m = _mb(s, bot[i].id, bot[i + 1].id, SHS_200_10)
        lc_q.set_member_load(m.id, MemberLoad(w_start=5_000.0, w_end=5_000.0))

    # Top chord
    for i in range(5):
        _mb(s, top[i].id, top[i + 1].id, SHS_200_10)

    # Verticals — HEB 220 for Vierendeel bending capacity (all BEAM connections)
    for i in range(6):
        _mb(s, bot[i].id, top[i].id, HEB_220)

    return s


def rc_moment_frame() -> ModelState:
    """2-bay × 2-storey reinforced concrete moment frame — C30/37.

    Columns 400×400 mm, beams 300×600 mm. Fixed column bases.
    Load cases: Permanent G (12 kN/m slab + finishes), Variable Q (6 kN/m imposed),
    Wind W (increasing with height on windward side).
    """
    s = ModelState()
    s.load_cases[0].name = "Permanent (G)"
    lc_g = s.load_cases[0]
    lc_q = s.add_load_case("Variable (Q)", category="Q")
    lc_w = s.add_load_case("Wind (W)", category="W")

    bw, sh = 7.0, 3.5
    grid = [[s.add_node(col * bw, row * sh) for col in range(3)] for row in range(3)]

    for n in grid[0]:
        n.support_type = SupportType.FIXED

    # Columns — RC density
    for row in range(2):
        for col in range(3):
            m = _mb(s, grid[row][col].id, grid[row + 1][col].id, RC_COL_400)
            m.density = _RHO_RC

    # Beams — dead on G, imposed on Q
    for row in range(1, 3):
        for col in range(2):
            m = _mb(s, grid[row][col].id, grid[row][col + 1].id,
                    RC_BM_300x600, udl=12_000.0, case=lc_g)
            m.density = _RHO_RC
            lc_q.set_member_load(m.id, MemberLoad(w_start=6_000.0, w_end=6_000.0))

    # Wind: increasing with height on windward (left) side
    _nload(s, grid[1][0].id, fx=15_000.0, case=lc_w)
    _nload(s, grid[2][0].id, fx=25_000.0, case=lc_w)

    return s


def rc_transfer_beam() -> ModelState:
    """RC transfer beam — C35/45, 15 m span, 600×1800 mm deep section.

    Models a basement-level transfer structure receiving three heavy column
    loads (800 kN each) from the superstructure above, applied as mid-member
    point loads at 4 m, 7.5 m and 11 m along the span.
    Load cases: Slab dead G (25 kN/m), Column loads from above Q (3 × 800 kN).
    """
    s = ModelState()
    s.load_cases[0].name = "Slab Dead (G)"
    lc_g = s.load_cases[0]
    lc_q = s.add_load_case("Column loads — superstructure (Q)", category="Q")

    n0 = s.add_node(0.0,  0.0); n0.support_type = SupportType.PIN
    n1 = s.add_node(15.0, 0.0); n1.support_type = SupportType.ROLLER

    beam = _mb(s, n0.id, n1.id, RC_TRANSFER, udl=25_000.0, case=lc_g)
    beam.density = _RHO_RC

    # Three column loads as point loads at fractional positions (0–1)
    lc_q.set_member_load(beam.id, MemberLoad(
        w_start=0.0, w_end=0.0,
        point_loads=[
            PointLoadData(load_type="FORCE", position=4.0  / 15.0, magnitude=800_000.0),
            PointLoadData(load_type="FORCE", position=7.5  / 15.0, magnitude=800_000.0),
            PointLoadData(load_type="FORCE", position=11.0 / 15.0, magnitude=800_000.0),
        ],
    ))

    return s


def rc_continuous_bridge() -> ModelState:
    """4-span continuous RC bridge deck — C35/45, 4 × 10 m = 40 m total.

    Equivalent box-section deck (A = 0.8 m², I = 0.15 m⁴).
    Fixed left abutment, roller intermediate piers, pin right abutment.
    Load cases: Permanent G (self-weight + surfacing 25 kN/m),
    Traffic Q (EN 1991-2 LM1-type 45 kN/m) — pattern loading applies.
    """
    s = ModelState()
    s.load_cases[0].name = "Permanent (G)"
    lc_g = s.load_cases[0]
    lc_q = s.add_load_case("Traffic (Q)", category="Q")

    nodes = [s.add_node(i * 10.0, 0.0) for i in range(5)]
    nodes[0].support_type = SupportType.FIXED
    nodes[1].support_type = SupportType.ROLLER
    nodes[2].support_type = SupportType.ROLLER
    nodes[3].support_type = SupportType.ROLLER
    nodes[4].support_type = SupportType.PIN

    for i in range(4):
        m = _mb(s, nodes[i].id, nodes[i + 1].id, RC_BRIDGE, udl=25_000.0, case=lc_g)
        m.density = _RHO_RC
        lc_q.set_member_load(m.id, MemberLoad(w_start=45_000.0, w_end=45_000.0))

    return s


RC_BM_300x500 = (_E_C30, 0.150, 3.125e-3)   # 300×500 mm beam (C30/37)


# ═══════════════════════════════════════════════════════════════════════════════
#  Demo presets — one or two curated examples per structural type
# ═══════════════════════════════════════════════════════════════════════════════

def demo_beam_steel() -> ModelState:
    """Simply-supported IPE 400 steel beam — 8 m span, G + Q.

    Dead G: 12 kN/m full-span UDL (roof dead + finishes).
    Imposed Q: 8 kN/m UDL + 50 kN point load at midspan.
    """
    s = ModelState()
    s.load_cases[0].name = "Dead (G)"
    lc_g = s.load_cases[0]
    lc_q = s.add_load_case("Imposed (Q)", category="Q")

    n0 = s.add_node(0.0, 0.0); n0.support_type = SupportType.PIN
    n1 = s.add_node(4.0, 0.0)   # midspan node for point load
    n2 = s.add_node(8.0, 0.0); n2.support_type = SupportType.ROLLER

    m0 = _mb(s, n0.id, n1.id, IPE_400, udl=12_000.0, case=lc_g)
    m1 = _mb(s, n1.id, n2.id, IPE_400, udl=12_000.0, case=lc_g)
    lc_q.set_member_load(m0.id, MemberLoad(w_start=8_000.0, w_end=8_000.0))
    lc_q.set_member_load(m1.id, MemberLoad(w_start=8_000.0, w_end=8_000.0))
    _nload(s, n1.id, fy=-50_000.0, case=lc_q)
    return s


def demo_beam_rc() -> ModelState:
    """RC propped cantilever — C30/37, 300×500 mm, 6 m span.

    Fixed at wall, roller at free end. Typical floor beam cross-section.
    Dead G: 15 kN/m (slab weight + finishes). Imposed Q: 10 kN/m.
    """
    s = ModelState()
    s.load_cases[0].name = "Dead (G)"
    lc_g = s.load_cases[0]
    lc_q = s.add_load_case("Imposed (Q)", category="Q")

    n0 = s.add_node(0.0, 0.0); n0.support_type = SupportType.FIXED
    n1 = s.add_node(6.0, 0.0); n1.support_type = SupportType.ROLLER

    m = _mb(s, n0.id, n1.id, RC_BM_300x500, udl=15_000.0, case=lc_g)
    m.density = _RHO_RC
    lc_q.set_member_load(m.id, MemberLoad(w_start=10_000.0, w_end=10_000.0))
    return s


def demo_gerber() -> ModelState:
    """Gerber beam (internal hinge) — IPE 360 steel, 10 m.

    Fixed at wall (x=0), Gerber hinge + roller at x=5 m, roller at x=10 m.
    The internal hinge creates a Gerber beam (statically determinate).
    """
    s = ModelState()
    s.load_cases[0].name = "Dead + Imposed (G+Q)"
    lc = s.load_cases[0]

    n0 = s.add_node(0.0,  0.0); n0.support_type = SupportType.FIXED
    n1 = s.add_node(5.0,  0.0); n1.support_type = SupportType.ROLLER   # Gerber hinge with roller
    n2 = s.add_node(10.0, 0.0); n2.support_type = SupportType.ROLLER

    m0 = _mb(s, n0.id, n1.id, IPE_360, udl=20_000.0, case=lc)
    m0.element_type = ElementType.PIN_RIGHT   # moment release at hinge node n1
    _mb(s, n1.id, n2.id, IPE_360, udl=20_000.0, case=lc)
    return s


def demo_frame_steel() -> ModelState:
    """Fixed-base steel portal frame — S355, 10 m × 5 m.

    HEB 260 columns, IPE 450 rafter. Three load cases:
    Dead G: 12 kN/m on rafter.  Snow Q: 8 kN/m on rafter.
    Wind W: 50 kN lateral at windward eave.
    """
    s = ModelState()
    s.load_cases[0].name = "Dead (G)"
    lc_g = s.load_cases[0]
    lc_q = s.add_load_case("Snow (Q)", category="Q")
    lc_w = s.add_load_case("Wind (W)", category="W")

    n0 = s.add_node(0.0,  0.0); n0.support_type = SupportType.FIXED
    n1 = s.add_node(0.0,  5.0)   # left eave
    n2 = s.add_node(10.0, 5.0)   # right eave
    n3 = s.add_node(10.0, 0.0); n3.support_type = SupportType.FIXED

    _mb(s, n0.id, n1.id, HEB_260)
    rafter = _mb(s, n1.id, n2.id, IPE_450, udl=12_000.0, case=lc_g)
    _mb(s, n3.id, n2.id, HEB_260)

    lc_q.set_member_load(rafter.id, MemberLoad(w_start=8_000.0, w_end=8_000.0))
    _nload(s, n1.id, fx=50_000.0, case=lc_w)
    return s


def demo_frame_rc() -> ModelState:
    """RC moment frame — C30/37, 2-bay × 3-storey, fixed bases.

    Columns 400×400 mm, beams 300×600 mm. Bay width 6 m, storey height 3 m.
    Dead G: 14 kN/m on beams.  Imposed Q: 7 kN/m.
    Wind W: increasing floor forces on the windward (left) side.
    """
    s = ModelState()
    s.load_cases[0].name = "Dead (G)"
    lc_g = s.load_cases[0]
    lc_q = s.add_load_case("Imposed (Q)", category="Q")
    lc_w = s.add_load_case("Wind (W)", category="W")

    bw, sh = 6.0, 3.0
    grid = [[s.add_node(col * bw, row * sh) for col in range(3)] for row in range(4)]

    for n in grid[0]:
        n.support_type = SupportType.FIXED

    for row in range(3):
        for col in range(3):
            m = _mb(s, grid[row][col].id, grid[row + 1][col].id, RC_COL_400)
            m.density = _RHO_RC

    for row in range(1, 4):
        for col in range(2):
            m = _mb(s, grid[row][col].id, grid[row][col + 1].id,
                    RC_BM_300x600, udl=14_000.0, case=lc_g)
            m.density = _RHO_RC
            lc_q.set_member_load(m.id, MemberLoad(w_start=7_000.0, w_end=7_000.0))

    _nload(s, grid[1][0].id, fx=12_000.0, case=lc_w)
    _nload(s, grid[2][0].id, fx=18_000.0, case=lc_w)
    _nload(s, grid[3][0].id, fx=22_000.0, case=lc_w)
    return s


def demo_truss_pratt() -> ModelState:
    """8-panel Pratt roof truss — S355, 16 m span, 2 m depth.

    SHS 200×10 top/bottom chords, SHS 150×8 verticals and diagonals (all BAR).
    Pratt arrangement: left-half diagonals B[i]→T[i+1], right-half T[i]→B[i+1].
    Under gravity: diagonals in tension, verticals in compression.
    Q: 30 kN at each interior top-chord panel point (purlin reactions).
    """
    s = ModelState()
    s.load_cases[0].name = "Roof Loads (Q)"
    s.load_cases[0].category = "Q"
    lc_q = s.load_cases[0]

    panel_w, depth, n = 2.0, 2.0, 8

    bot = [s.add_node(i * panel_w, 0.0)   for i in range(n + 1)]
    top = [s.add_node(i * panel_w, depth) for i in range(n + 1)]

    bot[0].support_type = SupportType.PIN
    bot[n].support_type = SupportType.ROLLER

    for i in range(1, n):
        _nload(s, top[i].id, fy=-30_000.0, case=lc_q)

    for i in range(n):
        _mb(s, bot[i].id, bot[i + 1].id, SHS_200_10, etype=ElementType.BAR)
        _mb(s, top[i].id, top[i + 1].id, SHS_200_10, etype=ElementType.BAR)
    for i in range(n + 1):
        _mb(s, top[i].id, bot[i].id, SHS_150_8, etype=ElementType.BAR)

    half = n // 2
    for i in range(half):
        _mb(s, bot[i].id, top[i + 1].id, SHS_150_8, etype=ElementType.BAR)
    for i in range(half, n):
        _mb(s, bot[i + 1].id, top[i].id, SHS_150_8, etype=ElementType.BAR)

    return s


def demo_mixed() -> ModelState:
    """Mixed beam + vertical bar strut — IPE 360 beam, SHS 150×8 prop.

    Simply-supported IPE 360 beam (12 m), mid-propped at 6 m by a vertical
    SHS 150×8 bar anchored 3 m below at a pin support.
    Demonstrates mixed BEAM + BAR element types in one model.
    Dead G: 20 kN/m UDL over full beam.
    """
    s = ModelState()
    s.load_cases[0].name = "Dead (G)"
    lc_g = s.load_cases[0]

    n0 = s.add_node(0.0,  0.0); n0.support_type = SupportType.PIN
    n1 = s.add_node(6.0,  0.0)   # beam midspan — top of strut
    n2 = s.add_node(12.0, 0.0); n2.support_type = SupportType.ROLLER
    n3 = s.add_node(6.0, -3.0); n3.support_type = SupportType.PIN   # strut base

    _mb(s, n0.id, n1.id, IPE_360, udl=20_000.0, case=lc_g)
    _mb(s, n1.id, n2.id, IPE_360, udl=20_000.0, case=lc_g)
    strut = s.add_member(n1.id, n3.id)
    strut.element_type = ElementType.BAR
    strut.E, strut.A, strut.I = SHS_150_8
    return s


def demo_spring_beam() -> ModelState:
    """Steel beam on elastic intermediate support — IPE 300, 2 × 5 m.

    PIN at left end, elastic spring (k = 1 MN/m) at midpoint, ROLLER at right.
    A spring stiffness of 1 MN/m represents a flexible pile or pad foundation.
    Shows moment redistribution vs. a fully rigid intermediate support.
    Imposed Q: 12 kN/m UDL over full span.
    """
    s = ModelState()
    s.load_cases[0].name = "Imposed (Q)"
    s.load_cases[0].category = "Q"
    lc_q = s.load_cases[0]

    n0 = s.add_node(0.0,  0.0); n0.support_type = SupportType.PIN
    n1 = s.add_node(5.0,  0.0)
    n2 = s.add_node(10.0, 0.0); n2.support_type = SupportType.ROLLER

    n1.support_type = SupportType.SPRING
    n1.spring_ky    = 1_000_000.0   # 1 MN/m

    m0 = _mb(s, n0.id, n1.id, IPE_300, udl=12_000.0, case=lc_q)
    _mb(s, n1.id, n2.id, IPE_300, udl=12_000.0, case=lc_q)
    return s


def demo_wind_portal_qx() -> ModelState:
    """Fixed-base steel portal frame — wind as distributed lateral pressure on columns.

    Geometry: 12 m wide × 6 m tall. HEB 300 columns, IPE 500 rafter.

    Load cases:
      Dead G   : 10 kN/m gravity UDL on rafter.
      Snow Q   : 6 kN/m downward UDL on rafter.
      Wind W   : EN 1991-1-4 inspired — wind pressure on windward column
                 and suction on leeward column, both linearly varying
                 with height (base → eave), plus 2 kN/m uplift on rafter.
                 Windward (left) column : qx = 2.0 kN/m (base) → 3.5 kN/m (eave)
                 Leeward  (right) column: qx = −0.8 kN/m (base) → −1.4 kN/m (eave)
                 Rafter uplift          : w  = −2.0 kN/m (upward)

    The distributed lateral load on the columns is modelled using qx_start /
    qx_end — the global-X distributed load.  Compare with demo_frame_steel
    which uses a single nodal force at the eave.  With the default n_sub = 10,
    the trapezoidal tributary-area integration is already well converged.
    """
    s = ModelState()
    s.load_cases[0].name = "Dead (G)"
    lc_g = s.load_cases[0]
    lc_q = s.add_load_case("Snow (Q)",  category="Q")
    lc_w = s.add_load_case("Wind (W)",  category="W")

    # ── geometry ──────────────────────────────────────────────────────────────
    n0 = s.add_node(0.0,  0.0); n0.support_type = SupportType.FIXED   # left base
    n1 = s.add_node(0.0,  6.0)                                          # left eave
    n2 = s.add_node(12.0, 6.0)                                          # right eave
    n3 = s.add_node(12.0, 0.0); n3.support_type = SupportType.FIXED   # right base

    # ── members ───────────────────────────────────────────────────────────────
    left_col  = _mb(s, n0.id, n1.id, HEB_300)
    rafter    = _mb(s, n1.id, n2.id, IPE_500, udl=10_000.0, case=lc_g)
    right_col = _mb(s, n2.id, n3.id, HEB_300)   # note: node_i = eave, node_j = base

    # ── snow on rafter ─────────────────────────────────────────────────────────
    lc_q.set_member_load(rafter.id, MemberLoad(w_start=6_000.0, w_end=6_000.0))

    # ── wind: distributed lateral load on columns + rafter uplift ─────────────
    # Left (windward) column goes from n0 (base, y=0) to n1 (eave, y=6).
    # node_i = base → qx_start applies at base; node_j = eave → qx_end at eave.
    lc_w.set_member_load(left_col.id, MemberLoad(
        qx_start=2_000.0,   # N/m at base
        qx_end  =3_500.0,   # N/m at eave  (increasing wind pressure with height)
    ))

    # Right (leeward) column goes from n2 (eave) to n3 (base).
    # node_i = eave → qx_start applies at eave; node_j = base → qx_end at base.
    # Suction is negative (leftward): larger magnitude at eave, smaller at base.
    lc_w.set_member_load(right_col.id, MemberLoad(
        qx_start=-1_400.0,  # N/m at eave  (suction, leftward)
        qx_end  = -800.0,   # N/m at base
    ))

    # Rafter: roof uplift (negative w = upward)
    lc_w.set_member_load(rafter.id, MemberLoad(w_start=-2_000.0, w_end=-2_000.0))

    return s


# ═══════════════════════════════════════════════════════════════════════════════
#  Wizard builder functions — called by parameterised wizard dialogs
# ═══════════════════════════════════════════════════════════════════════════════

def beam_wizard(
    spans: list,
    support_types: list,
    E: float, A: float, I: float,
    udl_g: float = 0.0,
    udl_q: float = 0.0,
    point_q: float = 0.0,
    density: float = 0.0,
) -> ModelState:
    """Build a beam from wizard parameters.

    spans:         span lengths [m]. N spans → N+1 nodes.
    support_types: SupportType name per node (length N+1).
    udl_g:         permanent G UDL [N/m, downward positive]; 0 = omit G case loads.
    udl_q:         variable Q UDL [N/m]; 0 = omit.
    point_q:       midspan point load on central span in Q case [N]; 0 = omit.
    """
    s = ModelState()
    s.load_cases[0].name = "Permanent (G)"
    lc_g = s.load_cases[0]
    needs_q = udl_q > 0.0 or point_q > 0.0
    lc_q = s.add_load_case("Variable (Q)", category="Q") if needs_q else None

    x = 0.0
    nodes = []
    for i, sup in enumerate(support_types):
        nd = s.add_node(x, 0.0)
        nd.support_type = SupportType[sup]
        nodes.append(nd)
        if i < len(spans):
            x += spans[i]

    members = []
    for i in range(len(spans)):
        m = s.add_member(nodes[i].id, nodes[i + 1].id)
        m.E, m.A, m.I = E, A, I
        m.density = density
        members.append(m)
        if udl_g > 0.0:
            lc_g.set_member_load(m.id, MemberLoad(w_start=udl_g, w_end=udl_g))
        if lc_q and udl_q > 0.0:
            lc_q.set_member_load(m.id, MemberLoad(w_start=udl_q, w_end=udl_q))

    if lc_q and point_q > 0.0:
        mid_idx = len(members) // 2
        ml = lc_q.get_member_load(members[mid_idx].id)
        lc_q.set_member_load(members[mid_idx].id, MemberLoad(
            w_start=ml.w_start, w_end=ml.w_end,
            point_loads=list(ml.point_loads) + [
                PointLoadData(load_type="FORCE", position=0.5, magnitude=point_q)
            ],
        ))

    return s


def portal_wizard(
    span: float,
    height: float,
    fixed_base: bool,
    E_col: float, A_col: float, I_col: float,
    E_raf: float, A_raf: float, I_raf: float,
    udl_g: float = 0.0,
    udl_q: float = 0.0,
    wind_h: float = 0.0,
) -> ModelState:
    """Build a single-bay portal frame from wizard parameters.

    fixed_base: True = FIXED column bases, False = PIN.
    udl_g / udl_q: rafter UDL [N/m, downward positive].
    wind_h: lateral point load at windward eave [N, positive = left→right].
    """
    s = ModelState()
    s.load_cases[0].name = "Permanent (G)"
    lc_g = s.load_cases[0]
    lc_q = s.add_load_case("Variable (Q)", category="Q") if udl_q > 0.0 else None
    lc_w = s.add_load_case("Wind (W)", category="W") if wind_h != 0.0 else None

    base_sup = SupportType.FIXED if fixed_base else SupportType.PIN

    n0 = s.add_node(0.0,   0.0); n0.support_type = base_sup
    n1 = s.add_node(0.0,   height)
    n2 = s.add_node(span,  height)
    n3 = s.add_node(span,  0.0); n3.support_type = base_sup

    col_profile = (E_col, A_col, I_col)
    raf_profile = (E_raf, A_raf, I_raf)

    _mb(s, n0.id, n1.id, col_profile)
    rafter = _mb(s, n1.id, n2.id, raf_profile)
    _mb(s, n3.id, n2.id, col_profile)

    if udl_g > 0.0:
        lc_g.set_member_load(rafter.id, MemberLoad(w_start=udl_g, w_end=udl_g))
    if lc_q and udl_q > 0.0:
        lc_q.set_member_load(rafter.id, MemberLoad(w_start=udl_q, w_end=udl_q))
    if lc_w and wind_h != 0.0:
        _nload(s, n1.id, fx=wind_h, case=lc_w)

    return s


def truss_wizard(
    truss_type: str,
    n_panels: int,
    span: float,
    depth: float,
    chord_section: tuple,
    web_section: tuple,
    panel_load: float = 0.0,
    load_on_top: bool = True,
) -> ModelState:
    """Build a flat-chord truss from wizard parameters.

    truss_type:    "Pratt" (tension diagonals), "Warren" (alternating),
                   "Howe" (compression diagonals).
    n_panels:      number of panels (≥ 2; even recommended for Pratt/Howe).
    chord_section: (E, A, I) tuple for top and bottom chords.
    web_section:   (E, A, I) tuple for verticals and diagonals.
    panel_load:    vertical point load [N] at each interior loaded-chord node.
    load_on_top:   True = loads on top chord (roof), False = on bottom (bridge).
    """
    s = ModelState()
    s.load_cases[0].name = "Panel Loads (Q)"
    s.load_cases[0].category = "Q"
    lc_q = s.load_cases[0]

    panel_w = span / n_panels

    bot = [s.add_node(i * panel_w, 0.0)   for i in range(n_panels + 1)]
    top = [s.add_node(i * panel_w, depth) for i in range(n_panels + 1)]

    bot[0].support_type = SupportType.PIN
    bot[n_panels].support_type = SupportType.ROLLER

    if panel_load > 0.0:
        loaded = top if load_on_top else bot
        for i in range(1, n_panels):
            _nload(s, loaded[i].id, fy=-panel_load, case=lc_q)

    def _bar(ni: int, nj: int, profile: tuple) -> None:
        m = s.add_member(ni, nj)
        m.E, m.A, m.I = profile
        m.element_type = ElementType.BAR

    for i in range(n_panels):
        _bar(bot[i].id, bot[i + 1].id, chord_section)
        _bar(top[i].id, top[i + 1].id, chord_section)
    for i in range(n_panels + 1):
        _bar(top[i].id, bot[i].id, web_section)

    n = n_panels
    half = n // 2
    if truss_type == "Pratt":
        for i in range(half):
            _bar(bot[i].id, top[i + 1].id, web_section)
        for i in range(half, n):
            _bar(bot[i + 1].id, top[i].id, web_section)
    elif truss_type == "Howe":
        for i in range(half):
            _bar(top[i].id, bot[i + 1].id, web_section)
        for i in range(half, n):
            _bar(top[i + 1].id, bot[i].id, web_section)
    else:   # Warren
        for i in range(n):
            if i % 2 == 0:
                _bar(bot[i].id, top[i + 1].id, web_section)
            else:
                _bar(top[i].id, bot[i + 1].id, web_section)

    return s


# ═══════════════════════════════════════════════════════════════════════════════
#  3D Presets — spatial structures with non-zero z coordinates
# ═══════════════════════════════════════════════════════════════════════════════

def demo_3d_portal() -> ModelState:
    """3D portal frame — 6 m span × 4 m height × 3 m depth.

    Two parallel portal frames connected by roof purlins.
    S355 steel, IPE 360 beams, HEB 220 columns.
    Coordinate convention: X,Y = ground, Z = up.
    Dead G: 15 kN/m on roof beams. Wind W: 8 kN lateral at eaves.
    """
    s = ModelState()
    s.load_cases[0].name = "Dead (G)"
    lc_g = s.load_cases[0]
    lc_w = s.add_load_case("Wind (W)", category="W")

    w, h, d = 6.0, 4.0, 3.0  # span, height, depth

    # Front frame (y=0): columns in XZ plane
    n0 = s.add_node(0, 0, 0); n0.support_type = SupportType.FIXED
    n1 = s.add_node(0, 0, h)                    # left column top
    n2 = s.add_node(w, 0, h)                    # right column top
    n3 = s.add_node(w, 0, 0); n3.support_type = SupportType.FIXED

    # Back frame (y=d): columns in XZ plane
    n4 = s.add_node(0, d, 0); n4.support_type = SupportType.FIXED
    n5 = s.add_node(0, d, h)
    n6 = s.add_node(w, d, h)
    n7 = s.add_node(w, d, 0); n7.support_type = SupportType.FIXED

    _mb(s, n0.id, n1.id, HEB_260)
    _mb(s, n1.id, n2.id, IPE_360, udl=15_000.0, case=lc_g)
    _mb(s, n3.id, n2.id, HEB_260)
    _mb(s, n4.id, n5.id, HEB_260)
    _mb(s, n5.id, n6.id, IPE_360, udl=15_000.0, case=lc_g)
    _mb(s, n7.id, n6.id, HEB_260)

    # Roof purlins (along Y, connecting front to back) — continuous connection
    for ni, nj in [(n1, n5), (n2, n6)]:
        purlin = s.add_member(ni.id, nj.id)
        purlin.E, purlin.A, purlin.I = IPE_300
        purlin.element_type = ElementType.BEAM

    _nload(s, n1.id, fx=4_000.0, case=lc_w)
    _nload(s, n2.id, fx=4_000.0, case=lc_w)
    s.mode_3d = True
    return s


def demo_space_truss() -> ModelState:
    """Space truss tower — 2 m × 2 m base (XY), 4 m tall (Z), 4 panels.

    SHS chords (BAR elements).  Vertical load 20 kN at top corners.
    Coordinate convention: X,Y = ground, Z = up.
    """
    s = ModelState()
    s.load_cases[0].name = "Gravity (G)"
    lc = s.load_cases[0]

    h, d = 4.0, 2.0  # height (Z), base width (XY)
    n_panels = 4
    panel_h = h / n_panels

    CHORD = (_E_STEEL, 0.004544, 1.532e-5)
    WEB   = (_E_STEEL, 0.001870, 1.202e-6)

    def _bar(st, ni, nj, prof):
        m = st.add_member(ni, nj)
        m.E, m.A, m.I = prof
        m.element_type = ElementType.BAR
        return m

    levels = []
    for lev in range(n_panels + 1):
        z = lev * panel_h                       # elevation
        nds = [s.add_node(0, 0, z),             # front-left  (X,Y,Z)
               s.add_node(d, 0, z),             # front-right
               s.add_node(d, d, z),             # back-right
               s.add_node(0, d, z)]             # back-left
        if lev == 0:
            for nd in nds:
                nd.support_type = SupportType.PIN
        levels.append(nds)

    for lev in range(n_panels):
        for i in range(4):
            _bar(s, levels[lev][i].id, levels[lev + 1][i].id, CHORD)
    for lev in range(n_panels + 1):
        nds = levels[lev]
        for i in range(4):
            _bar(s, nds[i].id, nds[(i + 1) % 4].id, WEB)
    for lev in range(n_panels):
        cur, nxt = levels[lev], levels[lev + 1]
        for i in range(4):
            _bar(s, cur[i].id, nxt[(i + 1) % 4].id, WEB)

    # Vertical (gravity) load distributed to top corner nodes — fz = global Z
    for nd in levels[-1]:
        _nload(s, nd.id, fz=-5_000.0)
    s.mode_3d = True
    return s
