"""Every user command, defined once as a QAction.

``build_actions(window)`` creates one QAction per command from the ``COMMANDS`` table
(text, icon, shortcut, tooltip, checkable, handler) and returns them by key. The classic
menus and toolbars and the ribbon all place these same actions, so a command's shortcut,
enabled and checked state are shared wherever it appears.

A handler is the name of a MainWindow method, or a callable taking the window (for
commands that act on the scene or view directly). Checkable commands connect ``toggled``,
others ``triggered``. Every action is also added to the window itself, so its shortcut works
whether or not a menu bar is visible.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PyQt6.QtGui import QAction, QActionGroup, QKeySequence

from ui_qt.icons import icon


@dataclass(frozen=True)
class Command:
    key: str
    text: str
    handler: str | Callable | None = None
    icon: str = ""
    shortcut: str = ""
    tip: str = ""
    checkable: bool = False
    checked: bool = False


def _delete_selection(win) -> None:
    win._scene.save_snapshot()
    win._scene._delete_selected()


COMMANDS: tuple[Command, ...] = (
    # ── file ──────────────────────────────────────────────────────────────────
    Command("new", "New", "_on_new", "file-plus", "Ctrl+N", "Start a new model"),
    Command("open", "Open…", "_on_open", "folder-open", "Ctrl+O", "Open a .slab model"),
    Command("save", "Save", "_on_save", "save", "Ctrl+S", "Save the model"),
    Command("save_as", "Save As…", "_on_save_as", "save-all", "Ctrl+Shift+S", "Save under a new name"),
    Command("close_model", "Close Model", "_on_close_model", "file-x", "",
            "Close the current model (prompts to save if unsaved)"),
    Command("project_info", "Project Info…", "_on_project_info", "info"),
    Command("import_csv", "From CSV…", "_on_import_csv", "import", tip="Import nodes and members from CSV"),
    Command("export_png", "PNG Image…", "_on_export_png", "image"),
    Command("export_svg", "SVG Vector…", "_on_export_svg", "file-image"),
    Command("export_pdf", "PDF Report…", "_on_export_pdf", "file-text", tip="Write the calculation report"),
    Command("beam_wizard", "Beam Wizard…", "_on_beam_wizard", "wand-sparkles"),
    Command("portal_wizard", "Portal Frame Wizard…", "_on_portal_wizard", "wand-sparkles"),
    Command("truss_wizard", "Truss Wizard…", "_on_truss_wizard", "wand-sparkles"),
    Command("frame_wizard", "Frame Wizard…", "_on_frame_wizard", "wand-sparkles"),
    # ── edit ──────────────────────────────────────────────────────────────────
    Command("undo", "Undo", lambda w: w._scene.undo(), "undo-2", "Ctrl+Z"),
    Command("redo", "Redo", lambda w: w._scene.redo(), "redo-2", "Ctrl+Y"),
    Command("copy", "Copy", "_on_copy", "copy", "Ctrl+C"),
    Command("paste", "Paste", "_on_paste", "clipboard-paste", "Ctrl+V"),
    Command("duplicate", "Duplicate", "_on_duplicate", "copy-plus", "Ctrl+D", "Duplicate the selection with an offset"),
    Command("delete", "Delete", _delete_selection, "trash-2", tip="Delete the selection (Del)"),
    Command("zoom_fit", "Zoom to Fit", lambda w: w._view.zoom_to_fit(), "maximize", "F"),
    # ── selection ─────────────────────────────────────────────────────────────
    Command("select_all", "Select All", "_on_select_all", "square-dashed-mouse-pointer", "Ctrl+A"),
    Command("deselect_all", "Deselect All", "_on_deselect_all", "", "Ctrl+Shift+A"),
    Command("invert_selection", "Invert Selection", "_on_invert_selection", "", "Ctrl+I"),
    Command("check_duplicates", "Check Duplicates…", "_on_check_duplicates", "scan-search", "",
            "Find coincident nodes and duplicate or zero-length members, then select or merge them"),
    Command("rotate_selection", "Rotate…", "_on_rotate_selection", "rotate-3d", "",
            "Rotate the selection by an exact angle about X, Y or Z — optionally as copies"),
    Command("scale_selection", "Scale Selection…", "_on_scale_selection", "scaling",
            tip="Scale the selected nodes about their centroid (or press S on the canvas)"),
    # ── drawing modes (exclusive group, see build_actions) ────────────────────
    Command("mode_select", "Select", None, "mouse-pointer-2", "S", "Select and edit (S)", True, True),
    Command("mode_node", "Add Node", None, "circle-dot", "N", "Click to place nodes (N)", True),
    Command("mode_member", "Add Member", None, "member", "M", "Drag between nodes to add a member (M)", True),
    Command("mode_measure", "Measure", None, "ruler", "R", "Measure between two nodes (R)", True),
    # ── loads ─────────────────────────────────────────────────────────────────
    Command("add_lc", "Add Case", "_on_add_lc", "plus", tip="Add a new load case"),
    Command("remove_lc", "Remove Case", "_on_remove_lc", "minus", tip="Remove the active load case"),
    Command("self_weight", "Self-weight", "_on_sw_toggle", "weight", "",
            "Include member self-weight in a dedicated load case.\n"
            "Only one case can carry self-weight; members need a density > 0.", True),
    Command("combinations", "Combinations…", "_on_combinations", "sigma", "",
            "Manage EN 1990 load combinations and solve them"),
    # ── analysis and results ──────────────────────────────────────────────────
    Command("solve", "Solve", "_on_solve", "play", "F5", "Solve the active load case (F5)"),
    Command("clear_results", "Clear Results", "_on_clear_results", "eraser"),
    Command("ov_bmd", "BMD", None, "chart-spline", "", "Bending moment diagram", True, True),
    Command("ov_sfd", "SFD", None, "chart-column", "", "Shear force diagram", True),
    Command("ov_afd", "AFD", None, "arrow-left-right", "", "Axial force diagram", True),
    Command("ov_def", "Deformed", None, "activity", "", "Deformed shape", True, True),
    Command("ov_labels", "Labels", None, "tag", "", "Value labels on the diagrams", True),
    Command("force_colours", "Force Colours", "_on_force_colour_toggle", "palette", "",
            "Colour members by axial force: red = compression, blue = tension", True),
    Command("util_colours", "Utilisation", "_on_util_colour_toggle", "gauge", "",
            "Colour members by utilisation η: steel angles by EN 1993-1-1 buckling / tension,\n"
            "other steel by cross-section only (no buckling), concrete by EN 1992-1-1 §6.1\n"
            "Green < 50%  ·  Yellow 50–100%  ·  Red > 100%", True),
    Command("animate", "Animate", "_on_animate_toggled", "clapperboard", "",
            "Loop the deformed shape from undeformed to full size (needs a solved model)", True),
    # ── view ──────────────────────────────────────────────────────────────────
    Command("show_loads", "Show Loads", "_on_show_loads_toggled", "arrow-down-to-line", "L",
            "Show load arrows and labels (L)", True, True),
    Command("colour_group", "Colour by Group", "_on_colour_by_group_toggled", "paintbrush", "Ctrl+G",
            "Tint members by their group label, with a legend (Ctrl+G)", True),
    Command("thickness", "Thickness by Section", "_on_thickness_toggled", "pen-line", "Ctrl+T",
            "Draw members thicker the larger their cross-section area (Ctrl+T)", True),
    Command("local_axes", "Local Axes", "_on_toggle_local_axes", "axis-3d", "",
            "Show the local axis triad on all members\n"
            "Red = x (along member)  Green = y (strong axis)  Blue = z (weak axis)", True),
    Command("section_cut", "Section Cut…", "_open_section_cut", "scissors", "",
            "Hide everything on one side of a plane to look inside the model"),
    Command("reset_layout", "Reset Panel Layout", "_reset_dock_layout", "layout-panel-left"),
    Command("ribbon_interface", "Ribbon Interface", "_on_interface_toggled", "", "",
            "Use the ribbon (on) or the classic menus and toolbars (off).\n"
            "Takes effect the next time StructLab starts.", True),
    # ── tools and help ────────────────────────────────────────────────────────
    Command("console", "Python Console", "_open_console", "terminal", "Ctrl+`"),
    Command("keyboard_shortcuts", "Keyboard Shortcuts…", "_on_keyboard_shortcuts", "keyboard"),
    Command("about", "About StructLab…", "_on_about", "circle-help"),
)

# Exclusive groups: (keys, handler(window, key)) — only one action of the group is checked.
MODE_KEYS = ("mode_select", "mode_node", "mode_member", "mode_measure")
OVERLAY_KEYS = {"ov_bmd": "BMD", "ov_sfd": "SFD", "ov_afd": "AFD", "ov_def": "Def", "ov_labels": "Labels"}


def _make(win, c: Command) -> QAction:
    act = QAction(icon(c.icon) if c.icon else icon(""), c.text, win)
    if c.shortcut:
        act.setShortcut(QKeySequence(c.shortcut))
    if c.tip:
        act.setToolTip(c.tip)
        act.setStatusTip(c.tip.splitlines()[0])
    if c.checkable:
        act.setCheckable(True)
        act.setChecked(c.checked)
    if c.handler is not None:
        slot = getattr(win, c.handler) if isinstance(c.handler, str) else (lambda *_a, f=c.handler: f(win))
        (act.toggled if c.checkable else act.triggered).connect(slot)
    win.addAction(act)
    return act


def build_actions(win) -> dict[str, QAction]:
    """Create every command's QAction on ``win`` and return them by key."""
    actions = {c.key: _make(win, c) for c in COMMANDS}

    group = QActionGroup(win)
    group.setExclusive(True)
    from ui_qt.canvas import CanvasMode
    modes = dict(zip(MODE_KEYS, (CanvasMode.SELECT, CanvasMode.ADD_NODE,
                                 CanvasMode.ADD_MEMBER, CanvasMode.MEASURE)))
    for key, mode in modes.items():
        group.addAction(actions[key])
        actions[key].triggered.connect(lambda _c=False, m=mode: win._set_mode(m))
    win._mode_action_group = group

    for key, layer in OVERLAY_KEYS.items():
        target = "Deformed" if layer == "Def" else layer
        actions[key].toggled.connect(lambda checked, k=target: win._on_overlay_toggle(k, checked))
    return actions
