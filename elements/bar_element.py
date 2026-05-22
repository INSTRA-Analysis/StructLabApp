"""BarElement: pure axial member using exact 4×4 stiffness (no bending DOFs)."""

from core.material import Material
from core.node import Node
from core.section import Section
from elements.frame_element import FrameElement


class BarElement(FrameElement):
    """Pure axial (bar/truss) member — both ends pin-released.

    Uses the exact 4×4 local stiffness derived by condensing θ_i and θ_j from
    the full 6×6 frame stiffness.  No bending capacity; only EA/L axial terms
    remain in K.  Moment of inertia is set to zero internally.

    Usage::

        bar = BarElement(id=0, node_i=n0, node_j=n1, material=mat, area=0.01)
    """

    def __init__(
        self,
        id: int,
        node_i: Node,
        node_j: Node,
        material: Material,
        area: float,
    ) -> None:
        section = Section(f"bar_{id}", area, 0.0)
        super().__init__(
            id, node_i, node_j, material, section, pin_i=True, pin_j=True
        )
