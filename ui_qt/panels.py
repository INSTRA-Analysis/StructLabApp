"""Properties inspector and Results panels for the StructLab Qt UI."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtGui import QBrush, QColor, QFont, QPixmap
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QDoubleSpinBox, QSpinBox, QComboBox, QPushButton, QLineEdit,
    QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QScrollArea, QSizePolicy, QFrame, QSplitter, QMenu,
)
from PyQt6.QtCore import Qt, pyqtSignal, QItemSelectionModel

from ui_qt.model_state import (
    NodeData, MemberData, SupportType, ElementType, PointLoadData,
    LoadCase, NodeLoad, MemberLoad, PartialDistLoad, DistLoad,
)

_ASSETS = Path(__file__).parent / "assets"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _spin(value: float, lo: float, hi: float, step: float,
          decimals: int = 3) -> QDoubleSpinBox:
    w = QDoubleSpinBox()
    w.setRange(lo, hi)
    w.setSingleStep(step)
    w.setDecimals(decimals)
    w.setValue(value)
    return w


def _label_value(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return lbl


# ── selection summary helpers (read-only "current properties" read-out) ───────

_ETYPE_LABELS = {
    ElementType.BEAM:      "Beam — rigid (full bending)",
    ElementType.BAR:       "Bar — pin–pin (axial only)",
    ElementType.PIN_LEFT:  "Pin at I end",
    ElementType.PIN_RIGHT: "Pin at J end",
}


def _profile_name(E: float, A: float, I: float) -> str:
    """Reverse-lookup a steel section name from (A, I); 'Custom' if no match."""
    name = _build_section_lookup().get((round(A, 8), round(I, 12)))
    return name if name else "Custom"


def _summary_table(rows: list[tuple[str, str]]) -> str:
    """Render (key, value) rows as a compact two-column HTML table."""
    cells = "".join(
        f"<tr><td style='color:#8a93a6;padding-right:10px'>{k}</td>"
        f"<td><b>{v}</b></td></tr>"
        for k, v in rows
    )
    return f"<table cellspacing='2'>{cells}</table>"


def _member_summary_html(m: MemberData) -> str:
    """Read-only summary of a member's *current saved* properties."""
    rows: list[tuple[str, str]] = [
        ("Element type", _ETYPE_LABELS.get(m.element_type, m.element_type.name)),
    ]
    if (m.group or "").strip():
        rows.append(("Group", m.group.strip()))
    rows.append(("Profile", _profile_name(m.E, m.A, m.I)))
    rows.append(("A", f"{m.A:.4g} m²"))
    rows.append(("E", f"{m.E / 1e9:.0f} GPa"))
    if m.element_type != ElementType.BAR:
        rows.append(("I_z", f"{m.I * 1e6:.4g} ×10⁻⁶ m⁴"))
    rows.append(("f_y", f"{m.fy / 1e6:.0f} MPa"))
    return _summary_table(rows)


def _multi_member_summary_html(members: list) -> str:
    """Read-only summary across a multi-member selection ('mixed' if not uniform)."""
    def uniform(key):
        vals = {key(m) for m in members}
        return vals.pop() if len(vals) == 1 else None

    et = uniform(lambda m: m.element_type)
    et_str = _ETYPE_LABELS.get(et, et.name) if et is not None else "mixed"
    prof_uniform = uniform(lambda m: (round(m.A, 8), round(m.I, 12)))
    prof_str = (_profile_name(members[0].E, members[0].A, members[0].I)
                if prof_uniform is not None else "mixed")
    distinct_groups = sorted({(m.group or "").strip() for m in members
                              if (m.group or "").strip()})
    grp_str = ", ".join(distinct_groups) if distinct_groups else "—"
    return _summary_table([
        ("Count", f"{len(members)} members"),
        ("Element type", et_str),
        ("Profile", prof_str),
        ("Groups", grp_str),
    ])


# ─────────────────────────────────────────────────────────────────────────────
# PropertiesPanel
# ─────────────────────────────────────────────────────────────────────────────

class PropertiesPanel(QWidget):
    """Context-sensitive inspector shown in the Properties dock.

    Call show_node(node) or show_member(member) after a canvas selection event.
    The panel emits no signals — the Apply button writes directly to the data
    object and then calls the optional refresh_callback so the canvas redraws.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._placeholder = QLabel("Click a node or member to inspect.")
        self._placeholder.setWordWrap(True)
        self._layout.addWidget(self._placeholder)
        self._content: QWidget | None = None
        self.refresh_callback = None      # set by MainWindow
        self.divide_callback = None       # set by MainWindow: (member_id, n_div) -> None
        self._model_state = None          # set by MainWindow via set_model_state()

    def set_model_state(self, state) -> None:
        """Keep a reference so forms can read/write the active load case."""
        self._model_state = state

    def _active_case(self) -> LoadCase | None:
        return self._model_state.active_case if self._model_state else None

    # ── public entry points ───────────────────────────────────────────────────

    def show_empty(self) -> None:
        self._replace(None)

    def show_node(self, node: NodeData) -> None:
        is_2d = bool(self._model_state and self._model_state.is_2d)
        self._replace(_NodeForm(node, self._active_case(), self._on_apply, is_2d=is_2d))

    def show_member(self, member: MemberData) -> None:
        self._replace(_MemberForm(member, self._model_state, self._on_apply,
                                  self.divide_callback))

    def show_nodes(self, nodes: list) -> None:
        self._replace(_MultiNodeForm(nodes, self._active_case(), self._on_apply))

    def show_members(self, members: list) -> None:
        self._replace(_MultiMemberForm(members, self._model_state, self._on_apply))

    def show_mixed(self, nodes: list, members: list, on_filter) -> None:
        self._replace(_MixedFilterForm(nodes, members, on_filter))

    # ── internal ─────────────────────────────────────────────────────────────

    def _replace(self, widget: QWidget | None) -> None:
        if self._content:
            self._layout.removeWidget(self._content)
            self._content.deleteLater()
            self._content = None

        if widget is None:
            self._placeholder.show()
        else:
            self._placeholder.hide()
            self._content = widget
            self._layout.addWidget(widget)

    def _on_apply(self) -> None:
        if self.refresh_callback:
            self.refresh_callback()


# Distributed load direction definitions — shared by single and multi member forms
_DL_DIRS = [
    ("w",  "Local ↓  (w)",     "Full-span load local ⊥ to member  —  ↓ positive"),
    ("qx", "qx  (→ Global X)", "Global X direction  —  + rightward"),
    ("qy", "qy  (↗ Global Y)", "Global Y direction  —  + into scene"),
]

# ─────────────────────────────────────────────────────────────────────────────
# _NodeForm
# ─────────────────────────────────────────────────────────────────────────────

class _NodeForm(QWidget):
    def __init__(self, node: NodeData, load_case: LoadCase | None,
                 on_apply, is_2d: bool = False) -> None:
        super().__init__()
        self._node      = node
        self._load_case = load_case
        self._on_apply  = on_apply
        self._is_2d     = is_2d
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        layout.addWidget(QLabel(f"<b>Node {node.id}</b>"))

        # ── coordinates ──────────────────────────────────────────────────────
        coord_box = QGroupBox("Coordinates")
        form = QFormLayout(coord_box)
        self._x = _spin(node.x, -1000, 1000, 0.25)
        self._y = _spin(node.y, -1000, 1000, 0.25)
        self._z = _spin(node.z, -1000, 1000, 0.25)
        form.addRow("x (m):", self._x)
        form.addRow("y (m) ↑:" if is_2d else "y (m):", self._y)
        if not is_2d:
            form.addRow("z (m):", self._z)
        layout.addWidget(coord_box)

        # ── support ──────────────────────────────────────────────────────────
        sup_box = QGroupBox("Support")
        sup_layout = QVBoxLayout(sup_box)
        self._sup_combo = QComboBox()
        self._sup_names = ["FREE","FIXED","PIN","ROLLER","ROLLER_Y","ROLLER_Z","SPRING"]
        self._sup_combo.addItems(["Free", "Fixed", "Pinned", "Roller (vert)", "Roller (horiz)", "Roller (Z)", "Spring"])
        _cur = node.support_type.name
        _cur_idx = self._sup_names.index(_cur) if _cur in self._sup_names else 0
        self._sup_combo.setCurrentIndex(_cur_idx)
        self._sup_combo.currentIndexChanged.connect(self._toggle_spring)
        sup_layout.addWidget(self._sup_combo)

        self._spring_group = QGroupBox("Spring stiffness")
        sg = QFormLayout(self._spring_group)
        self._kx    = _spin(node.spring_kx,     0, 1e12, 1e5, 0)
        self._ky    = _spin(node.spring_ky,     0, 1e12, 1e5, 0)
        self._kz    = _spin(node.spring_kz,     0, 1e12, 1e5, 0)
        self._kth   = _spin(node.spring_ktheta, 0, 1e12, 1e5, 0)
        self._krx   = _spin(node.spring_krx,    0, 1e12, 1e5, 0)
        self._kry   = _spin(node.spring_kry,    0, 1e12, 1e5, 0)
        sg.addRow("k_x (N/m):",      self._kx)
        sg.addRow("k_y (N/m):",      self._ky)
        sg.addRow("k_z (N/m):",      self._kz)
        sg.addRow("k_θz (N·m/rad):", self._kth)
        sg.addRow("k_rx (N·m/rad):", self._krx)
        sg.addRow("k_ry (N·m/rad):", self._kry)
        sup_layout.addWidget(self._spring_group)
        layout.addWidget(sup_box)
        self._toggle_spring()

        # ── applied loads (read from active load case) ────────────────────────
        nl = load_case.get_node_load(node.id) if load_case else NodeLoad()
        load_box = QGroupBox("Applied load  [active case]")
        lf = QFormLayout(load_box)
        self._fx = _spin(nl.fx / 1e3,     -1e6, 1e6, 1)
        self._fy = _spin(nl.fy / 1e3,     -1e6, 1e6, 1)
        self._fz = _spin(nl.fz / 1e3,     -1e6, 1e6, 1)
        self._m  = _spin(nl.moment / 1e3, -1e6, 1e6, 1)
        self._mx = _spin(nl.moment_x / 1e3, -1e6, 1e6, 1)
        self._my = _spin(nl.moment_y / 1e3, -1e6, 1e6, 1)
        if is_2d:
            # 2D-XY: in-plane only — horizontal Fx, vertical Fy (Y up), moment.
            lf.addRow("Fx (kN) →:", self._fx)
            lf.addRow("Fy (kN) ↓:", self._fy)
            lf.addRow("M (kN·m):",  self._m)
        else:
            lf.addRow("Fx (kN):",   self._fx)
            lf.addRow("Fy (kN):",   self._fy)
            lf.addRow("Fz (kN):",   self._fz)
            lf.addRow("Mz (kN·m):", self._m)
            lf.addRow("Mx (kN·m):", self._mx)
            lf.addRow("My (kN·m):", self._my)
        layout.addWidget(load_box)

        btn = QPushButton("Apply")
        btn.clicked.connect(self._apply)
        layout.addWidget(btn)

    def _toggle_spring(self) -> None:
        is_spring = self._sup_combo.currentText() == "Spring"
        self._spring_group.setVisible(is_spring)

    def _apply(self) -> None:
        node = self._node
        node.x = self._x.value()
        node.y = self._y.value()
        node.z = self._z.value()
        node.support_type  = SupportType[self._sup_names[self._sup_combo.currentIndex()]]
        node.spring_kx     = self._kx.value()
        node.spring_ky     = self._ky.value()
        node.spring_kz     = self._kz.value()
        node.spring_ktheta = self._kth.value()
        node.spring_krx    = self._krx.value()
        node.spring_kry    = self._kry.value()
        if self._load_case is not None:
            self._load_case.set_node_load(node.id, NodeLoad(
                fx=self._fx.value() * 1e3,
                fy=self._fy.value() * 1e3,
                fz=self._fz.value() * 1e3,
                moment=self._m.value() * 1e3,
                moment_x=self._mx.value() * 1e3,
                moment_y=self._my.value() * 1e3,
            ))
        self._on_apply()


# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
# Load summary helper
# ─────────────────────────────────────────────────────────────────────────────

def _load_summary(ml: MemberLoad) -> str:
    """Return a compact one-line description of the non-zero loads in *ml*."""
    parts: list[str] = []
    # Aggregate dist_loads by direction for the summary line
    by_dir: dict[str, tuple[float, float]] = {}
    for dl in ml.dist_loads:
        ws0, we0 = by_dir.get(dl.direction, (0.0, 0.0))
        by_dir[dl.direction] = (ws0 + dl.w_start, we0 + dl.w_end)
    for direction in ("w", "qx", "qy", "qz"):
        if direction not in by_dir:
            continue
        ws, we = by_dir[direction]
        if ws == 0.0 and we == 0.0:
            continue
        ws_k, we_k = ws / 1e3, we / 1e3
        if abs(ws_k - we_k) < 1e-10:
            parts.append(f"{direction}={ws_k:.3g} kN/m")
        else:
            parts.append(f"{direction}={ws_k:.3g}→{we_k:.3g} kN/m")
    if ml.point_loads:
        n = len(ml.point_loads)
        parts.append(f"{n} point load{'s' if n > 1 else ''}")
    if ml.partial_loads:
        n = len(ml.partial_loads)
        parts.append(f"{n} partial load{'s' if n > 1 else ''}")
    return "  ·  ".join(parts) if parts else "—"


def _infer_mat_type(E: float) -> str:
    """Guess material type from Young's modulus for initial Design-tab visibility."""
    if 20e9 <= E <= 45e9:
        return "concrete"
    if 8e9 <= E <= 16e9:
        return "timber"
    return "steel"


