"""Load data models: nodal loads and element-distributed loads."""

from dataclasses import dataclass, field
from enum import Enum, auto


class LoadType(Enum):
    POINT_FORCE = auto()
    POINT_MOMENT = auto()
    UDL = auto()   # uniformly distributed load
    UVL = auto()   # uniformly varying load


class LoadDirection(Enum):
    """Direction in which an element load acts.

    LOCAL_Y  — transverse in the local x-y plane (standard 2D bending, default)
    LOCAL_Z  — transverse in the local x-z plane (weak-axis bending, 3D)
    GLOBAL_X — axial / lateral in global X direction
    GLOBAL_Y — vertical / lateral in global Y direction
    GLOBAL_Z — vertical / lateral in global Z direction (3D)
    """
    LOCAL_Y = auto()
    LOCAL_Z = auto()
    GLOBAL_X = auto()
    GLOBAL_Y = auto()
    GLOBAL_Z = auto()


@dataclass
class NodalLoad:
    """Force and moment applied directly at a node (global axes).

    Positive directions:
      fx, fy, fz → right, up, +Z (global)
      moment → about Z (2D, CCW) or moment_x/y/z → about X/Y/Z (3D, right-hand rule)
    """

    node_id: int
    fx: float = 0.0       # N, positive → right (global +X)
    fy: float = 0.0       # N, positive → up (global +Y)
    moment: float = 0.0   # N·m, positive → CCW about Z (kept for 2D backward compat)
    fz: float = 0.0       # N, positive → +Z (global, 3D only)
    moment_x: float = 0.0  # N·m, positive → right-hand about X (3D only)
    moment_y: float = 0.0  # N·m, positive → right-hand about Y (3D only)

    @property
    def moment_z(self) -> float:
        """Alias for ``moment`` — the Z-axis moment (consistent naming with 3D)."""
        return self.moment


@dataclass
class ElementLoad:
    """Load applied along an element (e.g. UDL, point load on span).

    The ``direction`` field controls which local or global axis the load acts
    along.  Default is LOCAL_Y for backward compatibility with 2D models.
    """

    element_id: int
    load_type: LoadType
    magnitude: float                         # N/m for distributed, N or N·m for point
    position: float = field(default=0.0)     # m from start node (point loads only)
    direction: LoadDirection = field(default=LoadDirection.LOCAL_Y)
