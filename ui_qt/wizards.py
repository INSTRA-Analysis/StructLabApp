"""Parameterised wizard dialogs for StructLab.

Each dialog collects geometry, section, and load parameters, then calls the
corresponding builder function in presets.py to produce a ready-to-use
ModelState.

Four wizards are provided:
  BeamWizardDialog   — multi-span beam (steel or RC), per-span length and
                       per-node support type
  PortalWizardDialog — single-bay portal frame (steel or RC, pinned/fixed base)
  TrussWizardDialog  — flat-chord truss (Pratt / Warren / Howe)
  FrameWizardDialog  — regular multi-story, multi-bay frame

Section/material selection everywhere goes through _SectionPickerRow, a thin
wrapper around section_picker.SectionPickerDialog (the same full material +
profile library the properties panel uses) — no wizard hand-rolls its own
section list.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QHBoxLayout, QGroupBox,
    QSpinBox, QDoubleSpinBox, QComboBox, QLabel, QPushButton,
    QRadioButton, QDialogButtonBox, QWidget,
    QTableWidget, QHeaderView,
)

from ui_qt.presets import (
    _E_C30, _E_C35, _FCK_C30, _FCK_C35, _RHO_RC,
    beam_wizard, portal_wizard, truss_wizard, frame_wizard,
)
from ui_qt.model_state import ModelState
from ui_qt.section_library import default_steel_section


class _SectionPickerRow(QWidget):
    """'Current section' label + 'Pick…' button opening the full
    SectionPickerDialog (material + profile library) — shared by every
    wizard dialog so none of them hand-roll a hardcoded, steel-only list.

    .result holds (E, A, I, W_pl, W_el, b, h, density, fy, mat_type) — the
    same tuple shape SectionPickerDialog.get_result() returns.
    """

    def __init__(self, default_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._label = QLabel()
        btn = QPushButton("Pick…")
        btn.setFixedWidth(70)
        btn.clicked.connect(self._pick)
        layout.addWidget(self._label, 1)
        layout.addWidget(btn)

        bundle = default_steel_section(default_name) or default_steel_section("IPE 300")
        E, A, I, W_pl, W_el, fy = bundle
        self.result: tuple = (E, A, I, W_pl, W_el, 0.0, 0.0, 7850.0, fy, "steel")
        self._name: str | None = default_name
        self._refresh_label()

    def _refresh_label(self) -> None:
        E, A, I, W_pl, W_el, b, h, density, fy, mat_type = self.result
        if self._name:
            self._label.setText(f"{self._name}  ·  {fy / 1e6:.0f} MPa")
        elif mat_type == "concrete":
            self._label.setText(f"{b * 1000:.0f}×{h * 1000:.0f} mm  ·  fck={fy / 1e6:.0f} MPa")
        else:
            self._label.setText(f"A={A * 1e4:.2f} cm²  ·  fy={fy / 1e6:.0f} MPa")

    def _pick(self) -> None:
        from ui_qt.section_picker import SectionPickerDialog
        E, A, I = self.result[0], self.result[1], self.result[2]
        dlg = SectionPickerDialog(current_E=E, current_A=A, current_I=I, parent=self)
        if dlg.exec() and dlg.get_result():
            self.result = dlg.get_result()
            self._name = None
            self._refresh_label()


# ─────────────────────────────────────────────────────────────────────────────

class BeamWizardDialog(QDialog):
    """Wizard for generating a single or multi-span beam model."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Beam Wizard")
        self.setMinimumWidth(400)
        self._state: ModelState | None = None
        self._init_ui()

    _SUPPORT_CHOICES = ["FIXED", "PIN", "ROLLER", "FREE"]

    def _init_ui(self) -> None:
        root = QVBoxLayout(self)

        # ── Geometry & supports ──────────────────────────────────────────────
        geo = QGroupBox("Geometry & Supports")
        gv  = QVBoxLayout(geo)

        n_row = QHBoxLayout()
        n_row.addWidget(QLabel("Number of spans:"))
        self._n_spans = QSpinBox()
        self._n_spans.setRange(1, 10)
        self._n_spans.setValue(1)
        self._n_spans.valueChanged.connect(self._rebuild_span_tables)
        n_row.addWidget(self._n_spans)
        n_row.addStretch()
        gv.addLayout(n_row)

        gv.addWidget(QLabel("Span lengths:"))
        self._spans_table = QTableWidget(0, 1)
        self._spans_table.setHorizontalHeaderLabels(["Length (m)"])
        self._spans_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._spans_table.setFixedHeight(90)
        gv.addWidget(self._spans_table)

        gv.addWidget(QLabel("Node supports  (a FREE end = cantilever tip):"))
        self._supports_table = QTableWidget(0, 1)
        self._supports_table.setHorizontalHeaderLabels(["Support"])
        self._supports_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._supports_table.setFixedHeight(110)
        gv.addWidget(self._supports_table)

        root.addWidget(geo)
        self._rebuild_span_tables(self._n_spans.value())

        # ── Section ───────────────────────────────────────────────────────────
        sec = QGroupBox("Section")
        sl  = QVBoxLayout(sec)

        mat_row = QHBoxLayout()
        self._rb_steel = QRadioButton("Steel (S355)")
        self._rb_rc    = QRadioButton("Reinforced Concrete")
        self._rb_steel.setChecked(True)
        mat_row.addWidget(self._rb_steel)
        mat_row.addWidget(self._rb_rc)
        sl.addLayout(mat_row)

        self._steel_w = QWidget()
        stf = QFormLayout(self._steel_w)
        stf.setContentsMargins(0, 0, 0, 0)
        self._steel_sec = _SectionPickerRow("IPE 400")
        stf.addRow("Profile:", self._steel_sec)
        sl.addWidget(self._steel_w)

        self._rc_w = QWidget()
        rcf = QFormLayout(self._rc_w)
        rcf.setContentsMargins(0, 0, 0, 0)
        self._rc_grade = QComboBox()
        self._rc_grade.addItems(["C30/37  (Ecm = 32 GPa)", "C35/45  (Ecm = 34 GPa)"])
        self._rc_b = QDoubleSpinBox()
        self._rc_b.setRange(100, 2000); self._rc_b.setValue(300); self._rc_b.setSuffix("  mm")
        self._rc_h = QDoubleSpinBox()
        self._rc_h.setRange(100, 3000); self._rc_h.setValue(500); self._rc_h.setSuffix("  mm")
        rcf.addRow("Concrete grade:", self._rc_grade)
        rcf.addRow("Width  b:", self._rc_b)
        rcf.addRow("Height h:", self._rc_h)
        self._rc_w.setVisible(False)
        sl.addWidget(self._rc_w)
        root.addWidget(sec)

        # ── Loads ─────────────────────────────────────────────────────────────
        ld = QGroupBox("Loads")
        lf = QFormLayout(ld)

        self._udl_g = QDoubleSpinBox()
        self._udl_g.setRange(0, 9999); self._udl_g.setValue(12.0); self._udl_g.setSuffix("  kN/m")
        self._udl_q = QDoubleSpinBox()
        self._udl_q.setRange(0, 9999); self._udl_q.setValue(8.0);  self._udl_q.setSuffix("  kN/m")
        self._pt_q  = QDoubleSpinBox()
        self._pt_q.setRange(0, 99999); self._pt_q.setValue(0.0);  self._pt_q.setSuffix("  kN")

        lf.addRow("Dead G  (UDL):", self._udl_g)
        lf.addRow("Imposed Q  (UDL):", self._udl_q)
        lf.addRow("Q  midspan point load:", self._pt_q)
        root.addWidget(ld)

        # ── Dialog buttons ─────────────────────────────────────────────────────
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

        self._rb_steel.toggled.connect(
            lambda steel: (
                self._steel_w.setVisible(steel),
                self._rc_w.setVisible(not steel),
            )
        )

    def _rebuild_span_tables(self, n_spans: int) -> None:
        """Resize the spans/supports tables to match n_spans, preserving any
        values already entered in the rows that still exist."""
        old_lengths = [self._spans_table.cellWidget(r, 0).value()
                       for r in range(self._spans_table.rowCount())] \
            if hasattr(self, "_spans_table") else []
        old_supports = [self._supports_table.cellWidget(r, 0).currentText()
                        for r in range(self._supports_table.rowCount())] \
            if hasattr(self, "_supports_table") else []

        self._spans_table.setRowCount(n_spans)
        self._spans_table.setVerticalHeaderLabels([f"Span {i + 1}" for i in range(n_spans)])
        for r in range(n_spans):
            sp = QDoubleSpinBox()
            sp.setRange(0.5, 200.0)
            sp.setSuffix("  m")
            sp.setValue(old_lengths[r] if r < len(old_lengths) else 6.0)
            self._spans_table.setCellWidget(r, 0, sp)

        n_nodes = n_spans + 1
        self._supports_table.setRowCount(n_nodes)
        self._supports_table.setVerticalHeaderLabels([f"Node {i + 1}" for i in range(n_nodes)])
        for r in range(n_nodes):
            cb = QComboBox()
            cb.addItems(self._SUPPORT_CHOICES)
            if r < len(old_supports) and old_supports[r] in self._SUPPORT_CHOICES:
                cb.setCurrentText(old_supports[r])
            else:
                cb.setCurrentText("PIN" if r == 0 else "ROLLER")
            self._supports_table.setCellWidget(r, 0, cb)

    def _section(self) -> tuple[float, float, float]:
        if self._rb_steel.isChecked():
            return self._steel_sec.result[0], self._steel_sec.result[1], self._steel_sec.result[2]
        E = _E_C30 if self._rc_grade.currentIndex() == 0 else _E_C35
        b = self._rc_b.value() / 1000.0
        h = self._rc_h.value() / 1000.0
        return E, b * h, b * h ** 3 / 12.0

    def _on_accept(self) -> None:
        spans     = [self._spans_table.cellWidget(r, 0).value()
                    for r in range(self._spans_table.rowCount())]
        sup_types = [self._supports_table.cellWidget(r, 0).currentText()
                    for r in range(self._supports_table.rowCount())]

        E, A, I  = self._section()
        density  = _RHO_RC if self._rb_rc.isChecked() else 0.0

        if self._rb_steel.isChecked():
            _, _, _, W_pl, W_el, _, _, _, fy, _ = self._steel_sec.result
            b_sec = h_sec = 0.0
        else:
            fy = _FCK_C30 if self._rc_grade.currentIndex() == 0 else _FCK_C35
            W_pl = W_el = 0.0
            b_sec = self._rc_b.value() / 1000.0
            h_sec = self._rc_h.value() / 1000.0

        self._state = beam_wizard(
            spans=spans,
            support_types=sup_types,
            E=E, A=A, I=I,
            udl_g=self._udl_g.value() * 1_000.0,
            udl_q=self._udl_q.value() * 1_000.0,
            point_q=self._pt_q.value()  * 1_000.0,
            density=density,
            fy=fy, W_pl=W_pl, W_el=W_el, b_sec=b_sec, h_sec=h_sec,
        )
        self.accept()

    def result(self) -> ModelState | None:
        return self._state


