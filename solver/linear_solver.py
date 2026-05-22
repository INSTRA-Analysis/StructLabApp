"""LinearSolver: applies boundary conditions and solves [K]{d} = {F}."""

from dataclasses import dataclass

import numpy as np

from core.model import Model
from core.support import SupportType


@dataclass
class SolverResult:
    displacements: np.ndarray   # full (num_dofs,) displacement vector
    reactions: np.ndarray       # full (num_dofs,) reaction force vector (non-zero at restrained DOFs)
    free_dofs: list[int]
    restrained_dofs: list[int]


class LinearSolver:
    """Partition K into free/restrained DOFs, solve for displacements, recover reactions."""

    def __init__(self, model: Model) -> None:
        self.model = model
        self._dpn: int = model.dofs_per_node  # 3 (2D) or 6 (3D)
        self.num_dofs: int = (max(n.id for n in model.nodes) + 1) * self._dpn

    def _classify_dofs(self) -> tuple[list[int], list[int]]:
        """Return (free_dofs, restrained_dofs) based on support definitions."""
        restrained: set[int] = set()
        for support in self.model.supports:
            restrained.update(support.restrained_dofs(self._dpn))
        all_dofs = list(range(self.num_dofs))
        free = [d for d in all_dofs if d not in restrained]
        restrained_sorted = sorted(restrained)
        return free, restrained_sorted

    def solve(self, K: np.ndarray, F: np.ndarray) -> SolverResult:
        """Solve the partitioned system and return displacements and reactions.

        Partitions K as:
            [ K_ff  K_fr ] { d_f }   { F_f }
            [ K_rf  K_rr ] { d_r } = { F_r }

        Since d_r = 0 (no settlement), solve K_ff @ d_f = F_f.
        Reactions = K_rf @ d_f + K_rr @ d_r = K_rf @ d_f.

        DOFs in free_dofs that have zero diagonal stiffness and zero applied
        load (θ at bar-only nodes) are auto-excluded from K_ff — they would
        make it singular.  Their displacements remain zero, which is correct
        (a bar-only node carries no moment so θ is indeterminate but physically
        zero under statics).
        """
        free_dofs, restrained_dofs = self._classify_dofs()

        # Exclude free DOFs where K diagonal is zero AND applied force is zero.
        # These arise at θ DOFs of nodes connected only to BarElements.
        active_free = [
            d for d in free_dofs
            if abs(K[d, d]) > 1e-14 or abs(F[d]) > 1e-14
        ]

        K_ff = K[np.ix_(active_free, active_free)]
        F_f = F[active_free]

        d_f = np.linalg.solve(K_ff, F_f)

        displacements = np.zeros(self.num_dofs)
        for i, dof in enumerate(active_free):
            displacements[dof] = d_f[i]

        # True reactions: R = K @ d - F_effective (zero at free DOFs by construction)
        reactions = np.zeros(self.num_dofs)
        K_rf = K[np.ix_(restrained_dofs, list(range(self.num_dofs)))]
        r_values = K_rf @ displacements - F[restrained_dofs]
        for i, dof in enumerate(restrained_dofs):
            reactions[dof] = r_values[i]

        return SolverResult(
            displacements=displacements,
            reactions=reactions,
            free_dofs=active_free,
            restrained_dofs=restrained_dofs,
        )
