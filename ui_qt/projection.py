"""Isometric and perspective projection utilities for 3D → 2D canvas.

Coordinate convention:  X, Y = ground plane (horizontal), Z = up (elevation).
All functions map 3D model coordinates (x, y, z) to 2D scene coordinates
(scene_x, scene_y) for rendering on a QGraphicsScene.

Projection model: orthographic with azimuth/elevation.
  - ISO_AZIMUTH:   orbit angle around the Z axis (degrees).
                   0° = looking from +X direction; positive = rotate CCW from above.
  - ISO_ELEVATION: tilt angle above the ground plane (degrees).
                   0° = horizontal view; 90° = top-down plan view.

Forward transform for a point (x, y, z):
  1. Rotate around Z by azimuth:
       x1 =  x*cos(az) + y*sin(az)
       y1 = -x*sin(az) + y*cos(az)   (y1 is the depth axis)
  2. Orthographic projection (Qt Y-axis is downward):
       screen_x =  x1 * ppm
       screen_y = (y1*sin(el) - z*cos(el)) * ppm

Inverse: given (screen_x, screen_y) and known z, recover (x, y):
  x1 = screen_x / ppm
  y1 = (screen_y/ppm + z*cos(el)) / sin(el)
  x  =  x1*cos(az) - y1*sin(az)
  y  =  x1*sin(az) + y1*cos(az)
"""

import math
import numpy as np


# ── Default projection parameters ────────────────────────────────────────────

# Pixels per metre (same as the 2D canvas)
PX_PER_M = 80.0

# Azimuth: orbit angle around Z axis (degrees).  -45° gives the classic view
# where X projects right-down and Y projects left-down.
ISO_AZIMUTH = -45.0

# Elevation: tilt above the ground plane (degrees).
ISO_ELEVATION = 30.0


def isometric(x: float, y: float, z: float,
              px_per_m: float = PX_PER_M,
              azimuth_deg: float | None = None,
              elevation_deg: float | None = None) -> tuple[float, float]:
    """Project a 3D point to 2D scene coordinates (orthographic az/el).

    Returns (scene_x, scene_y) in pixels.
    """
    if azimuth_deg is None:
        azimuth_deg = ISO_AZIMUTH
    if elevation_deg is None:
        elevation_deg = ISO_ELEVATION

    az = math.radians(azimuth_deg)
    el = math.radians(elevation_deg)

    x1 =  x * math.cos(az) + y * math.sin(az)
    y1 = -x * math.sin(az) + y * math.cos(az)

    sx = x1 * px_per_m
    sy = (y1 * math.sin(el) - z * math.cos(el)) * px_per_m

    return sx, sy


def isometric_array(points: np.ndarray,
                    px_per_m: float = PX_PER_M,
                    azimuth_deg: float | None = None,
                    elevation_deg: float | None = None) -> np.ndarray:
    """Project an (N, 3) array of [x, y, z] points to (N, 2) scene coords."""
    if azimuth_deg is None:
        azimuth_deg = ISO_AZIMUTH
    if elevation_deg is None:
        elevation_deg = ISO_ELEVATION

    az = math.radians(azimuth_deg)
    el = math.radians(elevation_deg)

    x1 =  points[:, 0] * math.cos(az) + points[:, 1] * math.sin(az)
    y1 = -points[:, 0] * math.sin(az) + points[:, 1] * math.cos(az)

    result = np.zeros((points.shape[0], 2))
    result[:, 0] = x1 * px_per_m
    result[:, 1] = (y1 * math.sin(el) - points[:, 2] * math.cos(el)) * px_per_m
    return result


def depth_order(members: list[tuple[float, float, float, float, float, float]]) -> list[int]:
    """Return indices sorted by depth (far → near) for painter's algorithm.

    Each member is (x_i, y_i, z_i, x_j, y_j, z_j).
    Uses the current ISO_AZIMUTH to compute the correct depth axis.
    Returns indices sorted far-to-near.
    """
    az = math.radians(ISO_AZIMUTH)
    # Depth axis = y1 direction in the rotated frame (points away from camera)
    # A point with larger y1 = -x*sin(az) + y*cos(az) is farther away.
    depths = []
    for m in members:
        mx = (m[0] + m[3]) / 2
        my = (m[1] + m[4]) / 2
        y1 = -mx * math.sin(az) + my * math.cos(az)
        depths.append(y1)

    return sorted(range(len(depths)), key=lambda i: depths[i])


