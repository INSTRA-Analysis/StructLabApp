"""Start page shown at launch: one page, one tab per module.

Layout (Blender-splash style, framed like the main window)::

    ┌ banner: wordmark, version, tagline over the rotating art ──────────────────┐
    ├ [Static Analysis] [Dynamic Analysis · soon] [Plates & Shells · soon]  tabs ┤
    ├ Static Analysis tab:                                                       ┤
    │  Start / Templates (wizards)      │ Recent models (thumbnails)              │
    │ a coming-soon module's tab: what it will do, planned scope, what the model │
    │  will need, and the way to Static Analysis meanwhile (ui_qt/modules.py)     │
    └────────────────────────────────────────────────────────────────────────────┘
      Keyboard shortcuts · About                        validation note · licence

The caller opens it on ``start_module`` (the tab used last time) and saves
``current_page`` afterwards.

Recent-model thumbnails are wireframes drawn from each .slab when the page opens (default
isometric view for 3D models, elevation for 2D); nothing is written next to the files.

After ``exec()`` read ``choice``: "blank" (with ``start_mode`` "3D", or "plane" for a plane
frame in the XZ plane: StructLab no longer creates 2D models), "open",
"file:<path>", "wizard:beam|portal|truss|frame" or "help:shortcuts" / "help:about".
"""

from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QBrush, QColor, QFont, QFontMetrics, QImage, QLinearGradient, QPainter, QPen, QPixmap,
)
from PyQt6.QtWidgets import (
    QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from ui_qt import theme
from ui_qt.icons import icon, icon_pixmap
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
    """Wordmark over a blue gradient, with the banner art from ui_qt/banner_art.py.

    The art (the frame element "inside and out"; ``AssemblyArt`` is the kept alternative)
    draws itself in once, the first time the banner is shown, then rests complete; clicking
    the banner replays it.
    """

    ART_WIDTH = 480          # px from the right edge reserved for the art
    STEP_MS = 50             # one draw-in step

    def __init__(self, art=None, lines: tuple[str, str, str] | None = None) -> None:
        super().__init__()
        self.lines = lines or ("StructLab", f"{VERSION_LABEL}   ·   Plane and space frame analysis",
                               "Beams · frames · trusses · towers  —  Direct Stiffness Method")
        self.setFixedHeight(150)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if art is None:
            from ui_qt.banner_art import ElementArt
            art = ElementArt()
        self.art = art
        self.setToolTip(self.art.tooltip)
        self._steps = self.art.steps
        self.count = self._steps              # draw-in progress (complete at rest)
        self._played = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._step)

    # ── animation ─────────────────────────────────────────────────────────────

    def play(self) -> None:
        """Replay the assembly from an empty matrix."""
        self.count = 0
        self._timer.start(self.STEP_MS)
        self.update()

    def _step(self) -> None:
        self.count += 1
        if self.count >= self._steps:
            self.count = self._steps
            self._timer.stop()
        self.update()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if not self._played:
            self._played = True
            self.play()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.play()
        super().mousePressEvent(event)

    # ── painting ──────────────────────────────────────────────────────────────

    def _art_layer(self, w: int, h: int) -> QImage:
        """The art on a transparent layer, faded in from the left so it never meets the text."""
        dpr = self.devicePixelRatioF()
        img = QImage(int(w * dpr), int(h * dpr), QImage.Format.Format_ARGB32_Premultiplied)
        img.setDevicePixelRatio(dpr)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        origin_x = w - self.ART_WIDTH
        self.art.paint(p, QPointF(origin_x, 0), self.count)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        fade_from, fade_to = self.art.fade
        mask = QLinearGradient(origin_x + fade_from, 0, origin_x + fade_to, 0)
        mask.setColorAt(0.0, QColor(0, 0, 0, 0))
        mask.setColorAt(1.0, QColor(0, 0, 0, 255))
        p.fillRect(QRectF(0, 0, w, h), QBrush(mask))
        p.end()
        return img

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
        p.drawImage(QPointF(0, 0), self._art_layer(w, h))
        p.setClipping(False)

        # Theme label, bottom-right ("FINITE ELEMENTS", "DYNAMICS", …)
        theme_name = getattr(self.art, "theme", "")
        if theme_name:
            lf = QFont(); lf.setPointSizeF(7.0); lf.setBold(True)
            lf.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.4)
            p.setFont(lf)
            label = QColor(theme.TEXT_DIM); label.setAlpha(170)
            p.setPen(label)
            p.drawText(QRectF(w - 260, h - 20, 246, 14),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, theme_name.upper())

        f = QFont(); f.setPointSize(30); f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("#ffffff"))
        title, line1, line2 = self.lines
        p.drawText(QPointF(28, 66), title)
        f2 = QFont(); f2.setPointSize(10)
        p.setFont(f2)
        p.setPen(QColor(theme.CYAN))
        p.drawText(QPointF(32, 92), line1)
        p.setPen(QColor(theme.TEXT_DIM))
        p.drawText(QPointF(32, 114), line2)
        p.end()


