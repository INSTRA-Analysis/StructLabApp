"""Model: top-level container aggregating all structural components."""

from dataclasses import dataclass, field

from core.node import Node
from core.element import Element
from core.support import Support
from core.load import NodalLoad, ElementLoad


@dataclass
class Model:
    """Complete structural model ready for analysis.

    ``dofs_per_node`` is auto-detected: 3 if all nodes have z == 0 (2D model),
    6 otherwise (3D model).  This controls the size of the global stiffness
    matrix and the DOF index mapping used throughout the solver.
    """

    nodes: list[Node] = field(default_factory=list)
    elements: list[Element] = field(default_factory=list)
    supports: list[Support] = field(default_factory=list)
    nodal_loads: list[NodalLoad] = field(default_factory=list)
    element_loads: list[ElementLoad] = field(default_factory=list)

    @property
    def dofs_per_node(self) -> int:
        """Return 3 for pure 2D models, 6 if any node has a non-zero z coordinate."""
        if not self.nodes:
            return 3
        if any(n.z != 0.0 for n in self.nodes):
            return 6
        return 3

    @property
    def is_3d(self) -> bool:
        """True if this is a 3D model (any node has z != 0)."""
        return self.dofs_per_node == 6
