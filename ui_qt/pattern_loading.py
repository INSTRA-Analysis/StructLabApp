"""Pattern loading detection and generation per EN 1992-1-1 §5.1.3.

Pattern loading is required when variable (Q) loads act on two or more
connected spans.  Applying Q to every span simultaneously (as EN 1990
combinations do) underestimates the maximum sagging moment in individual
spans.  This module:

  1. Detects continuous Q-loaded chains from the ModelState.
  2. Generates the critical EN 1992-1-1 load patterns (alternating + adjacent).
  3. Produces a plain-text assessment message for display in the UI.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ── Public data types ─────────────────────────────────────────────────────────

@dataclass
class PatternAssessment:
    """Result of detect_pattern_loading."""
    needed: bool
    q_member_ids: list[int]              # all member IDs carrying Q loads
    continuous_chains: list[list[int]]   # ordered chains of 2+ Q-loaded members
    single_span_ids: list[int]           # isolated Q-loaded members (no chain)
    reason: str                          # one-sentence explanation


@dataclass
class PatternRun:
    """One EN 1992-1-1 pattern arrangement to solve."""
    name: str
    active_q_member_ids: set[int]        # members receiving full Q; others get 0


# ── Detection ─────────────────────────────────────────────────────────────────

def detect_pattern_loading(state) -> PatternAssessment:
    """Inspect ModelState and determine whether pattern loading is needed.

    A chain of 2+ Q-loaded members sharing nodes makes pattern loading
    necessary — applying Q everywhere would miss the worst span moments.
    Members with only nodal Q loads are excluded (point loads at joints do
    not benefit from span-by-span alternation).
    """
    q_cases = [lc for lc in state.load_cases if lc.category != "G"]

    # Members with distributed or member point loads in any Q case
    q_loaded: set[int] = set()
    for lc in q_cases:
        for mid, ml in lc.member_loads.items():
            if ml.dist_loads or ml.point_loads:
                q_loaded.add(mid)

    if len(q_loaded) < 2:
        return PatternAssessment(
            needed=False,
            q_member_ids=sorted(q_loaded),
            continuous_chains=[],
            single_span_ids=sorted(q_loaded),
            reason=(
                "All Q loads are on isolated or single members — "
                "no alternating arrangement is possible."
            ),
        )

    # Node-pair lookup for Q-loaded members only
    member_nodes: dict[int, tuple[int, int]] = {
        md.id: (md.node_i, md.node_j)
        for md in state.members if md.id in q_loaded
    }

    # Build adjacency: two Q-loaded members are adjacent if they share a node
    adjacency: dict[int, set[int]] = {mid: set() for mid in q_loaded}
    mids = sorted(q_loaded)
    for i, a in enumerate(mids):
        na_i, na_j = member_nodes[a]
        for b in mids[i + 1:]:
            nb_i, nb_j = member_nodes[b]
            if {na_i, na_j} & {nb_i, nb_j}:          # non-empty intersection
                adjacency[a].add(b)
                adjacency[b].add(a)

    # Connected components via BFS
    visited: set[int] = set()
    raw_components: list[list[int]] = []
    for start in mids:
        if start in visited:
            continue
        component: list[int] = []
        queue = [start]
        while queue:
            mid = queue.pop(0)
            if mid in visited:
                continue
            visited.add(mid)
            component.append(mid)
            for nb in adjacency[mid]:
                if nb not in visited:
                    queue.append(nb)
        raw_components.append(component)

    # Order each component by following connectivity from one terminal
    ordered = [_order_chain(c, member_nodes) for c in raw_components]
    continuous   = [c for c in ordered if len(c) >= 2]
    single_spans = [c[0] for c in ordered if len(c) == 1]

    needed = bool(continuous)
    if needed:
        desc = "; ".join(
            f"{len(c)}-span chain (members {', '.join(str(m) for m in c)})"
            for c in continuous
        )
        reason = f"Continuous Q-loaded chain(s) detected: {desc}."
    else:
        reason = "All Q-loaded members are isolated — no alternating pattern possible."

    return PatternAssessment(
        needed=needed,
        q_member_ids=sorted(q_loaded),
        continuous_chains=continuous,
        single_span_ids=single_spans,
        reason=reason,
    )


def _order_chain(
    chain_ids: list[int],
    member_nodes: dict[int, tuple[int, int]],
) -> list[int]:
    """Order members in a connected chain from one terminal end to the other."""
    if len(chain_ids) <= 1:
        return chain_ids

    node_to_mids: dict[int, list[int]] = {}
    for mid in chain_ids:
        ni, nj = member_nodes[mid]
        node_to_mids.setdefault(ni, []).append(mid)
        node_to_mids.setdefault(nj, []).append(mid)

    # Terminal nodes are endpoints of exactly one chain member
    terminals = [n for n, mids in node_to_mids.items() if len(mids) == 1]
    if not terminals:
        return chain_ids            # closed loop — fall back to BFS order

    ordered: list[int] = []
    visited_mids: set[int] = set()
    current_node = terminals[0]
    current_mid  = node_to_mids[current_node][0]

    while current_mid is not None and current_mid not in visited_mids:
        ordered.append(current_mid)
        visited_mids.add(current_mid)
        ni, nj = member_nodes[current_mid]
        next_node = nj if ni == current_node else ni
        nexts = [m for m in node_to_mids.get(next_node, []) if m not in visited_mids]
        current_node = next_node
        current_mid  = nexts[0] if nexts else None

    return ordered if len(ordered) == len(chain_ids) else chain_ids


# ── Pattern generation ────────────────────────────────────────────────────────

def generate_pattern_runs(assessment: PatternAssessment) -> list[PatternRun]:
    """Generate EN 1992-1-1 §5.1.3 critical load patterns.

    For each continuous chain of N spans:
      - Alt A : odd-indexed spans loaded (1, 3, 5 …)  → max sagging odd spans
      - Alt B : even-indexed spans loaded (2, 4, 6 …) → max sagging even spans
      - N-1 adjacent pairs                             → max hogging at supports

    The "all spans" pattern is omitted — it is already covered by the
    1.35G + 1.5Q EN 1990 combination.

    When multiple chains exist, each chain's patterns are generated while
    keeping all other chains at full Q load (conservative assumption).
    """
    all_q = set(assessment.q_member_ids)
    runs: list[PatternRun] = []

    n_chains = len(assessment.continuous_chains)

    for chain_idx, chain in enumerate(assessment.continuous_chains):
        N = len(chain)
        label = f"chain {chain_idx + 1}" if n_chains > 1 else "beam"
        other_q = all_q - set(chain)    # other chains always fully loaded

        # ── Alternating A (spans 1, 3, 5 …) ─────────────────────────────────
        alt_a = {chain[i] for i in range(0, N, 2)}
        runs.append(PatternRun(
            name=f"[Pattern] Alt A – {label} (spans {_span_label(chain, alt_a)})",
            active_q_member_ids=alt_a | other_q,
        ))

        # ── Alternating B (spans 2, 4, 6 …) ─────────────────────────────────
        alt_b = {chain[i] for i in range(1, N, 2)}
        if alt_b:
            runs.append(PatternRun(
                name=f"[Pattern] Alt B – {label} (spans {_span_label(chain, alt_b)})",
                active_q_member_ids=alt_b | other_q,
            ))

        # ── Adjacent pairs ────────────────────────────────────────────────────
        for j in range(N - 1):
            adj = {chain[j], chain[j + 1]}
            runs.append(PatternRun(
                name=f"[Pattern] Adj {j + 1}–{j + 2} – {label}",
                active_q_member_ids=adj | other_q,
            ))

    return runs


def _span_label(chain: list[int], active: set[int]) -> str:
    """Return '1,3' for spans in chain whose IDs are in active."""
    return ",".join(str(i + 1) for i, mid in enumerate(chain) if mid in active)


# ── Assessment message ────────────────────────────────────────────────────────

def build_assessment_message(
    assessment: PatternAssessment,
    n_patterns_solved: int,
    pattern_governs: list[tuple[int, float, float]],   # (member_id, pat_M, full_M)
) -> tuple[str, str]:
    """Return (message, level) for display in the assessment bar.

    level is one of 'ok', 'info', 'warning'.
    """
    if not assessment.needed:
        return (
            "Pattern loading not required — all Q loads are on isolated spans. "
            "EN 1990 combinations are sufficient for this structure.",
            "ok",
        )

    chain_desc = "; ".join(
        f"{len(c)}-span beam (members {', '.join(str(m) for m in c)})"
        for c in assessment.continuous_chains
    )

    lines = [
        "EN 1992-1-1 §5.1.3  |  Pattern loading detected and applied automatically.",
        f"Continuous Q chains: {chain_desc}.",
        f"{n_patterns_solved} ULS pattern combination(s) generated and included in the envelope.",
    ]

    if pattern_governs:
        worst_id, worst_pat, worst_full = max(
            pattern_governs,
            key=lambda t: (t[1] - t[2]) / t[2] if t[2] > 0 else 0.0,
        )
        worst_pct = 100.0 * (worst_pat - worst_full) / worst_full if worst_full > 0 else 0.0
        n = len(pattern_governs)
        lines.append(
            f"Pattern loading GOVERNS for {n} member(s).  "
            f"Worst: Member {worst_id}  {worst_pat / 1e3:.2f} kN·m "
            f"vs {worst_full / 1e3:.2f} kN·m full  (+{worst_pct:.0f}%).  "
            "See envelope table for full detail."
        )
        level = "warning"
    else:
        lines.append(
            "Full loading governs for all members — "
            "EN 1990 combinations are the critical ones."
        )
        level = "info"

    return "\n".join(lines), level
