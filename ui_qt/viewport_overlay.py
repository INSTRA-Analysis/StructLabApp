"""Floating tool strips over the canvas: tools (left), view (top centre), results (right).

Each strip is a rounded, semi-transparent panel of icon buttons that floats inside the
canvas box, like the tool shelves of Blender. The buttons are bound to the window's
shared QActions (ui_qt/commands.py and the view/plane actions in main_window.py) with
``setDefaultAction``, so a strip button, its ribbon button and its menu entry always share
the same checked / enabled state and shortcut; no command logic lives here.

The strips are children of the QGraphicsView itself, not of its viewport, so scrolling
the scene never moves them. They are re-placed whenever the view is resized.
"""

from __future__ import annotations

from typing import Callable

from PyQt6 import sip
from PyQt6.QtCore import QEvent, QObject, QSize, Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QBoxLayout, QFrame, QToolButton, QWidget

# Command keys per strip; "|" starts a new group (a thin divider)
LEFT_KEYS = ("mode_select", "mode_node", "mode_member", "mode_measure", "|",
             "duplicate", "delete", "|", "zoom_fit")
TOP_KEYS = ("view_top", "view_front", "view_left", "view_right", "view_sw", "|",
            "plane_xy", "plane_xz", "plane_yz", "plane_free", "plane_offset", "|",
            "local_axes", "show_loads", "section_cut")
RIGHT_KEYS = ("ov_def", "ov_bmd", "ov_sfd", "ov_afd", "ov_labels", "|",
              "force_colours", "util_colours", "|", "animate")

EDGE_GAP = 10          # px between a strip and the canvas edge
BUTTON = 30            # px, square icon button
ICON = QSize(18, 18)
RIGHT_STRIP_TOP = 132  # px, the right strip starts below the axis gizmo
GIZMO_SPACE = 124      # px kept free at the top right for the axis gizmo


class FloatingStrip(QFrame):
    """A rounded panel of buttons laid out in a row or a column."""

    def __init__(self, parent: QWidget, vertical: bool, name: str) -> None:
        super().__init__(parent)
        self.setObjectName("float_strip")
        self.setAccessibleName(name)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        direction = (QBoxLayout.Direction.TopToBottom if vertical
                     else QBoxLayout.Direction.LeftToRight)
        self._layout = QBoxLayout(direction, self)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.setSpacing(2)
        self._vertical = vertical
        self.buttons: list[QToolButton] = []
        self.groups: list[list[QWidget]] = [[]]   # widgets per group, a group's divider first

    def add_action(self, action: QAction) -> QToolButton:
        """A button bound to ``action``: icon-only when it has an icon, else its short text."""
        btn = QToolButton(self)
        btn.setObjectName("float_btn")
        btn.setDefaultAction(action)
        btn.setAutoRaise(True)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)    # keyboard shortcuts stay on the canvas
        btn.setIconSize(ICON)
        if action.icon().isNull():
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            btn.setMinimumSize(BUTTON, BUTTON)
            btn.setFixedHeight(BUTTON)
        else:
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            btn.setFixedSize(BUTTON, BUTTON)
        if action.menu() is not None:
            btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._layout.addWidget(btn)
        self.buttons.append(btn)
        self.groups[-1].append(btn)
        return btn

    def add_divider(self) -> None:
        """End the current group: a thin line, then the next group's buttons."""
        line = QFrame(self)
        line.setObjectName("float_divider")
        if self._vertical:
            line.setFixedHeight(1)
        else:
            line.setFixedWidth(1)
        self._layout.addWidget(line)
        self.groups.append([line])

    def fresh_size(self) -> QSize:
        """Size hint measured now (the layout caches it until the next event loop pass,
        which is stale right after buttons were shown or hidden)."""
        self._layout.invalidate()
        return self._layout.sizeHint()

    def set_group_visible(self, index: int, visible: bool) -> None:
        """Show or hide one group; the first group's following divider goes with it."""
        widgets = list(self.groups[index])
        if index == 0 and len(self.groups) > 1:
            widgets.append(self.groups[1][0])
        for w in widgets:
            w.setVisible(visible)


class ViewportStrips(QObject):
    """Builds the three strips on ``view`` and keeps them placed inside its viewport."""

    def __init__(self, view, actions: dict[str, QAction], is_3d: Callable[[], bool]) -> None:
        super().__init__(view)
        self._view = view
        self._is_3d = is_3d
        self.left = self._build(LEFT_KEYS, actions, vertical=True, name="Tools")
        self.top = self._build(TOP_KEYS, actions, vertical=False, name="View")
        self.right = self._build(RIGHT_KEYS, actions, vertical=True, name="Results")
        # The viewport is resized after the view's own Resize event has been filtered,
        # so its Resize event is the one that carries the final geometry.
        self._viewport = view.viewport()
        self._viewport.installEventFilter(self)
        self.refresh()

    def _build(self, keys: tuple[str, ...], actions: dict[str, QAction],
               vertical: bool, name: str) -> FloatingStrip:
        strip = FloatingStrip(self._view, vertical, name)
        pending_divider = False
        for key in keys:
            if key == "|":
                pending_divider = bool(strip.buttons)
                continue
            action = actions.get(key)
            if action is None:          # a command this build does not have
                continue
            if pending_divider:
                strip.add_divider()
                pending_divider = False
            strip.add_action(action)
        strip.adjustSize()
        strip.raise_()
        return strip

    def refresh(self) -> None:
        """Re-evaluate the view strip (3D only) and re-place everything."""
        if not self._alive():
            return
        self.reposition()

    def _alive(self) -> bool:
        """False while Qt tears the window down: an exception raised from a Qt callback
        at that point aborts the whole process, so every entry point checks first."""
        return not any(sip.isdeleted(o) for o in
                       (self, self._view, self._viewport, self.left, self.top, self.right))

    def _fit_top(self, free_width: int) -> bool:
        """Fit the view strip into ``free_width``: drop the view presets (the gizmo does
        the same job) before hiding the strip. True if it is shown."""
        if not self._is_3d():
            self.top.hide()
            return False
        self.top.set_group_visible(0, True)
        if self.top.fresh_size().width() > free_width:
            self.top.set_group_visible(0, False)
        size = self.top.fresh_size()
        fits = size.width() <= free_width
        self.top.setVisible(fits)
        if fits:
            self.top.resize(size)
        return fits

    def reposition(self) -> None:
        vp = self._view.viewport().geometry()
        self.left.resize(self.left.fresh_size())
        self.right.resize(self.right.fresh_size())
        self.left.move(vp.left() + EDGE_GAP, vp.top() + EDGE_GAP)
        self.right.move(vp.right() - EDGE_GAP - self.right.width() + 1,
                        vp.top() + RIGHT_STRIP_TOP)
        # The view strip is centred in the gap between the tools strip and the gizmo
        gap_left = self.left.geometry().right() + 1 + EDGE_GAP
        gap_right = vp.right() + 1 - GIZMO_SPACE
        if self._fit_top(gap_right - gap_left):
            x =gap_left + (gap_right - gap_left - self.top.width()) // 2
            self.top.move(x, vp.top() + EDGE_GAP)
        for strip in (self.left, self.top, self.right):
            strip.raise_()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if (event.type() in (QEvent.Type.Resize, QEvent.Type.Show)
                and obj is self._viewport and self._alive()):
            self.reposition()
        return False