_MAT_TYPE_LABELS = {"steel": "fy (MPa):", "concrete": "fck (MPa):", "timber": "fk (MPa):"}

_GAMMA_M0 = 1.0   # EN 1993-1-1 §6.1(1)
# Below this |N_Ed|, a BEAM-family member's axial force is treated as solver
# noise, not a real column-style combined action, and only the bending check
# is shown.
_DESIGN_N_THRESHOLD_N = 50.0   # ~0.05 kN


def _design_bending_row(mat: str, fk: float, W_pl: float, W_el: float,
                        b: float, d: float, As: float, fyk_v: float, M_Ed: float) -> dict:
    """One 'Bending M' capacity-check row (EC2 §6.1 for concrete, EC3 §6.2.5
    plastic/elastic for steel & timber — same formulas the member-properties
    Design tab's live M_Rd preview uses)."""
    if mat == "concrete":
        if b > 0 and d > 0 and As > 0 and fk > 0:
            fcd = fk / 1.5
            fyd = fyk_v / 1.15
            x   = min(As * fyd / (0.8 * b * fcd), d)
            M_Rd = As * fyd * (d - 0.4 * x)
            eta  = (M_Ed / M_Rd * 100) if M_Rd > 0 else None
            status = ("PASS ✓" if eta <= 100.0 else "FAIL ✗") if eta is not None else "N/A"
        else:
            M_Rd, eta, status = 0.0, None, "Set b/d/As"
    else:
        if W_pl > 0:
            M_Rd = fk * W_pl / _GAMMA_M0
        elif W_el > 0:
            M_Rd = fk * W_el / _GAMMA_M0
        else:
            M_Rd = 0.0
        eta = (M_Ed / M_Rd * 100) if M_Rd > 0 else None
        if eta is not None:
            status = "PASS ✓" if eta <= 100.0 else "FAIL ✗"
        elif W_pl == 0 and W_el == 0:
            status = "N/A — set W_pl"
        else:
            status = "N/A"
    return {"check": "Bending M", "demand": M_Ed, "capacity": M_Rd if M_Rd > 0 else None,
            "eta": eta, "status": status, "unit": "kN·m"}


def _design_axial_row(mat: str, fk: float, A: float, As: float, fyk_v: float,
                      N_Ed: float) -> dict:
    """One 'Axial N' capacity-check row. N_Ed sign follows the solver's own
    convention (postprocessor.py): positive = compression, negative = tension.

    Steel — EC3 §6.2.3 cross-section yield (no buckling — same no-buckling
    scope as the bending check above), same capacity either direction.

    Concrete — EC2 §6.1: compression is resisted by the concrete *and* the
    reinforcement together (N_Rd = Ac·fcd + As·fyd); tension is resisted by
    the reinforcement alone (concrete is assumed cracked, N_Rd = As·fyd).
    `As` here is the member's single reinforcement-area field, treated as
    the *total* longitudinal steel for this check (not just one face) — a
    simplification worth knowing about, not a full column interaction check.

    Timber: not implemented, explicit N/A.
    """
    if mat == "timber":
        return {"check": "Axial N", "demand": N_Ed, "capacity": None, "eta": None,
                "status": "N/A — axial check not implemented for timber", "unit": "kN"}

    if mat == "steel":
        label = "Axial N"
        N_Rd = A * fk / _GAMMA_M0 if A > 0 and fk > 0 else 0.0
        not_set_status = "N/A — set A"
    else:   # concrete
        fcd = fk / 1.5 if fk > 0 else 0.0
        fyd = fyk_v / 1.15 if fyk_v > 0 else 0.0
        if N_Ed >= 0.0:
            label = "Axial N (compression)"
            N_Rd = A * fcd + As * fyd
        else:
            label = "Axial N (tension)"
            N_Rd = As * fyd
        not_set_status = "N/A — set As" if As <= 0.0 else "N/A — set A/fck"

    eta = (abs(N_Ed) / N_Rd * 100) if N_Rd > 0 else None
    status = ("PASS ✓" if eta <= 100.0 else "FAIL ✗") if eta is not None else not_set_status
    return {"check": label, "demand": N_Ed, "capacity": N_Rd if N_Rd > 0 else None,
            "eta": eta, "status": status, "unit": "kN"}


def _compute_member_design_rows(
    element_type: ElementType, mat: str, fk: float, A: float,
    W_pl: float, W_el: float, b: float, d: float, As: float, fyk_v: float,
    M_Ed: float, N_Ed: float,
) -> list[dict]:
    """Capacity-check row(s) for one member, chosen by element_type:
      BAR                        -> axial only (a truss bar has no bending stiffness)
      BEAM/PIN_LEFT/PIN_RIGHT,
        negligible axial         -> bending only (today's behaviour)
      BEAM/PIN_LEFT/PIN_RIGHT,
        real combined axial      -> axial + bending, shown as two separate
                                     checks (no combined N+M interaction row —
                                     that would need a buckling-aware EC3 §6.3
                                     check to be meaningful, not just implemented).
    Each dict: {check, demand, capacity, eta (%), status, unit}.
    """
    if element_type == ElementType.BAR:
        return [_design_axial_row(mat, fk, A, As, fyk_v, N_Ed)]

    if abs(N_Ed) <= _DESIGN_N_THRESHOLD_N:
        return [_design_bending_row(mat, fk, W_pl, W_el, b, d, As, fyk_v, M_Ed)]

    return [_design_axial_row(mat, fk, A, As, fyk_v, N_Ed),
           _design_bending_row(mat, fk, W_pl, W_el, b, d, As, fyk_v, M_Ed)]


# ── Shared Design-tab logic (used by _MemberForm & _MultiMemberForm) ──────────
# Bundles the widgets so the M_Rd / visibility logic is written once instead
# of twice with an "_m" suffix — the two forms only differ in which spinboxes
# they wire into the bundle.

@dataclass
class _DesignWidgets:
    form: QFormLayout
    fy: QDoubleSpinBox
    Wpl: QDoubleSpinBox
    Wel: QDoubleSpinBox
    melrd_lbl: QLabel
    b_sec: QDoubleSpinBox
    h_sec: QDoubleSpinBox
    cover: QDoubleSpinBox
    d_lbl: QLabel
    As_t: QDoubleSpinBox
    fyk: QDoubleSpinBox
    mrd_lbl: QLabel


def _design_update_visibility(dw: _DesignWidgets, mat_type: str) -> None:
    """Show concrete section fields or steel/timber W_pl/W_el based on material type."""
    is_conc = (mat_type == "concrete")
    dw.form.setRowVisible(dw.Wpl,       not is_conc)
    dw.form.setRowVisible(dw.Wel,       not is_conc)
    dw.form.setRowVisible(dw.melrd_lbl, not is_conc)
    dw.form.setRowVisible(dw.b_sec,   is_conc)
    dw.form.setRowVisible(dw.h_sec,   is_conc)
    dw.form.setRowVisible(dw.cover,   is_conc)
    dw.form.setRowVisible(dw.d_lbl,   is_conc)
    dw.form.setRowVisible(dw.As_t,    is_conc)
    dw.form.setRowVisible(dw.fyk,     is_conc)
    dw.form.setRowVisible(dw.mrd_lbl, is_conc)


def _design_update_mrd(dw: _DesignWidgets) -> None:
    """Recompute and display M_Rd live from concrete section inputs (EN 1992-1-1 §6.1)."""
    fck = dw.fy.value() * 1e6
    b   = dw.b_sec.value() / 1000
    h   = dw.h_sec.value() / 1000
    c   = dw.cover.value() / 1000
    d   = h - c
    As  = dw.As_t.value() / 1e6
    fyk = dw.fyk.value()  * 1e6
    dw.d_lbl.setText(f"{d * 1000:.0f} mm" if d > 0 else "—")
    if b > 0 and d > 0 and As > 0 and fck > 0:
        fcd = fck / 1.5
        fyd = fyk / 1.15
        x   = min(As * fyd / (0.8 * b * fcd), d)
        mrd = As * fyd * (d - 0.4 * x)
        dw.mrd_lbl.setText(f"{mrd / 1e3:.2f} kN·m")
    else:
        dw.mrd_lbl.setText("—")


def _design_update_melrd(dw: _DesignWidgets) -> None:
    """Live M_Rd for steel / timber — plastic (W_pl) preferred, elastic (W_el) fallback.

    EC3 §6.2.5: M_c,Rd = W_pl × fy / γ_M0  (Class 1/2)
                          W_el × fy / γ_M0  (Class 3)
    γ_M0 = 1.0 per EN 1993-1-1 §6.1(1).
    """
    fy  = dw.fy.value()  * 1e6
    Wpl = dw.Wpl.value() * 1e-6
    Wel = dw.Wel.value() * 1e-6
    gamma_M0 = 1.0
    if Wpl > 0 and fy > 0:
        dw.melrd_lbl.setText(f"{Wpl * fy / gamma_M0 / 1e3:.2f} kN·m  (pl)")
    elif Wel > 0 and fy > 0:
        dw.melrd_lbl.setText(f"{Wel * fy / gamma_M0 / 1e3:.2f} kN·m  (el)")
    else:
        dw.melrd_lbl.setText("—")


# ── Shared distributed-load table logic (used by _MemberForm & _MultiMemberForm) ──

@dataclass
class _DLTableWidgets:
    table: QTableWidget
    model_state: object   # ModelState | None
    active_case_id: int    # fallback case id used for newly-added rows


def _dlt_populate(dw: _DLTableWidgets, member_id: int) -> None:
    """Populate table from all load cases' dist_loads for one member."""
    dw.table.setRowCount(0)
    if not dw.model_state:
        return
    for lc in dw.model_state.load_cases:
        for dl in lc.get_member_load(member_id).dist_loads:
            if dl.direction == "qz":  # hidden from UI
                continue
            _dlt_add_row(dw, lc.id, dl.direction, dl.w_start / 1e3, dl.w_end / 1e3)


def _dlt_add_row(dw: _DLTableWidgets, case_id: int,
                  direction_key: str, ws_kn: float, we_kn: float) -> None:
    row = dw.table.rowCount()
    dw.table.insertRow(row)
    # Case column: dropdown of all load cases — user can reassign here
    case_combo = QComboBox()
    if dw.model_state:
        for lc in dw.model_state.load_cases:
            case_combo.addItem(lc.name, lc.id)
    for i in range(case_combo.count()):
        if case_combo.itemData(i) == case_id:
            case_combo.setCurrentIndex(i)
            break
    dw.table.setCellWidget(row, 0, case_combo)
    # Direction column (read-only, stores direction key in UserRole)
    for dkey, dlabel, dtip in _DL_DIRS:
        if dkey == direction_key:
            di = QTableWidgetItem(dlabel)
            di.setToolTip(dtip)
            di.setFlags(di.flags() & ~Qt.ItemFlag.ItemIsEditable)
            di.setData(Qt.ItemDataRole.UserRole, dkey)
            dw.table.setItem(row, 1, di)
            break
    dw.table.setCellWidget(row, 2, _spin(ws_kn, -1e6, 1e6, 1.0, 2))
    dw.table.setCellWidget(row, 3, _spin(we_kn, -1e6, 1e6, 1.0, 2))


def _dlt_add_entry(dw: _DLTableWidgets, direction: str) -> None:
    """Add a new empty row for the given direction, defaulting to the active case."""
    _dlt_add_row(dw, dw.active_case_id, direction, 0.0, 0.0)


def _dlt_remove_row(dw: _DLTableWidgets) -> None:
    rows = sorted({idx.row() for idx in dw.table.selectedIndexes()}, reverse=True)
    for r in rows:
        dw.table.removeRow(r)
    if not rows and dw.table.rowCount() > 0:
        dw.table.removeRow(dw.table.rowCount() - 1)


# ── Shared section-picker logic (used by _MemberForm & _MultiMemberForm) ──────

