"""Member capacity checks (no Qt): one place for the design formulas the panels and the canvas use.

Today: cross-section resistance for steel (EN 1993-1-1 §6.2), concrete bending/axial
(EN 1992-1-1 §6.1) and the material guess from E. Sign convention is the solver's:
N positive = compression, negative = tension.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ui_qt.model_state import ElementType


def infer_material(E: float) -> str:
    """Guess material type from Young's modulus for initial Design-tab visibility."""
    if 20e9 <= E <= 45e9:
        return "concrete"
    if 8e9 <= E <= 16e9:
        return "timber"
    return "steel"


GAMMA_M0 = 1.0   # EN 1993-1-1 §6.1(1)
# Below this |N_Ed|, a BEAM-family member's axial force is treated as solver
# noise, not a real column-style combined action, and only the bending check
# is shown.
DESIGN_N_THRESHOLD_N = 50.0   # ~0.05 kN


def bending_row(mat: str, fk: float, W_pl: float, W_el: float,
                b: float, d: float, As: float, fyk_v: float, M_Ed: float) -> dict:
    """One 'Bending M' capacity-check row (EC2 §6.1 for concrete, EC3 §6.2.5
    plastic/elastic for steel & timber — same formulas the member-properties
    Design tab's live M_Rd preview uses)."""
    if mat == "concrete":
        if b > 0 and d > 0 and As > 0 and fk > 0:
            fcd = fk / 1.5
            fyd = fyk_v / 1.15
            x   = min(As * fyd / (0.8 * b * fcd), d)
            M_Rd = As * fyd * (d - 0.4 * x)
            eta  = (M_Ed / M_Rd * 100) if M_Rd > 0 else None
            status = ("PASS ✓" if eta <= 100.0 else "FAIL ✗") if eta is not None else "N/A"
        else:
            M_Rd, eta, status = 0.0, None, "Set b/d/As"
    else:
        if W_pl > 0:
            M_Rd = fk * W_pl / GAMMA_M0
        elif W_el > 0:
            M_Rd = fk * W_el / GAMMA_M0
        else:
            M_Rd = 0.0
        eta = (M_Ed / M_Rd * 100) if M_Rd > 0 else None
        if eta is not None:
            status = "PASS ✓" if eta <= 100.0 else "FAIL ✗"
        elif W_pl == 0 and W_el == 0:
            status = "N/A — set W_pl"
        else:
            status = "N/A"
    return {"check": "Bending M", "demand": M_Ed, "capacity": M_Rd if M_Rd > 0 else None,
            "eta": eta, "status": status, "unit": "kN·m"}


def axial_row(mat: str, fk: float, A: float, As: float, fyk_v: float,
              N_Ed: float) -> dict:
    """One 'Axial N' capacity-check row. N_Ed sign follows the solver's own
    convention (postprocessor.py): positive = compression, negative = tension.

    Steel — EC3 §6.2.3 cross-section yield (no buckling — same no-buckling
    scope as the bending check above), same capacity either direction.

    Concrete — EC2 §6.1: compression is resisted by the concrete *and* the
    reinforcement together (N_Rd = Ac·fcd + As·fyd); tension is resisted by
    the reinforcement alone (concrete is assumed cracked, N_Rd = As·fyd).
    `As` here is the member's single reinforcement-area field, treated as
    the *total* longitudinal steel for this check (not just one face) — a
    simplification worth knowing about, not a full column interaction check.

    Timber: not implemented, explicit N/A.
    """
    if mat == "timber":
        return {"check": "Axial N", "demand": N_Ed, "capacity": None, "eta": None,
                "status": "N/A — axial check not implemented for timber", "unit": "kN"}

    if mat == "steel":
        label = "Axial N"
        N_Rd = A * fk / GAMMA_M0 if A > 0 and fk > 0 else 0.0
        not_set_status = "N/A — set A"
    else:   # concrete
        fcd = fk / 1.5 if fk > 0 else 0.0
        fyd = fyk_v / 1.15 if fyk_v > 0 else 0.0
        if N_Ed >= 0.0:
            label = "Axial N (compression)"
            N_Rd = A * fcd + As * fyd
        else:
            label = "Axial N (tension)"
            N_Rd = As * fyd
        not_set_status = "N/A — set As" if As <= 0.0 else "N/A — set A/fck"

    eta = (abs(N_Ed) / N_Rd * 100) if N_Rd > 0 else None
    status = ("PASS ✓" if eta <= 100.0 else "FAIL ✗") if eta is not None else not_set_status
    return {"check": label, "demand": N_Ed, "capacity": N_Rd if N_Rd > 0 else None,
            "eta": eta, "status": status, "unit": "kN"}


