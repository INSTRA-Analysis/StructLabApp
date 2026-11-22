"""Ribbon widget: tabs, groups, large/small buttons bound to actions, collapsing."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication([])


def _action(text, checkable=False, parent=None):
    from PyQt6.QtGui import QAction
    a = QAction(text, parent)
    a.setCheckable(checkable)
    return a


def test_tabs_switch_pages_and_find_by_title(qapp):
    from ui_qt.ribbon import RibbonBar
    bar = RibbonBar()
    home, model = bar.add_tab("Home"), bar.add_tab("Model")
    assert bar.tabs.count() == 2 and bar.current_page() is home
    bar.set_current_tab("Model")
    assert bar.current_page() is model
    assert bar.page("Home") is home and bar.page("Nope") is None


def test_buttons_follow_their_action(qapp):
    from PyQt6.QtWidgets import QToolButton
    from ui_qt.ribbon import RibbonBar
    bar = RibbonBar()
    group = bar.add_tab("Home").add_group("Edit")
    fired = []
    act = _action("Undo")
    act.triggered.connect(lambda: fired.append(1))
    big = group.add_large(act)
    assert big.toolButtonStyle() == big.toolButtonStyle().ToolButtonTextUnderIcon
    big.click()
    assert fired == [1]
    act.setEnabled(False)
    assert not big.isEnabled()
    act.setText("Undo move")
    assert big.text() == "Undo move"


def test_checkable_action_keeps_button_and_action_in_sync(qapp):
    from ui_qt.ribbon import RibbonBar
    group = RibbonBar().add_tab("Results").add_group("Diagrams")
    act = _action("BMD", checkable=True)
    btn = group.add_small(act)
    btn.click()
    assert act.isChecked() and btn.isChecked()
    act.setChecked(False)
    assert not btn.isChecked()


def test_small_items_stack_three_per_column(qapp):
    from PyQt6.QtWidgets import QComboBox
    from ui_qt.ribbon import RibbonBar, SMALL_ROWS
    group = RibbonBar().add_tab("Home").add_group("Draw")
    for i in range(SMALL_ROWS + 1):
        group.add_small(_action(f"s{i}"))
    columns = [group._row.itemAt(i).layout() for i in range(group._row.count())]
    assert [c.count() for c in columns] == [SMALL_ROWS, 1]
    group.end_column()
    combo = QComboBox()
    holder = group.add_widget(combo, "Type:")
    assert combo.parent() is holder                      # labelled field in a fresh column
    assert group._row.count() == 3


def test_collapse_by_double_click_and_expand_by_clicking_a_tab(qapp):
    from ui_qt.ribbon import RibbonBar
    bar = RibbonBar()
    bar.add_tab("Home")
    bar.add_tab("View")
    seen = []
    bar.collapsed_changed.connect(seen.append)
    bar.tabs.tabBarDoubleClicked.emit(0)
    assert bar.is_collapsed() and bar.pages.isHidden() and seen == [True]
    bar.tabs.tabBarClicked.emit(1)
    assert not bar.is_collapsed() and not bar.pages.isHidden() and seen == [True, False]
    bar.collapse_button.click()
    assert bar.is_collapsed()


def test_file_menu_and_quick_access(qapp):
    from PyQt6.QtWidgets import QMenu
    from ui_qt.ribbon import RibbonBar
    bar = RibbonBar()
    menu = QMenu()
    menu.addAction("Open…")
    bar.set_file_menu(menu)
    assert bar.file_button.menu() is menu
    save = _action("Save")
    btn = bar.add_quick_action(save)
    assert btn.defaultAction() is save


def test_action_with_menu_gets_an_instant_popup(qapp):
    from PyQt6.QtWidgets import QMenu, QToolButton
    from ui_qt.ribbon import RibbonBar
    act = _action("Named Views")
    menu = QMenu()                                        # keep a reference: Python owns it
    act.setMenu(menu)
    btn = RibbonBar().add_tab("View").add_group("Camera").add_large(act)
    assert btn.popupMode() == QToolButton.ToolButtonPopupMode.InstantPopup


# ── the ribbon in the main window ─────────────────────────────────────────────

def _window(qapp, monkeypatch, mode):
    from PyQt6.QtWidgets import QMessageBox
    from ui_qt.main_window import MainWindow
    monkeypatch.setenv("STRUCTLAB_UI", mode)
    monkeypatch.setattr(MainWindow, "_show_welcome", lambda self: None)
    monkeypatch.setattr(MainWindow, "_check_autosave_recovery", lambda self: False)
    for name in ("question", "warning", "information", "critical"):
        monkeypatch.setattr(QMessageBox, name,
                            lambda *a, _n=name, **k: pytest.fail(f"unexpected {_n} dialog: {a[1:3]}"))
    return MainWindow()


def _close(qapp, win):
    win._scene.clearSelection()
    qapp.processEvents()
    win._is_dirty = False
    win.close()


def test_window_uses_the_ribbon_and_hides_the_menu_bar(qapp, monkeypatch):
    win = _window(qapp, monkeypatch, "ribbon")
    try:
        bar = win._ribbon
        tabs = [bar.tabs.tabText(i) for i in range(bar.tabs.count())]
        assert tabs == ["Home", "Model", "Loads", "Analysis", "Results", "View", "Modules", "Tools"]
        assert win.menuBar().isHidden()
        assert bar.file_button.menu() is win._file_menu
        # the ribbon's Solve button and the menu's Solve are the same action
        group = bar.page("Analysis").groups[0]
        assert group.buttons[0].defaultAction() is win._act["solve"]
        texts = {b.defaultAction().text() for p in bar._page_list for g in p.groups for b in g.buttons}
        for wanted in ("Paste", "Select", "Self-weight", "Solve", "BMD", "Animate", "Named Views",
                       "Section Cut…", "Python Console", "Supports", "Wizards"):
            assert wanted in texts, wanted
    finally:
        _close(qapp, win)


def test_ribbon_widgets_are_the_shared_inputs(qapp, monkeypatch):
    win = _window(qapp, monkeypatch, "ribbon")
    try:
        assert win._lc_combo.window() is win and win._lc_combo.isVisibleTo(win._ribbon.page("Loads"))
        win._ribbon.set_current_tab("Loads")
        assert win._ribbon.current_page().isAncestorOf(win._lc_combo)
        assert win._ribbon.page("Home").isAncestorOf(win._member_type_combo)
        assert win._ribbon.page("Results").isAncestorOf(win._diag_scale_spin)
    finally:
        _close(qapp, win)


def test_supports_drop_down_assigns_to_the_selected_nodes(qapp, monkeypatch):
    from ui_qt.model_state import ModelState, SupportType
    win = _window(qapp, monkeypatch, "ribbon")
    try:
        s = ModelState()
        a, b = s.add_node(0, 0, 0), s.add_node(3, 0, 0)
        s.add_member(a.id, b.id)
        win._apply_model_state(s, "t")
        win._scene._node_items[a.id].setSelected(True)
        support_btn = next(btn for p in win._ribbon._page_list for g in p.groups for btn in g.buttons
                           if btn.defaultAction().text() == "Supports")
        menu = support_btn.defaultAction().menu()
        next(x for x in menu.actions() if x.text() == "Pinned").trigger()
        assert win._scene.model_state.get_node(a.id).support_type == SupportType.PIN
        assert win._scene.model_state.get_node(b.id).support_type == SupportType.FREE
    finally:
        _close(qapp, win)


def test_ctrl_f1_collapses_and_dock_shortcuts_survive_the_hidden_menu_bar(qapp, monkeypatch):
    win = _window(qapp, monkeypatch, "ribbon")
    try:
        win._act["collapse_ribbon"].trigger()
        assert win._ribbon.is_collapsed()
        win._act["collapse_ribbon"].trigger()
        assert not win._ribbon.is_collapsed()
        shortcuts = {act.shortcut().toString() for act in win.actions()}
        assert {"Alt+1", "Alt+2", "Alt+3", "Ctrl+F1"} <= shortcuts
    finally:
        _close(qapp, win)


def test_classic_mode_keeps_menus_and_toolbars(qapp, monkeypatch):
    from PyQt6.QtWidgets import QToolBar
    win = _window(qapp, monkeypatch, "classic")
    try:
        assert not hasattr(win, "_ribbon")
        assert not win.menuBar().isHidden()
        titles = [tb.windowTitle() for tb in win.findChildren(QToolBar)]
        assert "Main" in titles and "Visualization" in titles
    finally:
        _close(qapp, win)
