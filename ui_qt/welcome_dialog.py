"""WelcomeDialog — shown at startup to choose a structure type or open a file."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout,
    QLabel, QListWidget, QListWidgetItem, QPushButton, QTabWidget,
    QVBoxLayout, QWidget,
)

_TAB_STYLE = """
QTabWidget::pane {
    border: 1px solid #2a2a34;
    background: #1a1a22;
    border-radius: 0 4px 4px 4px;
}
QTabBar::tab {
    background: #16161e;
    color: #666;
    border: 1px solid #2a2a34;
    border-bottom: none;
    padding: 7px 28px;
    margin-right: 2px;
    font-size: 12px;
    font-weight: bold;
}
QTabBar::tab:selected {
    background: #1a1a22;
    color: #00ACC1;
    border-color: #2a2a34;
}
QTabBar::tab:hover:!selected {
    color: #aaa;
    background: #1e1e28;
}
"""


class _StructCard(QFrame):
    """Clickable card button for a structure type."""

    clicked = pyqtSignal()

    _NORMAL = (
        "QFrame { background:#1e1e28; border:1px solid #333; border-radius:6px; }"
    )
    _HOVER = (
        "QFrame { background:#252530; border:1px solid #00ACC1; border-radius:6px; }"
    )

    def __init__(self, name: str, symbol: str, desc: str, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(128, 118)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(self._NORMAL)

        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(8, 10, 8, 8)

        sym = QLabel(symbol)
        sym.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sym.setStyleSheet("color:#00ACC1; font-size:16px; font-weight:bold; background:transparent;")
        layout.addWidget(sym)

        title = QLabel(name)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        f = QFont(); f.setBold(True); f.setPointSize(11)
        title.setFont(f)
        title.setStyleSheet("color:#eee; background:transparent;")
        layout.addWidget(title)

        description = QLabel(desc)
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        description.setWordWrap(True)
        description.setStyleSheet("color:#777; font-size:9px; background:transparent;")
        layout.addWidget(description)

    def enterEvent(self, event) -> None:
        self.setStyleSheet(self._HOVER)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.setStyleSheet(self._NORMAL)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


def _make_cards_page(cards: list[tuple[str, str, str, str]],
                     callback) -> QWidget:
    """Build a tab page containing a row of _StructCard widgets."""
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(0)

    row = QHBoxLayout()
    row.setSpacing(10)
    for choice, name, sym, desc in cards:
        card = _StructCard(name, sym, desc)
        card.clicked.connect(lambda c=choice: callback(c))
        row.addWidget(card)
    row.addStretch()
    layout.addLayout(row)
    layout.addStretch()
    return page


class WelcomeDialog(QDialog):
    """Startup dialog: choose structure type, recent file, or blank canvas.

    After exec(), read:
      ``self.choice`` — "beam" | "frame" | "truss" | "blank" | "open" | "file:<path>"
      ``self.is_3d``  — True if user selected the 3D tab
    """

    def __init__(self, parent=None, recent_files: list[str] | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Welcome to StructLab")
        self.setModal(True)
        self.setMinimumWidth(600)
        self.choice: str = "blank"
        self.is_3d: bool = False
        self._build_ui(recent_files or [])

    def _build_ui(self, recent_files: list[str]) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(14)
        root.setContentsMargins(28, 24, 28, 24)

        # ── Branding ──────────────────────────────────────────────────────────
        title = QLabel("StructLab")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        f = QFont(); f.setPointSize(26); f.setBold(True)
        title.setFont(f)
        title.setStyleSheet("color:#00ACC1;")
        root.addWidget(title)

        sub = QLabel("Structural Analysis  —  Direct Stiffness Method")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet("color:#666; font-size:11px;")
        root.addWidget(sub)

        root.addWidget(self._hline())

        # ── Structure type label ───────────────────────────────────────────────
        section_lbl = QLabel("Start a new model")
        section_lbl.setStyleSheet("font-weight:bold; font-size:12px; color:#bbb;")
        root.addWidget(section_lbl)

        # ── Tab widget ─────────────────────────────────────────────────────────
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(_TAB_STYLE)
        self._tabs.setFixedHeight(172)

        CARDS_2D = [
            ("beam",  "Beam",   "━━━━",
             "Continuous beams,\nGerber beams,\nUDL + point loads"),
            ("frame", "Frame",  "╬ ╬",
             "Portal frames,\nmulti-bay &\nmulti-storey"),
            ("truss", "Truss",  "△△△",
             "Pratt, Warren,\nHowe and\ncustom trusses"),
            ("blank", "Blank",  "  +  ",
             "Empty canvas —\nstart from\nscratch"),
        ]
        CARDS_3D = [
            ("frame", "Frame",  "╬ ╬",
             "3D portal frames,\nspace frames &\nmulti-storey"),
            ("truss", "Truss",  "△△△",
             "3D space trusses\nand lattice\nstructures"),
            ("blank", "Blank",  "  +  ",
             "Empty 3D canvas —\nstart from\nscratch"),
        ]

        self._tabs.addTab(
            _make_cards_page(CARDS_2D, self._choose_2d),
            "  2D  ",
        )
        self._tabs.addTab(
            _make_cards_page(CARDS_3D, self._choose_3d),
            "  3D  ",
        )

        root.addWidget(self._tabs)

        # ── Recent files ───────────────────────────────────────────────────────
        if recent_files:
            root.addWidget(self._hline())

            recent_lbl = QLabel("Recent files")
            recent_lbl.setStyleSheet("font-weight:bold; font-size:12px; color:#bbb;")
            root.addWidget(recent_lbl)

            self._recent_list = QListWidget()
            self._recent_list.setMaximumHeight(120)
            self._recent_list.setStyleSheet(
                "QListWidget { background:#1a1a22; border:1px solid #2a2a34; }"
                "QListWidget::item { padding:6px 10px; color:#ccc; }"
                "QListWidget::item:hover { background:#252530; color:#00ACC1; }"
                "QListWidget::item:selected { background:#252530; color:#00ACC1; }"
            )
            for path in recent_files:
                item = QListWidgetItem(f"  {Path(path).name}")
                item.setToolTip(path)
                item.setData(Qt.ItemDataRole.UserRole, path)
                self._recent_list.addItem(item)
            self._recent_list.itemActivated.connect(self._on_recent_activated)
            root.addWidget(self._recent_list)

        root.addWidget(self._hline())

        # ── Open existing ──────────────────────────────────────────────────────
        open_btn = QPushButton("Open existing file…")
        open_btn.setFixedHeight(34)
        open_btn.setStyleSheet(
            "QPushButton { background:transparent; border:1px solid #444;"
            "  color:#aaa; border-radius:4px; }"
            "QPushButton:hover { border-color:#00ACC1; color:#00ACC1; }"
        )
        open_btn.clicked.connect(self._on_open)
        root.addWidget(open_btn)

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _hline() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color:#2a2a34;")
        return line

    def _choose_2d(self, choice: str) -> None:
        self.is_3d = False
        self.choice = choice
        self.accept()

    def _choose_3d(self, choice: str) -> None:
        self.is_3d = True
        self.choice = choice
        self.accept()

    def _on_recent_activated(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        self.choice = f"file:{path}"
        self.accept()

    def _on_open(self) -> None:
        self.choice = "open"
        self.accept()
