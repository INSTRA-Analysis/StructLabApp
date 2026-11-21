"""Application-wide colours, palette and Qt stylesheet for StructLab.

The frame is calm mid-grey (Blender-like, not near-black) with one cyan accent for the
active state.  Colour that carries meaning comes from the category colours below: each
command family tints its icons with one colour, so the interface reads by function.
Adjust the tokens here to retheme the whole app; ``apply_theme`` installs them.
"""

from __future__ import annotations

# ── Blue–cyan family: the interface and structure colours, navy → aqua ───────
NAVY      = "#0f2a3d"   # deep fills: checked buttons, start-page banner
DEEP_BLUE = "#1e4f8a"   # selected rows, active workspace, menu highlight
BLUE      = "#3d8bfd"   # secondary accent: selection, focus, links; BMD
SKY       = "#4fb3f6"   # beams on the canvas, highlights
CYAN      = "#00b4d8"   # primary accent — active state, primary action; deformed shape
AQUA      = "#4fd1c5"   # soft highlights; SFD

CYAN_DIM  = "#1e6a80"   # subordinate borders (group boxes, inner tabs pane)
CYAN_TINT = NAVY        # checked-button fill

# Neutrals: blue-grey (same lightness steps as plain grey, a few degrees toward blue)
BG        = "#22272e"   # deepest surface: inputs, tables, panes
SURFACE   = "#2a3039"   # panels and docks
SURFACE2  = "#343b46"   # headers, buttons, tabs
BORDER    = "#444d5a"
TEXT      = "#e1e6ee"
TEXT_DIM  = "#97a1b0"

# Primary actions and the active workspace: blue → cyan
GRADIENT_PRIMARY = f"qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {BLUE}, stop:1 {CYAN})"
GRADIENT_PRIMARY_HOVER = ("qlineargradient(x1:0, y1:0, x2:1, y2:0, "
                          f"stop:0 {SKY}, stop:1 #33c6e6)")
GRADIENT_ACTIVE = f"qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {DEEP_BLUE}, stop:1 #0e7a93)"

# ── Framed areas (VS Code-like): each region is a rounded box on a dark gutter ─
FRAME_GAP    = "#11151b"   # gutter between the boxes (window background)
FRAME_LINE   = "#5a6880"   # the box outline
FRAME_RADIUS = 6           # px, box corner radius

# ── Viewport background (vertical gradient, navy-tinted) ─────────────────────
VIEWPORT_TOP    = "#2f3b4a"
VIEWPORT_BOTTOM = "#1b2028"

# ── Category colours (icons, panel accents, canvas symbols) ──────────────────
GEOMETRY  = CYAN        # nodes, members, modelling tools
SUPPORT   = "#5cc96b"   # supports and restraints
LOAD      = "#f0a030"   # load cases, loads, combinations
RESULT    = "#a87ee8"   # analysis results and diagrams
DESIGN    = "#e8c840"   # design checks, utilisation

# ── Axis colours (grid, gizmo, local axes) — Blender convention ─────────────
AXIS_X    = "#e8505b"
AXIS_Y    = "#7ccc4a"
AXIS_Z    = "#4a90e8"


def apply_theme(app) -> None:
    """Install the Fusion style, a palette built from the tokens, and the stylesheet.

    Fusion honours the palette on every platform, so widgets the stylesheet does not name
    (dialogs, check boxes, list views) still take the theme greys instead of the OS ones.
    """
    from PyQt6.QtGui import QColor, QPalette

    app.setStyle("Fusion")
    pal = QPalette()
    role = QPalette.ColorRole
    for r, colour in (
        (role.Window, SURFACE), (role.WindowText, TEXT), (role.Base, BG),
        (role.AlternateBase, SURFACE), (role.ToolTipBase, SURFACE2), (role.ToolTipText, TEXT),
        (role.Text, TEXT), (role.Button, SURFACE2), (role.ButtonText, TEXT),
        (role.BrightText, "#ffffff"), (role.Highlight, DEEP_BLUE), (role.HighlightedText, "#ffffff"),
        (role.Link, BLUE), (role.PlaceholderText, TEXT_DIM), (role.Mid, BORDER),
        (role.Dark, BG), (role.Light, SURFACE2), (role.Shadow, "#0b0e12"),
    ):
        pal.setColor(r, QColor(colour))
    disabled = QPalette.ColorGroup.Disabled
    for r in (role.WindowText, role.Text, role.ButtonText):
        pal.setColor(disabled, r, QColor(TEXT_DIM))
    app.setPalette(pal)
    app.setStyleSheet(STYLESHEET)

