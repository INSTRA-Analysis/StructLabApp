"""MainWindow: three-panel PyQt6 desktop layout for StructLab.

Layout:
  ┌──────────────┬──────────────────────────┬───────────────┐
  │  Properties  │  Canvas (QGraphicsView)  │  Results      │
  │  (left dock) │                          │  (right dock) │
  └──────────────┴──────────────────────────┴───────────────┘

Diagrams (BMD/SFD/AFD/Deformed) are drawn as QGraphicsItem overlays
directly on the canvas via StructCanvas.update_overlays().
"""

from __future__ import annotations

import os
from pathlib import Path
from PyQt6.QtWidgets import (
    QMainWindow, QToolBar, QStatusBar, QWidget,
    QDockWidget, QPushButton, QButtonGroup, QMessageBox,
    QFileDialog, QMenu, QMenuBar,
    QLabel, QDoubleSpinBox, QComboBox, QGraphicsView,
    QScrollArea, QVBoxLayout, QHBoxLayout,
)
from PyQt6.QtCore import Qt, QSize, QTimer
from PyQt6.QtGui import QColor

from ui_qt.canvas import StructCanvas, StructView, CanvasMode, WorkingPlane
from ui_qt.model_state import ElementType
from ui_qt.panels import PropertiesPanel, ResultsPanel, BrandingFooter

_AUTOSAVE_PATH = Path.home() / ".structlab" / "autosave.slab"


def _plane_for_view(az: float, el: float) -> WorkingPlane:
    """Return the natural working plane for a named view direction."""
    if el > 60.0 or el < -60.0:
        return WorkingPlane.XY          # Top / Bottom
    if el > 20.0:
        return WorkingPlane.FREE        # ISO corner views
    # Low-elevation face views — pick XZ (Front/Back) or YZ (Left/Right)
    az_norm = ((az % 360) + 360) % 360
    if az_norm > 180:
        az_norm -= 360                  # normalise to [-180, 180]
    if abs(az_norm) < 45 or abs(az_norm) > 135:
        return WorkingPlane.XZ          # Front (0°) or Back (±180°)
    return WorkingPlane.YZ              # Right (90°) or Left (-90°)

_DOCK_HDR = (
    "background:#00ACC1; color:#ffffff;"
    " font-size:11px; font-weight:bold; padding-left:6px;"
)

_DOCK_BTN = (
    "QPushButton { background: transparent; color: #ffffff; border: none;"
    " font-size: 13px; padding: 0 2px; }"
    "QPushButton:hover { background: rgba(255,255,255,50); border-radius: 2px; }"
)


class _DockTitleBar(QWidget):
    """Cyan title bar for a QDockWidget.

    Double-click or the ⧉ button floats/re-docks the panel.
    The × button hides it (restore via View menu or keyboard shortcut).
    """

    def __init__(self, title: str, dock: QDockWidget) -> None:
        super().__init__()
        self._dock = dock
        self.setFixedHeight(22)
        self.setStyleSheet(_DOCK_HDR)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 4, 0)
        layout.setSpacing(2)

        lbl = QLabel(title)
        lbl.setStyleSheet("background: transparent;")
        layout.addWidget(lbl)
        layout.addStretch()

        self._float_btn = QPushButton("⧉")
        self._float_btn.setFixedSize(20, 18)
        self._float_btn.setToolTip("Detach to floating window  (double-click title to toggle)")
        self._float_btn.setStyleSheet(_DOCK_BTN)
        self._float_btn.clicked.connect(self._toggle_float)
        layout.addWidget(self._float_btn)

        hide_btn = QPushButton("✕")
        hide_btn.setFixedSize(20, 18)
        hide_btn.setToolTip("Hide panel  (restore via View menu)")
        hide_btn.setStyleSheet(_DOCK_BTN)
        hide_btn.clicked.connect(dock.hide)
        layout.addWidget(hide_btn)

        dock.topLevelChanged.connect(self._on_float_changed)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        self._toggle_float()

    def _toggle_float(self) -> None:
        self._dock.setFloating(not self._dock.isFloating())

    def _on_float_changed(self, floating: bool) -> None:
        if floating:
            self._float_btn.setText("⊟")
            self._float_btn.setToolTip("Re-dock panel")
        else:
            self._float_btn.setText("⧉")
            self._float_btn.setToolTip("Detach to floating window  (double-click title to toggle)")


