"""Standalone dialog builder functions extracted from MainWindow.

Each function takes a parent QWidget and any model data it needs,
builds and shows the dialog, and returns nothing (or the user's choice).
No dependency on MainWindow internals.
"""
from __future__ import annotations

import sys

from ui_qt import theme
from ui_qt.dialog_style import apply_dialog_style, mark_primary
from ui_qt.version import VERSION_LABEL

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QHeaderView,
    QHBoxLayout, QLabel, QLineEdit, QComboBox, QDoubleSpinBox,
    QPushButton, QRadioButton, QSpinBox, QTableWidget, QTableWidgetItem,
    QTextEdit, QVBoxLayout,
)


# ── Keyboard shortcuts dialog ─────────────────────────────────────────────────

_SHORTCUTS = [
    ("File",                     None),
    ("New",                      "Ctrl+N"),
    ("Open",                     "Ctrl+O"),
    ("Save",                     "Ctrl+S"),
    ("Save As",                  "Ctrl+Shift+S"),
    ("Edit",                     None),
    ("Undo",                     "Ctrl+Z"),
    ("Redo",                     "Ctrl+Y"),
    ("Copy",                     "Ctrl+C"),
    ("Paste",                    "Ctrl+V"),
    ("Duplicate Array",          "Ctrl+D"),
    ("Solve",                    "F5"),
    ("Zoom to Fit",              "F"),
    ("View",                     None),
    ("Toggle Properties Panel",  "Alt+1"),
    ("Toggle Results Panel",     "Alt+2"),
    ("Canvas Modes",             None),
    ("Select Mode",              "S"),
    ("Add Node Mode",            "N"),
    ("Add Member Mode",          "M"),
    ("Measure Mode",             "R"),
    ("Selection",                None),
    ("Select All",               "Ctrl+A"),
    ("Deselect All",             "Ctrl+Shift+A"),
    ("Invert Selection",         "Ctrl+I"),
    ("Delete Selected",          "Del"),
    ("Transform (with a selection)", None),
    ("Move / Grab",              "G"),
    ("Extrude",                  "E"),
    ("Scale",                    "S"),
    ("Isolate / Restore All",    "I"),
    ("Lock to X / Y / Z axis",   "X / Y / Z"),
    ("Slide along a member (A again: next member)", "A"),
    ("Type an exact value",      "0-9 . , -"),
    ("Confirm typed value",      "Enter"),
    ("Cancel (grab/scale/measure)", "Esc"),
    ("Tools",                    None),
    ("Toggle Load Arrows",       "L"),
    ("Colour by Group",          "Ctrl+G"),
    ("Thickness by Section",     "Ctrl+T"),
    ("Groups Panel",             "Alt+3"),
    ("Collapse / Expand Ribbon", "Ctrl+F1"),
    ("Python Console",           "Ctrl+`"),
]


def show_keyboard_shortcuts(parent) -> None:
    """Display the keyboard shortcuts reference dialog."""
    dlg = QDialog(parent)
    dlg.setWindowTitle("Keyboard Shortcuts")
    dlg.resize(360, 440)
    layout = QVBoxLayout(dlg)

    table = QTableWidget(len(_SHORTCUTS), 2)
    table.setHorizontalHeaderLabels(["Action", "Shortcut"])
    table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
    table.verticalHeader().setVisible(False)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
    table.setShowGrid(False)

    bold = QFont()
    bold.setBold(True)

    for row, (action, key) in enumerate(_SHORTCUTS):
        if key is None:
            item = QTableWidgetItem(f"  {action}")
            item.setFont(bold)
            item.setForeground(QColor(theme.CYAN))
            table.setItem(row, 0, item)
            table.setSpan(row, 0, 1, 2)
        else:
            table.setItem(row, 0, QTableWidgetItem(f"    {action}"))
            table.setItem(row, 1, QTableWidgetItem(key))

    layout.addWidget(table)
    btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    btns.rejected.connect(dlg.accept)
    layout.addWidget(btns)
    dlg.resize(400, 560)
    apply_dialog_style(dlg, "Keyboard shortcuts", "Grouped by where they work",
                       theme.CYAN, "keyboard")
    dlg.exec()


# ── About dialog ──────────────────────────────────────────────────────────────

