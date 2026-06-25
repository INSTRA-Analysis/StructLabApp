"""Preset structural models for StructLab.

Each public function returns a populated ModelState ready for the canvas.
Loads live in LoadCase objects (EN 1990): academic presets use a single
Dead/Permanent (G) case; showcase presets add Variable (Q) and Wind (W).

Convention (must match the auto-detecting engine):
  * **2D presets** keep every node at z = 0 → the engine analyses them in
    2D mode (3 DOF/node), with **Y vertical**. Downward loads are fy < 0.
  * **3D presets** set ``mode_3d`` and use a non-zero z → 6 DOF/node, with
    **Z vertical**. Downward loads are fz < 0.

Steel members are sized from the EN section library so the EC3 design table
(N_Rd, M_Rd from W_pl/W_el, utilisation η) is populated. RC members carry the
EN 1992-1-1 geometry fields (b, h, d, As, fyk) for the concrete check.
"""

from __future__ import annotations

from ui_qt.model_state import (
    ModelState, NodeData, MemberData,
    SupportType, ElementType,
    LoadCase, NodeLoad, MemberLoad, PointLoadData,
    DEFAULT_E, DEFAULT_A, DEFAULT_I,
)
from ui_qt.section_library import STEEL_PROFILES, rectangular_section

# ── Material constants ────────────────────────────────────────────────────────
_E_STEEL = 210_000_000_000.0   # Pa — EN 1993-1-1
_FY_S235 = 235_000_000.0       # Pa
_FY_S355 = 355_000_000.0       # Pa

_E_C30  = 32_000_000_000.0     # Pa — Ecm for C30/37
_E_C35  = 34_000_000_000.0     # Pa — Ecm for C35/45
_FCK_C30 = 30_000_000.0        # Pa
_FCK_C35 = 35_000_000.0        # Pa
_RHO_RC = 2500.0               # kg/m³ — reinforced concrete
_FYK_REBAR = 500_000_000.0     # Pa — B500 reinforcement

# ── Legacy section tuples (E, A, I) — kept for the parametric wizards ─────────
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

def _steel_props(name: str) -> tuple[float, float, float, float]:
    """(A, I, W_pl, W_el) for a profile name from the EN section library."""
    for _series, profiles in STEEL_PROFILES.items():
        for pname, A, I, W_pl, W_el in profiles:
            if pname == name:
                return A, I, W_pl, W_el
    raise KeyError(f"Unknown steel profile: {name!r}")


def _mb(state: ModelState, ni: int, nj: int, profile: tuple,
        udl: float = 0.0, etype: ElementType = ElementType.BEAM,
        case: LoadCase | None = None) -> MemberData:
    """Add a member from an (E, A, I) tuple and optionally assign a UDL.

    Retained for the parametric wizards; new presets prefer _msteel/_mrc.
    """
    m = state.add_member(ni, nj)
    if m is None:
        raise ValueError(f"Failed to add member {ni}→{nj}: node missing")
    m.element_type = etype
    m.E, m.A, m.I = profile
    if udl != 0.0:
        lc = case if case is not None else state.active_case
        lc.set_member_load(m.id, MemberLoad(w_start=udl, w_end=udl))
    return m


def _msteel(state: ModelState, ni: int, nj: int, name: str, *,
            etype: ElementType = ElementType.BEAM, udl: float = 0.0,
            fy: float = _FY_S355, group: str = "",
            case: LoadCase | None = None) -> MemberData:
    """Add a steel member sized from the section library (design props set)."""
    m = state.add_member(ni, nj)
    if m is None:
        raise ValueError(f"Failed to add member {ni}→{nj}: node missing")
    A, I, W_pl, W_el = _steel_props(name)
    m.E, m.A, m.I, m.I_y = _E_STEEL, A, I, I
    m.W_pl, m.W_el, m.fy = W_pl, W_el, fy
    m.element_type = etype
    if group:
        m.group = group
    if udl != 0.0:
        lc = case if case is not None else state.active_case
        lc.set_member_load(m.id, MemberLoad(w_start=udl, w_end=udl))
    return m