def _run_section_picker(parent: QWidget, *, E: QDoubleSpinBox, A: QDoubleSpinBox,
                         I: QDoubleSpinBox, density: QDoubleSpinBox,
                         fy: QDoubleSpinBox, fy_lbl: QLabel,
                         Wpl: QDoubleSpinBox, Wel: QDoubleSpinBox,
                         b_sec: QDoubleSpinBox, h_sec: QDoubleSpinBox,
                         on_material_change, on_done) -> None:
    """Open the section-library picker and push the result into the given
    widgets. on_material_change(mat_type) updates Design-tab visibility;
    on_done() saves immediately, without an extra Apply click."""
    from ui_qt.section_picker import SectionPickerDialog
    dlg = SectionPickerDialog(
        current_E=E.value() * 1e9, current_A=A.value(), current_I=I.value() * 1e-6,
        parent=parent,
    )
    if not (dlg.exec() and dlg.get_result()):
        return
    E_val, A_val, I_val, W_pl, W_el, b, h, density_val, fy_val, mat_type = dlg.get_result()
    E.setValue(E_val / 1e9)
    A.setValue(A_val)
    I.setValue(I_val * 1e6)
    density.setValue(density_val)
    fy.setValue(fy_val / 1e6)
    if W_pl > 0:
        Wpl.setValue(W_pl * 1e6)
    if W_el > 0:
        Wel.setValue(W_el * 1e6)
    if b > 0:
        b_sec.setValue(b * 1000)   # m → mm
    if h > 0:
        h_sec.setValue(h * 1000)   # m → mm
    fy_lbl.setText(_MAT_TYPE_LABELS.get(mat_type, "fy (MPa):"))
    on_material_change(mat_type)
    on_done()


# _MemberForm
# ─────────────────────────────────────────────────────────────────────────────

class _MemberForm(QWidget):
    def __init__(self, member: MemberData, model_state,
                 on_apply, divide_callback=None) -> None:
        super().__init__()
        self._member          = member
        self._model_state     = model_state
        self._load_case       = model_state.active_case if model_state else None
        self._on_apply        = on_apply
        self._divide_callback = divide_callback
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        layout.addWidget(QLabel(f"<b>Member {member.id}</b> (nodes {member.node_i}→{member.node_j})"))

        # ── current-properties read-out (reflects the saved state) ─────────────
        summary_box = QGroupBox("Current properties")
        _sm = QVBoxLayout(summary_box)
        self._summary_lbl = QLabel(_member_summary_html(member))
        self._summary_lbl.setTextFormat(Qt.TextFormat.RichText)
        _sm.addWidget(self._summary_lbl)
        layout.addWidget(summary_box)

        tabs = QTabWidget()

        # ══ Tab 1 — Section ══════════════════════════════════════════════════
        _sec_tab = QWidget()
        _sl = QVBoxLayout(_sec_tab)
        _sl.setAlignment(Qt.AlignmentFlag.AlignTop)

        type_box = QGroupBox("Element type")
        tf = QFormLayout(type_box)
        self._type_combo = QComboBox()
        self._type_combo.addItems(["Beam", "Bar", "Pin-Left", "Pin-Right"])
        type_names = ["BEAM","BAR","PIN_LEFT","PIN_RIGHT"]
        self._type_combo.setCurrentIndex(type_names.index(member.element_type.name))
        tf.addRow("Type:", self._type_combo)
        self._group = QLineEdit(member.group)
        self._group.setPlaceholderText("e.g. Column, Rafter, Diagonal…")
        self._group.setToolTip(
            "Free-form label — used by 'Colour by Group' (Ctrl+G) and reporting.")
        tf.addRow("Group:", self._group)
        _sl.addWidget(type_box)

        sec_box = QGroupBox("Section properties")
        sf = QFormLayout(sec_box)
        self._E    = _spin(member.E / 1e9,        0, 1000,   1,    1)
        self._A    = _spin(member.A,               0, 100,    0.001, 6)
        self._I    = _spin(member.I * 1e6,         0, 1e6,    1,    2)
        _Iy_val    = member.I_y if member.I_y is not None else member.I
        self._Iy   = _spin(_Iy_val * 1e6,          0, 1e6,    1,    2)
        self._J    = _spin(member.J * 1e6,         0, 1e6,    0.01, 3)
        self._beta = _spin(math.degrees(member.beta_angle), -180.0, 180.0, 5.0, 1)
        sf.addRow("E (GPa):",         self._E)
        sf.addRow("A (m²):",          self._A)
        sf.addRow("I_z (×10⁻⁶ m⁴):", self._I)
        sf.addRow("I_y (×10⁻⁶ m⁴):", self._Iy)
        sf.addRow("J (×10⁻⁶ m⁴):",   self._J)
        _beta_w = QWidget()
        _beta_l = QHBoxLayout(_beta_w)
        _beta_l.setContentsMargins(0, 0, 0, 0)
        _beta_l.setSpacing(4)
        _beta_l.addWidget(self._beta)
        for _lbl, _delta in [("−90°", -90.0), ("+90°", +90.0)]:
            _b = QPushButton(_lbl)
            _b.setFixedSize(42, 24)
            _b.clicked.connect(lambda _c=False, d=_delta: self._beta.setValue(
                max(-180.0, min(180.0, self._beta.value() + d))
            ))
            _beta_l.addWidget(_b)
        sf.addRow("β angle (°):",     _beta_w)
        _pick_btn = QPushButton("Pick from library...")
        _pick_btn.clicked.connect(self._pick_section)
        sf.addRow("", _pick_btn)

        self._density = _spin(member.density, 0, 20000, 50, 0)
        self._density.setToolTip("0 = no self-weight contribution from this member")
        sf.addRow("Density (kg/m³):", self._density)

        _sl.addWidget(sec_box)

        mesh_box = QGroupBox("Analysis mesh")
        mf = QFormLayout(mesh_box)
        self._nsub = QSpinBox()
        self._nsub.setRange(1, 100)
        self._nsub.setValue(member.n_sub)
        self._nsub.setToolTip("Number of sub-elements for analysis (more = better deformed shape)")
        mf.addRow("Sub-elements:", self._nsub)
        _sl.addWidget(mesh_box)

        tabs.addTab(_sec_tab, "Section")

        # ══ Tab 2 — Loads ════════════════════════════════════════════════════
        _ld_tab = QWidget()
        _ll = QVBoxLayout(_ld_tab)
        _ll.setAlignment(Qt.AlignmentFlag.AlignTop)

        dl_box = QGroupBox("Distributed loads")
        dl_layout = QVBoxLayout(dl_box)
        self._dl_table = QTableWidget(0, 4)
        self._dl_table.setHorizontalHeaderLabels(
            ["Case", "Direction", "w start (kN/m)", "w end (kN/m)"]
        )
        hh = self._dl_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._dl_table.verticalHeader().setVisible(False)
        self._dl_table.setFixedHeight(120)
        _active_id = self._load_case.id if self._load_case else (
            self._model_state.load_cases[0].id
            if self._model_state and self._model_state.load_cases else 0
        )
        self._dlw = _DLTableWidgets(table=self._dl_table, model_state=self._model_state,
                                     active_case_id=_active_id)
        self._dl_populate()
        dl_layout.addWidget(self._dl_table)
        dl_btn_row = QHBoxLayout()
        for _key, _lbl in [("w", "+ Local w"), ("qx", "+ qx"), ("qy", "+ qy")]:
            _b = QPushButton(_lbl)
            _b.setFixedHeight(28)
            _b.clicked.connect(lambda checked=False, k=_key: self._dl_add_entry(k))
            dl_btn_row.addWidget(_b)
        _rm = QPushButton("Remove")
        _rm.setFixedHeight(28)
        _rm.clicked.connect(self._dl_remove_row)
        dl_btn_row.addWidget(_rm)
        dl_layout.addLayout(dl_btn_row)
        _ll.addWidget(dl_box)

        ml = self._load_case.get_member_load(member.id) if self._load_case else MemberLoad()

        pl_box = QGroupBox("Point loads  [active case]")
        pl_layout = QVBoxLayout(pl_box)
        self._pl_table = QTableWidget(0, 3)
        self._pl_table.setHorizontalHeaderLabels(["Type", "Pos (0–1)", "Value (kN or kN·m)"])
        self._pl_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._pl_table.setFixedHeight(120)
        for pl in ml.point_loads:
            self._add_pl_row(pl.load_type, pl.position, pl.magnitude / 1e3)
        pl_layout.addWidget(self._pl_table)
        pl_btn_row = QHBoxLayout()
        btn_add_f = QPushButton("+ Force")
        btn_add_m = QPushButton("+ Moment")
        btn_del   = QPushButton("Remove")
        for _pb in (btn_add_f, btn_add_m, btn_del):
            _pb.setFixedHeight(28)
        btn_add_f.clicked.connect(lambda: self._add_pl_row("FORCE",  0.5, 0.0))
        btn_add_m.clicked.connect(lambda: self._add_pl_row("MOMENT", 0.5, 0.0))
        btn_del.clicked.connect(self._remove_pl_row)
        pl_btn_row.addWidget(btn_add_f)
        pl_btn_row.addWidget(btn_add_m)
        pl_btn_row.addWidget(btn_del)
        pl_layout.addLayout(pl_btn_row)
        _ll.addWidget(pl_box)

        pdl_box = QGroupBox("Partial distributed loads  [active case]")
        pdl_layout = QVBoxLayout(pdl_box)
        self._pdl_table = QTableWidget(0, 4)
        self._pdl_table.setHorizontalHeaderLabels(
            ["Start (0–1)", "End (0–1)", "w start (kN/m)", "w end (kN/m)"]
        )
        self._pdl_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._pdl_table.setFixedHeight(120)
        for pdl in ml.partial_loads:
            self._add_pdl_row(pdl.start_pos, pdl.end_pos,
                              pdl.w_start / 1e3, pdl.w_end / 1e3)
        pdl_layout.addWidget(self._pdl_table)
        pdl_btn_row = QHBoxLayout()
        btn_add_pdl = QPushButton("+ Partial load")
        btn_del_pdl = QPushButton("Remove")
        for _pb in (btn_add_pdl, btn_del_pdl):
            _pb.setFixedHeight(28)
        btn_add_pdl.clicked.connect(lambda: self._add_pdl_row(0.25, 0.75, 0.0, 0.0))
        btn_del_pdl.clicked.connect(self._remove_pdl_row)
        pdl_btn_row.addWidget(btn_add_pdl)
        pdl_btn_row.addWidget(btn_del_pdl)
        pdl_layout.addLayout(pdl_btn_row)
        _ll.addWidget(pdl_box)

        tabs.addTab(_ld_tab, "Loads")

        # ══ Tab 3 — Design ═══════════════════════════════════════════════════
        _ds_tab = QWidget()
        _dl2 = QVBoxLayout(_ds_tab)
        _dl2.setAlignment(Qt.AlignmentFlag.AlignTop)

        design_box = QGroupBox("Design properties")
        self._design_form = QFormLayout(design_box)
        df = self._design_form

        # ── Characteristic strength (label updates with material) ─────────────
        self._fy     = _spin(member.fy / 1e6,    0, 2000, 5,   0)
        self._fy_lbl = QLabel("fy (MPa):")
        df.addRow(self._fy_lbl, self._fy)

        # ── Steel / timber: section moduli ────────────────────────────────────
        self._Wpl = _spin(member.W_pl * 1e6, 0, 1e6, 0.1, 1)
        self._Wel = _spin(member.W_el * 1e6, 0, 1e6, 0.1, 1)
        df.addRow("W_pl (cm³):", self._Wpl)
        df.addRow("W_el (cm³):", self._Wel)
        self._melrd_lbl = QLabel("—")
        self._melrd_lbl.setStyleSheet("color:#00cccc; font-weight:bold;")
        df.addRow("M_Rd (kN·m):", self._melrd_lbl)

        # ── Concrete: section geometry (EN 1992-1-1 §6.1) ────────────────────
        self._b_sec = _spin(member.b_sec * 1000, 0, 5000, 10, 0)
        self._h_sec = _spin(member.h_sec * 1000, 0, 5000, 10, 0)
        # Cover: derive from stored h and d if available, else default 50 mm
        _h_mm = member.h_sec * 1000
        _d_mm = member.d_eff * 1000
        _cov0 = round(_h_mm - _d_mm) if (_h_mm > 0 and _d_mm > 0) else 50
        self._cover = _spin(_cov0, 0, 500, 5, 0)
        self._d_lbl = QLabel("—")
        self._d_lbl.setStyleSheet("color:#aaaaaa; font-size:10px;")
        self._As_t  = _spin(member.As_tension * 1e6, 0, 100000, 50, 0)
        self._fyk   = _spin(member.fyk / 1e6,  200, 1000, 10, 0)
        df.addRow("b (mm):",      self._b_sec)
        df.addRow("h (mm):",      self._h_sec)
        df.addRow("Cover c (mm):", self._cover)
        df.addRow("d = h−c (mm):", self._d_lbl)
        df.addRow("As (mm²):",    self._As_t)
        df.addRow("fyk (MPa):",   self._fyk)
        self._mrd_lbl = QLabel("—")
        self._mrd_lbl.setStyleSheet("color:#00cccc; font-weight:bold;")
        df.addRow("M_Rd (kN·m):", self._mrd_lbl)

        self._dw = _DesignWidgets(
            form=self._design_form, fy=self._fy, Wpl=self._Wpl, Wel=self._Wel,
            melrd_lbl=self._melrd_lbl, b_sec=self._b_sec, h_sec=self._h_sec,
            cover=self._cover, d_lbl=self._d_lbl, As_t=self._As_t, fyk=self._fyk,
            mrd_lbl=self._mrd_lbl,
        )

        # Connect concrete fields to live M_Rd display
        for _w in (self._fy, self._b_sec, self._h_sec, self._cover,
                   self._As_t, self._fyk):
            _w.valueChanged.connect(self._update_mrd_display)

        # Connect steel/timber fields to live M_Rd display (plastic preferred)
        for _w in (self._fy, self._Wpl, self._Wel):
            _w.valueChanged.connect(self._update_melrd_display)

        _dl2.addWidget(design_box)
        tabs.addTab(_ds_tab, "Design")

        # Sync visibility + label with detected material
        _mat_type = _infer_mat_type(member.E)
        self._fy_lbl.setText(_MAT_TYPE_LABELS.get(_mat_type, "fy (MPa):"))
        self._update_design_visibility(_mat_type)
        self._update_mrd_display()
        self._update_melrd_display()

        layout.addWidget(tabs)

        # ── Divide — split this member into multiple real elements ───────────
        if self._divide_callback is not None:
            div_box = QGroupBox("Divide into elements")
            div_layout = QHBoxLayout(div_box)
            div_layout.setSpacing(4)
            # label, n_divisions (= intermediate nodes + 1)
            for _lbl, _ndiv in [("Halve", 2), ("5 nodes", 6), ("10 nodes", 11)]:
                _b = QPushButton(_lbl)
                _b.setFixedHeight(28)
                _b.setToolTip(f"Split into {_ndiv} elements")
                _b.clicked.connect(
                    lambda _c=False, n=_ndiv: self._divide_callback(self._member.id, n)
                )
                div_layout.addWidget(_b)
            _bc = QPushButton("Custom…")
            _bc.setFixedHeight(28)
            _bc.clicked.connect(self._divide_custom)
            div_layout.addWidget(_bc)
            layout.addWidget(div_box)

        btn = QPushButton("Apply")
        btn.clicked.connect(self._apply)
        layout.addWidget(btn)

    def _divide_custom(self) -> None:
        """Prompt for an element count, then divide the member into that many."""
        from PyQt6.QtWidgets import QInputDialog
        n, ok = QInputDialog.getInt(
            self, "Divide Member", "Number of elements:",
            value=4, min=2, max=100,
        )
        if ok and self._divide_callback is not None:
            self._divide_callback(self._member.id, n)

    def _update_design_visibility(self, mat_type: str) -> None:
        _design_update_visibility(self._dw, mat_type)

    def _update_mrd_display(self, _val: float = 0.0) -> None:
        _design_update_mrd(self._dw)

    def _update_melrd_display(self, _val: float = 0.0) -> None:
        _design_update_melrd(self._dw)

    def _pick_section(self) -> None:
        _run_section_picker(
            self, E=self._E, A=self._A, I=self._I, density=self._density,
            fy=self._fy, fy_lbl=self._fy_lbl, Wpl=self._Wpl, Wel=self._Wel,
            b_sec=self._b_sec, h_sec=self._h_sec,
            on_material_change=self._update_design_visibility, on_done=self._apply,
        )

    def _add_pl_row(self, load_type: str, position: float, magnitude_kn: float) -> None:
        row = self._pl_table.rowCount()
        self._pl_table.insertRow(row)
        combo = QComboBox()
        combo.addItems(["Force ↓", "Moment ↺"])
        combo.setCurrentIndex(0 if load_type == "FORCE" else 1)
        self._pl_table.setCellWidget(row, 0, combo)
        pos_spin = _spin(position, 0.0, 1.0, 0.05, 2)
        self._pl_table.setCellWidget(row, 1, pos_spin)
        val_spin = _spin(magnitude_kn, -1e6, 1e6, 1.0, 2)
        self._pl_table.setCellWidget(row, 2, val_spin)

    def _remove_pl_row(self) -> None:
        rows = sorted({idx.row() for idx in self._pl_table.selectedIndexes()}, reverse=True)
        for r in rows:
            self._pl_table.removeRow(r)
        if not rows and self._pl_table.rowCount() > 0:
            self._pl_table.removeRow(self._pl_table.rowCount() - 1)

    # ── distributed loads table helpers ──────────────────────────────────────

    def _dl_populate(self) -> None:
        _dlt_populate(self._dlw, self._member.id)

    def _dl_add_entry(self, direction: str) -> None:
        _dlt_add_entry(self._dlw, direction)

    def _dl_remove_row(self) -> None:
        _dlt_remove_row(self._dlw)

    def _dl_add_row(self, case_id: int,
                    direction_key: str, ws_kn: float, we_kn: float) -> None:
        _dlt_add_row(self._dlw, case_id, direction_key, ws_kn, we_kn)

    def _add_pdl_row(self, start: float, end: float,
                     w_start_kn: float, w_end_kn: float) -> None:
        row = self._pdl_table.rowCount()
        self._pdl_table.insertRow(row)
        self._pdl_table.setCellWidget(row, 0, _spin(start,    0.0, 1.0, 0.05, 2))
        self._pdl_table.setCellWidget(row, 1, _spin(end,      0.0, 1.0, 0.05, 2))
        self._pdl_table.setCellWidget(row, 2, _spin(w_start_kn, -1e6, 1e6, 1.0, 2))
        self._pdl_table.setCellWidget(row, 3, _spin(w_end_kn,   -1e6, 1e6, 1.0, 2))

    def _remove_pdl_row(self) -> None:
        rows = sorted({idx.row() for idx in self._pdl_table.selectedIndexes()}, reverse=True)
        for r in rows:
            self._pdl_table.removeRow(r)
        if not rows and self._pdl_table.rowCount() > 0:
            self._pdl_table.removeRow(self._pdl_table.rowCount() - 1)

    def _apply(self) -> None:
        m = self._member
        type_names = ["BEAM","BAR","PIN_LEFT","PIN_RIGHT"]
        m.element_type = ElementType[type_names[self._type_combo.currentIndex()]]
        m.group   = self._group.text().strip()
        m.E       = self._E.value() * 1e9
        m.A       = self._A.value()
        m.I       = self._I.value() * 1e-6
        m.I_y     = self._Iy.value() * 1e-6
        m.J       = self._J.value() * 1e-6
        m.beta_angle = math.radians(self._beta.value())
        m.density = self._density.value()
        m.n_sub   = self._nsub.value()
        m.fy      = self._fy.value() * 1e6
        m.W_pl    = self._Wpl.value() * 1e-6
        m.W_el    = self._Wel.value() * 1e-6
        m.b_sec       = self._b_sec.value() / 1000
        m.h_sec       = self._h_sec.value() / 1000
        m.d_eff       = (self._h_sec.value() - self._cover.value()) / 1000
        m.As_tension  = self._As_t.value()  / 1e6
        m.fyk         = self._fyk.value()   * 1e6
        m.reinforcement_estimated = False   # user has now reviewed/set it directly
        if self._load_case is not None:
            # ── point loads (active case) ─────────────────────────────────────
            point_loads = []
            for row in range(self._pl_table.rowCount()):
                combo    = self._pl_table.cellWidget(row, 0)
                pos_spin = self._pl_table.cellWidget(row, 1)
                val_spin = self._pl_table.cellWidget(row, 2)
                lt = "FORCE" if combo.currentIndex() == 0 else "MOMENT"
                point_loads.append(PointLoadData(
                    load_type=lt,
                    position=pos_spin.value(),
                    magnitude=val_spin.value() * 1e3,
                ))

            # ── partial loads (active case) ───────────────────────────────────
            partial_loads = []
            for row in range(self._pdl_table.rowCount()):
                s_spin  = self._pdl_table.cellWidget(row, 0)
                e_spin  = self._pdl_table.cellWidget(row, 1)
                ws_spin = self._pdl_table.cellWidget(row, 2)
                we_spin = self._pdl_table.cellWidget(row, 3)
                start = max(0.0, min(1.0, s_spin.value()))
                end   = max(0.0, min(1.0, e_spin.value()))
                if end > start + 1e-6:
                    partial_loads.append(PartialDistLoad(
                        start_pos=start, end_pos=end,
                        w_start=ws_spin.value() * 1e3,
                        w_end=we_spin.value()   * 1e3,
                    ))

            # ── distributed loads (all cases from table) ──────────────────────
            case_dls: dict[int, list[DistLoad]] = {}
            for row in range(self._dl_table.rowCount()):
                case_combo = self._dl_table.cellWidget(row, 0)
                di   = self._dl_table.item(row, 1)
                ws   = self._dl_table.cellWidget(row, 2)
                we   = self._dl_table.cellWidget(row, 3)
                if case_combo and di and ws and we:
                    cid = case_combo.currentData()
                    case_dls.setdefault(cid, []).append(DistLoad(
                        direction=di.data(Qt.ItemDataRole.UserRole),
                        w_start=ws.value() * 1e3,
                        w_end=we.value()   * 1e3,
                    ))

            active_id = self._load_case.id if self._load_case else -1
            for lc in self._model_state.load_cases:
                old_ml = lc.get_member_load(m.id)
                dls = case_dls.get(lc.id, [])
                if lc.id == active_id:
                    lc.set_member_load(m.id, MemberLoad(
                        dist_loads=dls,
                        point_loads=point_loads,
                        partial_loads=partial_loads,
                    ))
                else:
                    lc.set_member_load(m.id, MemberLoad(
                        dist_loads=dls,
                        point_loads=old_ml.point_loads,
                        partial_loads=old_ml.partial_loads,
                    ))
        # Refresh the read-out so it reflects the just-saved values (confirms
        # the change landed, even when "Colour by Group" masks the line colour).
        self._summary_lbl.setText(_member_summary_html(m))
        self._on_apply()


