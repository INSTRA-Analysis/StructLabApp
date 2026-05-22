"""UI model state: pure-Python data layer shared by canvas, panels, and solver bridge.

No Qt dependency — fully testable standalone.

Load architecture (7C):
  All loads live in LoadCase objects, not on NodeData/MemberData.
  NodeData and MemberData hold only geometry and section properties.
  ModelState always has at least one LoadCase (the active one).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Literal


# ── Load primitives ───────────────────────────────────────────────────────────

@dataclass
class PointLoadData:
    """A concentrated force or moment at a fractional position along a member."""
    load_type: Literal["FORCE", "MOMENT"]
    position: float   # fractional (0.0 = node_i, 1.0 = node_j)
    magnitude: float  # N (downward positive) for FORCE; N·m (CCW positive) for MOMENT


@dataclass
class NodeLoad:
    """Loads applied at a node for one load case (global axes)."""
    fx: float = 0.0       # N, positive → right
    fy: float = 0.0       # N, positive → up
    moment: float = 0.0   # N·m, positive → CCW about Z (kept for 2D backward compat)
    fz: float = 0.0       # N, positive → +Z (3D only)
    moment_x: float = 0.0 # N·m, positive → right-hand about X (3D only)
    moment_y: float = 0.0 # N·m, positive → right-hand about Y (3D only)

    def is_zero(self) -> bool:
        return (self.fx == 0.0 and self.fy == 0.0 and self.moment == 0.0
                and self.fz == 0.0 and self.moment_x == 0.0 and self.moment_y == 0.0)


@dataclass
class MemberLoad:
    """Loads applied along a member for one load case.

    Coordinate convention (matches canvas): X=right, Y=depth, Z=up.
      w   — local transverse (perpendicular to member), ↓ positive relative to member
      qx  — global X distributed load; +X positive (rightward)
      qy  — global Y distributed load; +Y positive (into scene, 3D only)
      qz  — vertical distributed load; ↓ positive (gravity direction, same as w, 3D only)
    """
    w_start: float = 0.0      # N/m at node_i, ↓ positive (local ⊥ to member)
    w_end: float = 0.0        # N/m at node_j
    qx_start: float = 0.0    # N/m at node_i, +X positive (global X, rightward)
    qx_end: float = 0.0      # N/m at node_j
    qy_start: float = 0.0    # N/m at node_i, +Y positive (global Y, depth — 3D only)
    qy_end: float = 0.0      # N/m at node_j
    qz_start: float = 0.0    # N/m at node_i, ↓ positive (downward / gravity — 3D only)
    qz_end: float = 0.0      # N/m at node_j
    point_loads: list = field(default_factory=list)  # list[PointLoadData]

    def is_zero(self) -> bool:
        return (self.w_start == 0.0 and self.w_end == 0.0
                and self.qx_start == 0.0 and self.qx_end == 0.0
                and self.qy_start == 0.0 and self.qy_end == 0.0
                and self.qz_start == 0.0 and self.qz_end == 0.0
                and not self.point_loads)


# ── Load category (EN 1990) ───────────────────────────────────────────────────

LOAD_CATEGORIES: dict[str, str] = {
    "G": "Permanent (G)",
    "Q": "Variable (Q)",
    "W": "Wind (W)",
    "S": "Snow (S)",
    "E": "Seismic (E)",
}


@dataclass
class LoadCase:
    """One named load case — geometry-independent set of loads."""
    id: int
    name: str
    category: str = "G"                              # key into LOAD_CATEGORIES
    node_loads: dict = field(default_factory=dict)   # node_id  → NodeLoad
    member_loads: dict = field(default_factory=dict) # member_id → MemberLoad
    include_self_weight: bool = False                # True on exactly one G case

    # ── accessors ──────────────────────────────────────────────────────────────

    def get_node_load(self, node_id: int) -> NodeLoad:
        return self.node_loads.get(node_id, NodeLoad())

    def set_node_load(self, node_id: int, load: NodeLoad) -> None:
        if load.is_zero():
            self.node_loads.pop(node_id, None)
        else:
            self.node_loads[node_id] = load

    def get_member_load(self, member_id: int) -> MemberLoad:
        return self.member_loads.get(member_id, MemberLoad())

    def set_member_load(self, member_id: int, load: MemberLoad) -> None:
        if load.is_zero():
            self.member_loads.pop(member_id, None)
        else:
            self.member_loads[member_id] = load

    def remove_node(self, node_id: int) -> None:
        self.node_loads.pop(node_id, None)

    def remove_member(self, member_id: int) -> None:
        self.member_loads.pop(member_id, None)

    # ── serialization ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Serialize to a plain dict (JSON-safe)."""
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "include_self_weight": self.include_self_weight,
            "node_loads": {
                str(nid): {"fx": nl.fx, "fy": nl.fy, "moment": nl.moment,
                            "fz": nl.fz, "moment_x": nl.moment_x, "moment_y": nl.moment_y}
                for nid, nl in self.node_loads.items()
            },
            "member_loads": {
                str(mid): {
                    "w_start": ml.w_start,
                    "w_end": ml.w_end,
                    "qx_start": ml.qx_start,
                    "qx_end": ml.qx_end,
                    "qy_start": ml.qy_start,
                    "qy_end": ml.qy_end,
                    "qz_start": ml.qz_start,
                    "qz_end": ml.qz_end,
                    "point_loads": [
                        {"load_type": pl.load_type, "position": pl.position,
                         "magnitude": pl.magnitude}
                        for pl in ml.point_loads
                    ],
                }
                for mid, ml in self.member_loads.items()
            },
        }

    @classmethod
    def from_dict(cls, d: dict) -> "LoadCase":
        """Deserialize from a plain dict."""
        lc = cls(
            id=d["id"],
            name=d["name"],
            category=d.get("category", "G"),
            include_self_weight=d.get("include_self_weight", False),
        )
        for nid_str, nl_data in d.get("node_loads", {}).items():
            lc.node_loads[int(nid_str)] = NodeLoad(
                fx=nl_data.get("fx", 0.0),
                fy=nl_data.get("fy", 0.0),
                moment=nl_data.get("moment", 0.0),
                fz=nl_data.get("fz", 0.0),
                moment_x=nl_data.get("moment_x", 0.0),
                moment_y=nl_data.get("moment_y", 0.0),
            )
        for mid_str, ml_data in d.get("member_loads", {}).items():
            point_loads = [
                PointLoadData(
                    load_type=pl["load_type"],
                    position=pl["position"],
                    magnitude=pl["magnitude"],
                )
                for pl in ml_data.get("point_loads", [])
            ]
            lc.member_loads[int(mid_str)] = MemberLoad(
                w_start=ml_data.get("w_start", 0.0),
                w_end=ml_data.get("w_end", 0.0),
                qx_start=ml_data.get("qx_start", 0.0),
                qx_end=ml_data.get("qx_end", 0.0),
                qy_start=ml_data.get("qy_start", 0.0),
                qy_end=ml_data.get("qy_end", 0.0),
                qz_start=ml_data.get("qz_start", 0.0),
                qz_end=ml_data.get("qz_end", 0.0),
                point_loads=point_loads,
            )
        return lc