def member_design_rows(
    element_type: ElementType, mat: str, fk: float, A: float,
    W_pl: float, W_el: float, b: float, d: float, As: float, fyk_v: float,
    M_Ed: float, N_Ed: float,
) -> list[dict]:
    """Capacity-check row(s) for one member, chosen by element_type:
      BAR                        -> axial only (a truss bar has no bending stiffness)
      BEAM/PIN_LEFT/PIN_RIGHT,
        negligible axial         -> bending only (today's behaviour)
      BEAM/PIN_LEFT/PIN_RIGHT,
        real combined axial      -> axial + bending, shown as two separate
                                     checks (no combined N+M interaction row —
                                     that would need a buckling-aware EC3 §6.3
                                     check to be meaningful, not just implemented).
    Each dict: {check, demand, capacity, eta (%), status, unit}.
    """
    if element_type == ElementType.BAR:
        return [axial_row(mat, fk, A, As, fyk_v, N_Ed)]

    if abs(N_Ed) <= DESIGN_N_THRESHOLD_N:
        return [bending_row(mat, fk, W_pl, W_el, b, d, As, fyk_v, M_Ed)]

    return [axial_row(mat, fk, A, As, fyk_v, N_Ed),
           bending_row(mat, fk, W_pl, W_el, b, d, As, fyk_v, M_Ed)]


# ── Steel angles: flexural buckling and tension (EN 1993-1-1) ─────────────────
#
# Scope, stated so nobody reads more into a green number than is there:
#   * compression: flexural buckling about the weak (minor principal) axis, EN 1993-1-1 §6.3.1,
#     buckling curve b for L-sections (Table 6.2), buckling length = the member length between
#     its two nodes (pinned ends, k = 1). Torsional / torsional-flexural buckling (§6.3.1.4) and the
#     end-connection eccentricity rules of EN 1993-3-1 are NOT applied.
#   * tension: gross cross-section yielding, §6.2.3(2)(a). The net section through the bolt holes
#     (§6.2.3(2)(b), EN 1993-1-8 §3.10.3) is NOT checked: the model holds no bolt data.
#   * bending: elastic, M / (W_el fy / γM0). The §6.3.3 interaction factors are not applied; the
#     axial and bending ratios are summed as an indication only and reported separately as well.
#   * partial factors: the recommended values γM0 = γM1 = 1.0 (National Annexes may differ).
#   * sections are recognised from the angle library (equal angles, EN 10056-1) by area and minor
#     moment of inertia; anything else is "not checked", never assumed.


GAMMA_M1 = 1.0    # EN 1993-1-1 §6.1(1), recommended value

# EN 1993-1-1 Table 6.1 imperfection factors
IMPERFECTION = {"a0": 0.13, "a": 0.21, "b": 0.34, "c": 0.49, "d": 0.76}
ANGLE_CURVE = "b"       # Table 6.2: L-sections


def buckling_reduction(lambda_bar: float, curve: str = ANGLE_CURVE) -> float:
    """χ from EN 1993-1-1 eq. (6.49): 1 / (Φ + √(Φ² − λ̄²)) ≤ 1, Φ = 0.5[1 + α(λ̄ − 0.2) + λ̄²]."""
    if lambda_bar <= 0.2:
        return 1.0
    alpha = IMPERFECTION[curve]
    phi = 0.5 * (1.0 + alpha * (lambda_bar - 0.2) + lambda_bar ** 2)
    return min(1.0, 1.0 / (phi + math.sqrt(phi * phi - lambda_bar ** 2)))


def flexural_buckling_resistance(A: float, I_min: float, length: float, fy: float, E: float,
                                 curve: str = ANGLE_CURVE) -> dict:
    """N_b,Rd = χ A fy / γM1 (class 1-3 / effective area A) for buckling about the axis of I_min.

    Returns N_cr, λ̄ (eq. 6.50), χ, N_b,Rd (all N, Pa, m)."""
    n_cr = math.pi ** 2 * E * I_min / length ** 2
    lam = math.sqrt(A * fy / n_cr)
    chi = 1.0 if lam <= 0.2 else buckling_reduction(lam, curve)
    return {"N_cr": n_cr, "lambda_bar": lam, "chi": chi, "N_b_Rd": chi * A * fy / GAMMA_M1}