# ─────────────────────────────────────────────────────────────────────────────
# _MixedFilterForm
# ─────────────────────────────────────────────────────────────────────────────

_SECTION_LOOKUP_CACHE: dict[tuple[float, float], str] | None = None


def _build_section_lookup() -> dict[tuple[float, float], str]:
    """Return {(rounded_A, rounded_I): profile_name} from the section library.

    The section library is static, so the lookup is built once and cached.
    Robust to STEEL_PROFILES entries carrying extra columns (e.g. W_pl, W_el):
    only the first three (name, A, I) are read.
    """
    global _SECTION_LOOKUP_CACHE
    if _SECTION_LOOKUP_CACHE is not None:
        return _SECTION_LOOKUP_CACHE
    lookup: dict[tuple[float, float], str] = {}
    try:
        from ui_qt.section_library import STEEL_PROFILES
        for _series, profiles in STEEL_PROFILES.items():
            for entry in profiles:
                name, A, I = entry[0], entry[1], entry[2]
                lookup[(round(A, 8), round(I, 12))] = name
    except Exception:
        lookup = {}
    _SECTION_LOOKUP_CACHE = lookup
    return lookup


class _MixedFilterForm(QWidget):
    """Shown when the window selection contains both nodes and members.

    Presents filter buttons so the user can narrow the selection to a single
    homogeneous group before editing properties.
    """

    def __init__(self, nodes: list, members: list, on_filter) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setSpacing(6)

        hdr = QLabel(
            f"<b>Mixed selection</b><br>"
            f"<small>{len(nodes)} node(s)  ·  {len(members)} member(s)<br>"
            "Click a filter to narrow the selection.</small>"
        )
        hdr.setWordWrap(True)
        layout.addWidget(hdr)

        # ── Nodes ─────────────────────────────────────────────────────────────
        if nodes:
            node_box = QGroupBox("Nodes")
            row = QHBoxLayout(node_box)
            row.setSpacing(4)

            all_node_ids = {n.id for n in nodes}
            btn_all = QPushButton(f"All nodes  ({len(nodes)})")
            btn_all.clicked.connect(lambda: on_filter(all_node_ids, set()))
            row.addWidget(btn_all)

            supported = [n for n in nodes if n.support_type != SupportType.FREE]
            if supported:
                sup_ids = {n.id for n in supported}
                btn_sup = QPushButton(f"Supports  ({len(supported)})")
                btn_sup.clicked.connect(lambda: on_filter(sup_ids, set()))
                row.addWidget(btn_sup)

            row.addStretch()
            layout.addWidget(node_box)

        # ── Element type ───────────────────────────────────────────────────────
        if members:
            type_box = QGroupBox("Element type")
            type_row = QHBoxLayout(type_box)
            type_row.setSpacing(4)

            _type_labels = {
                ElementType.BEAM:      "Beam",
                ElementType.BAR:       "Bar",
                ElementType.PIN_LEFT:  "Pin-Left",
                ElementType.PIN_RIGHT: "Pin-Right",
            }
            by_type: dict[ElementType, list] = {}
            for m in members:
                by_type.setdefault(m.element_type, []).append(m)

            for etype, label in _type_labels.items():
                grp = by_type.get(etype)
                if not grp:
                    continue
                ids = {m.id for m in grp}
                btn = QPushButton(f"{label}  ({len(grp)})")
                btn.clicked.connect(lambda checked, _ids=ids: on_filter(set(), _ids))
                type_row.addWidget(btn)

            type_row.addStretch()
            layout.addWidget(type_box)

            # ── Section profile ────────────────────────────────────────────────
            def _pkey(m: MemberData) -> tuple[float, float]:
                return (round(m.A, 8), round(m.I, 12))

            by_profile: dict[tuple[float, float], list] = {}
            for m in members:
                by_profile.setdefault(_pkey(m), []).append(m)

            if len(by_profile) > 1 or (len(by_profile) == 1 and nodes):
                sec_box = QGroupBox("Section profile")
                sec_layout = QVBoxLayout(sec_box)
                sec_layout.setSpacing(3)
                lookup = _build_section_lookup()

                for idx, (key, grp) in enumerate(
                    sorted(by_profile.items(), key=lambda kv: -kv[0][0]), start=1
                ):
                    name = lookup.get(key, f"Profile {idx}")
                    ids = {m.id for m in grp}
                    tip = (f"A = {key[0] * 1e4:.2f} cm²  "
                           f"I = {key[1] * 1e8:.2f} cm⁴")
                    btn_row = QHBoxLayout()
                    btn_p = QPushButton(f"{name}  ({len(grp)})")
                    btn_p.setToolTip(tip)
                    btn_p.clicked.connect(lambda checked, _ids=ids: on_filter(set(), _ids))
                    btn_row.addWidget(btn_p)
                    btn_row.addStretch()
                    sec_layout.addLayout(btn_row)

                layout.addWidget(sec_box)

        layout.addStretch()