def _mrc(state: ModelState, ni: int, nj: int, b: float, h: float, *,
         fck: float = _FCK_C30, E: float = _E_C30, udl: float = 0.0,
         As: float = 0.0, cover: float = 0.05, group: str = "",
         case: LoadCase | None = None) -> MemberData:
    """Add a rectangular RC member with the EN 1992-1-1 design fields set."""
    m = state.add_member(ni, nj)
    if m is None:
        raise ValueError(f"Failed to add member {ni}→{nj}: node missing")
    A, I = rectangular_section(b, h)
    m.E, m.A, m.I, m.I_y = E, A, I, I
    m.fy = fck                       # material strength field = fck for concrete
    m.density = _RHO_RC
    m.b_sec, m.h_sec = b, h
    m.d_eff = h - cover
    m.As_tension, m.fyk = As, _FYK_REBAR
    m.W_el = I / (h / 2) if h > 0 else 0.0
    m.W_pl = b * h * h / 4
    if group:
        m.group = group
    if udl != 0.0:
        lc = case if case is not None else state.active_case
        lc.set_member_load(m.id, MemberLoad(w_start=udl, w_end=udl))
    return m


def _bar(state: ModelState, ni: int, nj: int, area: float, *,
         fy: float = _FY_S355, group: str = "", E: float = _E_STEEL) -> MemberData:
    """Add a pin-jointed truss bar (axial only). I is irrelevant for BARs."""
    m = state.add_member(ni, nj)
    if m is None:
        raise ValueError(f"Failed to add bar {ni}→{nj}: node missing")
    m.element_type = ElementType.BAR
    m.E, m.A, m.I, m.fy = E, area, 1e-6, fy
    if group:
        m.group = group
    return m


def _nload(state: ModelState, node_id: int, fx: float = 0.0, fy: float = 0.0,
           moment: float = 0.0, fz: float = 0.0,
           case: LoadCase | None = None) -> None:
    """Set a nodal load on a load case (default = active case)."""
    lc = case if case is not None else state.active_case
    lc.set_node_load(node_id, NodeLoad(fx=fx, fy=fy, moment=moment, fz=fz))


# ═══════════════════════════════════════════════════════════════════════════════
#  Academic / teaching presets — 2D (X-Y plane, z = 0), single G case
# ═══════════════════════════════════════════════════════════════════════════════

def simple_beam() -> ModelState:
    """Simply-supported beam — IPE 300 (S355), 6 m, 20 kN/m UDL + 30 kN midspan."""
    s = ModelState()
    n0 = s.add_node(0, 0, 0); n0.support_type = SupportType.PIN
    n1 = s.add_node(3, 0, 0)
    n2 = s.add_node(6, 0, 0); n2.support_type = SupportType.ROLLER
    _msteel(s, n0.id, n1.id, "IPE 300", udl=20_000)
    _msteel(s, n1.id, n2.id, "IPE 300", udl=20_000)
    _nload(s, n1.id, fy=-30_000)
    return s


def propped_cantilever() -> ModelState:
    """Propped cantilever — IPE 360 (S355), 6 m, 25 kN/m UDL. Fixed left, roller right."""
    s = ModelState()
    n0 = s.add_node(0, 0, 0); n0.support_type = SupportType.FIXED
    n1 = s.add_node(3, 0, 0)
    n2 = s.add_node(6, 0, 0); n2.support_type = SupportType.ROLLER
    _msteel(s, n0.id, n1.id, "IPE 360", udl=25_000)
    _msteel(s, n1.id, n2.id, "IPE 360", udl=25_000)
    return s


