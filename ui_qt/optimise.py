"""Choose the lightest steel angle for each member group (no Qt).

For every group the module picks the smallest equal angle from the library whose utilisation —
the EN 1993-1-1 buckling / tension / bending check in ``design_checks`` — stays at or under a
target in every ULS combination, then re-solves, because changing a section changes stiffness and
the force distribution, until the choice stops changing.

The groups stay the groups: members of a group always share one section, and ``ordered`` chains
(for example the four leg sections) are kept non-increasing in size so a lighter group never sits
below a heavier one. Only groups whose members are all recognised library angles are touched; the
rest are reported as skipped.

Limits worth knowing (they are the limits of the check, see ``design_checks``): buckling length is
the member length between nodes — or, when ``state.crossing_braces`` is set, the stretch to a
crossing held by a member in tension — there is no net-section or connection check, and the
slenderness limit is the one you pass in, not one taken from a code.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from types import SimpleNamespace

import numpy as np

from ui_qt.angle_sections import ANGLE_SECTIONS
from ui_qt.design_checks import check_angle, identify_angle
from ui_qt.model_state import ElementType, MemberData, ModelState


@dataclass
class GroupResult:
    group: str
    before: str                 # section name before ("?" when not a library angle)
    after: str
    eta_before: float | None
    eta_after: float | None
    governing: str = ""
    slenderness: float = 0.0    # worst L / i_v in the group with the chosen section
    note: str = ""


@dataclass
class OptimiseResult:
    groups: list[GroupResult] = field(default_factory=list)
    iterations: int = 0
    converged: bool = False
    mass_before: float = 0.0    # kg
    mass_after: float = 0.0

    def table(self) -> str:
        rows = [f"{'group':22s}{'before':>10s}{'after':>10s}{'η before':>10s}{'η after':>9s}  governs"]
        for g in self.groups:
            eb = f"{g.eta_before:.2f}" if g.eta_before is not None else "-"
            ea = f"{g.eta_after:.2f}" if g.eta_after is not None else "-"
            rows.append(f"{g.group:22s}{g.before:>10s}{g.after:>10s}{eb:>10s}{ea:>9s}  {g.governing or g.note}")
        rows.append(f"steel mass {self.mass_before:,.0f} kg -> {self.mass_after:,.0f} kg  "
                    f"({self.iterations} solve round(s), {'converged' if self.converged else 'NOT converged'})")
        return "\n".join(rows)


def equal_angles() -> list:
    """Equal angles of the library, smallest area first."""
    return sorted((s for s in ANGLE_SECTIONS.values() if s.kind == "equal"), key=lambda s: s.A)


def _length(state: ModelState, m: MemberData) -> float:
    a, b = state.get_node(m.node_i), state.get_node(m.node_j)
    return math.dist((a.x, a.y, a.z), (b.x, b.y, b.z))


def apply_section(m: MemberData, sec) -> None:
    """Give a member an angle's properties, keeping how its two inertias were assigned: a member
    whose I and I_y differed (a corner leg on principal axes) keeps I = I_v, I_y = I_u."""
    principal = m.I_y is not None and abs(m.I - m.I_y) > 1e-9 * max(m.I, 1e-30)
    m.A, m.J = sec.A, sec.J
    m.I = sec.I_v
    m.I_y = sec.I_u if principal else sec.I_v


ForceSet = tuple[np.ndarray, list[np.ndarray]]
"""(end forces, one row per member in ``state.members`` order; per member, its moments at the
fixed stations along it) — both superpose linearly across load cases."""


def solve_case_forces(state: ModelState) -> dict[int, ForceSet]:
    """End forces and station moments of every member for every load case."""
    from ui_qt.model_builder import build_model
    from ui_qt.solve_actions import solve_engine
    out: dict[int, ForceSet] = {}
    for case in state.load_cases:
        model, emap = build_model(state, case)
        cache = solve_engine(model, emap, state)
        out[case.id] = (np.array([r.end_forces for r in cache["member_results"]]),
                        [r.moment_stations for r in cache["member_results"]])
    return out


def combination_forces(state: ModelState, case_forces: dict[int, ForceSet], combo) -> ForceSet:
    """End forces and station moments of a combination: the factored sum of the case results
    (the analysis is linear; the peak along a member is taken after summing)."""
    ends, stations = None, None
    for cid, factor in combo.factors.items():
        if cid in case_forces and factor:
            e, st = case_forces[cid]
            if ends is None:
                ends, stations = factor * e, [factor * s for s in st]
            else:
                ends = ends + factor * e
                stations = [a + factor * s for a, s in zip(stations, st)]
    if ends is None:
        e, st = next(iter(case_forces.values()))
        return np.zeros_like(e), [np.zeros_like(s) for s in st]
    return ends, stations


def group_utilisation(state: ModelState, members: list[MemberData], sec, forces: list[ForceSet],
                      lengths: dict[int, float], index: dict[int, int],
                      restraints: dict | None = None) -> tuple[float | None, str, float]:
    """(worst η, governing check, worst slenderness) of ``members`` if they all had ``sec``.

    ``forces`` is one ForceSet (end forces + station moments) per ULS combination. ``restraints`` (from
    ``model_checks.crossing_restraints``) shortens the buckling length of a member that a tension
    member crosses, combination by combination. Returns η None when the section cannot be
    checked for some member (class 4 outstand with ρ < 1)."""
    from ui_qt.design_checks import buckling_length, member_forces
    worst, gov, slender = 0.0, "", 0.0
    for m in members:
        has_bending = m.element_type != ElementType.BAR
        for arr, stations in forces:
            n, mom = member_forces(SimpleNamespace(end_forces=arr[index[m.id]],
                                                   moment_stations=stations[index[m.id]]))
            L = lengths[m.id]
            if restraints and m.id in restraints:
                L = buckling_length(L, restraints[m.id],
                                    lambda pid, arr=arr: member_forces(SimpleNamespace(
                                        end_forces=arr[index[pid]]))[0])
            slender = max(slender, L / math.sqrt(sec.I_v / sec.A))
            c = check_angle(sec, n, mom if has_bending else 0.0, L, m.fy, m.E, has_bending)
            if c.eta is None:
                return None, c.notes[0], slender
            if c.eta > worst:
                worst, gov = c.eta, c.governing
    return worst, gov, slender


def optimise_groups(state: ModelState, combinations: list, *, target: float = 0.85,
                    min_section: str | None = None, max_slenderness: float | None = None,
                    ordered: list[list[str]] | None = None, groups: list[str] | None = None,
                    max_rounds: int = 8) -> OptimiseResult:
    """Re-profile the angle groups of ``state`` in place; see the module docstring.

    ``combinations``  the ULS combinations to satisfy (SLS ones are ignored).
    ``target``        the utilisation every member should stay at or under.
    ``min_section``   name of the smallest section allowed (for example "L 50×5").
    ``max_slenderness`` L / i_v limit for every member of a group (your limit, not a code's).
    ``ordered``       chains of group names whose sections must not increase down the list.
    ``groups``        only these groups (default: every group of recognised angles).
    """
    combos = [c for c in combinations if c.limit_state == "ULS"]
    if not combos:
        raise ValueError("optimise_groups needs at least one ULS combination")
    candidates = equal_angles()
    if min_section:
        floor = next(s for s in candidates if s.name == min_section).A
        candidates = [s for s in candidates if s.A >= floor - 1e-12]

    by_group: dict[str, list[MemberData]] = {}
    for m in state.members:
        by_group.setdefault(m.group, []).append(m)
    todo: dict[str, list[MemberData]] = {}
    result = OptimiseResult()
    for g, ms in by_group.items():
        if groups is not None and g not in groups:
            continue
        secs = {identify_angle(m.A, m.I, m.I_y if m.I_y else m.I) for m in ms}
        if None in secs or len(secs) != 1:
            result.groups.append(GroupResult(g, "?", "?", None, None,
                                             note="not a single library angle: left alone"))
            continue
        todo[g] = ms
    lengths = {m.id: _length(state, m) for m in state.members}
    restraints = None
    if state.crossing_braces:
        from ui_qt.model_checks import crossing_restraints
        restraints = crossing_restraints(state)
    index = {m.id: i for i, m in enumerate(state.members)}
    name = lambda ms: identify_angle(ms[0].A, ms[0].I, ms[0].I_y if ms[0].I_y else ms[0].I).name  # noqa: E731
    before = {g: name(ms) for g, ms in todo.items()}
    result.mass_before = _mass(state, lengths)

    chosen: dict[str, object] = {}
    eta_first: dict[str, float | None] = {}
    for rnd in range(1, max_rounds + 1):
        cf = solve_case_forces(state)
        forces = [combination_forces(state, cf, c) for c in combos]
        picks: dict[str, object] = {}
        for g, ms in todo.items():
            if rnd == 1:
                cur = identify_angle(ms[0].A, ms[0].I, ms[0].I_y if ms[0].I_y else ms[0].I)
                eta_first[g] = group_utilisation(state, ms, cur, forces, lengths, index, restraints)[0]
            for sec in candidates:
                eta, _, slender = group_utilisation(state, ms, sec, forces, lengths, index, restraints)
                if eta is not None and eta <= target and (max_slenderness is None or slender <= max_slenderness):
                    picks[g] = sec
                    break
            else:
                picks[g] = candidates[-1]                       # nothing passes: the largest, flagged below
        for chain in ordered or []:                              # enforce non-increasing size along a chain
            chain = [g for g in chain if g in picks]
            for i in range(len(chain) - 2, -1, -1):
                if picks[chain[i]].A < picks[chain[i + 1]].A:
                    picks[chain[i]] = picks[chain[i + 1]]
        result.iterations = rnd
        if {g: s.name for g, s in picks.items()} == {g: s.name for g, s in chosen.items()}:
            result.converged = True
            break
        chosen = picks
        for g, ms in todo.items():
            for m in ms:
                apply_section(m, picks[g])

    cf = solve_case_forces(state)                                # verify the final assignment
    forces = [combination_forces(state, cf, c) for c in combos]
    for g, ms in todo.items():
        sec = identify_angle(ms[0].A, ms[0].I, ms[0].I_y if ms[0].I_y else ms[0].I)
        eta, gov, slender = group_utilisation(state, ms, sec, forces, lengths, index, restraints)
        note = "" if eta is not None and eta <= target + 1e-9 else "ABOVE TARGET with the largest section"
        result.groups.append(GroupResult(g, before[g], sec.name, eta_first.get(g), eta, gov, slender, note))
    result.mass_after = _mass(state, lengths)
    return result


def _mass(state: ModelState, lengths: dict[int, float]) -> float:
    return sum(m.A * lengths[m.id] * m.density for m in state.members)
