"""Section picker dialog for StructLab.

Opens from the member Properties panel. User selects:
  - Material (sets E)
  - Section type: Steel profile, Rectangular, T-beam, Circular, Hollow RHS
  - Profile / dimensions → A and I auto-computed

On Accept, calls the callback with (E, A, I).
"""

from __future__ import annotations
import math

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QDoubleSpinBox, QComboBox, QPushButton,
    QGroupBox, QTabWidget, QWidget, QDialogButtonBox,
    QSizePolicy,
)
from PyQt6.QtCore import Qt

from ui_qt.section_library import (
    MATERIALS, STEEL_PROFILES,
    rectangular_section, t_beam_section,
    circular_section, hollow_rect_section,
)


def _dspin(val: float, lo: float, hi: float, step: float,
           decimals: int = 4) -> QDoubleSpinBox:
    w = QDoubleSpinBox()
    w.setRange(lo, hi)
    w.setSingleStep(step)
    w.setDecimals(decimals)
    w.setValue(val)
    return w


class SectionPickerDialog(QDialog):
    """Modal dialog to choose material + section; returns (E, A, I, W_pl, W_el) on accept."""

    def __init__(self, current_E: float, current_A: float, current_I: float,
                 parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Section Library")
        self.setMinimumWidth(420)
        self._result: tuple[float, float, float, float, float] | None = None

        layout = QVBoxLayout(self)

        # ── Material ──────────────────────────────────────────────────────────
        mat_box = QGroupBox("Material")
        mat_form = QFormLayout(mat_box)
        self._mat_combo = QComboBox()
        self._mat_combo.addItems(list(MATERIALS.keys()))
        self._mat_label = QLabel()
        self._mat_combo.currentTextChanged.connect(self._on_material_changed)
        mat_form.addRow("Material:", self._mat_combo)
        mat_form.addRow("",          self._mat_label)

        self._E_spin = _dspin(current_E / 1e9, 0.1, 1000, 1, 1)
        mat_form.addRow("E (GPa):", self._E_spin)
        layout.addWidget(mat_box)

        # ── Section tabs ──────────────────────────────────────────────────────
        sec_box = QGroupBox("Section")
        sec_layout = QVBoxLayout(sec_box)
        self._tabs = QTabWidget()

        self._tabs.addTab(self._build_steel_tab(),  "Steel profiles")
        self._tabs.addTab(self._build_rect_tab(),   "Rectangular")
        self._tabs.addTab(self._build_tbeam_tab(),  "T-beam")
        self._tabs.addTab(self._build_circ_tab(),   "Circular")
        self._tabs.addTab(self._build_hollow_tab(), "Hollow RHS")

        sec_layout.addWidget(self._tabs)
        layout.addWidget(sec_box)

        # ── Preview ───────────────────────────────────────────────────────────
        prev_box = QGroupBox("Computed section properties")
        prev_form = QFormLayout(prev_box)
        self._lbl_A   = QLabel("—")
        self._lbl_I   = QLabel("—")
        self._lbl_Wel = QLabel("—")
        prev_form.addRow("A (cm²):",       self._lbl_A)
        prev_form.addRow("I (cm⁴):",       self._lbl_I)
        prev_form.addRow("W_el (cm³):",    self._lbl_Wel)
        layout.addWidget(prev_box)

        # ── Buttons ───────────────────────────────────────────────────────────
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        # Wire live preview — call after all widgets exist
        self._tabs.currentChanged.connect(self._update_preview)
        self._mat_combo.setCurrentIndex(0)   # triggers _on_material_changed
        self._update_preview()               # populate preview on first open

    # ── Tab builders ──────────────────────────────────────────────────────────

    def _build_steel_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self._series_combo = QComboBox()
        self._series_combo.addItems(list(STEEL_PROFILES.keys()))
        self._profile_combo = QComboBox()
        self._series_combo.currentTextChanged.connect(self._on_series_changed)
        self._profile_combo.currentIndexChanged.connect(self._update_preview)
        form.addRow("Series:",  self._series_combo)
        form.addRow("Profile:", self._profile_combo)
        self._on_series_changed(self._series_combo.currentText())
        return w

    def _build_rect_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self._rect_b = _dspin(0.3, 0.001, 10, 0.05, 3)
        self._rect_h = _dspin(0.5, 0.001, 10, 0.05, 3)
        self._rect_b.valueChanged.connect(self._update_preview)
        self._rect_h.valueChanged.connect(self._update_preview)
        form.addRow("Width b (m):",  self._rect_b)
        form.addRow("Height h (m):", self._rect_h)
        return w

    def _build_tbeam_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self._tb_bf = _dspin(0.8, 0.001, 10, 0.05, 3)
        self._tb_hf = _dspin(0.12, 0.001, 5, 0.01, 3)
        self._tb_bw = _dspin(0.25, 0.001, 5, 0.05, 3)
        self._tb_hw = _dspin(0.5, 0.001, 10, 0.05, 3)
        for sp in (self._tb_bf, self._tb_hf, self._tb_bw, self._tb_hw):
            sp.valueChanged.connect(self._update_preview)
        form.addRow("Flange width bf (m):",  self._tb_bf)
        form.addRow("Flange depth hf (m):",  self._tb_hf)
        form.addRow("Web width bw (m):",     self._tb_bw)
        form.addRow("Web depth hw (m):",     self._tb_hw)
        return w

    def _build_circ_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self._circ_d = _dspin(0.4, 0.01, 10, 0.05, 3)
        self._circ_d.valueChanged.connect(self._update_preview)
        form.addRow("Diameter d (m):", self._circ_d)
        return w

    def _build_hollow_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self._rhs_b = _dspin(0.2, 0.01, 5, 0.05, 3)
        self._rhs_h = _dspin(0.3, 0.01, 5, 0.05, 3)
        self._rhs_t = _dspin(0.01, 0.001, 0.1, 0.005, 4)
        for sp in (self._rhs_b, self._rhs_h, self._rhs_t):
            sp.valueChanged.connect(self._update_preview)
        form.addRow("Width b (m):",     self._rhs_b)
        form.addRow("Height h (m):",    self._rhs_h)
        form.addRow("Wall thick t (m):", self._rhs_t)
        return w

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_material_changed(self, name: str) -> None:
        E, label = MATERIALS[name]
        self._mat_label.setText(label)
        if name != "Custom":
            self._E_spin.setValue(E / 1e9)
        self._E_spin.setEnabled(name == "Custom")

    def _on_series_changed(self, series: str) -> None:
        self._profile_combo.blockSignals(True)
        self._profile_combo.clear()
        for name, A, I, W_pl, W_el in STEEL_PROFILES[series]:
            self._profile_combo.addItem(name)
        self._profile_combo.blockSignals(False)
        self._update_preview()

    def _compute_section(self) -> tuple[float, float, float, float] | None:
        """Return (A, I, W_pl, W_el) in SI units, or None on error."""
        tab = self._tabs.currentIndex()
        try:
            if tab == 0:  # Steel
                series = self._series_combo.currentText()
                idx    = self._profile_combo.currentIndex()
                if idx < 0:
                    return None
                _, A, I, W_pl, W_el = STEEL_PROFILES[series][idx]
                return A, I, W_pl, W_el
            elif tab == 1:  # Rect
                b = self._rect_b.value()
                h = self._rect_h.value()
                A, I = rectangular_section(b, h)
                W_pl = b * h**2 / 4         # plastic modulus, solid rectangle
                W_el = b * h**2 / 6         # elastic modulus, solid rectangle
                return A, I, W_pl, W_el
            elif tab == 2:  # T-beam
                A, I = t_beam_section(
                    self._tb_bf.value(), self._tb_hf.value(),
                    self._tb_bw.value(), self._tb_hw.value(),
                )
                return A, I, 0.0, 0.0       # W_pl/W_el not computed for T-beam
            elif tab == 3:  # Circ
                d = self._circ_d.value()
                A, I = circular_section(d)
                W_pl = d**3 / 6                        # plastic modulus, solid circle
                W_el = math.pi * d**3 / 32             # elastic modulus, solid circle
                return A, I, W_pl, W_el
            elif tab == 4:  # Hollow RHS
                b = self._rhs_b.value()
                h = self._rhs_h.value()
                t = self._rhs_t.value()
                A, I = hollow_rect_section(b, h, t)
                h_max = max(b, h)
                b_max = min(b, h)
                W_pl = (b_max * h_max**2 - (b_max - 2*t) * (h_max - 2*t)**2) / 4
                W_el = 2 * I / h_max        # elastic modulus, hollow rectangle
                return A, I, W_pl, W_el
        except Exception:
            return None
        return None

    def _update_preview(self, *_) -> None:
        if not hasattr(self, "_lbl_A"):
            return   # called during __init__ before preview labels exist
        result = self._compute_section()
        if result is None:
            self._lbl_A.setText("—")
            self._lbl_I.setText("—")
            self._lbl_Wel.setText("—")
        else:
            A, I, W_pl, W_el = result
            self._lbl_A.setText(f"{A * 1e4:.2f} cm²")
            self._lbl_I.setText(f"{I * 1e8:.2f} cm⁴")
            self._lbl_Wel.setText(f"{W_el * 1e6:.1f} cm³" if W_el > 0 else "—")

    def _on_accept(self) -> None:
        result = self._compute_section()
        if result is None:
            return
        A, I, W_pl, W_el = result
        E = self._E_spin.value() * 1e9
        self._result = (E, A, I, W_pl, W_el)
        self.accept()

    # ── Public accessor ───────────────────────────────────────────────────────

    def get_result(self) -> tuple[float, float, float, float, float] | None:
        """Return (E, A, I, W_pl, W_el) in SI units, or None if cancelled."""
        return self._result
