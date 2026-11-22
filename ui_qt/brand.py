"""The instrahub mark: one place to draw it, at any size, and to build the application icon.

The mark itself is ``assets/instrahub_mark.svg`` (hub and modules). ``app_icon`` puts it on a
rounded dark tile so it stays visible on a light or a dark taskbar; the same artwork is frozen
into ``assets/structlab.ico`` for the packaged .exe (``write_ico`` rebuilds it).
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

ASSETS = Path(__file__).parent / "assets"
MARK_SVG = ASSETS / "instrahub_mark.svg"
ICO_PATH = ASSETS / "structlab.ico"
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)
TILE = QColor("#22272e")

_renderer: QSvgRenderer | None = None


def _mark_renderer() -> QSvgRenderer:
    global _renderer
    if _renderer is None:
        _renderer = QSvgRenderer(str(MARK_SVG))
    return _renderer


def paint_mark(painter: QPainter, rect: QRectF) -> None:
    """Draw the mark into ``rect`` (square artwork, centred if ``rect`` is not square)."""
    side = min(rect.width(), rect.height())
    square = QRectF(rect.center().x() - side / 2, rect.center().y() - side / 2, side, side)
    _mark_renderer().render(painter, square)


def mark_pixmap(size: int, ratio: float = 1.0) -> QPixmap:
    """The mark alone on a transparent ground, ``size`` logical pixels square."""
    px = max(1, round(size * ratio))
    image = QImage(px, px, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    paint_mark(painter, QRectF(0, 0, px, px))
    painter.end()
    pixmap = QPixmap.fromImage(image)
    pixmap.setDevicePixelRatio(ratio)
    return pixmap


def icon_image(size: int) -> QImage:
    """The application icon at ``size`` px: the mark on a rounded dark tile."""
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(TILE)
    painter.drawRoundedRect(QRectF(0, 0, size, size), size * 0.2, size * 0.2)
    inset = size * 0.06
    paint_mark(painter, QRectF(inset, inset, size - 2 * inset, size - 2 * inset))
    painter.end()
    return image


def app_icon() -> QIcon:
    """Window and taskbar icon, with a hand-rendered image at every standard size."""
    result = QIcon()
    for size in ICON_SIZES:
        result.addPixmap(QPixmap.fromImage(icon_image(size)))
    return result


def write_ico(path: Path = ICO_PATH) -> None:
    """Rebuild the .ico used by PyInstaller (needs Pillow, a build-time tool only)."""
    from io import BytesIO

    from PIL import Image

    frames = [Image.open(BytesIO(_png_bytes(icon_image(s)))) for s in ICON_SIZES]
    frames[-1].save(path, format="ICO", sizes=[(s, s) for s in ICON_SIZES],
                    append_images=frames[:-1])


def _png_bytes(image: QImage) -> bytes:
    from PyQt6.QtCore import QBuffer, QIODevice
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())
