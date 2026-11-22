"""LinearSolver: applies boundary conditions and solves [K]{d} = {F}."""

from dataclasses import dataclass

import numpy as np
from scipy import sparse
from scipy.sparse.linalg import splu

from core.model import Model
from core.support import SupportType


class UnstableStructureError(np.linalg.LinAlgError):
    """The stiffness matrix is singular or the structure is a mechanism.

    Subclasses LinAlgError (callers that already catch it keep working) and its
    message starts with "Singular matrix" (the UI keys its help dialog on that).
    ``hint`` names the nodes that move the most, which is where the mechanism is.
    """

    def __init__(self, reason: str, hint: str = "", node_ids: tuple[int, ...] = ()) -> None:
        detail = f"\n{hint}" if hint else ""
        super().__init__(f"Singular matrix — {reason}{detail}")
        self.hint = hint
        self.node_ids = tuple(node_ids)       # where the mechanism is (for select-and-zoom)


# A linear-elastic structure never legitimately displaces by many times its own
# size; a mechanism does (or gives non-finite numbers). Raw condition-number
# tests are NOT used: pin-jointed trusses have near-zero rotational stiffness at
# bar-only nodes and legitimately sit near 1e-18.
_MECHANISM_DISPLACEMENT_FACTOR = 100.0
# A linear analysis never turns a node through more than a few degrees; 100 rad is only
# reached by an unrestrained rotation (a loaded twist held by nothing but _rotation_guard).
_MECHANISM_ROTATION_RAD = 100.0


