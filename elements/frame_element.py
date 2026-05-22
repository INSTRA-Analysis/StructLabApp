"""FrameElement: 2D (3-DOF/node) and 3D (6-DOF/node) frame element.

Auto-detects dimensionality from node z-coordinates:
  - All z == 0  →  2D mode (3 DOF/node: dx, dy, θ_z)
  - Any z != 0  →  3D mode (6 DOF/node: dx, dy, dz, θ_x, θ_y, θ_z)

Pin releases (pin_i, pin_j) remove bending-moment continuity at that end via
static condensation.  In 3D this releases both θ_y and θ_z at the pinned end.
"""

import math
import numpy as np

from core.node import Node
from core.material import Material
from core.section import Section


class FrameElement:
    """Frame element connecting two nodes in 2D or 3D.

    Parameters
    ----------
    beta_angle : float
        Section rotation about the local x-axis in radians (3D only, ignored in 2D).
        Default 0 means the local y-axis lies in the global X-Y plane for non-vertical
        members (standard "strong-axis-vertical" orientation).
    """

    # ── Per-node DOF counts ────────────────────────────────────────────────
    DOF_2D = 3   # [dx, dy, θ_z]
    DOF_3D = 6   # [dx, dy, dz, θ_x, θ_y, θ_z]

    # Dot-product threshold for detecting near-vertical members in _compute_3d_basis.
    _VERTICAL_THRESHOLD: float = 0.9999

    def __init__(
        self,
        id: int,
        node_i: Node,
        node_j: Node,
        material: Material,
        section: Section,
        pin_i: bool = False,
        pin_j: bool = False,
        beta_angle: float = 0.0,
    ) -> None:
        self.id = id
        self.node_i = node_i
        self.node_j = node_j
        self.material = material
        self.section = section
        self.pin_i = pin_i
        self.pin_j = pin_j
        self.beta_angle = beta_angle

        dx = node_j.x - node_i.x
        dy = node_j.y - node_i.y
        dz = node_j.z - node_i.z
        self.length: float = math.sqrt(dx * dx + dy * dy + dz * dz)
        self._is_3d: bool = (node_i.z != 0.0 or node_j.z != 0.0 or dz != 0.0)

        if self.length == 0.0:
            raise ValueError(
                f"Element {id}: zero-length between nodes {node_i.id} and {node_j.id}"
            )

        if self._is_3d:
            self._dx, self._dy, self._dz = dx, dy, dz
            self.angle: float = math.atan2(dy, dx)  # XY-plane projection angle
            self._compute_3d_basis()
        else:
            self.angle: float = math.atan2(dy, dx)  # radians from +x axis

    # ── dimensionality query ────────────────────────────────────────────────

    @property
    def is_3d(self) -> bool:
        """True if either node has a non-zero z coordinate."""
        return self._is_3d

    @property
    def dofs_per_node(self) -> int:
        """3 for 2D, 6 for 3D."""
        return self.DOF_3D if self._is_3d else self.DOF_2D

    # ── local basis vectors (3D only) ───────────────────────────────────────

    def _compute_3d_basis(self) -> None:
        """Compute local orthonormal basis {x̂, ŷ, ẑ} in global coordinates.

        x̂  — along the element (node_i → node_j)
        ŷ  — perpendicular to x̂, oriented toward global +Z when possible
             (the "top" of the section faces up)
        ẑ  — cross(x̂, ŷ), completing the right-handed triad

        Coordinate convention: X,Y = ground plane, Z = up (elevation).

        The basis is then rotated by ``beta_angle`` about x̂.
        The resulting 3×3 rotation matrix R (columns = basis vectors) maps
        local → global:  v_global = R @ v_local.
        """
        L = self.length
        x_hat = np.array([self._dx / L, self._dy / L, self._dz / L])

        # Reference: global +Z is "up" (elevation).
        # We prefer local ŷ to have a positive Z component.
        ref = np.array([0.0, 0.0, 1.0])  # global +Z as "up"

        if abs(np.dot(x_hat, ref)) > self._VERTICAL_THRESHOLD:
            # Member is (near-)vertical — use global X to define the local y-z plane.
            z_hat = np.cross(x_hat, np.array([1.0, 0.0, 0.0]))
            z_hat /= np.linalg.norm(z_hat)
            y_hat = np.cross(z_hat, x_hat)
        else:
            z_hat = np.cross(x_hat, ref)
            z_hat /= np.linalg.norm(z_hat)
            y_hat = np.cross(z_hat, x_hat)

        # Apply beta rotation (section orientation about local x-axis).
        if self.beta_angle != 0.0:
            cb = math.cos(self.beta_angle)
            sb = math.sin(self.beta_angle)
            y_rot = cb * y_hat + sb * z_hat
            z_rot = -sb * y_hat + cb * z_hat
            y_hat, z_hat = y_rot, z_rot

        # 3×3 rotation: columns are the local axes in global coordinates.
        self._R3: np.ndarray = np.column_stack((x_hat, y_hat, z_hat))

    # ── public interface ────────────────────────────────────────────────────

    def local_stiffness_matrix(self, dofs_per_node: int | None = None) -> np.ndarray:
        """Local stiffness matrix sized to active DOFs."""
        dpn = dofs_per_node if dofs_per_node is not None else self.dofs_per_node
        if dpn >= 6 and self._is_3d:
            return self._local_stiffness_3d()
        else:
            return self._local_stiffness_2d()

    def transformation_matrix(self, dofs_per_node: int | None = None) -> np.ndarray:
        """Rotation matrix T sized to active DOFs (matches k_local size)."""
        dpn = dofs_per_node if dofs_per_node is not None else self.dofs_per_node
        if dpn >= 6 and self._is_3d:
            return self._transformation_3d()
        else:
            return self._transformation_2d()

    def full_transformation_matrix(self, dofs_per_node: int | None = None) -> np.ndarray:
        """Full-sized T regardless of pin flags.

        In 2D: 6×6.  In 3D: 12×12.
        For a 2D element embedded in a 3D model (dpn=6, _is_3d=False),
        returns the 6×6 2D transformation — the element only has 2D DOFs.
        """
        dpn = dofs_per_node if dofs_per_node is not None else self.dofs_per_node
        if dpn >= 6 and self._is_3d:
            return self._full_transformation_3d()
        else:
            return self._full_transformation_2d()

    def global_stiffness_matrix(self, dofs_per_node: int | None = None) -> np.ndarray:
        """Element stiffness matrix in global coordinates: Tᵀ @ k_local @ T.

        If *dofs_per_node* is provided and differs from the auto-detected value,
        the local stiffness is embedded/upgraded to the target size before
        transformation.
        """
        dpn = dofs_per_node if dofs_per_node is not None else self.dofs_per_node
        T = self.transformation_matrix(dpn)
        k_local = self.local_stiffness_matrix(dpn)
        return T.T @ k_local @ T

    def dof_indices(self, dofs_per_node: int | None = None) -> list[int]:
        """Global DOF indices for active DOFs (pinned rotations omitted).

        If *dofs_per_node* is provided it overrides the auto-detected value.
        """
        dpn = dofs_per_node if dofs_per_node is not None else self.dofs_per_node
        bi = self.node_i.id * dpn
        bj = self.node_j.id * dpn

        if dpn >= 6:
            if self._is_3d:
                # Always return all 12 DOFs (all 6 per node).
                # Pin releases are handled by non-square T in _transformation_3d:
                # k_global = T.T @ k_local @ T is 12×12 with zero entries for
                # condensed DOFs, so the assembler scatter works correctly and the
                # linear solver auto-excludes truly unconstrained zero-stiffness DOFs.
                return [bi, bi + 1, bi + 2, bi + 3, bi + 4, bi + 5,
                        bj, bj + 1, bj + 2, bj + 3, bj + 4, bj + 5]
            else:
                # 2D element embedded in 3D model.
                # 2D problem is in XZ plane: u→dx(0), v→dz(2), θ→θ_y(4)
                if self.pin_i and self.pin_j:
                    return [bi, bi + 2, bj, bj + 2]
                elif self.pin_i:
                    return [bi, bi + 2, bj, bj + 2, bj + 4]
                elif self.pin_j:
                    return [bi, bi + 2, bi + 4, bj, bj + 2]
                else:
                    return [bi, bi + 2, bi + 4, bj, bj + 2, bj + 4]
        else:
            # 2D mode (original behavior)
            if self.pin_i and self.pin_j:
                return [bi, bi + 1, bj, bj + 1]
            elif self.pin_i:
                return [bi, bi + 1, bj, bj + 1, bj + 2]
            elif self.pin_j:
                return [bi, bi + 1, bi + 2, bj, bj + 1]
            else:
                return [bi, bi + 1, bi + 2, bj, bj + 1, bj + 2]

    def expand_end_forces(self, f_reduced: np.ndarray) -> np.ndarray:
        """Map reduced local end-force vector to the standard full-size vector.

        2D: 6 entries [N_i, V_i, M_i, N_j, V_j, M_j]
        3D: 12 entries [N_i, V_y_i, V_z_i, T_i, M_y_i, M_z_i,
                        N_j, V_y_j, V_z_j, T_j, M_y_j, M_z_j]
        """
        if self._is_3d:
            return self._expand_3d(f_reduced)
        else:
            if not self.pin_i and not self.pin_j:
                return f_reduced
            f = np.zeros(6)
            if self.pin_i and self.pin_j:
                f[0] = f_reduced[0]
                f[3] = f_reduced[2]
            elif self.pin_i:
                f[0] = f_reduced[0]
                f[1] = f_reduced[1]
                f[3] = f_reduced[2]
                f[4] = f_reduced[3]
                f[5] = f_reduced[4]
            elif self.pin_j:
                f[0] = f_reduced[0]
                f[1] = f_reduced[1]
                f[2] = f_reduced[2]
                f[3] = f_reduced[3]
                f[4] = f_reduced[4]
            return f

    # ═══════════════════════════════════════════════════════════════════════
    #  2D  stiffness  &  transformation  (unchanged logic)
    # ═══════════════════════════════════════════════════════════════════════

    def _local_stiffness_2d(self) -> np.ndarray:
        if self.pin_i and self.pin_j:
            return self._bar_local_stiffness_2d()
        elif self.pin_i:
            return self._pin_left_local_stiffness_2d()
        elif self.pin_j:
            return self._pin_right_local_stiffness_2d()
        else:
            return self._full_local_stiffness_2d()

    def _transformation_2d(self) -> np.ndarray:
        cs = math.cos(self.angle)
        sn = math.sin(self.angle)
        r = np.array([[cs, sn], [-sn, cs]])

        if self.pin_i and self.pin_j:
            T = np.zeros((4, 4))
            T[0:2, 0:2] = r
            T[2:4, 2:4] = r
        elif self.pin_i:
            T = np.zeros((5, 5))
            T[0:2, 0:2] = r
            T[2:4, 2:4] = r
            T[4, 4] = 1.0
        elif self.pin_j:
            T = np.zeros((5, 5))
            T[0:2, 0:2] = r
            T[2, 2] = 1.0
            T[3:5, 3:5] = r
        else:
            T = np.zeros((6, 6))
            T[0:2, 0:2] = r
            T[2, 2] = 1.0
            T[3:5, 3:5] = r
            T[5, 5] = 1.0
        return T

    def _full_transformation_2d(self) -> np.ndarray:
        cs = math.cos(self.angle)
        sn = math.sin(self.angle)
        r = np.array([[cs, sn], [-sn, cs]])
        T = np.zeros((6, 6))
        T[0:2, 0:2] = r
        T[2, 2] = 1.0
        T[3:5, 3:5] = r
        T[5, 5] = 1.0
        return T

    def _full_transformation_2d_to_3d(self) -> np.ndarray:
        """Convert the 2D rotation into a 12×12 3D transformation.

        The 2D element lies in the XZ plane (X = horizontal, Z = vertical/up).
        Local axes:
          x̂ = (cos θ, 0, sin θ)    — along member in XZ plane
          ŷ = (0, 1, 0)            — out of plane (global Y, into the page)
          ẑ = (−sin θ, 0, cos θ)   — in-plane perpendicular
        """
        cs = math.cos(self.angle)
        sn = math.sin(self.angle)
        # 3×3 rotation about Y: columns = local axes in global coords
        R = np.array([
            [cs, 0.0, -sn],
            [0.0, 1.0, 0.0],
            [sn, 0.0,  cs],
        ])
        T = np.zeros((12, 12))
        for block in (0, 3, 6, 9):
            T[block:block + 3, block:block + 3] = R.T
        return T

    def _full_local_stiffness_2d(self) -> np.ndarray:
        E = self.material.elastic_modulus
        A = self.section.area
        I = self.section.I_z
        L = self.length

        a = E * A / L
        b = 12 * E * I / L**3
        c = 6 * E * I / L**2
        d = 4 * E * I / L
        e = 2 * E * I / L

        k = np.zeros((6, 6))
        k[0, 0] = a;   k[0, 3] = -a
        k[3, 0] = -a;  k[3, 3] = a
        k[1, 1] = b;   k[1, 2] = c;   k[1, 4] = -b;  k[1, 5] = c
        k[2, 1] = c;   k[2, 2] = d;   k[2, 4] = -c;  k[2, 5] = e
        k[4, 1] = -b;  k[4, 2] = -c;  k[4, 4] = b;   k[4, 5] = -c
        k[5, 1] = c;   k[5, 2] = e;   k[5, 4] = -c;  k[5, 5] = d
        return k

    def _pin_left_local_stiffness_2d(self) -> np.ndarray:
        E = self.material.elastic_modulus
        A = self.section.area
        I = self.section.I_z
        L = self.length

        a = E * A / L
        b = 3 * E * I / L**3
        c = 3 * E * I / L**2
        d = 3 * E * I / L

        k = np.zeros((5, 5))
        k[0, 0] = a;   k[0, 2] = -a
        k[2, 0] = -a;  k[2, 2] = a
        k[1, 1] = b;   k[1, 3] = -b;  k[1, 4] = c
        k[3, 1] = -b;  k[3, 3] = b;   k[3, 4] = -c
        k[4, 1] = c;   k[4, 3] = -c;  k[4, 4] = d
        return k

    def _pin_right_local_stiffness_2d(self) -> np.ndarray:
        E = self.material.elastic_modulus
        A = self.section.area
        I = self.section.I_z
        L = self.length

        a = E * A / L
        b = 3 * E * I / L**3
        c = 3 * E * I / L**2
        d = 3 * E * I / L

        k = np.zeros((5, 5))
        k[0, 0] = a;   k[0, 3] = -a
        k[3, 0] = -a;  k[3, 3] = a
        k[1, 1] = b;   k[1, 2] = c;   k[1, 4] = -b
        k[2, 1] = c;   k[2, 2] = d;   k[2, 4] = -c
        k[4, 1] = -b;  k[4, 2] = -c;  k[4, 4] = b
        return k

    def _bar_local_stiffness_2d(self) -> np.ndarray:
        a = self.material.elastic_modulus * self.section.area / self.length
        k = np.zeros((4, 4))
        k[0, 0] = a;   k[0, 2] = -a
        k[2, 0] = -a;  k[2, 2] = a
        return k

    # ── 2D → 3D embedding helpers ──────────────────────────────────────────

    @staticmethod
    def _embed_2d_stiffness_into_3d(k2d: np.ndarray) -> np.ndarray:
        """Embed a 2D local stiffness (4×4/5×5/6×6) into 3D positions.

        2D problem is in XZ plane: u→dx(0), v→dz(2), θ→θ_y(4).
        3D DOF order: [u_i, v_i, w_i, θ_xi, θ_yi, θ_zi,  u_j, v_j, w_j, θ_xj, θ_yj, θ_zj]

        2D index → 3D index:  0→0 (u_i), 1→2 (v_i→dz), 2→4 (θ_i→θ_y),
                               3→6 (u_j), 4→8 (v_j→dz), 5→10 (θ_j→θ_y)
        """
        n2 = k2d.shape[0]
        if n2 == 6:
            n3, idx_map = 12, {0: 0, 1: 2, 2: 4, 3: 6, 4: 8, 5: 10}
        elif n2 == 5:
            n3 = 10
            # pin_i [u_i,v_i,u_j,v_j,θ_j] → [0,2,6,8,10]
            # pin_j [u_i,v_i,θ_i,u_j,v_j] → [0,2,4,6,8]
            if k2d[2, 2] != 0.0 and abs(k2d[4, 4]) < 1e-30:
                idx_map = {0: 0, 1: 2, 2: 4, 3: 6, 4: 8}   # pin_j
            else:
                idx_map = {0: 0, 1: 2, 2: 6, 3: 8, 4: 10}  # pin_i
        else:
            n3, idx_map = 8, {0: 0, 1: 2, 2: 6, 3: 8}     # bar

        k3d = np.zeros((n3, n3))
        for i2 in range(n2):
            i3 = idx_map[i2]
            for j2 in range(n2):
                j3 = idx_map[j2]
                k3d[i3, j3] = k2d[i2, j2]
        return k3d

    def _reduce_12x12_T_for_pins(self, T12: np.ndarray) -> np.ndarray:
        """Remove pinned DOF rows/cols from a 12×12 transformation matrix.

        Pin flags use the 3D convention: pin_i → drop θ_yi(4), θ_zi(5);
        pin_j → drop θ_yj(10), θ_zj(11).
        """
        condense: list[int] = []
        if self.pin_i:
            condense.extend([4, 5])
        if self.pin_j:
            condense.extend([10, 11])
        if not condense:
            return T12
        keep = [i for i in range(12) if i not in condense]
        return T12[np.ix_(keep, keep)]

    # ═══════════════════════════════════════════════════════════════════════
    #  3D  stiffness  &  transformation
    # ═══════════════════════════════════════════════════════════════════════
    #
    #  Local DOF order (12 entries):
    #    [u_i, v_i, w_i, θ_xi, θ_yi, θ_zi, u_j, v_j, w_j, θ_xj, θ_yj, θ_zj]
    #
    #  u = axial (local x), v = transverse in local y, w = transverse in local z
    #  θ_x = torsion, θ_y = bending about y (w deflection), θ_z = bending about z (v deflection)

    def _local_stiffness_3d(self) -> np.ndarray:
        """Build 12×12, then statically condense pinned rotations."""
        k12 = self._full_local_stiffness_3d()

        if not self.pin_i and not self.pin_j:
            return k12

        # Identify indices to condense (0-based in the 12×12).
        condense: list[int] = []
        if self.pin_i:
            condense.extend([4, 5])   # θ_yi, θ_zi
        if self.pin_j:
            condense.extend([10, 11])  # θ_yj, θ_zj

        return self._static_condensation(k12, condense)

    def _full_local_stiffness_3d(self) -> np.ndarray:
        """12×12 Euler-Bernoulli 3D local stiffness matrix."""
        E = self.material.elastic_modulus
        G = self.material.shear_modulus
        A = self.section.area
        Iy = self.section.I_y      # weak axis  — bending in x-z plane
        Iz = self.section.I_z      # strong axis — bending in x-y plane
        J = self.section.J
        L = self.length

        # ── scalar coefficients ─────────────────────────────────────────
        a = E * A / L                     # axial
        g = G * J / L                     # torsion

        # Bending about z (xy-plane, v displacement, uses I_z)
        bz = 12.0 * E * Iz / (L ** 3)
        cz = 6.0 * E * Iz / (L ** 2)
        dz = 4.0 * E * Iz / L
        ez = 2.0 * E * Iz / L

        # Bending about y (xz-plane, w displacement, uses I_y)
        # Sign convention differs from z-bending (standard beam theory).
        by_ = 12.0 * E * Iy / (L ** 3)
        cy = 6.0 * E * Iy / (L ** 2)
        dy = 4.0 * E * Iy / L
        ey = 2.0 * E * Iy / L

        k = np.zeros((12, 12))

        # ── axial: u_i(0) ↔ u_j(6) ──────────────────────────────────────
        k[0, 0] = a;   k[0, 6] = -a
        k[6, 0] = -a;  k[6, 6] = a

        # ── torsion: θ_xi(3) ↔ θ_xj(9) ──────────────────────────────────
        k[3, 3] = g;   k[3, 9] = -g
        k[9, 3] = -g;  k[9, 9] = g

        # ── bending about z (v, θ_z): rows/cols 1, 5, 7, 11 ─────────────
        k[1, 1] = bz;   k[1, 5] = cz;   k[1, 7] = -bz;  k[1, 11] = cz
        k[5, 1] = cz;   k[5, 5] = dz;   k[5, 7] = -cz;  k[5, 11] = ez
        k[7, 1] = -bz;  k[7, 5] = -cz;  k[7, 7] = bz;   k[7, 11] = -cz
        k[11, 1] = cz;  k[11, 5] = ez;  k[11, 7] = -cz; k[11, 11] = dz

        # ── bending about y (w, θ_y): rows/cols 2, 4, 8, 10 ─────────────
        # Coupling terms (cy) are NEGATIVE because θ_y = +dw/dx (right-hand rule
        # about local y points in the −z direction), opposite to the v/θ_z convention
        # where θ_z = +dv/dx. This matches Cook et al. and McGuire et al. exactly.
        k[2, 2] = by_;   k[2, 4] = -cy;  k[2, 8] = -by_;  k[2, 10] = -cy
        k[4, 2] = -cy;   k[4, 4] = dy;   k[4, 8] = cy;    k[4, 10] = ey
        k[8, 2] = -by_;  k[8, 4] = cy;   k[8, 8] = by_;   k[8, 10] = cy
        k[10, 2] = -cy;  k[10, 4] = ey;  k[10, 8] = cy;   k[10, 10] = dy

        return k

    def _transformation_3d(self) -> np.ndarray:
        """Rotation matrix T sized to active DOFs (n_reduced × 12).

        For pin-released elements T is non-square: n_reduced rows (active local
        DOFs after condensation) × 12 columns (all global DOFs).  This preserves
        the correct global-DOF column mapping for every active local DOF.

        k_global = T.T @ k_local @ T  →  12×12 regardless of pin releases.
        The condensed pin-rotation DOFs naturally accumulate zero stiffness.
        """
        if not self.pin_i and not self.pin_j:
            return self._full_transformation_3d()

        T12 = self._full_transformation_3d()
        condense: list[int] = []
        if self.pin_i:
            condense.extend([4, 5])   # θ_yi, θ_zi
        if self.pin_j:
            condense.extend([10, 11])  # θ_yj, θ_zj

        keep = [i for i in range(12) if i not in condense]
        # Non-square: select only the active LOCAL rows, keep ALL 12 global cols.
        return T12[keep, :]

    def _full_transformation_3d(self) -> np.ndarray:
        """Full 12×12 transformation: T maps global → local, so T = diag(R3.T, ...)."""
        R = self._R3
        T = np.zeros((12, 12))
        for block in (0, 3, 6, 9):
            T[block:block + 3, block:block + 3] = R.T
        return T

    def _expand_3d(self, f_reduced: np.ndarray) -> np.ndarray:
        """Map reduced 3D local end-force vector to full 12-entry vector."""
        if not self.pin_i and not self.pin_j:
            return f_reduced

        f = np.zeros(12)
        if self.pin_i and self.pin_j:
            # Reduced [u_i, v_i, w_i, θ_xi,  u_j, v_j, w_j, θ_xj]  (8 entries)
            f[0] = f_reduced[0]    # N_i
            f[1] = f_reduced[1]    # V_y_i
            f[2] = f_reduced[2]    # V_z_i
            f[3] = f_reduced[3]    # T_i
            # f[4], f[5] = 0       # M_y_i, M_z_i = 0 (pinned)
            f[6] = f_reduced[4]    # N_j
            f[7] = f_reduced[5]    # V_y_j
            f[8] = f_reduced[6]    # V_z_j
            f[9] = f_reduced[7]    # T_j
            # f[10], f[11] = 0     # M_y_j, M_z_j = 0 (pinned)
        elif self.pin_i:
            # Reduced [u_i, v_i, w_i, θ_xi,  u_j, v_j, w_j, θ_xj, θ_yj, θ_zj]  (10)
            f[0] = f_reduced[0]
            f[1] = f_reduced[1]
            f[2] = f_reduced[2]
            f[3] = f_reduced[3]
            # f[4], f[5] = 0
            f[6] = f_reduced[4]
            f[7] = f_reduced[5]
            f[8] = f_reduced[6]
            f[9] = f_reduced[7]
            f[10] = f_reduced[8]
            f[11] = f_reduced[9]
        elif self.pin_j:
            # Reduced [u_i, v_i, w_i, θ_xi, θ_yi, θ_zi,  u_j, v_j, w_j, θ_xj]  (10)
            f[0] = f_reduced[0]
            f[1] = f_reduced[1]
            f[2] = f_reduced[2]
            f[3] = f_reduced[3]
            f[4] = f_reduced[4]
            f[5] = f_reduced[5]
            f[6] = f_reduced[6]
            f[7] = f_reduced[7]
            f[8] = f_reduced[8]
            f[9] = f_reduced[9]
            # f[10], f[11] = 0
        return f

    # ── static condensation helper ──────────────────────────────────────────

    @staticmethod
    def _static_condensation(K: np.ndarray, condense: list[int]) -> np.ndarray:
        """Statically condense specified DOFs out of the stiffness matrix.

        Partitions K into [K_aa  K_ab; K_ba  K_bb] where 'b' are the DOFs to
        condense.  The condensed matrix is K_aa − K_ab @ inv(K_bb) @ K_ba.
        """
        n = K.shape[0]
        keep = [i for i in range(n) if i not in condense]
        K_aa = K[np.ix_(keep, keep)]
        K_ab = K[np.ix_(keep, condense)]
        K_ba = K[np.ix_(condense, keep)]
        K_bb = K[np.ix_(condense, condense)]

        # Solve K_bb @ X = K_ba → X = inv(K_bb) @ K_ba
        try:
            X = np.linalg.solve(K_bb, K_ba)
        except np.linalg.LinAlgError:
            # K_bb may be singular if the pinned DOFs carry no stiffness
            # (e.g. pure bar).  Fall back to least-squares pseudo-inverse.
            X = np.linalg.lstsq(K_bb, K_ba, rcond=None)[0]

        return K_aa - K_ab @ X
