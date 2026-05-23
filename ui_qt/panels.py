"""Properties inspector and Results panels for the StructLab Qt UI."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtGui import QBrush, QColor, QFont, QPixmap
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QDoubleSpinBox, QSpinBox, QComboBox, QPushButton,
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
        self._model_state = None          # set by MainWindow via set_model_state()

    def set_model_state(self, state) -> None:
        """Keep a reference so forms can read/write the active load case."""
        self._model_state = state

    def _active_case(self) -> LoadCase | None:
        return self._model_state.active_case if self._model_state else None

    # ── public entry points ───────────────────────────────────────────────────

    def show_empty(self) -> None:
        self._replace(None)

    def _is_3d(self) -> bool:
        if not self._model_state:
            return False
        # Consistent with _node_pos: treat model as 3D if mode_3d flag is set
        # OR if any node already has a non-zero z coordinate.
        return self._model_state.mode_3d or any(
            n.z != 0.0 for n in self._model_state.nodes
        )

    def show_node(self, node: NodeData) -> None:
        self._replace(_NodeForm(node, self._active_case(), self._on_apply, self._is_3d()))

    def show_member(self, member: MemberData) -> None:
        self._replace(_MemberForm(
            member, self._model_state, self._on_apply, self._is_3d(),
        ))

    def show_nodes(self, nodes: list) -> None:
        self._replace(_MultiNodeForm(nodes, self._active_case(), self._on_apply, self._is_3d()))

    def show_members(self, members: list) -> None:
        self._replace(_MultiMemberForm(members, self._active_case(), self._on_apply, self._is_3d()))

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


# ─────────────────────────────────────────────────────────────────────────────
# _NodeForm
# ─────────────────────────────────────────────────────────────────────────────

class _NodeForm(QWidget):
    def __init__(self, node: NodeData, load_case: LoadCase | None,
                 on_apply, mode_3d: bool = False) -> None:
        super().__init__()
        self._node      = node
        self._load_case = load_case
        self._on_apply  = on_apply
        self._mode_3d   = mode_3d
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        layout.addWidget(QLabel(f"<b>Node {node.id}</b>"))

        # ── coordinates ──────────────────────────────────────────────────────
        coord_box = QGroupBox("Coordinates")
        form = QFormLayout(coord_box)
        self._x = _spin(node.x, -1000, 1000, 0.25)
        self._y = _spin(node.y, -1000, 1000, 0.25)
        self._z = _spin(node.z, -1000, 1000, 0.25)
        form.addRow("x (m):", self._x)     # row 0
        form.addRow("y (m):", self._y)     # row 1
        form.addRow("z (m):", self._z)     # row 2
        form.setRowVisible(2, mode_3d)
        layout.addWidget(coord_box)

        # ── support ──────────────────────────────────────────────────────────
        sup_box = QGroupBox("Support")
        sup_layout = QVBoxLayout(sup_box)
        self._sup_combo = QComboBox()
        if mode_3d:
            self._sup_names = ["FREE","FIXED","PIN","ROLLER","ROLLER_Y","ROLLER_Z","SPRING"]
            self._sup_combo.addItems(["Free", "Fixed", "Pinned", "Roller (vert)", "Roller (horiz)", "Roller (Z)", "Spring"])
        else:
            self._sup_names = ["FREE","FIXED","PIN","ROLLER","ROLLER_Y","SPRING"]
            self._sup_combo.addItems(["Free", "Fixed", "Pinned", "Roller (vert)", "Roller (horiz)", "Spring"])
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
        self._krz   = _spin(node.spring_krz,    0, 1e12, 1e5, 0)
        sg.addRow("k_x (N/m):",     self._kx)   # row 0
        sg.addRow("k_y (N/m):",     self._ky)   # row 1
        sg.addRow("k_z (N/m):",     self._kz)   # row 2
        sg.addRow("k_θ (N·m/rad):", self._kth)  # row 3
        sg.addRow("k_rx (N·m/rad):", self._krx) # row 4
        sg.addRow("k_ry (N·m/rad):", self._kry) # row 5
        sg.addRow("k_rz (N·m/rad):", self._krz) # row 6
        sg.setRowVisible(2, mode_3d)
        sg.setRowVisible(4, mode_3d)
        sg.setRowVisible(5, mode_3d)
        sg.setRowVisible(6, mode_3d)
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
        lf.addRow("Fx (kN):",   self._fx)   # row 0
        lf.addRow("Fy (kN):",   self._fy)   # row 1
        lf.addRow("Fz (kN):",   self._fz)   # row 2
        lf.addRow("Mz (kN·m):", self._m)    # row 3
        lf.addRow("Mx (kN·m):", self._mx)   # row 4
        lf.addRow("My (kN·m):", self._my)   # row 5
        lf.setRowVisible(2, mode_3d)
        lf.setRowVisible(4, mode_3d)
        lf.setRowVisible(5, mode_3d)
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
        node.z = self._z.value() if self._mode_3d else 0.0
        node.support_type  = SupportType[self._sup_names[self._sup_combo.currentIndex()]]
        node.spring_kx     = self._kx.value()
        node.spring_ky     = self._ky.value()
        node.spring_kz     = self._kz.value()
        node.spring_ktheta = self._kth.value()
        node.spring_krx    = self._krx.value()
        node.spring_kry    = self._kry.value()
        node.spring_krz    = self._krz.value()
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


# _MemberForm
# ─────────────────────────────────────────────────────────────────────────────

class _MemberForm(QWidget):
    def __init__(self, member: MemberData, model_state,
                 on_apply, mode_3d: bool = False) -> None:
        super().__init__()
        self._member      = member
        self._model_state = model_state
        self._load_case   = model_state.active_case if model_state else None
        self._on_apply    = on_apply
        self._mode_3d     = mode_3d
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        layout.addWidget(QLabel(f"<b>Member {member.id}</b> (nodes {member.node_i}→{member.node_j})"))

        # ── element type ─────────────────────────────────────────────────────
        type_box = QGroupBox("Element type")
        tf = QFormLayout(type_box)
        self._type_combo = QComboBox()
        self._type_combo.addItems(["Beam", "Bar", "Pin-Left", "Pin-Right"])
        type_names = ["BEAM","BAR","PIN_LEFT","PIN_RIGHT"]
        self._type_combo.setCurrentIndex(type_names.index(member.element_type.name))
        tf.addRow("Type:", self._type_combo)
        layout.addWidget(type_box)

        # ── section properties ────────────────────────────────────────────────
        sec_box = QGroupBox("Section properties")
        sf = QFormLayout(sec_box)
        self._E = _spin(member.E / 1e9, 0, 1000, 1, 1)   # GPa
        self._A = _spin(member.A,       0, 100,  0.001, 6)
        self._I = _spin(member.I * 1e6, 0, 1e6,  1, 2)   # ×10⁻⁶ m⁴ display (I_z)
        Iy_val  = member.I_y if member.I_y is not None else member.I
        self._Iy = _spin(Iy_val * 1e6,  0, 1e6,  1, 2)   # I_y weak axis
        self._J  = _spin(member.J * 1e6, 0, 1e6,  0.01, 3)  # J torsion
        self._beta = _spin(member.beta_angle, -6.283, 6.283, 0.1, 3)  # rad
        self._fy   = _spin(member.fy / 1e6, 0, 2000, 5, 0)       # MPa
        self._Wpl  = _spin(member.W_pl * 1e6, 0, 1e6, 0.1, 1)   # cm³
        self._Wel  = _spin(member.W_el * 1e6, 0, 1e6, 0.1, 1)   # cm³
        sf.addRow("E (GPa):",         self._E)        # row 0
        sf.addRow("A (m²):",          self._A)        # row 1
        sf.addRow("I_z (×10⁻⁶ m⁴):", self._I)        # row 2
        sf.addRow("I_y (×10⁻⁶ m⁴):", self._Iy)       # row 3
        sf.addRow("J (×10⁻⁶ m⁴):",   self._J)        # row 4
        sf.addRow("β angle (rad):",   self._beta)     # row 5
        sf.setRowVisible(3, mode_3d)
        sf.setRowVisible(4, mode_3d)
        sf.setRowVisible(5, mode_3d)
        sf.addRow("fy (MPa):",        self._fy)       # row 6
        sf.addRow("W_pl (cm³):",      self._Wpl)      # row 7
        sf.addRow("W_el (cm³):",      self._Wel)      # row 8
        pick_btn = QPushButton("Pick from library...")
        pick_btn.clicked.connect(self._pick_section)
        sf.addRow("", pick_btn)

        # ── material / density ───────────────────────────────────────────────
        self._mat_preset = QComboBox()
        self._mat_preset.addItems(["Steel (7850)", "Concrete (2500)", "Timber (500)", "Custom"])
        _PRESETS = [7850.0, 2500.0, 500.0]
        def _density_from_preset(idx: int, presets=_PRESETS) -> None:
            if idx < len(presets):
                self._density.setValue(presets[idx])
        self._mat_preset.currentIndexChanged.connect(_density_from_preset)
        sf.addRow("Material:", self._mat_preset)

        self._density = _spin(member.density, 0, 20000, 50, 0)
        self._density.setToolTip("0 = no self-weight contribution from this member")
        def _mark_custom() -> None:
            self._mat_preset.setCurrentIndex(3)   # "Custom"
        self._density.valueChanged.connect(_mark_custom)
        sf.addRow("Density (kg/m³):", self._density)

        # Set preset index to match current density without triggering valueChanged loop
        self._mat_preset.blockSignals(True)
        for _i, _d in enumerate(_PRESETS):
            if abs(member.density - _d) < 1.0:
                self._mat_preset.setCurrentIndex(_i)
                break
        else:
            self._mat_preset.setCurrentIndex(3)
        self._mat_preset.blockSignals(False)

        layout.addWidget(sec_box)

        # ── distributed loads — all cases ────────────────────────────────────
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
        self._dl_populate()
        dl_layout.addWidget(self._dl_table)

        dl_btn_row = QHBoxLayout()
        for _key, _lbl in [("w", "+ Local w"), ("qx", "+ qx"), ("qy", "+ qy")]:
            if _key == "qy" and not mode_3d:
                continue
            _b = QPushButton(_lbl)
            _b.setFixedHeight(26)
            _b.clicked.connect(lambda checked=False, k=_key: self._dl_add_entry(k))
            dl_btn_row.addWidget(_b)
        _rm = QPushButton("Remove")
        _rm.setFixedHeight(26)
        _rm.clicked.connect(self._dl_remove_row)
        dl_btn_row.addWidget(_rm)
        dl_layout.addLayout(dl_btn_row)
        layout.addWidget(dl_box)

        # ── point loads on member ─────────────────────────────────────────────
        ml = self._load_case.get_member_load(member.id) if self._load_case else MemberLoad()
        pl_box = QGroupBox("Point loads on member  [active case]")
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
            _pb.setFixedHeight(26)
        btn_add_f.clicked.connect(lambda: self._add_pl_row("FORCE",  0.5, 0.0))
        btn_add_m.clicked.connect(lambda: self._add_pl_row("MOMENT", 0.5, 0.0))
        btn_del.clicked.connect(self._remove_pl_row)
        pl_btn_row.addWidget(btn_add_f)
        pl_btn_row.addWidget(btn_add_m)
        pl_btn_row.addWidget(btn_del)
        pl_layout.addLayout(pl_btn_row)
        layout.addWidget(pl_box)

        # ── partial distributed loads ─────────────────────────────────────────
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
            _pb.setFixedHeight(26)
        btn_add_pdl.clicked.connect(lambda: self._add_pdl_row(0.25, 0.75, 0.0, 0.0))
        btn_del_pdl.clicked.connect(self._remove_pdl_row)
        pdl_btn_row.addWidget(btn_add_pdl)
        pdl_btn_row.addWidget(btn_del_pdl)
        pdl_layout.addLayout(pdl_btn_row)
        layout.addWidget(pdl_box)

        # ── mesh ──────────────────────────────────────────────────────────────
        mesh_box = QGroupBox("Analysis mesh")
        mf = QFormLayout(mesh_box)
        self._nsub = QSpinBox()
        self._nsub.setRange(1, 100)
        self._nsub.setValue(member.n_sub)
        self._nsub.setToolTip("Number of sub-elements for analysis (more = better deformed shape)")
        mf.addRow("Sub-elements:", self._nsub)
        layout.addWidget(mesh_box)

        btn = QPushButton("Apply")
        btn.clicked.connect(self._apply)
        layout.addWidget(btn)


    def _pick_section(self) -> None:
        from ui_qt.section_picker import SectionPickerDialog
        dlg = SectionPickerDialog(
            current_E=self._E.value() * 1e9,
            current_A=self._A.value(),
            current_I=self._I.value() * 1e-6,
            parent=self,
        )
        if dlg.exec() and dlg.get_result():
            E, A, I, W_pl, W_el = dlg.get_result()
            self._E.setValue(E / 1e9)
            self._A.setValue(A)
            self._I.setValue(I * 1e6)
            if W_pl > 0:
                self._Wpl.setValue(W_pl * 1e6)
            if W_el > 0:
                self._Wel.setValue(W_el * 1e6)

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

    _DL_DIRS = [
        ("w",  "Local ↓  (w)",     "Full-span load local ⊥ to member  —  ↓ positive"),
        ("qx", "qx  (→ Global X)", "Global X direction  —  + rightward"),
        ("qy", "qy  (↗ Global Y)", "Global Y direction  —  + into scene  (3D only)"),
    ]

    def _dl_populate(self) -> None:
        """Populate table from all load cases' dist_loads for this member."""
        self._dl_table.setRowCount(0)
        if not self._model_state:
            return
        for lc in self._model_state.load_cases:
            for dl in lc.get_member_load(self._member.id).dist_loads:
                if dl.direction == "qy" and not self._mode_3d:
                    continue
                if dl.direction == "qz":  # hidden from UI
                    continue
                self._dl_add_row(lc.id, lc.name, dl.direction, dl.w_start / 1e3, dl.w_end / 1e3)

    def _dl_add_entry(self, direction: str) -> None:
        """Add a new empty row for the given direction in the active case."""
        if self._load_case:
            self._dl_add_row(self._load_case.id, self._load_case.name, direction, 0.0, 0.0)

    def _dl_remove_row(self) -> None:
        rows = sorted({idx.row() for idx in self._dl_table.selectedIndexes()}, reverse=True)
        for r in rows:
            self._dl_table.removeRow(r)
        if not rows and self._dl_table.rowCount() > 0:
            self._dl_table.removeRow(self._dl_table.rowCount() - 1)

    def _dl_add_row(self, case_id: int, case_name: str,
                    direction_key: str, ws_kn: float, we_kn: float) -> None:
        row = self._dl_table.rowCount()
        self._dl_table.insertRow(row)
        # Case column (read-only, stores case_id in UserRole)
        ci = QTableWidgetItem(case_name)
        ci.setFlags(ci.flags() & ~Qt.ItemFlag.ItemIsEditable)
        ci.setData(Qt.ItemDataRole.UserRole, case_id)
        self._dl_table.setItem(row, 0, ci)
        # Direction column (read-only, stores direction key in UserRole)
        for dkey, dlabel, dtip in self._DL_DIRS:
            if dkey == direction_key:
                di = QTableWidgetItem(dlabel)
                di.setToolTip(dtip)
                di.setFlags(di.flags() & ~Qt.ItemFlag.ItemIsEditable)
                di.setData(Qt.ItemDataRole.UserRole, dkey)
                self._dl_table.setItem(row, 1, di)
                break
        self._dl_table.setCellWidget(row, 2, _spin(ws_kn, -1e6, 1e6, 1.0, 2))
        self._dl_table.setCellWidget(row, 3, _spin(we_kn, -1e6, 1e6, 1.0, 2))

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
        m.E       = self._E.value() * 1e9
        m.A       = self._A.value()
        m.I       = self._I.value() * 1e-6
        m.I_y     = self._Iy.value() * 1e-6
        m.J       = self._J.value() * 1e-6
        m.beta_angle = self._beta.value()
        m.density = self._density.value()
        m.n_sub   = self._nsub.value()
        m.fy      = self._fy.value() * 1e6
        m.W_pl    = self._Wpl.value() * 1e-6
        m.W_el    = self._Wel.value() * 1e-6
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
                ci   = self._dl_table.item(row, 0)
                di   = self._dl_table.item(row, 1)
                ws   = self._dl_table.cellWidget(row, 2)
                we   = self._dl_table.cellWidget(row, 3)
                if ci and di and ws and we:
                    cid = ci.data(Qt.ItemDataRole.UserRole)
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
        self._on_apply()


