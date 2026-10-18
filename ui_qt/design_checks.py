"""Member capacity checks (no Qt): one place for the design formulas the panels and the canvas use.

Today: cross-section resistance for steel (EN 1993-1-1 §6.2), concrete bending/axial
(EN 1992-1-1 §6.1) and the material guess from E. Sign convention is the solver's:
N positive = compression, negative = tension.
"""

from __future__ import annotations

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