def gerber_beam() -> ModelState:
    """Gerber beam with an internal hinge — IPE 400 (S355), 6 m, 15 kN/m UDL."""
    s = ModelState()
    n0 = s.add_node(0, 0, 0); n0.support_type = SupportType.FIXED
    n1 = s.add_node(4, 0, 0)
    n2 = s.add_node(6, 0, 0); n2.support_type = SupportType.ROLLER
    m0 = _msteel(s, n0.id, n1.id, "IPE 400", udl=15_000)
    m0.element_type = ElementType.PIN_RIGHT   # hinge at node 1
    _msteel(s, n1.id, n2.id, "IPE 400", udl=15_000)
    return s


def continuous_beam() -> ModelState:
    """Three-span continuous beam — IPE 400 (S355), 3 × 6 m, 20 kN/m UDL."""
    s = ModelState()
    supports = [SupportType.PIN, SupportType.ROLLER,
                SupportType.ROLLER, SupportType.ROLLER]
    nodes = []
    for i, x in enumerate((0, 6, 12, 18)):
        nd = s.add_node(x, 0, 0); nd.support_type = supports[i]
        nodes.append(nd)
    for i in range(3):
        _msteel(s, nodes[i].id, nodes[i + 1].id, "IPE 400", udl=20_000)
    return s


# ═══════════════════════════════════════════════════════════════════════════════
#  Beams — design-ready (steel EC3 / concrete EC2)
# ═══════════════════════════════════════════════════════════════════════════════

def demo_beam_steel() -> ModelState:
    """Steel beam — IPE 400 (S355), 8 m SS, 15 kN/m permanent + 25 kN variable point."""
    s = ModelState()
    lc_g = s.active_case
    lc_q = s.add_load_case("Variable (Q)", category="Q")
    n0 = s.add_node(0, 0, 0); n0.support_type = SupportType.PIN
    n1 = s.add_node(4, 0, 0)
    n2 = s.add_node(8, 0, 0); n2.support_type = SupportType.ROLLER
    _msteel(s, n0.id, n1.id, "IPE 400", udl=15_000, case=lc_g)
    _msteel(s, n1.id, n2.id, "IPE 400", udl=15_000, case=lc_g)
    _nload(s, n1.id, fy=-25_000, case=lc_q)
    return s


def demo_beam_rc() -> ModelState:
    """RC continuous beam — 300 × 600 C30/37, 2 × 6 m, 30 kN/m permanent."""
    s = ModelState()
    supports = [SupportType.PIN, SupportType.ROLLER, SupportType.ROLLER]
    nodes = []
    for i, x in enumerate((0, 6, 12)):
        nd = s.add_node(x, 0, 0); nd.support_type = supports[i]
        nodes.append(nd)
    for i in range(2):
        _mrc(s, nodes[i].id, nodes[i + 1].id, 0.30, 0.60, udl=30_000, As=1.5e-3)
    return s


def design_steel_beam() -> ModelState:
    """Steel beam for the EC3 design check — IPE 360 (S355), 7 m SS, 18 kN/m."""
    s = ModelState()
    n0 = s.add_node(0, 0, 0); n0.support_type = SupportType.PIN
    n1 = s.add_node(3.5, 0, 0)
    n2 = s.add_node(7, 0, 0); n2.support_type = SupportType.ROLLER
    _msteel(s, n0.id, n1.id, "IPE 360", udl=18_000)
    _msteel(s, n1.id, n2.id, "IPE 360", udl=18_000)
    return s


def design_rc_beam() -> ModelState:
    """RC beam for the EC2 design check — 300 × 500 C30/37, 6 m SS, 25 kN/m."""
    s = ModelState()
    n0 = s.add_node(0, 0, 0); n0.support_type = SupportType.PIN
    n1 = s.add_node(3, 0, 0)
    n2 = s.add_node(6, 0, 0); n2.support_type = SupportType.ROLLER
    _mrc(s, n0.id, n1.id, 0.30, 0.50, udl=25_000, As=1.2e-3)
    _mrc(s, n1.id, n2.id, 0.30, 0.50, udl=25_000, As=1.2e-3)
    return s


# ═══════════════════════════════════════════════════════════════════════════════
#  Frames — 2D (X-Y plane, Y vertical, z = 0)
# ═══════════════════════════════════════════════════════════════════════════════

