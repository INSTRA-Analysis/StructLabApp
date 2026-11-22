"""Fixed-end force vectors for element loads in local coordinates.

2D DOF order:  [u_i, v_i, θ_i, u_j, v_j, θ_j]
3D DOF order:  [u_i, v_i, w_i, θ_xi, θ_yi, θ_zi, u_j, v_j, w_j, θ_xj, θ_yj, θ_zj]

Convention: transverse magnitude positive = downward; fy positive upward in output.
Assembler applies F -= FEF, so FEF represents fixed-end support reactions.

Pin-release correction:
  When an element has pin_i=True or pin_j=True, the fixed-fixed FEFs must be
  corrected because the pinned end cannot carry moment.  The correction uses
  the classic moment-release method: release the pinned end, find the rotation
  that cancels its moment, and back-substitute the carry-over to the fixed end.
"""

import numpy as np

from core.load import ElementLoad, LoadDirection, LoadType


def _correct_for_pins(f: np.ndarray, L: float,
                      pin_i: bool, pin_j: bool,
                      is_3d: bool = False) -> np.ndarray:
    """Correct a fixed-fixed FEF vector for pin releases.

    Parameters
    ----------
    f : ndarray — fixed-fixed FEF (6 or 12 entries)
    L : float — element length
    pin_i : bool — is the i-end pinned?
    pin_j : bool — is the j-end pinned?
    is_3d : bool — True for 12-entry 3D vectors

    Returns
    -------
    f_corr : ndarray — corrected FEF (pin-released ends have zero moment)
    """
    if not pin_i and not pin_j:
        return f.copy()

    f_out = f.copy()

    if is_3d:
        # 3D: two independent bending planes to correct
        # xy-plane bending about z: V_y(1,7), M_z(5,11)
        # xz-plane bending about y: V_z(2,8), M_y(4,10) — opposite moment sign (θ_y = −dw/dx)
        _pin_correct_plane(f_out, L, pin_i, pin_j, v_i=1, m_i=5, v_j=7, m_j=11, sign=1.0)
        _pin_correct_plane(f_out, L, pin_i, pin_j, v_i=2, m_i=4, v_j=8, m_j=10, sign=-1.0)
    else:
        # 2D: single bending plane
        _pin_correct_plane(f_out, L, pin_i, pin_j, v_i=1, m_i=2, v_j=4, m_j=5, sign=1.0)

    return f_out


def _pin_correct_plane(f: np.ndarray, L: float,
                       pin_i: bool, pin_j: bool,
                       v_i: int, m_i: int, v_j: int, m_j: int, sign: float) -> None:
    """Correct FEF for one bending plane (in-place).

    Releasing an end moment M distributes −M to that end and, through the far end's
    carry-over factor ½, −M/2 to a fixed far end (none when both ends are released).  The
    end moments change by ΔM_i, ΔM_j, so the end shears change by ±(ΔM_i + ΔM_j)/L
    (``sign`` +1 in the x-y plane, −1 in the x-z plane), keeping the element in equilibrium.
    """
    M_i = f[m_i]
    M_j = f[m_j]

    if pin_i and pin_j:
        dM_i, dM_j = -M_i, -M_j
    elif pin_j:
        dM_i, dM_j = -0.5 * M_j, -M_j
    else:                                    # pin_i only
        dM_i, dM_j = -M_i, -0.5 * M_i
    dV = sign * (dM_i + dM_j) / L
    f[m_i] = M_i + dM_i
    f[m_j] = M_j + dM_j
    f[v_i] += dV
    f[v_j] -= dV


