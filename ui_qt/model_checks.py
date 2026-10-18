"""Model hygiene checks: coincident nodes, duplicate members, zero-length members.

Typical sources are rotate/mirror copies, pasted geometry and imported files. A duplicated
member silently doubles the stiffness; a node lying on another without sharing it leaves the
structure disconnected there. ``check_duplicates`` finds them; ``merge_duplicates`` repairs
the model in place:

* coincident nodes merge into the lowest id; members are re-pointed, node loads summed, and
  the kept node takes the first non-free support of the cluster (conflicts are reported);
* members that become zero-length are removed;
* duplicate members (same two nodes, either direction) are removed, keeping the lowest id;
  a duplicate's member loads move to the kept member when both run the same way. A reversed
  duplicate that carries loads is NOT removed (its local-direction loads would need flipping)
  and is reported for review.

Pure data operations on a ModelState; no Qt.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ui_qt.model_state import ModelState, NodeLoad, SupportType

DEFAULT_TOL = 1e-3          # m — nodes closer than 1 mm are the same point


@dataclass
class DuplicateReport:
    node_clusters: list[list[int]] = field(default_factory=list)    # coincident node ids, lowest first
    member_groups: list[list[int]] = field(default_factory=list)    # duplicate member ids, lowest first
    zero_length: list[int] = field(default_factory=list)            # members whose ends coincide

    @property
    def extra_nodes(self) -> int:
        return sum(len(c) - 1 for c in self.node_clusters)

    @property
    def extra_members(self) -> int:
        return sum(len(g) - 1 for g in self.member_groups)

    @property
    def is_clean(self) -> bool:
        return not (self.node_clusters or self.member_groups or self.zero_length)

    def node_ids(self) -> list[int]:
        return [n for c in self.node_clusters for n in c]

    def member_ids(self) -> list[int]:
        return [m for g in self.member_groups for m in g] + list(self.zero_length)


@dataclass
class MergeSummary:
    nodes_merged: int = 0
    members_removed: int = 0
    zero_length_removed: int = 0
    kept_reversed_with_loads: list[int] = field(default_factory=list)
    support_conflicts: list[int] = field(default_factory=list)       # kept node ids


def _representatives(state: ModelState, tol: float) -> dict[int, int]:
    """node id -> lowest id of its coincident cluster (itself when alone). Grid-hashed, O(n)."""
    parent = {n.id: n.id for n in state.nodes}

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    cell = max(tol, 1e-12)
    grid: dict[tuple[int, int, int], list] = {}
    for n in state.nodes:
        key = (math.floor(n.x / cell), math.floor(n.y / cell), math.floor(n.z / cell))
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for other in grid.get((key[0] + dx, key[1] + dy, key[2] + dz), ()):
                        if math.dist((n.x, n.y, n.z), (other.x, other.y, other.z)) <= tol:
                            a, b = find(n.id), find(other.id)
                            if a != b:
                                parent[max(a, b)] = min(a, b)
        grid.setdefault(key, []).append(n)
    return {nid: find(nid) for nid in parent}


def check_duplicates(state: ModelState, tol: float = DEFAULT_TOL) -> DuplicateReport:
    rep = _representatives(state, tol)
    clusters: dict[int, list[int]] = {}
    for nid, root in rep.items():
        clusters.setdefault(root, []).append(nid)
    report = DuplicateReport(node_clusters=sorted(sorted(c) for c in clusters.values() if len(c) > 1))

    pairs: dict[frozenset, list[int]] = {}
    for m in state.members:
        a, b = rep.get(m.node_i, m.node_i), rep.get(m.node_j, m.node_j)
        if a == b:
            report.zero_length.append(m.id)
            continue
        pairs.setdefault(frozenset((a, b)), []).append(m.id)
    report.member_groups = sorted(sorted(g) for g in pairs.values() if len(g) > 1)
    return report


def _add_node_load(total: NodeLoad, extra: NodeLoad) -> NodeLoad:
    return NodeLoad(fx=total.fx + extra.fx, fy=total.fy + extra.fy, moment=total.moment + extra.moment,
                    fz=total.fz + extra.fz, moment_x=total.moment_x + extra.moment_x,
                    moment_y=total.moment_y + extra.moment_y)


def _has_member_loads(state: ModelState, member_id: int) -> bool:
    return any(member_id in lc.member_loads for lc in state.load_cases)


def merge_duplicates(state: ModelState, tol: float = DEFAULT_TOL) -> MergeSummary:
    """Repair the duplicates ``check_duplicates`` finds; see the module docstring."""
    summary = MergeSummary()
    rep = _representatives(state, tol)
    nodes = {n.id: n for n in state.nodes}

    # ── nodes: supports, loads, member ends ──────────────────────────────────
    clusters: dict[int, list[int]] = {}
    for nid, root in rep.items():
        clusters.setdefault(root, []).append(nid)
    for root, ids in clusters.items():
        if len(ids) < 2:
            continue
        keep = nodes[root]
        supported = [nodes[i] for i in sorted(ids) if nodes[i].support_type != SupportType.FREE]
        if supported:
            if len({s.support_type for s in supported}) > 1:
                summary.support_conflicts.append(root)
            if keep.support_type == SupportType.FREE:
                src = supported[0]
                for name in ("support_type", "spring_kx", "spring_ky", "spring_ktheta", "spring_kz",
                             "spring_krx", "spring_kry", "spring_krz"):
                    setattr(keep, name, getattr(src, name))
        for lc in state.load_cases:
            total = lc.get_node_load(root)
            for other in ids:
                if other != root and other in lc.node_loads:
                    total = _add_node_load(total, lc.node_loads.pop(other))
            lc.set_node_load(root, total)
    for m in state.members:
        m.node_i, m.node_j = rep.get(m.node_i, m.node_i), rep.get(m.node_j, m.node_j)
    removed_nodes = [nid for nid, root in rep.items() if nid != root]
    state.nodes = [n for n in state.nodes if rep.get(n.id, n.id) == n.id]
    summary.nodes_merged = len(removed_nodes)

    # ── members: zero length, then duplicates ────────────────────────────────
    for m in [m for m in state.members if m.node_i == m.node_j]:
        state.remove_member(m.id)
        summary.zero_length_removed += 1

    by_pair: dict[frozenset, list] = {}
    for m in state.members:
        by_pair.setdefault(frozenset((m.node_i, m.node_j)), []).append(m)
    for group in by_pair.values():
        if len(group) < 2:
            continue
        group.sort(key=lambda m: m.id)
        keep = group[0]
        for dup in group[1:]:
            same_way = (dup.node_i, dup.node_j) == (keep.node_i, keep.node_j)
            if _has_member_loads(state, dup.id):
                if not same_way:
                    summary.kept_reversed_with_loads.append(dup.id)
                    continue
                for lc in state.load_cases:
                    moved = lc.member_loads.pop(dup.id, None)
                    if moved is None:
                        continue
                    target = lc.get_member_load(keep.id)
                    target.dist_loads += moved.dist_loads
                    target.point_loads += moved.point_loads
                    target.partial_loads += moved.partial_loads
                    lc.member_loads[keep.id] = target
            state.remove_member(dup.id)
            summary.members_removed += 1
    return summary
