"""Start page shown at launch: banner, new model / open, templates and recent models.

Layout (Blender-splash style, framed like the main window)::

    ┌ banner: wordmark, version, tagline over a faint lattice drawing ────────────┐
    ├ Start ───────────────┐ ┌ Recent models ─────────────────────────────────────┤
    │ New 3D model         │ │ [thumb] tower.slab   [thumb] bridge.slab   …       │
    │ New 2D model         │ │  folder · date        folder · date                │
    │ Open…                │ │                                                    │
    │ Templates (wizards)  │ │                                                    │
    └──────────────────────┘ └────────────────────────────────────────────────────┘
      Keyboard shortcuts · About                        validation note · licence

Recent-model thumbnails are wireframes drawn from each .slab when the page opens (default
isometric view for 3D models, elevation for 2D); nothing is written next to the files.

After ``exec()`` read ``choice``: "blank" (with ``start_mode`` "3D" or "2D"), "open",
"file:<path>", "wizard:beam|portal|truss|frame" or "help:shortcuts" / "help:about".
"""

from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import (
    QBrush, QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPen, QPixmap,
)
from PyQt6.QtWidgets import (
    QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from ui_qt import theme
from ui_qt.icons import icon
from ui_qt.version import VERSION_LABEL

Segment = tuple[tuple[float, float, float], tuple[float, float, float]]

THUMB = QSize(176, 112)
TEMPLATE_THUMB = QSize(112, 64)

# Template sketches (line segments, x right / y up, 2D) — what each wizard builds
_TEMPLATES: tuple[tuple[str, str, str, list[Segment]], ...] = (
    ("beam", "Continuous beam", "Spans, supports, UDL and a midspan point load",
     [((0, 0, 0), (9, 0, 0)), ((0, -0.5, 0), (0, 0, 0)), ((4.5, -0.5, 0), (4.5, 0, 0)),
      ((9, -0.5, 0), (9, 0, 0))]),
    ("portal", "Portal frame", "Single-bay portal, pinned or fixed bases",
     [((0, 0, 0), (0, 4, 0)), ((0, 4, 0), (8, 4, 0)), ((8, 4, 0), (8, 0, 0))]),
    ("truss", "Truss", "Pratt, Warren or Howe trusses",
     [((0, 0, 0), (10, 0, 0)), ((0, 0, 0), (0, 2, 0)), ((0, 2, 0), (10, 2, 0)),
      ((10, 2, 0), (10, 0, 0))]
     + [((x, 0, 0), (x, 2, 0)) for x in (2.5, 5, 7.5)]
     + [((x, 2, 0), (x + 2.5, 0, 0)) for x in (0, 2.5)]
     + [((x, 0, 0), (x + 2.5, 2, 0)) for x in (5, 7.5)]),
    ("frame", "Multi-storey frame", "Bays × storeys, rigid joints",
     [((x, 0, 0), (x, 9, 0)) for x in (0, 4, 8)]
     + [((0, y, 0), (8, y, 0)) for y in (3, 6, 9)]),
)


# ── wireframe thumbnails ──────────────────────────────────────────────────────

def model_segments(path: str) -> tuple[list[Segment], bool] | None:
    """Member segments of a .slab file and whether it is 3D; None if it cannot be read."""
    try:
        from ui_qt.io import load_model
        state = load_model(path)
    except Exception:
        return None
    nodes = {n.id: n for n in state.nodes}
    segs: list[Segment] = []
    for m in state.members:
        a, b = nodes.get(m.node_i), nodes.get(m.node_j)
        if a is not None and b is not None:
            segs.append(((a.x, a.y, a.z), (b.x, b.y, b.z)))
    return segs, state.analysis_mode == "3D"


def _project(p: tuple[float, float, float], is_3d: bool) -> tuple[float, float]:
    """Default SW isometric (az -45°, el 30°) for 3D; plain elevation for 2D. y down."""
    x, y, z = p
    if not is_3d:
        return x, -y
    az, el = math.radians(-45.0), math.radians(30.0)
    sx = x * math.cos(az) + y * math.sin(az)
    sy = (-x * math.sin(az) + y * math.cos(az)) * math.sin(el) - z * math.cos(el)
    return sx, sy


def render_wireframe(segs: list[Segment], size: QSize, is_3d: bool,
                     colour: str = "#aab6c4", background: bool = True) -> QPixmap:
    """Draw ``segs`` fitted into a pixmap of ``size`` (aspect kept, small margin)."""
    pm = QPixmap(size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    if background:
        grad = QLinearGradient(0, 0, 0, size.height())
        grad.setColorAt(0.0, QColor(theme.VIEWPORT_TOP))       # same as the canvas
        grad.setColorAt(1.0, QColor(theme.VIEWPORT_BOTTOM))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(grad))
        p.drawRoundedRect(QRectF(0, 0, size.width(), size.height()), 5, 5)
    pts = [(_project(a, is_3d), _project(b, is_3d)) for a, b in segs]
    if pts:
        xs = [c[0] for seg in pts for c in seg]
        ys = [c[1] for seg in pts for c in seg]
        w, h = max(xs) - min(xs), max(ys) - min(ys)
        pad = 10.0
        scale = min((size.width() - 2 * pad) / w if w > 1e-9 else 1e9,
                    (size.height() - 2 * pad) / h if h > 1e-9 else 1e9)
        if scale == 1e9:
            scale = 1.0
        ox = (size.width() - w * scale) / 2 - min(xs) * scale
        oy = (size.height() - h * scale) / 2 - min(ys) * scale
        pen = QPen(QColor(colour), 1.2 if len(segs) > 60 else 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        for (x1, y1), (x2, y2) in pts:
            p.drawLine(QPointF(ox + x1 * scale, oy + y1 * scale),
                       QPointF(ox + x2 * scale, oy + y2 * scale))
    p.end()
    return pm


# ── widgets ───────────────────────────────────────────────────────────────────

class _Banner(QWidget):
    """Wordmark over a gradient with a faint lattice tower and truss drawn in."""

    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(150)

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        grad = QLinearGradient(0, 0, w, h)
        grad.setColorAt(0.0, QColor(theme.DEEP_BLUE))           # blue → navy → panel
        grad.setColorAt(0.45, QColor(theme.NAVY))
        grad.setColorAt(1.0, QColor(theme.SURFACE))
        p.setPen(QPen(QColor(theme.FRAME_LINE), 1))
        p.setBrush(QBrush(grad))
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), theme.FRAME_RADIUS, theme.FRAME_RADIUS)

        p.setClipRect(QRectF(1, 1, w - 2, h - 2))
        line = QColor(theme.CYAN)
        line.setAlpha(70)
        p.setPen(QPen(line, 1.2))
        # Warren truss along the bottom
        y0, y1, step = h - 18.0, h - 52.0, 34.0
        x = w * 0.50
        p.drawLine(QPointF(x, y0), QPointF(w + 10, y0))
        p.drawLine(QPointF(x + step / 2, y1), QPointF(w + 10, y1))
        while x < w + step:
            p.drawLine(QPointF(x, y0), QPointF(x + step / 2, y1))
            p.drawLine(QPointF(x + step / 2, y1), QPointF(x + step, y0))
            x += step
        # Lattice mast on the right, tapering to the top
        cx, base, top = w - 120.0, h - 52.0, 10.0
        half_b, half_t, panels = 26.0, 7.0, 6
        line.setAlpha(110)
        p.setPen(QPen(line, 1.3))
        for i in range(panels):
            ya = base - (base - top) * i / panels
            yb = base - (base - top) * (i + 1) / panels
            ha = half_b + (half_t - half_b) * i / panels
            hb = half_b + (half_t - half_b) * (i + 1) / panels
            p.drawLine(QPointF(cx - ha, ya), QPointF(cx - hb, yb))
            p.drawLine(QPointF(cx + ha, ya), QPointF(cx + hb, yb))
            p.drawLine(QPointF(cx - ha, ya), QPointF(cx + hb, yb))
            p.drawLine(QPointF(cx + ha, ya), QPointF(cx - hb, yb))
            p.drawLine(QPointF(cx - hb, yb), QPointF(cx + hb, yb))
        arm_y = top + (base - top) * 0.25
        p.drawLine(QPointF(cx - 60, arm_y), QPointF(cx + 60, arm_y))
        p.setClipping(False)

        f = QFont(); f.setPointSize(30); f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("#ffffff"))
        p.drawText(QPointF(28, 66), "StructLab")
        f2 = QFont(); f2.setPointSize(10)
        p.setFont(f2)
        p.setPen(QColor(theme.CYAN))
        p.drawText(QPointF(32, 92), f"{VERSION_LABEL}   ·   2D and 3D structural analysis")
        p.setPen(QColor(theme.TEXT_DIM))
        p.drawText(QPointF(32, 114), "Beams · frames · trusses · space structures  —  "
                                     "Direct Stiffness Method")
        p.end()


