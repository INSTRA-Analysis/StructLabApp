"""Postprocessor: recovers internal element forces and SFD/BMD from nodal displacements."""

from dataclasses import dataclass

import numpy as np

from core.load import ElementLoad, LoadType
from elements.frame_element import FrameElement
from solver.fem_loads import fixed_end_forces


@dataclass
class ElementResult:
    """Internal end-forces for one element in local coordinates.

    Sign convention: positive N = tension, positive V = upward on left face,
    positive M = sagging (bottom fiber in tension).

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
    def V_i(self) -> float:
        if self.is_3d:
            Vy, Vz = self.end_forces[1], self.end_forces[2]
            return Vy if abs(Vy) >= abs(Vz) else Vz
        return self.end_forces[1]
    @property
    def M_i(self) -> float:
        if self.is_3d:
            My, Mz = self.end_forces[4], self.end_forces[5]
            return My if abs(My) >= abs(Mz) else Mz
        return self.end_forces[2]
    @property
    def N_j(self) -> float:
        return self.end_forces[6] if self.is_3d else self.end_forces[3]
    @property
    def V_j(self) -> float:
        if self.is_3d:
            Vy, Vz = self.end_forces[7], self.end_forces[8]
            return Vy if abs(Vy) >= abs(Vz) else Vz
        return self.end_forces[4]
    @property
    def M_j(self) -> float:
        if self.is_3d:
            My, Mz = self.end_forces[10], self.end_forces[11]
            return My if abs(My) >= abs(Mz) else Mz
        return self.end_forces[5]

    @property
    def _bmd_V_i(self) -> float:
        """Effective shear for M(x) = M_i + _bmd_V_i * x.

        dM_z/dx = +V_y  (M_z plane)
        dM_y/dx = -V_z  (M_y plane, e.g. vertical members with global-Y load)
        """
        if self.is_3d:
            My, Mz = self.end_forces[4], self.end_forces[5]
            return -self.end_forces[2] if abs(My) >= abs(Mz) else self.end_forces[1]
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
        """Compute V(x) and M(x) along element from end forces and element loads."""
        V = np.full_like(x, er.V_i)
        M = er.M_i + er._bmd_V_i * x

        for eload in self._load_map.get(el.id, []):
            if eload.load_type == LoadType.UDL:
                w = eload.magnitude  # positive = downward
                V -= w * x
                M -= w * x**2 / 2
            elif eload.load_type == LoadType.POINT_FORCE:
                P = eload.magnitude   # positive = downward
                a = eload.position    # m from node_i
                mask = x >= a
                V[mask] -= P
                M[mask] -= P * (x[mask] - a)

        return V, M
