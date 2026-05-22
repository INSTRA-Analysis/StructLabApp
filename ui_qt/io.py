"""JSON save/load for StructLab model files (.slab).

Version 3 format stores 3D fields (z, I_y, J, fz, mx, my, qz, etc.).
Version 2 backward-compat: loads are in a load_cases array (EN 1990 architecture).
Version 1 backward-compat: node fx/fy/moment and member w_start/w_end are
imported into the default Gravity (G) load case on load.

Serialization logic is shared with canvas.py undo/redo via
ModelState.to_dict() / ModelState.from_dict().
"""

from __future__ import annotations

import json
from pathlib import Path

from ui_qt.model_state import (
    ModelState, NodeData, MemberData,
    SupportType, ElementType, PointLoadData,
    LoadCase, NodeLoad, MemberLoad, LoadCombination,
)


_FILE_VERSION = 3


def save_model(state: ModelState, filepath: str | Path) -> None:
    """Serialize ModelState to a .slab JSON file (version 3)."""
    data = state.to_dict()
    data["version"] = _FILE_VERSION
    Path(filepath).write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_model(filepath: str | Path) -> ModelState:
    """Deserialize a .slab JSON file into a ModelState.

    Handles v3 (full 3D), v2 (EN 1990 loads, 2D-only), and v1 (legacy).
    """
    raw = json.loads(Path(filepath).read_text(encoding="utf-8"))
    version = raw.get("version", 1)

    if version >= 2:
        # v2 and v3 share the same structure; ModelState.from_dict handles
        # missing 3D fields with defaults (z=0, I_y=None, etc.)
        return ModelState.from_dict(raw)

    # ── Version 1 backward-compat ────────────────────────────────────────────
    s = ModelState()
    for nd in raw["nodes"]:
        node = NodeData(
            id=nd["id"], x=nd["x"], y=nd["y"],
            support_type=SupportType[nd["support"]],
            spring_kx=nd.get("spring_kx", 0.0),
            spring_ky=nd.get("spring_ky", 0.0),
            spring_ktheta=nd.get("spring_ktheta", 0.0),
        )
        s.nodes.append(node)

    for md in raw["members"]:
        member = MemberData(
            id=md["id"], node_i=md["ni"], node_j=md["nj"],
            element_type=ElementType[md["type"]],
            E=md.get("E", 210e9),
            A=md.get("A", 0.03),
            I=md.get("I", 300e-6),
            n_sub=md.get("n_sub", 10),
            density=md.get("density", 0.0),
        )
        s.members.append(member)

    # Import per-node/member loads into default G case
    lc = s.load_cases[0]
    for nd_raw in raw["nodes"]:
        fx     = nd_raw.get("fx", 0.0)
        fy     = nd_raw.get("fy", 0.0)
        moment = nd_raw.get("moment", 0.0)
        if fx != 0.0 or fy != 0.0 or moment != 0.0:
            lc.set_node_load(nd_raw["id"], NodeLoad(fx=fx, fy=fy, moment=moment))
    for md_raw in raw["members"]:
        legacy_udl = md_raw.get("udl_w", 0.0)
        w_start    = md_raw.get("w_start", legacy_udl)
        w_end      = md_raw.get("w_end",   legacy_udl)
        point_loads = [
            PointLoadData(
                load_type=pl["load_type"],
                position=pl["position"],
                magnitude=pl["magnitude"],
            )
            for pl in md_raw.get("point_loads", [])
        ]
        if w_start != 0.0 or w_end != 0.0 or point_loads:
            lc.set_member_load(md_raw["id"], MemberLoad(
                w_start=w_start, w_end=w_end, point_loads=point_loads,
            ))

    s._next_node_id   = raw.get("_next_node_id",
                                 max((n.id for n in s.nodes),   default=-1) + 1)
    s._next_member_id = raw.get("_next_member_id",
                                 max((m.id for m in s.members), default=-1) + 1)
    return s