# ─────────────────────────────────────────────────────────────────────────────

class PortalWizardDialog(QDialog):
    """Wizard for generating a single-bay portal frame model."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Portal Frame Wizard")
        self.setMinimumWidth(400)
        self._state: ModelState | None = None
        self._init_ui()

    def _init_ui(self) -> None:
        root = QVBoxLayout(self)

        # ── Geometry ──────────────────────────────────────────────────────────
        geo = QGroupBox("Geometry")
        gf  = QFormLayout(geo)

        self._span = QDoubleSpinBox()
        self._span.setRange(1.0, 100.0); self._span.setValue(10.0); self._span.setSuffix("  m")
        self._height = QDoubleSpinBox()
        self._height.setRange(1.0, 50.0); self._height.setValue(5.0); self._height.setSuffix("  m")
        gf.addRow("Span:", self._span)
        gf.addRow("Column height:", self._height)
        root.addWidget(geo)

        # ── Base condition ─────────────────────────────────────────────────────
        base = QGroupBox("Column Bases")
        base_row = QHBoxLayout(base)
        self._rb_pin   = QRadioButton("Pinned  (statically determinate)")
        self._rb_fixed = QRadioButton("Fixed  (2-degree indeterminate)")
        self._rb_fixed.setChecked(True)
        base_row.addWidget(self._rb_pin)
        base_row.addWidget(self._rb_fixed)
        root.addWidget(base)

        # ── Sections ──────────────────────────────────────────────────────────
        sec = QGroupBox("Sections")
        sl  = QVBoxLayout(sec)

        mat_row = QHBoxLayout()
        self._rb_steel = QRadioButton("Steel (S355)")
        self._rb_rc    = QRadioButton("Reinforced Concrete")
        self._rb_steel.setChecked(True)
        mat_row.addWidget(self._rb_steel)
        mat_row.addWidget(self._rb_rc)
        sl.addLayout(mat_row)

        self._steel_w = QWidget()
        stf = QFormLayout(self._steel_w)
        stf.setContentsMargins(0, 0, 0, 0)
        self._col_sec = _SectionPickerRow("HEB 260")
        self._raf_sec = _SectionPickerRow("IPE 450")
        stf.addRow("Column profile:", self._col_sec)
        stf.addRow("Rafter profile:", self._raf_sec)
        sl.addWidget(self._steel_w)

        self._rc_w = QWidget()
        rcf = QFormLayout(self._rc_w)
        rcf.setContentsMargins(0, 0, 0, 0)
        self._rc_grade = QComboBox()
        self._rc_grade.addItems(["C30/37  (Ecm = 32 GPa)", "C35/45  (Ecm = 34 GPa)"])
        self._rc_col_b = QDoubleSpinBox()
        self._rc_col_b.setRange(100, 2000); self._rc_col_b.setValue(400); self._rc_col_b.setSuffix("  mm")
        self._rc_col_h = QDoubleSpinBox()
        self._rc_col_h.setRange(100, 2000); self._rc_col_h.setValue(400); self._rc_col_h.setSuffix("  mm")
        self._rc_raf_b = QDoubleSpinBox()
        self._rc_raf_b.setRange(100, 2000); self._rc_raf_b.setValue(300); self._rc_raf_b.setSuffix("  mm")
        self._rc_raf_h = QDoubleSpinBox()
        self._rc_raf_h.setRange(100, 3000); self._rc_raf_h.setValue(600); self._rc_raf_h.setSuffix("  mm")
        rcf.addRow("Concrete grade:", self._rc_grade)
        rcf.addRow("Column b × h:", self._rc_col_b)
        rcf.addRow("", self._rc_col_h)
        rcf.addRow("Rafter b × h:", self._rc_raf_b)
        rcf.addRow("", self._rc_raf_h)
        self._rc_w.setVisible(False)
        sl.addWidget(self._rc_w)
        root.addWidget(sec)

        self._rb_steel.toggled.connect(
            lambda steel: (
                self._steel_w.setVisible(steel),
                self._rc_w.setVisible(not steel),
            )
        )

        # ── Loads ─────────────────────────────────────────────────────────────
        ld = QGroupBox("Loads on Rafter")
        lf = QFormLayout(ld)

        self._udl_g = QDoubleSpinBox()
        self._udl_g.setRange(0, 9999); self._udl_g.setValue(12.0); self._udl_g.setSuffix("  kN/m")
        self._udl_q = QDoubleSpinBox()
        self._udl_q.setRange(0, 9999); self._udl_q.setValue(8.0);  self._udl_q.setSuffix("  kN/m")
        self._wind  = QDoubleSpinBox()
        self._wind.setRange(-9999, 9999); self._wind.setValue(50.0); self._wind.setSuffix("  kN")
        lf.addRow("Dead G  (UDL):", self._udl_g)
        lf.addRow("Imposed Q  (UDL):", self._udl_q)
        lf.addRow("Wind W  (lateral at eave, +→):", self._wind)
        root.addWidget(ld)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def _on_accept(self) -> None:
        if self._rb_steel.isChecked():
            E_col, A_col, I_col, col_W_pl, col_W_el, *_ , col_fy, _ = self._col_sec.result
            E_raf, A_raf, I_raf, raf_W_pl, raf_W_el, *_ , raf_fy, _ = self._raf_sec.result
            col_b_sec = col_h_sec = raf_b_sec = raf_h_sec = 0.0
            density = 0.0
        else:
            E = _E_C30 if self._rc_grade.currentIndex() == 0 else _E_C35
            fck = _FCK_C30 if self._rc_grade.currentIndex() == 0 else _FCK_C35
            col_b_sec, col_h_sec = self._rc_col_b.value() / 1000.0, self._rc_col_h.value() / 1000.0
            raf_b_sec, raf_h_sec = self._rc_raf_b.value() / 1000.0, self._rc_raf_h.value() / 1000.0
            A_col, I_col = col_b_sec * col_h_sec, col_b_sec * col_h_sec ** 3 / 12.0
            A_raf, I_raf = raf_b_sec * raf_h_sec, raf_b_sec * raf_h_sec ** 3 / 12.0
            E_col = E_raf = E
            col_fy = raf_fy = fck
            col_W_pl = col_W_el = raf_W_pl = raf_W_el = 0.0
            density = _RHO_RC

        self._state = portal_wizard(
            span=self._span.value(),
            height=self._height.value(),
            fixed_base=self._rb_fixed.isChecked(),
            E_col=E_col, A_col=A_col, I_col=I_col,
            E_raf=E_raf, A_raf=A_raf, I_raf=I_raf,
            udl_g=self._udl_g.value() * 1_000.0,
            udl_q=self._udl_q.value() * 1_000.0,
            wind_h=self._wind.value()  * 1_000.0,
            col_fy=col_fy, col_W_pl=col_W_pl, col_W_el=col_W_el,
            raf_fy=raf_fy, raf_W_pl=raf_W_pl, raf_W_el=raf_W_el,
            col_b_sec=col_b_sec, col_h_sec=col_h_sec,
            raf_b_sec=raf_b_sec, raf_h_sec=raf_h_sec,
            density=density,
        )
        self.accept()

    def result(self) -> ModelState | None:
        return self._state


# ─────────────────────────────────────────────────────────────────────────────

class TrussWizardDialog(QDialog):
    """Wizard for generating a flat-chord truss model (Pratt / Warren / Howe)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Truss Wizard")
        self.setMinimumWidth(400)
        self._state: ModelState | None = None
        self._init_ui()

    def _init_ui(self) -> None:
        root = QVBoxLayout(self)

        # ── Truss type ────────────────────────────────────────────────────────
        typ = QGroupBox("Truss Type")
        type_row = QHBoxLayout(typ)
        self._rb_pratt  = QRadioButton("Pratt\n(diagonals in tension)")
        self._rb_warren = QRadioButton("Warren\n(alternating diagonals)")
        self._rb_howe   = QRadioButton("Howe\n(diagonals in compression)")
        self._rb_pratt.setChecked(True)
        type_row.addWidget(self._rb_pratt)
        type_row.addWidget(self._rb_warren)
        type_row.addWidget(self._rb_howe)
        root.addWidget(typ)

        # ── Geometry ──────────────────────────────────────────────────────────
        geo = QGroupBox("Geometry")
        gf  = QFormLayout(geo)

        self._n_panels = QSpinBox()
        self._n_panels.setRange(2, 20); self._n_panels.setValue(8)
        self._n_panels.setToolTip("Number of panels (use even values for Pratt / Howe)")
        gf.addRow("Panels:", self._n_panels)

        self._span = QDoubleSpinBox()
        self._span.setRange(1.0, 200.0); self._span.setValue(16.0); self._span.setSuffix("  m")
        gf.addRow("Total span:", self._span)

        self._depth = QDoubleSpinBox()
        self._depth.setRange(0.5, 20.0); self._depth.setValue(2.0); self._depth.setSuffix("  m")
        gf.addRow("Truss depth:", self._depth)
        root.addWidget(geo)

        # ── Sections ──────────────────────────────────────────────────────────
        sec = QGroupBox("Sections  (Steel — all BAR elements)")
        sf  = QFormLayout(sec)

        self._chord_sec = _SectionPickerRow("RHS 200×100×8")
        self._web_sec   = _SectionPickerRow("RHS 150×100×6")
        sf.addRow("Chord section:", self._chord_sec)
        sf.addRow("Web section  (diagonals + verticals):", self._web_sec)
        root.addWidget(sec)

        # ── Loads ─────────────────────────────────────────────────────────────
        ld = QGroupBox("Panel Loads")
        lf = QFormLayout(ld)

        self._panel_load = QDoubleSpinBox()
        self._panel_load.setRange(0, 999999); self._panel_load.setValue(30.0)
        self._panel_load.setSuffix("  kN  per panel point")
        lf.addRow("Panel point load (Q):", self._panel_load)

        self._rb_top    = QRadioButton("On top chord  (roof / purlin loads)")
        self._rb_bottom = QRadioButton("On bottom chord  (bridge / floor loads)")
        self._rb_top.setChecked(True)
        lf.addRow(self._rb_top)
        lf.addRow(self._rb_bottom)
        root.addWidget(ld)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def _on_accept(self) -> None:
        if self._rb_pratt.isChecked():
            t = "Pratt"
        elif self._rb_warren.isChecked():
            t = "Warren"
        else:
            t = "Howe"

        chord_E, chord_A, chord_I, *_, chord_fy, _ = self._chord_sec.result
        web_E, web_A, web_I, *_, web_fy, _ = self._web_sec.result

        self._state = truss_wizard(
            truss_type=t,
            n_panels=self._n_panels.value(),
            span=self._span.value(),
            depth=self._depth.value(),
            chord_section=(chord_E, chord_A, chord_I),
            web_section=(web_E, web_A, web_I),
            panel_load=self._panel_load.value() * 1_000.0,
            load_on_top=self._rb_top.isChecked(),
            chord_fy=chord_fy, web_fy=web_fy,
        )
        self.accept()

    def result(self) -> ModelState | None:
        return self._state


