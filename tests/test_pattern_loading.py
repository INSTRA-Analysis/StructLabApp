"""Tests for ui_qt/pattern_loading.py — EN 1992-1-1 §5.1.3 pattern loading.

Pure-Python logic (no Qt), but previously had zero test coverage despite
deciding which spans get loaded in which arrangement for the governing
moment on a continuous beam — a wrong chain/pattern here silently produces
the wrong design moment with no numerical error to flag it.
"""

from ui_qt.model_state import (
    ModelState, NodeData, MemberData, LoadCase, MemberLoad, DistLoad,
    PointLoadData, NodeLoad,
)
from ui_qt.pattern_loading import (
    detect_pattern_loading, generate_pattern_runs, build_assessment_message,
)


def _chain_state(n_spans: int, q_loaded_spans: set[int],
                  nodal_q_span_ends: set[int] | None = None) -> ModelState:
    """Build a straight chain of `n_spans` members (node i -- node i+1).

    q_loaded_spans: member ids (0-indexed, in creation order) to give a Q
    (variable) distributed load.
    nodal_q_span_ends: node ids to give a nodal Q load (should NOT count
    towards pattern detection — nodal Q loads don't benefit from alternation).
    """
    nodes = [NodeData(id=i, x=float(i), y=0.0) for i in range(n_spans + 1)]
    members = [MemberData(id=i, node_i=i, node_j=i + 1) for i in range(n_spans)]

    g_case = LoadCase(id=0, name="G", category="G")
    q_case = LoadCase(id=1, name="Q", category="Q")
    for mid in q_loaded_spans:
        q_case.member_loads[mid] = MemberLoad(dist_loads=[DistLoad("w", 10e3, 10e3)])
    for nid in (nodal_q_span_ends or set()):
        q_case.node_loads[nid] = NodeLoad(fy=-5e3)

    return ModelState(nodes=nodes, members=members, load_cases=[g_case, q_case])


# ── detect_pattern_loading ──────────────────────────────────────────────────

def test_no_q_case_loads_not_needed():
    state = _chain_state(3, q_loaded_spans=set())
    a = detect_pattern_loading(state)
    assert a.needed is False
    assert a.q_member_ids == []
    assert a.continuous_chains == []
    assert "isolated" in a.reason.lower()


def test_single_loaded_span_not_needed():
    state = _chain_state(3, q_loaded_spans={0})
    a = detect_pattern_loading(state)
    assert a.needed is False
    assert a.q_member_ids == [0]
    assert a.single_span_ids == [0]
    assert a.continuous_chains == []


def test_two_isolated_spans_no_chain():
    """Members 0 and 2 are both Q-loaded but don't share a node (span 1 is
    unloaded) — two isolated single-span components, no alternation possible."""
    state = _chain_state(3, q_loaded_spans={0, 2})
    a = detect_pattern_loading(state)
    assert a.needed is False
    assert a.q_member_ids == [0, 2]
    assert a.continuous_chains == []
    assert sorted(a.single_span_ids) == [0, 2]


def test_two_adjacent_spans_form_a_chain():
    state = _chain_state(3, q_loaded_spans={0, 1})
    a = detect_pattern_loading(state)
    assert a.needed is True
    assert a.continuous_chains == [[0, 1]]
    assert a.single_span_ids == []


def test_three_span_chain_ordered_geometrically():
    state = _chain_state(3, q_loaded_spans={0, 1, 2})
    a = detect_pattern_loading(state)
    assert a.needed is True
    assert a.continuous_chains == [[0, 1, 2]]
    assert "3-span chain" in a.reason
    assert "0, 1, 2" in a.reason


def test_chain_ordering_independent_of_member_creation_order():
    """Members added out of geometric order must still be ordered end-to-end."""
    nodes = [NodeData(id=i, x=float(i), y=0.0) for i in range(4)]
    # Member ids deliberately out of geometric order: id 5 = span(2,3), id 1 = span(0,1),
    # id 3 = span(1,2).
    members = [
        MemberData(id=5, node_i=2, node_j=3),
        MemberData(id=1, node_i=0, node_j=1),
        MemberData(id=3, node_i=1, node_j=2),
    ]
    q_case = LoadCase(id=1, name="Q", category="Q")
    for mid in (1, 3, 5):
        q_case.member_loads[mid] = MemberLoad(dist_loads=[DistLoad("w", 10e3, 10e3)])
    state = ModelState(nodes=nodes, members=members,
                        load_cases=[LoadCase(id=0, name="G"), q_case])

    a = detect_pattern_loading(state)
    assert a.needed is True
    assert a.continuous_chains == [[1, 3, 5]]   # geometric order, not id/creation order


def test_point_load_on_member_counts_as_q_loaded():
    state = _chain_state(3, q_loaded_spans=set())
    state.load_cases[1].member_loads[0] = MemberLoad(
        point_loads=[PointLoadData(load_type="FORCE", position=0.5, magnitude=5e3)]
    )
    state.load_cases[1].member_loads[1] = MemberLoad(
        point_loads=[PointLoadData(load_type="FORCE", position=0.5, magnitude=5e3)]
    )
    a = detect_pattern_loading(state)
    assert a.needed is True
    assert a.continuous_chains == [[0, 1]]


def test_nodal_only_q_load_is_excluded_from_pattern_detection():
    """A nodal Q load at the shared node of two otherwise-unloaded spans must
    NOT be treated as making those spans Q-loaded (per module docstring)."""
    state = _chain_state(3, q_loaded_spans=set(), nodal_q_span_ends={1})
    a = detect_pattern_loading(state)
    assert a.needed is False
    assert a.q_member_ids == []


