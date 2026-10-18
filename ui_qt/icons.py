"""Themed icons from the bundled SVG sets.

``icon("save")`` returns a QIcon drawn from ``assets/icons/lucide/save.svg`` (or from
``assets/icons/structlab/`` for StructLab's own engineering icons). The SVGs draw with
``currentColor``; it is replaced by the theme text colour for the normal state and a dimmed
colour for the disabled state, so the files stay unmodified (see THIRD_PARTY_NOTICES.md).
Icons are cached per name.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PyQt6.QtCore import QByteArray, QSize, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

from ui_qt.theme import CYAN, TEXT, TEXT_DIM

_ROOT = Path(__file__).parent / "assets" / "icons"
_SETS = ("structlab", "lucide")          # StructLab's own icons win on a name clash
_SIZES = (16, 20, 24, 32)


def icon_path(name: str) -> Path | None:
    """The SVG file for ``name``, or None if no bundled set has it."""
    for folder in _SETS:
        path = _ROOT / folder / f"{name}.svg"
        if path.is_file():
            return path
    return None


def _pixmap(svg: str, colour: str, size: int) -> QPixmap:
    renderer = QSvgRenderer(QByteArray(svg.replace("currentColor", colour).encode("utf-8")))
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    renderer.render(painter)
    painter.end()
    return pm


@lru_cache(maxsize=None)
def icon(name: str) -> QIcon:
    """Themed QIcon for ``name``; an empty QIcon if the name is unknown."""
    path = icon_path(name)
    if path is None:
        return QIcon()
    svg = path.read_text(encoding="utf-8")
    result = QIcon()
    for size in _SIZES:
        result.addPixmap(_pixmap(svg, TEXT, size), QIcon.Mode.Normal, QIcon.State.Off)
        result.addPixmap(_pixmap(svg, CYAN, size), QIcon.Mode.Normal, QIcon.State.On)
        result.addPixmap(_pixmap(svg, TEXT_DIM, size), QIcon.Mode.Disabled, QIcon.State.Off)
    return result


def icon_size(large: bool) -> QSize:
    return QSize(28, 28) if large else QSize(16, 16)
