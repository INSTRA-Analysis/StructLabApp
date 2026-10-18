"""Section cut: hide everything on one side of an axis-aligned plane.

Useful for looking inside a structure (the base of a tower, one arm, one storey). The
pure helper ``members_beyond`` decides which members are cut away; ``SectionCutDialog``
is a small non-modal control with live preview. A member is cut only when BOTH of its
nodes lie beyond the plane, so members crossing the plane stay visible.
"""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel,
    QPushButton, QSlider, QVBoxLayout,
)

from ui_qt.model_state import ModelState

AXES = ("X", "Y", "Z")
_TOL = 1e-9


@dataclass(frozen=True)
class SectionCut:
    axis: str            # "X" | "Y" | "Z"
    position: float      # plane coordinate along that axis [m]
    keep_above: bool     # True keeps coordinate >= position, False keeps <= position


def _coordinate(node, axis: str) -> float:
    return {"X": node.x, "Y": node.y, "Z": node.z}[axis]


def members_beyond(state: ModelState, cut: SectionCut) -> set[int]:
    """Ids of the members lying entirely on the removed side of the plane."""
    hidden: set[int] = set()
    for m in state.members:
        ni, nj = state.get_node(m.node_i), state.get_node(m.node_j)
        if ni is None or nj is None:
            continue
        ci, cj = _coordinate(ni, cut.axis), _coordinate(nj, cut.axis)
        if cut.keep_above:
            beyond = ci < cut.position - _TOL and cj < cut.position - _TOL
        else:
            beyond = ci > cut.position + _TOL and cj > cut.position + _TOL
        if beyond:
            hidden.add(m.id)
    return hidden


def coordinate_range(state: ModelState, axis: str) -> tuple[float, float]:
    values = [_coordinate(n, axis) for n in state.nodes]
    return (min(values), max(values)) if values else (0.0, 1.0)


class SectionCutDialog(QDialog):
    """Non-modal panel: axis, plane position (slider + exact value), side to keep."""

    _STEPS = 400

    def __init__(self, scene, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Section Cut")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self._scene = scene
        self._busy = False

        self._axis = QComboBox()
        self._axis.addItems(AXES)
        self._axis.setCurrentText("Z" if any(n.z != 0 for n in scene.model_state.nodes) else "Y")
        self._keep = QComboBox()
        self._keep.addItems(["Keep above the plane", "Keep below the plane"])
        self._pos = QDoubleSpinBox()
        self._pos.setDecimals(3)
        self._pos.setSuffix(" m")
        self._pos.setSingleStep(0.25)
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, self._STEPS)
        self._info = QLabel("")
        self._info.setStyleSheet("color: #888888;")

        form = QFormLayout()
        form.addRow("Axis:", self._axis)
        form.addRow("Position:", self._pos)
        form.addRow("", self._slider)
        form.addRow("Side:", self._keep)

        clear = QPushButton("Clear cut")
        clear.clicked.connect(self.clear_cut)
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        row = QHBoxLayout()
        row.addWidget(clear)
        row.addStretch()
        row.addWidget(close)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(self._info)
        lay.addLayout(row)

        self._axis.currentTextChanged.connect(self._axis_changed)
        self._pos.valueChanged.connect(self._pos_changed)
        self._slider.valueChanged.connect(self._slider_changed)
        self._keep.currentIndexChanged.connect(lambda _i: self._apply())
        self._axis_changed()

    # ── helpers ───────────────────────────────────────────────────────────────

    def _range(self) -> tuple[float, float]:
        return coordinate_range(self._scene.model_state, self._axis.currentText())

    def _axis_changed(self, *_args) -> None:
        lo, hi = self._range()
        self._busy = True
        self._pos.setRange(lo - 1.0, hi + 1.0)
        self._pos.setValue((lo + hi) / 2)
        self._slider.setValue(self._STEPS // 2)
        self._busy = False
        self._apply()

    def _pos_changed(self, value: float) -> None:
        if self._busy:
            return
        lo, hi = self._range()
        self._busy = True
        self._slider.setValue(round((value - lo) / (hi - lo) * self._STEPS) if hi > lo else 0)
        self._busy = False
        self._apply()

    def _slider_changed(self, step: int) -> None:
        if self._busy:
            return
        lo, hi = self._range()
        self._busy = True
        self._pos.setValue(lo + (hi - lo) * step / self._STEPS)
        self._busy = False
        self._apply()

    def current_cut(self) -> SectionCut:
        return SectionCut(self._axis.currentText(), self._pos.value(),
                          self._keep.currentIndex() == 0)

    def _apply(self) -> None:
        cut = self.current_cut()
        self._scene.set_section_cut(cut)
        hidden = len(members_beyond(self._scene.model_state, cut))
        total = len(self._scene.model_state.members)
        self._info.setText(f"{hidden} of {total} members cut away")

    def clear_cut(self) -> None:
        self._scene.clear_section_cut()
        self._info.setText("No cut applied")

    def closeEvent(self, event) -> None:       # noqa: N802
        self._scene.clear_section_cut()        # the view returns to normal when the panel closes
        super().closeEvent(event)