class MainWindow(QMainWindow):
    """Top-level application window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("StructLab V1.0.0 — Structural Analysis")
        self.resize(1280, 800)
        # Hide toolbar drag handles (toolbars remain movable for auto-wrap, not drag)
        self.setStyleSheet("QToolBar::handle { width: 0px; height: 0px; }")

        # Solve cache: populated after a successful solve, None otherwise
        self._solve_cache: dict | None = None
        self._all_combos_cache: list | None = None   # populated after Solve All
        self._syncing_selection = False   # guard against canvas↔table loops

        # Dirty tracking
        self._is_dirty: bool = False
        self._filepath: str | None = None

        # Copy/paste clipboard (in-process only)
        self._clipboard: dict | None = None

        self._build_canvas()
        self._build_menu()
        self._build_toolbar()
        self.addToolBarBreak(Qt.ToolBarArea.TopToolBarArea)
        self._build_overlay_toolbar()
        self.addToolBarBreak(Qt.ToolBarArea.TopToolBarArea)
        self._build_view_toolbar()
        self._build_docks()
        self._build_view_menu()
        self._build_status_bar()
        self._wire_selection()
        self._setup_autosave()
        recovered = self._check_autosave_recovery()
        if not recovered:
            self._show_welcome()

    # ── canvas ────────────────────────────────────────────────────────────────

    def _build_canvas(self) -> None:
        self._scene = StructCanvas()
        self._view  = StructView(self._scene)
        self.setCentralWidget(self._view)
        self._scene.model_changed.connect(self._on_model_changed)
        self._scene.view_changed.connect(self._redraw_overlays)
        self._scene.view_preset.connect(self._on_view_preset)
        self._scene.plane_offset_changed.connect(self._on_scene_plane_offset_changed)

    # ── menu bar ─────────────────────────────────────────────────────────────

    def _build_menu(self) -> None:
        from ui_qt import presets as P
        mb = self.menuBar()

        file_menu = mb.addMenu("File")
        file_menu.addAction("New",      "Ctrl+N",       self._on_new)
        file_menu.addAction("Open…",   "Ctrl+O",       self._on_open)
        file_menu.addAction("Save",    "Ctrl+S",       self._on_save)
        file_menu.addAction("Save As…","Ctrl+Shift+S", self._on_save_as)
        file_menu.addSeparator()
        file_menu.addAction("Project Info…", self._on_project_info)
        file_menu.addSeparator()
        self._recent_menu = file_menu.addMenu("Recent Files")
        self._recent_menu.aboutToShow.connect(self._rebuild_recent_menu)
        file_menu.addSeparator()
        import_menu = file_menu.addMenu("Import")
        import_menu.addAction("From CSV…", self._on_import_csv)
        export_menu = file_menu.addMenu("Export")
        export_menu.addAction("PNG Image…",  self._on_export_png)
        export_menu.addAction("SVG Vector…", self._on_export_svg)
        export_menu.addAction("PDF Report…", self._on_export_pdf)

        self._build_edit_menu(mb)
        self._build_selection_menu(mb)
        self._build_tools_menu(mb)
        self._build_help_menu(mb)

        preset_menu = mb.addMenu("Presets")

        def _section(title: str) -> None:
            a = preset_menu.addAction(f"  {title}")
            a.setEnabled(False)
            f = a.font(); f.setBold(True); a.setFont(f)

        def _add(label: str, fn) -> None:
            preset_menu.addAction(label, lambda _=None, f=fn: self._load_preset(f))

        _section("── Beams ───────────────────")
        _add("Steel Beam — IPE 400, SS, UDL + P",          P.demo_beam_steel)
        _add("RC Propped Cantilever — C30/37",              P.demo_beam_rc)
        _add("Steel Beam — IPE 360, elastic design (S355)", P.design_steel_beam)
        _add("RC Beam — 300×500, concrete design (C30)",    P.design_rc_beam)
        _add("Steel Cantilevered Canopy — UVL wind uplift", P.steel_cantilevered_canopy)
        _add("RC Transfer Beam — C35/45, 600×1800 mm",     P.rc_transfer_beam)
        _add("RC Bridge Deck — C35/45, 4 × 10 m",          P.rc_continuous_bridge)

        preset_menu.addSeparator()
        _section("── Frames ──────────────────")
        _add("Steel Portal Frame — S355, G+Q+W",                     P.demo_frame_steel)
        _add("RC Moment Frame — C30/37, 2-bay 3-storey",              P.demo_frame_rc)
        _add("Steel Portal Frame — Wind Distributed on Columns (qx)", P.demo_wind_portal_qx)
        _add("Steel Industrial Portal — HEB 340 + IPE 500, G+Q+W",   P.steel_industrial_portal)
        _add("RC Building Frame — C30/37, 2-bay 2-storey",            P.rc_moment_frame)
        _add("Steel Vierendeel Bridge — S355, 15 m, 5 panels",        P.steel_vierendeel_bridge)

        preset_menu.addSeparator()
        _section("── Trusses ─────────────────")
        _add("Pratt Roof Truss — SHS 200, 8 panels",            P.demo_truss_pratt)
        _add("3D Pratt Space Truss — SHS, 12×4 m, 4 panels",   P.demo_3d_pratt_roof)

        preset_menu.addSeparator()
        _section("── Mixed & Special ─────────")
        _add("Beam + Bar Strut — mixed IPE 360 + SHS", P.demo_mixed)
        _add("Spring-Supported Beam — IPE 300, 1 MN/m", P.demo_spring_beam)

        preset_menu.addSeparator()
        _section("── 3D Structures ───────────")
        _add("3D Portal Frame — S355, 6×4×3 m",          P.demo_3d_portal)
        _add("3D Floor Grid — HEB 220 + IPE 300, 3×3 bays", P.demo_3d_floor_grid)
        _add("Space Truss Tower — SHS, 2×2×4 m",          P.demo_space_truss)

        preset_menu.addSeparator()
        _section("── Wizards ─────────────────")
        preset_menu.addAction("Beam Wizard…",         self._on_beam_wizard)
        preset_menu.addAction("Portal Frame Wizard…", self._on_portal_wizard)
        preset_menu.addAction("Truss Wizard…",        self._on_truss_wizard)
        preset_menu.addAction("Frame Wizard…",        self._on_frame_wizard)

    # ── Edit menu ─────────────────────────────────────────────────────────────

    def _build_edit_menu(self, mb) -> None:
        edit_menu = mb.addMenu("Edit")
        edit_menu.addAction("Undo",      "Ctrl+Z", self._scene.undo)
        edit_menu.addAction("Redo",      "Ctrl+Y", self._scene.redo)
        edit_menu.addSeparator()
        edit_menu.addAction("Copy",      "Ctrl+C", self._on_copy)
        edit_menu.addAction("Paste",     "Ctrl+V", self._on_paste)
        edit_menu.addAction("Duplicate", "Ctrl+D", self._on_duplicate)
        edit_menu.addSeparator()
        edit_menu.addAction("Solve",        "F5", self._on_solve)
        edit_menu.addAction("Zoom to Fit",  "F",  self._view.zoom_to_fit)

    # ── Selection menu ────────────────────────────────────────────────────────

    def _batch_select(self, action) -> None:
        """Execute *action* with selectionChanged signals blocked, then
        fire the selection-changed handler exactly once."""
        self._scene.blockSignals(True)
        try:
            action()
        finally:
            self._scene.blockSignals(False)
            self._on_selection_changed()

    def _build_selection_menu(self, mb) -> None:
        edit_menu = mb.addMenu("Selection")

        edit_menu.addAction("Select All",      "Ctrl+A",        self._on_select_all)
        edit_menu.addAction("Deselect All",    "Ctrl+Shift+A",  self._on_deselect_all)
        edit_menu.addAction("Invert Selection","Ctrl+I",        self._on_invert_selection)
        edit_menu.addSeparator()

        # ── Select by Element Type submenu ─────────────────────────────────
        type_menu = edit_menu.addMenu("Select by Element Type")
        from ui_qt.model_state import ElementType as ET
        for et in ET:
            label = et.name.replace("_", " ").title()
            type_menu.addAction(label, lambda *args, et=et: self._on_select_by_type(et))

        # ── Select by Profile submenu (built lazily on aboutToShow) ───────
        self._select_profile_menu = edit_menu.addMenu("Select by Profile")
        self._select_profile_menu.aboutToShow.connect(self._rebuild_select_profile_menu)

    def _on_select_all(self) -> None:
        """Select all nodes and members on the canvas."""
        def _do():
            for item in self._scene.items():
                item.setSelected(True)
        self._batch_select(_do)

    def _on_deselect_all(self) -> None:
        """Clear the current selection."""
        self._scene.clearSelection()

    def _on_invert_selection(self) -> None:
        """Invert the current selection."""
        def _do():
            for item in self._scene.items():
                item.setSelected(not item.isSelected())
        self._batch_select(_do)

    def _on_select_by_type(self, element_type) -> None:
        """Select all members of a given ElementType."""
        from ui_qt.canvas_items import MemberItem
        ms = self._scene.model_state
        def _do():
            for item in self._scene.items():
                if isinstance(item, MemberItem):
                    member = ms.get_member(item.member.id)
                    if member and member.element_type == element_type:
                        item.setSelected(True)
        self._batch_select(_do)

    # ── Profile name resolution ───────────────────────────────────────────────

    @staticmethod
    def _resolve_profile_name(E: float, A: float, I: float) -> str:
        """Try to reverse-lookup a section library name from (E, A, I).
        Returns a display string like 'IPE 400' or 'Custom (E=210 GPa, A=0.00845 m²)'.
        """
        from ui_qt.section_library import STEEL_PROFILES
        EPS = 1e-8  # tolerance for floating-point equality
        for series, profiles in STEEL_PROFILES.items():
            for name, pA, pI in profiles:
                if abs(A - pA) < EPS * max(A, 1.0) and abs(I - pI) < EPS * max(I, 1.0):
                    return name
        # No exact match — build a descriptive label
        E_gpa = E / 1e9
        return f"Custom  (E={E_gpa:.0f} GPa,  A={A:.4g} m²,  I={I:.4g} m⁴)"

    def _rebuild_select_profile_menu(self) -> None:
        """Dynamically rebuild the 'Select by Profile' submenu from current members."""
        menu = self._select_profile_menu
        menu.clear()

        ms = self._scene.model_state

        # Group members by (E, A, I) tuple, collecting member IDs
        profile_groups: dict[tuple, list[int]] = {}
        for member in ms.members:
            key = (member.E, member.A, member.I)
            profile_groups.setdefault(key, []).append(member.id)

        if not profile_groups:
            a = menu.addAction("(no members)")
            a.setEnabled(False)
            return

        # Sort groups by member count (largest first), then by A descending
        sorted_groups = sorted(
            profile_groups.items(),
            key=lambda kv: (-len(kv[1]), -kv[0][1]),
        )

        for (E, A, I), member_ids in sorted_groups:
            label = self._resolve_profile_name(E, A, I)
            count = len(member_ids)
            action_label = f"{label}   [{count} member{'s' if count != 1 else ''}]"
            menu.addAction(action_label, lambda *args, mids=member_ids: self._on_select_by_member_ids(mids))

    def _on_select_by_member_ids(self, member_ids: list[int]) -> None:
        """Select all members whose IDs are in the given list."""
        def _do():
            for mid in member_ids:
                item = self._scene.get_member_item(mid)
                if item:
                    item.setSelected(True)
        self._batch_select(_do)

    # ── help menu ─────────────────────────────────────────────────────────────

    def _build_help_menu(self, mb) -> None:
        help_menu = mb.addMenu("Help")
        help_menu.addAction("Keyboard Shortcuts…", self._on_keyboard_shortcuts)
        help_menu.addSeparator()
        help_menu.addAction("About StructLab…", self._on_about)

    def _build_tools_menu(self, mb) -> None:
        from PyQt6.QtGui import QKeySequence
        tools_menu = mb.addMenu("Tools")
        act = tools_menu.addAction("Python Console", self._open_console)
        act.setShortcut(QKeySequence("Ctrl+`"))

    def _open_console(self) -> None:
        from ui_qt.console import ConsoleDialog
        if not hasattr(self, "_console_dialog") or self._console_dialog is None:
            self._console_dialog = ConsoleDialog(
                self._scene.model_state, parent=self
            )
            self._console_dialog.finished.connect(
                lambda: setattr(self, "_console_dialog", None)
            )
        self._console_dialog.show()
        self._console_dialog.raise_()
        self._console_dialog.activateWindow()

    def _on_keyboard_shortcuts(self) -> None:
        from ui_qt.dialogs import show_keyboard_shortcuts
        show_keyboard_shortcuts(self)

    def _on_about(self) -> None:
        from ui_qt.dialogs import show_about
        show_about(self)

    # ── view menu (built after docks exist) ───────────────────────────────────

    def _build_view_menu(self) -> None:
        """Add a View menu that toggles the two dock panels.

        Must be called after _build_docks() so self._left_dock / _right_dock exist.
        """
        mb = self.menuBar()
        view_menu = mb.addMenu("View")

        act_props = self._left_dock.toggleViewAction()
        act_props.setText("Properties Panel")
        act_props.setShortcut("Alt+1")
        view_menu.addAction(act_props)

        act_res = self._right_dock.toggleViewAction()
        act_res.setText("Results Panel")
        act_res.setShortcut("Alt+2")
        view_menu.addAction(act_res)

        view_menu.addSeparator()
        view_menu.addAction("Reset Panel Layout", self._reset_dock_layout)

    def _reset_dock_layout(self) -> None:
        """Return both panels to their default docked positions."""
        for dock in (self._left_dock, self._right_dock):
            dock.setFloating(False)
            dock.show()
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea,  self._left_dock)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._right_dock)

    def _on_toggle_local_axes(self, checked: bool) -> None:
        from ui_qt.canvas_items import set_show_local_axes
        set_show_local_axes(checked)
        self._scene.update()

    def _set_working_plane(self, plane: WorkingPlane) -> None:
        """Switch the canvas working plane and sync toolbar button + label states."""
        self._active_plane = plane
        self._scene.set_working_plane(plane)
        for p, btn in self._plane_btns.items():
            btn.setChecked(p == plane)
        _label = {WorkingPlane.XY: " Z =", WorkingPlane.XZ: " Y =", WorkingPlane.YZ: " X ="}
        self._plane_label.setText(_label.get(plane, ""))
        show_offset = plane != WorkingPlane.FREE
        self._plane_label.setVisible(show_offset)
        self._plane_spin.setVisible(show_offset)
        if show_offset:
            # Restore this plane's remembered offset without triggering a save-back
            restored = self._plane_offsets.get(plane, 0.0)
            self._plane_spin.blockSignals(True)
            self._plane_spin.setValue(restored)
            self._plane_spin.blockSignals(False)
            self._scene.set_plane_offset(restored)

    def _on_plane_offset_changed(self, value: float) -> None:
        """Spin-box changed: push to scene (signal chain syncs per-plane memory)."""
        self._scene.set_plane_offset(value)

    def _on_scene_plane_offset_changed(self, value: float) -> None:
        """Scene offset changed from any source: sync spinbox and per-plane memory."""
        self._plane_spin.blockSignals(True)
        self._plane_spin.setValue(value)
        self._plane_spin.blockSignals(False)
        if self._active_plane != WorkingPlane.FREE:
            self._plane_offsets[self._active_plane] = value

    def _on_set_view(self, azimuth: float, elevation: float,
                     plane: WorkingPlane | None = None) -> None:
        self._scene.set_view(azimuth, elevation)
        if plane is not None:
            self._set_working_plane(plane)
        self._on_combo_view_changed(self._combo_view.currentIndex())

    def _on_view_preset(self, az: float, el: float) -> None:
        """Called when ViewCube face or numpad face-key snaps to a named view.

        Derives and sets the matching working plane automatically.
        """
        self._set_working_plane(_plane_for_view(az, el))

    # ── welcome screen ────────────────────────────────────────────────────────

    def _show_welcome(self) -> None:
        from ui_qt.welcome_dialog import WelcomeDialog
        from ui_qt import recent_files as RF
        from PyQt6.QtWidgets import QDialog

        dlg = WelcomeDialog(self, recent_files=RF.load())
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return  # closed without choosing → blank canvas

        choice = dlg.choice
        from ui_qt import presets as P
        if choice == "beam":
            self._apply_model_state(P.demo_beam_steel(), "Steel Beam")
        elif choice == "frame":
            self._apply_model_state(P.demo_3d_portal(), "3D Portal Frame")
        elif choice == "truss":
            self._apply_model_state(P.demo_space_truss(), "Space Truss")
        elif choice == "blank":
            from ui_qt.model_state import ModelState
            self._apply_model_state(ModelState(), "Blank")
        elif choice.startswith("file:"):
            self._open_file(choice[5:])
        elif choice == "open":
            self._on_open()

    def _rebuild_recent_menu(self) -> None:
        from ui_qt import recent_files as RF
        self._recent_menu.clear()
        paths = RF.load()
        if not paths:
            a = self._recent_menu.addAction("(none)")
            a.setEnabled(False)
            return
        for path in paths:
            self._recent_menu.addAction(
                Path(path).name,
                lambda _=None, p=path: self._open_file(p),
            ).setToolTip(path)

    def _open_file(self, path: str) -> None:
        """Open a .slab file by path without showing a file dialog."""
        from ui_qt.io import load_model
        from ui_qt import recent_files as RF
        try:
            state = load_model(path)
            self._scene.load_state(state)
            self._scene._hide_welcome = True
            self._props_panel.set_model_state(self._scene.model_state)
            self._refresh_lc_combo()
            self._results_panel.clear()
            self._scene.clear_overlays()
            self._solve_cache = None
            self._reset_combo_view()
            self._set_overlay_controls_enabled(False)
            self._view.zoom_to_fit()
            self._is_dirty = False
            self._filepath = path
            _AUTOSAVE_PATH.unlink(missing_ok=True)
            self._update_title()
            self._update_status_stats()
            self._sb.showMessage(f"Opened: {path}")
            RF.push(path)
        except Exception as exc:
            QMessageBox.critical(self, "Open error", str(exc))

    def _load_preset(self, fn) -> None:
        self._apply_model_state(fn(), fn.__name__.replace("_", " ").title())

    def _apply_model_state(self, state, label: str = "") -> None:
        """Load a ModelState onto the canvas, clearing any prior results."""
        self._scene.load_state(state)
        self._scene._hide_welcome = True
        self._props_panel.set_model_state(self._scene.model_state)
        self._refresh_lc_combo()
        self._results_panel.clear()
        self._scene.clear_overlays()
        self._solve_cache = None
        self._reset_combo_view()
        self._set_overlay_controls_enabled(False)
        self._view.zoom_to_fit()
        self._is_dirty = False
        self._filepath = None
        self._update_title()
        self._sb.showMessage(f"Loaded: {label}" if label else "Preset loaded")
        self._update_status_stats()

    def _on_frame_wizard(self) -> None:
        from PyQt6.QtWidgets import (
            QDialog, QFormLayout, QSpinBox, QDoubleSpinBox,
            QDialogButtonBox, QVBoxLayout,
        )
        dlg = QDialog(self)
        dlg.setWindowTitle("Frame Wizard")
        layout = QVBoxLayout(dlg)
        form = QFormLayout()

        bays_sb   = QSpinBox(); bays_sb.setRange(1, 20);  bays_sb.setValue(2)
        stories_sb = QSpinBox(); stories_sb.setRange(1, 30); stories_sb.setValue(3)
        width_sb  = QDoubleSpinBox(); width_sb.setRange(1, 50);  width_sb.setValue(6.0); width_sb.setSuffix(" m")
        height_sb = QDoubleSpinBox(); height_sb.setRange(1, 20); height_sb.setValue(3.0); height_sb.setSuffix(" m")

        form.addRow("Number of bays:",   bays_sb)
        form.addRow("Number of stories:", stories_sb)
        form.addRow("Bay width:",         width_sb)
        form.addRow("Story height:",      height_sb)
        layout.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            from ui_qt.presets import frame_wizard
            state = frame_wizard(bays_sb.value(), stories_sb.value(),
                                 width_sb.value(), height_sb.value())
            self._apply_model_state(
                state,
                f"Frame Wizard — {bays_sb.value()} bays × {stories_sb.value()} stories",
            )

    def _on_beam_wizard(self) -> None:
        from PyQt6.QtWidgets import QDialog
        from ui_qt.wizards import BeamWizardDialog
        dlg = BeamWizardDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.result():
            self._apply_model_state(dlg.result(), "Beam Wizard")

    def _on_portal_wizard(self) -> None:
        from PyQt6.QtWidgets import QDialog
        from ui_qt.wizards import PortalWizardDialog
        dlg = PortalWizardDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.result():
            self._apply_model_state(dlg.result(), "Portal Frame Wizard")

    def _on_truss_wizard(self) -> None:
        from PyQt6.QtWidgets import QDialog
        from ui_qt.wizards import TrussWizardDialog
        dlg = TrussWizardDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.result():
            self._apply_model_state(dlg.result(), "Truss Wizard")

    # ── helpers ───────────────────────────────────────────────────────────────

    def _add_section_divider(self, toolbar: QToolBar, label: str = "") -> None:
        """Add a styled visual divider (spacer or labeled separator) to toolbar."""
        # Add spacing before divider
        spacer = QWidget()
        spacer.setFixedWidth(8)
        toolbar.addWidget(spacer)

        # Add the divider line (using a label with background styling)
        divider = QLabel("│")
        divider.setStyleSheet("color: #666666; font-weight: bold; padding: 0px 6px;")
        toolbar.addWidget(divider)

        # Add optional label
        if label:
            lbl = QLabel(f"  {label}  ")
            lbl.setStyleSheet("color: #000000; font-size: 9px; font-weight: bold; background-color: #ffffff; padding: 2px 6px; border-radius: 3px;")
            toolbar.addWidget(lbl)

            divider2 = QLabel("│")
            divider2.setStyleSheet("color: #666666; font-weight: bold; padding: 0px 6px;")
            toolbar.addWidget(divider2)

        # Add spacing after divider
        spacer2 = QWidget()
        spacer2.setFixedWidth(8)
        toolbar.addWidget(spacer2)

    # ── main toolbar ──────────────────────────────────────────────────────────

    def _build_toolbar(self) -> None:
        tb = QToolBar("Main")
        tb.setMovable(True)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb)

        # ── file buttons ─────────────────────────────────────────────────────
        for label, slot in [("New", self._on_new), ("Open", self._on_open),
                             ("Save", self._on_save)]:
            btn = QPushButton(label)
            btn.clicked.connect(slot)
            tb.addWidget(btn)

        close_btn = QPushButton("✕ Close")
        close_btn.setToolTip("Close current model (prompts to save if unsaved)")
        close_btn.clicked.connect(self._on_close_model)
        close_btn.setStyleSheet(
            "QPushButton { color: #e74c3c; }"
            "QPushButton:hover { background: #c0392b; color: white; }"
        )
        tb.addWidget(close_btn)

        tb.addSeparator()

        # ── mode toggle buttons ───────────────────────────────────────────────
        self._mode_buttons: dict[CanvasMode, QPushButton] = {}
        self._mode_group = QButtonGroup(self)
        self._mode_group.setExclusive(True)

        mode_defs = [
            (CanvasMode.SELECT,     "Select",    "S"),
            (CanvasMode.ADD_NODE,   "Add Node",  "N"),
            (CanvasMode.ADD_MEMBER, "Add Member","M"),
        ]
        for mode, label, shortcut in mode_defs:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setShortcut(shortcut)
            btn.clicked.connect(lambda _checked, m=mode: self._set_mode(m))
            self._mode_group.addButton(btn)
            self._mode_buttons[mode] = btn
            tb.addWidget(btn)

        self._mode_buttons[CanvasMode.SELECT].setChecked(True)
        self._scene.set_mode(CanvasMode.SELECT)
        self._view.setDragMode(QGraphicsView.DragMode.NoDrag)

        # ── member type selector ───────────────────────────────────────────────
        tb.addWidget(QLabel(" Type:"))
        self._member_type_combo = QComboBox()
        self._member_type_combo.addItems([et.name for et in ElementType])
        self._member_type_combo.setCurrentIndex(0)  # default BEAM
        self._member_type_combo.currentTextChanged.connect(self._on_member_type_changed)
        tb.addWidget(self._member_type_combo)

        tb.addSeparator()

        # ── load case selector ─────────────────────────────────────────────────
        tb.addWidget(QLabel(" Case:"))
        self._lc_combo = QComboBox()
        self._lc_combo.setMinimumWidth(140)
        self._lc_combo.currentIndexChanged.connect(self._on_lc_changed)
        tb.addWidget(self._lc_combo)

        _btn_base = (
            "QPushButton {{"
            "  font-weight: bold; color: white;"
            "  border-radius: 3px; padding: 3px 6px;"
            "  background-color: {bg};"
            "}}"
            "QPushButton:hover {{ background-color: {hover}; }}"
            "QPushButton:pressed {{ background-color: {pressed}; }}"
            "QPushButton:disabled {{ background-color: #555555; color: #888888; }}"
        )

        add_lc_btn = QPushButton("+")
        add_lc_btn.setFixedWidth(26)
        add_lc_btn.setToolTip("Add new load case")
        add_lc_btn.setStyleSheet(
            _btn_base.format(bg="#27ae60", hover="#2ecc71", pressed="#1e8449")
        )
        add_lc_btn.clicked.connect(self._on_add_lc)
        tb.addWidget(add_lc_btn)

        self._remove_lc_btn = QPushButton("−")
        self._remove_lc_btn.setFixedWidth(26)
        self._remove_lc_btn.setToolTip("Remove active load case")
        self._remove_lc_btn.setStyleSheet(
            _btn_base.format(bg="#c0392b", hover="#e74c3c", pressed="#922b21")
        )
        self._remove_lc_btn.clicked.connect(self._on_remove_lc)
        tb.addWidget(self._remove_lc_btn)

        self._sw_btn = QPushButton("SW")
        self._sw_btn.setCheckable(True)
        self._sw_btn.setToolTip(
            "Self-weight: include member self-weight in this load case.\n"
            "Only one case can carry self-weight at a time.\n"
            "Requires member density > 0 (set in Member Properties)."
        )
        self._sw_btn.toggled.connect(self._on_sw_toggle)
        tb.addWidget(self._sw_btn)

        self._refresh_lc_combo()

        tb.addSeparator()

        # ── solve ─────────────────────────────────────────────────────────────
        solve_btn = QPushButton("Solve")
        solve_btn.setShortcut("F5")
        solve_btn.setToolTip("Solve active load case (F5)")
        solve_btn.setStyleSheet(
            "QPushButton { "
            "  font-weight: bold; "
            "  background-color: #2196F3; "
            "  color: white; "
            "  padding: 6px 16px; "
            "  border-radius: 3px; "
            "} "
            "QPushButton:hover { background-color: #1976D2; } "
            "QPushButton:pressed { background-color: #0D47A1; }"
        )
        solve_btn.clicked.connect(self._on_solve)
        tb.addWidget(solve_btn)

        combs_btn = QPushButton("Combinations…")
        combs_btn.setToolTip("Manage EN 1990 load combinations and solve")
        combs_btn.setStyleSheet(
            "QPushButton { "
            "  font-weight: bold; "
            "  background-color: #6A1B9A; "
            "  color: white; "
            "  padding: 6px 14px; "
            "  border-radius: 3px; "
            "} "
            "QPushButton:hover { background-color: #7B1FA2; } "
            "QPushButton:pressed { background-color: #4A148C; }"
        )
        combs_btn.clicked.connect(self._on_combinations)
        tb.addWidget(combs_btn)

    # ── overlay toolbar ───────────────────────────────────────────────────────

    def _build_overlay_toolbar(self) -> None:
        tb = QToolBar("Visualization")
        tb.setMovable(True)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb)

        # ── clear results ─────────────────────────────────────────────────────
        clr_btn = QPushButton("Clear Results")
        clr_btn.clicked.connect(self._on_clear_results)
        tb.addWidget(clr_btn)

        tb.addSeparator()

        # 5 checkable layer-toggle buttons
        layers = [
            ('BMD',    True),
            ('SFD',    False),
            ('AFD',    False),
            ('Def',    True),
            ('Labels', False),
        ]
        self._overlay_btns: dict[str, QPushButton] = {}
        for name, default in layers:
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setChecked(default)
            key = 'Deformed' if name == 'Def' else name
            btn.toggled.connect(lambda checked, k=key: self._on_overlay_toggle(k, checked))
            self._overlay_btns[name] = btn
            tb.addWidget(btn)

        tb.addSeparator()

        # Force colour toggle
        self._force_colour_btn = QPushButton("Force colours")
        self._force_colour_btn.setCheckable(True)
        self._force_colour_btn.setChecked(False)
        self._force_colour_btn.toggled.connect(self._on_force_colour_toggle)
        tb.addWidget(self._force_colour_btn)

        # Utilization colour toggle
        self._util_colour_btn = QPushButton("Util %")
        self._util_colour_btn.setCheckable(True)
        self._util_colour_btn.setChecked(False)
        self._util_colour_btn.setToolTip(
            "Colour members by EC3 utilization ratio η = N/Npl + M/Mpl\n"
            "Green < 50%  ·  Yellow = 50–100%  ·  Red > 100%"
        )
        self._util_colour_btn.toggled.connect(self._on_util_colour_toggle)
        tb.addWidget(self._util_colour_btn)

        tb.addSeparator()

        # Diagram scale spinbox
        tb.addWidget(QLabel("  Diag ×:"))
        self._diag_scale_spin = QDoubleSpinBox()
        self._diag_scale_spin.setRange(0.01, 10000.0)
        self._diag_scale_spin.setValue(30.0)
        self._diag_scale_spin.setSingleStep(10.0)
        self._diag_scale_spin.setDecimals(2)
        self._diag_scale_spin.setFixedWidth(95)
        self._diag_scale_spin.valueChanged.connect(self._redraw_overlays)
        tb.addWidget(self._diag_scale_spin)

        # Deformed scale spinbox
        tb.addWidget(QLabel("  Def ×:"))
        self._def_scale_spin = QDoubleSpinBox()
        self._def_scale_spin.setRange(0.01, 100000.0)
        self._def_scale_spin.setValue(5.0)
        self._def_scale_spin.setSingleStep(1.0)
        self._def_scale_spin.setDecimals(1)
        self._def_scale_spin.setFixedWidth(95)
        self._def_scale_spin.valueChanged.connect(self._redraw_overlays)
        tb.addWidget(self._def_scale_spin)

        # ── combo view selector ────────────────────────────────────────────────
        tb.addSeparator()

        self._combo_view = QComboBox()
        self._combo_view.setMinimumWidth(300)
        self._combo_view.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToContents
        )
        self._combo_view.addItem("Active case", userData="active")
        self._combo_view.setEnabled(False)   # enabled after Solve All & Envelope
        self._combo_view.currentIndexChanged.connect(self._on_combo_view_changed)
        tb.addWidget(self._combo_view)

        # All overlay controls disabled until after a successful solve
        self._set_overlay_controls_enabled(False)

    # ── 3D view preset toolbar ────────────────────────────────────────────────

    def _build_view_toolbar(self) -> None:
        """Preset view buttons + working plane controls — visible only in 3D mode."""
        self._view_tb = QToolBar("3D View Presets")
        self._view_tb.setMovable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self._view_tb)

        # ── Camera preset buttons ──────────────────────────────────────────────
        self._view_tb.addWidget(QLabel(" View: "))

        _VIEWS = [
            ("Top",    0.0,    87.0, "Plan view — looking from above",               WorkingPlane.XY),
            ("Front",  0.0,     2.0, "Front elevation — XZ plane (Ctrl+drag orbit)", WorkingPlane.XZ),
            ("Left",  -90.0,    2.0, "Left side elevation — YZ plane",               WorkingPlane.YZ),
            ("Right",  90.0,    2.0, "Right side elevation — YZ plane",              WorkingPlane.YZ),
            ("|",     None,   None, "",                                               None),
            ("↙ SW",  -45.0,  30.0, "Isometric — camera from SW (default)",         WorkingPlane.FREE),
            ("↘ SE",   45.0,  30.0, "Isometric — camera from SE",                   WorkingPlane.FREE),
            ("↖ NW", -135.0,  30.0, "Isometric — camera from NW",                   WorkingPlane.FREE),
            ("↗ NE",  135.0,  30.0, "Isometric — camera from NE",                   WorkingPlane.FREE),
        ]

        for label, az, el, tip, view_plane in _VIEWS:
            if az is None:
                self._view_tb.addSeparator()
                continue
            btn = QPushButton(label)
            btn.setFixedSize(70, 28)
            btn.setToolTip(tip + f"\n  Az={az:.0f}°  El={el:.0f}°")
            btn.clicked.connect(
                lambda _c=False, a=az, e=el, p=view_plane: self._on_set_view(a, e, p)
            )
            self._view_tb.addWidget(btn)

        # ── Working plane controls ─────────────────────────────────────────────
        self._view_tb.addSeparator()
        self._view_tb.addWidget(QLabel(" Plane: "))

        self._plane_btns: dict[WorkingPlane, QPushButton] = {}
        plane_group = QButtonGroup(self)
        plane_group.setExclusive(True)

        for plane, lbl, tip in [
            (WorkingPlane.XY,   "XY",   "Lock Z — place nodes on the horizontal X-Y plane"),
            (WorkingPlane.XZ,   "XZ",   "Lock Y — place nodes on the vertical X-Z plane"),
            (WorkingPlane.YZ,   "YZ",   "Lock X — place nodes on the vertical Y-Z plane"),
            (WorkingPlane.FREE, "Free", "No plane lock — nodes project to XY ground (Z=0)"),
        ]:
            btn = QPushButton(lbl)
            btn.setCheckable(True)
            btn.setFixedSize(52 if lbl == "Free" else 48, 28)
            btn.setToolTip(tip)
            plane_group.addButton(btn)
            self._plane_btns[plane] = btn
            self._view_tb.addWidget(btn)
            btn.clicked.connect(
                lambda _c=False, p=plane: self._set_working_plane(p)
            )

        self._plane_btns[WorkingPlane.XY].setChecked(True)  # default

        # Per-plane offset memory — each plane remembers its own locked coordinate
        self._plane_offsets: dict[WorkingPlane, float] = {
            WorkingPlane.XY: 0.0,
            WorkingPlane.XZ: 0.0,
            WorkingPlane.YZ: 0.0,
        }
        self._active_plane: WorkingPlane = WorkingPlane.XY

        # Dynamic axis label + offset spinbox
        self._plane_label = QLabel(" Z =")
        self._plane_spin = QDoubleSpinBox()
        self._plane_spin.setRange(-1000.0, 1000.0)
        self._plane_spin.setSingleStep(0.5)
        self._plane_spin.setDecimals(2)
        self._plane_spin.setSuffix(" m")
        self._plane_spin.setFixedWidth(100)
        self._plane_spin.setToolTip("Fixed coordinate on the locked axis (per-plane memory)")
        self._plane_spin.valueChanged.connect(self._on_plane_offset_changed)
        self._view_tb.addWidget(self._plane_label)
        self._view_tb.addWidget(self._plane_spin)

        self._view_tb.addSeparator()
        self._local_axes_btn = QPushButton("⊕ Axes")
        self._local_axes_btn.setCheckable(True)
        self._local_axes_btn.setFixedSize(62, 28)
        self._local_axes_btn.setToolTip(
            "Show local axis triad on all members\n"
            "Red = x̂ (along member)  Green = ŷ (strong axis)  Blue = ẑ (weak axis)\n"
            "Triad is always shown on selected members regardless of this toggle."
        )
        self._local_axes_btn.toggled.connect(self._on_toggle_local_axes)
        self._view_tb.addWidget(self._local_axes_btn)

        self._view_tb.setVisible(False)  # shown only in 3D mode

    # ── docks ─────────────────────────────────────────────────────────────────

    def _build_docks(self) -> None:
        self._props_panel = PropertiesPanel()
        self._props_panel.refresh_callback = self._on_properties_applied
        self._props_panel.set_model_state(self._scene.model_state)
        self._results_panel = ResultsPanel()

        _feat = (
            QDockWidget.DockWidgetFeature.DockWidgetFloatable |
            QDockWidget.DockWidgetFeature.DockWidgetMovable
        )

        # ── Left dock: Properties ─────────────────────────────────────────────
        props_frame = QWidget()
        pf = QVBoxLayout(props_frame)
        pf.setContentsMargins(0, 0, 0, 0)
        pf.setSpacing(0)
        props_scroll = QScrollArea()
        props_scroll.setWidget(self._props_panel)
        props_scroll.setWidgetResizable(True)
        props_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        pf.addWidget(props_scroll)

        self._left_dock = QDockWidget(self)
        self._left_dock.setWidget(props_frame)
        self._left_dock.setMinimumWidth(230)
        self._left_dock.setFeatures(_feat)
        self._left_dock.setWindowTitle("Properties")
        self._left_dock.setTitleBarWidget(_DockTitleBar("  Properties", self._left_dock))
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._left_dock)

        # ── Right dock: Results ───────────────────────────────────────────────
        results_frame = QWidget()
        rf = QVBoxLayout(results_frame)
        rf.setContentsMargins(0, 0, 0, 0)
        rf.setSpacing(0)
        rf.addWidget(self._results_panel)
        rf.addWidget(BrandingFooter())

        self._right_dock = QDockWidget(self)
        self._right_dock.setWidget(results_frame)
        self._right_dock.setMinimumWidth(260)
        self._right_dock.setFeatures(_feat)
        self._right_dock.setWindowTitle("Results")
        self._right_dock.setTitleBarWidget(_DockTitleBar("  Results", self._right_dock))
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._right_dock)

    # ── status bar ────────────────────────────────────────────────────────────

    def _build_status_bar(self) -> None:
        self._sb = QStatusBar()
        self._sb.showMessage("Ready  |  S=Select  N=Add Node  M=Add Member")
        self._sb_stats = QLabel("")
        self._sb_stats.setStyleSheet("color: #888888; padding-right: 8px;")
        self._sb.addPermanentWidget(self._sb_stats)
        self.setStatusBar(self._sb)

    # ── selection wiring ─────────────────────────────────────────────────────

    def _wire_selection(self) -> None:
        self._scene.selectionChanged.connect(self._on_selection_changed)
        self._results_panel.nodes_selected.connect(self._on_table_nodes_selected)
        self._results_panel.members_selected.connect(self._on_table_members_selected)

    def _on_selection_changed(self) -> None:
        if self._syncing_selection:
            return
        self._syncing_selection = True
        try:
            from ui_qt.canvas_items import NodeItem, MemberItem
            try:
                selected = self._scene.selectedItems()
            except RuntimeError:
                return  # scene already destroyed during window close

            nodes   = [it.node   for it in selected if isinstance(it, NodeItem)]
            members = [it.member for it in selected if isinstance(it, MemberItem)]

            # Update properties panel
            if not selected:
                self._props_panel.show_empty()
            elif len(selected) == 1:
                if nodes:
                    self._props_panel.show_node(nodes[0])
                else:
                    self._props_panel.show_member(members[0])
            elif nodes and not members:
                self._props_panel.show_nodes(nodes)
            elif members and not nodes:
                self._props_panel.show_members(members)
            else:
                self._props_panel.show_mixed(nodes, members, self._apply_selection_filter)

            # Sync results table highlight
            self._results_panel.select_nodes([n.id for n in nodes])
            self._results_panel.select_members([m.id for m in members])
        finally:
            self._syncing_selection = False

    def _apply_selection_filter(
        self, keep_node_ids: set[int], keep_member_ids: set[int]
    ) -> None:
        """Deselect canvas items that don't belong to the chosen filter group."""
        from ui_qt.canvas_items import NodeItem, MemberItem
        self._syncing_selection = True
        try:
            for item in list(self._scene.selectedItems()):
                if isinstance(item, NodeItem):
                    if item.node.id not in keep_node_ids:
                        item.setSelected(False)
                elif isinstance(item, MemberItem):
                    if item.member.id not in keep_member_ids:
                        item.setSelected(False)
        finally:
            self._syncing_selection = False
        self._on_selection_changed()

    def _on_table_nodes_selected(self, node_ids: list[int]) -> None:
        if self._syncing_selection:
            return
        self._syncing_selection = True
        try:
            self._scene.clearSelection()
            for nid in node_ids:
                item = self._scene.get_node_item(nid)
                if item:
                    item.setSelected(True)
        finally:
            self._syncing_selection = False

    def _on_table_members_selected(self, member_ids: list[int]) -> None:
        if self._syncing_selection:
            return
        self._syncing_selection = True
        try:
            self._scene.clearSelection()
            for mid in member_ids:
                item = self._scene.get_member_item(mid)
                if item:
                    item.setSelected(True)
        finally:
            self._syncing_selection = False

    # ── mode switching ────────────────────────────────────────────────────────

    def _set_mode(self, mode: CanvasMode) -> None:
        self._scene.set_mode(mode)
        self._view.setDragMode(QGraphicsView.DragMode.NoDrag)
        self._sb.showMessage(f"Mode: {mode.name}")

    def _on_member_type_changed(self) -> None:
        """Update canvas with selected member type."""
        selected_type = ElementType[self._member_type_combo.currentText()]
        self._scene.set_next_member_type(selected_type)

    def _refresh_lc_combo(self) -> None:
        """Repopulate the load case combo from the current model state."""
        self._lc_combo.blockSignals(True)
        self._lc_combo.clear()
        state = self._scene.model_state
        self._lc_combo.addItem("── All Cases ──", userData=-1)
        for lc in state.load_cases:
            label = lc.name + (" [SW]" if lc.include_self_weight else "")
            self._lc_combo.addItem(label, userData=lc.id)
        # Select the active case (skip index 0 = "All Cases")
        for i in range(self._lc_combo.count()):
            if self._lc_combo.itemData(i) == state.active_case_id:
                self._lc_combo.setCurrentIndex(i)
                break
        self._lc_combo.blockSignals(False)
        # Disable remove button when only one case remains
        if hasattr(self, "_remove_lc_btn"):
            self._remove_lc_btn.setEnabled(len(state.load_cases) > 1)
        # Sync SW button to global state — checked if ANY case carries SW
        if hasattr(self, "_sw_btn"):
            sw_active = any(lc.include_self_weight for lc in state.load_cases)
            self._sw_btn.blockSignals(True)
            self._sw_btn.setChecked(sw_active)
            self._sw_btn.blockSignals(False)
            self._update_sw_btn_style()

    def _on_lc_changed(self, index: int) -> None:
        """Switch the active load case and refresh canvas load displays."""
        if index < 0:
            return
        lc_id = self._lc_combo.itemData(index)
        state = self._scene.model_state
        if lc_id == -1:
            # "All Cases" view — overlay every LC, don't change active_case_id
            self._scene._show_all_cases = True
            self._scene.refresh_all_loads()
            self._sb.showMessage(
                "Showing all load cases  —  select a single case to edit loads or solve"
            )
        else:
            self._scene._show_all_cases = False
            state.active_case_id = lc_id
            self._props_panel.set_model_state(state)
            self._scene.refresh_all_loads()
            self._sb.showMessage(f"Active load case: {state.active_case.name}")

    def _on_add_lc(self) -> None:
        """Dialog to add a new named load case."""
        from PyQt6.QtWidgets import (
            QDialog, QFormLayout, QLineEdit, QComboBox as _CB,
            QDialogButtonBox, QVBoxLayout,
        )
        from ui_qt.model_state import LOAD_CATEGORIES

        dlg = QDialog(self)
        dlg.setWindowTitle("Add Load Case")
        layout = QVBoxLayout(dlg)
        form = QFormLayout()

        name_edit = QLineEdit("New load case")
        cat_combo = _CB()
        for key, label in LOAD_CATEGORIES.items():
            cat_combo.addItem(label, userData=key)
        cat_combo.setCurrentIndex(1)   # default Variable (Q)

        # Auto-fill a sensible name when category changes
        def _auto_name(idx):
            key = cat_combo.itemData(idx)
            name_edit.setText(LOAD_CATEGORIES[key])
        cat_combo.currentIndexChanged.connect(_auto_name)
        _auto_name(cat_combo.currentIndex())

        form.addRow("Name:", name_edit)
        form.addRow("Category:", cat_combo)
        layout.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        name = name_edit.text().strip() or "Load case"
        cat  = cat_combo.currentData()
        state = self._scene.model_state
        new_lc = state.add_load_case(name, category=cat)
        state.active_case_id = new_lc.id
        self._props_panel.set_model_state(state)
        self._refresh_lc_combo()
        self._scene.refresh_all_loads()
        self._sb.showMessage(f"Load case added: {name}")

    def _on_remove_lc(self) -> None:
        """Remove the active load case (blocked when only one remains)."""
        state = self._scene.model_state
        if len(state.load_cases) <= 1:
            return
        lc = state.active_case
        from PyQt6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, "Remove load case",
            f"Remove load case '{lc.name}'?\nAll loads in this case will be lost.",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        state.remove_load_case(lc.id)
        self._props_panel.set_model_state(state)
        self._refresh_lc_combo()
        self._scene.refresh_all_loads()
        self._sb.showMessage(f"Load case removed: {lc.name}")

    def _on_sw_toggle(self, checked: bool) -> None:
        """Create/enable or disable the dedicated self-weight load case."""
        state = self._scene.model_state
        if checked:
            # Reuse an existing SW case if one is already present (by flag or name)
            sw_lc = next((lc for lc in state.load_cases if lc.include_self_weight), None)
            if sw_lc is None:
                sw_lc = next((lc for lc in state.load_cases if lc.name == "Self-weight"), None)
            if sw_lc is None:
                sw_lc = state.add_load_case("Self-weight", category="G")
            state.set_self_weight_case(sw_lc.id)   # exclusive: clears all others
            state.active_case_id = sw_lc.id         # switch to it so user can inspect
            self._props_panel.set_model_state(state)
            self._scene.refresh_all_loads()
            self._sb.showMessage(f"Self-weight ON — load case '{sw_lc.name}'")
        else:
            state.set_self_weight_case(None)
            self._sb.showMessage("Self-weight OFF")
        self._refresh_lc_combo()
        self._update_sw_btn_style()

    def _update_sw_btn_style(self) -> None:
        if self._sw_btn.isChecked():
            self._sw_btn.setStyleSheet(
                "QPushButton { font-weight:bold; background:#27ae60; color:white;"
                " border-radius:3px; padding:3px 4px; }"
                "QPushButton:hover { background:#2ecc71; }"
            )
        else:
            self._sw_btn.setStyleSheet("")

    # ── combinations ─────────────────────────────────────────────────────────

    def _on_combinations(self) -> None:
        """Open the EN 1990 load combinations manager."""
        from ui_qt.combinations import CombinationsDialog
        dlg = CombinationsDialog(
            self._scene.model_state,
            solve_callback=self._solve_combination,
            envelope_callback=self._solve_all_combinations,
            parent=self,
        )
        dlg.exec()

    def _solve_combination(self, combo) -> None:
        """Solve the model for a specific load combination."""
        state = self._scene.model_state
        if not state.nodes or not state.members:
            QMessageBox.warning(self, "Nothing to solve",
                                "Add nodes and members before solving.")
            return

        # Structural validation (skip the "no loads" check — combo provides loads)
        errors, warnings = self._validate_model()
        # Remove the "no loads" warning — not applicable for combinations
        warnings = [w for w in warnings if "No loads applied" not in w]
        if errors:
            msg = "Cannot solve — model has the following issues:\n\n"
            msg += "\n\n".join(f"  • {e}" for e in errors)
            QMessageBox.critical(self, "Model validation failed", msg)
            return
        if warnings:
            msg = "Model has warnings:\n\n"
            msg += "\n".join(f"  • {w}" for w in warnings)
            msg += "\n\nSolve anyway?"
            reply = QMessageBox.question(self, "Model warnings", msg)
            if reply != QMessageBox.StandardButton.Yes:
                return

        try:
            from ui_qt.model_builder import build_model_combined

            model, member_el_map = build_model_combined(state, combo)
            cache = self._solve_engine(model, member_el_map, state)

            dpn = cache['model'].dofs_per_node
            self._results_panel.populate(
                cache['displacements'], cache['reactions'],
                cache['member_results'], state, dpn,
                member_el_map=cache['member_el_map'],
                sub_results=cache['sub_results'],
            )

            self._solve_cache = cache
            self._reset_combo_view()

            self._scene.update_overlays(
                cache['model'], cache['sub_results'],
                cache['displacements'], cache['member_el_map'],
                diag_scale_mult=self._diag_scale_spin.value(),
                def_scale_mult=self._def_scale_spin.value(),
            )
            for name, btn in self._overlay_btns.items():
                key = 'Deformed' if name == 'Def' else name
                self._scene.set_overlay_visible(key, btn.isChecked())

            self._set_overlay_controls_enabled(True)

            if self._force_colour_btn.isChecked():
                self._scene.update_member_colours(cache['member_results'])
            elif self._util_colour_btn.isChecked():
                self._scene.update_member_util_colours(
                    cache['member_results'], state.members)
            else:
                self._scene.clear_member_colours()

            disp = cache['displacements']
            member_results = cache['member_results']
            max_dy_mm = max((abs(disp[n.id * dpn + 1]) * 1000 for n in state.nodes), default=0)
            max_dy_node = max(state.nodes, key=lambda n: abs(disp[n.id * dpn + 1]))
            max_m = max(
                (max(abs(r.M_i), abs(r.M_j)) for r in member_results), default=0
            )
            max_m_member = max(
                member_results, key=lambda r: max(abs(r.M_i), abs(r.M_j)), default=None
            )
            self._sb.showMessage(
                f"[{combo.limit_state}] {combo.name}  |  "
                f"Max deflection: {max_dy_mm:.2f} mm (node {max_dy_node.id})  |  "
                f"Max moment: {max_m/1000:.2f} kN·m "
                f"(member {max_m_member.element_id if max_m_member else '-'})"
            )
        except Exception as exc:
            msg = str(exc)
            if "Singular matrix" in msg or "singular" in msg.lower():
                QMessageBox.critical(
                    self, "Cannot solve — unstable structure",
                    "The stiffness matrix is singular.\n"
                    "Check supports and structure geometry."
                )
            else:
                QMessageBox.critical(self, "Solve error", msg)
            self._sb.showMessage("Combination solve failed.")

    def _solve_all_combinations(self, combos: list) -> None:
        """Solve every combination and show envelope max/min results."""
        state = self._scene.model_state
        if not state.nodes or not state.members:
            QMessageBox.warning(self, "Nothing to solve",
                                "Add nodes and members before solving.")
            return

        errors, _ = self._validate_model()
        errors = [e for e in errors]   # copy
        if errors:
            msg = "Cannot solve — model has issues:\n\n"
            msg += "\n\n".join(f"  • {e}" for e in errors)
            QMessageBox.critical(self, "Model validation failed", msg)
            return

        try:
            from ui_qt.model_builder import build_model_combined
            from ui_qt.envelope import EnvelopeDialog

            solve_runs = []
            failed = []

            for combo in combos:
                if not combo.factors:
                    continue
                try:
                    model, member_el_map = build_model_combined(state, combo)
                    cache = self._solve_engine(model, member_el_map, state)

                    solve_runs.append({
                        'combo':          combo,
                        'displacements':  cache['displacements'],
                        'reactions':      cache['reactions'],
                        'member_results': cache['member_results'],
                        'sub_results':    cache['sub_results'],
                        'member_el_map':  cache['member_el_map'],
                        'model':          cache['model'],
                    })

                    # Keep single-solve cache updated (used by "Active case" view)
                    self._solve_cache = cache

                except Exception as exc:
                    failed.append(f"{combo.name}: {exc}")

            if not solve_runs:
                QMessageBox.warning(self, "No results",
                                    "No combinations could be solved.\n" +
                                    "\n".join(failed))
                return

            if failed:
                QMessageBox.warning(
                    self, "Some combinations failed",
                    f"{len(failed)} combination(s) could not be solved:\n\n" +
                    "\n".join(f"  • {f}" for f in failed)
                )

            # ── Pattern loading: detect, generate, solve ──────────────────────
            from ui_qt.pattern_loading import (
                detect_pattern_loading,
                generate_pattern_runs,
                build_assessment_message,
            )
            from ui_qt.model_builder import build_model_pattern
            from ui_qt.model_state import LoadCombination as _LC

            assessment = detect_pattern_loading(state)
            pattern_solve_runs: list[dict] = []

            if assessment.needed:
                g_cases = [lc for lc in state.load_cases if lc.category == "G"]
                q_cases = [lc for lc in state.load_cases if lc.category != "G"]

                for pr in generate_pattern_runs(assessment):
                    try:
                        p_model, p_mel = build_model_pattern(
                            state, g_cases, 1.35, q_cases, 1.50,
                            pr.active_q_member_ids,
                        )
                        cache = self._solve_engine(p_model, p_mel, state)

                        synthetic_combo = _LC(
                            id=-(len(pattern_solve_runs) + 1),
                            name=pr.name,
                            limit_state="ULS",
                            is_auto=True,
                        )
                        pattern_solve_runs.append({
                            'combo':          synthetic_combo,
                            'displacements':  cache['displacements'],
                            'reactions':      cache['reactions'],
                            'member_results': cache['member_results'],
                            'sub_results':    cache['sub_results'],
                            'member_el_map':  cache['member_el_map'],
                            'model':          cache['model'],
                        })
                    except Exception as exc:
                        failed.append(f"{pr.name}: {exc}")

                solve_runs.extend(pattern_solve_runs)

            # ── Determine which members pattern loading governs ───────────────
            n_en1990 = len(solve_runs) - len(pattern_solve_runs)
            pattern_governs: list[tuple[int, float, float]] = []
            if pattern_solve_runs:
                en1990_runs = solve_runs[:n_en1990]
                for md in state.members:
                    full_M = max(
                        (max(abs(r.M_i), abs(r.M_j))
                         for run in en1990_runs
                         for r in run['member_results']
                         if r.element_id == md.id),
                        default=0.0,
                    )
                    pat_M = max(
                        (max(abs(r.M_i), abs(r.M_j))
                         for run in pattern_solve_runs
                         for r in run['member_results']
                         if r.element_id == md.id),
                        default=0.0,
                    )
                    if pat_M > full_M * 1.01 and full_M > 1.0:
                        pattern_governs.append((md.id, pat_M, full_M))

            # ── Update assessment bar ─────────────────────────────────────────
            msg, lvl = build_assessment_message(
                assessment, len(pattern_solve_runs), pattern_governs
            )
            self._results_panel.set_pattern_assessment(msg, lvl)

            # Store cache and populate combo-view dropdown
            self._all_combos_cache = solve_runs
            self._populate_combo_view(solve_runs)
            self._set_overlay_controls_enabled(True)

            # Draw envelope on canvas (combo view set to "Envelope" by _populate_combo_view)
            self._on_combo_view_changed(self._combo_view.currentIndex())
            for name, btn in self._overlay_btns.items():
                key = 'Deformed' if name == 'Def' else name
                self._scene.set_overlay_visible(key, btn.isChecked())

            # Populate Results panel with envelope so numbers are visible
            # immediately after the dialog closes (or without reopening it)
            _env_dpn = solve_runs[0]['model'].dofs_per_node if solve_runs else 3
            self._results_panel.populate_envelope(solve_runs, state, _env_dpn)

            self._sb.showMessage(
                f"Solved {len(solve_runs)}/{len(combos)} combination(s) — "
                "Results panel shows envelope (governing values per element)"
            )

            dlg = EnvelopeDialog(solve_runs, state, parent=self)
            dlg.exec()

        except Exception as exc:
            QMessageBox.critical(self, "Envelope solve error", str(exc))
            self._sb.showMessage("Envelope solve failed.")

    # ── overlay helpers ───────────────────────────────────────────────────────

    def _on_overlay_toggle(self, layer: str, checked: bool) -> None:
        """Forward layer visibility toggle to the canvas."""
        self._scene.set_overlay_visible(layer, checked)

    def _redraw_overlays(self) -> None:
        """Recompute overlays for the current combo-view mode and scale spinbox values."""
        self._on_combo_view_changed(self._combo_view.currentIndex())

    def _on_force_colour_toggle(self, checked: bool) -> None:
        if checked:
            self._util_colour_btn.setChecked(False)
            if self._solve_cache is not None:
                self._scene.update_member_colours(self._solve_cache['member_results'])
        else:
            self._scene.clear_member_colours()

    def _on_util_colour_toggle(self, checked: bool) -> None:
        if checked:
            self._force_colour_btn.setChecked(False)
            if self._solve_cache is not None:
                self._scene.update_member_util_colours(
                    self._solve_cache['member_results'],
                    self._scene.model_state.members,
                )
        else:
            self._scene.clear_util_colours()

    def _set_overlay_controls_enabled(self, enabled: bool) -> None:
        """Enable or disable all overlay toolbar controls."""
        for btn in self._overlay_btns.values():
            btn.setEnabled(enabled)
        self._force_colour_btn.setEnabled(enabled)
        self._util_colour_btn.setEnabled(enabled)
        self._diag_scale_spin.setEnabled(enabled)
        self._def_scale_spin.setEnabled(enabled)

    def _reset_combo_view(self) -> None:
        """Reset the combo-view dropdown to 'Active case' and clear the cache."""
        self._combo_view.blockSignals(True)
        self._combo_view.clear()
        self._combo_view.addItem("Active case", userData="active")
        self._combo_view.setEnabled(False)
        self._combo_view.blockSignals(False)
        self._all_combos_cache = None

    def _populate_combo_view(self, solve_runs: list) -> None:
        """Fill the combo-view dropdown with individual combos + superposed + envelope."""
        self._combo_view.blockSignals(True)
        self._combo_view.clear()
        self._combo_view.addItem("Active case", userData="active")
        for i, run in enumerate(solve_runs):
            self._combo_view.addItem(run['combo'].name, userData=f"combo:{i}")
        self._combo_view.addItem("All superposed", userData="all")
        self._combo_view.addItem("Envelope (max/min)", userData="envelope")
        self._combo_view.setCurrentIndex(self._combo_view.count() - 1)  # default: envelope
        self._combo_view.setEnabled(True)
        self._combo_view.blockSignals(False)

    def _on_combo_view_changed(self, index: int) -> None:
        """Redraw canvas overlays for the selected combo-view mode."""
        if index < 0:
            return
        data = self._combo_view.itemData(index)

        # Visibility helper
        def _apply_vis():
            for name, btn in self._overlay_btns.items():
                key = 'Deformed' if name == 'Def' else name
                self._scene.set_overlay_visible(key, btn.isChecked())

        if data == "active" or self._all_combos_cache is None:
            if self._solve_cache is None:
                return
            self._scene.update_overlays(
                self._solve_cache['model'],
                self._solve_cache['sub_results'],
                self._solve_cache['displacements'],
                self._solve_cache['member_el_map'],
                diag_scale_mult=self._diag_scale_spin.value(),
                def_scale_mult=self._def_scale_spin.value(),
            )
            _apply_vis()
        elif isinstance(data, str) and data.startswith("combo:"):
            ci  = int(data.split(":")[1])
            run = self._all_combos_cache[ci]
            self._scene.update_overlays_single_combo(
                run, ci, self._all_combos_cache,
                diag_scale_mult=self._diag_scale_spin.value(),
                def_scale_mult=self._def_scale_spin.value(),
            )
            _apply_vis()
        elif data == "all":
            ref_model = self._all_combos_cache[0]['model']
            self._scene.update_overlays_all_combos(
                ref_model, self._all_combos_cache,
                diag_scale_mult=self._diag_scale_spin.value(),
            )
            _apply_vis()
        elif data == "envelope":
            ref_model = self._all_combos_cache[0]['model']
            self._scene.update_overlays_envelope(
                ref_model, self._all_combos_cache,
                diag_scale_mult=self._diag_scale_spin.value(),
            )
            _apply_vis()

    # ── pre-solve validation ──────────────────────────────────────────────────

    def _validate_model(self) -> tuple[list[str], list[str]]:
        """Return (errors, warnings) for the current model state."""
        from ui_qt.solve_actions import validate_model
        return validate_model(self._scene.model_state)

    # ── solve ─────────────────────────────────────────────────────────────────

    def _solve_engine(self, model, member_el_map, state):
        """Run assemble → solve → postprocess → aggregate pipeline."""
        from ui_qt.solve_actions import solve_engine
        return solve_engine(model, member_el_map, state)

    def _on_solve(self) -> None:
        state = self._scene.model_state
        if not state.nodes or not state.members:
            QMessageBox.warning(self, "Nothing to solve",
                                "Add nodes and members before solving.")
            return
        if self._scene._show_all_cases:
            QMessageBox.information(
                self, "Select a load case",
                "The solver works on one load case at a time.\n\n"
                "Please select a specific load case from the Case drop-down, "
                "then click Solve.\n\n"
                "To analyse all cases together, use Load Combinations "
                "(Toolbar → Combinations)."
            )
            return

        # Run pre-solve validation
        errors, warnings = self._validate_model()
        if errors:
            msg = "Cannot solve — model has the following issues:\n\n"
            msg += "\n\n".join(f"  • {e}" for e in errors)
            QMessageBox.critical(self, "Model validation failed", msg)
            self._sb.showMessage("Solve blocked — fix model issues first.")
            return
        if warnings:
            msg = "Model has warnings:\n\n"
            msg += "\n".join(f"  • {w}" for w in warnings)
            msg += "\n\nSolve anyway?"
            reply = QMessageBox.question(self, "Model warnings", msg)
            if reply != QMessageBox.StandardButton.Yes:
                return

        try:
            from ui_qt.model_builder import build_model

            model, member_el_map = build_model(state)
            cache = self._solve_engine(model, member_el_map, state)

            dpn = cache['model'].dofs_per_node
            self._results_panel.populate(
                cache['displacements'], cache['reactions'],
                cache['member_results'], state, dpn,
                member_el_map=cache['member_el_map'],
                sub_results=cache['sub_results'],
            )

            # Cache solve data for re-draw when scale spinboxes change
            self._solve_cache = cache
            self._reset_combo_view()

            # Draw overlays on canvas
            self._scene.update_overlays(
                cache['model'], cache['sub_results'],
                cache['displacements'], cache['member_el_map'],
                diag_scale_mult=self._diag_scale_spin.value(),
                def_scale_mult=self._def_scale_spin.value(),
            )

            # Apply current toggle-button visibility state
            for name, btn in self._overlay_btns.items():
                key = 'Deformed' if name == 'Def' else name
                self._scene.set_overlay_visible(key, btn.isChecked())

            self._set_overlay_controls_enabled(True)

            # Apply member colour overlay if toggle is on
            if self._force_colour_btn.isChecked():
                self._scene.update_member_colours(cache['member_results'])
            elif self._util_colour_btn.isChecked():
                self._scene.update_member_util_colours(
                    cache['member_results'],
                    self._scene.model_state.members)
            else:
                self._scene.clear_member_colours()

            # Results summary for status bar
            disp = cache['displacements']
            member_results = cache['member_results']
            max_dy_mm = max((abs(disp[n.id * dpn + 1]) * 1000 for n in state.nodes), default=0)
            max_dy_node = max(state.nodes, key=lambda n: abs(disp[n.id * dpn + 1]))
            max_m = max(
                (max(abs(r.M_i), abs(r.M_j)) for r in member_results),
                default=0
            )
            max_m_member = max(
                member_results, key=lambda r: max(abs(r.M_i), abs(r.M_j)),
                default=None
            )
            summary = (
                f"Solved  |  "
                f"Max deflection: {max_dy_mm:.2f} mm (node {max_dy_node.id})  |  "
                f"Max moment: {max_m/1000:.2f} kN·m (member {max_m_member.element_id if max_m_member else '-'})"
            )
            self._sb.showMessage(summary)
            self._update_status_stats()
        except Exception as exc:
            msg = str(exc)
            if "Singular matrix" in msg or "singular" in msg.lower():
                detail = (
                    "The stiffness matrix is singular — the structure cannot be solved.\n\n"
                    "Common causes:\n"
                    "  • Missing support — structure has no fixed point (add a PIN or FIXED support)\n"
                    "  • Only ROLLER supports — at least one PIN is needed to prevent sliding\n"
                    "  • Floating node — a node with no members attached\n"
                    "  • Mechanism — the truss or frame can move without any member stretching\n\n"
                    "Tip: For a truss, use PIN at one end and ROLLER at the other."
                )
                QMessageBox.critical(self, "Cannot solve — unstable structure", detail)
            else:
                QMessageBox.critical(self, "Solve error", msg)
            self._sb.showMessage("Solve failed — see error dialog for details.")

    # ── properties applied callback ───────────────────────────────────────────

    def _on_properties_applied(self) -> None:
        """Refresh canvas after node/member properties change."""
        from ui_qt.canvas_items import NodeItem, MemberItem
        for item in self._scene.selectedItems():
            if isinstance(item, NodeItem):
                item.refresh()
            elif isinstance(item, MemberItem):
                item.refresh()
        # Redraw ALL load arrows so the model-wide max is recomputed and every
        # member's arrow length is rescaled relative to the updated values.
        self._scene.refresh_all_loads()
        self._sb.showMessage("Properties updated.")

    # ── autosave ──────────────────────────────────────────────────────────────

    def _setup_autosave(self) -> None:
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(120_000)  # every 2 minutes
        self._autosave_timer.timeout.connect(self._do_autosave)
        self._autosave_timer.start()

    def _do_autosave(self) -> None:
        if not self._is_dirty or not self._scene.model_state.nodes:
            return
        try:
            _AUTOSAVE_PATH.parent.mkdir(parents=True, exist_ok=True)
            from ui_qt.io import save_model
            save_model(self._scene.model_state, _AUTOSAVE_PATH)
        except Exception:
            pass

    def _check_autosave_recovery(self) -> bool:
        """Offer to recover an autosaved model. Returns True if recovery happened."""
        if not _AUTOSAVE_PATH.exists():
            return False
        reply = QMessageBox.question(
            self, "Recover previous session?",
            "StructLab found an autosaved model from a previous session.\n"
            "Recover it now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        recovered = False
        if reply == QMessageBox.StandardButton.Yes:
            try:
                from ui_qt.io import load_model
                state = load_model(_AUTOSAVE_PATH)
                self._apply_model_state(state, "Recovered session")
                self._is_dirty = True
                self._update_title()
                self._sb.showMessage("Previous session recovered from autosave.")
                recovered = True
            except Exception as exc:
                QMessageBox.warning(self, "Recovery failed", str(exc))
        _AUTOSAVE_PATH.unlink(missing_ok=True)
        return recovered

    # ── dirty tracking & close ───────────────────────────────────────────────

    def _update_title(self) -> None:
        prefix = "• " if self._is_dirty else ""
        fname = os.path.basename(self._filepath) if self._filepath else "Untitled"
        self.setWindowTitle(f"{prefix}{fname} — StructLab V1.0.0")

    def _maybe_save_before_close(self) -> bool:
        """Return True if it's safe to proceed (saved or user chose discard)."""
        if not self._is_dirty:
            return True
        fname = os.path.basename(self._filepath) if self._filepath else "Untitled"
        reply = QMessageBox.question(
            self, "Unsaved changes",
            f"Save changes to « {fname} » before closing?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Save:
            self._on_save()
            return not self._is_dirty  # False if save was cancelled
        return reply == QMessageBox.StandardButton.Discard

    def _on_close_model(self) -> None:
        """Close the current model, returning to the welcome screen."""
        if self._scene.model_state.nodes and not self._maybe_save_before_close():
            return
        self._do_clear_model()
        self._sb.showMessage("Model closed — ready for new project")

    def _on_model_changed(self) -> None:
        """Canvas model changed — update dirty flag and status bar."""
        if self._scene.model_state.nodes:
            self._scene._hide_welcome = True  # user has started building
        self._is_dirty = True
        # Discard stale solve results — node IDs in the cache may no longer
        # match the current model after deletions or duplications.
        self._solve_cache = None
        self._update_title()
        self._update_status_stats()
        self._props_panel.set_model_state(self._scene.model_state)

    def _update_status_stats(self) -> None:
        """Update the status bar permanent widget with live model + results stats."""
        state = self._scene.model_state
        n_nodes = len(state.nodes)
        n_members = len(state.members)
        parts = [f"Nodes: {n_nodes}", f"Members: {n_members}"]

        if self._solve_cache is not None:
            cache = self._solve_cache
            disp = cache["displacements"]
            member_results = cache["member_results"]
            _dpn = cache["model"].dofs_per_node
            if n_nodes > 0:
                max_dy = max(
                    (abs(disp[n.id * _dpn + 1]) * 1000 for n in state.nodes),
                    default=0,
                )
                parts.append(f"δ max: {max_dy:.1f} mm")
            if member_results:
                max_m = max(
                    (max(abs(r.M_i), abs(r.M_j)) for r in member_results),
                    default=0,
                )
                parts.append(f"M max: {max_m / 1e3:.1f} kN·m")

        self._sb_stats.setText("  |  ".join(parts))

    # ── keyboard shortcuts ────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:
        if self._maybe_save_before_close():
            _AUTOSAVE_PATH.unlink(missing_ok=True)
            event.accept()
        else:
            event.ignore()

    def keyPressEvent(self, event) -> None:
        ctrl = event.modifiers() == Qt.KeyboardModifier.ControlModifier
        if event.key() == Qt.Key.Key_F5:
            self._on_solve()
        elif event.key() == Qt.Key.Key_F:
            self._view.zoom_to_fit()
        elif event.key() == Qt.Key.Key_Z and ctrl:
            self._scene.undo()
            self._on_undo_redo()
        elif event.key() == Qt.Key.Key_Y and ctrl:
            self._scene.redo()
            self._on_undo_redo()
        else:
            super().keyPressEvent(event)

    def _on_undo_redo(self) -> None:
        """Clear solve results after undo/redo since model has changed."""
        self._results_panel.clear()
        self._props_panel.show_empty()
        self._scene.clear_overlays()
        self._scene.clear_member_colours()
        self._solve_cache = None
        self._reset_combo_view()
        self._set_overlay_controls_enabled(False)
        self._sb.showMessage("Undo/Redo — results cleared, re-solve to update.")

    # ── export ───────────────────────────────────────────────────────────────

    def _export_scene_rect(self):
        """Bounding rect of all canvas items, with 1 m padding. None if canvas empty."""
        if not self._scene.model_state.nodes:
            QMessageBox.warning(self, "Export", "Nothing to export — the canvas is empty.")
            return None
        from ui_qt.canvas_items import PX_PER_M
        pad = PX_PER_M  # 1 m padding on each side
        return self._scene.itemsBoundingRect().adjusted(-pad, -pad, pad, pad)

    def _on_export_png(self) -> None:
        from PyQt6.QtGui import QImage, QPainter
        rect = self._export_scene_rect()
        if rect is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export PNG", "", "PNG Image (*.png)"
        )
        if not path:
            return
        if not path.endswith(".png"):
            path += ".png"

        scale = 2  # 2× for sharp output on retina / high-DPI screens
        img = QImage(int(rect.width() * scale), int(rect.height() * scale),
                     QImage.Format.Format_ARGB32)
        img.fill(QColor("#1a1a1e"))

        painter = QPainter(img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._scene.render(painter, source=rect)
        painter.end()

        if img.save(path):
            self._sb.showMessage(f"Exported PNG: {path}")
        else:
            QMessageBox.critical(self, "Export error", f"Could not write {path}")

    def _on_export_svg(self) -> None:
        from PyQt6.QtGui import QPainter
        from PyQt6.QtSvg import QSvgGenerator
        from PyQt6.QtCore import QRectF
        rect = self._export_scene_rect()
        if rect is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export SVG", "", "SVG Vector (*.svg)"
        )
        if not path:
            return
        if not path.endswith(".svg"):
            path += ".svg"

        gen = QSvgGenerator()
        gen.setFileName(path)
        gen.setSize(QSize(int(rect.width()), int(rect.height())))
        gen.setViewBox(QRectF(0, 0, rect.width(), rect.height()))
        gen.setTitle("StructLab Export")
        gen.setDescription("Generated by StructLab V1.0.0")

        painter = QPainter(gen)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Fill dark background explicitly (SVG generator doesn't call drawBackground)
        painter.fillRect(QRectF(0, 0, rect.width(), rect.height()), QColor("#1a1a1e"))
        self._scene.render(painter, source=rect)
        painter.end()

        self._sb.showMessage(f"Exported SVG: {path}")

    # ── project info dialog ───────────────────────────────────────────────────

    def _on_project_info(self) -> None:
        """Open the Project Info dialog to edit ProjectMetadata."""
        from ui_qt.dialogs import show_project_info
        if show_project_info(self, self._scene.model_state):
            self._is_dirty = True
            self._update_title()
            meta = self._scene.model_state.metadata
            self._sb.showMessage(f"Project info updated: {meta.title}")

    # ── PDF export ────────────────────────────────────────────────────────────

    def _on_export_pdf(self) -> None:
        state = self._scene.model_state
        if not state.nodes:
            QMessageBox.warning(self, "Export PDF",
                                "Nothing to export — the canvas is empty.")
            return

        # ── Step 1: ask what to report on ─────────────────────────────────────
        from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
                                     QGroupBox, QRadioButton, QComboBox,
                                     QDialogButtonBox, QLabel)

        class _BasisDlg(QDialog):
            def __init__(self, st, parent=None):
                super().__init__(parent)
                self.setWindowTitle("PDF Report — Report basis")
                self.setMinimumWidth(380)
                lay = QVBoxLayout(self)

                grp = QGroupBox("Solve and report on:")
                glay = QVBoxLayout(grp)

                self._rb_lc    = QRadioButton("Load Case")
                self._rb_combo = QRadioButton("Load Combination")
                self._rb_lc.setChecked(True)

                self._cb_lc = QComboBox()
                for lc in st.load_cases:
                    self._cb_lc.addItem(f"LC{lc.id}: {lc.name}", lc.id)

                self._cb_combo = QComboBox()
                self._cb_combo.setEnabled(False)
                if st.combinations:
                    for c in st.combinations:
                        self._cb_combo.addItem(
                            f"{c.name}  [{c.limit_state}]", c.id)
                else:
                    self._rb_combo.setEnabled(False)
                    self._cb_combo.addItem("(no combinations defined)")

                self._rb_lc.toggled.connect(self._toggle)

                glay.addWidget(self._rb_lc)
                glay.addWidget(self._cb_lc)
                glay.addSpacing(6)
                glay.addWidget(self._rb_combo)
                glay.addWidget(self._cb_combo)
                lay.addWidget(grp)

                btns = QDialogButtonBox(
                    QDialogButtonBox.StandardButton.Ok |
                    QDialogButtonBox.StandardButton.Cancel)
                btns.accepted.connect(self.accept)
                btns.rejected.connect(self.reject)
                lay.addWidget(btns)

            def _toggle(self, lc_checked: bool) -> None:
                self._cb_lc.setEnabled(lc_checked)
                self._cb_combo.setEnabled(not lc_checked)

            def is_lc(self) -> bool:
                return self._rb_lc.isChecked()

            def lc_id(self) -> int:
                return self._cb_lc.currentData()

            def combo_id(self) -> int:
                return self._cb_combo.currentData()

        dlg = _BasisDlg(state, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        # ── Step 2: choose file path ───────────────────────────────────────────
        path, _ = QFileDialog.getSaveFileName(
            self, "Export PDF Report", "", "PDF files (*.pdf)"
        )
        if not path:
            return
        if not path.endswith(".pdf"):
            path += ".pdf"

        # ── Step 3: solve the chosen LC / combination ──────────────────────────
        try:
            if dlg.is_lc():
                lc = next(c for c in state.load_cases
                          if c.id == dlg.lc_id())
                from ui_qt.model_builder import build_model
                model, member_el_map = build_model(state, lc)
                report_basis = f"Load Case: LC{lc.id} — {lc.name}"
            else:
                combo = next(c for c in state.combinations
                             if c.id == dlg.combo_id())
                from ui_qt.model_builder import build_model_combined
                model, member_el_map = build_model_combined(state, combo)
                report_basis = f"Combination: {combo.name}  [{combo.limit_state}]"

            cache = self._solve_engine(model, member_el_map, state)

        except Exception as exc:
            QMessageBox.critical(self, "Solve error",
                                 f"Could not solve for report:\n{exc}")
            return

        # ── Step 4: render canvas snapshot ────────────────────────────────────
        import tempfile, os
        tmp_png = None
        try:
            from PyQt6.QtGui import QImage, QPainter
            rect = self._export_scene_rect()
            if rect is not None:
                scale = 2
                img = QImage(int(rect.width() * scale),
                             int(rect.height() * scale),
                             QImage.Format.Format_ARGB32)
                img.fill(QColor("#1a1a1e"))
                painter = QPainter(img)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                self._scene.render(painter, source=rect)
                painter.end()
                fd, tmp_png = tempfile.mkstemp(suffix=".png")
                os.close(fd)
                img.save(tmp_png)
        except Exception:
            tmp_png = None

        # ── Step 5: generate PDF ───────────────────────────────────────────────
        try:
            from ui_qt.pdf_report import generate_report
            generate_report(
                filepath=path,
                state=state,
                canvas_image_path=tmp_png,
                solve_cache=cache,
                report_basis=report_basis,
            )
            self._sb.showMessage(f"PDF report saved: {path}")
        except Exception as exc:
            QMessageBox.critical(self, "PDF export error", str(exc))
        finally:
            if tmp_png and os.path.exists(tmp_png):
                os.remove(tmp_png)

    # ── copy / paste / duplicate ──────────────────────────────────────────────

    def _on_copy(self) -> None:
        from ui_qt.canvas_items import NodeItem, MemberItem
        ms = self._scene.model_state
        selected = self._scene.selectedItems()

        selected_members = [it.member for it in selected if isinstance(it, MemberItem)]
        node_ids_from_members = {m.node_i for m in selected_members} | {m.node_j for m in selected_members}
        lone_node_ids = {it.node.id for it in selected if isinstance(it, NodeItem)}
        all_node_ids = node_ids_from_members | lone_node_ids

        if not all_node_ids and not selected_members:
            self._sb.showMessage("Nothing selected to copy.")
            return

        nodes = [ms.get_node(nid) for nid in all_node_ids if ms.get_node(nid)]
        self._clipboard = {
            "nodes": [{"id": n.id, "x": n.x, "y": n.y} for n in nodes],
            "members": [
                {
                    "node_i": m.node_i, "node_j": m.node_j,
                    "element_type": m.element_type.name,
                    "E": m.E, "A": m.A, "I": m.I,
                    "n_sub": m.n_sub, "density": m.density,
                }
                for m in selected_members
            ],
        }
        n_m = len(selected_members)
        n_n = len(nodes)
        self._sb.showMessage(f"Copied {n_m} member(s), {n_n} node(s)  —  Ctrl+V to paste")

    def _on_paste(self) -> None:
        if not self._clipboard:
            self._sb.showMessage("Clipboard is empty — copy a selection first.")
            return

        new_node_ids, new_member_ids = self._scene.paste(self._clipboard)

        # Select newly pasted items so the user can drag them immediately
        self._scene.clearSelection()
        for nid in new_node_ids:
            item = self._scene.get_node_item(nid)
            if item:
                item.setSelected(True)
        for mid in new_member_ids:
            item = self._scene.get_member_item(mid)
            if item:
                item.setSelected(True)

        self._sb.showMessage(
            f"Pasted {len(new_member_ids)} member(s) — drag to position, or Ctrl+V again"
        )

    def _on_duplicate(self) -> None:
        """Show the Duplicate dialog and create offset copies of the selection."""
        from ui_qt.canvas_items import NodeItem
        from ui_qt.dialogs import DuplicateDialog

        if not any(isinstance(it, NodeItem) for it in self._scene.selectedItems()):
            self._sb.showMessage("Select nodes or members to duplicate  (Ctrl+D)")
            return

        dlg = DuplicateDialog(self, is_3d=True)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return

        self._scene.duplicate_selection(dlg.axis, dlg.offset, dlg.copies)

        n_copies = dlg.copies
        self._sb.showMessage(
            f"Duplicated × {n_copies}  along {dlg.axis}  offset {dlg.offset:+.2f} m"
        )

    # ── file operations ───────────────────────────────────────────────────────

    def _on_new(self) -> None:
        # Only prompt to save if there's actually a model to lose
        if self._scene.model_state.nodes and not self._maybe_save_before_close():
            return
        self._do_clear_model()
        self._sb.showMessage("New model — ready")

    def _do_clear_model(self) -> None:
        """Clear canvas and return to welcome screen (no save prompt)."""
        self._scene.clear_model()
        self._scene._hide_welcome = True   # dismiss first-launch welcome
        self._props_panel.set_model_state(self._scene.model_state)
        self._refresh_lc_combo()
        self._results_panel.clear()
        self._props_panel.show_empty()
        self._solve_cache = None
        self._reset_combo_view()
        self._set_overlay_controls_enabled(False)
        self._is_dirty = False
        self._filepath = None
        _AUTOSAVE_PATH.unlink(missing_ok=True)
        self._update_title()
        self._update_status_stats()

    def _on_open(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open StructLab model", "", "StructLab files (*.slab);;All files (*)"
        )
        if path:
            self._open_file(path)

    def _on_import_csv(self) -> None:
        """Import a sectioned StructLab CSV (nodes/members/supports/forces)."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Import structure from CSV", "", "CSV files (*.csv);;All files (*)"
        )
        if not path:
            return
        from ui_qt.csv_import import parse_structlab_csv
        try:
            state, warnings = parse_structlab_csv(path)
        except Exception as exc:  # malformed file, encoding error, etc.
            QMessageBox.critical(self, "CSV import error", str(exc))
            return
        if not state.nodes:
            QMessageBox.warning(
                self, "CSV import",
                "No nodes were read — check the file uses the #NODES / #MEMBERS / "
                "#SUPPORTS / #FORCES section format.",
            )
            return
        self._apply_model_state(state, f"CSV Import: {Path(path).name}")
        if warnings:
            shown = "\n".join(warnings[:20])
            if len(warnings) > 20:
                shown += f"\n… and {len(warnings) - 20} more."
            QMessageBox.warning(
                self, "CSV import — completed with warnings",
                f"Imported with {len(warnings)} warning(s):\n\n{shown}",
            )

    def _on_save(self) -> None:
        """Save to current file, or prompt for a path if none is set yet."""
        if self._filepath:
            self._save_to(self._filepath)
        else:
            self._on_save_as()

    def _on_save_as(self) -> None:
        """Always prompt for a new file path, then save."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Save StructLab model",
            self._filepath or "",
            "StructLab files (*.slab);;All files (*)",
        )
        if not path:
            return
        if not path.endswith(".slab"):
            path += ".slab"
        self._save_to(path)

    def _save_to(self, path: str) -> None:
        """Write model to path, update state. Shared by Save and Save As."""
        try:
            from ui_qt.io import save_model
            save_model(self._scene.model_state, path)
            self._is_dirty = False
            self._filepath = path
            _AUTOSAVE_PATH.unlink(missing_ok=True)
            self._update_title()
            self._sb.showMessage(f"Saved: {path}")
            from ui_qt import recent_files as RF
            RF.push(path)
        except Exception as exc:
            QMessageBox.critical(self, "Save error", str(exc))

    def _on_clear_results(self) -> None:
        self._results_panel.clear()
        self._scene.clear_overlays()
        self._scene.clear_member_colours()
        self._solve_cache = None
        self._reset_combo_view()
        self._set_overlay_controls_enabled(False)
        self._sb.showMessage("Results cleared.")