def show_about(parent) -> None:
    """Display the About StructLab dialog."""
    dlg = QDialog(parent)
    dlg.setWindowTitle("About StructLab")
    dlg.setFixedWidth(440)
    layout = QVBoxLayout(dlg)

    def _row(label: str, text: str) -> None:
        form.addRow(label, QLabel(text))

    box = QGroupBox("Details")
    form = QFormLayout(box)
    form.setSpacing(6)
    _row("Method:", "Direct Stiffness Method, linear static")
    _row("Structures:", "Beams · frames · trusses · mixed, 2D and 3D")
    _row("Validation:", "20 benchmark cases against OpenSeesPy and closed-form results")
    py = sys.version_info
    _row("Built with:", f"Python {py.major}.{py.minor}  ·  PyQt6  ·  NumPy / SciPy  ·  Matplotlib")
    _row("Licence:", "GPL v3  ·  © 2024–2026 Imed Mhamdi / INSTRA Analysis")
    for lbl in box.findChildren(QLabel):
        lbl.setWordWrap(True)
    layout.addWidget(box)

    btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    btns.rejected.connect(dlg.accept)
    layout.addWidget(btns)
    apply_dialog_style(dlg, f"StructLab {VERSION_LABEL}",
                       "2D and 3D structural analysis", theme.CYAN, "info")
    dlg.exec()


# ── Project info dialog ───────────────────────────────────────────────────────

def show_project_info(parent, state) -> bool:
    """Display the Project Info dialog. Returns True if user accepted changes."""
    from ui_qt.model_state import ProjectMetadata

    meta = state.metadata
    dlg = QDialog(parent)
    dlg.setWindowTitle("Project Information")
    dlg.setMinimumWidth(420)
    layout = QVBoxLayout(dlg)

    project_box = QGroupBox("Project")
    form = QFormLayout(project_box)
    form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
    form.setSpacing(8)

    def _field(value: str, placeholder: str = "") -> QLineEdit:
        le = QLineEdit(value)
        if placeholder:
            le.setPlaceholderText(placeholder)
        return le

    title_ed    = _field(meta.title, "Untitled Project")
    ref_ed      = _field(meta.project_ref, "e.g. 2024-ST-001")
    client_ed   = _field(meta.client, "Client name")
    company_ed  = _field(meta.company, "Engineering firm")
    designer_ed = _field(meta.designer_name, "Designer / Author")
    reviewer_ed = _field(meta.reviewer_name, "Reviewer")
    approver_ed = _field(meta.approver_name, "Approver / Principal")
    desc_ed     = QTextEdit(meta.description)
    desc_ed.setFixedHeight(72)
    desc_ed.setPlaceholderText("Brief description of the structure / project…")

    status_cb = QComboBox()
    for s in ("Preliminary", "For Review", "Approved"):
        status_cb.addItem(s)
    status_cb.setCurrentText(meta.status)

    form.addRow("Project title:", title_ed)
    form.addRow("Project ref:",   ref_ed)
    form.addRow("Client:",        client_ed)
    form.addRow("Company:",       company_ed)
    form.addRow("Status:",        status_cb)
    form.addRow("Description:",   desc_ed)

    layout.addWidget(project_box)

    sign_box = QGroupBox("Signatories")
    sign_form = QFormLayout(sign_box)
    sign_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
    sign_form.setSpacing(8)
    sign_form.addRow("Designer:",  designer_ed)
    sign_form.addRow("Reviewer:",  reviewer_ed)
    sign_form.addRow("Approver:",  approver_ed)
    layout.addWidget(sign_box)

    btns = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok |
        QDialogButtonBox.StandardButton.Cancel
    )
    btns.accepted.connect(dlg.accept)
    btns.rejected.connect(dlg.reject)
    layout.addWidget(btns)
    apply_dialog_style(dlg, "Project information",
                       "Title, client and signatories, shown on the PDF report",
                       theme.CYAN, "info")

    if dlg.exec() != QDialog.DialogCode.Accepted:
        return False

    meta.title         = title_ed.text().strip() or "Untitled Project"
    meta.project_ref   = ref_ed.text().strip()
    meta.client        = client_ed.text().strip()
    meta.company       = company_ed.text().strip()
    meta.description   = desc_ed.toPlainText().strip()
    meta.designer_name = designer_ed.text().strip()
    meta.reviewer_name = reviewer_ed.text().strip()
    meta.approver_name = approver_ed.text().strip()
    meta.status        = status_cb.currentText()
    return True


