"""Benchmark result dataclasses.

BenchResult is the single data object each case produces.
The PDF generator and run_all.py consume these.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ReferenceType = Literal["analytical", "OpenSeesPy", "PyNite", "OpenSeesPy+PyNite"]
Category = Literal["2D Beams", "2D Frames", "2D Trusses", "3D Frames"]

TOL = 0.001  # 0.1 % default pass tolerance


@dataclass
class QuantityResult:
    """One compared quantity within a benchmark case."""
    label: str          # e.g. "Mid-span deflection"
    unit: str           # e.g. "mm"
    structlab: float
    reference: float
    reference_type: str = "analytical"

    @property
    def rel_error(self) -> float:
        if abs(self.reference) > 1e-12:
            return abs(self.structlab - self.reference) / abs(self.reference)
        return abs(self.structlab - self.reference)

    @property
    def passed(self) -> bool:
        return self.rel_error <= TOL


@dataclass
class BenchResult:
    """Full result for one benchmark case."""
    case_id: str                        # "B1", "F2", "3D4", etc.
    title: str                          # short title
    description: str                    # one or two sentences
    category: Category
    reference_types: list[str]          # e.g. ["analytical", "OpenSeesPy"]
    quantities: list[QuantityResult] = field(default_factory=list)
    sketch_func: object = None          # callable() → matplotlib Figure (set by case module)
    notes: str = ""                     # optional extra notes

    @property
    def passed(self) -> bool:
        return all(q.passed for q in self.quantities)

    @property
    def n_pass(self) -> int:
        return sum(q.passed for q in self.quantities)

    @property
    def n_total(self) -> int:
        return len(self.quantities)

    @property
    def max_error_pct(self) -> float:
        if not self.quantities:
            return 0.0
        return max(q.rel_error for q in self.quantities) * 100