def _check_direction(load: ElementLoad, is_3d: bool) -> None:
    """Reject load directions this module cannot represent, instead of misreading them.

    Only local transverse directions have fixed-end formulas: LOCAL_Y (2D and 3D)
    and LOCAL_Z (3D). The GLOBAL_* members of LoadDirection are not implemented;
    resolve such a load into local components (or lump it to nodes) before it
    reaches the solver, as model_builder does for qx / qy / qz.
    """
    allowed = ((LoadDirection.LOCAL_X, LoadDirection.LOCAL_Y, LoadDirection.LOCAL_Z) if is_3d
               else (LoadDirection.LOCAL_X, LoadDirection.LOCAL_Y))
    if load.direction == LoadDirection.LOCAL_X and load.load_type not in (LoadType.UDL, LoadType.UVL):
        raise ValueError(f"Element load on element {load.element_id}: an axial (LOCAL_X) load "
                         "must be distributed (UDL or UVL).")
    if load.direction not in allowed:
        mode = "3D" if is_3d else "2D"
        raise ValueError(
            f"Element load on element {load.element_id} has direction "
            f"{load.direction.name}, which is not supported in {mode} analysis "
            f"(supported: {', '.join(d.name for d in allowed)})."
        )


def fixed_end_forces(load: ElementLoad, length: float,
                     pin_i: bool = False, pin_j: bool = False,
                     is_3d: bool = False) -> np.ndarray:
    """Return fixed-end force vector in local coordinates.

    Parameters
    ----------
    load : ElementLoad
    length : float — element length (m)
    pin_i : bool — is the i-end moment-released?
    pin_j : bool — is the j-end moment-released?
    is_3d : bool — return 12-entry (3D) vector instead of 6-entry (2D)

    2D DOF order: [u_i, v_i, θ_i, u_j, v_j, θ_j]
    3D DOF order: [u_i, v_i, w_i, θ_xi, θ_yi, θ_zi, u_j, v_j, w_j, θ_xj, θ_yj, θ_zj]

    Convention: transverse magnitude positive = downward; fy/fz positive upward in output.
    Assembler applies F -= FEF, so FEF represents fixed-end support reactions.
    """
    L = length
    _check_direction(load, is_3d)

    if is_3d:
        return _fef_3d(load, L, pin_i, pin_j)
    else:
        return _fef_2d(load, L, pin_i, pin_j)


def _fef_2d(load: ElementLoad, L: float, pin_i: bool, pin_j: bool) -> np.ndarray:
    """2D 6-entry FEF vector."""
    f = np.zeros(6)

    if load.direction == LoadDirection.LOCAL_X:          # distributed axial (see _fef_3d)
        w1 = load.magnitude
        w2 = load.position if load.load_type == LoadType.UVL else w1
        f[0] = L * (2 * w1 + w2) / 6
        f[3] = L * (w1 + 2 * w2) / 6
        return f

    if load.load_type == LoadType.UDL:
        w = load.magnitude  # N/m, positive downward
        f[1] =  w * L / 2
        f[2] =  w * L**2 / 12
        f[4] =  w * L / 2
        f[5] = -w * L**2 / 12

    elif load.load_type == LoadType.POINT_FORCE:
        P = load.magnitude
        a = load.position
        b = L - a
        f[1] =  P * b**2 * (3 * a + b) / L**3
        f[2] =  P * a * b**2 / L**2
        f[4] =  P * a**2 * (a + 3 * b) / L**3
        f[5] = -P * a**2 * b / L**2

    elif load.load_type == LoadType.POINT_MOMENT:
        M = load.magnitude
        a = load.position
        b = L - a
        f[1] =  6 * M * a * b / L**3
        f[2] =  M * b * (2 * a - b) / L**2
        f[4] = -6 * M * a * b / L**3
        f[5] =  M * a * (2 * b - a) / L**2

    elif load.load_type == LoadType.UVL:
        w1 = load.magnitude
        w2 = load.position
        # Same sign pattern as the UDL (w1 = w2 = w reproduces it exactly).
        f[1] =  L * (7 * w1 + 3 * w2) / 20
        f[2] =  L**2 * (3 * w1 + 2 * w2) / 60
        f[4] =  L * (3 * w1 + 7 * w2) / 20
        f[5] = -L**2 * (2 * w1 + 3 * w2) / 60

    if pin_i or pin_j:
        f = _correct_for_pins(f, L, pin_i, pin_j, is_3d=False)

    return f


