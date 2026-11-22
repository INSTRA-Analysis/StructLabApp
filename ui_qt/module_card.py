"""The card a module's button opens while the module is not available yet ("Coming soon").

Built from the module's ModuleSpec (ui_qt/modules.py): what it will do, the planned scope,
what the model will need. Shared by the ribbon / menu command and the start page.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout, QWidget

from ui_qt import theme
from ui_qt.dialog_style import apply_dialog_style
from ui_qt.modules import ModuleSpec


class ModuleCard(QDialog):
    """What a module will do, before it exists."""

    def __init__(self, spec: ModuleSpec, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.spec = spec
        self.setWindowTitle(f"{spec.title} — {spec.status_label or 'Module'}")
        self.setMinimumWidth(480)
        lay = QVBoxLayout(self)

        summary = QLabel(spec.summary)
        summary.setObjectName("module_summary")
        summary.setWordWrap(True)
        summary.setStyleSheet(f"color: {theme.TEXT}; font-size: 13px;")
        lay.addWidget(summary)

        if spec.scope:
            head = QLabel("PLANNED SCOPE" if spec.status == "coming_soon" else "SCOPE")
            head.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: 10px; font-weight: bold;"
                               " letter-spacing: 1px; margin-top: 4px;")
            lay.addWidget(head)
            items = "".join(f"<li style='margin-bottom:4px'>{line}</li>" for line in spec.scope)
            scope = QLabel(f"<ul style='margin:0 0 0 -18px'>{items}</ul>")
            scope.setObjectName("module_scope")
            scope.setTextFormat(Qt.TextFormat.RichText)
            scope.setWordWrap(True)
            lay.addWidget(scope)

        if spec.requires:
            needs = QLabel(f"<b>Your model will need:</b> {', '.join(spec.requires)}")
            needs.setObjectName("module_requires")
            needs.setTextFormat(Qt.TextFormat.RichText)
            needs.setWordWrap(True)
            needs.setStyleSheet(f"background: {theme.BG}; color: {theme.TEXT_DIM};"
                                " padding: 8px 10px; border-radius: 4px;")
            lay.addWidget(needs)

        if spec.status == "coming_soon":
            note = QLabel("Until then, Static Analysis covers frames, trusses and towers.")
            note.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: 11px;")
            lay.addWidget(note)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        apply_dialog_style(self, spec.title, spec.status_label or "Module", spec.hue, spec.icon)


def show_module_card(parent: QWidget | None, spec: ModuleSpec) -> None:
    """Open the card for ``spec`` (modal)."""
    ModuleCard(spec, parent).exec()