def outstand_reduction(width_over_t: float, fy: float, k_sigma: float = 0.43) -> float:
    """ρ for an outstand element in uniform compression (EN 1993-1-5 §4.4, Table 4.2, ψ = 1):
    ρ = (λ̄p − 0.188) / λ̄p² ≤ 1 with λ̄p = (b/t) / (28.4 ε √kσ), ε = √(235/fy[MPa])."""
    eps = math.sqrt(235e6 / fy)
    lam_p = width_over_t / (28.4 * eps * math.sqrt(k_sigma))
    return 1.0 if lam_p <= 0.748 else (lam_p - 0.188) / lam_p ** 2


def angle_is_class_3_or_better(leg: float, thickness: float, fy: float) -> bool:
    """EN 1993-1-1 Table 5.2 (angles): h/t ≤ 15ε and (b+h)/2t ≤ 11.5ε (equal legs: b/t ≤ 11.5ε)."""
    eps = math.sqrt(235e6 / fy)
    return leg / thickness <= 15 * eps and leg / thickness <= 11.5 * eps


_angle_cache: dict[tuple[float, float], object] = {}


def identify_angle(A: float, I_a: float, I_b: float):
    """The library angle whose area and minor moment of inertia match (0.5 % / 1 %), or None.

    ``I_a`` and ``I_b`` are the member's two second moments; the minor principal one is the smaller."""
    from ui_qt.angle_sections import ANGLE_SECTIONS
    key = (round(A, 9), round(min(I_a, I_b), 14))
    if key in _angle_cache:
        return _angle_cache[key]
    found = None
    for sec in ANGLE_SECTIONS.values():
        if sec.kind == "equal" and abs(sec.A - A) <= 0.005 * sec.A \
                and abs(sec.I_v - min(I_a, I_b)) <= 0.01 * sec.I_v:
            found = sec
            break
    _angle_cache[key] = found
    return found


@dataclass
class MemberCheck:
    """Result of checking one member for one set of forces."""
    eta: float | None                 # governing utilisation (1.0 = exactly at capacity); None = not checked
    governing: str = ""               # what governs, e.g. "Buckling" / "Tension" / "Bending"
    rows: list[dict] = field(default_factory=list)   # same row format as member_design_rows (eta in %)
    notes: list[str] = field(default_factory=list)   # scope limits / reasons nothing was checked

    @property
    def checked(self) -> bool:
        return self.eta is not None


def _row(check: str, demand: float, capacity: float | None, unit: str = "kN", status: str = "") -> dict:
    eta = abs(demand) / capacity * 100 if capacity and capacity > 0 else None
    if not status:
        status = ("PASS ✓" if eta <= 100.0 else "FAIL ✗") if eta is not None else "N/A"
    return {"check": check, "demand": demand, "capacity": capacity, "eta": eta, "status": status, "unit": unit}


def check_angle(section, N_Ed: float, M_Ed: float, length: float, fy: float, E: float,
                has_bending: bool) -> MemberCheck:
    """Axial (+ bending) check of an equal angle. N_Ed in N (compression positive), M_Ed in N·m."""
    notes = ["Torsional-flexural buckling, end-connection eccentricity (EN 1993-3-1) and the "
             "net section are not checked."]
    rows: list[dict] = []
    if length <= 0:
        return MemberCheck(None, notes=["zero-length member"])
    if N_Ed > 0:
        if not angle_is_class_3_or_better(section.a, section.t, fy):
            rho = outstand_reduction(section.a / section.t, fy)
            if rho < 1.0:
                return MemberCheck(None, notes=[
                    f"{section.name} is a class 4 angle in this steel (effective area ρ = {rho:.2f}); "
                    "the effective-section check is not implemented"])
            notes.append(f"{section.name}: class 4 limit exceeded but ρ = 1, gross area is effective.")
        b = flexural_buckling_resistance(section.A, section.I_v, length, fy, E)
        rows.append(_row("Axial N (buckling)", N_Ed, b["N_b_Rd"]))
        notes.append(f"λ̄ = {b['lambda_bar']:.2f}, χ = {b['chi']:.3f}, curve b, L = {length:.2f} m")
        eta_n, governing = abs(N_Ed) / b["N_b_Rd"], "Buckling"
    else:
        rows.append(_row("Axial N (tension)", N_Ed, section.A * fy / GAMMA_M0))
        eta_n, governing = abs(N_Ed) / (section.A * fy / GAMMA_M0), "Tension"
    eta = eta_n
    if has_bending and M_Ed > 0:
        m_rd = min(section.W_u, section.W_v) * fy / GAMMA_M0
        rows.append(_row("Bending M (elastic)", M_Ed, m_rd, "kN·m"))
        eta_m = M_Ed / m_rd
        eta = eta_n + eta_m
        notes.append("N and M ratios are summed as an indication; EN 1993-1-1 §6.3.3 factors are not applied.")
        if eta_m > eta_n:
            governing = "Bending"
    return MemberCheck(eta, governing, rows, notes)