# ── Duplicate dialog ──────────────────────────────────────────────────────────

class DuplicateDialog(QDialog):
    """Ask the user for duplicate axis, offset distance, and copy count."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Duplicate Selection")

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # ── Axis ──────────────────────────────────────────────────────────────
        axis_box = QGroupBox("Axis")
        axis_row = QHBoxLayout(axis_box)
        self._axis_btns: dict[str, QRadioButton] = {}
        for ax in ("X", "Y", "Z"):
            rb = QRadioButton(ax)
            axis_row.addWidget(rb)
            self._axis_btns[ax] = rb
        self._axis_btns["Z"].setChecked(True)
        layout.addWidget(axis_box)

        # ── Offset + Copies ───────────────────────────────────────────────────
        form = QFormLayout()
        form.setSpacing(8)

        self._offset_spin = QDoubleSpinBox()
        self._offset_spin.setRange(-1000.0, 1000.0)
        self._offset_spin.setSingleStep(0.5)
        self._offset_spin.setDecimals(2)
        self._offset_spin.setSuffix(" m")
        self._offset_spin.setValue(3.0)
        form.addRow("Offset:", self._offset_spin)

        self._copies_spin = QSpinBox()
        self._copies_spin.setRange(1, 50)
        self._copies_spin.setValue(1)
        form.addRow("Copies:", self._copies_spin)

        layout.addLayout(form)

        # ── Buttons ───────────────────────────────────────────────────────────
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("Duplicate")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)
        self.setFixedWidth(340)
        apply_dialog_style(self, "Duplicate selection", "Copies along an axis",
                           theme.GEOMETRY, "copy-plus")

    @property
    def axis(self) -> str:
        for ax, rb in self._axis_btns.items():
            if rb.isChecked():
                return ax
        return "X"

    @property
    def offset(self) -> float:
        return self._offset_spin.value()

    @property
    def copies(self) -> int:
        return self._copies_spin.value()


# ── Subdivide dialog ──────────────────────────────────────────────────────────

class SubdivideDialog(QDialog):
    """Ask the user how many divisions to cut a member into."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Subdivide Member")

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        form = QFormLayout()
        form.setSpacing(8)

        self._div_spin = QSpinBox()
        self._div_spin.setRange(2, 50)
        self._div_spin.setValue(4)
        form.addRow("Divisions:", self._div_spin)
        layout.addLayout(form)

        self._nodes_only = QCheckBox("Nodes only  (remove sub-member segments)")
        layout.addWidget(self._nodes_only)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("Subdivide")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)
        self.setFixedWidth(340)
        apply_dialog_style(self, "Subdivide member", "Equal parts with new nodes",
                           theme.GEOMETRY, "split")

    @property
    def n_divisions(self) -> int:
        return self._div_spin.value()

    @property
    def nodes_only(self) -> bool:
        return self._nodes_only.isChecked()


# ── Mirror dialog ─────────────────────────────────────────────────────────────