# ─────────────────────────────────────────────────────────────────────────────

class FrameWizardDialog(QDialog):
    """Wizard for generating a regular multi-story, multi-bay frame."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Frame Wizard")
        self.setMinimumWidth(400)
        self._state: ModelState | None = None
        self._init_ui()

    def _init_ui(self) -> None:
        root = QVBoxLayout(self)

        # ── Geometry ──────────────────────────────────────────────────────────
        geo = QGroupBox("Geometry")
        gf  = QFormLayout(geo)

        self._bays = QSpinBox(); self._bays.setRange(1, 20); self._bays.setValue(2)
        self._stories = QSpinBox(); self._stories.setRange(1, 30); self._stories.setValue(3)
        self._width = QDoubleSpinBox()
        self._width.setRange(1, 50); self._width.setValue(6.0); self._width.setSuffix("  m")
        self._height = QDoubleSpinBox()
        self._height.setRange(1, 20); self._height.setValue(3.0); self._height.setSuffix("  m")
        gf.addRow("Number of bays:",    self._bays)
        gf.addRow("Number of stories:", self._stories)
        gf.addRow("Bay width:",         self._width)
        gf.addRow("Story height:",      self._height)
        root.addWidget(geo)

        # ── Base condition ───────────────────────────────────────────────────
        base = QGroupBox("Column Bases")
        base_row = QHBoxLayout(base)
        self._rb_pin   = QRadioButton("Pinned  (statically determinate)")
        self._rb_fixed = QRadioButton("Fixed  (indeterminate)")
        self._rb_pin.setChecked(True)
        base_row.addWidget(self._rb_pin)
        base_row.addWidget(self._rb_fixed)
        root.addWidget(base)

        # ── Section ───────────────────────────────────────────────────────────
        sec = QGroupBox("Section  (steel or concrete — applied to every member, "
                        "refine per-member afterward)")
        sf  = QFormLayout(sec)
        self._sec = _SectionPickerRow("IPE 300")
        sf.addRow("Profile:", self._sec)
        root.addWidget(sec)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def _on_accept(self) -> None:
        E, A, I, W_pl, W_el, b, h, density, fy, mat_type = self._sec.result
        if mat_type == "concrete":
            b_sec, h_sec, density_out = b, h, density
        else:
            # Steel/timber: self-weight stays an explicit load, not auto-added
            # from the picker's material density (matches Beam/Portal Wizard).
            b_sec = h_sec = density_out = 0.0

        self._state = frame_wizard(
            self._bays.value(), self._stories.value(),
            self._width.value(), self._height.value(),
            fixed_base=self._rb_fixed.isChecked(),
            E=E, A=A, I=I, fy=fy, W_pl=W_pl, W_el=W_el,
            b_sec=b_sec, h_sec=h_sec, density=density_out,
        )
        self.accept()

    def result(self) -> ModelState | None:
        return self._state
