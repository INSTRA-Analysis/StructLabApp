"""TrussElement: axial-only frame element with moment DOFs effectively disabled."""

import numpy as np

from core.material import Material
from core.node import Node
from core.section import Section
from elements.frame_element import FrameElement


class TrussElement(FrameElement):
    """Frame element restricted to axial behaviour.

    The user supplies only cross-sectional area; moment of inertia is set to
    1e-20 m⁴ internally so that bending stiffness is negligible compared to
    axial stiffness for any engineering geometry (EI/EA·L² ≈ 1e-20/A·L² → 0).
    """

    def __init__(
        self,
        id: int,
        node_i: Node,
        node_j: Node,
        material: Material,
        area: float,
    ) -> None:
        section = Section("truss", area, 1e-20)
        super().__init__(id, node_i, node_j, material, section)
