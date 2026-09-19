"""Parametric model generators for StructLab's wizard dialogs.

Each public function returns a populated ModelState ready for the canvas.
These are called from the Beam / Portal Frame / Truss / Frame wizard dialogs
in wizards.py (keep the function signatures stable — the dialogs call them
by name). Section/material data comes from the caller (wizards.py resolves
it via section_library.py's full profile library) — this module only builds
geometry and applies whatever properties it's given.

Convention (must match the auto-detecting engine):
  * **2D presets** keep every node at z = 0 → the engine analyses them in
    2D mode (3 DOF/node), with **Y vertical**. Downward loads are fy < 0.
  * **3D presets** set ``mode_3d`` and use a non-zero z → 6 DOF/node, with
    **Z vertical**. Downward loads are fz < 0.
"""

from __future__ import annotations

from ui_qt.model_state import (
    ModelState, NodeData, MemberData,
    SupportType, ElementType,
    LoadCase, NodeLoad, MemberLoad, PointLoadData,
)
from ui_qt.section_library import min_reinforcement_area


def _apply_min_reinforcement(m: MemberData) -> None:
    """Auto-place EC2 §9.2.1.1 minimum tension reinforcement on a concrete
    member and flag it as a provisional starting point, not a real design —
    called wherever a wizard sets concrete section geometry but has no way
    to know the actual reinforcement design."""
    if m.b_sec > 0.0 and m.d_eff > 0.0:
        m.As_tension = min_reinforcement_area(m.b_sec, m.d_eff, m.fy, m.fyk)
        m.reinforcement_estimated = True

# ── Material constants ────────────────────────────────────────────────────────
_E_C30  = 32_000_000_000.0     # Pa — Ecm for C30/37
_E_C35  = 34_000_000_000.0     # Pa — Ecm for C35/45
_FCK_C30 = 30_000_000.0        # Pa
_FCK_C35 = 35_000_000.0        # Pa
_RHO_RC = 2500.0               # kg/m³ — reinforced concrete


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mb(state: ModelState, ni: int, nj: int, profile: tuple,
        udl: float = 0.0, etype: ElementType = ElementType.BEAM,
        case: LoadCase | None = None) -> MemberData:
    """Add a member from an (E, A, I) tuple and optionally assign a UDL."""
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
#  Parametric wizards (called from the wizard dialogs — keep signatures stable)
# ═══════════════════════════════════════════════════════════════════════════════

def frame_wizard(n_bays: int, n_stories: int,
                 bay_width: float, story_height: float,
                 fixed_base: bool = False,
                 E: float = 210e9, A: float = 0.03, I: float = 300e-6,
                 fy: float = 275e6, W_pl: float = 0.0, W_el: float = 0.0,
                 b_sec: float = 0.0, h_sec: float = 0.0, density: float = 0.0,
                 ) -> ModelState:
    """Generate a regular multi-story frame (no loads by default).

    fixed_base: True = FIXED column bases, False = PIN.
    E/A/I: applied to every member (columns and beams alike — this wizard
    doesn't distinguish member roles). fy/W_pl/W_el: steel/timber Design-tab
    capacity check inputs; W_pl/W_el = 0 shows "N/A" until a real profile is
    set. b_sec/h_sec: concrete section width/depth [m] (0 = not concrete).
    density: kg/m3 — must be concrete-range (~2500) for the Design tab to
    run the concrete check instead of misreading the member as steel.
    """
    s = ModelState()
    base_sup = SupportType.FIXED if fixed_base else SupportType.PIN
    node_grid: list[list[NodeData]] = []
    for story in range(n_stories + 1):
        row = []
        for bay in range(n_bays + 1):
            nd = s.add_node(bay * bay_width, 0, story * story_height)
            if story == 0:
                nd.support_type = base_sup
            row.append(nd)
        node_grid.append(row)

    def _member(ni: int, nj: int) -> None:
        m = s.add_member(ni, nj)
        m.E, m.A, m.I = E, A, I
        m.fy, m.W_pl, m.W_el = fy, W_pl, W_el
        m.b_sec, m.h_sec = b_sec, h_sec
        m.d_eff = h_sec - 0.05 if h_sec > 0.0 else 0.0   # assumed 50 mm cover
        m.density = density
        _apply_min_reinforcement(m)

    for story in range(n_stories):
        for bay in range(n_bays + 1):
            _member(node_grid[story][bay].id, node_grid[story + 1][bay].id)
    for story in range(1, n_stories + 1):
        for bay in range(n_bays):
            _member(node_grid[story][bay].id, node_grid[story][bay + 1].id)
    return s


