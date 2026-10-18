"""Ribbon command bar: tabs of labelled groups holding large and small buttons.

StructLab's own implementation (no third-party ribbon library), styled from ``theme``.
Every button is a QToolButton bound to a QAction with ``setDefaultAction``, so text, icon,
shortcut, checked and enabled state live on the action and stay in sync with any menu
that shows the same action.

Structure::

    RibbonBar
      ├── top row: [File ▾] [tab][tab]…            [quick-access buttons] [⌃]
      └── pages (one per tab)
            RibbonPage ── RibbonGroup ── large buttons, columns of small buttons / widgets
                                    └── group title

Collapse: double-click a tab, the ⌃ button, or ``RibbonBar.toggle_collapsed``. While
collapsed, clicking a tab expands the ribbon again.
"""

from __future__ import annotations

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMenu, QSizePolicy, QStackedWidget, QTabBar,
    QToolButton, QVBoxLayout, QWidget,
)

from ui_qt.theme import BG, BORDER, CYAN, CYAN_TINT, SURFACE, SURFACE2, TEXT, TEXT_DIM

LARGE_ICON = QSize(28, 28)
SMALL_ICON = QSize(16, 16)
SMALL_ROWS = 3                      # small buttons / widgets stacked per column

STYLESHEET = f"""
QWidget#ribbon {{ background: {SURFACE}; }}
QWidget#ribbon_top {{ background: {BG}; }}
QTabBar#ribbon_tabs::tab {{
    background: transparent; color: {TEXT_DIM}; padding: 5px 14px; border: none;
    border-bottom: 2px solid transparent;
}}
QTabBar#ribbon_tabs::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {CYAN}; }}
QTabBar#ribbon_tabs::tab:hover {{ color: {TEXT}; }}
QToolButton#ribbon_file {{
    background: {CYAN_TINT}; color: {TEXT}; border: 1px solid {CYAN}; border-radius: 3px;
    padding: 3px 12px; margin: 2px 6px;
}}
QToolButton#ribbon_file::menu-indicator {{ image: none; }}
QStackedWidget#ribbon_pages {{ background: {SURFACE}; border-top: 1px solid {BORDER};
    border-bottom: 1px solid {BORDER}; }}
QFrame#ribbon_group {{ border-right: 1px solid {BORDER}; }}
QLabel#ribbon_group_title {{ color: {TEXT_DIM}; font-size: 8pt; padding-top: 1px; }}
QToolButton#ribbon_large, QToolButton#ribbon_small, QToolButton#ribbon_quick {{
    background: transparent; color: {TEXT}; border: 1px solid transparent; border-radius: 3px;
}}
QToolButton#ribbon_large {{ padding: 2px 4px; }}
QToolButton#ribbon_small {{ padding: 1px 4px; text-align: left; }}
QToolButton#ribbon_large:hover, QToolButton#ribbon_small:hover, QToolButton#ribbon_quick:hover {{
    background: {SURFACE2}; border-color: {BORDER};
}}
QToolButton#ribbon_large:checked, QToolButton#ribbon_small:checked {{
    background: {CYAN_TINT}; border-color: {CYAN};
}}
QToolButton#ribbon_large:disabled, QToolButton#ribbon_small:disabled {{ color: {TEXT_DIM}; }}
QLabel#ribbon_field_label {{ color: {TEXT_DIM}; }}
"""


def _tool_button(action: QAction, large: bool) -> QToolButton:
    btn = QToolButton()
    btn.setDefaultAction(action)
    btn.setAutoRaise(True)
    if large:
        btn.setObjectName("ribbon_large")
        btn.setIconSize(LARGE_ICON)
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        btn.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        btn.setMinimumWidth(52)
    else:
        btn.setObjectName("ribbon_small")
        btn.setIconSize(SMALL_ICON)
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    if action.menu() is not None:
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    return btn


class RibbonGroup(QFrame):
    """A titled block of commands inside a ribbon page."""

    def __init__(self, title: str) -> None:
        super().__init__()
        self.setObjectName("ribbon_group")
        self.title = title
        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 2, 4, 1)
        outer.setSpacing(0)
        self._row = QHBoxLayout()
        self._row.setSpacing(2)
        outer.addLayout(self._row, 1)
        label = QLabel(title)
        label.setObjectName("ribbon_group_title")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(label)
        self._column: QVBoxLayout | None = None
        self._column_count = 0
        self.buttons: list[QToolButton] = []

    def add_large(self, action: QAction) -> QToolButton:
        """A big icon-over-text button (the group's main commands)."""
        self._column = None
        btn = _tool_button(action, large=True)
        self._row.addWidget(btn)
        self.buttons.append(btn)
        return btn

    def _next_slot(self) -> QVBoxLayout:
        if self._column is None or self._column_count >= SMALL_ROWS:
            self._column = QVBoxLayout()
            self._column.setSpacing(1)
            self._column_count = 0
            self._row.addLayout(self._column)
        self._column_count += 1
        return self._column

    def add_small(self, action: QAction) -> QToolButton:
        """A compact icon-beside-text button; consecutive ones stack in columns of three."""
        btn = _tool_button(action, large=False)
        self._next_slot().addWidget(btn)
        self.buttons.append(btn)
        return btn

    def add_widget(self, widget: QWidget, label: str = "") -> QWidget:
        """An input control (combo box, spin box) in the small-button grid, with a label."""
        if label:
            row = QWidget()
            lay = QHBoxLayout(row)
            lay.setContentsMargins(2, 0, 2, 0)
            lay.setSpacing(4)
            text = QLabel(label)
            text.setObjectName("ribbon_field_label")
            lay.addWidget(text)
            lay.addWidget(widget, 1)
            self._next_slot().addWidget(row)
            return row
        self._next_slot().addWidget(widget)
        return widget

    def end_column(self) -> None:
        """Start the next small item in a fresh column."""
        if self._column is not None:
            self._column.addStretch(1)
        self._column = None