def test_g_case_loads_are_ignored():
    """Only non-'G'-category cases contribute to Q-loaded detection."""
    state = _chain_state(3, q_loaded_spans=set())
    state.load_cases[0].member_loads[0] = MemberLoad(dist_loads=[DistLoad("w", 10e3, 10e3)])
    state.load_cases[0].member_loads[1] = MemberLoad(dist_loads=[DistLoad("w", 10e3, 10e3)])
    a = detect_pattern_loading(state)
    assert a.needed is False
    assert a.q_member_ids == []


def test_closed_loop_falls_back_without_crashing():
    """A 3-member ring (no free terminal) must not crash _order_chain — it
    falls back to returning the raw (unordered) component."""
    nodes = [NodeData(id=i, x=float(i), y=0.0) for i in range(3)]
    members = [
        MemberData(id=0, node_i=0, node_j=1),
        MemberData(id=1, node_i=1, node_j=2),
        MemberData(id=2, node_i=2, node_j=0),
    ]
    q_case = LoadCase(id=1, name="Q", category="Q")
    for mid in (0, 1, 2):
        q_case.member_loads[mid] = MemberLoad(dist_loads=[DistLoad("w", 10e3, 10e3)])
    state = ModelState(nodes=nodes, members=members,
                        load_cases=[LoadCase(id=0, name="G"), q_case])

    a = detect_pattern_loading(state)
    assert a.needed is True
    assert len(a.continuous_chains) == 1
    assert sorted(a.continuous_chains[0]) == [0, 1, 2]


# ── generate_pattern_runs ────────────────────────────────────────────────────

def test_generate_runs_three_span_chain():
    state = _chain_state(3, q_loaded_spans={0, 1, 2})
    a = detect_pattern_loading(state)
    runs = generate_pattern_runs(a)

    by_name = {r.name: r.active_q_member_ids for r in runs}
    names = list(by_name)
    assert any("Alt A" in n for n in names)
    assert any("Alt B" in n for n in names)
    assert sum("Adj" in n for n in names) == 2   # N-1 = 2 adjacent pairs for a 3-span chain

    alt_a = next(v for k, v in by_name.items() if "Alt A" in k)
    alt_b = next(v for k, v in by_name.items() if "Alt B" in k)
    assert alt_a == {0, 2}          # spans 1, 3 (odd-indexed)
    assert alt_b == {1}             # span 2 (even-indexed)

    adj_sets = [v for k, v in by_name.items() if "Adj" in k]
    assert {0, 1} in adj_sets
    assert {1, 2} in adj_sets


def test_generate_runs_two_span_chain_has_no_duplicate_alt_b_and_adj():
    state = _chain_state(2, q_loaded_spans={0, 1})
    a = detect_pattern_loading(state)
    runs = generate_pattern_runs(a)
    # Alt A ({0}) + Alt B ({1}) + 1 adjacent pair ({0,1}) = 3 runs
    assert len(runs) == 3


def test_generate_runs_other_chains_stay_fully_loaded():
    """With two independent chains, patterns for chain 1 must keep chain 2's
    members fully Q-loaded (conservative assumption), and vice versa."""
    nodes = [NodeData(id=i, x=float(i), y=0.0) for i in range(7)]
    # chain A: members 0,1 (nodes 0-1-2); chain B: members 3,4 (nodes 4-5-6);
    # member 2 (nodes 2-3... wait keep unloaded to separate chains) left unloaded.
    members = [MemberData(id=i, node_i=i, node_j=i + 1) for i in range(6)]
    q_case = LoadCase(id=1, name="Q", category="Q")
    for mid in (0, 1, 4, 5):
        q_case.member_loads[mid] = MemberLoad(dist_loads=[DistLoad("w", 10e3, 10e3)])
    state = ModelState(nodes=nodes, members=members,
                        load_cases=[LoadCase(id=0, name="G"), q_case])

    a = detect_pattern_loading(state)
    assert len(a.continuous_chains) == 2

    runs = generate_pattern_runs(a)
    chain1_names = [r for r in runs if "chain 1" in r.name]
    chain2_names = [r for r in runs if "chain 2" in r.name]
    assert chain1_names and chain2_names

    # Every chain-1 run must fully include chain 2's members (4, 5), and vice versa.
    for r in chain1_names:
        assert {4, 5}.issubset(r.active_q_member_ids)
    for r in chain2_names:
        assert {0, 1}.issubset(r.active_q_member_ids)


def test_generate_runs_no_chains_returns_empty():
    state = _chain_state(3, q_loaded_spans=set())
    a = detect_pattern_loading(state)
    assert generate_pattern_runs(a) == []


# ── build_assessment_message ────────────────────────────────────────────────

def test_assessment_message_not_needed():
    state = _chain_state(3, q_loaded_spans={0})
    a = detect_pattern_loading(state)
    msg, level = build_assessment_message(a, 0, [])
    assert level == "ok"
    assert "not required" in msg.lower()


def test_assessment_message_needed_full_loading_governs():
    state = _chain_state(3, q_loaded_spans={0, 1, 2})
    a = detect_pattern_loading(state)
    msg, level = build_assessment_message(a, 4, [])
    assert level == "info"
    assert "Full loading governs" in msg


def test_assessment_message_pattern_governs_picks_worst_by_percentage():
    state = _chain_state(3, q_loaded_spans={0, 1, 2})
    a = detect_pattern_loading(state)
    # member 7: +10% increase; member 9: +50% increase — member 9 must be reported as worst
    # even though member 7's absolute pattern moment is larger.
    pattern_governs = [
        (7, 110_000.0, 100_000.0),
        (9, 15_000.0, 10_000.0),
    ]
    msg, level = build_assessment_message(a, 6, pattern_governs)
    assert level == "warning"
    assert "GOVERNS for 2 member" in msg
    assert "Member 9" in msg
    assert "+50%" in msg
