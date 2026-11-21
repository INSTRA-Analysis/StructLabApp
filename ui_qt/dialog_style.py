"""Shared look for StructLab's dialogs: header card, framed group boxes, one primary button.

``apply_dialog_style(dialog, title, subtitle, accent, icon_name)`` is called at the end of a
dialog's ``__init__`` (after its layout is built). It

* names the dialog ``themed_dialog`` so the rules in ``theme.STYLESHEET`` apply to it only
  (group boxes become outlined boxes with small grey titles, like the main window docks);
* inserts a header card at the top: accent bar and icon in the dialog's category colour
  (theme.GEOMETRY for the wizards, theme.LOAD for combinations…), title and one-line
  description;
* marks the OK button of every QDialogButtonBox as the primary button.

``mark_primary(button)`` marks any other button as the dialog's main action.
"""

from __future__ import annotations

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import (
    QAbstractButton, QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel, QVBoxLayout,
    QWidget,
)

from ui_qt import theme
from ui_qt.icons import icon


def mark_primary(button: QAbstractButton) -> None:
    """Style ``button`` as the dialog's main action (accent fill)."""
    button.setProperty("role", "primary")
    button.style().unpolish(button)
    button.style().polish(button)


def _header(title: str, subtitle: str, accent: str, icon_name: str) -> QFrame:
    card = QFrame()
    card.setObjectName("dialog_header")
    row = QHBoxLayout(card)
    row.setContentsMargins(0, 0, 12, 0)
    row.setSpacing(12)

    bar = QFrame()
    bar.setObjectName("dialog_header_bar")
    bar.setFixedWidth(4)
    bar.setStyleSheet(f"background: {accent}; border: none;"
                      " border-top-left-radius: 6px; border-bottom-left-radius: 6px;")
    row.addWidget(bar)

    if icon_name:
        ico = QLabel()
        ico.setPixmap(icon(icon_name, accent).pixmap(QSize(24, 24)))
        ico.setStyleSheet("background: transparent; border: none;")
        row.addWidget(ico, 0, Qt.AlignmentFlag.AlignVCenter)

    text = QVBoxLayout()
    text.setContentsMargins(0, 9, 0, 9)
    text.setSpacing(2)
    t = QLabel(title)
    t.setObjectName("dialog_header_title")
    text.addWidget(t)
    if subtitle:
        s = QLabel(subtitle)
        s.setObjectName("dialog_header_sub")
        s.setWordWrap(True)
        text.addWidget(s)
    row.addLayout(text, 1)
    return card


def apply_dialog_style(dialog: QDialog, title: str, subtitle: str = "",
                       accent: str = theme.CYAN, icon_name: str = "") -> None:
    """Give ``dialog`` the StructLab dialog look (see the module docstring)."""
    dialog.setObjectName("themed_dialog")
    lay = dialog.layout()
    if lay is not None and not isinstance(lay, QVBoxLayout):
        # Any other top-level layout (form, grid…) moves into a body widget under the header
        body = QWidget()
        body.setLayout(lay)               # reparents the layout away from the dialog
        lay.setContentsMargins(0, 0, 0, 0)
        lay = QVBoxLayout(dialog)
        lay.addWidget(body, 1)
    if lay is not None:
        lay.setContentsMargins(14, 14, 14, 12)
        lay.setSpacing(10)
        lay.insertWidget(0, _header(title, subtitle, accent, icon_name))
    for box in dialog.findChildren(QDialogButtonBox):
        ok = box.button(QDialogButtonBox.StandardButton.Ok)
        if ok is not None:
            mark_primary(ok)
