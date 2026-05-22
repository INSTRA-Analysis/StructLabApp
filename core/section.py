"""Section data model: cross-sectional geometric properties.

For 3D elements, I_z is the strong-axis moment of inertia (bending in the
local x-y plane), I_y is the weak-axis moment of inertia (bending in the
local x-z plane), and J is the torsional constant (Saint-Venant).

For backward compatibility, ``moment_of_inertia`` is kept as the primary
field and is also accessible via the ``I_z`` property.
"""

from dataclasses import dataclass


@dataclass
class Section:
    """Cross-sectional properties for a structural element.

    Parameters
    ----------
    name : str
        Descriptive label (e.g. "IPE 300").
    area : float
        Cross-sectional area in m².
    moment_of_inertia : float
        Strong-axis moment of inertia I_z in m⁴ (bending about Z, i.e. in the
        local x-y plane).  Kept as positional for backward compatibility.
    I_y : float or None
        Weak-axis moment of inertia in m⁴.  Defaults to ``moment_of_inertia``
        (square / isotropic section) when ``None``.
    J : float
        Torsional constant in m⁴ (Saint-Venant).  Default 0.0 (no torsional
        stiffness — safe for 2D models where torsion is irrelevant).
    """

    name: str
    area: float               # m²
    moment_of_inertia: float   # m⁴ — strong-axis I_z (kept for backward compat)
    I_y: float | None = None   # m⁴ — weak-axis; defaults to moment_of_inertia
    J: float = 0.0             # m⁴ — torsional constant

    def __post_init__(self) -> None:
        if self.I_y is None:
            self.I_y = self.moment_of_inertia

    @property
    def I_z(self) -> float:
        """Strong-axis moment of inertia (alias for moment_of_inertia)."""
        return self.moment_of_inertia
