"""Postprocessor: recovers internal element forces and SFD/BMD from nodal displacements."""

from dataclasses import dataclass

import numpy as np

from core.load import ElementLoad, LoadDirection, LoadType
from elements.frame_element import FrameElement
from solver.fem_loads import fixed_end_forces


@dataclass
class ElementResult:
    """Internal end-forces for one element in local coordinates.

    Sign convention (N is the nodal axial force at node i):
      positive N = compression, negative N = tension
      positive V = upward on left face
      positive M = sagging (bottom fibre in tension)
    This compression-positive N convention is used consistently across the
    solver, the displays (AFD: red = compression, blue = tension) and the tests.

    2D (6 entries):  [N_i, V_i, M_i, N_j, V_j, M_j]
    3D (12 entries): [N_i, V_y_i, V_z_i, T_i, M_y_i, M_z_i,
                      N_j, V_y_j, V_z_j, T_j, M_y_j, M_z_j]
    """
    element_id: int
    end_forces: np.ndarray  # shape (6,) in 2D, (12,) in 3D

    @property
    def is_3d(self) -> bool:
        return len(self.end_forces) == 12

    # ── Primary accessors (2D/3D-aware) ─────────────────────────────────
    # In 3D, DOF layout is [N_i, Vy_i, Vz_i, T_i, My_i, Mz_i, N_j, Vy_j, Vz_j, T_j, My_j, Mz_j].
    # N_i, V_i (=Vy_i) are at the same index in both layouts.
    # M_i, M_j, V_j, N_j differ between 2D (6-entry) and 3D (12-entry).
    @property
    def N_i(self) -> float: return self.end_forces[0]
    @property
    def _weak_plane(self) -> bool:
        """3D only: True when bending is dominated by the x-z plane (M_y, V_z).

        Chosen once per element from BOTH ends, so M_i, M_j, V_i, V_j and the
        diagram slope always refer to the same plane. Ties go to the strong
        (x-y, M_z) plane.
        """
        f = self.end_forces
        return max(abs(f[4]), abs(f[10])) > max(abs(f[5]), abs(f[11]))

    @property
    def V_i(self) -> float:
        if self.is_3d:
            return self.end_forces[2] if self._weak_plane else self.end_forces[1]
        return self.end_forces[1]
    @property
    def M_i(self) -> float:
        if self.is_3d:
            return self.end_forces[4] if self._weak_plane else self.end_forces[5]
        return self.end_forces[2]
    @property
    def N_j(self) -> float:
        return self.end_forces[6] if self.is_3d else self.end_forces[3]
    @property
    def V_j(self) -> float:
        if self.is_3d:
            return self.end_forces[8] if self._weak_plane else self.end_forces[7]
        return self.end_forces[4]
    @property
    def M_j(self) -> float:
        if self.is_3d:
            return self.end_forces[10] if self._weak_plane else self.end_forces[11]
        return self.end_forces[5]

    @property
    def _bmd_V_i(self) -> float:
        """Effective shear for M(x) = M_i + _bmd_V_i * x.

        dM_z/dx = +V_y  (M_z plane)
        dM_y/dx = -V_z  (M_y plane, e.g. vertical members with global-Y load)
        """
        if self.is_3d:
            return -self.end_forces[2] if self._weak_plane else self.end_forces[1]
        return self.end_forces[1]

    # ── 3D-specific accessors (valid when is_3d is True) ─────────────────
    @property
    def V_y_i(self) -> float: return self.end_forces[1]
    @property
    def V_z_i(self) -> float: return self.end_forces[2]
    @property
    def T_i(self) -> float: return self.end_forces[3]
    @property
    def M_y_i(self) -> float: return self.end_forces[4]
    @property
    def M_z_i(self) -> float: return self.end_forces[5]
    @property
    def V_y_j(self) -> float: return self.end_forces[7]
    @property
    def V_z_j(self) -> float: return self.end_forces[8]
    @property
    def T_j(self) -> float: return self.end_forces[9]
    @property
    def M_y_j(self) -> float: return self.end_forces[10]
    @property
    def M_z_j(self) -> float: return self.end_forces[11]