def check_member(member, N_Ed: float, M_Ed: float, length: float) -> MemberCheck:
    """Utilisation of one member for one force set (N in N, compression positive; M in N·m).

    Steel angles recognised from the library get the EN 1993-1-1 buckling / tension / bending
    check above. Any other steel section gets the cross-section check only and says so. Concrete
    keeps the EN 1992-1-1 §6.1 rows (second-order slenderness, §5.8, is not checked); timber has
    no axial check.
    """
    mat = infer_material(member.E)
    has_bending = member.element_type != ElementType.BAR
    if mat == "steel":
        angle = identify_angle(member.A, member.I, member.I_y if member.I_y else member.I)
        if angle is not None:
            return check_angle(angle, N_Ed, M_Ed if has_bending else 0.0, length,
                               member.fy, member.E, has_bending)
    rows = member_design_rows(member.element_type, mat, member.fy, member.A, member.W_pl, member.W_el,
                              member.b_sec, member.d_eff, member.As_tension, member.fyk, M_Ed, N_Ed)
    etas = [r["eta"] for r in rows if r["eta"] is not None]
    notes = []
    if mat == "steel":
        notes.append("Cross-section resistance only: buckling is not checked for this section.")
    elif mat == "concrete":
        notes.append("EN 1992-1-1 §6.1 resistance only: second-order slenderness (§5.8) is not checked.")
    if not etas:
        return MemberCheck(None, rows=rows, notes=notes or ["no capacity data set"])
    worst = max(rows, key=lambda r: r["eta"] if r["eta"] is not None else -1)
    return MemberCheck(max(etas) / 100.0, worst["check"], rows, notes)


# ── from solver results to a displayed utilisation ────────────────────────────

def member_forces(result) -> tuple[float, float]:
    """(N_Ed, M_Ed) of a member from its ElementResult, for design checks.

    The solver reports the axial force on each end with opposite signs (compression positive at
    node i, so the j-end value is −N for a member in compression), so the compression and the
    tension demand are max(N_i, −N_j) and max(−N_i, N_j); the larger governs and keeps its sign.
    M_Ed is the largest resultant end moment (both bending planes in 3D), in N·m.
    """
    f = result.end_forces
    if len(f) == 12:
        n_i, n_j = f[0], f[6]
        m = max(math.hypot(f[4], f[5]), math.hypot(f[10], f[11]))
    else:
        n_i, n_j = f[0], f[3]
        m = max(abs(f[2]), abs(f[5]))
    compression = max(n_i, -n_j)
    tension = max(-n_i, n_j)
    return (compression if compression >= tension else -tension), m


def section_utilisation(member, N_Ed: float, M_Ed: float) -> float:
    """Cross-section utilisation N/(A·fy) + M/(W_pl·fy), γM0 = 1.0 — no buckling, no interaction
    factors. Used for sections the buckling check does not cover."""
    fy = member.fy if member.fy > 1e3 else 275e6
    n_rd = member.A * fy if member.A > 0 else 1e20
    m_rd = member.W_pl * fy if member.W_pl > 0 else 0.0
    eta_n = abs(N_Ed) / n_rd if n_rd > 1e-12 else 0.0
    eta_m = M_Ed / m_rd if m_rd > 1e-12 else 0.0
    return eta_n + eta_m


def display_utilisation(member, result, length: float) -> tuple[float | None, str]:
    """(η, basis) for the colouring and the tooltip. ``basis`` says what the number is, so a
    cross-section-only value is never mistaken for a buckling check.

    η is None when nothing can be checked (and the basis says why)."""
    n_ed, m_ed = member_forces(result)
    mat = infer_material(member.E)
    if mat == "steel":
        angle = identify_angle(member.A, member.I, member.I_y if member.I_y else member.I)
        if angle is not None:
            c = check_angle(angle, n_ed, m_ed if member.element_type != ElementType.BAR else 0.0,
                            length, member.fy, member.E, member.element_type != ElementType.BAR)
            if c.eta is None:
                return None, c.notes[0]
            return c.eta, f"{c.governing.lower()}, EN 1993-1-1"
        return section_utilisation(member, n_ed, m_ed), "section only, no buckling"
    if mat == "concrete":
        c = check_member(member, n_ed, m_ed, length)
        return (c.eta, "EN 1992-1-1 §6.1, slenderness not checked") if c.eta is not None \
            else (None, "reinforcement / section data not set")
    return None, "no check for this material"
