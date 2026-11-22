"""Assembler: builds the global stiffness matrix and load vector from the model."""

import numpy as np
from scipy import sparse

from core.model import Model
from elements.frame_element import FrameElement
from solver.fem_loads import fixed_end_forces


class Assembler:
    """Scatter element stiffness contributions into the global system."""

    def __init__(self, model: Model) -> None:
        self.model = model
        self._dpn: int = model.dofs_per_node  # 3 (2D) or 6 (3D)
        self.num_dofs: int = (max(n.id for n in model.nodes) + 1) * self._dpn
        for element in model.elements:          # every element works in the model's dimension
            element.bind_dimension(self._dpn)

    def global_stiffness_sparse(self, elements: list[FrameElement]) -> sparse.csr_matrix:
        """Assemble the (num_dofs × num_dofs) global stiffness matrix in sparse (CSR) form.

        Element stiffness contributions are scattered as (row, col, value) triplets — summed
        where they coincide — plus any elastic spring stiffnesses on supports (diagonal).
        A frame's K has a few dozen non-zeros per row whatever its size, so this stays small
        where the dense matrix grows with the square of the DOF count.
        """
        rows: list[np.ndarray] = []
        cols: list[np.ndarray] = []
        vals: list[np.ndarray] = []
        for element in elements:
            k_global = element.global_stiffness_matrix(self._dpn)
            dofs = np.asarray(element.dof_indices(self._dpn))
            rows.append(np.repeat(dofs, len(dofs)))
            cols.append(np.tile(dofs, len(dofs)))
            vals.append(k_global.ravel())
        for support in self.model.supports:
            for dof, k_spring in support.spring_contributions(self._dpn):
                rows.append(np.array([dof]))
                cols.append(np.array([dof]))
                vals.append(np.array([k_spring]))
        if not vals:
            return sparse.csr_matrix((self.num_dofs, self.num_dofs))
        return sparse.coo_matrix(
            (np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
            shape=(self.num_dofs, self.num_dofs),
        ).tocsr()                                       # duplicates are summed

    def global_stiffness_matrix(self, elements: list[FrameElement]) -> np.ndarray:
        """The global stiffness matrix as a dense array (small models, tests, inspection);
        the application solves with ``global_stiffness_sparse``."""
        return self.global_stiffness_sparse(elements).toarray()

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