def demo_frame_steel() -> ModelState:
    """Steel portal frame — HEB 220 columns + IPE 360 rafter, 6 m × 4 m. G + Q + W."""
    s = ModelState()
    lc_g = s.active_case
    lc_q = s.add_load_case("Variable (Q)", category="Q")
    lc_w = s.add_load_case("Wind (W)", category="W")
    n0 = s.add_node(0, 0, 0); n0.support_type = SupportType.FIXED
    n1 = s.add_node(0, 4, 0)
    n2 = s.add_node(6, 4, 0)
    n3 = s.add_node(6, 0, 0); n3.support_type = SupportType.FIXED
    _msteel(s, n0.id, n1.id, "HEB 220", group="Column")
    rafter = _msteel(s, n1.id, n2.id, "IPE 360", group="Rafter")
    _msteel(s, n3.id, n2.id, "HEB 220", group="Column")
    lc_g.set_member_load(rafter.id, MemberLoad(w_start=12_000, w_end=12_000))
    lc_q.set_member_load(rafter.id, MemberLoad(w_start=10_000, w_end=10_000))
    _nload(s, n1.id, fx=15_000, case=lc_w)
    return s


def rc_moment_frame() -> ModelState:
    """RC moment frame — C30/37, 2 bays × 2 storeys (6 m bays, 3.5 m storeys)."""
    s = ModelState()
    bay, storey, n_cols, n_levels = 6.0, 3.5, 3, 3
    grid: list[list[NodeData]] = []
    for j in range(n_levels):
        row = []
        for i in range(n_cols):
            nd = s.add_node(i * bay, j * storey, 0)
            if j == 0:
                nd.support_type = SupportType.FIXED
            row.append(nd)
        grid.append(row)
    for j in range(n_levels - 1):              # columns
        for i in range(n_cols):
            _mrc(s, grid[j][i].id, grid[j + 1][i].id, 0.40, 0.40, group="Column")
    for j in range(1, n_levels):               # beams
        for i in range(n_cols - 1):
            _mrc(s, grid[j][i].id, grid[j][i + 1].id, 0.30, 0.60,
                 udl=25_000, group="Beam")
    return s


# ═══════════════════════════════════════════════════════════════════════════════
#  Trusses
# ═══════════════════════════════════════════════════════════════════════════════

def demo_truss_pratt() -> ModelState:
    """2D Pratt roof truss — SHS bars, 12 m span × 1.5 m deep, 6 panels. Grouped."""
    s = ModelState()
    span, depth, n = 12.0, 1.5, 6
    pw = span / n
    A_chord, A_web = SHS_150_8[1], SHS_150_8[1]
    bot = [s.add_node(i * pw, 0, 0)     for i in range(n + 1)]
    top = [s.add_node(i * pw, depth, 0) for i in range(n + 1)]
    bot[0].support_type = SupportType.PIN
    bot[n].support_type = SupportType.ROLLER
    for i in range(n):
        _bar(s, bot[i].id, bot[i + 1].id, A_chord, group="Bottom chord")
        _bar(s, top[i].id, top[i + 1].id, A_chord, group="Top chord")
    for i in range(n + 1):
        _bar(s, top[i].id, bot[i].id, A_web, group="Vertical")
    half = n // 2
    for i in range(half):                      # Pratt diagonals
        _bar(s, bot[i].id, top[i + 1].id, A_web, group="Diagonal")
    for i in range(half, n):
        _bar(s, bot[i + 1].id, top[i].id, A_web, group="Diagonal")
    for i in range(1, n):                       # panel loads on top chord
        _nload(s, top[i].id, fy=-20_000)
    return s