# ── Load combination (EN 1990) ────────────────────────────────────────────────

@dataclass
class LoadCombination:
    """One EN 1990 load combination — weighted sum of named load cases."""
    id: int
    name: str
    limit_state: str = "ULS"                 # "ULS" or "SLS"
    factors: dict = field(default_factory=dict)  # {case_id (int): factor (float)}
    is_auto: bool = False                    # True = generated by auto-generate (replaceable)


# ── Geometry enums ────────────────────────────────────────────────────────────

class SupportType(Enum):
    FREE     = auto()
    FIXED    = auto()
    PIN      = auto()
    ROLLER   = auto()   # vertical roller — free in X, restrained in Y
    ROLLER_Y = auto()   # horizontal roller — free in Y, restrained in X
    ROLLER_Z = auto()   # Z-direction roller — free in Z, restrained in X,Y (3D only)
    SPRING   = auto()


class ElementType(Enum):
    BEAM      = auto()  # full 6x6, no pin releases
    BAR       = auto()  # axial only (pin_i=True, pin_j=True)
    PIN_LEFT  = auto()  # pin at node_i (5x5 condensed)
    PIN_RIGHT = auto()  # pin at node_j (5x5 condensed)


# ── Default section (EN 1993 steel) ──────────────────────────────────────────

