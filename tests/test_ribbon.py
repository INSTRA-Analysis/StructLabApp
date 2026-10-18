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
    assert bar.tabs.count() == 2 and bar.pages.currentWidget() is home
    bar.set_current_tab("Model")
    assert bar.pages.currentWidget() is model
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
