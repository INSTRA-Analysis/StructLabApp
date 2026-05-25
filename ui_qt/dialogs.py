"""Standalone dialog builder functions extracted from MainWindow.

Each function takes a parent QWidget and any model data it needs,
builds and shows the dialog, and returns nothing (or the user's choice).
No dependency on MainWindow internals.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QHeaderView,
    QHBoxLayout, QLabel, QLineEdit, QComboBox, QDoubleSpinBox,
    QRadioButton, QSpinBox, QTableWidget, QTableWidgetItem,
    QTextEdit, QVBoxLayout,
)


# ── Keyboard shortcuts dialog ─────────────────────────────────────────────────

_SHORTCUTS = [
    ("File",              None),
    ("New",               "Ctrl+N"),
    ("Open",              "Ctrl+O"),
    ("Save",              "Ctrl+S"),
    ("Edit",              None),
    ("Undo",              "Ctrl+Z"),
    ("Redo",              "Ctrl+Y"),
    ("Copy",              "Ctrl+C"),
    ("Paste",             "Ctrl+V"),
    ("Duplicate",         "Ctrl+D"),
    ("Solve",             "F5"),
    ("Zoom to Fit",       "F"),
    ("Canvas Modes",      None),
    ("Select Mode",       "S"),
    ("Add Node Mode",     "N"),
    ("Add Member Mode",   "M"),
    ("Selection",         None),
    ("Select All",        "Ctrl+A"),
    ("Deselect All",      "Ctrl+Shift+A"),
    ("Invert Selection",  "Ctrl+I"),
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
            item.setForeground(QColor("#00ACC1"))
            table.setItem(row, 0, item)
            table.setSpan(row, 0, 1, 2)
        else:
            table.setItem(row, 0, QTableWidgetItem(f"    {action}"))
            table.setItem(row, 1, QTableWidgetItem(key))

    layout.addWidget(table)
    btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    btns.rejected.connect(dlg.accept)
    layout.addWidget(btns)
    dlg.exec()


# ── About dialog ──────────────────────────────────────────────────────────────

def show_about(parent) -> None:
    """Display the About StructLab dialog."""
    dlg = QDialog(parent)
    dlg.setWindowTitle("About StructLab")
    dlg.setFixedWidth(380)
    layout = QVBoxLayout(dlg)
    layout.setSpacing(10)
    layout.setContentsMargins(28, 24, 28, 20)

    def _lbl(text: str, style: str = "") -> QLabel:
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setWordWrap(True)
        if style:
            lbl.setStyleSheet(style)
        return lbl

    title_font = QFont(); title_font.setPointSize(22); title_font.setBold(True)
    title = _lbl("StructLab")
    title.setFont(title_font)
    title.setStyleSheet("color:#00ACC1;")
    layout.addWidget(title)

    layout.addWidget(_lbl("V1.0.0", "color:#888; font-size:11px;"))

    line = QLabel(); line.setFixedHeight(1)
    line.setStyleSheet("background:#2a2a34;")
    layout.addWidget(line)

    layout.addWidget(_lbl(
        "2D structural analysis using the Direct Stiffness Method.\n"
        "Beams · Frames · Trusses · Mixed structures.",
        "color:#bbb; font-size:11px; padding: 4px 0;",
    ))

    line2 = QLabel(); line2.setFixedHeight(1)
    line2.setStyleSheet("background:#2a2a34;")
    layout.addWidget(line2)

    layout.addWidget(_lbl("Built with", "color:#666; font-size:10px;"))
    layout.addWidget(_lbl(
        "Python 3.12  ·  PyQt6  ·  NumPy / SciPy  ·  Matplotlib",
        "color:#888; font-size:10px;",
    ))

    layout.addWidget(_lbl(
        "Validated against OpenSeesPy — 13 benchmark cases, 0.00 % error",
        "color:#666; font-size:10px; padding-top:4px;",
    ))

    btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    btns.rejected.connect(dlg.accept)
    layout.addWidget(btns)
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
    layout.setSpacing(10)
    layout.setContentsMargins(20, 16, 20, 16)

    form = QFormLayout()
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

    lbl = QLabel("Signatories")
    lbl.setStyleSheet("color:#00ACC1; font-weight:bold; padding-top:6px;")
    layout.addLayout(form)
    layout.addWidget(lbl)

    sign_form = QFormLayout()
    sign_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
    sign_form.setSpacing(8)
    sign_form.addRow("Designer:",  designer_ed)
    sign_form.addRow("Reviewer:",  reviewer_ed)
    sign_form.addRow("Approver:",  approver_ed)
    layout.addLayout(sign_form)

    btns = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok |
        QDialogButtonBox.StandardButton.Cancel
    )
    btns.accepted.connect(dlg.accept)
    btns.rejected.connect(dlg.reject)
    layout.addWidget(btns)

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

    def __init__(self, parent=None, is_3d: bool = False) -> None:
        super().__init__(parent)
        self.setWindowTitle("Duplicate Selection")
        self.setFixedWidth(300)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # ── Axis ──────────────────────────────────────────────────────────────
        axis_box = QGroupBox("Axis")
        axis_row = QHBoxLayout(axis_box)
        self._axis_btns: dict[str, QRadioButton] = {}
        axes = ["X", "Y", "Z"] if is_3d else ["X", "Y"]
        for ax in axes:
            rb = QRadioButton(ax)
            axis_row.addWidget(rb)
            self._axis_btns[ax] = rb
        default_ax = "Z" if is_3d else "X"
        self._axis_btns[default_ax].setChecked(True)
        layout.addWidget(axis_box)

        # ── Offset + Copies ───────────────────────────────────────────────────
        form = QFormLayout()
        form.setSpacing(8)

        self._offset_spin = QDoubleSpinBox()
        self._offset_spin.setRange(-1000.0, 1000.0)
        self._offset_spin.setSingleStep(0.5)
        self._offset_spin.setDecimals(2)
        self._offset_spin.setSuffix(" m")
        self._offset_spin.setValue(3.0 if is_3d else 1.0)
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
        self.setFixedWidth(280)

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

    @property
    def n_divisions(self) -> int:
        return self._div_spin.value()

    @property
    def nodes_only(self) -> bool:
        return self._nodes_only.isChecked()


# ── Mirror dialog ─────────────────────────────────────────────────────────────

class MirrorDialog(QDialog):
    """Ask the user for mirror plane, offset, and whether to keep the original."""

    def __init__(self, parent=None, is_3d: bool = True) -> None:
        super().__init__(parent)
        self.setWindowTitle("Mirror Selection")
        self.setFixedWidth(280)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        plane_box = QGroupBox("Mirror plane")
        plane_row = QHBoxLayout(plane_box)
        self._plane_btns: dict[str, QRadioButton] = {}
        planes = ["XY", "XZ", "YZ"] if is_3d else ["XY"]
        for pl in planes:
            rb = QRadioButton(pl)
            plane_row.addWidget(rb)
            self._plane_btns[pl] = rb
        default = "XZ" if is_3d else "XY"
        self._plane_btns[default].setChecked(True)
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
