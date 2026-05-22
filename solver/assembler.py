"""Assembler: builds the global stiffness matrix and load vector from the model."""

import numpy as np

from core.model import Model
from elements.frame_element import FrameElement
from solver.fem_loads import fixed_end_forces


class Assembler:
    """Scatter element stiffness contributions into the global system."""

    def __init__(self, model: Model) -> None:
        self.model = model
        self._dpn: int = model.dofs_per_node  # 3 (2D) or 6 (3D)
        self.num_dofs: int = (max(n.id for n in model.nodes) + 1) * self._dpn

    def global_stiffness_matrix(self, elements: list[FrameElement]) -> np.ndarray:
        """Assemble and return the (num_dofs × num_dofs) global stiffness matrix.

        Includes element stiffness contributions (scatter approach) plus any
        elastic spring stiffnesses defined on supports (added to K diagonal).
        """
        K = np.zeros((self.num_dofs, self.num_dofs))
        for element in elements:
            k_global = element.global_stiffness_matrix(self._dpn)
            dofs = element.dof_indices(self._dpn)
            for i, gi in enumerate(dofs):
                for j, gj in enumerate(dofs):
                    K[gi, gj] += k_global[i, j]
        for support in self.model.supports:
            for dof, k_spring in support.spring_contributions(self._dpn):
                K[dof, dof] += k_spring
        return K

    def global_force_vector(self, elements: list[FrameElement]) -> np.ndarray:
        """Assemble global force vector from nodal loads and element fixed-end forces."""
        F = np.zeros(self.num_dofs)
        dpn = self._dpn

        for load in self.model.nodal_loads:
            base = load.node_id * dpn
            F[base]     += load.fx
            F[base + 1] += load.fy
            if dpn >= 6:
                F[base + 2] += load.fz
                F[base + 3] += load.moment_x
                F[base + 4] += load.moment_y
                F[base + 5] += load.moment   # moment_z
            else:
                F[base + 2] += load.moment

        element_map = {el.id: el for el in elements}
        for eload in self.model.element_loads:
            el = element_map[eload.element_id]
            f_local = fixed_end_forces(eload, el.length,
                                        pin_i=getattr(el, 'pin_i', False),
                                        pin_j=getattr(el, 'pin_j', False),
                                        is_3d=el.is_3d)
            # Use the full transformation matrix so pin-released elements
            # (which have reduced T) don't cause a shape mismatch.
            T = el.full_transformation_matrix(dpn)
            f_global = T.T @ f_local

            # Scatter using the FULL DOF set (not pin-reduced).
            # Pin-released DOFs may receive zero FEF contribution, which is
            # correct, but the transformation must be applied across all DOFs
            # to properly resolve global force components.
            bi = el.node_i.id * dpn
            bj = el.node_j.id * dpn
            if dpn == 3:
                full_dofs = [bi, bi + 1, bi + 2, bj, bj + 1, bj + 2]
            else:
                full_dofs = [bi, bi + 1, bi + 2, bi + 3, bi + 4, bi + 5,
                             bj, bj + 1, bj + 2, bj + 3, bj + 4, bj + 5]
            for gi, fval in zip(full_dofs, f_global):
                F[gi] -= fval

        return F
