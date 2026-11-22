"""Model: top-level container aggregating all structural components."""

from dataclasses import dataclass, field

from core.node import Node
from core.element import Element
from core.support import Support
from core.load import NodalLoad, ElementLoad


@dataclass
class Model:
    """Complete structural model ready for analysis.

    ``dimension`` (2 or 3) declares the analysis: 3 DOF/node in 2D, 6 in 3D, whatever the
    node coordinates (a 3D model may lie entirely at z = 0: a grillage, a floor).  Left as
    None, it is detected as before: 3 if all nodes have z == 0, 6 otherwise.  This controls
    the size of the global stiffness matrix and the DOF index mapping used by the solver.
    """

    nodes: list[Node] = field(default_factory=list)
    elements: list[Element] = field(default_factory=list)
    supports: list[Support] = field(default_factory=list)
    nodal_loads: list[NodalLoad] = field(default_factory=list)
    element_loads: list[ElementLoad] = field(default_factory=list)
    dimension: int | None = None

    @property
    def dofs_per_node(self) -> int:
        """3 in 2D, 6 in 3D: the declared dimension, else detected from the z values."""
        if self.dimension is not None:
            return 6 if self.dimension == 3 else 3
        if not self.nodes:
            return 3
        if any(n.z != 0.0 for n in self.nodes):
            return 6
        return 3

    @property
    def is_3d(self) -> bool:
        """True for a 3D (6 DOF/node) model."""
        return self.dofs_per_node == 6
