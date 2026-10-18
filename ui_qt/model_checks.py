"""Model hygiene checks: coincident nodes, duplicate, overlapping and zero-length members.

Typical sources are rotate/mirror copies, pasted geometry and imported files. A duplicated
member silently doubles the stiffness; a node lying on another without sharing it leaves the
structure disconnected there. ``check_duplicates`` finds them; ``merge_duplicates`` repairs
the model in place:

* coincident nodes merge into the lowest id; members are re-pointed, node loads summed, and
  the kept node takes the first non-free support of the cluster (conflicts are reported);
* members that become zero-length are removed;
* overlapping members — collinear and sharing part of their length without joining the same
  two points (typically a member drawn over a divided one) — are REPORTED only: which one to
  delete is a modelling decision;
* duplicate members (same two nodes, either direction) are removed, keeping the lowest id;
  a duplicate's member loads move to the kept member when both run the same way. A reversed
  duplicate that carries loads is NOT removed (its local-direction loads would need flipping)
  and is reported for review.

Pure data operations on a ModelState; no Qt.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ui_qt.model_state import MemberData, ModelState, NodeLoad, SupportType

DEFAULT_TOL = 1e-3          # m — nodes closer than 1 mm are the same point


@dataclass
class DuplicateReport:
    node_clusters: list[list[int]] = field(default_factory=list)    # coincident node ids, lowest first
    member_groups: list[list[int]] = field(default_factory=list)    # duplicate member ids, lowest first
    zero_length: list[int] = field(default_factory=list)            # members whose ends coincide
    overlaps: list[tuple[int, int]] = field(default_factory=list)   # collinear, partly shared members

    @property
    def extra_nodes(self) -> int:
        return sum(len(c) - 1 for c in self.node_clusters)

    @property
    def extra_members(self) -> int:
        return sum(len(g) - 1 for g in self.member_groups)

    @property
    def is_clean(self) -> bool:
        return not (self.node_clusters or self.member_groups or self.zero_length or self.overlaps)

    @property
    def fixable(self) -> bool:
        """Anything ``merge_duplicates`` can repair (overlaps are only reported)."""
        return bool(self.node_clusters or self.member_groups or self.zero_length)

    def node_ids(self) -> list[int]:
        return [n for c in self.node_clusters for n in c]

    def member_ids(self) -> list[int]:
        overlapping = sorted({m for pair in self.overlaps for m in pair})
        return [m for g in self.member_groups for m in g] + list(self.zero_length) + overlapping


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


def _line_key(p, q, tol: float):
    """(direction key, unit direction, perpendicular foot, t-interval) of segment p→q, with the
    direction made canonical so collinear members point the same way; None if too short."""
    d = [q[k] - p[k] for k in range(3)]
    length = math.sqrt(sum(c * c for c in d))
    if length <= tol:
        return None
    d = [c / length for c in d]
    lead = next(c for c in d if abs(c) > 1e-9)
    if lead < 0:
        d = [-c for c in d]
    t0, t1 = sorted((sum(p[k] * d[k] for k in range(3)), sum(q[k] * d[k] for k in range(3))))
    foot = [p[k] - sum(p[i] * d[i] for i in range(3)) * d[k] for k in range(3)]
    return tuple(round(c, 5) for c in d), d, foot, (t0, t1)


def find_overlapping_members(state: ModelState, tol: float = DEFAULT_TOL,
                             rep: dict[int, int] | None = None) -> list[tuple[int, int]]:
    """Pairs of collinear members that share more than ``tol`` of their length but do not
    join the same two points (those are duplicates) — e.g. a member drawn over a divided one."""
    rep = rep if rep is not None else _representatives(state, tol)
    coords = {n.id: (n.x, n.y, n.z) for n in state.nodes}
    cell = max(10 * tol, 1e-3)
    buckets: dict[tuple, list] = {}
    pairs: list[tuple[int, int]] = []
    for m in state.members:
        if m.node_i not in coords or m.node_j not in coords:
            continue
        key = _line_key(coords[m.node_i], coords[m.node_j], tol)
        if key is None:
            continue
        dkey, _d, foot, (t0, t1) = key
        ends = frozenset((rep.get(m.node_i, m.node_i), rep.get(m.node_j, m.node_j)))
        base = tuple(math.floor(c / cell) for c in foot)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for other_id, other_foot, (u0, u1), other_ends in buckets.get(
                            (dkey, base[0] + dx, base[1] + dy, base[2] + dz), ()):
                        if other_ends == ends:
                            continue                     # an exact duplicate, reported separately
                        if math.dist(foot, other_foot) > tol:
                            continue                     # parallel but on a different line
                        if min(t1, u1) - max(t0, u0) > tol:
                            pairs.append((min(other_id, m.id), max(other_id, m.id)))
        buckets.setdefault((dkey, *base), []).append((m.id, foot, (t0, t1), ends))
    return sorted(set(pairs))


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
    report.overlaps = find_overlapping_members(state, tol, rep)
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


# ── Crossing members (X-bracing drawn without a node at the crossing) ──────────

@dataclass
class Crossing:
    """Two members whose axes meet in the interior of both, with no node there."""
    member_a: int
    member_b: int
    point: tuple[float, float, float]
    param_a: float          # 0..1 along member_a from its node_i
    param_b: float


@dataclass
class SplitSummary:
    crossings: int = 0
    nodes_created: int = 0
    members_split: int = 0
    members_created: int = 0
    skipped_loaded: list[int] = field(default_factory=list)   # members with member loads, left alone

    def message(self) -> str:
        if not self.crossings:
            if self.skipped_loaded:
                return (f"{len(self.skipped_loaded)} member(s) cross without a node but carry member "
                        "loads, so they were left alone.")
            return "No crossing members without a node were found."
        text = (f"Split {self.members_split} member(s) at {self.nodes_created} crossing node(s): "
                f"{self.members_created} new member(s).")
        if self.skipped_loaded:
            text += (f" {len(self.skipped_loaded)} member(s) carry member loads and were left alone "
                     f"(ids {', '.join(map(str, self.skipped_loaded[:8]))}"
                     f"{'…' if len(self.skipped_loaded) > 8 else ''}).")
        return text


def find_crossings(state: ModelState, tol: float = DEFAULT_TOL,
                   member_ids: set[int] | None = None) -> list[Crossing]:
    """Pairs of members that cross within ``tol`` at a point interior to both and share no node.

    Parallel members are ignored (collinear overlaps are ``check_duplicates``' job). A crossing
    within ``tol`` of an end of either member is a node-meets-member contact, not an X, and is
    not reported. ``member_ids`` limits the search to those members (both of a pair must be in it).
    """
    import numpy as np

    coords = {n.id: (n.x, n.y, n.z) for n in state.nodes}
    members = [m for m in state.members if m.node_i != m.node_j
               and (member_ids is None or m.id in member_ids)]
    if len(members) < 2:
        return []
    p = np.array([coords[m.node_i] for m in members], dtype=float)
    q = np.array([coords[m.node_j] for m in members], dtype=float)
    d = q - p
    length = np.linalg.norm(d, axis=1)
    found: list[Crossing] = []
    for i in range(len(members) - 1):
        j = np.arange(i + 1, len(members))
        r = p[i] - p[j]
        a = float(d[i] @ d[i])
        e = np.einsum("ij,ij->i", d[j], d[j])
        b = d[j] @ d[i]
        c = d[i] @ r.T
        f = np.einsum("ij,ij->i", d[j], r)
        den = a * e - b * b
        ok = den > 1e-9 * a * e                            # not parallel
        with np.errstate(divide="ignore", invalid="ignore"):
            s = np.where(ok, (b * f - c * e) / den, 0.0)
            t = np.where(ok, (a * f - b * c) / den, 0.0)   # parameter along member j
        # interior of both, farther than tol from every end
        eps_i, eps_j = tol / max(length[i], 1e-12), tol / np.maximum(length[j], 1e-12)
        inside = ok & (s > eps_i) & (s < 1 - eps_i) & (t > eps_j) & (t < 1 - eps_j)
        gap = np.linalg.norm((p[i] + np.outer(s, d[i])) - (p[j] + t[:, None] * d[j]), axis=1)
        for k in np.nonzero(inside & (gap <= tol))[0]:
            mi, mj = members[i], members[j[k]]
            if {mi.node_i, mi.node_j} & {mj.node_i, mj.node_j}:
                continue
            pt = p[i] + s[k] * d[i]
            found.append(Crossing(mi.id, mj.id, (float(pt[0]), float(pt[1]), float(pt[2])),
                                  float(s[k]), float(t[k])))
    return found


def split_crossings(state: ModelState, tol: float = DEFAULT_TOL,
                    member_ids: set[int] | None = None) -> SplitSummary:
    """Put a node at every crossing and split the crossing members there (X-bracing becomes joined).

    Crossings that fall on the same point (three members through one point) share one node, and a
    member crossed several times is cut into as many pieces. The pieces keep every property of the
    original (section, material, group, design data, orientation). A member that carries member
    loads in any load case is NOT split — its loads would need re-distributing — and is listed in
    ``skipped_loaded``; a crossing that involves one is skipped as a whole.
    """
    import dataclasses

    summary = SplitSummary()
    loaded = {mid for lc in state.load_cases for mid, ml in lc.member_loads.items() if not ml.is_zero()}
    crossings = [c for c in find_crossings(state, tol, member_ids)]
    skipped = sorted({m for c in crossings for m in (c.member_a, c.member_b) if m in loaded})
    crossings = [c for c in crossings if c.member_a not in loaded and c.member_b not in loaded]
    summary.skipped_loaded = skipped
    summary.crossings = len(crossings)
    if not crossings:
        return summary

    by_id = {m.id: m for m in state.members}
    node_at: dict[tuple[int, int, int], int] = {}

    def node_for(point: tuple[float, float, float]) -> int:
        key = tuple(round(v / (2 * tol)) for v in point)        # points within ~tol share a node
        if key not in node_at:
            node_at[key] = state.add_node(*point).id
            summary.nodes_created += 1
        return node_at[key]

    cuts: dict[int, dict[int, float]] = {}          # member -> {node id: parameter along it}
    for c in crossings:
        nid = node_for(c.point)                     # a member crossed by two others at one point
        cuts.setdefault(c.member_a, {})[nid] = c.param_a     # meets the same node twice: keep one
        cuts.setdefault(c.member_b, {})[nid] = c.param_b

    keep = [f.name for f in dataclasses.fields(MemberData) if f.name not in ("id", "node_i", "node_j")]
    for mid, pieces in cuts.items():
        old = by_id[mid]
        chain = [old.node_i] + [nid for nid, _ in sorted(pieces.items(), key=lambda kv: kv[1])] + [old.node_j]
        state.remove_member(mid)
        summary.members_split += 1
        for a, b in zip(chain, chain[1:]):
            new = state.add_member(a, b)
            for name in keep:
                setattr(new, name, getattr(old, name))
            summary.members_created += 1
    return summary