class _Card(QFrame):
    """A clickable framed card: optional picture, title, subtitle."""

    clicked = pyqtSignal()

    def __init__(self, title: str, subtitle: str, picture: QPixmap | None = None,
                 icon_name: str = "", horizontal: bool = False, tip: str = "",
                 text_width: int = 0) -> None:
        super().__init__()
        self.setObjectName("start_card")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tip)
        lay = QHBoxLayout(self) if horizontal else QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(10 if horizontal else 6)
        if picture is not None:
            pic = QLabel()
            pic.setPixmap(picture)
            pic.setStyleSheet("background: transparent; border: none;")
            lay.addWidget(pic, 0, Qt.AlignmentFlag.AlignCenter if not horizontal
                          else Qt.AlignmentFlag.AlignVCenter)
        elif icon_name:
            ico = QLabel()
            ico.setPixmap(icon(icon_name, theme.CYAN).pixmap(QSize(22, 22)))
            ico.setStyleSheet("background: transparent; border: none;")
            lay.addWidget(ico, 0, Qt.AlignmentFlag.AlignVCenter)
        text = QVBoxLayout()
        text.setSpacing(1)
        if text_width:                  # fixed-width card: shorten long names with "…"
            bold = QFont(self.font()); bold.setBold(True)
            title = QFontMetrics(bold).elidedText(title, Qt.TextElideMode.ElideMiddle, text_width)
            subtitle = QFontMetrics(self.font()).elidedText(
                subtitle, Qt.TextElideMode.ElideRight, text_width)
        t = QLabel(title)
        t.setObjectName("start_card_title")
        s = QLabel(subtitle)
        s.setObjectName("start_card_sub")
        s.setWordWrap(not text_width)
        text.addWidget(t)
        if subtitle:
            text.addWidget(s)
        lay.addLayout(text, 1)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.pos()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