@dataclass
class SFDBMDResult:
    """Shear and bending moment along one element at discrete sample points.

    Sign convention matches ElementResult: V positive = upward on left face,
    M positive = sagging (bending in the local x-y plane, about z-axis).
    """
    element_id: int
    x: np.ndarray   # local positions along element, 0 to L (m)
    V: np.ndarray   # shear force V_y at each x (N)
    M: np.ndarray   # bending moment M_z at each x (N·m)


def bending_profile(
    end_forces: np.ndarray,
    element_loads: list[ElementLoad],
    length: float,
    x: np.ndarray,
    plane: str = "z",
) -> tuple[np.ndarray, np.ndarray]:
    """Exact shear V(x) and moment M(x) along one element in one bending plane.

    ``end_forces`` is an ElementResult's vector (6 entries in 2D, 12 in 3D, moments at
    node i already in the sagging convention).  ``plane`` "z" is bending about local z
    (V_y, M_z, loads along LOCAL_Y: the only plane in 2D); "y" is bending about local y
    (V_z, M_y, loads along LOCAL_Z), whose moment slope is −V_z.  Every element load type
    is included: UDL, UVL, point force and point moment (a step in M at its position, so
    sample both sides of it to draw the step).  M(L) equals the solver's j-end moment.
    """
    f = end_forces
    x = np.asarray(x, dtype=float)
    if len(f) == 12 and plane == "y":
        m0, v0, slope_sign, direction = f[4], f[2], -1.0, LoadDirection.LOCAL_Z
    elif len(f) == 12:
        m0, v0, slope_sign, direction = f[5], f[1], 1.0, LoadDirection.LOCAL_Y
    else:
        m0, v0, slope_sign, direction = f[2], f[1], 1.0, LoadDirection.LOCAL_Y
    V = np.full_like(x, v0)
    M = m0 + slope_sign * v0 * x
    for load in element_loads:
        if load.direction != direction:
            continue
        if load.load_type == LoadType.UDL:
            w = load.magnitude                               # positive = downward
            V = V - w * x
            M = M - slope_sign * w * x ** 2 / 2
        elif load.load_type == LoadType.UVL:
            w1, w2 = load.magnitude, load.position           # w at i and at j
            V = V - w1 * x - (w2 - w1) * x ** 2 / (2 * length)
            M = M - slope_sign * (w1 * x ** 2 / 2 + (w2 - w1) * x ** 3 / (6 * length))
        elif load.load_type == LoadType.POINT_FORCE:
            beyond = x >= load.position
            V = np.where(beyond, V - load.magnitude, V)
            M = np.where(beyond, M - slope_sign * load.magnitude * (x - load.position), M)
        elif load.load_type == LoadType.POINT_MOMENT:
            M = np.where(x >= load.position, M + _POINT_MOMENT_STEP * load.magnitude, M)
    return V, M


# Sign of the step a point moment makes in M (fixed by the FEF convention in fem_loads;
# pinned by tests/test_bending_profile.py, which checks M(L) against the solver).
_POINT_MOMENT_STEP = -1.0