# ─────────────────────────────────────────────────────────────────────────────
# _MixedFilterForm
# ─────────────────────────────────────────────────────────────────────────────

def _build_section_lookup() -> dict[tuple[float, float], str]:
    """Return {(rounded_A, rounded_I): profile_name} from the section library."""
    try:
        from ui_qt.section_library import STEEL_PROFILES
        lookup: dict[tuple[float, float], str] = {}
        for _series, profiles in STEEL_PROFILES.items():
            for entry in profiles:
                name, A, I = entry[0], entry[1], entry[2]
                lookup[(round(A, 8), round(I, 12))] = name
        return lookup
    except Exception:
        return {}


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
                btn.clicked.connect(lambda _ids=ids: on_filter(set(), _ids))
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
                    btn_p.clicked.connect(lambda _ids=ids: on_filter(set(), _ids))
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

    def __init__(self, members: list, load_case: LoadCase | None,
                 on_apply, mode_3d: bool = False) -> None:
        super().__init__()
        self._members   = members
        self._load_case = load_case
        self._on_apply  = on_apply
        self._mode_3d   = mode_3d
        first = members[0]

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        hdr = QLabel(f"<b>{len(members)} members selected</b><br>"
                     "<small>Edits apply to all selected members</small>")
        hdr.setWordWrap(True)
        layout.addWidget(hdr)

        # ── element type ─────────────────────────────────────────────────────
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
        layout.addWidget(type_box)

        # ── section properties ─────────────────────────────────────────────
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

        self._mat_preset = QComboBox()
        self._mat_preset.addItems(["Steel (7850)", "Concrete (2500)", "Timber (500)", "Custom"])
        _PRESETS_M = [7850.0, 2500.0, 500.0]
        def _density_from_preset_m(idx: int, presets=_PRESETS_M) -> None:
            if idx < len(presets):
                self._density.setValue(presets[idx])
        self._mat_preset.currentIndexChanged.connect(_density_from_preset_m)
        sf.addRow("Material:", self._mat_preset)

        self._density = _spin(first.density, 0, 20000, 50, 0)
        self._density.setToolTip("0 = no self-weight contribution from this member")
        self._density.valueChanged.connect(lambda: self._mat_preset.setCurrentIndex(3))
        sf.addRow("Density (kg/m³):", self._density)

        self._mat_preset.blockSignals(True)
        for _i, _d in enumerate(_PRESETS_M):
            if abs(first.density - _d) < 1.0:
                self._mat_preset.setCurrentIndex(_i)
                break
        else:
            self._mat_preset.setCurrentIndex(3)
        self._mat_preset.blockSignals(False)

        layout.addWidget(sec_box)

        # ── distributed load (read from active load case for first member) ────
        first_ml = load_case.get_member_load(first.id) if load_case else MemberLoad()
        _w_s,  _w_e  = first_ml.net("w")
        _qx_s, _qx_e = first_ml.net("qx")
        _qy_s, _qy_e = first_ml.net("qy")
        _qz_s, _qz_e = first_ml.net("qz")
        load_box = QGroupBox("Distributed loads  [active case]")
        lf = QFormLayout(load_box)
        self._w_start  = _spin(_w_s  / 1e3, -1e6, 1e6, 1, 1)
        self._w_end    = _spin(_w_e  / 1e3, -1e6, 1e6, 1, 1)
        self._qx_start = _spin(_qx_s / 1e3, -1e6, 1e6, 1, 1)
        self._qx_end   = _spin(_qx_e / 1e3, -1e6, 1e6, 1, 1)
        self._qy_start = _spin(_qy_s / 1e3, -1e6, 1e6, 1, 1)
        self._qy_end   = _spin(_qy_e / 1e3, -1e6, 1e6, 1, 1)
        self._qz_start = _spin(_qz_s / 1e3, -1e6, 1e6, 1, 1)
        self._qz_end   = _spin(_qz_e / 1e3, -1e6, 1e6, 1, 1)
        lf.addRow("w start (kN/m):", self._w_start)
        lf.addRow("w end   (kN/m):", self._w_end)
        lf.addRow("", QLabel("Local ⊥ to member  —  ↓ positive"))
        lf.addRow("qx start (kN/m):", self._qx_start)
        lf.addRow("qx end   (kN/m):", self._qx_end)
        lf.addRow("", QLabel("Global X (→ right)  —  + rightward"))
        lf.addRow("qy start (kN/m):", self._qy_start)
        lf.addRow("qy end   (kN/m):", self._qy_end)
        lf.addRow("", QLabel("Global Y (↗ depth)  —  + into scene  (3D)"))
        lf.addRow("qz start (kN/m):", self._qz_start)
        lf.addRow("qz end   (kN/m):", self._qz_end)
        lf.addRow("", QLabel("Global Z (↓ gravity)  —  + downward  (3D)"))
        lf.setRowVisible(6,  mode_3d)
        lf.setRowVisible(7,  mode_3d)
        lf.setRowVisible(8,  mode_3d)
        lf.setRowVisible(9,  mode_3d)
        lf.setRowVisible(10, mode_3d)
        lf.setRowVisible(11, mode_3d)
        layout.addWidget(load_box)

        # ── mesh ──────────────────────────────────────────────────────────
        mesh_box = QGroupBox("Analysis mesh")
        mf = QFormLayout(mesh_box)
        self._nsub = QSpinBox()
        self._nsub.setRange(1, 100)
        self._nsub.setValue(first.n_sub)
        mf.addRow("Sub-elements:", self._nsub)
        layout.addWidget(mesh_box)

        btn = QPushButton(f"Apply to all {len(members)} members")
        btn.clicked.connect(self._apply)
        layout.addWidget(btn)

    def _pick_section(self) -> None:
        from ui_qt.section_picker import SectionPickerDialog
        dlg = SectionPickerDialog(
            current_E=self._E.value() * 1e9,
            current_A=self._A.value(),
            current_I=self._I.value() * 1e-6,
            parent=self,
        )
        if dlg.exec() and dlg.get_result():
            E, A, I, W_pl, W_el = dlg.get_result()
            self._E.setValue(E / 1e9)
            self._A.setValue(A)
            self._I.setValue(I * 1e6)

    def _apply(self) -> None:
        type_names = ["BEAM", "BAR", "PIN_LEFT", "PIN_RIGHT"]
        elem_type = ElementType[type_names[self._type_combo.currentIndex()]]
        E       = self._E.value() * 1e9
        A       = self._A.value()
        I       = self._I.value() * 1e-6
        density = self._density.value()
        n_sub   = self._nsub.value()
        w_start = self._w_start.value() * 1e3
        w_end   = self._w_end.value()   * 1e3
        for m in self._members:
            m.element_type = elem_type
            m.E       = E
            m.A       = A
            m.I       = I
            m.density = density
            m.n_sub   = n_sub
            if self._load_case is not None:
                _dl: list[DistLoad] = []
                _pairs = [
                    ("w",  w_start,                             w_end),
                    ("qx", self._qx_start.value() * 1e3,       self._qx_end.value()   * 1e3),
                    ("qy", self._qy_start.value() * 1e3,       self._qy_end.value()   * 1e3),
                    ("qz", self._qz_start.value() * 1e3,       self._qz_end.value()   * 1e3),
                ]
                for _dir, _ws, _we in _pairs:
                    if _ws != 0.0 or _we != 0.0:
                        _dl.append(DistLoad(_dir, _ws, _we))
                self._load_case.set_member_load(m.id, MemberLoad(dist_loads=_dl))
        self._on_apply()


