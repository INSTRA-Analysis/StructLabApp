"""Support data model: boundary conditions applied at nodes.

A Support combines a rigid restraint type (SupportType) with optional elastic
spring stiffnesses.  Springs and rigid restraints are independent: a PINNED
support can carry a rotational spring; a FREE node can sit on a translational
spring (Winkler foundation, prop, etc.).
"""

from dataclasses import dataclass, field
from enum import Enum, auto


class SupportType(Enum):
    FREE = auto()
    PINNED = auto()
    ROLLER_X = auto()   # free to move in X, restrained in Y (and Z in 3D)
    ROLLER_Y = auto()   # free to move in Y, restrained in X (and Z in 3D)
    ROLLER_Z = auto()   # free to move in Z, restrained in X and Y (3D only)
    FIXED = auto()


@dataclass
class Support:
    """Boundary condition applied at a specific node.

    Spring stiffnesses add elastic stiffness to the global K diagonal at the
    corresponding DOF without fully restraining it.  Values of 0.0 are ignored
    (no spring).

    In 2D mode (dofs_per_node=3) the z / rx / ry springs are ignored.
    """

    node_id: int
    support_type: SupportType
    spring_stiffness_x: float = field(default=0.0)      # N/m
    spring_stiffness_y: float = field(default=0.0)      # N/m
    spring_stiffness_theta: float = field(default=0.0)  # N·m/rad  (θ_z in both 2D and 3D)
    spring_stiffness_z: float = field(default=0.0)      # N/m      (dz, 3D only)
    spring_stiffness_rx: float = field(default=0.0)     # N·m/rad  (θ_x, 3D only)
    spring_stiffness_ry: float = field(default=0.0)     # N·m/rad  (θ_y, 3D only)

    def restrained_dofs(self, dofs_per_node: int = 3) -> list[int]:
        """Return global DOF indices fully restrained by rigid support type.

        With dofs_per_node=3 (2D): indices in [0, 1, 2] range per node.
        With dofs_per_node=6 (3D): indices in [0..5] range per node.
        """
        base = self.node_id * dofs_per_node
        if dofs_per_node == 3:
            restraints_2d = {
                SupportType.FREE:     [],
                SupportType.PINNED:   [base, base + 1],
                SupportType.ROLLER_X: [base + 1],
                SupportType.ROLLER_Y: [base],
                SupportType.ROLLER_Z: [base, base + 1],  # restrained in X,Y; free in Z → treats Z as the "free" axis in 3D
                SupportType.FIXED:    [base, base + 1, base + 2],
            }
            return restraints_2d[self.support_type]
        else:
            # 3D: 6 DOFs / node [dx, dy, dz, θ_x, θ_y, θ_z]
            dx, dy, dz = base, base + 1, base + 2
            rx, ry, rz = base + 3, base + 4, base + 5
            restraints_3d = {
                SupportType.FREE:     [],
                SupportType.PINNED:   [dx, dy, dz],
                SupportType.ROLLER_X: [dy, dz],         # free in X
                SupportType.ROLLER_Y: [dx, dz],         # free in Y
                SupportType.ROLLER_Z: [dx, dy],         # free in Z
                SupportType.FIXED:    [dx, dy, dz, rx, ry, rz],
            }
            return restraints_3d[self.support_type]

    def spring_contributions(self, dofs_per_node: int = 3) -> list[tuple[int, float]]:
        """Return (global_dof_index, stiffness) for each active spring (k > 0).

        With dofs_per_node=3, z/rx/ry springs are ignored (no effect in 2D).
        """
        base = self.node_id * dofs_per_node
        result: list[tuple[int, float]] = []
        if self.spring_stiffness_x > 0.0:
            result.append((base, self.spring_stiffness_x))
        if self.spring_stiffness_y > 0.0:
            result.append((base + 1, self.spring_stiffness_y))
        if dofs_per_node == 3:
            # 2D: DOF order [dx, dy, θ_z]
            if self.spring_stiffness_theta > 0.0:
                result.append((base + 2, self.spring_stiffness_theta))
        else:
            # 3D: DOF order [dx, dy, dz, θ_x, θ_y, θ_z]
            if self.spring_stiffness_z > 0.0:
                result.append((base + 2, self.spring_stiffness_z))
            if self.spring_stiffness_rx > 0.0:
                result.append((base + 3, self.spring_stiffness_rx))
            if self.spring_stiffness_ry > 0.0:
                result.append((base + 4, self.spring_stiffness_ry))
            if self.spring_stiffness_theta > 0.0:
                result.append((base + 5, self.spring_stiffness_theta))
        return result