DEFAULT_E: float = 210e9   # Pa — EN 1993-1-1
DEFAULT_A: float = 0.03    # m²
DEFAULT_I: float = 300e-6  # m⁴


# ── Project metadata ──────────────────────────────────────────────────────────

@dataclass
class ProjectMetadata:
    """Project identification and signatory information stored in the .slab file."""
    title: str = "Untitled Project"
    project_ref: str = ""
    client: str = ""
    company: str = ""
    description: str = ""
    designer_name: str = ""
    reviewer_name: str = ""
    approver_name: str = ""
    status: str = "Preliminary"   # Preliminary / For Review / Approved

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "project_ref": self.project_ref,
            "client": self.client,
            "company": self.company,
            "description": self.description,
            "designer_name": self.designer_name,
            "reviewer_name": self.reviewer_name,
            "approver_name": self.approver_name,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ProjectMetadata":
        return cls(
            title=d.get("title", "Untitled Project"),
            project_ref=d.get("project_ref", ""),
            client=d.get("client", ""),
            company=d.get("company", ""),
            description=d.get("description", ""),
            designer_name=d.get("designer_name", ""),
            reviewer_name=d.get("reviewer_name", ""),
            approver_name=d.get("approver_name", ""),
            status=d.get("status", "Preliminary"),
        )


# ── Geometry data ─────────────────────────────────────────────────────────────

@dataclass
class NodeData:
    """Node geometry and boundary condition. Loads live in LoadCase."""
    id: int
    x: float
    y: float
    z: float = 0.0
    support_type: SupportType = SupportType.FREE
    spring_kx: float = 0.0      # N/m
    spring_ky: float = 0.0      # N/m
    spring_ktheta: float = 0.0  # N·m/rad  (θ_z)
    spring_kz: float = 0.0      # N/m      (3D only)
    spring_krx: float = 0.0     # N·m/rad  (θ_x, 3D only)
    spring_kry: float = 0.0     # N·m/rad  (θ_y, 3D only)
    spring_krz: float = 0.0     # N·m/rad  (θ_z, 3D only) — alias for ktheta in 3D


@dataclass
class MemberData:
    """Member connectivity and section properties. Loads live in LoadCase."""
    id: int
    node_i: int
    node_j: int
    element_type: ElementType = ElementType.BEAM
    E: float = DEFAULT_E
    A: float = DEFAULT_A
    I: float = DEFAULT_I        # I_z — strong-axis moment of inertia (m⁴)
    I_y: float | None = None    # weak-axis moment of inertia (m⁴, defaults to I)
    J: float = 0.0              # torsional constant (m⁴, 3D only)
    n_sub: int = 10    # sub-elements per member for analysis mesh
    density: float = 0.0  # kg/m³ — 0 disables self-weight for this member
    beta_angle: float = 0.0  # rad — section rotation about local x-axis (3D only)
    fy: float = 275e6   # Pa — yield strength (EN 1993-1-1, default S275)
    W_pl: float = 0.0   # m³ — plastic section modulus (strong axis), 0 = not set
    W_el: float = 0.0   # m³ — elastic section modulus (strong axis), 0 = not set


# ── Full model state ──────────────────────────────────────────────────────────

