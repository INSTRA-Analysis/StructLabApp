"""Application-wide Qt stylesheet for StructLab.

Single cyan accent on a dark base.  Canvas and scene content are untouched.
Adjust CYAN / CYAN_DIM here to retheme the whole app.
"""

CYAN      = "#00b4d8"   # primary accent — borders, active tabs, headers
CYAN_DIM  = "#1e5f74"   # subordinate borders (group boxes, inner tabs pane)
CYAN_TINT = "#003d4f"   # checked-button fill

SURFACE   = "#252526"
SURFACE2  = "#2d2d2d"
BORDER    = "#3c3c3c"
TEXT      = "#d4d4d4"
TEXT_DIM  = "#888888"
BG        = "#1e1e1e"

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

"""