def beam_wizard(
    spans: list,
    support_types: list,
    E: float, A: float, I: float,
    udl_g: float = 0.0,
    udl_q: float = 0.0,
    point_q: float = 0.0,
    density: float = 0.0,
    fy: float = 275e6,
    W_pl: float = 0.0,
    W_el: float = 0.0,
    b_sec: float = 0.0,
    h_sec: float = 0.0,
) -> ModelState:
    """Build a beam from wizard parameters.

    spans:         span lengths [m]. N spans → N+1 nodes.
    support_types: SupportType name per node (length N+1).
    udl_g:         permanent G UDL [N/m, downward positive]; 0 = omit G case loads.
    udl_q:         variable Q UDL [N/m]; 0 = omit.
    point_q:       midspan point load on central span in Q case [N]; 0 = omit.
    fy:            steel yield / concrete fck [Pa] — Design-tab capacity checks.
    W_pl, W_el:    steel plastic/elastic section modulus [m^3]; 0 = unknown
                   (Design tab shows "N/A" for bending until a real profile is set).
    b_sec, h_sec:  concrete section width/depth [m]; 0 = not concrete.
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
        m.fy = fy
        m.W_pl, m.W_el = W_pl, W_el
        m.b_sec, m.h_sec = b_sec, h_sec
        m.d_eff = h_sec - 0.05 if h_sec > 0.0 else 0.0   # assumed 50 mm cover
        _apply_min_reinforcement(m)
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
    col_fy: float = 275e6, col_W_pl: float = 0.0, col_W_el: float = 0.0,
    raf_fy: float = 275e6, raf_W_pl: float = 0.0, raf_W_el: float = 0.0,
    col_b_sec: float = 0.0, col_h_sec: float = 0.0,
    raf_b_sec: float = 0.0, raf_h_sec: float = 0.0,
    density: float = 0.0,
) -> ModelState:
    """Build a single-bay portal frame from wizard parameters.

    fixed_base: True = FIXED column bases, False = PIN.
    udl_g / udl_q: rafter UDL [N/m, downward positive].
    wind_h: lateral point load at windward eave [N, positive = left→right].
    col_fy/W_pl/W_el, raf_fy/W_pl/W_el: Design-tab capacity check inputs for
    steel columns and the rafter; W_pl/W_el = 0 shows "N/A" until a real
    profile is set.
    col_b_sec/h_sec, raf_b_sec/h_sec: concrete section width/depth [m] for
    columns and the rafter (0 = not concrete).
    density: kg/m3 — must be set to a concrete-range value (~2500) for RC
    frames, or the Design tab infers "steel" from density=0 and shows the
    wrong capacity check regardless of col_b_sec/h_sec being set.
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

    col1 = _mb(s, n0.id, n1.id, col_profile)
    rafter = _mb(s, n1.id, n2.id, raf_profile)
    col2 = _mb(s, n3.id, n2.id, col_profile)
    for col in (col1, col2):
        col.fy, col.W_pl, col.W_el = col_fy, col_W_pl, col_W_el
        col.b_sec, col.h_sec = col_b_sec, col_h_sec
        col.d_eff = col_h_sec - 0.05 if col_h_sec > 0.0 else 0.0
        col.density = density
        _apply_min_reinforcement(col)
    rafter.fy, rafter.W_pl, rafter.W_el = raf_fy, raf_W_pl, raf_W_el
    rafter.b_sec, rafter.h_sec = raf_b_sec, raf_h_sec
    rafter.d_eff = raf_h_sec - 0.05 if raf_h_sec > 0.0 else 0.0
    rafter.density = density
    _apply_min_reinforcement(rafter)

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
    chord_fy: float = 275e6,
    web_fy: float = 275e6,
) -> ModelState:
    """Build a flat-chord truss from wizard parameters.

    truss_type:    "Pratt" (tension diagonals), "Warren" (alternating),
                   "Howe" (compression diagonals).
    n_panels:      number of panels (≥ 2; even recommended for Pratt/Howe).
    chord_section: (E, A, I) tuple for top and bottom chords.
    web_section:   (E, A, I) tuple for verticals and diagonals.
    panel_load:    vertical point load [N] at each interior loaded-chord node.
    load_on_top:   True = loads on top chord (roof), False = on bottom (bridge).
    chord_fy/web_fy: steel yield strength [Pa] — Design tab's axial capacity
                   check, independent per role since chord/web may differ.
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

    def _wbar(ni: int, nj: int, profile: tuple, fy: float) -> None:
        m = s.add_member(ni, nj)
        m.E, m.A, m.I = profile
        m.element_type = ElementType.BAR
        m.fy = fy

    for i in range(n_panels):
        _wbar(bot[i].id, bot[i + 1].id, chord_section, chord_fy)
        _wbar(top[i].id, top[i + 1].id, chord_section, chord_fy)
    for i in range(n_panels + 1):
        _wbar(top[i].id, bot[i].id, web_section, web_fy)

    n = n_panels
    half = n // 2
    if truss_type == "Pratt":
        for i in range(half):
            _wbar(bot[i].id, top[i + 1].id, web_section, web_fy)
        for i in range(half, n):
            _wbar(bot[i + 1].id, top[i].id, web_section, web_fy)
    elif truss_type == "Howe":
        for i in range(half):
            _wbar(top[i].id, bot[i + 1].id, web_section, web_fy)
        for i in range(half, n):
            _wbar(top[i + 1].id, bot[i].id, web_section, web_fy)
    else:   # Warren
        for i in range(n):
            if i % 2 == 0:
                _wbar(bot[i].id, top[i + 1].id, web_section, web_fy)
            else:
                _wbar(top[i].id, bot[i + 1].id, web_section, web_fy)

    return s