@dataclass
class ModelState:
    """Mutable container for the full UI model.

    Geometry (nodes, members) is shared across all load cases.
    Loads are stored per LoadCase. At least one LoadCase always exists.
    """

    nodes: list[NodeData] = field(default_factory=list)
    members: list[MemberData] = field(default_factory=list)
    load_cases: list[LoadCase] = field(default_factory=list)
    combinations: list[LoadCombination] = field(default_factory=list)
    active_case_id: int = field(default=0)
    metadata: ProjectMetadata = field(default_factory=ProjectMetadata)
    mode_3d: bool = field(default=False)
    _next_node_id: int = field(default=0, repr=False)
    _next_member_id: int = field(default=0, repr=False)
    _next_case_id: int = field(default=1, repr=False)
    _next_combo_id: int = field(default=0, repr=False)

    def __post_init__(self) -> None:
        if not self.load_cases:
            self.load_cases.append(LoadCase(id=0, name="Dead load", category="G"))

    # ── load case accessors ───────────────────────────────────────────────────

    @property
    def active_case(self) -> LoadCase:
        for lc in self.load_cases:
            if lc.id == self.active_case_id:
                return lc
        return self.load_cases[0]

    def add_load_case(self, name: str, category: str = "Q") -> LoadCase:
        lc = LoadCase(id=self._next_case_id, name=name, category=category)
        self.load_cases.append(lc)
        self._next_case_id += 1
        return lc

    def remove_load_case(self, case_id: int) -> None:
        if len(self.load_cases) <= 1:
            return
        self.load_cases = [lc for lc in self.load_cases if lc.id != case_id]
        if self.active_case_id == case_id:
            self.active_case_id = self.load_cases[0].id

    def get_load_case(self, case_id: int) -> LoadCase | None:
        return next((lc for lc in self.load_cases if lc.id == case_id), None)

    def set_self_weight_case(self, case_id: int | None) -> None:
        """Set include_self_weight exclusively on one load case (None clears all)."""
        for lc in self.load_cases:
            lc.include_self_weight = (lc.id == case_id) if case_id is not None else False

    # ── combination operations ────────────────────────────────────────────────

    def add_combination(self, name: str, limit_state: str = "ULS") -> LoadCombination:
        c = LoadCombination(id=self._next_combo_id, name=name, limit_state=limit_state)
        self.combinations.append(c)
        self._next_combo_id += 1
        return c

    def remove_combination(self, combo_id: int) -> None:
        self.combinations = [c for c in self.combinations if c.id != combo_id]

    def get_combination(self, combo_id: int) -> LoadCombination | None:
        return next((c for c in self.combinations if c.id == combo_id), None)

    # ── node operations ───────────────────────────────────────────────────────

    def add_node(self, x: float, y: float, z: float = 0.0) -> NodeData:
        node = NodeData(id=self._next_node_id, x=x, y=y, z=z)
        self.nodes.append(node)
        self._next_node_id += 1
        return node

    def remove_node(self, node_id: int) -> None:
        self.nodes = [n for n in self.nodes if n.id != node_id]
        self.members = [m for m in self.members
                        if m.node_i != node_id and m.node_j != node_id]
        for lc in self.load_cases:
            lc.remove_node(node_id)

    def get_node(self, node_id: int) -> NodeData | None:
        return next((n for n in self.nodes if n.id == node_id), None)

    # ── member operations ─────────────────────────────────────────────────────

    def add_member(self, node_i: int, node_j: int) -> MemberData | None:
        if not self.get_node(node_i) or not self.get_node(node_j):
            return None
        member = MemberData(id=self._next_member_id, node_i=node_i, node_j=node_j)
        self.members.append(member)
        self._next_member_id += 1
        return member

    def remove_member(self, member_id: int) -> None:
        self.members = [m for m in self.members if m.id != member_id]
        for lc in self.load_cases:
            lc.remove_member(member_id)

    def get_member(self, member_id: int) -> MemberData | None:
        return next((m for m in self.members if m.id == member_id), None)

    # ── convenience ───────────────────────────────────────────────────────────

    def clear(self, keep_mode_3d: bool = False) -> None:
        _mode = self.mode_3d if keep_mode_3d else False
        self.nodes.clear()
        self.members.clear()
        self.load_cases.clear()
        self.load_cases.append(LoadCase(id=0, name="Dead load", category="G"))
        self.combinations.clear()
        self.active_case_id = 0
        self.metadata = ProjectMetadata()
        self.mode_3d = _mode
        self._next_node_id = 0
        self._next_member_id = 0
        self._next_case_id = 1
        self._next_combo_id = 0

    def node_at(self, x: float, y: float, z: float = 0.0, tol: float = 0.1) -> NodeData | None:
        return next(
            (n for n in self.nodes
             if abs(n.x - x) <= tol and abs(n.y - y) <= tol and abs(n.z - z) <= tol),
            None,
        )

    # ── serialization ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Serialize the full model state to a plain dict (JSON-safe).

        Used by both canvas undo/redo snapshots and io.py save/load.
        """
        return {
            "metadata": self.metadata.to_dict(),
            "nodes": [
                {"id": n.id, "x": n.x, "y": n.y, "z": n.z,
                 "support": n.support_type.name,
                 "spring_kx": n.spring_kx, "spring_ky": n.spring_ky,
                 "spring_ktheta": n.spring_ktheta,
                 "spring_kz": n.spring_kz, "spring_krx": n.spring_krx,
                 "spring_kry": n.spring_kry, "spring_krz": n.spring_krz}
                for n in self.nodes
            ],
            "members": [
                {"id": m.id, "ni": m.node_i, "nj": m.node_j,
                 "type": m.element_type.name,
                 "E": m.E, "A": m.A, "I": m.I,
                 "I_y": m.I_y, "J": m.J, "beta_angle": m.beta_angle,
                 "n_sub": m.n_sub, "density": m.density,
                 "fy": m.fy, "W_pl": m.W_pl, "W_el": m.W_el}
                for m in self.members
            ],
            "load_cases": [lc.to_dict() for lc in self.load_cases],
            "active_case_id": self.active_case_id,
            "combinations": [
                {"id": c.id, "name": c.name,
                 "limit_state": c.limit_state,
                 "factors": {str(k): v for k, v in c.factors.items()},
                 "is_auto": c.is_auto}
                for c in self.combinations
            ],
            "mode_3d": self.mode_3d,
            "_next_node_id": self._next_node_id,
            "_next_member_id": self._next_member_id,
            "_next_case_id": self._next_case_id,
            "_next_combo_id": self._next_combo_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ModelState":
        """Deserialize from a plain dict.

        Handles both full v2+ snapshots and older snapshots that may lack
        combinations or include_self_weight.
        """
        s = cls()
        if "metadata" in d:
            s.metadata = ProjectMetadata.from_dict(d["metadata"])
        for nd in d["nodes"]:
            s.nodes.append(NodeData(
                id=nd["id"], x=nd["x"], y=nd["y"],
                z=nd.get("z", 0.0),
                support_type=SupportType[nd["support"]],
                spring_kx=nd.get("spring_kx", 0.0),
                spring_ky=nd.get("spring_ky", 0.0),
                spring_ktheta=nd.get("spring_ktheta", 0.0),
                spring_kz=nd.get("spring_kz", 0.0),
                spring_krx=nd.get("spring_krx", 0.0),
                spring_kry=nd.get("spring_kry", 0.0),
                spring_krz=nd.get("spring_krz", 0.0),
            ))
        for md in d["members"]:
            s.members.append(MemberData(
                id=md["id"], node_i=md["ni"], node_j=md["nj"],
                element_type=ElementType[md["type"]],
                E=md.get("E", 210e9), A=md.get("A", 0.03),
                I=md.get("I", 300e-6), n_sub=md.get("n_sub", 10),
                I_y=md.get("I_y", None), J=md.get("J", 0.0),
                beta_angle=md.get("beta_angle", 0.0),
                density=md.get("density", 0.0),
                fy=md.get("fy", 275e6),
                W_pl=md.get("W_pl", 0.0),
                W_el=md.get("W_el", 0.0),
            ))
        if "load_cases" in d:
            s.load_cases.clear()
            for lc_data in d["load_cases"]:
                s.load_cases.append(LoadCase.from_dict(lc_data))
            s.active_case_id = d.get(
                "active_case_id",
                s.load_cases[0].id if s.load_cases else 0,
            )
            s._next_case_id = d.get("_next_case_id", len(s.load_cases))
        if "combinations" in d:
            s.combinations.clear()
            for c_data in d["combinations"]:
                s.combinations.append(LoadCombination(
                    id=c_data["id"],
                    name=c_data["name"],
                    limit_state=c_data.get("limit_state", "ULS"),
                    factors={int(k): v
                             for k, v in c_data.get("factors", {}).items()},
                    is_auto=c_data.get("is_auto", False),
                ))
            s._next_combo_id = d.get("_next_combo_id", len(s.combinations))
        s._next_node_id = d.get("_next_node_id", len(s.nodes))
        s._next_member_id = d.get("_next_member_id", len(s.members))
        # Auto-detect 3D from z≠0 for old files that predate mode_3d field
        s.mode_3d = d.get("mode_3d", any(n.z != 0.0 for n in s.nodes))
        return s