def inverse_isometric(sx: float, sy: float, z: float,
                       px_per_m: float = PX_PER_M,
                       azimuth_deg: float | None = None,
                       elevation_deg: float | None = None) -> tuple[float, float]:
    """Inverse-project a 2D scene point back to 3D model coords at known Z.

    Given scene coords (sx, sy) and the working-plane elevation z,
    returns (x, y) in model metres.
    """
    if azimuth_deg is None:
        azimuth_deg = ISO_AZIMUTH
    if elevation_deg is None:
        elevation_deg = ISO_ELEVATION

    az = math.radians(azimuth_deg)
    el = math.radians(elevation_deg)

    sin_el = math.sin(el)
    if abs(sin_el) < 1e-15:
        return 0.0, 0.0

    x1 = sx / px_per_m
    y1 = (sy / px_per_m + z * math.cos(el)) / sin_el

    x =  x1 * math.cos(az) - y1 * math.sin(az)
    y =  x1 * math.sin(az) + y1 * math.cos(az)
    return x, y


def inverse_isometric_xz(sx: float, sy: float, y_fixed: float,
                          px_per_m: float = PX_PER_M,
                          azimuth_deg: float | None = None,
                          elevation_deg: float | None = None) -> tuple[float, float]:
    """Inverse-project a 2D scene point to the XZ plane at fixed Y = y_fixed.

    Returns (x, z) in model metres.
    Derivation:
        x1 = x*cos(az) + y_fixed*sin(az)  =>  x = (x1 - y_fixed*sin(az)) / cos(az)
        y1 = -x*sin(az) + y_fixed*cos(az)
        z  = (y1*sin(el) - sy/ppm) / cos(el)
    """
    if azimuth_deg is None:
        azimuth_deg = ISO_AZIMUTH
    if elevation_deg is None:
        elevation_deg = ISO_ELEVATION

    az = math.radians(azimuth_deg)
    el = math.radians(elevation_deg)
    cos_az = math.cos(az)
    cos_el = math.cos(el)

    if abs(cos_az) < 1e-15:  # plane is edge-on — degenerate view
        return 0.0, 0.0

    x1 = sx / px_per_m
    x  = (x1 - y_fixed * math.sin(az)) / cos_az
    y1 = -x * math.sin(az) + y_fixed * math.cos(az)

    if abs(cos_el) < 1e-15:
        return x, 0.0
    z = (y1 * math.sin(el) - sy / px_per_m) / cos_el
    return x, z


def inverse_isometric_yz(sx: float, sy: float, x_fixed: float,
                          px_per_m: float = PX_PER_M,
                          azimuth_deg: float | None = None,
                          elevation_deg: float | None = None) -> tuple[float, float]:
    """Inverse-project a 2D scene point to the YZ plane at fixed X = x_fixed.

    Returns (y, z) in model metres.
    Derivation:
        x1 = x_fixed*cos(az) + y*sin(az)  =>  y = (x1 - x_fixed*cos(az)) / sin(az)
        y1 = -x_fixed*sin(az) + y*cos(az)
        z  = (y1*sin(el) - sy/ppm) / cos(el)
    """
    if azimuth_deg is None:
        azimuth_deg = ISO_AZIMUTH
    if elevation_deg is None:
        elevation_deg = ISO_ELEVATION

    az = math.radians(azimuth_deg)
    el = math.radians(elevation_deg)
    sin_az = math.sin(az)
    cos_el = math.cos(el)

    if abs(sin_az) < 1e-15:  # plane is edge-on — degenerate view
        return 0.0, 0.0

    x1 = sx / px_per_m
    y  = (x1 - x_fixed * math.cos(az)) / sin_az
    y1 = -x_fixed * math.sin(az) + y * math.cos(az)

    if abs(cos_el) < 1e-15:
        return y, 0.0
    z = (y1 * math.sin(el) - sy / px_per_m) / cos_el
    return y, z


def is_3d_model(nodes: list) -> bool:
    """Return True if any node in the model has a non-zero z coordinate."""
    return any(getattr(n, 'z', 0.0) != 0.0 for n in nodes)
