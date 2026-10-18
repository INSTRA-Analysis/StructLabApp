"""Rigid-body geometry for modelling tools (rotate; shared by any future transform tool).

Pure functions on coordinates, no Qt. Angles are in degrees, positive by the right-hand
rule about the chosen global axis (counter-clockwise when looking from the +axis end
towards the origin), so +90° about Z turns +X into +Y.

``rotated_beta`` keeps a member's cross-section orientation under the rotation: the
default local axes are recomputed from the member's direction (canvas_items.
_compute_local_axes, which matches the solver), so the roll angle ``beta`` has to be
re-derived for the section to turn with the structure rather than snap to the new default.
"""

from __future__ import annotations

import math

import numpy as np

AXES = ("X", "Y", "Z")


def rotation_matrix(axis: str, angle_deg: float) -> np.ndarray:
    """3×3 right-handed rotation about a global axis."""
    a = math.radians(angle_deg)
    c, s = math.cos(a), math.sin(a)
    if axis == "X":
        return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])
    if axis == "Y":
        return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
    if axis == "Z":
        return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
    raise ValueError(f"axis must be one of {AXES}, not {axis!r}")


def rotate_point(point, pivot, rotation: np.ndarray) -> tuple[float, float, float]:
    """``point`` rotated by ``rotation`` about ``pivot``; tiny round-off is snapped to zero."""
    p = np.asarray(point, dtype=float) - np.asarray(pivot, dtype=float)
    q = rotation @ p + np.asarray(pivot, dtype=float)
    q[np.abs(q) < 1e-9] = 0.0
    return float(q[0]), float(q[1]), float(q[2])


def rotated_beta(start, end, beta_rad: float, rotation: np.ndarray,
                 new_start, new_end) -> float:
    """Roll angle that keeps the section's local y-axis turned with the member.

    ``start``/``end`` are the member's end coordinates before the rotation and
    ``new_start``/``new_end`` after it.
    """
    from ui_qt.canvas_items import _compute_local_axes
    old = _compute_local_axes(*start, *end, beta_rad)
    new_default = _compute_local_axes(*new_start, *new_end, 0.0)
    if old is None or new_default is None:
        return beta_rad
    y_target = rotation @ old[1]
    _, y0, z0 = new_default
    beta = math.atan2(float(np.dot(y_target, z0)), float(np.dot(y_target, y0)))
    return 0.0 if abs(beta) < 1e-12 else beta
