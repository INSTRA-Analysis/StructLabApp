"""Material data model: linear-elastic isotropic material properties."""

from dataclasses import dataclass, field


@dataclass
class Material:
    """Linear-elastic isotropic material."""

    name: str
    elastic_modulus: float  # Pa (Young's modulus E)
    poisson_ratio: float = field(default=0.3)

    @property
    def shear_modulus(self) -> float:
        """Shear modulus G = E / (2·(1 + ν)) in Pa."""
        return self.elastic_modulus / (2.0 * (1.0 + self.poisson_ratio))