class _ModuleTab(QFrame):
    """One module in the start page's tab strip: its icon in its colour, its name, and a
    'soon' badge while it is coming soon. The selected tab is underlined in the module's
    colour; a coming-soon tab keeps a dashed outline so it never reads as broken."""

    clicked = pyqtSignal()

    def __init__(self, spec) -> None:
        super().__init__()
        self.spec = spec
        self.soon = spec.status == "coming_soon"
        self.setObjectName("start_tab_soon" if self.soon else "start_tab")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(spec.tooltip if self.soon else spec.summary)
        self.setMinimumHeight(46)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 14, 6)
        lay.setSpacing(9)
        ico = QLabel()
        ico.setPixmap(icon_pixmap(spec.icon, spec.hue, 28, self.devicePixelRatioF()))
        ico.setStyleSheet("background: transparent; border: none;")
        lay.addWidget(ico)
        name = QLabel(spec.title)
        name.setObjectName("start_tab_text")
        lay.addWidget(name)
        if self.soon:
            badge = QLabel("soon")
            badge.setObjectName("start_badge_soon")
            lay.addWidget(badge, 0, Qt.AlignmentFlag.AlignVCenter)   # a pill, not the tab's height
        self.set_selected(False)

    def set_selected(self, on: bool) -> None:
        self.selected = on
        edge = f"border-bottom: 3px solid {self.spec.hue};" if on else ""
        fill = "#3a404c" if on else "transparent"
        line = "dashed" if self.soon else "solid"
        outline = theme.FRAME_LINE if self.soon else ("transparent" if not on else theme.BORDER)
        self.setStyleSheet(
            f"QFrame#{self.objectName()} {{ background: {fill}; border: 1px {line} {outline};"
            f" border-radius: 5px; {edge} }}"
            f"QFrame#{self.objectName()}:hover {{ background: #353c48; }}")

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.pos()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


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
QLabel#start_badge_included {{
    background: #1d3b2a; color: #8be29a; border-radius: 9px; padding: 1px 8px;
    font-size: 11px; font-weight: bold;
}}
QLabel#start_badge_soon {{
    background: #3a2f52; color: #cdb6f5; border-radius: 9px; padding: 1px 8px;
    font-size: 11px; font-weight: bold;
}}
QLabel#start_tab_text {{ color: {theme.TEXT}; font-size: 14px; font-weight: bold;
    background: transparent; border: none; }}