def demo_space_truss() -> ModelState:
    """3D space-truss tower — 2 × 2 m base, 3 levels × 3 m, SHS bars. Grouped."""
    s = ModelState()
    s.mode_3d = True
    w, h, levels = 2.0, 3.0, 3
    A = SHS_150_8[1]
    corners = [(-w / 2, -w / 2), (w / 2, -w / 2), (w / 2, w / 2), (-w / 2, w / 2)]
    ring: list[list[NodeData]] = []
    for lv in range(levels + 1):
        nodes = []
        for cx, cy in corners:
            nd = s.add_node(cx, cy, lv * h)
            if lv == 0:
                nd.support_type = SupportType.FIXED
            nodes.append(nd)
        ring.append(nodes)
    # plan bracing (one diagonal) at base and top rings for torsional stability
    _bar(s, ring[0][0].id, ring[0][2].id, A, group="Plan bracing")
    _bar(s, ring[levels][0].id, ring[levels][2].id, A, group="Plan bracing")
    for lv in range(levels + 1):                # horizontal rings
        for c in range(4):
            _bar(s, ring[lv][c].id, ring[lv][(c + 1) % 4].id, A, group="Horizontal")
    for lv in range(levels):                    # legs + face diagonals
        for c in range(4):
            _bar(s, ring[lv][c].id, ring[lv + 1][c].id, A, group="Leg")
            _bar(s, ring[lv][c].id, ring[lv + 1][(c + 1) % 4].id, A, group="Diagonal")
    for c in range(4):                          # gravity + lateral loads at top
        _nload(s, ring[levels][c].id, fz=-10_000)
    _nload(s, ring[levels][0].id, fx=5_000)
    return s


# ═══════════════════════════════════════════════════════════════════════════════
#  3D structures (Z vertical, fully braced)
# ═══════════════════════════════════════════════════════════════════════════════

def demo_3d_portal() -> ModelState:
    """3D portal frame — 6 × 4 m plan, 4 m tall, HEB 220 columns + IPE 360 roof beams."""
    s = ModelState()
    s.mode_3d = True
    plan = [(0, 0), (6, 0), (6, 4), (0, 4)]
    bot, top = [], []
    for x, y in plan:
        nb = s.add_node(x, y, 0); nb.support_type = SupportType.FIXED; bot.append(nb)
        top.append(s.add_node(x, y, 4))
    for i in range(4):                          # columns
        _msteel(s, bot[i].id, top[i].id, "HEB 220", group="Column")
    for i in range(4):                          # perimeter roof beams
        _msteel(s, top[i].id, top[(i + 1) % 4].id, "IPE 360", group="Roof beam")
    for nt in top:                              # roof gravity loads
        _nload(s, nt.id, fz=-30_000)
    _nload(s, top[0].id, fx=10_000)            # lateral
    return s


def demo_3d_floor_grid() -> ModelState:
    """3D floor grid — 2 × 2 bays (6 m), HEB 260 columns + IPE 300 floor beams."""
    s = ModelState()
    s.mode_3d = True
    bay, n, H = 6.0, 3, 4.0
    top: dict[tuple[int, int], NodeData] = {}
    for j in range(n):
        for i in range(n):
            nb = s.add_node(i * bay, j * bay, 0); nb.support_type = SupportType.FIXED
            nt = s.add_node(i * bay, j * bay, H)
            top[(i, j)] = nt
            _msteel(s, nb.id, nt.id, "HEB 260", group="Column")
    for j in range(n):                          # primary beams (X)
        for i in range(n - 1):
            _msteel(s, top[(i, j)].id, top[(i + 1, j)].id, "IPE 300", group="Primary")
    for j in range(n - 1):                      # secondary beams (Y)
        for i in range(n):
            _msteel(s, top[(i, j)].id, top[(i, j + 1)].id, "IPE 300", group="Secondary")
    for nt in top.values():
        _nload(s, nt.id, fz=-20_000)
    return s


# ═══════════════════════════════════════════════════════════════════════════════
#  Special — springs, mixed element types
# ═══════════════════════════════════════════════════════════════════════════════

