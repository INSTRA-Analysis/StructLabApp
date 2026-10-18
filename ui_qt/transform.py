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
from dataclasses import dataclass

import numpy as np

AXES = ("X", "Y", "Z")


@dataclass
class RotateResult:
    """What a rotation actually did, so the UI can say so (truthy when something was selected)."""
    done: bool = True
    nodes_created: int = 0
    members_created: int = 0
    members_skipped: int = 0     # copies that landed exactly on an existing member
    nodes_reused: int = 0        # copied nodes that landed on an existing node
    coincident_nodes: int = 0    # in place: moved nodes now lying on other nodes
    duplicate_members: int = 0   # in place: moved members now lying on other members

    def __bool__(self) -> bool:
        return self.done

    def message(self, angle: float, axis: str, copies: int) -> str:
        if copies:
            text = (f"{copies} rotated cop{'y' if copies == 1 else 'ies'} at {angle:g}° about {axis}: "
                    f"{self.members_created} new member(s), {self.nodes_created} new node(s).")
            if self.members_skipped:
                text += (f" {self.members_skipped} member cop{'y' if self.members_skipped == 1 else 'ies'} "
                         "skipped — they landed exactly on existing members.")
            return text
        text = f"Rotated {angle:g}° about {axis}."
        if self.coincident_nodes or self.duplicate_members:
            text += (f" The rotated selection now lies on existing geometry: {self.coincident_nodes} "
                     f"coincident node(s), {self.duplicate_members} duplicate member(s) — use "
                     "Check Duplicates to merge them, or undo.")
        return text

    @property
    def needs_attention(self) -> bool:
        """Nothing new was created by a copy, or an in-place move landed on existing geometry."""
        return (self.members_skipped > 0 and self.members_created == 0 and self.nodes_created == 0) \
            or self.coincident_nodes > 0 or self.duplicate_members > 0


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
