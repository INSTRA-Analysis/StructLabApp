"""Load combination manager — EN 1990 Table A1.2(B).

CombinationsDialog: manage combinations, auto-generate from existing load cases,
and solve individual combinations via a callback to MainWindow.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QPushButton, QLabel, QFormLayout,
    QLineEdit, QComboBox, QDoubleSpinBox,
    QDialogButtonBox, QMessageBox, QAbstractItemView,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from ui_qt.model_state import ModelState, LoadCombination


# ── EN 1990 auto-generation ───────────────────────────────────────────────────

# EN 1990 Annex A1 recommended ψ factors (buildings)
_PSI0: dict[str, float] = {"Q": 0.7, "W": 0.6, "S": 0.5}   # companion ψ₀
_PSI2: dict[str, float] = {"Q": 0.3, "W": 0.0, "S": 0.2}   # quasi-permanent ψ₂


def auto_generate_en1990(state: ModelState) -> list[LoadCombination]:
    """Generate EN 1990 Table A1.2(B) combinations — general algorithm.

    For N variable load cases this produces:
      - N × ULS fundamental combinations  (one per leading variable action)
      - N × SLS characteristic combinations
      - 1 × SLS quasi-permanent combination
    i.e. 2N + 1 total (ψ₂ = 0 cases are excluded from the QP combo).

    Previously auto-generated combinations (is_auto=True) are removed first so
    re-running after load-case edits gives a clean replacement.
    Manually-added combinations (is_auto=False) are preserved.

    γG = 1.35 (unfavourable permanent)
    γQ = 1.50 (leading variable)
    ψ₀ per category: Q=0.7, W=0.6, S=0.5  (default 0.7 for unknown categories)
    ψ₂ per category: Q=0.3, W=0.0, S=0.2  (default 0.3 for unknown categories)
    """
    # Remove old auto-generated combinations; keep manually-added ones
    for cid in [c.id for c in state.combinations if c.is_auto]:
        state.remove_combination(cid)

    g_cases   = [lc for lc in state.load_cases if lc.category == "G"]
    var_cases = [lc for lc in state.load_cases if lc.category != "G"]

    generated: list[LoadCombination] = []

    def _psi0(lc) -> float:
        return _PSI0.get(lc.category, 0.7)

    def _psi2(lc) -> float:
        return _PSI2.get(lc.category, 0.3)

    def _combo(name: str, ls: str, pairs: list) -> LoadCombination:
        c = state.add_combination(name, ls)
        c.is_auto = True
        for lc, factor in pairs:
            if abs(factor) > 1e-9:
                c.factors[lc.id] = factor
        generated.append(c)
        return c

    def _fmt(factor: float, name: str) -> str:
        return f"{factor:g}·{name}"

    g_uls = [(g, 1.35) for g in g_cases]
    g_sls = [(g, 1.00) for g in g_cases]

    if not var_cases:
        if g_cases:
            _combo("ULS: 1.35G", "ULS", g_uls)
            _combo("SLS: 1.0G",  "SLS", g_sls)
        return generated

    # One ULS + one SLS Char per leading variable action
    for i, leading in enumerate(var_cases):
        companions = [lc for j, lc in enumerate(var_cases) if j != i]

        uls_parts = ["1.35G", _fmt(1.50, leading.name)]
        uls_parts += [_fmt(_psi0(c) * 1.5, c.name) for c in companions]
        _combo("ULS STR: " + " + ".join(uls_parts), "ULS",
               g_uls + [(leading, 1.50)] + [(c, _psi0(c) * 1.5) for c in companions])

        sls_parts = ["G", _fmt(1.00, leading.name)]
        sls_parts += [_fmt(_psi0(c), c.name) for c in companions]
        _combo("SLS Char: " + " + ".join(sls_parts), "SLS",
               g_sls + [(leading, 1.00)] + [(c, _psi0(c)) for c in companions])

    # SLS Quasi-permanent: exclude variable cases whose ψ₂ = 0 (e.g. wind)
    qp_pairs = [(lc, _psi2(lc)) for lc in var_cases if _psi2(lc) > 1e-9]
    qp_parts = ["G"] + [_fmt(f, lc.name) for lc, f in qp_pairs]
    _combo("SLS Quasi-permanent: " + " + ".join(qp_parts), "SLS",
           g_sls + qp_pairs)

    return generated


def _factors_summary(combo: LoadCombination, state: ModelState) -> str:
    """One-line description e.g. '1.35 × Gravity (G+Q)  +  1.50 × Wind (W)'."""
    parts = []
    for case_id, factor in combo.factors.items():
        lc = state.get_load_case(case_id)
        name = lc.name if lc else f"[deleted:{case_id}]"
        parts.append(f"{factor:g} × {name}")
    return "  +  ".join(parts) if parts else "(no factors)"


# ── CombinationsDialog ────────────────────────────────────────────────────────

_ULS_COLOR = QColor("#5a1a1a")
_SLS_COLOR = QColor("#0d2b45")

_BTN_STYLE = (
    "QPushButton {{ font-weight: bold; color: white; border-radius: 3px;"
    " padding: 5px 12px; background-color: {bg}; }}"
    "QPushButton:hover {{ background-color: {hv}; }}"
    "QPushButton:pressed {{ background-color: {pr}; }}"
    "QPushButton:disabled {{ background-color: #555; color: #888; }}"
)


class CombinationsDialog(QDialog):
    """Manage EN 1990 load combinations and solve individual ones."""

    def __init__(self, state: ModelState, solve_callback,
                 envelope_callback=None, parent=None) -> None:
        super().__init__(parent)
        self._state       = state
        self._solve_cb    = solve_callback
        self._envelope_cb = envelope_callback
        self.setWindowTitle("Load Combinations — EN 1990")
        self.setMinimumWidth(740)
        self.setMinimumHeight(400)

        layout = QVBoxLayout(self)

        # ── header ────────────────────────────────────────────────────────────
        hdr = QLabel(
            "<b>EN 1990 Load Combinations</b>  ·  "
            "Each combination is a factored superposition of load cases.  "
            "Click <b>Auto-generate</b> to build standard ULS/SLS combinations "
            "from the cases already in your model, then select one and click "
            "<b>Solve Selected</b>."
        )
        hdr.setWordWrap(True)
        layout.addWidget(hdr)

        # ── table ─────────────────────────────────────────────────────────────
        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Name", "Type", "Factors"])
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.setColumnWidth(0, 240)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        layout.addWidget(self._table)

        # ── button row ────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()

        auto_btn = QPushButton("Auto-generate EN 1990")
        auto_btn.setStyleSheet(
            _BTN_STYLE.format(bg="#1565C0", hv="#1976D2", pr="#0d47a1")
        )
        auto_btn.clicked.connect(self._on_auto_generate)
        btn_row.addWidget(auto_btn)

        btn_row.addSpacing(12)

        add_btn = QPushButton("Add…")
        add_btn.clicked.connect(self._on_add)
        btn_row.addWidget(add_btn)

        del_btn = QPushButton("Delete")
        del_btn.clicked.connect(self._on_delete)
        btn_row.addWidget(del_btn)

        btn_row.addStretch()

        self._env_btn = QPushButton("Solve All & Envelope…")
        self._env_btn.setStyleSheet(
            _BTN_STYLE.format(bg="#4A148C", hv="#6A1B9A", pr="#38006b")
        )
        self._env_btn.clicked.connect(self._on_envelope)
        btn_row.addWidget(self._env_btn)

        self._solve_btn = QPushButton("Solve Selected")
        self._solve_btn.setStyleSheet(
            _BTN_STYLE.format(bg="#2196F3", hv="#1976D2", pr="#0D47A1")
        )
        self._solve_btn.clicked.connect(self._on_solve)
        btn_row.addWidget(self._solve_btn)

        layout.addLayout(btn_row)

        close_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_box.rejected.connect(self.accept)
        layout.addWidget(close_box)

        self._rebuild_table()

    # ── table helpers ─────────────────────────────────────────────────────────

    def _rebuild_table(self) -> None:
        self._table.setRowCount(0)
        for combo in self._state.combinations:
            row = self._table.rowCount()
            self._table.insertRow(row)

            name_item = QTableWidgetItem(combo.name)
            name_item.setData(Qt.ItemDataRole.UserRole, combo.id)
            self._table.setItem(row, 0, name_item)

            ls_item = QTableWidgetItem(combo.limit_state)
            ls_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            ls_item.setBackground(_ULS_COLOR if combo.limit_state == "ULS" else _SLS_COLOR)
            self._table.setItem(row, 1, ls_item)

            self._table.setItem(row, 2,
                                QTableWidgetItem(_factors_summary(combo, self._state)))

        has = bool(self._state.combinations)
        self._solve_btn.setEnabled(has)
        self._env_btn.setEnabled(has and self._envelope_cb is not None)

    def _selected_combo(self) -> LoadCombination | None:
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, 0)
        return self._state.get_combination(
            item.data(Qt.ItemDataRole.UserRole)) if item else None

    # ── actions ───────────────────────────────────────────────────────────────

    def _on_auto_generate(self) -> None:
        if not self._state.load_cases:
            QMessageBox.information(self, "No load cases",
                                    "Add at least one load case to the model first.")
            return
        generated = auto_generate_en1990(self._state)
        if not generated:
            QMessageBox.information(
                self, "Nothing generated",
                "Could not determine standard combinations.\n"
                "Ensure your load cases have EN 1990 categories (G, Q, W, S)."
            )
            return
        self._rebuild_table()
        QMessageBox.information(
            self, "Combinations generated",
            f"{len(generated)} combination(s) created from EN 1990 Table A1.2(B).\n\n"
            "Select one and click Solve Selected."
        )

    def _on_add(self) -> None:
        dlg = _AddCombinationDialog(self._state, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._rebuild_table()

    def _on_delete(self) -> None:
        combo = self._selected_combo()
        if combo is None:
            QMessageBox.information(self, "No selection",
                                    "Select a combination to delete.")
            return
        self._state.remove_combination(combo.id)
        self._rebuild_table()

    def _on_envelope(self) -> None:
        if not self._state.combinations:
            QMessageBox.information(self, "No combinations",
                                    "Add or auto-generate combinations first.")
            return
        if self._envelope_cb:
            self._envelope_cb(self._state.combinations)

    def _on_solve(self) -> None:
        combo = self._selected_combo()
        if combo is None:
            QMessageBox.information(self, "No selection",
                                    "Select a combination to solve.")
            return
        if not combo.factors:
            QMessageBox.warning(self, "Empty combination",
                                "This combination has no load case factors defined.")
            return
        self._solve_cb(combo)


# ── _AddCombinationDialog ─────────────────────────────────────────────────────

class _AddCombinationDialog(QDialog):
    """Sub-dialog for defining one combination manually."""

    def __init__(self, state: ModelState, parent=None) -> None:
        super().__init__(parent)
        self._state = state
        self.setWindowTitle("Add Load Combination")
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._name = QLineEdit("New combination")
        self._ls   = QComboBox()
        self._ls.addItems(["ULS", "SLS"])
        form.addRow("Name:", self._name)
        form.addRow("Limit state:", self._ls)
        layout.addLayout(form)

        layout.addWidget(QLabel("<b>Partial factors per load case:</b>"))

        self._factor_spins: list[tuple[int, QDoubleSpinBox]] = []
        for lc in state.load_cases:
            row_layout = QHBoxLayout()
            lbl = QLabel(f"  {lc.name}  <small>({lc.category})</small>")
            lbl.setTextFormat(Qt.TextFormat.RichText)
            row_layout.addWidget(lbl)
            row_layout.addStretch()
            spin = QDoubleSpinBox()
            spin.setRange(-10.0, 10.0)
            spin.setSingleStep(0.05)
            spin.setDecimals(2)
            spin.setValue(0.0)
            spin.setFixedWidth(80)
            row_layout.addWidget(spin)
            layout.addLayout(row_layout)
            self._factor_spins.append((lc.id, spin))

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._on_ok)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _on_ok(self) -> None:
        name = self._name.text().strip() or "Combination"
        ls   = self._ls.currentText()
        c = self._state.add_combination(name, ls)
        for case_id, spin in self._factor_spins:
            f = spin.value()
            if f != 0.0:
                c.factors[case_id] = f
        self.accept()