# ── Stylesheet ────────────────────────────────────────────────────────────────

STYLESHEET = f"""

/* ═══════════════════════════════════════════════════════════
   RIGHT PANEL — south tabs  (Properties | Results)
   Heavy cyan pane border; indicator on the BOTTOM edge.
   ═══════════════════════════════════════════════════════════ */

QTabWidget#right_panel_tabs::pane {{
    border: 2px solid {CYAN};
    border-radius: 2px;
}}

QTabWidget#right_panel_tabs > QTabBar::tab {{
    background : {SURFACE2};
    color      : {TEXT_DIM};
    border     : 1px solid {BORDER};
    padding    : 5px 16px;
    min-width  : 80px;
}}

QTabWidget#right_panel_tabs > QTabBar::tab:selected {{
    background    : {BG};
    color         : {CYAN};
    border-bottom : 2px solid {CYAN};
    border-top    : 1px solid {BORDER};
}}

QTabWidget#right_panel_tabs > QTabBar::tab:hover:!selected {{
    color        : {TEXT};
    border-color : {CYAN_DIM};
}}


/* ═══════════════════════════════════════════════════════════
   RESULTS INNER TABS — north tabs  (Displacements / Reactions / Forces)
   Dimmer pane border; indicator on the TOP edge.
   ═══════════════════════════════════════════════════════════ */

QTabWidget#results_inner_tabs::pane {{
    border: 1px solid {CYAN_DIM};
    border-radius: 2px;
}}

QTabWidget#results_inner_tabs > QTabBar::tab {{
    background : {SURFACE2};
    color      : {TEXT_DIM};
    border     : 1px solid {BORDER};
    padding    : 4px 10px;
}}

QTabWidget#results_inner_tabs > QTabBar::tab:selected {{
    background : {BG};
    color      : {CYAN};
    border-top : 2px solid {CYAN};
}}

QTabWidget#results_inner_tabs > QTabBar::tab:hover:!selected {{
    color        : {TEXT};
    border-color : {CYAN_DIM};
}}


/* ═══════════════════════════════════════════════════════════
   GROUP BOXES — thin teal border, cyan title
   ═══════════════════════════════════════════════════════════ */

QGroupBox {{
    border        : 1px solid {CYAN_DIM};
    border-radius : 3px;
    margin-top    : 10px;
    padding-top   : 4px;
    font-weight   : bold;
    color         : {CYAN};
}}

QGroupBox::title {{
    subcontrol-origin   : margin;
    subcontrol-position : top left;
    left    : 8px;
    padding : 0 4px;
    color   : {CYAN};
}}


/* ═══════════════════════════════════════════════════════════
   BUTTONS — cyan border on hover / tint on checked
   ═══════════════════════════════════════════════════════════ */

QPushButton {{
    background    : {SURFACE2};
    color         : {TEXT};
    border        : 1px solid {BORDER};
    padding       : 4px 10px;
    border-radius : 2px;
}}

QPushButton:hover {{
    border-color : {CYAN};
    color        : {CYAN};
}}

QPushButton:checked {{
    background   : {CYAN_TINT};
    border       : 1px solid {CYAN};
    color        : {CYAN};
}}

QPushButton:pressed {{
    background : {CYAN_TINT};
}}


/* ═══════════════════════════════════════════════════════════
   TABLE HEADERS — cyan text on dark surface
   ═══════════════════════════════════════════════════════════ */

QHeaderView::section {{
    background  : {SURFACE2};
    border      : 1px solid {BORDER};
    color       : {CYAN};
    padding     : 3px 6px;
    font-weight : bold;
}}

QTableWidget {{
    gridline-color : {BORDER};
    border         : 1px solid {BORDER};
}}


/* ═══════════════════════════════════════════════════════════
   SCROLL BARS — slim, subtle teal handle
   ═══════════════════════════════════════════════════════════ */

QScrollBar:vertical {{
    background : {SURFACE};
    width      : 7px;
    margin     : 0;
}}
QScrollBar::handle:vertical {{
    background    : {BORDER};
    min-height    : 20px;
    border-radius : 3px;
}}
QScrollBar::handle:vertical:hover {{
    background : {CYAN_DIM};
}}

QScrollBar:horizontal {{
    background : {SURFACE};
    height     : 7px;
    margin     : 0;
}}
QScrollBar::handle:horizontal {{
    background    : {BORDER};
    min-width     : 20px;
    border-radius : 3px;
}}
QScrollBar::handle:horizontal:hover {{
    background : {CYAN_DIM};
}}

QScrollBar::add-line, QScrollBar::sub-line {{
    width: 0; height: 0;
}}


/* ═══════════════════════════════════════════════════════════
   DEPTH & BORDERS — docks, inputs, tables, tooltips, status bar
   Panels sit one step lighter than the canvas; every container
   has a 1px border so regions read as distinct surfaces.
   ═══════════════════════════════════════════════════════════ */

/* ═══════════════════════════════════════════════════════════
   FRAMED AREAS — every region (ribbon, canvas, each dock) is a
   rounded box with a light outline on a dark gutter, like VS Code.
   Dock boxes are two halves: the title bar (top corners) and
   QFrame#panel_body (bottom corners), see main_window.py.
   ═══════════════════════════════════════════════════════════ */

QMainWindow {{
    background : {FRAME_GAP};
}}
QMainWindow::separator {{
    background : {FRAME_GAP};
    width  : 6px;
    height : 6px;
}}
QMainWindow::separator:hover {{
    background : {CYAN_DIM};
}}

QWidget#dock_title {{
    background : {SURFACE2};
    border     : 1px solid {FRAME_LINE};
    border-bottom : 1px solid {BORDER};
    border-top-left-radius  : {FRAME_RADIUS}px;
    border-top-right-radius : {FRAME_RADIUS}px;
}}
QFrame#panel_body {{
    background : {SURFACE};
    border     : 1px solid {FRAME_LINE};
    border-top : none;
    border-bottom-left-radius  : {FRAME_RADIUS}px;
    border-bottom-right-radius : {FRAME_RADIUS}px;
}}
QFrame#canvas_frame {{
    background    : {BG};
    border        : 1px solid {FRAME_LINE};
    border-radius : {FRAME_RADIUS}px;
}}

/* Floating tool strips inside the canvas (viewport_overlay.py) */
QFrame#float_strip {{
    background    : rgba(42, 48, 57, 235);       /* SURFACE, slightly see-through */
    border        : 1px solid {FRAME_LINE};
    border-radius : 8px;
}}
QFrame#float_divider {{
    background : {BORDER};
    border     : none;
    margin     : 2px 3px;
}}
QToolButton#float_btn {{
    background    : transparent;
    color         : {TEXT};
    border        : 1px solid transparent;
    border-radius : 5px;
    padding       : 0 6px;
}}
QToolButton#float_btn:hover {{
    background   : {SURFACE2};
    border-color : {BORDER};
}}
QToolButton#float_btn:checked {{
    background   : {CYAN_TINT};
    border-color : {CYAN};
    color        : {CYAN};
}}
QToolButton#float_btn:disabled {{
    color : {TEXT_DIM};
}}

/* Dialogs styled with dialog_style.apply_dialog_style (wizards, combinations…) */
QDialog#themed_dialog {{
    background : {SURFACE};
}}
QDialog#themed_dialog QGroupBox {{
    background    : {BG};
    border        : 1px solid {FRAME_LINE};
    border-radius : {FRAME_RADIUS}px;
    margin-top    : 16px;
    padding       : 12px 10px 8px 10px;
    font-weight   : bold;
    color         : {TEXT_DIM};
}}
QDialog#themed_dialog QGroupBox::title {{
    subcontrol-origin   : margin;
    subcontrol-position : top left;
    left    : 10px;
    padding : 0 4px;
    color   : {TEXT_DIM};
}}
QDialog#themed_dialog QGroupBox QLabel,
QDialog#themed_dialog QGroupBox QRadioButton,
QDialog#themed_dialog QGroupBox QCheckBox {{
    font-weight : normal;
    color       : {TEXT};
}}
QFrame#dialog_header {{
    background    : {SURFACE2};
    border        : 1px solid {FRAME_LINE};
    border-radius : {FRAME_RADIUS}px;
}}
QLabel#dialog_header_title {{
    color : {TEXT}; font-size: 13pt; font-weight: bold; background: transparent; border: none;
}}
QLabel#dialog_header_sub {{
    color : {TEXT_DIM}; background: transparent; border: none;
}}
QPushButton[role="primary"] {{
    background   : {GRADIENT_PRIMARY};
    border       : 1px solid {SKY};
    color        : #ffffff;
    font-weight  : bold;
    padding      : 5px 18px;
}}
QPushButton[role="primary"]:hover {{
    background : {GRADIENT_PRIMARY_HOVER};
    color      : #ffffff;
}}
QPushButton[role="primary"]:pressed {{
    background : {DEEP_BLUE};
}}
QPushButton[role="primary"]:disabled {{
    background   : {SURFACE2};
    border-color : {BORDER};
    color        : {TEXT_DIM};
}}

/* Tabs of docks stacked in one place (Results | Groups) */
QMainWindow > QTabBar {{
    background : {FRAME_GAP};
}}
QMainWindow > QTabBar::tab {{
    background    : {FRAME_GAP};
    color         : {TEXT_DIM};
    border        : 1px solid {BORDER};
    border-radius : 4px;
    padding       : 3px 14px;
    margin        : 3px 2px;
}}
QMainWindow > QTabBar::tab:selected {{
    color        : {TEXT};
    border-color : {FRAME_LINE};
    background   : {SURFACE2};
}}
QMainWindow > QTabBar::tab:hover:!selected {{
    color : {TEXT};
}}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background    : {BG};
    border        : 1px solid {BORDER};
    border-radius : 3px;
    padding       : 2px 5px;
    selection-background-color : {DEEP_BLUE};
}}
QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover {{
    border-color : {CYAN_DIM};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border-color : {BLUE};
}}

/* Radio buttons and check boxes: outlined, filled with the accent when on
   (the Fusion defaults are dark-on-dark on this palette and hard to see) */
QRadioButton::indicator, QCheckBox::indicator {{
    width      : 12px;
    height     : 12px;
    border     : 1px solid {TEXT_DIM};
    background : {BG};
}}
QRadioButton::indicator {{
    border-radius : 7px;
}}
QCheckBox::indicator {{
    border-radius : 3px;
}}
QRadioButton::indicator:hover, QCheckBox::indicator:hover {{
    border-color : {CYAN};
}}
QRadioButton::indicator:checked {{
    background : qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
                                 stop:0 {CYAN}, stop:0.45 {CYAN}, stop:0.55 {BG}, stop:1 {BG});
    border-color : {CYAN};
}}
QCheckBox::indicator:checked {{
    background   : {CYAN};
    border-color : {CYAN};
}}
QRadioButton::indicator:disabled, QCheckBox::indicator:disabled {{
    border-color : {BORDER};
    background   : {SURFACE};
}}

QTableView {{
    alternate-background-color : {SURFACE};
    selection-background-color : {DEEP_BLUE};
    selection-color            : #ffffff;
}}

QToolTip {{
    background    : {SURFACE2};
    color         : {TEXT};
    border        : 1px solid {CYAN_DIM};
    padding       : 3px 6px;
}}

QStatusBar {{
    background : {FRAME_GAP};
    color      : {TEXT_DIM};
}}
QStatusBar::item {{
    border : none;
}}

QMenu {{
    background : {SURFACE2};
    border     : 1px solid {BORDER};
    padding    : 3px;
}}
QMenu::item {{
    padding : 4px 22px 4px 18px;
}}
QMenu::item:selected {{
    background : {DEEP_BLUE};
    color      : #ffffff;
}}
QMenu::separator {{
    height : 1px;
    background : {BORDER};
    margin : 3px 6px;
}}

"""