@dataclass
class SolverResult:
    displacements: np.ndarray   # full (num_dofs,) displacement vector
    reactions: np.ndarray       # full (num_dofs,) reaction force vector (non-zero at restrained DOFs)
    free_dofs: list[int]
    restrained_dofs: list[int]
    # Forces taken by Model.locked_dofs (e.g. a plane frame's out-of-plane locks), kept out
    # of the support reactions; near zero when everything acts in the plane.
    lock_forces: np.ndarray | None = None


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
        per_dof = displacements.reshape(-1, self._dpn)
        n_trans = 3 if self._dpn == 6 else 2
        size = np.linalg.norm(per_dof[:, :n_trans], axis=1)
        turn = np.abs(per_dof[:, n_trans:]).max(axis=1)
        if (np.all(np.isfinite(size)) and np.all(np.isfinite(turn))
                and size.max() <= _MECHANISM_DISPLACEMENT_FACTOR * extent
                and turn.max() <= _MECHANISM_ROTATION_RAD):
            return
        size = np.where(turn > _MECHANISM_ROTATION_RAD, np.inf, size)
        size = np.where(np.isfinite(size), size, np.inf)
        worst = [int(i) for i in np.argsort(-size)[:3]]
        raise UnstableStructureError(
            "the structure is a mechanism (it can move without any member resisting).",
            hint=("Largest movement at node(s) "
                  + ", ".join(str(i) for i in worst)
                  + " — look for a joint held only by members in one plane, a "
                    "missing brace, or a part not connected to a support."),
            node_ids=tuple(worst),
        )

    # Stiffness added to rotational DOFs, relative to the largest diagonal term, ONLY when K_ff
    # is exactly singular (see _rotation_guard).
    _ROTATION_GUARD = 1e-10

    def _rotation_guard(self, active: np.ndarray, diagonal: np.ndarray) -> sparse.spmatrix:
        """A tiny spring on every free rotational DOF, for a K_ff that is exactly singular.

        The common cause is an UNLOADED free rotation: a straight run of members on pins in a
        space frame can twist about its own axis.  The spring (1e-10 of that DOF's own
        diagonal stiffness, so no real stiffness changes by more than 1e-10) fixes that rigid
        twist; a LOADED rotational mechanism then turns through an absurd angle, which
        _check_for_mechanism reports.  A translational mechanism stays singular and is
        reported as before.
        """
        rot_offset = 2 if self._dpn == 3 else 3
        is_rotation = (active % self._dpn) >= rot_offset
        floor = 1e-12 * float(np.abs(diagonal).max())             # a zero diagonal still gets one
        k = self._ROTATION_GUARD * np.maximum(np.abs(diagonal), floor)
        return sparse.diags(np.where(is_rotation, k, 0.0))

    @staticmethod
    def _refine(solve_guarded, K_ff, F_f: np.ndarray, steps: int = 4) -> np.ndarray:
        """Solve with the guarded factor, then correct against the TRUE K_ff (iterative
        refinement): the guard only steers the free twist, never the real displacements."""
        d = solve_guarded(F_f)
        for _ in range(steps):
            d = d + solve_guarded(F_f - K_ff @ d)
        return d

    def _support_dofs(self) -> set[int]:
        restrained: set[int] = set()
        for support in self.model.supports:
            restrained.update(support.restrained_dofs(self._dpn))
        return restrained

    def _locked_dofs(self) -> set[int]:
        """DOFs held at every node by Model.locked_dofs (e.g. uy, θx, θz of a plane frame)."""
        local = tuple(self.model.locked_dofs)
        if any(not 0 <= k < self._dpn for k in local):
            raise ValueError(f"locked_dofs {local} outside 0..{self._dpn - 1}")
        return {n.id * self._dpn + k for n in self.model.nodes for k in local}

    def _classify_dofs(self) -> tuple[list[int], list[int]]:
        """Return (free_dofs, restrained_dofs): support restraints plus the model's locks."""
        restrained = self._support_dofs() | self._locked_dofs()
        all_dofs = list(range(self.num_dofs))
        free = [d for d in all_dofs if d not in restrained]
        restrained_sorted = sorted(restrained)
        return free, restrained_sorted

    def solve(self, K: "np.ndarray | sparse.spmatrix", F: np.ndarray) -> SolverResult:
        """Solve the partitioned system and return displacements and reactions.

        ``K`` may be dense (small models, tests) or sparse (``Assembler.global_stiffness_sparse``,
        what the application uses): the sparse path factorises K_ff with SuperLU.

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
        is_sparse = sparse.issparse(K)
        if is_sparse:
            K = K.tocsr()
        diagonal = K.diagonal() if is_sparse else np.diag(K)

        # Exclude free DOFs where K diagonal is zero AND applied force is zero.
        # These arise at θ DOFs of nodes connected only to BarElements.
        free = np.asarray(free_dofs, dtype=int)
        keep = (np.abs(diagonal[free]) > 1e-14) | (np.abs(F[free]) > 1e-14) if free.size else free
        active = free[keep] if free.size else free
        active_free = active.tolist()
        F_f = F[active]

        unstable = "the structure is unstable (check supports, floating nodes, mechanisms)"
        if active.size == 0:
            d_f = np.zeros(0)
        elif is_sparse:
            # Sparse LU: memory and time grow roughly with the DOF count, not its square/cube.
            K_ff = K[active][:, active].tocsc()
            try:
                d_f = splu(K_ff).solve(F_f)
            except RuntimeError as exc:                   # "Factor is exactly singular"
                try:
                    guarded = splu((K_ff + self._rotation_guard(active, K_ff.diagonal())).tocsc())
                except RuntimeError:
                    raise UnstableStructureError(unstable) from exc
                d_f = self._refine(guarded.solve, K_ff, F_f)
        else:
            K_ff = K[np.ix_(active, active)]
            try:
                d_f = np.linalg.solve(K_ff, F_f)
            except np.linalg.LinAlgError as exc:
                guarded = K_ff + self._rotation_guard(active, np.diag(K_ff)).toarray()
                try:
                    d_f = self._refine(lambda r: np.linalg.solve(guarded, r), K_ff, F_f)
                except np.linalg.LinAlgError:
                    raise UnstableStructureError(unstable) from exc

        displacements = np.zeros(self.num_dofs)
        displacements[active] = d_f
        self._check_for_mechanism(displacements)

        # True reactions: R = K @ d - F_effective (zero at free DOFs by construction)
        reactions = np.zeros(self.num_dofs)
        if restrained_dofs:
            K_r = K[restrained_dofs] if is_sparse else K[restrained_dofs, :]
            reactions[restrained_dofs] = K_r @ displacements - F[restrained_dofs]

        # A DOF held only by the model's locks is not a support: its force is reported
        # separately (a support that also restrains it keeps it as a reaction).
        lock_forces = np.zeros(self.num_dofs)
        for dof in self._locked_dofs() - self._support_dofs():
            lock_forces[dof] = reactions[dof]
            reactions[dof] = 0.0

        # Elastic supports: the spring pushes back on the structure with -k*d. Their
        # DOFs are free (not restrained), so they are added here; without this the
        # reactions would not sum to the applied load on a spring-supported model.
        restrained_set = set(restrained_dofs)
        for support in self.model.supports:
            for dof, stiffness in support.spring_contributions(self._dpn):
                if dof not in restrained_set:
                    reactions[dof] = -stiffness * displacements[dof]

        return SolverResult(
            displacements=displacements,
            reactions=reactions,
            free_dofs=active_free,
            restrained_dofs=restrained_dofs,
            lock_forces=lock_forces,
        )