QFrame#start_tabs {{
    background: {theme.SURFACE}; border: 1px solid {theme.FRAME_LINE};
    border-radius: {theme.FRAME_RADIUS}px;
}}
QLabel#start_soon_title {{
    color: {theme.TEXT}; font-size: 20px; font-weight: bold; background: transparent; border: none;
}}
QLabel#start_body {{ color: {theme.TEXT}; font-size: 15px; background: transparent; }}
QLabel#start_scope_item {{
    background: {theme.SURFACE2}; border: 1px solid {theme.BORDER}; border-radius: 6px;
    color: {theme.TEXT}; padding: 9px 12px;
}}
QLabel#start_requires {{
    background: {theme.BG}; color: {theme.TEXT_DIM}; border-radius: 5px; padding: 9px 12px;
}}
"""


class WelcomeDialog(QDialog):
    """The start page. See the module docstring for the ``choice`` values."""

    def __init__(self, parent=None, recent_files: list[str] | None = None,
                 banner_art=None, start_module: str | None = None) -> None:
        """``banner_art``: the art to show (ui_qt/banner_themes.next_banner); the frame
        element when None. Choosing it is left to the caller so that opening this dialog
        never changes the saved rotation by itself.

        ``start_module``: the tab to open on ("static" or a registry key) — the caller passes
        the tab the user was on last time; Static Analysis when None or unknown."""
        super().__init__(parent)
        self._banner_art = banner_art
        self.setObjectName("start_page")
        self.setWindowTitle("Welcome to StructLab")
        self.setModal(True)
        self.setStyleSheet(_STYLE)
        self.resize(1080, 720)
        self.choice: str = "blank"
        self.start_mode: str = "3D"
        self.recent_cards: list[_Card] = []
        self.module_tabs: list[_ModuleTab] = []
        self.pages: dict[str, QWidget] = {}
        self._build_ui(recent_files or [])
        from ui_qt.modules import STATIC_ANALYSIS
        self.show_page(start_module if start_module in self.pages else STATIC_ANALYSIS.key)

    # ── tabs ──────────────────────────────────────────────────────────────────

    @property
    def current_page(self) -> str:
        """Key of the tab on show: "static" or a module key."""
        widget = self._stack.currentWidget()
        return next(k for k, w in self.pages.items() if w is widget)

    def show_page(self, key: str) -> None:
        self._stack.setCurrentWidget(self.pages[key])
        for tab in self.module_tabs:
            tab.set_selected(tab.spec.key == key)

    # ── layout ────────────────────────────────────────────────────────────────

    def _build_ui(self, recent_files: list[str]) -> None:
        from PyQt6.QtWidgets import QStackedWidget
        from ui_qt.modules import MODULES, STATIC_ANALYSIS
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 10)
        root.setSpacing(10)
        self.banner = _Banner(self._banner_art)
        root.addWidget(self.banner)
        root.addWidget(self._tab_strip((STATIC_ANALYSIS,) + MODULES))
        self._stack = QStackedWidget()
        self._add_page(STATIC_ANALYSIS.key, self._static_page(recent_files))
        for spec in MODULES:
            self._add_page(spec.key, self._module_page(spec))
        root.addWidget(self._stack, 1)
        root.addLayout(self._footer())

    def _tab_strip(self, specs) -> QFrame:
        """One tab per module (Static Analysis first, then the registry), framed like the boxes."""
        strip = QFrame()
        strip.setObjectName("start_tabs")
        row = QHBoxLayout(strip)
        row.setContentsMargins(6, 5, 6, 5)
        row.setSpacing(6)
        for spec in specs:
            tab = _ModuleTab(spec)
            tab.clicked.connect(lambda k=spec.key: self.show_page(k))
            row.addWidget(tab)
            self.module_tabs.append(tab)
        row.addStretch(1)
        return strip

    def _add_page(self, key: str, widget: QWidget) -> None:
        self.pages[key] = widget
        self._stack.addWidget(widget)

    @staticmethod
    def _page() -> tuple[QWidget, QHBoxLayout]:
        page = QWidget()
        lay = QHBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        return page, lay

    def _static_page(self, recent_files: list[str]) -> QWidget:
        """Static Analysis: new model / open, templates, recent models."""
        page, lay = self._page()
        lay.addWidget(self._start_box(), 0)
        lay.addWidget(self._recent_box(recent_files), 1)
        return page

    def _module_page(self, spec) -> QWidget:
        """A module's tab. While it is coming soon: what it will do, its planned scope, what
        the model will need, and the way to Static Analysis meanwhile."""
        from ui_qt.modules import STATIC_ANALYSIS
        page, lay = self._page()

        main, inner = self._box()
        inner.setContentsMargins(20, 16, 20, 16)
        inner.setSpacing(10)
        head = QHBoxLayout()
        head.setSpacing(12)
        ico = QLabel()
        ico.setPixmap(icon_pixmap(spec.icon, spec.hue, 40, self.devicePixelRatioF()))
        ico.setStyleSheet("background: transparent; border: none;")
        head.addWidget(ico)
        title = QLabel(spec.title)
        title.setObjectName("start_soon_title")
        head.addWidget(title)
        if spec.status_label:
            badge = QLabel(spec.status_label)
            badge.setObjectName("start_badge_soon")
            head.addWidget(badge, 0, Qt.AlignmentFlag.AlignVCenter)
        head.addStretch(1)
        inner.addLayout(head)
        summary = QLabel(spec.summary)
        summary.setObjectName("start_body")
        summary.setWordWrap(True)
        inner.addWidget(summary)
        inner.addSpacing(4)
        inner.addWidget(self._heading("Planned scope" if spec.status == "coming_soon" else "Scope"))
        grid = QGridLayout()
        grid.setSpacing(8)
        for i, line in enumerate(spec.scope):
            item = QLabel(f"›  {line}")
            item.setObjectName("start_scope_item")
            item.setWordWrap(True)
            grid.addWidget(item, i // 2, i % 2)
        inner.addLayout(grid)
        if spec.requires:
            needs = QLabel(f"<b>Your model will need:</b> {', '.join(spec.requires)}")
            needs.setObjectName("start_requires")
            needs.setTextFormat(Qt.TextFormat.RichText)
            inner.addWidget(needs)
        inner.addStretch(1)
        lay.addWidget(main, 1)

        side, s = self._box()
        side.setFixedWidth(330)
        s.addWidget(self._heading("Meanwhile"))
        note = QLabel("Static Analysis covers plane and space frames, trusses and towers today "
                      "— and the models you build there will open in this module when it arrives.")
        note.setObjectName("start_card_sub")
        note.setWordWrap(True)
        s.addWidget(note)
        to_static = _Card(f"Open {STATIC_ANALYSIS.title}", "New model, templates, recent models",
                          picture=icon_pixmap(STATIC_ANALYSIS.icon, STATIC_ANALYSIS.hue, 32,
                                              self.devicePixelRatioF()), horizontal=True)
        to_static.clicked.connect(lambda: self.show_page(STATIC_ANALYSIS.key))
        s.addWidget(to_static)
        s.addStretch(1)
        lay.addWidget(side, 0)
        return page

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
            ("New plane frame", "Beams, portals and trusses in the XZ plane", "layers", "blank:plane"),
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