class Postprocessor:
    """Back-substitute displacements to recover internal element forces."""

    def __init__(
        self,
        elements: list[FrameElement],
        element_loads: list[ElementLoad],
        displacements: np.ndarray,
    ) -> None:
        self.elements = elements
        self.element_loads = element_loads
        self.displacements = displacements
        self._load_map: dict[int, list[ElementLoad]] = {}
        for eload in element_loads:
            self._load_map.setdefault(eload.element_id, []).append(eload)

    def compute(self) -> list[ElementResult]:
        """Return ElementResult for every element."""
        results = []
        for el in self.elements:
            results.append(self._recover_element(el))
        return results

    def sfd_bmd(self, n_points: int = 20) -> list[SFDBMDResult]:
        """Return shear and moment diagrams sampled at n_points per element."""
        el_results = self.compute()
        output = []
        for el, er in zip(self.elements, el_results):
            x = np.linspace(0.0, el.length, n_points)
            V, M = self._vm_along_element(el, er, x)
            output.append(SFDBMDResult(el.id, x, V, M))
        return output

    def _recover_element(self, el: FrameElement) -> ElementResult:
        dofs = el.dof_indices()
        d_global = self.displacements[dofs]
        T = el.transformation_matrix()
        d_local = T @ d_global

        k_local = el.local_stiffness_matrix()
        f_reduced = k_local @ d_local

        is_3d = el.is_3d

        # FEF superposition: add fixed-end forces back to recover true internal forces.
        # Pin-released elements need the FEF reduced to match their active DOFs.
        for eload in self._load_map.get(el.id, []):
            fef_full = fixed_end_forces(eload, el.length,
                                        pin_i=el.pin_i, pin_j=el.pin_j,
                                        is_3d=is_3d)
            if is_3d:
                if el.pin_i and el.pin_j:
                    # bar: drop θ_yi(4), θ_zi(5), θ_yj(10), θ_zj(11) → 8 entries
                    fef_reduced = fef_full[[0, 1, 2, 3, 6, 7, 8, 9]]
                elif el.pin_i:
                    # drop θ_yi(4), θ_zi(5) → 10 entries
                    fef_reduced = fef_full[[0, 1, 2, 3, 6, 7, 8, 9, 10, 11]]
                elif el.pin_j:
                    # drop θ_yj(10), θ_zj(11) → 10 entries
                    fef_reduced = fef_full[[0, 1, 2, 3, 4, 5, 6, 7, 8, 9]]
                else:
                    fef_reduced = fef_full
            else:
                if el.pin_i and el.pin_j:
                    fef_reduced = fef_full[[0, 1, 3, 4]]        # drop θ_i, θ_j
                elif el.pin_i:
                    fef_reduced = fef_full[[0, 1, 3, 4, 5]]     # drop θ_i
                elif el.pin_j:
                    fef_reduced = fef_full[[0, 1, 2, 3, 4]]     # drop θ_j
                else:
                    fef_reduced = fef_full                       # full 6 entries
            f_reduced += fef_reduced

        # Expand reduced force vector to standard full-size vector.
        f_local = el.expand_end_forces(f_reduced)

        if is_3d:
            # 3D: flip M_y_i (index 4) and M_z_i (index 5) sign conventions
            # (element → node moment sign convention)
            f_local[4] = -f_local[4]   # M_y_i
            f_local[5] = -f_local[5]   # M_z_i
        else:
            # 2D: M_i (index 2) — element applies CCW force to node;
            # internal moment = opposite → negate.
            f_local[2] = -f_local[2]
        return ElementResult(element_id=el.id, end_forces=f_local)

    def _vm_along_element(
        self, el: FrameElement, er: ElementResult, x: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        """V(x) and M(x) along the element, in the plane its results are reported in
        (``ElementResult._weak_plane`` in 3D), with every element load included."""
        plane = "y" if er.is_3d and er._weak_plane else "z"
        return bending_profile(er.end_forces, self._load_map.get(el.id, []), el.length, x, plane)


def sample_points(length: float, loads: list[ElementLoad], n: int = 12) -> np.ndarray:
    """Positions along an element for drawing its V / M: ``n`` even points plus both sides of
    every point load, so a kink or a step is drawn where the load is, not smoothed away."""
    xs = list(np.linspace(0.0, length, n))
    eps = 1e-9 * max(length, 1.0)
    for load in loads:
        if load.load_type in (LoadType.POINT_FORCE, LoadType.POINT_MOMENT) \
                and 0.0 < load.position < length:
            xs += [load.position - eps, load.position]
    return np.array(sorted(xs))