def demo_spring_beam() -> ModelState:
    """Beam with a pinned end and an elastic (spring) support — IPE 300, 6 m, k = 1 MN/m.

    The right support is a vertical spring (k = 1 MN/m), so it settles under load
    instead of being rigid — contrast the deflected shape with simple_beam.
    """
    s = ModelState()
    n0 = s.add_node(0, 0, 0); n0.support_type = SupportType.PIN
    n1 = s.add_node(3, 0, 0)
    n2 = s.add_node(6, 0, 0)
    n2.support_type = SupportType.SPRING
    n2.spring_ky = 1_000_000.0                 # N/m — vertical (2D) spring
    _msteel(s, n0.id, n1.id, "IPE 300", udl=15_000)
    _msteel(s, n1.id, n2.id, "IPE 300", udl=15_000)
    return s


def demo_mixed() -> ModelState:
    """Mixed model — IPE 360 beam propped at midspan by an inclined SHS bar strut."""
    s = ModelState()
    n0 = s.add_node(0, 0, 0); n0.support_type = SupportType.PIN
    n1 = s.add_node(3, 0, 0)
    n2 = s.add_node(6, 0, 0); n2.support_type = SupportType.ROLLER
    n3 = s.add_node(3, -2, 0); n3.support_type = SupportType.PIN   # strut base
    _msteel(s, n0.id, n1.id, "IPE 360", udl=20_000)
    _msteel(s, n1.id, n2.id, "IPE 360", udl=20_000)
    _bar(s, n1.id, n3.id, SHS_150_8[1], group="Strut")
    return s


# ═══════════════════════════════════════════════════════════════════════════════
#  Parametric wizards (called from the wizard dialogs — keep signatures stable)
# ═══════════════════════════════════════════════════════════════════════════════

def frame_wizard(n_bays: int, n_stories: int,
                 bay_width: float, story_height: float) -> ModelState:
    """Generate a regular multi-story frame (pinned bases, no loads by default)."""
    s = ModelState()
    node_grid: list[list[NodeData]] = []
    for story in range(n_stories + 1):
        row = []
        for bay in range(n_bays + 1):
            nd = s.add_node(bay * bay_width, 0, story * story_height)
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

    n0 = s.add_node(0.0,  0.0, 0.0); n0.support_type = base_sup
    n1 = s.add_node(0.0,  0.0, height)
    n2 = s.add_node(span, 0.0, height)
    n3 = s.add_node(span, 0.0, 0.0); n3.support_type = base_sup

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

    bot = [s.add_node(i * panel_w, 0.0, 0.0)   for i in range(n_panels + 1)]
    top = [s.add_node(i * panel_w, 0.0, depth) for i in range(n_panels + 1)]

    bot[0].support_type = SupportType.PIN
    bot[n_panels].support_type = SupportType.ROLLER

    if panel_load > 0.0:
        loaded = top if load_on_top else bot
        for i in range(1, n_panels):
            _nload(s, loaded[i].id, fz=-panel_load, case=lc_q)

    def _wbar(ni: int, nj: int, profile: tuple) -> None:
        m = s.add_member(ni, nj)
        m.E, m.A, m.I = profile
        m.element_type = ElementType.BAR

    for i in range(n_panels):
        _wbar(bot[i].id, bot[i + 1].id, chord_section)
        _wbar(top[i].id, top[i + 1].id, chord_section)
    for i in range(n_panels + 1):
        _wbar(top[i].id, bot[i].id, web_section)

    n = n_panels
    half = n // 2
    if truss_type == "Pratt":
        for i in range(half):
            _wbar(bot[i].id, top[i + 1].id, web_section)
        for i in range(half, n):
            _wbar(bot[i + 1].id, top[i].id, web_section)
    elif truss_type == "Howe":
        for i in range(half):
            _wbar(top[i].id, bot[i + 1].id, web_section)
        for i in range(half, n):
            _wbar(top[i + 1].id, bot[i].id, web_section)
    else:   # Warren
        for i in range(n):
            if i % 2 == 0:
                _wbar(bot[i].id, top[i + 1].id, web_section)
            else:
                _wbar(top[i].id, bot[i + 1].id, web_section)

    return s