# ─────────────────────────────────────────────────────────────────────────────
# _MultiMemberForm
# ─────────────────────────────────────────────────────────────────────────────

class _MultiMemberForm(QWidget):
    """Edit shared properties across multiple selected members at once."""

    def __init__(self, members: list, model_state,
                 on_apply) -> None:
        super().__init__()
        self._members     = members
        self._model_state = model_state
        self._load_case   = model_state.active_case if model_state else None
        self._on_apply    = on_apply
        first = members[0]

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        hdr = QLabel(f"<b>{len(members)} members selected</b>  "
                     "<small style='color:#888'>— edits apply to all</small>")
        hdr.setWordWrap(True)
        root.addWidget(hdr)

        summary_box = QGroupBox("Current selection")
        _sm = QVBoxLayout(summary_box)
        self._summary_lbl = QLabel(_multi_member_summary_html(members))
        self._summary_lbl.setTextFormat(Qt.TextFormat.RichText)
        _sm.addWidget(self._summary_lbl)
        root.addWidget(summary_box)

        tabs = QTabWidget()
        root.addWidget(tabs)

        # ── Section tab ───────────────────────────────────────────────────────
        sec_w = QWidget()
        sec_l = QVBoxLayout(sec_w)
        sec_l.setAlignment(Qt.AlignmentFlag.AlignTop)
        tabs.addTab(sec_w, "Section")

        type_box = QGroupBox("Element type")
        tf = QFormLayout(type_box)
        self._type_combo = QComboBox()
        self._type_combo.addItems(["Beam", "Bar", "Pin-Left", "Pin-Right"])
        type_names = ["BEAM", "BAR", "PIN_LEFT", "PIN_RIGHT"]
        all_same_type = all(m.element_type == first.element_type for m in members)
        self._type_combo.setCurrentIndex(
            type_names.index(first.element_type.name) if all_same_type else 0
        )
        tf.addRow("Type:", self._type_combo)
        self._group_m = QLineEdit(first.group)
        self._group_m.setPlaceholderText("e.g. Column, Rafter, Diagonal…")
        self._group_m.setToolTip(
            "Free-form label — used by 'Colour by Group' (Ctrl+G) and reporting.\n"
            "Applies to every selected member.")
        tf.addRow("Group:", self._group_m)
        sec_l.addWidget(type_box)

        sec_box = QGroupBox("Section properties")
        sf = QFormLayout(sec_box)
        self._E = _spin(first.E / 1e9, 0, 1000, 1, 1)
        self._A = _spin(first.A,       0, 100,  0.001, 6)
        self._I = _spin(first.I * 1e6, 0, 1e6,  1, 2)
        sf.addRow("E (GPa):",        self._E)
        sf.addRow("A (m²):",         self._A)
        sf.addRow("I (×10⁻⁶ m⁴):",  self._I)
        pick_btn = QPushButton("Pick from library...")
        pick_btn.clicked.connect(self._pick_section)
        sf.addRow("", pick_btn)

        self._density = _spin(first.density, 0, 20000, 50, 0)
        self._density.setToolTip("0 = no self-weight contribution from this member")
        sf.addRow("Density (kg/m³):", self._density)

        self._nsub = QSpinBox()
        self._nsub.setRange(1, 100)
        self._nsub.setValue(first.n_sub)
        sf.addRow("Sub-elements:", self._nsub)
        sec_l.addWidget(sec_box)

        # ── Loads tab ─────────────────────────────────────────────────────────
        load_w = QWidget()
        load_l = QVBoxLayout(load_w)
        load_l.setAlignment(Qt.AlignmentFlag.AlignTop)
        tabs.addTab(load_w, "Loads")

        dl_box = QGroupBox("Distributed loads")
        dl_layout = QVBoxLayout(dl_box)
        self._dl_table_m = QTableWidget(0, 4)
        self._dl_table_m.setHorizontalHeaderLabels(
            ["Case", "Direction", "w start (kN/m)", "w end (kN/m)"]
        )
        hh_m = self._dl_table_m.horizontalHeader()
        hh_m.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh_m.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh_m.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hh_m.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._dl_table_m.verticalHeader().setVisible(False)
        self._dl_table_m.setFixedHeight(120)
        _active_id_m = self._load_case.id if self._load_case else (
            self._model_state.load_cases[0].id
            if self._model_state and self._model_state.load_cases else 0
        )
        self._dlw = _DLTableWidgets(table=self._dl_table_m, model_state=self._model_state,
                                     active_case_id=_active_id_m)
        self._dl_populate_m()
        dl_layout.addWidget(self._dl_table_m)
        dl_btn_row = QHBoxLayout()
        for _key, _lbl in [("w", "+ Local w"), ("qx", "+ qx"), ("qy", "+ qy")]:
            _b = QPushButton(_lbl)
            _b.setFixedHeight(28)
            _b.clicked.connect(lambda checked=False, k=_key: self._dl_add_entry_m(k))
            dl_btn_row.addWidget(_b)
        _rm_m = QPushButton("Remove")
        _rm_m.setFixedHeight(28)
        _rm_m.clicked.connect(self._dl_remove_row_m)
        dl_btn_row.addWidget(_rm_m)
        dl_layout.addLayout(dl_btn_row)
        load_l.addWidget(dl_box)

        # ── Design tab ────────────────────────────────────────────────────────
        des_w = QWidget()
        des_l = QVBoxLayout(des_w)
        des_l.setAlignment(Qt.AlignmentFlag.AlignTop)
        tabs.addTab(des_w, "Design")

        des_box = QGroupBox("Section capacity")
        self._design_form_m = QFormLayout(des_box)
        self._fy_lbl_m = QLabel("fy (MPa):")
        self._fy_m  = _spin(first.fy / 1e6,   0, 2000, 5, 0)
        self._Wpl_m = _spin(first.W_pl * 1e6, 0, 1e6, 10, 1)
        self._Wel_m = _spin(first.W_el * 1e6, 0, 1e6, 10, 1)
        self._design_form_m.addRow(self._fy_lbl_m, self._fy_m)
        self._design_form_m.addRow("W_pl (cm³):", self._Wpl_m)
        self._design_form_m.addRow("W_el (cm³):", self._Wel_m)
        self._melrd_lbl_m = QLabel("—")
        self._melrd_lbl_m.setStyleSheet("color:#00cccc; font-weight:bold;")
        self._design_form_m.addRow("M_Rd (kN·m):", self._melrd_lbl_m)

        self._b_sec_m = _spin(first.b_sec * 1000,       0, 5000,   10, 0)
        self._h_sec_m = _spin(first.h_sec * 1000,       0, 5000,   10, 0)
        _h_mm_m = first.h_sec * 1000
        _d_mm_m = first.d_eff * 1000
        _cov0_m = round(_h_mm_m - _d_mm_m) if (_h_mm_m > 0 and _d_mm_m > 0) else 50
        self._cover_m = _spin(_cov0_m, 0, 500, 5, 0)
        self._d_lbl_m = QLabel("—")
        self._d_lbl_m.setStyleSheet("color:#aaaaaa; font-size:10px;")
        self._As_t_m  = _spin(first.As_tension * 1e6,   0, 100000, 50, 0)
        self._fyk_m   = _spin(first.fyk / 1e6,        200, 1000,   10, 0)
        self._design_form_m.addRow("b (mm):",       self._b_sec_m)
        self._design_form_m.addRow("h (mm):",       self._h_sec_m)
        self._design_form_m.addRow("Cover c (mm):", self._cover_m)
        self._design_form_m.addRow("d = h−c (mm):", self._d_lbl_m)
        self._design_form_m.addRow("As (mm²):",     self._As_t_m)
        self._design_form_m.addRow("fyk (MPa):",    self._fyk_m)
        self._mrd_lbl_m = QLabel("—")
        self._mrd_lbl_m.setStyleSheet("color:#00cccc; font-weight:bold;")
        self._design_form_m.addRow("M_Rd (kN·m):", self._mrd_lbl_m)
        des_l.addWidget(des_box)

        self._dw = _DesignWidgets(
            form=self._design_form_m, fy=self._fy_m, Wpl=self._Wpl_m, Wel=self._Wel_m,
            melrd_lbl=self._melrd_lbl_m, b_sec=self._b_sec_m, h_sec=self._h_sec_m,
            cover=self._cover_m, d_lbl=self._d_lbl_m, As_t=self._As_t_m, fyk=self._fyk_m,
            mrd_lbl=self._mrd_lbl_m,
        )

        for _w in (self._fy_m, self._b_sec_m, self._h_sec_m,
                   self._cover_m, self._As_t_m, self._fyk_m):
            _w.valueChanged.connect(self._update_mrd_display_m)

        for _w in (self._fy_m, self._Wpl_m, self._Wel_m):
            _w.valueChanged.connect(self._update_melrd_display_m)

        _mat_type_m = _infer_mat_type(first.E)
        self._fy_lbl_m.setText(_MAT_TYPE_LABELS.get(_mat_type_m, "fy (MPa):"))
        self._update_design_visibility_m(_mat_type_m)
        self._update_mrd_display_m()
        self._update_melrd_display_m()

        # ── Apply button ──────────────────────────────────────────────────────
        btn = QPushButton(f"Apply to all {len(members)} members")
        btn.clicked.connect(self._apply)
        root.addWidget(btn)

    def _update_design_visibility_m(self, mat_type: str = "steel") -> None:
        _design_update_visibility(self._dw, mat_type)

    def _update_mrd_display_m(self, _val: float = 0.0) -> None:
        _design_update_mrd(self._dw)

    def _update_melrd_display_m(self, _val: float = 0.0) -> None:
        _design_update_melrd(self._dw)

    def _dl_populate_m(self) -> None:
        _dlt_populate(self._dlw, self._members[0].id)

    def _dl_add_row_m(self, case_id: int,
                      direction_key: str, ws_kn: float, we_kn: float) -> None:
        _dlt_add_row(self._dlw, case_id, direction_key, ws_kn, we_kn)

    def _dl_add_entry_m(self, direction: str) -> None:
        _dlt_add_entry(self._dlw, direction)

    def _dl_remove_row_m(self) -> None:
        _dlt_remove_row(self._dlw)

    def _pick_section(self) -> None:
        _run_section_picker(
            self, E=self._E, A=self._A, I=self._I, density=self._density,
            fy=self._fy_m, fy_lbl=self._fy_lbl_m, Wpl=self._Wpl_m, Wel=self._Wel_m,
            b_sec=self._b_sec_m, h_sec=self._h_sec_m,
            on_material_change=self._update_design_visibility_m, on_done=self._apply,
        )

    def _apply(self) -> None:
        type_names = ["BEAM", "BAR", "PIN_LEFT", "PIN_RIGHT"]
        elem_type = ElementType[type_names[self._type_combo.currentIndex()]]
        E       = self._E.value() * 1e9
        A       = self._A.value()
        I       = self._I.value() * 1e-6
        density = self._density.value()
        n_sub   = self._nsub.value()
        fy      = self._fy_m.value()  * 1e6
        W_pl    = self._Wpl_m.value() * 1e-6
        W_el    = self._Wel_m.value() * 1e-6
        b_sec   = self._b_sec_m.value() / 1000
        h_sec   = self._h_sec_m.value() / 1000
        d_eff   = (self._h_sec_m.value() - self._cover_m.value()) / 1000
        As_t    = self._As_t_m.value()  / 1e6
        fyk     = self._fyk_m.value()   * 1e6
        # Collect distributed loads from table, keyed by case_id
        case_dls: dict[int, list[DistLoad]] = {}
        for row in range(self._dl_table_m.rowCount()):
            case_combo = self._dl_table_m.cellWidget(row, 0)
            di   = self._dl_table_m.item(row, 1)
            ws   = self._dl_table_m.cellWidget(row, 2)
            we   = self._dl_table_m.cellWidget(row, 3)
            if case_combo and di and ws and we:
                cid = case_combo.currentData()
                case_dls.setdefault(cid, []).append(DistLoad(
                    direction=di.data(Qt.ItemDataRole.UserRole),
                    w_start=ws.value() * 1e3,
                    w_end=we.value()   * 1e3,
                ))
        group = self._group_m.text().strip()
        for m in self._members:
            m.element_type = elem_type
            m.group   = group
            m.E       = E
            m.A       = A
            m.I       = I
            m.density = density
            m.n_sub   = n_sub
            m.fy      = fy
            m.W_pl    = W_pl
            m.W_el    = W_el
            m.b_sec       = b_sec
            m.h_sec       = h_sec
            m.d_eff       = d_eff
            m.As_tension  = As_t
            m.fyk         = fyk
            m.reinforcement_estimated = False   # user has now reviewed/set it directly
            if self._model_state:
                for lc in self._model_state.load_cases:
                    old_ml = lc.get_member_load(m.id)
                    lc.set_member_load(m.id, MemberLoad(
                        dist_loads=case_dls.get(lc.id, []),
                        point_loads=old_ml.point_loads,
                        partial_loads=old_ml.partial_loads,
                    ))
        self._summary_lbl.setText(_multi_member_summary_html(self._members))
        self._on_apply()