_STYLE = f"""
QDialog#start_page {{ background: {theme.FRAME_GAP}; }}
QFrame#start_box {{
    background: {theme.SURFACE}; border: 1px solid {theme.FRAME_LINE};
    border-radius: {theme.FRAME_RADIUS}px;
}}
QLabel#start_heading {{
    color: {theme.TEXT_DIM}; font-size: 10px; font-weight: bold; letter-spacing: 1px;
    background: transparent; border: none;
}}
QFrame#start_card {{
    background: {theme.SURFACE2}; border: 1px solid {theme.BORDER}; border-radius: 6px;
}}
QFrame#start_card:hover {{ border-color: {theme.CYAN}; background: #3b4350; }}
QLabel#start_card_title {{
    color: {theme.TEXT}; font-weight: bold; background: transparent; border: none;
}}
QLabel#start_card_sub {{
    color: {theme.TEXT_DIM}; font-size: 11px; background: transparent; border: none;
}}
QLabel#start_note {{ color: {theme.TEXT_DIM}; font-size: 11px; background: transparent; }}
QPushButton#start_link {{
    background: transparent; border: none; color: {theme.TEXT_DIM}; padding: 2px 6px;
}}
QPushButton#start_link:hover {{ color: {theme.CYAN}; }}
QScrollArea#start_scroll, QWidget#start_recent {{ background: transparent; border: none; }}
"""


