"""Parameterised wizard dialogs for StructLab.

Each dialog collects geometry, section, and load parameters, then calls the
corresponding builder function in presets.py to produce a ready-to-use
ModelState.

Three wizards are provided:
  BeamWizardDialog  — single or multi-span beam (steel or RC)
  PortalWizardDialog — single-bay portal frame (steel or RC, pinned/fixed base)
  TrussWizardDialog  — flat-chord truss (Pratt / Warren / Howe)
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QHBoxLayout, QGroupBox,
    QSpinBox, QDoubleSpinBox, QComboBox, QLabel,
    QRadioButton, QButtonGroup, QDialogButtonBox, QWidget,
)
from PyQt6.QtCore import Qt

from ui_qt.presets import (
    _E_STEEL, _E_C30, _E_C35, _RHO_RC,
    IPE_300, IPE_360, IPE_400, IPE_450, IPE_500,
    HEB_220, HEB_260, HEB_300, HEB_340,
    SHS_150_8, SHS_200_10,
    beam_wizard, portal_wizard, truss_wizard,
)
from ui_qt.model_state import ModelState


# ── Section lookup tables ─────────────────────────────────────────────────────

_BEAM_SECTIONS = [
    ("IPE 300", IPE_300),
    ("IPE 360", IPE_360),
    ("IPE 400", IPE_400),
    ("IPE 450", IPE_450),
    ("IPE 500", IPE_500),
    ("HEB 220", HEB_220),
    ("HEB 260", HEB_260),
    ("HEB 300", HEB_300),
    ("HEB 340", HEB_340),
    ("SHS 200×10", SHS_200_10),
]

_COLUMN_SECTIONS = [
    ("HEB 220", HEB_220),
    ("HEB 260", HEB_260),
    ("HEB 300", HEB_300),
    ("HEB 340", HEB_340),
    ("SHS 200×10", SHS_200_10),
    ("IPE 360", IPE_360),
    ("IPE 400", IPE_400),
]

_RAFTER_SECTIONS = [
    ("IPE 360", IPE_360),
    ("IPE_400", IPE_400),
    ("IPE 450", IPE_450),
    ("IPE 500", IPE_500),
    ("HEB 220", HEB_220),
    ("HEB 260", HEB_260),
    ("SHS 200×10", SHS_200_10),
]

_CHORD_SECTIONS = [
    ("SHS 200×10", SHS_200_10),
    ("SHS 150×8",  SHS_150_8),
    ("IPE 360",    IPE_360),
    ("IPE 400",    IPE_400),
]

_WEB_SECTIONS = [
    ("SHS 150×8",  SHS_150_8),
    ("SHS 200×10", SHS_200_10),
    ("IPE 300",    IPE_300),
]


def _profile_combo(options: list[tuple[str, tuple]], default: int = 0) -> QComboBox:
    cb = QComboBox()
    for name, profile in options:
        cb.addItem(name, userData=profile)
    cb.setCurrentIndex(min(default, len(options) - 1))
    return cb


# ─────────────────────────────────────────────────────────────────────────────

class BeamWizardDialog(QDialog):
    """Wizard for generating a single or multi-span beam model."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Beam Wizard")
        self.setMinimumWidth(400)
        self._state: ModelState | None = None
        self._init_ui()

    def _init_ui(self) -> None:
        root = QVBoxLayout(self)

        # ── Geometry ──────────────────────────────────────────────────────────
        geo = QGroupBox("Geometry")
        gf  = QFormLayout(geo)

        self._config = QComboBox()
        self._config.addItems([
            "Single span",
            "Continuous — 2 spans",
            "Continuous — 3 spans",
            "Continuous — 4 spans",
            "Continuous — 5 spans",
        ])
        gf.addRow("Configuration:", self._config)

        self._span_l = QDoubleSpinBox()
        self._span_l.setRange(0.5, 200.0)
        self._span_l.setValue(6.0)
        self._span_l.setSuffix("  m")
        gf.addRow("Span length (each):", self._span_l)
        root.addWidget(geo)

        # ── Supports ──────────────────────────────────────────────────────────
        sup = QGroupBox("Supports")
        sf  = QFormLayout(sup)

        self._left_sup = QComboBox()
        self._left_sup.addItems(["PIN", "FIXED"])
        sf.addRow("Left end:", self._left_sup)

        self._right_sup = QComboBox()
        self._right_sup.addItems(["ROLLER", "PIN"])
        sf.addRow("Right end:", self._right_sup)
        root.addWidget(sup)

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
        self._steel_sec = _profile_combo(_BEAM_SECTIONS, default=2)   # IPE 400
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

    def _section(self) -> tuple[float, float, float]:
        if self._rb_steel.isChecked():
            return self._steel_sec.currentData()
        E = _E_C30 if self._rc_grade.currentIndex() == 0 else _E_C35
        b = self._rc_b.value() / 1000.0
        h = self._rc_h.value() / 1000.0
        return E, b * h, b * h ** 3 / 12.0

    def _on_accept(self) -> None:
        n_spans = self._config.currentIndex() + 1
        spans   = [self._span_l.value()] * n_spans
        left    = self._left_sup.currentText()
        right   = self._right_sup.currentText()
        if n_spans == 1:
            sup_types = [left, right]
        else:
            sup_types = [left] + ["ROLLER"] * (n_spans - 1) + [right]

        E, A, I  = self._section()
        density  = _RHO_RC if self._rb_rc.isChecked() else 0.0

        self._state = beam_wizard(
            spans=spans,
            support_types=sup_types,
            E=E, A=A, I=I,
            udl_g=self._udl_g.value() * 1_000.0,
            udl_q=self._udl_q.value() * 1_000.0,
            point_q=self._pt_q.value()  * 1_000.0,
            density=density,
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
        sec = QGroupBox("Sections  (Steel S355)")
        sf  = QFormLayout(sec)

        self._col_sec = _profile_combo(_COLUMN_SECTIONS, default=1)   # HEB 260
        self._raf_sec = _profile_combo(_RAFTER_SECTIONS, default=2)   # IPE 450
        sf.addRow("Column profile:", self._col_sec)
        sf.addRow("Rafter profile:", self._raf_sec)
        root.addWidget(sec)

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
        col = self._col_sec.currentData()
        raf = self._raf_sec.currentData()

        self._state = portal_wizard(
            span=self._span.value(),
            height=self._height.value(),
            fixed_base=self._rb_fixed.isChecked(),
            E_col=col[0], A_col=col[1], I_col=col[2],
            E_raf=raf[0], A_raf=raf[1], I_raf=raf[2],
            udl_g=self._udl_g.value() * 1_000.0,
            udl_q=self._udl_q.value() * 1_000.0,
            wind_h=self._wind.value()  * 1_000.0,
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
        sec = QGroupBox("Sections  (Steel S355 — all BAR elements)")
        sf  = QFormLayout(sec)

        self._chord_sec = _profile_combo(_CHORD_SECTIONS, default=0)   # SHS 200×10
        self._web_sec   = _profile_combo(_WEB_SECTIONS,   default=0)   # SHS 150×8
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

        self._state = truss_wizard(
            truss_type=t,
            n_panels=self._n_panels.value(),
            span=self._span.value(),
            depth=self._depth.value(),
            chord_section=self._chord_sec.currentData(),
            web_section=self._web_sec.currentData(),
            panel_load=self._panel_load.value() * 1_000.0,
            load_on_top=self._rb_top.isChecked(),
        )
        self.accept()

    def result(self) -> ModelState | None:
        return self._state