# ─────────────────────────────────────────────────────────────────────────────
# _MultiNodeForm
# ─────────────────────────────────────────────────────────────────────────────

class _MultiNodeForm(QWidget):
    """Edit shared support and load properties across multiple selected nodes."""

    def __init__(self, nodes: list, load_case: LoadCase | None,
                 on_apply) -> None:
        super().__init__()
        self._nodes     = nodes
        self._load_case = load_case
        self._on_apply  = on_apply
        first = nodes[0]

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        hdr = QLabel(f"<b>{len(nodes)} nodes selected</b><br>"
                     "<small>Edits apply to all selected nodes</small>")
        hdr.setWordWrap(True)
        layout.addWidget(hdr)

        # ── support ───────────────────────────────────────────────────────
        sup_box = QGroupBox("Support")
        sup_layout = QVBoxLayout(sup_box)
        self._sup_combo = QComboBox()
        self._sup_names = ["FREE", "FIXED", "PIN", "ROLLER", "ROLLER_Y", "ROLLER_Z", "SPRING"]
        self._sup_combo.addItems(["Free", "Fixed", "Pinned", "Roller (vert)", "Roller (horiz)", "Roller (Z)", "Spring"])
        all_same_sup = all(n.support_type == first.support_type for n in nodes)
        _cur = first.support_type.name
        _cur_idx = self._sup_names.index(_cur) if (all_same_sup and _cur in self._sup_names) else 0
        self._sup_combo.setCurrentIndex(_cur_idx)
        self._sup_combo.currentIndexChanged.connect(self._toggle_spring)
        sup_layout.addWidget(self._sup_combo)

        self._spring_group = QGroupBox("Spring stiffness")
        sg = QFormLayout(self._spring_group)
        self._kx  = _spin(first.spring_kx,     0, 1e12, 1e5, 0)
        self._ky  = _spin(first.spring_ky,     0, 1e12, 1e5, 0)
        self._kz  = _spin(first.spring_kz,     0, 1e12, 1e5, 0)
        self._kth = _spin(first.spring_ktheta, 0, 1e12, 1e5, 0)
        self._krx = _spin(first.spring_krx,    0, 1e12, 1e5, 0)
        self._kry = _spin(first.spring_kry,    0, 1e12, 1e5, 0)
        sg.addRow("k_x (N/m):",      self._kx)
        sg.addRow("k_y (N/m):",      self._ky)
        sg.addRow("k_z (N/m):",      self._kz)
        sg.addRow("k_θz (N·m/rad):", self._kth)
        sg.addRow("k_rx (N·m/rad):", self._krx)
        sg.addRow("k_ry (N·m/rad):", self._kry)
        sup_layout.addWidget(self._spring_group)
        layout.addWidget(sup_box)
        self._toggle_spring()

        # ── applied loads (read from active load case for first node) ─────
        first_nl = load_case.get_node_load(first.id) if load_case else NodeLoad()
        load_box = QGroupBox("Applied load  [active case]")
        lf = QFormLayout(load_box)
        self._fx = _spin(first_nl.fx / 1e3,     -1e6, 1e6, 1)
        self._fy = _spin(first_nl.fy / 1e3,     -1e6, 1e6, 1)
        self._fz = _spin(first_nl.fz / 1e3,     -1e6, 1e6, 1)
        self._m  = _spin(first_nl.moment / 1e3, -1e6, 1e6, 1)
        self._mx = _spin(first_nl.moment_x / 1e3, -1e6, 1e6, 1)
        self._my = _spin(first_nl.moment_y / 1e3, -1e6, 1e6, 1)
        lf.addRow("Fx (kN):",   self._fx)
        lf.addRow("Fy (kN):",   self._fy)
        lf.addRow("Fz (kN):",   self._fz)
        lf.addRow("Mz (kN·m):", self._m)
        lf.addRow("Mx (kN·m):", self._mx)
        lf.addRow("My (kN·m):", self._my)
        layout.addWidget(load_box)

        btn = QPushButton(f"Apply to all {len(nodes)} nodes")
        btn.clicked.connect(self._apply)
        layout.addWidget(btn)

    def _toggle_spring(self) -> None:
        self._spring_group.setVisible(self._sup_combo.currentText() == "Spring")

    def _apply(self) -> None:
        sup_type = SupportType[self._sup_names[self._sup_combo.currentIndex()]]
        kx  = self._kx.value()
        ky  = self._ky.value()
        kz  = self._kz.value()
        kth = self._kth.value()
        krx = self._krx.value()
        kry = self._kry.value()
        fx  = self._fx.value() * 1e3
        fy  = self._fy.value() * 1e3
        fz  = self._fz.value() * 1e3
        m   = self._m.value()  * 1e3
        mx  = self._mx.value() * 1e3
        my  = self._my.value() * 1e3
        for nd in self._nodes:
            nd.support_type  = sup_type
            nd.spring_kx     = kx
            nd.spring_ky     = ky
            nd.spring_kz     = kz
            nd.spring_ktheta = kth
            nd.spring_krx    = krx
            nd.spring_kry    = kry
            if self._load_case is not None:
                self._load_case.set_node_load(nd.id, NodeLoad(
                    fx=fx, fy=fy, fz=fz, moment=m, moment_x=mx, moment_y=my
                ))
        self._on_apply()


# ─────────────────────────────────────────────────────────────────────────────
# ResultsPanel
# ─────────────────────────────────────────────────────────────────────────────