# ─────────────────────────────────────────────────────────────────────────────
# _MultiNodeForm
# ─────────────────────────────────────────────────────────────────────────────

class _MultiNodeForm(QWidget):
    """Edit shared support and load properties across multiple selected nodes."""

    def __init__(self, nodes: list, load_case: LoadCase | None,
                 on_apply, mode_3d: bool = False) -> None:
        super().__init__()
        self._nodes     = nodes
        self._load_case = load_case
        self._on_apply  = on_apply
        self._mode_3d   = mode_3d
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
        if mode_3d:
            self._sup_names = ["FREE", "FIXED", "PIN", "ROLLER", "ROLLER_Y", "ROLLER_Z", "SPRING"]
            self._sup_combo.addItems(["Free", "Fixed", "Pinned", "Roller (vert)", "Roller (horiz)", "Roller (Z)", "Spring"])
        else:
            self._sup_names = ["FREE", "FIXED", "PIN", "ROLLER", "ROLLER_Y", "SPRING"]
            self._sup_combo.addItems(["Free", "Fixed", "Pinned", "Roller (vert)", "Roller (horiz)", "Spring"])
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
        self._kth = _spin(first.spring_ktheta, 0, 1e12, 1e5, 0)
        sg.addRow("k_x (N/m):",     self._kx)  # row 0
        sg.addRow("k_y (N/m):",     self._ky)  # row 1
        sg.addRow("k_θ (N·m/rad):", self._kth) # row 2
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
        lf.addRow("Fx (kN):",   self._fx)  # row 0
        lf.addRow("Fy (kN):",   self._fy)  # row 1
        lf.addRow("Fz (kN):",   self._fz)  # row 2
        lf.addRow("Mz (kN·m):", self._m)   # row 3
        lf.addRow("Mx (kN·m):", self._mx)  # row 4
        lf.addRow("My (kN·m):", self._my)  # row 5
        lf.setRowVisible(2, mode_3d)
        lf.setRowVisible(4, mode_3d)
        lf.setRowVisible(5, mode_3d)
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
        kth = self._kth.value()
        fx  = self._fx.value() * 1e3
        fy  = self._fy.value() * 1e3
        fz  = self._fz.value() * 1e3 if self._mode_3d else 0.0
        m   = self._m.value()  * 1e3
        mx  = self._mx.value() * 1e3 if self._mode_3d else 0.0
        my  = self._my.value() * 1e3 if self._mode_3d else 0.0
        for nd in self._nodes:
            nd.support_type  = sup_type
            nd.spring_kx     = kx
            nd.spring_ky     = ky
            nd.spring_ktheta = kth
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

        self._tabs.addTab(self._wrap(self._disp_table),  "Displacements")
        self._tabs.addTab(self._wrap(self._react_table), "Reactions")
        self._tabs.addTab(self._wrap(self._force_table), "Member forces")

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
        self._syncing = False   # guard: prevents table→canvas→table loops

        # Multi-row selection
        for tbl in (self._disp_table, self._react_table, self._force_table):
            tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            tbl.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)

        # Table → canvas signals
        self._disp_table.itemSelectionChanged.connect(
            lambda: self._emit_node_sel(self._disp_table, self._disp_row_to_node))
        self._react_table.itemSelectionChanged.connect(
            lambda: self._emit_node_sel(self._react_table, self._react_row_to_node))
        self._force_table.itemSelectionChanged.connect(self._emit_member_sel)

    # ── public ────────────────────────────────────────────────────────────────

    def populate(self, displacements, reactions, member_results, model_state,
                 dpn: int = 3, **kwargs) -> None:
        """Fill all three tables with solver results and rebuild row→ID maps.

        dpn: degrees of freedom per node — 3 for 2D models, 6 for 3D models.
        kwargs: sub_results, member_el_map — used for peak moment scanning.
        """
        self._restore_force_tab()
        for tbl in (self._disp_table, self._react_table, self._force_table):
            tbl.blockSignals(True)

        self._disp_row_to_node    = []
        self._react_row_to_node   = []
        self._force_row_to_member = []

        # θ_z is at DOF offset 2 in 2D and offset 5 in 3D
        rot_offset = 5 if dpn == 6 else 2

        # ── Displacements ──────────────────────────────────────────────────────
        self._disp_table.setRowCount(len(model_state.nodes))
        for row, nd in enumerate(model_state.nodes):
            base = nd.id * dpn
            dx = displacements[base]              * 1e3
            dy = displacements[base + 1]          * 1e3
            th = displacements[base + rot_offset] * 1e3
            self._set_row(self._disp_table, row,
                          [str(nd.id), f"{dx:.4f}", f"{dy:.4f}", f"{th:.4f}"])
            self._disp_row_to_node.append(nd.id)

        # ── Reactions ──────────────────────────────────────────────────────────
        react_rows = [nd for nd in model_state.nodes if nd.support_type.name != "FREE"]
        self._react_table.setRowCount(len(react_rows))
        for row, nd in enumerate(react_rows):
            base = nd.id * dpn
            fx = reactions[base]              / 1e3
            fy = reactions[base + 1]          / 1e3
            m  = reactions[base + rot_offset] / 1e3
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

        for tbl in (self._disp_table, self._react_table, self._force_table):
            tbl.blockSignals(False)

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

        for tbl in (self._disp_table, self._react_table, self._env_force_table):
            tbl.blockSignals(True)

        self._disp_row_to_node    = []
        self._react_row_to_node   = []
        self._force_row_to_member = []
        state = model_state
        n_runs = len(solve_runs)

        rot_offset = 5 if dpn == 6 else 2

        # ── Displacements ─────────────────────────────────────────────────────
        self._disp_table.setRowCount(len(state.nodes))
        for row, nd in enumerate(state.nodes):
            base = nd.id * dpn
            dx = max((r['displacements'][base]              for r in solve_runs), key=abs)
            dy = max((r['displacements'][base + 1]          for r in solve_runs), key=abs)
            th = max((r['displacements'][base + rot_offset] for r in solve_runs), key=abs)
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
            if runs_with_r:
                fx = max((r['reactions'][base]              for r in runs_with_r), key=abs)
                fy = max((r['reactions'][base + 1]          for r in runs_with_r), key=abs)
                m  = max((r['reactions'][base + rot_offset] for r in runs_with_r), key=abs)
            else:
                fx = fy = m = 0.0
            self._set_row(self._react_table, row, [
                str(nd.id),
                f"{fx / 1e3:.3f}", f"{fy / 1e3:.3f}", f"{m / 1e3:.3f}",
            ])
            self._react_row_to_node.append(nd.id)

        # ── Member forces (simplified 4-column envelope) ───────────────────────
        self._env_force_table.setRowCount(len(state.members))
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

        for tbl in (self._disp_table, self._react_table, self._env_force_table):
            tbl.blockSignals(False)

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
            self._highlight_rows(self._force_table, self._force_row_to_member, member_ids)
        finally:
            self._syncing = False

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

        ver_lbl = QLabel("V 1.1")
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