class MirrorDialog(QDialog):
    """Ask the user for mirror plane, offset, and whether to keep the original."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Mirror Selection")

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        plane_box = QGroupBox("Mirror plane")
        plane_row = QHBoxLayout(plane_box)
        self._plane_btns: dict[str, QRadioButton] = {}
        for pl in ("XY", "XZ", "YZ"):
            rb = QRadioButton(pl)
            plane_row.addWidget(rb)
            self._plane_btns[pl] = rb
        self._plane_btns["XZ"].setChecked(True)
        layout.addWidget(plane_box)

        form = QFormLayout()
        form.setSpacing(8)
        self._offset_spin = QDoubleSpinBox()
        self._offset_spin.setRange(-1000.0, 1000.0)
        self._offset_spin.setSingleStep(0.5)
        self._offset_spin.setDecimals(2)
        self._offset_spin.setSuffix(" m")
        self._offset_spin.setValue(0.0)
        form.addRow("Plane offset:", self._offset_spin)
        layout.addLayout(form)

        self._keep_orig = QCheckBox("Keep original")
        self._keep_orig.setChecked(True)
        layout.addWidget(self._keep_orig)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("Mirror")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)
        self.setFixedWidth(340)
        apply_dialog_style(self, "Mirror selection", "Reflect about a plane",
                           theme.GEOMETRY, "flip-horizontal-2")

    @property
    def plane(self) -> str:
        for pl, rb in self._plane_btns.items():
            if rb.isChecked():
                return pl
        return "XZ"

    @property
    def offset(self) -> float:
        return self._offset_spin.value()

    @property
    def keep_original(self) -> bool:
        return self._keep_orig.isChecked()


class RotateDialog(QDialog):
    """Rotate the selection: axis, exact angle, pivot point, and optional duplication.

    ``copies`` is 0 for a plain rotation (the selection moves) and n >= 1 to keep the
    original and add n rotated copies at angle, 2·angle, … (a polar array).
    """

    def __init__(self, parent=None,
                 centroid: tuple[float, float, float] = (0.0, 0.0, 0.0)) -> None:
        super().__init__(parent)
        self.setWindowTitle("Rotate Selection")
        self.setMinimumWidth(320)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        axis_box = QGroupBox("Rotation axis (global, through the pivot)")
        axis_row = QHBoxLayout(axis_box)
        self._axis_btns: dict[str, QRadioButton] = {}
        for ax in ("X", "Y", "Z"):
            rb = QRadioButton(ax)
            axis_row.addWidget(rb)
            self._axis_btns[ax] = rb
        self._axis_btns["Z"].setChecked(True)
        layout.addWidget(axis_box)

        form = QFormLayout()
        self._angle = QDoubleSpinBox()
        self._angle.setRange(-360.0, 360.0)
        self._angle.setDecimals(4)
        self._angle.setSingleStep(15.0)
        self._angle.setSuffix(" °")
        self._angle.setValue(90.0)
        self._angle.setToolTip("Positive = anticlockwise looking down the axis from its + end (right-hand rule)")
        form.addRow("Angle:", self._angle)
        layout.addLayout(form)

        pivot_box = QGroupBox("Pivot")
        pv = QVBoxLayout(pivot_box)
        self._pivot_centroid = QRadioButton(
            f"Selection centre  ({centroid[0]:.3g}, {centroid[1]:.3g}, {centroid[2]:.3g}) m")
        self._pivot_point = QRadioButton("Point:")
        self._pivot_centroid.setChecked(True)
        pv.addWidget(self._pivot_centroid)
        row = QHBoxLayout()
        row.addWidget(self._pivot_point)
        self._pivot_spins = []
        for label, value in zip(("x", "y", "z"), centroid):
            spin = QDoubleSpinBox()
            spin.setRange(-10000.0, 10000.0)
            spin.setDecimals(3)
            spin.setSingleStep(0.5)
            spin.setValue(value)
            spin.setPrefix(f"{label} ")
            spin.setEnabled(False)
            row.addWidget(spin)
            self._pivot_spins.append(spin)
        pv.addLayout(row)
        self._pivot_point.toggled.connect(lambda on: [s.setEnabled(on) for s in self._pivot_spins])
        layout.addWidget(pivot_box)
        hint = QLabel("To copy around a tower or any symmetric structure, use Point on its axis "
                      "(e.g. 0, 0, 0). Copies that land exactly on existing members are skipped.")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {theme.TEXT_DIM};")
        layout.addWidget(hint)

        self._duplicate = QCheckBox("Duplicate — keep the original and add rotated copies")
        layout.addWidget(self._duplicate)
        copies_row = QFormLayout()
        self._copies = QSpinBox()
        self._copies.setRange(1, 360)
        self._copies.setValue(1)
        self._copies.setEnabled(False)
        self._copies.setToolTip("Copies at angle, 2×angle, 3×angle … (e.g. 3 copies at 90° fill a full turn)")
        copies_row.addRow("Number of copies:", self._copies)
        layout.addLayout(copies_row)
        self._duplicate.toggled.connect(self._copies.setEnabled)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("Rotate")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)
        apply_dialog_style(self, "Rotate selection",
                           "About a global axis, or as a polar array of copies",
                           theme.GEOMETRY, "rotate-3d")

    @property
    def axis(self) -> str:
        return next(ax for ax, rb in self._axis_btns.items() if rb.isChecked())

    @property
    def angle(self) -> float:
        return self._angle.value()

    @property
    def pivot(self) -> tuple[float, float, float] | None:
        """None = the selection centre; else the typed point."""
        if self._pivot_centroid.isChecked():
            return None
        return tuple(s.value() for s in self._pivot_spins)

    @property
    def copies(self) -> int:
        return self._copies.value() if self._duplicate.isChecked() else 0


class DuplicatesDialog(QDialog):
    """Check the model for coincident nodes, duplicate and zero-length members; select or fix them."""

    def __init__(self, scene, parent=None) -> None:
        super().__init__(parent)
        from ui_qt.model_checks import DEFAULT_TOL
        self.setWindowTitle("Check Duplicates")
        self.setMinimumWidth(420)
        self._scene = scene
        self.report = None
        self.summary = None

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self._tol = QDoubleSpinBox()
        self._tol.setRange(0.001, 1000.0)
        self._tol.setDecimals(3)
        self._tol.setSuffix(" mm")
        self._tol.setValue(DEFAULT_TOL * 1e3)
        self._tol.setToolTip("Nodes closer than this are treated as the same point")
        self._tol.valueChanged.connect(lambda _v: self.run_check())
        form.addRow("Tolerance:", self._tol)
        layout.addLayout(form)

        self._result = QLabel("")
        self._result.setWordWrap(True)
        self._result.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self._result)

        row = QHBoxLayout()
        self._btn_select = QPushButton("Select && Zoom")
        self._btn_select.setToolTip("Select the coincident nodes and duplicate members on the canvas")
        self._btn_select.clicked.connect(self.select_found)
        self._btn_fix = QPushButton("Merge && Remove")
        self._btn_fix.setToolTip("Merge coincident nodes and remove duplicate / zero-length members (undoable)")
        self._btn_fix.clicked.connect(self.fix)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        row.addWidget(self._btn_select)
        row.addWidget(self._btn_fix)
        row.addStretch()
        row.addWidget(close)
        layout.addLayout(row)
        apply_dialog_style(self, "Check duplicates",
                           "Coincident nodes; duplicate, zero-length and overlapping members",
                           theme.GEOMETRY, "scan-search")
        mark_primary(self._btn_fix)
        self.run_check()

    @property
    def tolerance(self) -> float:
        return self._tol.value() / 1e3

    def run_check(self) -> None:
        from ui_qt.model_checks import check_duplicates
        self.report = r = check_duplicates(self._scene.model_state, self.tolerance)
        if r.is_clean:
            self._result.setText("<b style='color:#2ecc71'>No duplicates found.</b><br>"
                                 f"{len(self._scene.model_state.nodes)} nodes and "
                                 f"{len(self._scene.model_state.members)} members checked.")
        else:
            lines = []
            if r.node_clusters:
                lines.append(f"<b>{r.extra_nodes}</b> coincident node(s) in {len(r.node_clusters)} location(s)")
            if r.member_groups:
                lines.append(f"<b>{r.extra_members}</b> duplicate member(s) in {len(r.member_groups)} location(s)")
            if r.zero_length:
                lines.append(f"<b>{len(r.zero_length)}</b> zero-length member(s)")
            if r.overlaps:
                lines.append(f"<b>{len(r.overlaps)}</b> pair(s) of overlapping members — collinear and "
                             "sharing part of their length (e.g. a member drawn over a divided one). "
                             "Select them and delete the one you do not want.")
            self._result.setText("<br>".join(lines))
        self._btn_select.setEnabled(not r.is_clean)
        self._btn_fix.setEnabled(r.fixable)

    def select_found(self) -> None:
        if self.report is not None:
            self._scene.focus_on(self.report.node_ids(), self.report.member_ids())

    def fix(self) -> None:
        self.summary = s = self._scene.merge_duplicates(self.tolerance)
        self.run_check()
        notes = [f"Merged {s.nodes_merged} node(s), removed {s.members_removed} duplicate and "
                 f"{s.zero_length_removed} zero-length member(s)."]
        if s.kept_reversed_with_loads:
            notes.append("Kept (reversed duplicates carrying loads — review by hand): members "
                         + ", ".join(map(str, s.kept_reversed_with_loads)))
        if s.support_conflicts:
            notes.append("Different supports met at node(s) "
                         + ", ".join(map(str, s.support_conflicts)) + " — check the support kept.")
        self._result.setText(self._result.text() + "<br><br>" + "<br>".join(notes))
