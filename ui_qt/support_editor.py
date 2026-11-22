"""Support editor for the Properties panel: a preset plus per-axis restraints and springs.

The preset combo (Free, Fixed, Pinned, rollers, Spring, Custom) is a shortcut that ticks the
restraint boxes; ticking boxes yourself selects the matching preset, or Custom.  A plane
frame shows its in-plane freedoms (ux, uz, θy) and keeps sensible out-of-plane restraints for a
later change to a space frame (``plane_frame_restraints``); a space frame shows all six.  A spring
stiffness can be given
on any free DOF.  Edits are written only when the support was actually changed, so editing a
selection's loads never overwrites different supports.
"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGridLayout, QGroupBox, QLabel, QVBoxLayout,
)

from ui_qt.model_state import (
    DOF_NAMES, SPRING_FOR_DOF, SUPPORT_PRESETS, NodeData, SupportType, classify_support,
)

_PRESETS_3D = [
    (SupportType.FREE, "Free"), (SupportType.FIXED, "Fixed"), (SupportType.PIN, "Pinned"),
    (SupportType.ROLLER, "Roller, free in X"), (SupportType.ROLLER_Y, "Roller, free in Y"),
    (SupportType.ROLLER_Z, "Roller, free in Z (vertical)"),
    (SupportType.SPRING, "Spring"), (SupportType.CUSTOM, "Custom"),
]
_PRESETS_PLANE = [
    (SupportType.FREE, "Free"), (SupportType.FIXED, "Fixed"), (SupportType.PIN, "Pinned"),
    (SupportType.ROLLER, "Roller, free in X (horizontal)"),
    (SupportType.ROLLER_Z, "Roller, free in Z (vertical)"),
    (SupportType.SPRING, "Spring"), (SupportType.CUSTOM, "Custom"),
]
_AXIS = ("X", "Y", "Z", "X", "Y", "Z")

# Two layouts: a plane frame in XZ (Z up; uy, θx, θz locked) and a space frame.  Each shows
# only the DOFs that exist for it.
LAYOUT_DOFS = {"plane": (0, 2, 4), "space": tuple(range(6))}
_LABELS = {"plane": {0: "ux →", 2: "uz ↑", 4: "θy"}}
_LAYOUT_PRESETS = {"plane": _PRESETS_PLANE, "space": _PRESETS_3D}


def support_layout(state) -> str:
    """'plane' for a plane frame, else 'space'."""
    return "plane" if state is not None and state.analysis_type == "plane_xz" else "space"


def plane_frame_restraints(ux: bool, uz: bool, ry: bool) -> tuple[bool, ...]:
    """Six flags for a support ticked in a plane frame (ux, uz, θy), with the out-of-plane
    ones a later space frame would want: uy held when any translation is, θx/θz only when
    fully fixed.  Reproduces the presets (a roller free in Z stays one)."""
    fixed = ux and uz and ry
    return (bool(ux), bool(ux or uz), bool(uz), fixed, bool(ry), fixed)


def menu_presets(layout) -> list[tuple[str, SupportType]]:
    """Presets for the ribbon and right-click "Set Support" menus (same names as the panel).

    Spring and Custom need values or ticks, so they are set in the Properties panel.
    """
    rigid = [(text, p) for p, text in _LAYOUT_PRESETS[layout]
             if p not in (SupportType.FREE, SupportType.SPRING, SupportType.CUSTOM)]
    return rigid + [("None (free)", SupportType.FREE)]


def _spring_spin(value: float) -> QDoubleSpinBox:
    w = QDoubleSpinBox()
    w.setRange(0.0, 1e12)
    w.setSingleStep(1e5)
    w.setDecimals(0)
    w.setValue(value)
    return w


class SupportEditor(QGroupBox):
    """Edits the support of one node, or of a selection (shown from the first node)."""

    changed = pyqtSignal()

    def __init__(self, nodes: list[NodeData], layout, parent=None) -> None:
        super().__init__("Support", parent)
        self._layout = layout                          # "plane" or "space"
        self._dofs = LAYOUT_DOFS[self._layout]
        labels = _LABELS.get(self._layout)
        self._syncing = False
        self.touched = False
        first = nodes[0]
        lay = QVBoxLayout(self)

        self.combo = QComboBox()
        for preset, text in _LAYOUT_PRESETS[self._layout]:
            self.combo.addItem(text, preset)
        lay.addWidget(self.combo)

        lay.addWidget(QLabel("Restrained:"))
        grid = QGridLayout()
        self.boxes: dict[int, QCheckBox] = {}
        for k, dof in enumerate(self._dofs):
            box = QCheckBox(labels[dof] if labels else DOF_NAMES[dof])
            kind = "translation along" if dof < 3 else "rotation about"
            box.setToolTip(f"Restrain the {kind} global {_AXIS[dof]}")
            box.setChecked(first.restraints[dof])
            box.toggled.connect(self._on_box)
            row, col = (0, k) if labels else divmod(k, 3)
            grid.addWidget(box, row, col)
            self.boxes[dof] = box
        lay.addLayout(grid)

        self.spring_group = QGroupBox("Spring stiffness on free DOFs")
        form = QFormLayout(self.spring_group)
        self.springs: dict[int, QDoubleSpinBox] = {}
        for dof in self._dofs:
            spin = _spring_spin(getattr(first, SPRING_FOR_DOF[dof]))
            spin.valueChanged.connect(self._on_spring)
            unit = "N/m" if dof < 3 else "N·m/rad"
            name = labels[dof].split()[0] if labels else DOF_NAMES[dof]
            form.addRow(f"k {name} ({unit}):", spin)
            self.springs[dof] = spin
        lay.addWidget(self.spring_group)

        if any(n.restraints != first.restraints or n.support_type != first.support_type for n in nodes[1:]):
            note = QLabel(f"<small>The selected nodes differ: showing node {first.id}. "
                          "Change the support to apply it to all.</small>")
            note.setWordWrap(True)
            lay.addWidget(note)

        lay.addStretch(1)                                # keep the rows packed at the top
        self._show_preset(first.support_type)
        self.combo.currentIndexChanged.connect(self._on_preset)
        self._refresh_springs()

    # ── state ────────────────────────────────────────────────────────────────

    def preset(self) -> SupportType:
        return self.combo.currentData()

    def flags(self) -> tuple[bool, ...]:
        """The six restraint flags the ticks describe (a plane frame adds the out-of-plane
        ones a later change to a space frame would want)."""
        if self._layout == "plane":
            return plane_frame_restraints(*(self.boxes[d].isChecked() for d in (0, 2, 4)))
        return tuple(self.boxes[d].isChecked() for d in range(6))

    def spring_values(self) -> dict[int, float]:
        """Stiffness per shown DOF; zero where the DOF is restrained."""
        flags = self.flags()
        return {d: (0.0 if flags[d] else spin.value()) for d, spin in self.springs.items()}

    # ── syncing the combo, the ticks and the springs ─────────────────────────

    def _show_preset(self, preset: SupportType) -> None:
        index = self.combo.findData(preset)
        self._syncing = True
        self.combo.setCurrentIndex(index if index >= 0 else self.combo.findData(SupportType.CUSTOM))
        self._syncing = False

    def _on_preset(self) -> None:
        if self._syncing:
            return
        self.touched = True
        preset = self.preset()
        if preset is not SupportType.CUSTOM:
            self._syncing = True
            for dof, box in self.boxes.items():
                box.setChecked(SUPPORT_PRESETS[preset][dof])
            if preset is not SupportType.SPRING:
                for spin in self.springs.values():
                    spin.setValue(0.0)
            self._syncing = False
        self._refresh_springs()
        self.changed.emit()

    def _on_box(self) -> None:
        if self._syncing:
            return
        self.touched = True
        self._reclassify()

    def _on_spring(self) -> None:
        if self._syncing:
            return
        self.touched = True
        self._reclassify()

    def _reclassify(self) -> None:
        has_springs = any(v > 0 for v in self.spring_values().values())
        self._show_preset(classify_support(self.flags(), has_springs,
                                           spring_preset=self.preset() is SupportType.SPRING))
        self._refresh_springs()
        self.changed.emit()

    def _refresh_springs(self) -> None:
        preset = self.preset()
        flags = self.flags()
        show = preset in (SupportType.SPRING, SupportType.CUSTOM) or any(
            s.value() > 0 for s in self.springs.values())
        self.spring_group.setVisible(show)
        for dof, spin in self.springs.items():
            spin.setEnabled(not flags[dof])

    # ── writing back ─────────────────────────────────────────────────────────

    def apply_to(self, node: NodeData) -> None:
        """Write the edited support to ``node`` (nothing if the support was not changed)."""
        if not self.touched:
            return
        preset = self.preset()
        if preset not in (SupportType.SPRING, SupportType.CUSTOM):
            node.support_type = preset                   # flags from the preset, springs cleared
            return
        if preset is SupportType.SPRING:
            node.support_type = SupportType.SPRING
        else:
            node.set_restraints(self.flags())
            node._spring_preset = False
        for dof, value in self.spring_values().items():
            setattr(node, SPRING_FOR_DOF[dof], value)
