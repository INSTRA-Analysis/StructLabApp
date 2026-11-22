"""UI model state: pure-Python data layer shared by canvas, panels, and solver bridge.

No Qt dependency — fully testable standalone.

Load architecture (7C):
  All loads live in LoadCase objects, not on NodeData/MemberData.
  NodeData and MemberData hold only geometry and section properties.
  ModelState always has at least one LoadCase (the active one).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Literal

import numpy as np


# ── Load primitives ───────────────────────────────────────────────────────────

@dataclass
class PointLoadData:
    """A concentrated force or moment at a fractional position along a member."""
    load_type: Literal["FORCE", "MOMENT"]
    position: float   # fractional (0.0 = node_i, 1.0 = node_j)
    magnitude: float  # N (downward positive) for FORCE; N·m (CCW positive) for MOMENT


@dataclass
class PartialDistLoad:
    """A partial-span distributed load acting between two positions on a member.

    Intensity varies linearly from w_start at start_pos to w_end at end_pos.
    Both positions are fractional (0.0 = node_i end, 1.0 = node_j end).
    Sign convention: positive = downward (local ⊥ to member), same as w.
    """
    start_pos: float  # 0.0 – 1.0
    end_pos:   float  # 0.0 – 1.0, must be > start_pos
    w_start:   float  # N/m at start_pos, ↓ positive
    w_end:     float  # N/m at end_pos


@dataclass
class DistLoad:
    """Full-span distributed load on a member (one direction, linearly varying).

    direction: 'w' = local ⊥ to member (↓ positive), 'qx'/'qy'/'qz' = global axes.
    w_start/w_end: intensity in N/m at node_i/node_j.
    """
    direction: str          # "w", "qx", "qy", or "qz"
    w_start:   float = 0.0  # N/m at node_i
    w_end:     float = 0.0  # N/m at node_j


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

    Use dist_loads for all full-span distributed loads. The legacy scalar fields
    (w_start, w_end, qx_start …) are supported for backward compat — __post_init__
    migrates any non-zero value into a DistLoad entry and zeros the scalar.
    """
    dist_loads:    list = field(default_factory=list)  # list[DistLoad]
    point_loads:   list = field(default_factory=list)  # list[PointLoadData]
    partial_loads: list = field(default_factory=list)  # list[PartialDistLoad]
    # Legacy scalar fields — auto-migrated and zeroed by __post_init__
    w_start:  float = 0.0
    w_end:    float = 0.0
    qx_start: float = 0.0
    qx_end:   float = 0.0
    qy_start: float = 0.0
    qy_end:   float = 0.0
    qz_start: float = 0.0
    qz_end:   float = 0.0

    def __post_init__(self) -> None:
        for key, ws, we in [
            ("w",  self.w_start,  self.w_end),
            ("qx", self.qx_start, self.qx_end),
            ("qy", self.qy_start, self.qy_end),
            ("qz", self.qz_start, self.qz_end),
        ]:
            if ws != 0.0 or we != 0.0:
                self.dist_loads.append(DistLoad(key, ws, we))
        self.w_start = self.w_end = 0.0
        self.qx_start = self.qx_end = 0.0
        self.qy_start = self.qy_end = 0.0
        self.qz_start = self.qz_end = 0.0

    def net(self, direction: str) -> tuple[float, float]:
        """Summed intensity for one direction across all dist_loads entries."""
        ws = sum(dl.w_start for dl in self.dist_loads if dl.direction == direction)
        we = sum(dl.w_end   for dl in self.dist_loads if dl.direction == direction)
        return ws, we

    def is_zero(self) -> bool:
        return not self.dist_loads and not self.point_loads and not self.partial_loads


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
    # Cases sharing a non-empty group are alternatives (e.g. wind +X / wind -X): the
    # auto-generated combinations never add two of them together.
    exclusive_group: str = ""
    # Multiplier on self-weight when include_self_weight is set. 1.0 for a stored
    # case; a combination's merged case carries its partial factor here.
    # Not serialised.
    self_weight_factor: float = 1.0

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
            **({"exclusive_group": self.exclusive_group} if self.exclusive_group else {}),
            "node_loads": {
                str(nid): {"fx": nl.fx, "fy": nl.fy, "moment": nl.moment,
                            "fz": nl.fz, "moment_x": nl.moment_x, "moment_y": nl.moment_y}
                for nid, nl in self.node_loads.items()
            },
            "member_loads": {
                str(mid): {
                    "dist_loads": [
                        {"direction": dl.direction,
                         "w_start": dl.w_start, "w_end": dl.w_end}
                        for dl in ml.dist_loads
                    ],
                    "point_loads": [
                        {"load_type": pl.load_type, "position": pl.position,
                         "magnitude": pl.magnitude}
                        for pl in ml.point_loads
                    ],
                    "partial_loads": [
                        {"start_pos": p.start_pos, "end_pos": p.end_pos,
                         "w_start": p.w_start, "w_end": p.w_end}
                        for p in ml.partial_loads
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
            exclusive_group=d.get("exclusive_group", ""),
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
            partial_loads = [
                PartialDistLoad(
                    start_pos=p["start_pos"],
                    end_pos=p["end_pos"],
                    w_start=p["w_start"],
                    w_end=p["w_end"],
                )
                for p in ml_data.get("partial_loads", [])
            ]
            dl_raw = ml_data.get("dist_loads")
            if dl_raw is not None:
                # New format: explicit dist_loads list
                dist_loads = [
                    DistLoad(d["direction"], d.get("w_start", 0.0), d.get("w_end", 0.0))
                    for d in dl_raw
                ]
                lc.member_loads[int(mid_str)] = MemberLoad(
                    dist_loads=dist_loads,
                    point_loads=point_loads,
                    partial_loads=partial_loads,
                )
            else:
                # Old format: scalar fields — __post_init__ migrates them
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
                    partial_loads=partial_loads,
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
    CUSTOM   = auto()   # any other set of restrained DOFs, ticked axis by axis


# ── Support restraints: six flags per node, one table for 2D and 3D ──────────
# A support is stored as the DOFs it restrains, (ux, uy, uz, θx, θy, θz), in the model's
# own axes.  2D analyses ux, uy and θz (PLANAR_DOFS); the other three hold the
# out-of-plane restraints, so rotate_axes carries a support through a 2D <-> 3D switch with its
# physical meaning intact (a wall roller stays free vertically).  The presets below are the
# same six flags in both modes and reproduce the solver's former per-mode tables exactly.
DOF_NAMES: tuple[str, ...] = ("ux", "uy", "uz", "θx", "θy", "θz")
# 3D analysis types -> per-node DOFs the solver holds at every node (core Model.locked_dofs).
ANALYSIS_TYPES: dict[str, tuple[int, ...]] = {"space": (), "plane_xz": (1, 3, 5)}
PLANAR_DOFS: tuple[int, ...] = (0, 1, 5)
_T, _F = True, False
SUPPORT_PRESETS: dict[SupportType, tuple[bool, ...]] = {
    SupportType.FREE:     (_F, _F, _F, _F, _F, _F),
    SupportType.FIXED:    (_T, _T, _T, _T, _T, _T),
    SupportType.PIN:      (_T, _T, _T, _F, _F, _F),
    SupportType.ROLLER:   (_F, _T, _T, _F, _F, _F),   # free in X
    SupportType.ROLLER_Y: (_T, _F, _T, _F, _F, _F),   # free in Y
    SupportType.ROLLER_Z: (_T, _T, _F, _F, _F, _F),   # free in Z
    SupportType.SPRING:   (_F, _F, _F, _F, _F, _F),
}
_SPRING_FIELDS = ("spring_kx", "spring_ky", "spring_ktheta", "spring_kz",
                  "spring_krx", "spring_kry", "spring_krz")


SPRING_FOR_DOF: tuple[str, ...] = ("spring_kx", "spring_ky", "spring_kz",
                                   "spring_krx", "spring_kry", "spring_ktheta")


def planar_restraints(ux: bool, uy: bool, rz: bool) -> tuple[bool, ...]:
    """Six flags for a support ticked in 2D, with sensible out-of-plane restraints for 3D:
    out-of-plane translation held when any translation is, out-of-plane rotations only when
    fully fixed.  Reproduces every preset (a wall roller becomes a vertical roller in 3D)."""
    fixed = ux and uy and rz
    return (bool(ux), bool(uy), bool(ux or uy), fixed, fixed, bool(rz))


def classify_support(restraints: tuple[bool, ...], has_springs: bool,
                     spring_preset: bool = False) -> SupportType:
    """The preset a set of restraints matches, CUSTOM if none.

    A rigid preset has no springs, so restraints plus springs (a pin with a rotational
    spring, say) is CUSTOM: the panel then shows both instead of hiding the springs.
    """
    restraints = tuple(bool(r) for r in restraints)
    if not any(restraints):
        return SupportType.SPRING if (has_springs or spring_preset) else SupportType.FREE
    if has_springs:
        return SupportType.CUSTOM
    for preset, flags in SUPPORT_PRESETS.items():
        if flags == restraints and preset not in (SupportType.FREE, SupportType.SPRING):
            return preset
    return SupportType.CUSTOM


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
    # ``restraints`` (six flags, see SUPPORT_PRESETS) is the stored truth; ``support_type`` is a
    # property over it (installed below): reading gives the matching preset (or CUSTOM),
    # assigning a preset sets the flags and, for a rigid preset, clears the springs.

    def has_springs(self) -> bool:
        return any(getattr(self, name, 0.0) > 0 for name in _SPRING_FIELDS)

    def set_restraints(self, flags) -> None:
        """Set the six restrained-DOF flags (ux, uy, uz, θx, θy, θz)."""
        flags = tuple(bool(f) for f in flags)
        if len(flags) != 6:
            raise ValueError(f"six restraint flags expected, got {len(flags)}")
        self.restraints = flags


def _get_support_type(self: NodeData) -> SupportType:
    return classify_support(self.restraints, self.has_springs(), getattr(self, "_spring_preset", False))


def _set_support_type(self: NodeData, value: SupportType) -> None:
    if value is SupportType.CUSTOM:
        if not hasattr(self, "restraints"):
            self.restraints = SUPPORT_PRESETS[SupportType.FREE]
        return                                   # custom flags are set with set_restraints
    self.restraints = SUPPORT_PRESETS[value]
    self._spring_preset = value is SupportType.SPRING
    if value is not SupportType.SPRING:
        for name in _SPRING_FIELDS:
            setattr(self, name, 0.0)


NodeData.support_type = property(_get_support_type, _set_support_type)


_SUPPORT_LABELS = {
    SupportType.FREE: "Free", SupportType.FIXED: "Fixed", SupportType.PIN: "Pinned",
    SupportType.ROLLER: "Roller, free in X", SupportType.ROLLER_Y: "Roller, free in Y",
    SupportType.ROLLER_Z: "Roller, free in Z", SupportType.SPRING: "Spring",
}
_PLANAR_LABELS = {(True, True, True): "Fixed", (True, True, False): "Pinned",
                  (False, True, False): "Roller, free in X", (True, False, False): "Roller, free in Y"}


def describe_support(node: NodeData, is_2d: bool = False) -> str:
    """Readable support label for reports and tooltips, true to the analysis mode.

    2D reads the in-plane restraints (a support that differs only out of plane gets its 2D
    name); anything without a preset name lists what it restrains, and springs alongside
    restraints are listed too.
    """
    dofs = PLANAR_DOFS if is_2d else tuple(range(6))
    held = [DOF_NAMES[i] for i in dofs if node.restraints[i]]
    springs = [DOF_NAMES[i] for i in dofs if getattr(node, SPRING_FOR_DOF[i]) > 0]
    if not held:
        return "Spring" if (springs or node.support_type is SupportType.SPRING) else "Free"
    if is_2d:
        label = _PLANAR_LABELS.get(tuple(node.restraints[i] for i in PLANAR_DOFS))
    else:
        label = _SUPPORT_LABELS.get(node.support_type)
    if label is None or springs:
        label = "Restrains " + ", ".join(held)
    return label + (f" + springs {', '.join(springs)}" if springs else "")


def analysis_label(state) -> tuple[str, str]:
    """(short, long) description of what the solver analyses, for the status bar and reports."""
    if state.is_2d:
        return "2D frame", "2D frame (XY plane, Y up): 3 DOF per node (ux, uy, θz)"
    if state.analysis_type == "plane_xz":
        return ("Plane frame (XZ)",
                "Plane frame (XZ): 3D engine, uy, θx, θz restrained at every node")
    return "Space frame", "Space frame (Z up): 6 DOF per node"


def node_from_dict(nd: dict) -> NodeData:
    """A node from its saved form.

    Files written before per-axis restraints have only the preset name: its flags are the
    preset's, and springs count only on a SPRING node (the solver ignored them elsewhere), so
    old models solve exactly as before.  Newer files carry the six flags explicitly.
    """
    support = SupportType[nd.get("support", "FREE")]
    springs_apply = "restraints" in nd or support is SupportType.SPRING
    node = NodeData(id=nd["id"], x=nd["x"], y=nd["y"], z=nd.get("z", 0.0),
                    support_type=support,
                    **{name: (nd.get(name, 0.0) if springs_apply else 0.0) for name in _SPRING_FIELDS})
    if "restraints" in nd:
        node.set_restraints(nd["restraints"])
    return node


@dataclass
class MemberData:
    """Member connectivity and section properties. Loads live in LoadCase."""
    id: int
    node_i: int
    node_j: int
    element_type: ElementType = ElementType.BEAM
    group: str = ""    # free descriptive label (e.g. Leg/Diagonal) — display/reporting only
    E: float = DEFAULT_E
    A: float = DEFAULT_A
    I: float = DEFAULT_I        # I_z — strong-axis moment of inertia (m⁴)
    I_y: float | None = None    # weak-axis moment of inertia (m⁴, defaults to I)
    J: float = 0.0              # torsional constant (m⁴, 3D only)
    n_sub: int = 20    # sub-elements per member for analysis mesh
    density: float = 0.0  # kg/m³ — 0 disables self-weight for this member
    beta_angle: float = 0.0  # rad — section rotation about local x-axis (3D only)
    fy: float = 275e6   # Pa — yield strength / fck / fk depending on material
    W_pl: float = 0.0   # m³ — plastic section modulus (strong axis), 0 = not set
    W_el: float = 0.0   # m³ — elastic section modulus (strong axis), 0 = not set
    # Concrete section geometry (EN 1992-1-1 §6.1 check, all SI units)
    b_sec:      float = 0.0    # m  — section width
    h_sec:      float = 0.0    # m  — total depth
    d_eff:      float = 0.0    # m  — effective depth to tension steel centroid
    As_tension: float = 0.0    # m² — tension reinforcement area
    fyk:        float = 500e6  # Pa — reinforcement yield strength (default 500 MPa)
    # True when As_tension was auto-placed at the EC2 §9.2.1.1 code minimum
    # (e.g. by a wizard) rather than chosen by the user — the Design tab
    # flags this so a passing check isn't mistaken for a finished design.
    # Cleared the moment the user applies a value from the properties panel.
    reinforcement_estimated: bool = False


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
    # Saved camera positions: name -> {"az", "el", "cx", "cy", "scale"} (scene coordinates).
    named_views: dict = field(default_factory=dict)
    # Design assumption: where two bracing members cross, they are connected there, so a
    # compression member is held at the crossing while the other one is in tension
    # (design_checks.buckling_length). It does not change the analysis model.
    crossing_braces: bool = False
    active_case_id: int = field(default=0)
    metadata: ProjectMetadata = field(default_factory=ProjectMetadata)
    # "3D" = 6-DOF space model (Z up). "2D" = planar 3-DOF model in the native
    # XY plane (X horizontal, Y vertical/up, z == 0 for all nodes); set_analysis_mode
    # swaps Y<->Z when toggling so a planar model keeps standing. The legacy boolean
    # `mode_3d` is kept as a property over this field for back-compat.
    analysis_mode: str = field(default="3D")
    # 3D analysis type: "space" (all six DOFs) or "plane_xz" (a plane frame in an XZ plane:
    # the solver holds uy, θx, θz at every node — a 2D analysis inside the 3D engine).
    analysis_type: str = field(default="space")
    _next_node_id: int = field(default=0, repr=False)
    _next_member_id: int = field(default=0, repr=False)
    _next_case_id: int = field(default=1, repr=False)
    _next_combo_id: int = field(default=0, repr=False)

    def __post_init__(self) -> None:
        if not self.load_cases:
            self.load_cases.append(LoadCase(id=0, name=LOAD_CATEGORIES["G"], category="G"))

    # ── analysis-mode accessors ───────────────────────────────────────────────

    @property
    def mode_3d(self) -> bool:
        """Back-compat boolean view over analysis_mode (True = 3D)."""
        return self.analysis_mode == "3D"

    @mode_3d.setter
    def mode_3d(self, value: bool) -> None:
        self.analysis_mode = "3D" if value else "2D"

    @property
    def is_2d(self) -> bool:
        return self.analysis_mode == "2D"

    def rotate_axes(self, to_mode: str) -> None:
        """Carry the model between the 2D axes (XY plane, Y up) and the 3D axes (Z up).

        A proper rotation of +90° about X, never a mirror, so every load keeps its physical
        sense: to 3D (x, y, z) -> (x, -z, y), to 2D the inverse (x, y, z) -> (x, z, -y).
        Forces, moments and displacements are vectors and rotate the same way, so a 2D
        anticlockwise moment M becomes My = -M.  A global 'qy' load is a +Y force and 'qz'
        is positive downward, so they map with the signs that keep the force direction.
        Restraint flags and spring stiffnesses follow their axes (no sign).
        """
        if to_mode not in ("2D", "3D"):
            raise ValueError(f"unknown mode {to_mode!r}")
        to_3d = to_mode == "3D"

        def rot(x: float, y: float, z: float) -> tuple[float, float, float]:
            x, y, z = (x, -z, y) if to_3d else (x, z, -y)
            return x + 0.0, y + 0.0, z + 0.0           # no negative zeros

        # Loads in a member's own axes (w, partial loads, member point forces and moments)
        # keep their physical direction only if the member's local y does: 2D takes y 90°
        # anticlockwise from the member, 3D takes it upward, and the two disagree on columns
        # and on members drawn right to left.  Judged with the model in its 3D axes.
        if not to_3d:
            flipped = self._members_with_reversed_local_y()
        for n in self.nodes:
            n.x, n.y, n.z = rot(n.x, n.y, n.z)
            ux, uy, uz, rx, ry, rz = n.restraints
            n.restraints = (ux, uz, uy, rx, rz, ry)
            n.spring_ky, n.spring_kz = n.spring_kz, n.spring_ky
            n.spring_ktheta, n.spring_kry = n.spring_kry, n.spring_ktheta
        if to_3d:
            flipped = self._members_with_reversed_local_y()
        # qy (+Y force) and qz (downward = -Z force): to 3D qy' = qz, qz' = -qy;
        # to 2D qy' = -qz, qz' = qy.
        dist_map = ({"qy": ("qz", -1.0), "qz": ("qy", 1.0)} if to_3d
                    else {"qy": ("qz", 1.0), "qz": ("qy", -1.0)})
        for lc in self.load_cases:
            for nl in lc.node_loads.values():
                nl.fx, nl.fy, nl.fz = rot(nl.fx, nl.fy, nl.fz)
                nl.moment_x, nl.moment_y, nl.moment = rot(nl.moment_x, nl.moment_y, nl.moment)
            for member_id, ml in lc.member_loads.items():
                reverse = member_id in flipped
                for dl in ml.dist_loads:
                    if dl.direction in dist_map:
                        dl.direction, sign = dist_map[dl.direction]
                        dl.w_start, dl.w_end = sign * dl.w_start + 0.0, sign * dl.w_end + 0.0
                    elif dl.direction == "w" and reverse:
                        dl.w_start, dl.w_end = -dl.w_start + 0.0, -dl.w_end + 0.0
                if reverse:
                    for pdl in ml.partial_loads:
                        pdl.w_start, pdl.w_end = -pdl.w_start + 0.0, -pdl.w_end + 0.0
                    for pl in ml.point_loads:
                        pl.magnitude = -pl.magnitude + 0.0

    def _members_with_reversed_local_y(self) -> set[int]:
        """Members of a planar model (in its 3D axes, XZ plane) whose 2D local y (90°
        anticlockwise from the member, mapped into XZ) opposes the 3D local y."""
        from elements.frame_element import FrameElement
        out: set[int] = set()
        for m in self.members:
            a, b = self.get_node(m.node_i), self.get_node(m.node_j)
            if a is None or b is None:
                continue
            dx, dz = b.x - a.x, b.z - a.z
            length = math.hypot(dx, dz)
            if length < 1e-12:
                continue
            c, s = dx / length, dz / length
            y_2d = np.array([-s, 0.0, c])                     # (-sin, cos) in the XZ plane
            y_3d = FrameElement.local_axes_3d(dx, b.y - a.y, dz, m.beta_angle)[:, 1]
            if float(y_2d @ y_3d) < 0.0:
                out.add(m.id)
        return out

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

    def clear(self) -> None:
        self.nodes.clear()
        self.members.clear()
        self.load_cases.clear()
        self.load_cases.append(LoadCase(id=0, name=LOAD_CATEGORIES["G"], category="G"))
        self.combinations.clear()
        self.named_views.clear()
        self.crossing_braces = False
        self.active_case_id = 0
        self.metadata = ProjectMetadata()
        self.mode_3d = True
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
                 "restraints": [int(r) for r in n.restraints],
                 "spring_kx": n.spring_kx, "spring_ky": n.spring_ky,
                 "spring_ktheta": n.spring_ktheta,
                 "spring_kz": n.spring_kz, "spring_krx": n.spring_krx,
                 "spring_kry": n.spring_kry, "spring_krz": n.spring_krz}
                for n in self.nodes
            ],
            "members": [
                {"id": m.id, "ni": m.node_i, "nj": m.node_j,
                 "type": m.element_type.name, "group": m.group,
                 "E": m.E, "A": m.A, "I": m.I,
                 "I_y": m.I_y, "J": m.J, "beta_angle": m.beta_angle,
                 "n_sub": m.n_sub, "density": m.density,
                 "fy": m.fy, "W_pl": m.W_pl, "W_el": m.W_el,
                 "b_sec": m.b_sec, "h_sec": m.h_sec, "d_eff": m.d_eff,
                 "As_tension": m.As_tension, "fyk": m.fyk,
                 "reinforcement_estimated": m.reinforcement_estimated}
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
            **({"named_views": self.named_views} if self.named_views else {}),
            **({"crossing_braces": True} if self.crossing_braces else {}),
            "analysis_mode": self.analysis_mode,
            "analysis_type": self.analysis_type,
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
            s.nodes.append(node_from_dict(nd))
        for md in d["members"]:
            s.members.append(MemberData(
                id=md["id"], node_i=md["ni"], node_j=md["nj"],
                element_type=ElementType[md["type"]],
                group=md.get("group", ""),
                E=md.get("E", 210e9), A=md.get("A", 0.03),
                I=md.get("I", 300e-6), n_sub=md.get("n_sub", 20),
                I_y=md.get("I_y", None), J=md.get("J", 0.0),
                beta_angle=md.get("beta_angle", 0.0),
                density=md.get("density", 0.0),
                fy=md.get("fy", 275e6),
                W_pl=md.get("W_pl", 0.0),
                W_el=md.get("W_el", 0.0),
                b_sec=md.get("b_sec", 0.0),
                h_sec=md.get("h_sec", 0.0),
                d_eff=md.get("d_eff", 0.0),
                As_tension=md.get("As_tension", 0.0),
                fyk=md.get("fyk", 500e6),
                reinforcement_estimated=md.get("reinforcement_estimated", False),
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
        s.named_views = {str(k): dict(v) for k, v in d.get("named_views", {}).items()}
        s.crossing_braces = bool(d.get("crossing_braces", False))
        s._next_node_id = d.get("_next_node_id", len(s.nodes))
        s._next_member_id = d.get("_next_member_id", len(s.members))
        # Prefer explicit analysis_mode (v4+); else fall back to the legacy
        # mode_3d boolean, or auto-detect 3D from z≠0 for the oldest files.
        s.analysis_type = d.get("analysis_type", "space")
        if s.analysis_type not in ANALYSIS_TYPES:
            s.analysis_type = "space"
        if "analysis_mode" in d:
            s.analysis_mode = d["analysis_mode"]
        else:
            s.mode_3d = d.get("mode_3d", any(n.z != 0.0 for n in s.nodes))
        return s
