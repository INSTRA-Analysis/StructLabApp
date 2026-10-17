"""LinearSolver: applies boundary conditions and solves [K]{d} = {F}."""

from dataclasses import dataclass

import numpy as np

from core.model import Model
from core.support import SupportType


class UnstableStructureError(np.linalg.LinAlgError):
    """The stiffness matrix is singular or the structure is a mechanism.

    Subclasses LinAlgError (callers that already catch it keep working) and its
    message starts with "Singular matrix" (the UI keys its help dialog on that).
    ``hint`` names the nodes that move the most, which is where the mechanism is.
    """

    def __init__(self, reason: str, hint: str = "") -> None:
        detail = f"\n{hint}" if hint else ""
        super().__init__(f"Singular matrix — {reason}{detail}")
        self.hint = hint


# A linear-elastic structure never legitimately displaces by many times its own
# size; a mechanism does (or gives non-finite numbers). Raw condition-number
# tests are NOT used: pin-jointed trusses have near-zero rotational stiffness at
# bar-only nodes and legitimately sit near 1e-18.
_MECHANISM_DISPLACEMENT_FACTOR = 100.0


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

    def _check_for_mechanism(self, displacements: np.ndarray) -> None:
        """Raise UnstableStructureError if the solution is non-finite or absurdly large."""
        coords = np.array([[n.x, n.y, n.z] for n in self.model.nodes])
        extent = max(float(np.linalg.norm(coords.max(axis=0) - coords.min(axis=0))), 1.0)
        per_node = displacements.reshape(-1, self._dpn)[:, :3 if self._dpn == 6 else 2]
        size = np.linalg.norm(per_node, axis=1)
        if np.all(np.isfinite(size)) and size.max() <= _MECHANISM_DISPLACEMENT_FACTOR * extent:
            return
        size = np.where(np.isfinite(size), size, np.inf)
        worst = [int(i) for i in np.argsort(-size)[:3]]
        raise UnstableStructureError(
            "the structure is a mechanism (it can move without any member resisting).",
            hint=("Largest movement at node(s) "
                  + ", ".join(str(i) for i in worst)
                  + " — look for a joint held only by members in one plane, a "
                    "missing brace, or a part not connected to a support."),
        )

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

        try:
            d_f = np.linalg.solve(K_ff, F_f)
        except np.linalg.LinAlgError as exc:
            raise UnstableStructureError(
                "the structure is unstable (check supports, floating nodes, mechanisms)"
            ) from exc

        displacements = np.zeros(self.num_dofs)
        for i, dof in enumerate(active_free):
            displacements[dof] = d_f[i]
        self._check_for_mechanism(displacements)

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