class RibbonPage(QWidget):
    """One tab's content: groups laid out left to right."""

    def __init__(self, title: str) -> None:
        super().__init__()
        self.title = title
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(2, 2, 2, 2)
        self._layout.setSpacing(0)
        self._layout.addStretch(1)
        self.groups: list[RibbonGroup] = []

    def add_group(self, title: str) -> RibbonGroup:
        group = RibbonGroup(title)
        self._layout.insertWidget(self._layout.count() - 1, group)
        self.groups.append(group)
        return group


class RibbonBar(QWidget):
    """The whole ribbon: File menu button, tabs, quick-access buttons and pages."""

    collapsed_changed = pyqtSignal(bool)

    PAGE_HEIGHT = 96

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ribbon")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(STYLESHEET)
        self._collapsed = False

        top = QWidget()
        top.setObjectName("ribbon_top")
        top.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        top_lay = QHBoxLayout(top)
        top_lay.setContentsMargins(0, 0, 4, 0)
        top_lay.setSpacing(2)

        self.file_button = QToolButton()
        self.file_button.setObjectName("ribbon_file")
        self.file_button.setText("File")
        self.file_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        top_lay.addWidget(self.file_button)

        self.tabs = QTabBar()
        self.tabs.setObjectName("ribbon_tabs")
        self.tabs.setDrawBase(False)
        self.tabs.setExpanding(False)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.tabs.tabBarClicked.connect(self._on_tab_clicked)
        self.tabs.tabBarDoubleClicked.connect(lambda _i: self.toggle_collapsed())
        top_lay.addWidget(self.tabs)
        top_lay.addStretch(1)

        self._quick = QHBoxLayout()
        self._quick.setSpacing(0)
        top_lay.addLayout(self._quick)

        self.collapse_button = QToolButton()
        self.collapse_button.setObjectName("ribbon_quick")
        self.collapse_button.setAutoRaise(True)
        self.collapse_button.setToolTip("Collapse / expand the ribbon (Ctrl+F1)")
        self.collapse_button.clicked.connect(self.toggle_collapsed)
        top_lay.addWidget(self.collapse_button)

        self.pages = QStackedWidget()
        self.pages.setObjectName("ribbon_pages")
        self.pages.setFixedHeight(self.PAGE_HEIGHT)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(top)
        lay.addWidget(self.pages)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._update_collapse_button()

    # ── building ──────────────────────────────────────────────────────────────

    def add_tab(self, title: str) -> RibbonPage:
        page = RibbonPage(title)
        self.pages.addWidget(page)
        self.tabs.addTab(title)
        return page

    def page(self, title: str) -> RibbonPage | None:
        for i in range(self.pages.count()):
            page = self.pages.widget(i)
            if page.title == title:
                return page
        return None

    def set_file_menu(self, menu: QMenu) -> None:
        self.file_button.setMenu(menu)

    def add_quick_action(self, action: QAction) -> QToolButton:
        btn = QToolButton()
        btn.setObjectName("ribbon_quick")
        btn.setDefaultAction(action)
        btn.setAutoRaise(True)
        btn.setIconSize(SMALL_ICON)
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self._quick.addWidget(btn)
        return btn

    # ── tabs and collapsing ───────────────────────────────────────────────────

    def set_current_tab(self, title: str) -> None:
        for i in range(self.tabs.count()):
            if self.tabs.tabText(i) == title:
                self.tabs.setCurrentIndex(i)
                return

    def _on_tab_changed(self, index: int) -> None:
        if index >= 0:
            self.pages.setCurrentIndex(index)

    def _on_tab_clicked(self, index: int) -> None:
        if self._collapsed and index >= 0:
            self.set_collapsed(False)

    def is_collapsed(self) -> bool:
        return self._collapsed

    def set_collapsed(self, collapsed: bool) -> None:
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        self.pages.setVisible(not collapsed)
        self._update_collapse_button()
        self.collapsed_changed.emit(collapsed)

    def toggle_collapsed(self) -> None:
        self.set_collapsed(not self._collapsed)

    def _update_collapse_button(self) -> None:
        self.collapse_button.setText("⌄" if self._collapsed else "⌃")
