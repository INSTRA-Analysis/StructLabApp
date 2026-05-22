"""Node data model: a 3D point with up to six degrees of freedom per node.

For 2D models (all z = 0) the effective DOF count remains 3 (dx, dy, θ_z).
For 3D models (any z ≠ 0) all 6 DOFs are active: dx, dy, dz, θ_x, θ_y, θ_z.
The caller determines dofs_per_node; Node does not inspect the global model.
"""

from dataclasses import dataclass


@dataclass
class Node:
    """A structural node at position (x, y, z) with a unique integer ID.

    z defaults to 0 for backward compatibility with 2D models.
    """

    id: int
    x: float
    y: float
    z: float = 0.0

    def dof_indices(self, dofs_per_node: int = 3) -> list[int]:
        """Return the global DOF indices for this node.

        With dofs_per_node=3 (2D): [dx, dy, θ_z]
        With dofs_per_node=6 (3D): [dx, dy, dz, θ_x, θ_y, θ_z]
        """
        base = self.id * dofs_per_node
        return [base + k for k in range(dofs_per_node)]