class WelcomeDialog(QDialog):
    """The start page. See the module docstring for the ``choice`` values."""

    def __init__(self, parent=None, recent_files: list[str] | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("start_page")
        self.setWindowTitle("Welcome to StructLab")
        self.setModal(True)
        self.setStyleSheet(_STYLE)
        self.resize(1040, 660)
        self.choice: str = "blank"
        self.start_mode: str = "3D"
        self.recent_cards: list[_Card] = []
        self._build_ui(recent_files or [])

    # ── layout ────────────────────────────────────────────────────────────────

    def _build_ui(self, recent_files: list[str]) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 10)
        root.setSpacing(10)
        root.addWidget(_Banner())

        body = QHBoxLayout()
        body.setSpacing(10)
        body.addWidget(self._start_box(), 0)
        body.addWidget(self._recent_box(recent_files), 1)
        root.addLayout(body, 1)
        root.addLayout(self._footer())

    @staticmethod
    def _box() -> tuple[QFrame, QVBoxLayout]:
        box = QFrame()
        box.setObjectName("start_box")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(14, 12, 14, 14)
        lay.setSpacing(8)
        return box, lay

    @staticmethod
    def _heading(text: str) -> QLabel:
        lbl = QLabel(text.upper())
        lbl.setObjectName("start_heading")
        return lbl

    def _start_box(self) -> QFrame:
        box, lay = self._box()
        box.setFixedWidth(360)
        lay.addWidget(self._heading("Start"))
        for title, sub, ico, choice in (
            ("New 3D model", "Space frames, towers, 3D trusses (Z up)", "box", "blank:3D"),
            ("New 2D model", "Plane beams, frames and trusses (XY)", "file-plus", "blank:2D"),
            ("Open…", "Open a .slab model from disk", "folder-open", "open"),
        ):
            card = _Card(title, sub, icon_name=ico, horizontal=True)
            card.clicked.connect(lambda c=choice: self._choose(c))
            lay.addWidget(card)

        lay.addSpacing(6)
        lay.addWidget(self._heading("Templates"))
        grid = QGridLayout()
        grid.setSpacing(8)
        for i, (key, title, sub, segs) in enumerate(_TEMPLATES):
            pic = render_wireframe(segs, TEMPLATE_THUMB, False, theme.CYAN)
            card = _Card(title, "", picture=pic, tip=f"{sub} — opens the {title.lower()} wizard")
            card.clicked.connect(lambda k=key: self._choose(f"wizard:{k}"))
            grid.addWidget(card, i // 2, i % 2)
        lay.addLayout(grid)
        lay.addStretch(1)
        return box

    def _recent_box(self, recent_files: list[str]) -> QFrame:
        box, lay = self._box()
        lay.addWidget(self._heading("Recent models"))
        if not recent_files:
            empty = QLabel("Models you open or save will appear here.")
            empty.setObjectName("start_note")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(empty, 1)
            return box

        holder = QWidget()
        holder.setObjectName("start_recent")
        grid = QGridLayout(holder)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(10)
        for i, path in enumerate(recent_files):
            card = self._recent_card(path)
            card.clicked.connect(lambda p=path: self._choose(f"file:{p}"))
            grid.addWidget(card, i // 3, i % 3, Qt.AlignmentFlag.AlignTop)
            self.recent_cards.append(card)
        grid.setRowStretch(grid.rowCount(), 1)
        grid.setColumnStretch(3, 1)

        scroll = QScrollArea()
        scroll.setObjectName("start_scroll")
        scroll.setWidget(holder)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        lay.addWidget(scroll, 1)
        return box

    @staticmethod
    def _recent_card(path: str) -> _Card:
        p = Path(path)
        loaded = model_segments(path)
        if loaded is not None:
            segs, is_3d = loaded
            pic = render_wireframe(segs, THUMB, is_3d)
        else:
            pic = render_wireframe([], THUMB, True)
        try:
            when = datetime.fromtimestamp(p.stat().st_mtime).strftime("%d %b %Y")
        except OSError:
            when = ""
        folder = p.parent.name or str(p.parent)
        sub = f"{folder}  ·  {when}" if when else folder
        card = _Card(p.name, sub, picture=pic, tip=str(p), text_width=THUMB.width())
        card.setFixedWidth(THUMB.width() + 18)
        return card

    def _footer(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(4, 0, 4, 0)
        for text, choice in (("Keyboard shortcuts", "help:shortcuts"), ("About", "help:about")):
            btn = QPushButton(text)
            btn.setObjectName("start_link")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _c=False, ch=choice: self._choose(ch))
            row.addWidget(btn)
        row.addStretch(1)
        note = QLabel("Checked against OpenSeesPy and closed-form solutions (20 benchmark cases)"
                      "   ·   GPL v3   ·   © 2024–2026 INSTRA Analysis")
        note.setObjectName("start_note")
        row.addWidget(note)
        return row

    # ── choices ───────────────────────────────────────────────────────────────

    def _choose(self, choice: str) -> None:
        if choice.startswith("blank:"):
            self.start_mode = choice.split(":", 1)[1]
            choice = "blank"
        self.choice = choice
        self.accept()
