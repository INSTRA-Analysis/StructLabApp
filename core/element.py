"""Element data model: connects two nodes with a material and section."""

from dataclasses import dataclass

from core.material import Material
from core.section import Section


@dataclass
class Element:
    """A structural element connecting two nodes."""

    id: int
    start_node_id: int
    end_node_id: int
    material: Material
    section: Section
