"""Load combination manager — EN 1990 Table A1.2(B).

CombinationsDialog: manage combinations, auto-generate from existing load cases,
and solve individual combinations via a callback to MainWindow.
"""

from __future__ import annotations

import itertools

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QPushButton, QLabel, QFormLayout,
    QLineEdit, QComboBox, QDoubleSpinBox,
    QDialogButtonBox, QMessageBox, QAbstractItemView,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from ui_qt import theme
from ui_qt.dialog_style import apply_dialog_style, mark_primary
from ui_qt.icons import icon
from ui_qt.model_state import ModelState, LoadCombination, VARIABLE_CATEGORIES


# ── EN 1990 auto-generation ───────────────────────────────────────────────────

# EN 1990 Annex A1 recommended ψ factors (buildings)
_PSI0: dict[str, float] = {"Q": 0.7, "W": 0.6, "S": 0.5}   # companion ψ₀
_PSI2: dict[str, float] = {"Q": 0.3, "W": 0.0, "S": 0.2}   # quasi-permanent ψ₂

# Above this many generated combinations the Generate message explains where they come from.
MANY_COMBINATIONS = 60


def _companion_sets(cases: list) -> list[list]:
    """Every set of companions that may act together, the empty set included.

    EN 1990 6.4.3.2: a variable action is included only where it is unfavourable, so a
    companion that relieves the member must be left out — each one is in or out. Cases
    sharing an exclusive group (wind +X / -X) are alternatives: none or one of them.
    The largest set comes first, the empty set last.
    """
    choices: list[list] = [[c, None] for c in cases if not c.exclusive_group]
    groups: dict[str, list] = {}
    for c in cases:
        if c.exclusive_group:
            groups.setdefault(c.exclusive_group, []).append(c)
    choices += [members + [None] for members in groups.values()]
    return [[c for c in pick if c is not None] for pick in itertools.product(*choices)]


def cases_left_out(state: ModelState) -> list:
    """Load cases the generator ignores: neither permanent nor a known variable category."""
    return [lc for lc in state.load_cases
            if lc.category != "G" and lc.category not in VARIABLE_CATEGORIES]


def auto_generate_en1990(state: ModelState) -> list[LoadCombination]:
    """Generate EN 1990 Table A1.2(B) combinations — general algorithm.

    For every leading variable action and every set of companions (each companion in or
    out, EN 1990 6.4.3.2 — see ``_companion_sets``) this produces:
      - one ULS fundamental combination with unfavourable permanent actions (γG,sup)
      - one ULS fundamental combination with favourable permanent actions (γG,inf),
        when there are permanent cases (without them it would repeat the γG,sup one)
      - one SLS characteristic combination
    plus 1.35G alone (ULS) and one SLS quasi-permanent combination (all ψ₂ > 0 actions).
    With N independent variable cases that is N·2^(N-1) sets: 3N·2^(N-1) + 2 combinations
    (N = 3: 38). Alternatives (an exclusive group) count as one case with more choices.

    The favourable set (EN 1990 Table A1.2(B), γG,inf = 1.00) is what governs uplift and
    the minimum compression: leg tension in a tower is larger with 1.0G than with 1.35G.
    Each set applies one factor to ALL permanent cases (EN 1990 A1.3.1(3) allows splitting
    one permanent action into sup/inf parts; independent factors per case are not generated).

    Previously auto-generated combinations (is_auto=True) are removed first so
    re-running after load-case edits gives a clean replacement.
    Manually-added combinations (is_auto=False) are preserved.
    Load cases sharing an ``exclusive_group`` (wind +X / -X) are alternatives and are
    never combined with each other.

    γG = 1.35 (unfavourable permanent, γG,sup) and 1.00 (favourable, γG,inf)
    γQ = 1.50 (leading variable)
    ψ₀ per category: Q=0.7, W=0.6, S=0.5
    ψ₂ per category: Q=0.3, W=0.0, S=0.2
    Cases of any other category (seismic "E" in older files) are left out: see
    ``cases_left_out``.
    """
    # Remove old auto-generated combinations; keep manually-added ones
    for cid in [c.id for c in state.combinations if c.is_auto]:
        state.remove_combination(cid)

    g_cases   = [lc for lc in state.load_cases if lc.category == "G"]
    var_cases = [lc for lc in state.load_cases if lc.category in VARIABLE_CATEGORIES]

    generated: list[LoadCombination] = []

    def _psi0(lc) -> float:
        return _PSI0[lc.category]

    def _psi2(lc) -> float:
        return _PSI2[lc.category]

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
    g_uls_inf = [(g, 1.00) for g in g_cases]
    g_sls = [(g, 1.00) for g in g_cases]

    if not var_cases:
        if g_cases:
            _combo("ULS: 1.35G", "ULS", g_uls)
            _combo("SLS: 1.0G",  "SLS", g_sls)
        return generated

    # Permanent actions alone: a variable action is included only where it is unfavourable
    # (EN 1990 6.4.3.2), so 1.35G with no variable action is a combination in its own right —
    # it governs wherever the variable actions relieve the member. 1.0G alone never governs
    # (every effect is 1/1.35 of the 1.35G one), so it is not generated.
    if g_cases:
        _combo("ULS STR: 1.35G", "ULS", g_uls)

    # One ULS + one SLS Char per leading variable action (and per choice among alternatives)
    for i, leading in enumerate(var_cases):
        others = [lc for j, lc in enumerate(var_cases) if j != i
                  and not (leading.exclusive_group
                           and lc.exclusive_group == leading.exclusive_group)]
        for companions in _companion_sets(others):
            uls_parts = ["1.35G", _fmt(1.50, leading.name)]
            uls_parts += [_fmt(_psi0(c) * 1.5, c.name) for c in companions]
            variable = [(leading, 1.50)] + [(c, _psi0(c) * 1.5) for c in companions]
            _combo("ULS STR: " + " + ".join(uls_parts), "ULS", g_uls + variable)
            if g_cases:
                _combo("ULS STR (γG,inf): " + " + ".join(["G"] + uls_parts[1:]), "ULS",
                       g_uls_inf + variable)

            sls_parts = ["G", _fmt(1.00, leading.name)]
            sls_parts += [_fmt(_psi0(c), c.name) for c in companions]
            _combo("SLS Char: " + " + ".join(sls_parts), "SLS",
                   g_sls + [(leading, 1.00)] + [(c, _psi0(c)) for c in companions])

    # SLS Quasi-permanent: exclude variable cases whose ψ₂ = 0 (e.g. wind)
    qp_pairs = [(lc, _psi2(lc)) for lc in var_cases if _psi2(lc) > 1e-9]
    # alternatives (same exclusive group) are never present together: keep the first
    seen_groups: set[str] = set()
    qp_pairs = [(lc, f) for lc, f in qp_pairs
                if not lc.exclusive_group
                or (lc.exclusive_group not in seen_groups and not seen_groups.add(lc.exclusive_group))]
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