def _fef_3d(load: ElementLoad, L: float, pin_i: bool, pin_j: bool) -> np.ndarray:
    """3D 12-entry FEF vector.

    Load direction defaults to LOCAL_Y (transverse in x-y plane, same as 2D).
    LOCAL_Z loads produce bending in the x-z plane (about y-axis).
    """
    f = np.zeros(12)

    if load.direction == LoadDirection.LOCAL_X:
        # Distributed axial load (positive along −x): fixed-end reactions push back along +x,
        # shared as for a bar fixed at both ends; no bending, pin releases do not affect it.
        w1 = load.magnitude
        w2 = load.position if load.load_type == LoadType.UVL else w1
        f[0] = L * (2 * w1 + w2) / 6
        f[6] = L * (w1 + 2 * w2) / 6
        return f

    if load.load_type == LoadType.UDL:
        w = load.magnitude  # N/m, positive downward in the load direction
        if load.direction.name in ("LOCAL_Y",):
            # Bending about z: V_y, M_z
            f[1] =  w * L / 2          # V_y_i
            f[5] =  w * L**2 / 12      # M_z_i
            f[7] =  w * L / 2          # V_y_j
            f[11] = -w * L**2 / 12     # M_z_j
        else:
            # LOCAL_Z (or others): Bending about y: V_z, M_y
            f[2] =  w * L / 2          # V_z_i
            f[4] = -w * L**2 / 12      # M_y_i  (sign flip vs z-bending)
            f[8] =  w * L / 2          # V_z_j
            f[10] = w * L**2 / 12      # M_y_j

    elif load.load_type == LoadType.POINT_FORCE:
        P = load.magnitude
        a = load.position
        b = L - a
        if load.direction.name in ("LOCAL_Y",):
            f[1] =  P * b**2 * (3 * a + b) / L**3
            f[5] =  P * a * b**2 / L**2
            f[7] =  P * a**2 * (a + 3 * b) / L**3
            f[11] = -P * a**2 * b / L**2
        else:
            f[2] =  P * b**2 * (3 * a + b) / L**3
            f[4] = -P * a * b**2 / L**2
            f[8] =  P * a**2 * (a + 3 * b) / L**3
            f[10] = P * a**2 * b / L**2

    elif load.load_type == LoadType.POINT_MOMENT:
        M = load.magnitude
        a = load.position
        b = L - a
        if load.direction.name in ("LOCAL_Y",):
            # Moment about z
            f[1] =  6 * M * a * b / L**3
            f[5] =  M * b * (2 * a - b) / L**2
            f[7] = -6 * M * a * b / L**3
            f[11] =  M * a * (2 * b - a) / L**2
        else:
            # Moment about y
            f[2] = -6 * M * a * b / L**3
            f[4] =  M * b * (2 * a - b) / L**2
            f[8] =  6 * M * a * b / L**3
            f[10] =  M * a * (2 * b - a) / L**2

    elif load.load_type == LoadType.UVL:
        w1 = load.magnitude
        w2 = load.position
        if load.direction.name in ("LOCAL_Y",):
            # Same sign pattern as the UDL in each plane (w1 = w2 reproduces it).
            f[1] =  L * (7 * w1 + 3 * w2) / 20
            f[5] =  L**2 * (3 * w1 + 2 * w2) / 60
            f[7] =  L * (3 * w1 + 7 * w2) / 20
            f[11] = -L**2 * (2 * w1 + 3 * w2) / 60
        else:
            f[2] =  L * (7 * w1 + 3 * w2) / 20
            f[4] = -L**2 * (3 * w1 + 2 * w2) / 60
            f[8] =  L * (3 * w1 + 7 * w2) / 20
            f[10] =  L**2 * (2 * w1 + 3 * w2) / 60

    if pin_i or pin_j:
        f = _correct_for_pins(f, L, pin_i, pin_j, is_3d=True)

    return f
