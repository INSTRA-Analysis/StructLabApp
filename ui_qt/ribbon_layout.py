"""The StructLab ribbon: which commands go on which tab and group.

``build_ribbon(window)`` places the window's shared actions (ui_qt/commands.py) and input
widgets into a RibbonBar. Only placement lives here; behaviour stays on the actions, so the
classic menus and the ribbon always do the same thing.

Tabs: Home · Model · Loads · Analysis · Results · View · Tools, plus the File button.
"""

from __future__ import annotations

from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import QMenu

from ui_qt import theme
from ui_qt.icons import icon
from ui_qt.ribbon import RibbonBar


def _menu_action(win, text: str, icon_name: str, menu: QMenu, tip: str = "",
                 tint: str | None = None) -> QAction:
    """An action whose button opens ``menu`` (kept alive by parenting it to the window)."""
    act = QAction(icon(icon_name, tint), text, win)
    act.setMenu(menu)
    if tip:
        act.setToolTip(tip)
    return act


def _supports_menu(win) -> QMenu:
    """Assign a support type to the selected nodes (same as the canvas right-click menu)."""
    from ui_qt.canvas_items import NodeItem
    from ui_qt.model_state import SupportType
    menu = QMenu(win)
    for label, stype in (("Fixed", SupportType.FIXED), ("Pinned", SupportType.PIN),
                         ("Roller", SupportType.ROLLER), ("Roller Y", SupportType.ROLLER_Y),
                         ("Roller Z", SupportType.ROLLER_Z), ("None", SupportType.FREE)):
        def apply(_checked=False, st=stype) -> None:
            nodes = [it.node for it in win._scene.selectedItems() if isinstance(it, NodeItem)]
            if not nodes:
                win._sb.showMessage("Select one or more nodes first.")
                return
            win._view._set_support(nodes, st)
        menu.addAction(label, apply)
    return menu


def build_ribbon(win) -> RibbonBar:
    a = win._act
    bar = RibbonBar(win)
    bar.set_file_menu(win._file_menu)
    bar.add_workspace_switcher([a[k] for k in ("ws_model", "ws_loads", "ws_results")])
    for key in ("save", "undo", "redo", "solve"):
        bar.add_quick_action(a[key])

    # ── Home ──────────────────────────────────────────────────────────────────
    home = bar.add_tab("Home")
    g = home.add_group("Clipboard")
    g.add_large(a["paste"])
    for key in ("copy", "duplicate", "delete"):
        g.add_small(a[key])
    g = home.add_group("Undo")
    g.add_small(a["undo"])
    g.add_small(a["redo"])
    g = home.add_group("Draw")
    g.add_large(a["mode_select"])
    for key in ("mode_node", "mode_member", "mode_measure"):
        g.add_small(a[key])
    g.end_column()
    g.add_widget(win._member_type_combo, "Type")
    g = home.add_group("Select")
    for key in ("select_all", "deselect_all", "invert_selection"):
        g.add_small(a[key])
    g.add_small(_menu_action(win, "By Type", "list-tree", win._select_type_menu))
    g.add_small(_menu_action(win, "By Profile", "layers", win._select_profile_menu))
    g.add_small(_menu_action(win, "By Group", "boxes", win._select_group_menu))

    # ── Model ─────────────────────────────────────────────────────────────────
    model = bar.add_tab("Model")
    g = model.add_group("Templates")
    g.add_large(_menu_action(win, "Wizards", "wand-sparkles", win._wizards_menu,
                             "Generate a beam, portal frame, truss or frame", theme.GEOMETRY))
    g = model.add_group("Geometry")
    mirror = QAction(icon("flip-horizontal-2", theme.GEOMETRY), "Mirror…", win)
    mirror.setToolTip("Mirror the selection about a plane")
    mirror.triggered.connect(lambda: win._view._on_mirror(True))
    g.add_small(mirror)
    g.add_small(a["rotate_selection"])
    g.add_small(a["scale_selection"])
    g = model.add_group("Element type")
    g.add_small(a["set_bars"])
    g.add_small(a["set_beams"])
    g = model.add_group("Check")
    g.add_large(a["check_duplicates"])
    g.add_small(a["crossing_braces"])
    g = model.add_group("Supports")
    g.add_large(_menu_action(win, "Supports", "support", _supports_menu(win),
                             "Assign a support to the selected nodes", theme.SUPPORT))
    g = model.add_group("Sections")
    g.add_large(a["panel_groups"])

    # ── Loads ─────────────────────────────────────────────────────────────────
    loads = bar.add_tab("Loads")
    g = loads.add_group("Load Case")
    g.add_widget(win._lc_combo, "Case")
    g.add_small(a["add_lc"])
    g.add_small(a["remove_lc"])
    g.end_column()
    g.add_large(a["self_weight"])
    g = loads.add_group("Combinations")
    g.add_large(a["combinations"])

    # ── Analysis ──────────────────────────────────────────────────────────────
    analysis = bar.add_tab("Analysis")
    g = analysis.add_group("Run")
    g.add_large(a["solve"])
    g.add_large(a["combinations"])
    g = analysis.add_group("Results")
    g.add_small(a["clear_results"])

    # ── Results ───────────────────────────────────────────────────────────────
    results = bar.add_tab("Results")
    g = results.add_group("Diagrams")
    for key in ("ov_bmd", "ov_sfd", "ov_afd", "ov_def", "ov_labels"):
        g.add_small(a[key])
    g.end_column()
    g.add_widget(win._diag_scale_spin, "Diagram ×")
    g.add_widget(win._def_scale_spin, "Deformed ×")
    g = results.add_group("Colouring")
    g.add_small(a["force_colours"])
    g.add_small(a["util_colours"])
    g = results.add_group("Result Set")
    g.add_widget(win._combo_view)
    g = results.add_group("Present")
    g.add_large(a["animate"])
    g.add_large(a["export_pdf"])

    # ── View ──────────────────────────────────────────────────────────────────
    view = bar.add_tab("View")
    g = view.add_group("Camera")
    g.add_large(a["zoom_fit"])
    for key in ("view_top", "view_front", "view_left", "view_right",
                "view_sw", "view_se", "view_nw", "view_ne"):
        g.add_small(a[key])
    g.end_column()
    g.add_large(a["named_views"])
    g = view.add_group("Working Plane")
    for key in ("plane_xy", "plane_xz", "plane_yz", "plane_free"):
        g.add_small(a[key])
    g.end_column()
    g.add_widget(win._plane_label)
    g.add_widget(win._plane_spin)
    g = view.add_group("Display")
    for key in ("show_loads", "colour_group", "thickness", "local_axes", "section_cut"):
        g.add_small(a[key])
    g = view.add_group("Panels")
    for key in ("panel_properties", "panel_results", "panel_groups", "reset_layout"):
        g.add_small(a[key])
    g = view.add_group("Interface")
    g.add_small(a["ribbon_interface"])
    g.add_small(a["banner_choice"])

    # ── Tools ─────────────────────────────────────────────────────────────────
    tools = bar.add_tab("Tools")
    g = tools.add_group("Scripting")
    g.add_large(a["console"])
    g = tools.add_group("Help")
    g.add_small(a["keyboard_shortcuts"])
    g.add_small(a["about"])

    collapse = QAction("Collapse Ribbon", win)
    collapse.setShortcut(QKeySequence("Ctrl+F1"))
    collapse.triggered.connect(bar.toggle_collapsed)
    win.addAction(collapse)
    a["collapse_ribbon"] = collapse
    return bar