# Limit-state cells: soft tints of the theme's red / blue (axis colours) on the dark table
_ULS_COLOR = QColor(232, 80, 91, 70)
_SLS_COLOR = QColor(74, 144, 232, 70)


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

        auto_btn = QPushButton(icon("sigma", theme.LOAD), "Auto-generate EN 1990")
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

        self._env_btn = QPushButton(icon("chart-column", theme.RESULT), "Solve All && Envelope…")
        self._env_btn.clicked.connect(self._on_envelope)
        btn_row.addWidget(self._env_btn)

        self._solve_btn = QPushButton(icon("play"), "Solve Selected")
        self._solve_btn.clicked.connect(self._on_solve)
        btn_row.addWidget(self._solve_btn)

        layout.addLayout(btn_row)

        close_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_box.rejected.connect(self.accept)
        layout.addWidget(close_box)

        apply_dialog_style(
            self, "Load combinations — EN 1990",
            "Each combination is a factored sum of load cases. Auto-generate builds the "
            "standard ULS and SLS sets from the cases in your model; select one and solve it.",
            theme.LOAD, "sigma")
        mark_primary(self._solve_btn)
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
        left_out = cases_left_out(self._state)
        note = ""
        if left_out:
            names = ", ".join(f"{lc.name} ({lc.category})" for lc in left_out)
            note = (f"\n\nLeft out: {names}. Only G, Q, W and S cases are combined "
                    "automatically; add a combination by hand with Add… to use them.")
        if not generated:
            QMessageBox.information(
                self, "Nothing generated",
                "Could not determine standard combinations.\n"
                "Ensure your load cases have EN 1990 categories (G, Q, W, S)." + note
            )
            return
        self._rebuild_table()
        many = ""
        if len(generated) > MANY_COMBINATIONS:
            many = ("\n\nEach companion action is taken both with and without (it is left "
                    "out where it would relieve a member), so the number doubles with every "
                    "independent variable case. Cases that never act together (wind from "
                    "opposite directions) belong in one alternative group.")
        QMessageBox.information(
            self, "Combinations generated",
            f"{len(generated)} combination(s) created from EN 1990 Table A1.2(B).\n\n"
            "Select one and click Solve Selected." + many + note
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
        apply_dialog_style(self, "Add load combination",
                           "Name, limit state and a partial factor for each load case "
                           "(0 leaves the case out)", theme.LOAD, "sigma")

    def _on_ok(self) -> None:
        name = self._name.text().strip() or "Combination"
        ls   = self._ls.currentText()
        c = self._state.add_combination(name, ls)
        for case_id, spin in self._factor_spins:
            f = spin.value()
            if f != 0.0:
                c.factors[case_id] = f
        self.accept()