class ResultsPanel(QWidget):
    """Tabbed results display: displacements, reactions, member forces.

    Bidirectional selection sync with the canvas:
      - Selecting rows in the table emits nodes_selected / members_selected
      - MainWindow calls select_nodes / select_members to highlight rows from canvas
    """

    nodes_selected   = pyqtSignal(list)   # list[int] of node IDs → canvas
    members_selected = pyqtSignal(list)   # list[int] of member IDs → canvas

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._tabs = QTabWidget()
        self._tabs.setObjectName("results_inner_tabs")
        layout.addWidget(self._tabs)

        self._disp_table  = self._make_table(["Node", "dx (mm)", "dy (mm)", "θ (mrad)"])
        self._react_table = self._make_table(["Node", "Fx (kN)", "Fy (kN)", "M (kN·m)"])
        # N/V as end pairs; M replaced by peak sagging M+, peak hogging M- with x/L positions
        self._force_table = self._make_table([
            "Member",
            "N_i (kN)", "N_j (kN)",
            "V_i (kN)", "V_j (kN)",
            "M+ (kN·m)", "@ x/L",
            "M- (kN·m)", "@ x/L",
        ])

        self._design_table = self._make_table([
            "Member", "Check", "Demand", "Capacity", "η (%)", "Status",
        ])

        self._tabs.addTab(self._wrap(self._disp_table),   "Displacements")
        self._tabs.addTab(self._wrap(self._react_table),  "Reactions")
        self._tabs.addTab(self._wrap(self._force_table),  "Member forces")
        self._tabs.addTab(self._wrap(self._design_table), "Design")

        # Envelope header — shown when results are from a combination envelope.
        # insertWidget(0, ...) places it ABOVE the tabs at the top of the panel.
        self._env_label = QLabel()
        self._env_label.setWordWrap(True)
        self._env_label.setContentsMargins(6, 4, 6, 4)
        self._env_label.setStyleSheet(
            "QLabel { background:#1a1a3a; color:#aabbff;"
            " border-left:4px solid #4466dd; padding:4px 8px; font-size:11px; }"
        )
        self._env_label.hide()
        layout.insertWidget(0, self._env_label)   # above tabs, not below

        self._placeholder = QLabel("Press Solve to see results.")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._placeholder)
        self._tabs.hide()

        # Pattern loading assessment bar — hidden until a solve runs detection
        self._assessment_bar = QLabel()
        self._assessment_bar.setWordWrap(True)
        self._assessment_bar.setContentsMargins(6, 4, 6, 4)
        self._assessment_bar.hide()
        layout.addWidget(self._assessment_bar)

        # Row → ID maps, rebuilt on every populate()
        self._disp_row_to_node:    list[int] = []
        self._react_row_to_node:   list[int] = []
        self._force_row_to_member: list[int] = []
        self._design_row_to_member: list[int] = []
        self._syncing = False   # guard: prevents table→canvas→table loops

        # Multi-row selection
        for tbl in (self._disp_table, self._react_table,
                    self._force_table, self._design_table):
            tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            tbl.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)

        # Table → canvas signals
        self._disp_table.itemSelectionChanged.connect(
            lambda: self._emit_node_sel(self._disp_table, self._disp_row_to_node))
        self._react_table.itemSelectionChanged.connect(
            lambda: self._emit_node_sel(self._react_table, self._react_row_to_node))
        self._force_table.itemSelectionChanged.connect(self._emit_member_sel)
        self._design_table.itemSelectionChanged.connect(self._emit_design_member_sel)

    # ── public ────────────────────────────────────────────────────────────────

    def _configure_dof_tables(self, dpn: int) -> None:
        """Update column count and headers of displacement/reaction tables for dpn."""
        if dpn == 6:
            self._disp_table.setColumnCount(7)
            self._disp_table.setHorizontalHeaderLabels(
                ["Node", "dx (mm)", "dy (mm)", "dz (mm)", "θx (mrad)", "θy (mrad)", "θz (mrad)"]
            )
            self._react_table.setColumnCount(7)
            self._react_table.setHorizontalHeaderLabels(
                ["Node", "Fx (kN)", "Fy (kN)", "Fz (kN)", "Mx (kN·m)", "My (kN·m)", "Mz (kN·m)"]
            )
        else:
            self._disp_table.setColumnCount(4)
            self._disp_table.setHorizontalHeaderLabels(
                ["Node", "dx (mm)", "dy (mm)", "θ (mrad)"]
            )
            self._react_table.setColumnCount(4)
            self._react_table.setHorizontalHeaderLabels(
                ["Node", "Fx (kN)", "Fy (kN)", "M (kN·m)"]
            )

    def populate(self, displacements, reactions, member_results, model_state,
                 dpn: int = 3, **kwargs) -> None:
        """Fill all three tables with solver results and rebuild row→ID maps.

        dpn: degrees of freedom per node — 3 for 2D models, 6 for 3D models.
        kwargs: sub_results, member_el_map — used for peak moment scanning.
        """
        self._restore_force_tab()
        for tbl in (self._disp_table, self._react_table,
                    self._force_table, self._design_table):
            tbl.blockSignals(True)

        self._disp_row_to_node    = []
        self._react_row_to_node   = []
        self._force_row_to_member = []
        self._design_row_to_member = []

        self._configure_dof_tables(dpn)

        # ── Displacements ──────────────────────────────────────────────────────
        self._disp_table.setRowCount(len(model_state.nodes))
        for row, nd in enumerate(model_state.nodes):
            base = nd.id * dpn
            if dpn == 6:
                d = displacements[base:base + 6] * 1e3
                self._set_row(self._disp_table, row, [
                    str(nd.id),
                    f"{d[0]:.4f}", f"{d[1]:.4f}", f"{d[2]:.4f}",
                    f"{d[3]:.4f}", f"{d[4]:.4f}", f"{d[5]:.4f}",
                ])
            else:
                dx = displacements[base]     * 1e3
                dy = displacements[base + 1] * 1e3
                th = displacements[base + 2] * 1e3
                self._set_row(self._disp_table, row,
                              [str(nd.id), f"{dx:.4f}", f"{dy:.4f}", f"{th:.4f}"])
            self._disp_row_to_node.append(nd.id)

        # ── Reactions ──────────────────────────────────────────────────────────
        react_rows = [nd for nd in model_state.nodes if nd.support_type.name != "FREE"]
        self._react_table.setRowCount(len(react_rows))
        for row, nd in enumerate(react_rows):
            base = nd.id * dpn
            if dpn == 6:
                r6 = reactions[base:base + 6]
                self._set_row(self._react_table, row, [
                    str(nd.id),
                    f"{r6[0]/1e3:.3f}", f"{r6[1]/1e3:.3f}", f"{r6[2]/1e3:.3f}",
                    f"{r6[3]/1e3:.3f}", f"{r6[4]/1e3:.3f}", f"{r6[5]/1e3:.3f}",
                ])
            else:
                fx = reactions[base]     / 1e3
                fy = reactions[base + 1] / 1e3
                m  = reactions[base + 2] / 1e3
                self._set_row(self._react_table, row,
                              [str(nd.id), f"{fx:.3f}", f"{fy:.3f}", f"{m:.3f}"])
            self._react_row_to_node.append(nd.id)

        # ── Member forces — peak M scan using sub-element endpoints ─────────────
        sub_results    = kwargs.get('sub_results')
        member_el_map  = kwargs.get('member_el_map')
        sub_by_id: dict = {r.element_id: r for r in sub_results} if sub_results else {}

        n_members = len(member_results)
        self._force_table.setRowCount(n_members + (2 if n_members > 0 else 0))

        # Per-column value lists for footer (cols 1-4 = N/V, 5 = M+, 7 = M-)
        col_vals: dict[int, list[float]] = {1: [], 2: [], 3: [], 4: [], 5: [], 7: []}
        xL_plus:  list[float] = []  # x/L where M+ peak occurs per member
        xL_minus: list[float] = []  # x/L where M- peak occurs per member
        design_data: list[tuple[int, float, float]] = []  # (mid, M_Ed N·m, N_Ed N)

        for row, res in enumerate(member_results):
            mid  = res.element_id
            N_i  = res.N_i / 1e3
            N_j  = res.N_j / 1e3
            V_i  = res.V_i / 1e3
            V_j  = res.V_j / 1e3

            # Scan sub-element endpoints for peak sagging (M+) and hogging (M-)
            M_plus  = 0.0;  xL_p = 0.0
            M_minus = 0.0;  xL_m = 0.0

            if member_el_map and sub_by_id and row < len(member_el_map):
                sub_ids = member_el_map[row]
                n_sub   = len(sub_ids)
                for k, sid in enumerate(sub_ids):
                    sr = sub_by_id.get(sid)
                    if sr is None:
                        continue
                    for m_val, pos in [(sr.M_i, k / n_sub), (sr.M_j, (k + 1) / n_sub)]:
                        if m_val > M_plus:
                            M_plus = m_val;  xL_p = pos
                        if m_val < M_minus:
                            M_minus = m_val; xL_m = pos
            else:
                # fallback: only end-force values available
                for m_val, pos in [(res.M_i, 0.0), (res.M_j, 1.0)]:
                    if m_val > M_plus:
                        M_plus = m_val;  xL_p = pos
                    if m_val < M_minus:
                        M_minus = m_val; xL_m = pos

            Mp_kNm = M_plus  / 1e3
            Mm_kNm = M_minus / 1e3

            self._set_row(self._force_table, row, [
                str(mid),
                f"{N_i:.3f}", f"{N_j:.3f}",
                f"{V_i:.3f}", f"{V_j:.3f}",
                f"{Mp_kNm:.3f}", f"{xL_p:.2f}",
                f"{Mm_kNm:.3f}", f"{xL_m:.2f}",
            ])
            self._force_row_to_member.append(mid)

            col_vals[1].append(N_i);  col_vals[2].append(N_j)
            col_vals[3].append(V_i);  col_vals[4].append(V_j)
            col_vals[5].append(Mp_kNm)
            col_vals[7].append(Mm_kNm)
            xL_plus.append(xL_p);    xL_minus.append(xL_m)
            design_data.append((mid, max(abs(M_plus), abs(M_minus)),
                               max((res.N_i, res.N_j), key=abs)))   # sign kept: + = compression

        # Footer Max / Min rows
        if n_members > 0:
            max_v = {c: max(col_vals[c]) for c in col_vals}
            min_v = {c: min(col_vals[c]) for c in col_vals}
            # x/L for the member whose M+ is max, and whose M- is min (worst hogging)
            xL_max_plus  = xL_plus [col_vals[5].index(max_v[5])]
            xL_min_minus = xL_minus[col_vals[7].index(min_v[7])]
            # x/L for the member whose M+ is min, and whose M- is max (least hogging)
            xL_min_plus  = xL_plus [col_vals[5].index(min_v[5])]
            xL_max_minus = xL_minus[col_vals[7].index(max_v[7])]
            self._set_footer_row(self._force_table, n_members, "Max", [
                f"{max_v[1]:.3f}", f"{max_v[2]:.3f}",
                f"{max_v[3]:.3f}", f"{max_v[4]:.3f}",
                f"{max_v[5]:.3f}", f"{xL_max_plus:.2f}",
                f"{max_v[7]:.3f}", f"{xL_max_minus:.2f}",
            ], bg="#2a1f00", fg="#ffb300")
            self._set_footer_row(self._force_table, n_members + 1, "Min", [
                f"{min_v[1]:.3f}", f"{min_v[2]:.3f}",
                f"{min_v[3]:.3f}", f"{min_v[4]:.3f}",
                f"{min_v[5]:.3f}", f"{xL_min_plus:.2f}",
                f"{min_v[7]:.3f}", f"{xL_min_minus:.2f}",
            ], bg="#001a2a", fg="#64b5f6")

        for tbl in (self._disp_table, self._react_table,
                    self._force_table, self._design_table):
            tbl.blockSignals(False)

        self._populate_design_table(design_data, model_state)

        self._env_label.hide()
        self._placeholder.hide()
        self._tabs.show()

    # Separate table used for envelope member forces (3 columns, not 6)
    _env_force_table: "QTableWidget | None" = None

    def populate_envelope(self, solve_runs: list, model_state, dpn: int = 3) -> None:
        """Fill all three tables with envelope values (max absolute across all runs).

        Member forces tab is replaced by a simplified 4-column table
        (max|N|, max|V|, max|M| across both ends) so it stays readable
        in a narrow panel.  Sign is preserved (governs for tension/compression).

        dpn: degrees of freedom per node — 3 for 2D models, 6 for 3D models.
        """
        from ui_qt.model_state import SupportType as _ST

        # ── Swap Member forces tab to a 4-column envelope table ──────────────
        if self._env_force_table is None:
            self._env_force_table = self._make_table(
                ["Member", "max|N| (kN)", "max|V| (kN)", "max|M| (kN·m)"]
            )
            self._env_force_table.setSelectionBehavior(
                QTableWidget.SelectionBehavior.SelectRows
            )
            self._env_force_table.setSelectionMode(
                QTableWidget.SelectionMode.ExtendedSelection
            )
            self._env_force_table.itemSelectionChanged.connect(self._emit_member_sel)

        # Replace the Member forces tab content with the envelope table
        self._tabs.removeTab(2)
        self._tabs.insertTab(2, self._wrap(self._env_force_table), "Member forces ▲")

        for tbl in (self._disp_table, self._react_table,
                    self._env_force_table, self._design_table):
            tbl.blockSignals(True)

        self._disp_row_to_node     = []
        self._react_row_to_node    = []
        self._force_row_to_member  = []
        self._design_row_to_member = []
        state = model_state
        n_runs = len(solve_runs)

        self._configure_dof_tables(dpn)

        # ── Displacements ─────────────────────────────────────────────────────
        self._disp_table.setRowCount(len(state.nodes))
        for row, nd in enumerate(state.nodes):
            base = nd.id * dpn
            if dpn == 6:
                d = [max((r['displacements'][base + k] for r in solve_runs), key=abs) for k in range(6)]
                self._set_row(self._disp_table, row, [
                    str(nd.id),
                    f"{d[0]*1e3:.4f}", f"{d[1]*1e3:.4f}", f"{d[2]*1e3:.4f}",
                    f"{d[3]*1e3:.4f}", f"{d[4]*1e3:.4f}", f"{d[5]*1e3:.4f}",
                ])
            else:
                dx = max((r['displacements'][base]     for r in solve_runs), key=abs)
                dy = max((r['displacements'][base + 1] for r in solve_runs), key=abs)
                th = max((r['displacements'][base + 2] for r in solve_runs), key=abs)
                self._set_row(self._disp_table, row, [
                    str(nd.id),
                    f"{dx * 1e3:.4f}", f"{dy * 1e3:.4f}", f"{th * 1e3:.4f}",
                ])
            self._disp_row_to_node.append(nd.id)

        # ── Reactions ─────────────────────────────────────────────────────────
        react_rows = [nd for nd in state.nodes if nd.support_type != _ST.FREE]
        self._react_table.setRowCount(len(react_rows))
        for row, nd in enumerate(react_rows):
            base = nd.id * dpn
            runs_with_r = [r for r in solve_runs if 'reactions' in r]
            if dpn == 6:
                if runs_with_r:
                    r6 = [max((r['reactions'][base + k] for r in runs_with_r), key=abs) for k in range(6)]
                else:
                    r6 = [0.0] * 6
                self._set_row(self._react_table, row, [
                    str(nd.id),
                    f"{r6[0]/1e3:.3f}", f"{r6[1]/1e3:.3f}", f"{r6[2]/1e3:.3f}",
                    f"{r6[3]/1e3:.3f}", f"{r6[4]/1e3:.3f}", f"{r6[5]/1e3:.3f}",
                ])
            else:
                if runs_with_r:
                    fx = max((r['reactions'][base]     for r in runs_with_r), key=abs)
                    fy = max((r['reactions'][base + 1] for r in runs_with_r), key=abs)
                    m  = max((r['reactions'][base + 2] for r in runs_with_r), key=abs)
                else:
                    fx = fy = m = 0.0
                self._set_row(self._react_table, row, [
                    str(nd.id),
                    f"{fx / 1e3:.3f}", f"{fy / 1e3:.3f}", f"{m / 1e3:.3f}",
                ])
            self._react_row_to_node.append(nd.id)

        # ── Member forces (simplified 4-column envelope) ───────────────────────
        self._env_force_table.setRowCount(len(state.members))
        env_design_data: list[tuple[int, float, float]] = []
        for row, md in enumerate(state.members):
            all_res = [
                r for run in solve_runs
                for r in run['member_results']
                if r.element_id == md.id
            ]
            if all_res:
                N = max((max(r.N_i, r.N_j, key=abs) for r in all_res), key=abs)
                V = max((max(r.V_i, r.V_j, key=abs) for r in all_res), key=abs)
                M = max((max(r.M_i, r.M_j, key=abs) for r in all_res), key=abs)
            else:
                N = V = M = 0.0
            self._set_row(self._env_force_table, row, [
                str(md.id),
                f"{N / 1e3:.3f}", f"{V / 1e3:.3f}", f"{M / 1e3:.3f}",
            ])
            self._force_row_to_member.append(md.id)
            env_design_data.append((md.id, abs(M), N))   # N keeps its sign: + = compression

        for tbl in (self._disp_table, self._react_table,
                    self._env_force_table, self._design_table):
            tbl.blockSignals(False)

        self._populate_design_table(env_design_data, state)

        self._env_label.setText(
            f"▲  Envelope — {n_runs} combinations.  "
            "Each value is the worst absolute across all combinations and both member ends."
        )
        self._env_label.show()
        self._placeholder.hide()
        self._tabs.show()
        self._tabs.setCurrentIndex(2)   # jump straight to Member forces ▲

    def _restore_force_tab(self) -> None:
        """Swap the Member forces tab back to the standard 9-column peak-moment table."""
        if self._env_force_table is None:
            return
        if self._tabs.tabText(2) == "Member forces ▲":
            self._tabs.removeTab(2)
            self._tabs.insertTab(2, self._wrap(self._force_table), "Member forces")

    def clear(self) -> None:
        self._restore_force_tab()
        self._tabs.hide()
        self._env_label.hide()
        self._placeholder.show()
        self._assessment_bar.hide()

    def set_pattern_assessment(self, message: str, level: str = "ok") -> None:
        """Show the pattern loading assessment banner.

        level: 'ok'      → green  (not required)
               'info'    → blue   (required, full loading governs)
               'warning' → amber  (required, pattern governs — non-conservative without it)
        """
        _styles = {
            "ok":      "background:#1b3a1b; color:#90ee90; border-left:4px solid #4caf50;",
            "info":    "background:#0d2b45; color:#90caf9; border-left:4px solid #1565c0;",
            "warning": "background:#3a2500; color:#ffcc66; border-left:4px solid #ff8f00;",
        }
        _icons = {"ok": "✓", "info": "ℹ", "warning": "⚠"}
        style = _styles.get(level, _styles["ok"])
        icon  = _icons.get(level, "")
        self._assessment_bar.setStyleSheet(f"QLabel {{ {style} padding:6px 8px; }}")
        self._assessment_bar.setText(f"{icon}  {message}")
        self._assessment_bar.show()

    # ── canvas → table ────────────────────────────────────────────────────────

    def select_nodes(self, node_ids: list[int]) -> None:
        """Highlight rows matching node_ids (called by canvas selection change)."""
        self._syncing = True
        try:
            self._highlight_rows(self._disp_table,  self._disp_row_to_node,  node_ids)
            self._highlight_rows(self._react_table, self._react_row_to_node, node_ids)
        finally:
            self._syncing = False

    def select_members(self, member_ids: list[int]) -> None:
        """Highlight rows matching member_ids (called by canvas selection change)."""
        self._syncing = True
        try:
            self._highlight_rows(self._force_table,  self._force_row_to_member,  member_ids)
            self._highlight_rows(self._design_table, self._design_row_to_member, member_ids)
        finally:
            self._syncing = False

    def _populate_design_table(
        self, m_ed_data: list[tuple[int, float, float]], model_state
    ) -> None:
        """Fill the Design tab from (member_id, M_Ed_Nm, N_Ed_N) triples.

        Each member contributes one row per applicable check, decided by its
        element_type: BAR -> axial only; BEAM/PIN_LEFT/PIN_RIGHT -> bending
        only, or axial + bending + a combined N+M interaction row when it
        carries real axial force (e.g. a column) — see _compute_member_design_rows.
        """
        self._design_row_to_member = []
        flat_rows: list[dict] = []

        for mid, M_Ed, N_Ed in m_ed_data:
            md = model_state.get_member(mid)
            fk   = md.fy      if md else 275e6
            A    = md.A       if md else 0.0
            W_pl = md.W_pl    if md else 0.0
            W_el = md.W_el    if md else 0.0
            dens = md.density if md else 0.0
            etype = md.element_type if md else ElementType.BEAM

            # Infer material family from density (same convention as the
            # member-properties Design tab's _infer_mat_type)
            if 2000 <= dens <= 3000:
                mat = "concrete"
            elif 300 <= dens <= 800:
                mat = "timber"
            else:
                mat = "steel"   # steel / custom / zero density all use steel formula

            b     = md.b_sec      if md else 0.0
            d     = md.d_eff      if md else 0.0
            As    = md.As_tension if md else 0.0
            fyk_v = md.fyk        if md else 500e6

            estimated = mat == "concrete" and bool(md and md.reinforcement_estimated)
            for check_row in _compute_member_design_rows(
                etype, mat, fk, A, W_pl, W_el, b, d, As, fyk_v, M_Ed, N_Ed,
            ):
                if estimated and check_row["eta"] is not None:
                    check_row["status"] += "  (min. reinf. — refine)"
                flat_rows.append({"mid": mid, **check_row})

        self._design_table.blockSignals(True)
        self._design_table.clearSpans()   # drop any spans from a previous populate
        self._design_table.setRowCount(len(flat_rows))

        for row, r in enumerate(flat_rows):
            demand   = f"{r['demand'] / 1e3:.3f} {r['unit']}"     if r['demand']   is not None else "—"
            capacity = f"{r['capacity'] / 1e3:.3f} {r['unit']}"   if r['capacity'] is not None else "—"
            self._set_row(self._design_table, row, [
                str(r["mid"]),
                r["check"],
                demand,
                capacity,
                f"{r['eta']:.1f}" if r["eta"] is not None else "—",
                r["status"],
            ])
            self._design_row_to_member.append(r["mid"])

            # Colour-code by utilisation
            if r["eta"] is None:
                bg, fg = QColor(28, 28, 48), QColor("#8899cc")     # info — check N/A or not configured
            elif r["eta"] <= 80.0:
                bg, fg = QColor("#1b3a1b"), QColor("#90ee90")       # green — low
            elif r["eta"] <= 100.0:
                bg, fg = QColor("#3a3000"), QColor("#ffe066")       # amber — near limit
            else:
                bg, fg = QColor("#3a0000"), QColor("#ff6b6b")       # red — exceeded

            bg_brush = QBrush(bg)
            fg_brush = QBrush(fg)
            # Column 0 (Member) is styled separately below as a spanned group
            # header, so its colour isn't tied to any one check's PASS/FAIL.
            for col in range(1, self._design_table.columnCount()):
                item = self._design_table.item(row, col)
                if item:
                    item.setBackground(bg_brush)
                    item.setForeground(fg_brush)

        # Group consecutive rows that belong to the same member: span the
        # Member cell across them so it's visually obvious "these N rows are
        # one element assessed against N different capacities," instead of
        # looking like N separate members that happen to share an ID.
        header_bg = QBrush(QColor("#26282c"))
        header_fg = QBrush(QColor("#dddddd"))
        row = 0
        while row < len(flat_rows):
            span = 1
            while row + span < len(flat_rows) and flat_rows[row + span]["mid"] == flat_rows[row]["mid"]:
                span += 1
            item = self._design_table.item(row, 0)
            if item:
                item.setBackground(header_bg)
                item.setForeground(header_fg)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                f = item.font(); f.setBold(True); item.setFont(f)
            if span > 1:
                self._design_table.setSpan(row, 0, span, 1)
            row += span

        self._design_table.blockSignals(False)

    def _highlight_rows(self, table: QTableWidget, row_to_id: list[int],
                        ids: list[int]) -> None:
        table.blockSignals(True)
        table.clearSelection()
        id_set = set(ids)
        sel = table.selectionModel()
        for row, item_id in enumerate(row_to_id):
            if item_id in id_set:
                for col in range(table.columnCount()):
                    sel.select(
                        table.model().index(row, col),
                        QItemSelectionModel.SelectionFlag.Select,
                    )
        if ids and any(item_id in id_set for item_id in row_to_id):
            # Scroll to first matching row
            for row, item_id in enumerate(row_to_id):
                if item_id in id_set:
                    table.scrollToItem(table.item(row, 0))
                    break
        table.blockSignals(False)

    # ── table → canvas ────────────────────────────────────────────────────────

    def _emit_node_sel(self, table: QTableWidget, row_to_id: list[int]) -> None:
        if self._syncing:
            return
        ids = list({row_to_id[idx.row()]
                    for idx in table.selectedIndexes()
                    if idx.column() == 0 and idx.row() < len(row_to_id)})
        self.nodes_selected.emit(ids)

    def _emit_member_sel(self) -> None:
        if self._syncing:
            return
        tbl = (self._env_force_table
               if self._tabs.tabText(2) == "Member forces ▲" and self._env_force_table
               else self._force_table)
        ids = list({self._force_row_to_member[idx.row()]
                    for idx in tbl.selectedIndexes()
                    if idx.column() == 0 and idx.row() < len(self._force_row_to_member)})
        self.members_selected.emit(ids)

    def _emit_design_member_sel(self) -> None:
        if self._syncing:
            return
        ids = list({self._design_row_to_member[idx.row()]
                    for idx in self._design_table.selectedIndexes()
                    if idx.column() == 0
                    and idx.row() < len(self._design_row_to_member)})
        self.members_selected.emit(ids)

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _make_table(headers: list[str]) -> QTableWidget:
        t = QTableWidget(0, len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.horizontalHeader().setStretchLastSection(True)
        t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        t.setAlternatingRowColors(True)
        return t

    @staticmethod
    def _set_row(table: QTableWidget, row: int, values: list[str]) -> None:
        for col, val in enumerate(values):
            item = QTableWidgetItem(val)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(row, col, item)

    @staticmethod
    def _set_footer_row(table: QTableWidget, row: int, label: str,
                        values: list[str], bg: str, fg: str) -> None:
        """Insert a styled Max/Min summary row.  Col 0 = label, cols 1+ = values."""
        bg_brush = QBrush(QColor(bg))
        fg_brush = QBrush(QColor(fg))
        font = QFont()
        font.setBold(True)
        for col in range(table.columnCount()):
            text = label if col == 0 else (values[col - 1] if col - 1 < len(values) else "—")
            item = QTableWidgetItem(text)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setBackground(bg_brush)
            item.setForeground(fg_brush)
            item.setFont(font)
            table.setItem(row, col, item)

    @staticmethod
    def _wrap(widget: QWidget) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidget(widget)
        scroll.setWidgetResizable(True)
        return scroll


# ─────────────────────────────────────────────────────────────────────────────
# BrandingFooter
# ─────────────────────────────────────────────────────────────────────────────

class BrandingFooter(QWidget):
    """Static INSTRA logo bar pinned to the bottom of the right panel."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedHeight(72)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)

        # Logo
        logo_label = QLabel()
        logo_path = _ASSETS / "instra_logo.png"
        if logo_path.exists():
            pix = QPixmap(str(logo_path))
            pix = pix.scaledToHeight(56, Qt.TransformationMode.SmoothTransformation)
            logo_label.setPixmap(pix)
        logo_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        # Text block: product name + version + copyright
        name_lbl = QLabel("StructLab")
        name_lbl.setStyleSheet("font-size: 13px; font-weight: bold; color: #d0d0d0;")

        ver_lbl = QLabel("V 1.2")
        ver_lbl.setStyleSheet("font-size: 10px; color: #787878;")

        copy_lbl = QLabel("© 2025 INSTRA")
        copy_lbl.setStyleSheet("font-size: 10px; color: #787878;")

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(6, 0, 0, 0)
        text_layout.setSpacing(1)
        text_layout.addStretch()
        text_layout.addWidget(name_lbl)
        text_layout.addWidget(ver_lbl)
        text_layout.addWidget(copy_lbl)
        text_layout.addStretch()

        inner = QHBoxLayout()
        inner.setContentsMargins(10, 4, 10, 4)
        inner.addWidget(logo_label)
        inner.addLayout(text_layout)
        inner.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(sep)
        layout.addLayout(inner)


# ─────────────────────────────────────────────────────────────────────────────
# RightPanel — Properties (top) + Results (bottom) with draggable splitter
# ─────────────────────────────────────────────────────────────────────────────

_SECTION_HEADER_STYLE = (
    "background:#2d2d2d; color:#cccccc;"
    " font-size:11px; font-weight:bold; padding-left:6px;"
)


class RightPanel(QWidget):
    """Properties panel always on top, Results panel always below.
    A draggable QSplitter lets the user resize the two panes.
    Branding footer is pinned at the very bottom."""

    def __init__(self, props_panel: PropertiesPanel,
                 results_panel: ResultsPanel, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(5)

        # ── Properties pane ───────────────────────────────────────────────────
        props_frame = QWidget()
        pf = QVBoxLayout(props_frame)
        pf.setContentsMargins(0, 0, 0, 0)
        pf.setSpacing(0)

        props_hdr = QLabel("  Properties")
        props_hdr.setFixedHeight(22)
        props_hdr.setStyleSheet(_SECTION_HEADER_STYLE)
        pf.addWidget(props_hdr)

        props_scroll = QScrollArea()
        props_scroll.setWidget(props_panel)
        props_scroll.setWidgetResizable(True)
        props_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        pf.addWidget(props_scroll)

        # ── Results pane ──────────────────────────────────────────────────────
        results_frame = QWidget()
        rf = QVBoxLayout(results_frame)
        rf.setContentsMargins(0, 0, 0, 0)
        rf.setSpacing(0)

        results_hdr = QLabel("  Results")
        results_hdr.setFixedHeight(22)
        results_hdr.setStyleSheet(_SECTION_HEADER_STYLE)
        rf.addWidget(results_hdr)
        rf.addWidget(results_panel)

        splitter.addWidget(props_frame)
        splitter.addWidget(results_frame)
        splitter.setSizes([350, 380])

        layout.addWidget(splitter)
        layout.addWidget(BrandingFooter())

    def raise_properties(self) -> None:
        pass   # both panes always visible — nothing to switch

    def raise_results(self) -> None:
        pass   # both panes always visible — nothing to switch
